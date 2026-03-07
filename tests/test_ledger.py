"""Tests for SQLite-backed trade ledger."""

import sqlite3
from pathlib import Path

from diamond.data.ledger import Ledger, Trade


class TestLedger:
    def test_initial_cash(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        assert ledger.get_cash() == 100000  # default from config

    def test_record_buy(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade(
            timestamp="2024-01-15",
            action="BUY",
            ticker="RELIANCE.NS",
            shares=10,
            price=2500.0,
            total_cost=50.0,
            rationale="Test buy",
        )
        ledger.record_trade(trade)

        holdings = ledger.get_holdings()
        assert holdings["RELIANCE.NS"] == 10
        assert ledger.get_cash() == 100000 - (10 * 2500) - 50  # 74950

    def test_record_sell(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")

        # Buy first
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))
        # Sell partial
        ledger.record_trade(Trade("2024-02-15", "SELL", "TCS.NS", 3, 3100.0, 20.0, "Sell"))

        holdings = ledger.get_holdings()
        assert holdings["TCS.NS"] == 2

    def test_sell_all_removes_holding(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "INFY.NS", 5, 1500.0, 15.0, "Buy"))
        ledger.record_trade(Trade("2024-02-15", "SELL", "INFY.NS", 5, 1600.0, 10.0, "Sell"))

        holdings = ledger.get_holdings()
        assert "INFY.NS" not in holdings

    def test_get_trades(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        ledger.record_trade(Trade("2024-02-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))

        trades = ledger.get_trades()
        assert len(trades) == 2
        assert trades[0].ticker == "RELIANCE.NS"

    def test_get_trades_since(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        ledger.record_trade(Trade("2024-03-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))

        trades = ledger.get_trades(since="2024-02-01")
        assert len(trades) == 1
        assert trades[0].ticker == "TCS.NS"

    def test_total_fees(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        ledger.record_trade(Trade("2024-02-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))

        assert ledger.get_total_fees() == 80.0

    def test_avg_price_on_buy(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 0, "Buy"))
        ledger.record_trade(Trade("2024-02-15", "BUY", "RELIANCE.NS", 10, 2600.0, 0, "Buy"))

        avg = ledger.get_avg_price("RELIANCE.NS")
        assert avg == 2550.0  # Weighted average

    def test_portfolio_value(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        prices = {"RELIANCE.NS": 2600.0}
        value = ledger.get_portfolio_value(prices)
        cash = 100000 - (10 * 2500) - 50  # 74950
        expected = cash + (10 * 2600)      # 74950 + 26000 = 100950
        assert value == expected

    def test_reset(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        ledger.reset(initial_capital=200000)

        assert ledger.get_cash() == 200000
        assert ledger.get_holdings() == {}
        assert ledger.get_trades() == []

    def test_last_rebalance(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        assert ledger.get_last_rebalance() == ""

        ledger.set_last_rebalance("2024-03-01")
        assert ledger.get_last_rebalance() == "2024-03-01"


class TestLedgerBackup:
    def test_backup_creates_file(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        backup_path = ledger.backup()
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.suffix == ".db"
        assert "backups" in str(backup_path.parent)

    def test_backup_is_valid_db(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        backup_path = ledger.backup()
        conn = sqlite3.connect(backup_path)
        count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        conn.close()
        assert count == 1

    def test_backup_prunes_old(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))

        # Create 7 backups with max_backups=3
        for _ in range(7):
            ledger.backup(max_backups=3)

        backup_dir = tmp_path / "backups"
        backups = list(backup_dir.glob("test_*.db"))
        assert len(backups) == 3

    def test_backup_no_db_returns_none(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "nonexistent.db")
        # Remove the db that _init_db created
        ledger.db_path.unlink()
        assert ledger.backup() is None

    def test_backup_default_max(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        for _ in range(8):
            ledger.backup()
        backup_dir = tmp_path / "backups"
        assert len(list(backup_dir.glob("test_*.db"))) == 5  # default max


class TestLedgerConcurrency:
    """Tests for WAL mode, busy_timeout, and file locking."""

    def test_wal_mode_enabled(self, tmp_path: Path):
        """Verify that WAL journal mode is set on new connections."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        conn = ledger._conn()
        result = conn.execute("PRAGMA journal_mode;").fetchone()
        assert result[0] == "wal"
        conn.close()

    def test_busy_timeout_set(self, tmp_path: Path):
        """Verify busy_timeout pragma is applied."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        conn = ledger._conn()
        result = conn.execute("PRAGMA busy_timeout;").fetchone()
        assert result[0] == 5000
        conn.close()

    def test_write_lock_creates_lock_file(self, tmp_path: Path):
        """Write lock should create a .lock file next to the database."""
        db_path = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db_path)
        lock_path = Path(f"{db_path}.lock")

        ledger.record_trade(
            Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Test")
        )
        assert lock_path.exists()

    def test_write_lock_does_not_deadlock_on_sequential_writes(self, tmp_path: Path):
        """Multiple sequential writes should not deadlock."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        for i in range(5):
            ledger.record_trade(
                Trade(f"2024-01-{15 + i:02d}", "BUY", "RELIANCE.NS", 1, 2500.0, 5.0, f"Buy {i}")
            )
        assert ledger.get_holdings()["RELIANCE.NS"] == 5

    def test_write_off_uses_lock(self, tmp_path: Path):
        """write_off should complete successfully under file locking."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(
            Trade("2024-01-15", "BUY", "DELISTED.NS", 10, 100.0, 5.0, "Buy")
        )
        assert ledger.write_off("DELISTED.NS")
        assert "DELISTED.NS" not in ledger.get_holdings()

    def test_concurrent_readers_with_wal(self, tmp_path: Path):
        """WAL mode should allow reads while a connection exists."""
        db_path = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db_path)
        ledger.record_trade(
            Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy")
        )

        # Open two read connections simultaneously — WAL allows this
        conn1 = sqlite3.connect(db_path)
        conn1.execute("PRAGMA journal_mode=WAL;")
        conn2 = sqlite3.connect(db_path)
        conn2.execute("PRAGMA journal_mode=WAL;")

        r1 = conn1.execute("SELECT COUNT(*) FROM trades").fetchone()
        r2 = conn2.execute("SELECT COUNT(*) FROM trades").fetchone()
        assert r1[0] == 1
        assert r2[0] == 1

        conn1.close()
        conn2.close()
