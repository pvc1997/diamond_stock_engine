"""Trade ledger backed by SQLite.

Single-file database per strategy. ACID transactions, queryable history.
"""

from __future__ import annotations

import fcntl
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from diamond.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    timestamp: str
    action: str  # BUY or SELL
    ticker: str
    shares: int
    price: float
    total_cost: float  # Transaction costs (brokerage + taxes)
    rationale: str


class Ledger:
    """SQLite-backed trade ledger for a single strategy."""

    def __init__(self, strategy: str, db_path: Path | None = None):
        self.strategy = strategy
        self.db_path = db_path or get_config().ledger_path(strategy)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
                    ticker TEXT NOT NULL,
                    shares INTEGER NOT NULL,
                    price REAL NOT NULL,
                    total_cost REAL NOT NULL DEFAULT 0,
                    rationale TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS holdings (
                    ticker TEXT PRIMARY KEY,
                    shares INTEGER NOT NULL DEFAULT 0,
                    avg_price REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            # Initialize cash if not present
            cur = conn.execute("SELECT value FROM state WHERE key = 'cash'")
            if cur.fetchone() is None:
                capital = get_config().risk.initial_capital
                conn.execute(
                    "INSERT INTO state (key, value) VALUES ('cash', ?)",
                    (str(capital),),
                )
                conn.execute(
                    "INSERT INTO state (key, value) VALUES ('initial_capital', ?)",
                    (str(capital),),
                )
                conn.execute(
                    "INSERT INTO state (key, value) VALUES ('last_rebalance', '')",
                )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    @contextmanager
    def _write_lock(self, timeout: float = 10.0):
        """Acquire an exclusive file lock for write operations.

        Uses fcntl.flock() on a .lock file adjacent to the database.
        Timeout after ``timeout`` seconds with a clear error message.
        """
        lock_path = Path(f"{self.db_path}.lock")
        lock_file = open(lock_path, "w")  # noqa: SIM115
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        lock_file.close()
                        raise TimeoutError(
                            f"Could not acquire ledger write lock on {self.db_path} "
                            f"within {timeout}s — another process may be writing."
                        ) from None
                    time.sleep(0.05)
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()

    # --- State ---

    def get_cash(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = 'cash'").fetchone()
            return float(row[0]) if row else 0.0

    def set_cash(self, amount: float) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE state SET value = ? WHERE key = 'cash'", (str(amount),))

    def get_initial_capital(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = 'initial_capital'").fetchone()
            return float(row[0]) if row else get_config().risk.initial_capital

    def get_last_rebalance(self) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = 'last_rebalance'").fetchone()
            return row[0] if row else ""

    def set_last_rebalance(self, date_str: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE state SET value = ? WHERE key = 'last_rebalance'", (date_str,))

    # --- Holdings ---

    def get_holdings(self) -> dict[str, int]:
        """Return {ticker: shares} for all current positions."""
        with self._conn() as conn:
            rows = conn.execute("SELECT ticker, shares FROM holdings WHERE shares > 0").fetchall()
            return {row[0]: row[1] for row in rows}

    def get_avg_price(self, ticker: str) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT avg_price FROM holdings WHERE ticker = ?", (ticker,)).fetchone()
            return row[0] if row else 0.0

    def update_holding(self, ticker: str, shares_delta: int, price: float) -> None:
        """Update holding after a trade. Positive delta = buy, negative = sell."""
        with self._conn() as conn:
            row = conn.execute("SELECT shares, avg_price FROM holdings WHERE ticker = ?", (ticker,)).fetchone()

            if row:
                old_shares, old_avg = row[0], row[1]
                new_shares = old_shares + shares_delta
                if new_shares <= 0:
                    conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker,))
                else:
                    if shares_delta > 0:
                        # Weighted average cost on buy
                        new_avg = (old_shares * old_avg + shares_delta * price) / new_shares
                    else:
                        new_avg = old_avg  # Sell doesn't change avg cost
                    conn.execute(
                        "UPDATE holdings SET shares = ?, avg_price = ? WHERE ticker = ?",
                        (new_shares, new_avg, ticker),
                    )
            elif shares_delta > 0:
                conn.execute(
                    "INSERT INTO holdings (ticker, shares, avg_price) VALUES (?, ?, ?)",
                    (ticker, shares_delta, price),
                )

    # --- Trades ---

    def record_trade(self, trade: Trade) -> None:
        """Record a trade and update holdings + cash."""
        with self._write_lock():
            with self._conn() as conn:  # noqa: SIM117
                conn.execute(
                    """INSERT INTO trades (timestamp, action, ticker, shares, price, total_cost, rationale)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trade.timestamp,
                        trade.action,
                        trade.ticker,
                        trade.shares,
                        trade.price,
                        trade.total_cost,
                        trade.rationale,
                    ),
                )

            # Update holdings (needs its own connection — cannot nest with above)
            delta = trade.shares if trade.action == "BUY" else -trade.shares
            self.update_holding(trade.ticker, delta, trade.price)

            # Update cash
            cash = self.get_cash()
            if trade.action == "BUY":
                cash -= (trade.shares * trade.price) + trade.total_cost
            else:
                cash += (trade.shares * trade.price) - trade.total_cost
            self.set_cash(cash)

    def get_trades(self, since: str | None = None) -> list[Trade]:
        """Return trade history, optionally filtered by date."""
        with self._conn() as conn:
            if since:
                rows = conn.execute(
                    "SELECT timestamp, action, ticker, shares, price, total_cost, rationale "
                    "FROM trades WHERE timestamp >= ? ORDER BY timestamp",
                    (since,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT timestamp, action, ticker, shares, price, total_cost, rationale "
                    "FROM trades ORDER BY timestamp"
                ).fetchall()
            return [
                Trade(
                    timestamp=r[0],
                    action=r[1],
                    ticker=r[2],
                    shares=r[3],
                    price=r[4],
                    total_cost=r[5],
                    rationale=r[6],
                )
                for r in rows
            ]

    def get_total_fees(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT COALESCE(SUM(total_cost), 0) FROM trades").fetchone()
            return row[0]

    # --- Portfolio Value ---

    def get_portfolio_value(self, current_prices: dict[str, float]) -> float:
        """Calculate total portfolio value = cash + sum(shares * price)."""
        holdings = self.get_holdings()
        holdings_value = sum(shares * current_prices.get(ticker, 0) for ticker, shares in holdings.items())
        return self.get_cash() + holdings_value

    def write_off(self, ticker: str, rationale: str = "Delisted / write-off") -> bool:
        """Write off a holding (e.g. delisted stock). Records SELL at price 0, no cash change."""
        holdings = self.get_holdings()
        shares = holdings.get(ticker, 0)
        if shares <= 0:
            return False

        with self._write_lock(), self._conn() as conn:
            conn.execute(
                """INSERT INTO trades (timestamp, action, ticker, shares, price, total_cost, rationale)
                   VALUES (?, 'SELL', ?, ?, 0, 0, ?)""",
                (datetime.now().strftime("%Y-%m-%d"), ticker, shares, rationale),
            )
            conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker,))
        return True

    def backup(self, max_backups: int = 5) -> Path | None:
        """Create a timestamped backup of the ledger database.

        Keeps at most ``max_backups`` recent backups, deleting older ones.
        Returns the backup path, or None if backup failed.
        """
        if not self.db_path.exists():
            return None

        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = backup_dir / f"{self.db_path.stem}_{timestamp}.db"

        try:
            # Use SQLite's online backup API rather than copying the file.
            # The ledger runs in WAL mode, so a plain file copy misses every
            # write still sitting in the -wal sidecar and yields an empty DB.
            src = sqlite3.connect(self.db_path)
            try:
                dst = sqlite3.connect(backup_path)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            logger.info(f"Ledger backed up to {backup_path}")

            # Prune old backups
            pattern = f"{self.db_path.stem}_*.db"
            backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
            while len(backups) > max_backups:
                oldest = backups.pop(0)
                oldest.unlink()
                logger.debug(f"Pruned old backup: {oldest}")

            return backup_path
        except Exception as e:
            logger.warning(f"Ledger backup failed: {e}")
            return None

    def reset(self, initial_capital: float | None = None) -> None:
        """Reset ledger to initial state. Use with caution."""
        capital = initial_capital or get_config().risk.initial_capital
        with self._conn() as conn:
            conn.executescript(f"""
                DELETE FROM trades;
                DELETE FROM holdings;
                UPDATE state SET value = '{capital}' WHERE key = 'cash';
                UPDATE state SET value = '{capital}' WHERE key = 'initial_capital';
                UPDATE state SET value = '' WHERE key = 'last_rebalance';
            """)
