"""Order management — lifecycle tracking, limit orders, staggered entry.

Tracks order state from PENDING -> PLACED -> FILLED/PARTIAL/FAILED/CANCELLED.
Supports limit orders with configurable price buffers, and staggered entry
for large positions (split into multiple smaller orders).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from diamond.config import get_config

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class Order:
    """Represents a single order in the system."""

    id: str  # Unique order ID (strategy_timestamp_ticker)
    strategy: str
    ticker: str
    action: str  # BUY or SELL
    shares: int  # Requested shares
    filled_shares: int = 0  # Actually filled
    price: float = 0.0  # Target/limit price
    filled_price: float = 0.0  # Average fill price
    order_type: str = "MARKET"  # MARKET or LIMIT
    status: str = "PENDING"
    broker_order_id: str = ""  # External broker order ID
    parent_id: str = ""  # For staggered orders: parent order ID
    created_at: str = ""
    updated_at: str = ""
    rationale: str = ""
    error: str = ""


class OrderBook:
    """SQLite-backed order book for tracking order lifecycle."""

    def __init__(self, strategy: str, db_path: Path | None = None):
        self.strategy = strategy
        cfg = get_config()
        self.db_path = db_path or cfg.data_dir / "orders" / f"{strategy}_orders.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    action TEXT NOT NULL,
                    shares INTEGER NOT NULL,
                    filled_shares INTEGER DEFAULT 0,
                    price REAL DEFAULT 0,
                    filled_price REAL DEFAULT 0,
                    order_type TEXT DEFAULT 'MARKET',
                    status TEXT DEFAULT 'PENDING',
                    broker_order_id TEXT DEFAULT '',
                    parent_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    rationale TEXT DEFAULT '',
                    error TEXT DEFAULT ''
                )
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def create_order(self, order: Order) -> Order:
        """Insert a new order into the book."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order.created_at = now
        order.updated_at = now

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO orders (id, strategy, ticker, action, shares, filled_shares,
                   price, filled_price, order_type, status, broker_order_id, parent_id,
                   created_at, updated_at, rationale, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order.id,
                    order.strategy,
                    order.ticker,
                    order.action,
                    order.shares,
                    order.filled_shares,
                    order.price,
                    order.filled_price,
                    order.order_type,
                    order.status,
                    order.broker_order_id,
                    order.parent_id,
                    order.created_at,
                    order.updated_at,
                    order.rationale,
                    order.error,
                ),
            )
        return order

    def update_status(
        self,
        order_id: str,
        status: str,
        filled_shares: int = 0,
        filled_price: float = 0,
        broker_order_id: str = "",
        error: str = "",
    ) -> None:
        """Update order status and fill info."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                """UPDATE orders SET status = ?, filled_shares = ?,
                   filled_price = ?, broker_order_id = ?, error = ?,
                   updated_at = ? WHERE id = ?""",
                (status, filled_shares, filled_price, broker_order_id, error, now, order_id),
            )

    def get_order(self, order_id: str) -> Order | None:
        """Get a single order by ID."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row:
                return self._row_to_order(row)
        return None

    def get_orders(self, status: str | None = None, since: str | None = None) -> list[Order]:
        """Get orders, optionally filtered by status and/or date."""
        with self._conn() as conn:
            query = "SELECT * FROM orders WHERE strategy = ?"
            params: list = [self.strategy]

            if status:
                query += " AND status = ?"
                params.append(status)
            if since:
                query += " AND created_at >= ?"
                params.append(since)

            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_order(r) for r in rows]

    def get_pending(self) -> list[Order]:
        """Get all pending orders."""
        return self.get_orders(status=OrderStatus.PENDING)

    def get_open(self) -> list[Order]:
        """Get all open orders (PENDING + PLACED + PARTIAL)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE strategy = ? AND status IN (?, ?, ?) ORDER BY created_at",
                (self.strategy, OrderStatus.PENDING, OrderStatus.PLACED, OrderStatus.PARTIAL),
            ).fetchall()
            return [self._row_to_order(r) for r in rows]

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order. Returns True if order was cancellable."""
        order = self.get_order(order_id)
        if not order:
            return False
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return False
        self.update_status(order_id, OrderStatus.CANCELLED)
        return True

    def cancel_all_pending(self) -> int:
        """Cancel all pending orders. Returns count cancelled."""
        pending = self.get_pending()
        for order in pending:
            self.cancel_order(order.id)
        return len(pending)

    def _row_to_order(self, row: tuple) -> Order:
        return Order(
            id=row[0],
            strategy=row[1],
            ticker=row[2],
            action=row[3],
            shares=row[4],
            filled_shares=row[5],
            price=row[6],
            filled_price=row[7],
            order_type=row[8],
            status=row[9],
            broker_order_id=row[10],
            parent_id=row[11],
            created_at=row[12],
            updated_at=row[13],
            rationale=row[14],
            error=row[15],
        )


def generate_order_id(strategy: str, ticker: str) -> str:
    """Generate a unique order ID."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")[:18]
    clean_ticker = ticker.replace(".NS", "").replace(".BO", "")
    return f"{strategy}_{clean_ticker}_{ts}"


def create_limit_order(
    strategy: str,
    ticker: str,
    action: str,
    shares: int,
    current_price: float,
    buffer_pct: float = 0.005,
    rationale: str = "",
) -> Order:
    """Create a limit order with price buffer.

    For BUY: limit = current_price * (1 + buffer_pct)  (slightly above market)
    For SELL: limit = current_price * (1 - buffer_pct)  (slightly below market)
    """
    if action == "BUY":
        limit_price = round(current_price * (1 + buffer_pct), 2)
    else:
        limit_price = round(current_price * (1 - buffer_pct), 2)

    return Order(
        id=generate_order_id(strategy, ticker),
        strategy=strategy,
        ticker=ticker,
        action=action,
        shares=shares,
        price=limit_price,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        rationale=rationale,
    )


def create_staggered_orders(
    strategy: str,
    ticker: str,
    action: str,
    total_shares: int,
    current_price: float,
    tranches: int = 3,
    rationale: str = "",
) -> list[Order]:
    """Split a large order into multiple smaller tranches.

    Useful for reducing market impact on large positions.

    Args:
        tranches: Number of sub-orders to create (default 3)
    """
    if tranches < 1:
        tranches = 1

    parent_id = generate_order_id(strategy, ticker)
    shares_per = total_shares // tranches
    remainder = total_shares % tranches

    orders = []
    for i in range(tranches):
        tranche_shares = shares_per + (1 if i < remainder else 0)
        if tranche_shares <= 0:
            continue

        order = Order(
            id=generate_order_id(strategy, f"{ticker}_t{i + 1}"),
            strategy=strategy,
            ticker=ticker,
            action=action,
            shares=tranche_shares,
            price=current_price,
            order_type=OrderType.MARKET,
            status=OrderStatus.PENDING,
            parent_id=parent_id,
            rationale=f"{rationale} (tranche {i + 1}/{tranches})" if rationale else f"Tranche {i + 1}/{tranches}",
        )
        orders.append(order)

    return orders


def get_order_summary(book: OrderBook) -> dict:
    """Get summary statistics for the order book."""
    all_orders = book.get_orders()

    summary = {
        "total": len(all_orders),
        "pending": 0,
        "placed": 0,
        "filled": 0,
        "partial": 0,
        "failed": 0,
        "cancelled": 0,
        "total_value": 0.0,
        "filled_value": 0.0,
    }

    for order in all_orders:
        status_key = order.status.lower()
        if status_key in summary:
            summary[status_key] += 1
        summary["total_value"] += order.shares * order.price
        summary["filled_value"] += order.filled_shares * order.filled_price

    return summary
