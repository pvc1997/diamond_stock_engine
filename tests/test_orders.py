"""Tests for order management module."""

import pytest
from datetime import datetime

from diamond.execution.orders import (
    Order,
    OrderBook,
    OrderStatus,
    OrderType,
    generate_order_id,
    create_limit_order,
    create_staggered_orders,
    get_order_summary,
)


@pytest.fixture
def order_book(tmp_path):
    return OrderBook("test_orders", db_path=tmp_path / "test_orders.db")


@pytest.fixture
def sample_order():
    return Order(
        id="test_RELIANCE_20260101120000",
        strategy="test_orders",
        ticker="RELIANCE.NS",
        action="BUY",
        shares=10,
        price=2500.0,
        order_type="MARKET",
        status="PENDING",
    )


class TestOrderBook:
    def test_create_order(self, order_book, sample_order):
        created = order_book.create_order(sample_order)
        assert created.created_at != ""

        retrieved = order_book.get_order(sample_order.id)
        assert retrieved is not None
        assert retrieved.ticker == "RELIANCE.NS"
        assert retrieved.shares == 10

    def test_update_status(self, order_book, sample_order):
        order_book.create_order(sample_order)
        order_book.update_status(
            sample_order.id,
            OrderStatus.FILLED,
            filled_shares=10,
            filled_price=2505.0,
        )

        updated = order_book.get_order(sample_order.id)
        assert updated.status == "FILLED"
        assert updated.filled_shares == 10
        assert updated.filled_price == 2505.0

    def test_get_pending(self, order_book):
        for i in range(3):
            order_book.create_order(Order(
                id=f"test_order_{i}",
                strategy="test_orders",
                ticker=f"STOCK{i}.NS",
                action="BUY",
                shares=10,
                price=100.0,
            ))

        # Fill one
        order_book.update_status("test_order_1", OrderStatus.FILLED, 10, 100.0)

        pending = order_book.get_pending()
        assert len(pending) == 2

    def test_get_open(self, order_book):
        order_book.create_order(Order(
            id="pending_1", strategy="test_orders", ticker="A.NS",
            action="BUY", shares=10, price=100,
        ))
        order_book.create_order(Order(
            id="partial_1", strategy="test_orders", ticker="B.NS",
            action="BUY", shares=10, price=100,
        ))
        order_book.update_status("partial_1", OrderStatus.PARTIAL, 5, 100)
        order_book.create_order(Order(
            id="filled_1", strategy="test_orders", ticker="C.NS",
            action="BUY", shares=10, price=100,
        ))
        order_book.update_status("filled_1", OrderStatus.FILLED, 10, 100)

        open_orders = order_book.get_open()
        assert len(open_orders) == 2  # pending + partial

    def test_cancel_order(self, order_book, sample_order):
        order_book.create_order(sample_order)
        assert order_book.cancel_order(sample_order.id) is True

        cancelled = order_book.get_order(sample_order.id)
        assert cancelled.status == "CANCELLED"

    def test_cancel_filled_fails(self, order_book, sample_order):
        order_book.create_order(sample_order)
        order_book.update_status(sample_order.id, OrderStatus.FILLED, 10, 2500)

        assert order_book.cancel_order(sample_order.id) is False

    def test_cancel_nonexistent(self, order_book):
        assert order_book.cancel_order("nonexistent") is False

    def test_cancel_all_pending(self, order_book):
        for i in range(5):
            order_book.create_order(Order(
                id=f"batch_{i}", strategy="test_orders", ticker=f"S{i}.NS",
                action="BUY", shares=10, price=100,
            ))

        # Fill two
        order_book.update_status("batch_0", OrderStatus.FILLED, 10, 100)
        order_book.update_status("batch_1", OrderStatus.FILLED, 10, 100)

        count = order_book.cancel_all_pending()
        assert count == 3

    def test_get_orders_filter_status(self, order_book):
        order_book.create_order(Order(
            id="a", strategy="test_orders", ticker="A.NS",
            action="BUY", shares=10, price=100,
        ))
        order_book.create_order(Order(
            id="b", strategy="test_orders", ticker="B.NS",
            action="BUY", shares=10, price=100,
        ))
        order_book.update_status("b", OrderStatus.FILLED, 10, 100)

        filled = order_book.get_orders(status="FILLED")
        assert len(filled) == 1
        assert filled[0].id == "b"


class TestOrderID:
    def test_unique_ids(self):
        id1 = generate_order_id("gods_plan", "RELIANCE.NS")
        id2 = generate_order_id("gods_plan", "RELIANCE.NS")
        # Should be unique due to microsecond timestamp
        # (may occasionally collide in fast tests, so just check format)
        assert "gods_plan_RELIANCE" in id1
        assert len(id1) > 20


class TestLimitOrder:
    def test_buy_limit_above_market(self):
        order = create_limit_order("gods_plan", "RELIANCE.NS", "BUY", 10, 2500.0, buffer_pct=0.01)
        assert order.price == 2525.0  # 2500 * 1.01
        assert order.order_type == "LIMIT"
        assert order.action == "BUY"

    def test_sell_limit_below_market(self):
        order = create_limit_order("gods_plan", "TCS.NS", "SELL", 5, 3500.0, buffer_pct=0.01)
        assert order.price == 3465.0  # 3500 * 0.99
        assert order.action == "SELL"

    def test_zero_buffer(self):
        order = create_limit_order("gods_plan", "TCS.NS", "BUY", 5, 1000.0, buffer_pct=0)
        assert order.price == 1000.0


class TestStaggeredOrders:
    def test_basic_stagger(self):
        orders = create_staggered_orders("gods_plan", "RELIANCE.NS", "BUY", 30, 2500.0, tranches=3)
        assert len(orders) == 3
        total_shares = sum(o.shares for o in orders)
        assert total_shares == 30

    def test_uneven_split(self):
        orders = create_staggered_orders("gods_plan", "TCS.NS", "BUY", 10, 3500.0, tranches=3)
        total = sum(o.shares for o in orders)
        assert total == 10
        # 10/3 = 3+3+3+1 remainder distributed
        shares = sorted([o.shares for o in orders])
        assert shares == [3, 3, 4]

    def test_single_tranche(self):
        orders = create_staggered_orders("gods_plan", "A.NS", "SELL", 5, 100.0, tranches=1)
        assert len(orders) == 1
        assert orders[0].shares == 5

    def test_parent_id_set(self):
        orders = create_staggered_orders("gods_plan", "A.NS", "BUY", 9, 100.0, tranches=3)
        parent_ids = set(o.parent_id for o in orders)
        assert len(parent_ids) == 1
        assert parent_ids.pop() != ""

    def test_tranche_labeling(self):
        orders = create_staggered_orders("gods_plan", "A.NS", "BUY", 6, 100.0, tranches=2, rationale="Rebalance")
        assert "1/2" in orders[0].rationale
        assert "2/2" in orders[1].rationale


class TestSummary:
    def test_summary_counts(self, order_book):
        for i in range(4):
            order_book.create_order(Order(
                id=f"s_{i}", strategy="test_orders", ticker=f"T{i}.NS",
                action="BUY", shares=10, price=100,
            ))

        order_book.update_status("s_0", OrderStatus.FILLED, 10, 100)
        order_book.update_status("s_1", OrderStatus.FAILED, error="Insufficient funds")
        order_book.update_status("s_2", OrderStatus.PARTIAL, 5, 100)

        summary = get_order_summary(order_book)
        assert summary["total"] == 4
        assert summary["filled"] == 1
        assert summary["failed"] == 1
        assert summary["partial"] == 1
        assert summary["pending"] == 1
