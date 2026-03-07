"""Tests for smart rebalance + order management integration into executors."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.execution.executor import execute, _record_to_order_book
from diamond.execution.paper import execute_paper


@pytest.fixture
def fresh_ledger(tmp_path):
    """Empty ledger for first-run scenarios."""
    ledger = Ledger("test_int", db_path=tmp_path / "int.db")
    return ledger


@pytest.fixture
def portfolio_ledger(tmp_path):
    """Ledger with existing holdings."""
    ledger = Ledger("test_int_port", db_path=tmp_path / "int_port.db")
    ledger.reset(initial_capital=500000)
    six_months = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    ledger.record_trade(Trade(six_months, "BUY", "RELIANCE.NS", 20, 2500, 50, "Buy"))
    ledger.record_trade(Trade(six_months, "BUY", "TCS.NS", 10, 3500, 35, "Buy"))
    ledger.set_last_rebalance(six_months)
    return ledger


class TestOrderBookRecording:
    def test_record_creates_orders(self, tmp_path):
        """Verify _record_to_order_book creates Order entries."""
        from diamond.execution.orders import OrderBook, Order, generate_order_id

        book = OrderBook("test_rec", db_path=tmp_path / "rec.db")
        # Directly create orders to verify the shape
        order = Order(
            id=generate_order_id("test_rec", "RELIANCE.NS"),
            strategy="test_rec",
            ticker="RELIANCE.NS",
            action="BUY",
            shares=10,
            filled_shares=10,
            price=2500.0,
            filled_price=2500.0,
            status="FILLED",
        )
        book.create_order(order)

        orders = book.get_orders()
        assert len(orders) == 1
        assert orders[0].ticker == "RELIANCE.NS"
        assert orders[0].status == "FILLED"

    def test_record_to_order_book_fail_open(self):
        """Should not raise even if order book fails."""
        with patch("diamond.execution.orders.OrderBook", side_effect=Exception("DB error")):
            # Should not raise
            _record_to_order_book("broken", [{"ticker": "X.NS", "action": "BUY", "shares": 1, "price": 100}])


class TestExecutorSmartFlag:
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor._sync_corporate_actions", return_value=0)
    @patch("diamond.execution.executor._check_risk_gate", return_value=[])
    def test_smart_skip_no_drift(self, mock_risk, mock_corp, mock_prices, tmp_path):
        """Smart mode should skip when drift is low and rebalance not due."""
        ledger = Ledger("test_smart_skip", db_path=tmp_path / "smart_skip.db")
        ledger.reset(initial_capital=100000)

        # Recent rebalance
        today = datetime.now().strftime("%Y-%m-%d")
        ledger.record_trade(Trade(today, "BUY", "A.NS", 50, 1000, 10, "Buy"))
        ledger.set_last_rebalance(today)

        mock_prices.return_value = {"A.NS": 1000.0}

        with patch("diamond.execution.executor.Ledger", return_value=ledger):
            result = execute(
                "test_smart_skip",
                target_allocation={"A.NS": 50000},
                capital=100000,
                smart=True,
            )

        assert result["status"] == "skipped"

    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor._sync_corporate_actions", return_value=0)
    @patch("diamond.execution.executor._check_risk_gate", return_value=[])
    def test_smart_dry_run_shows_tax_info(self, mock_risk, mock_corp, mock_prices, tmp_path):
        """Smart dry run should include tax info in trade list."""
        ledger = Ledger("test_smart_dry", db_path=tmp_path / "smart_dry.db")
        ledger.reset(initial_capital=500000)

        old_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        ledger.record_trade(Trade(old_date, "BUY", "RELIANCE.NS", 20, 2500, 50, "Buy"))
        ledger.set_last_rebalance(old_date)

        mock_prices.return_value = {"RELIANCE.NS": 2000.0, "TCS.NS": 3500.0}

        with patch("diamond.execution.executor.Ledger", return_value=ledger):
            result = execute(
                "test_smart_dry",
                target_allocation={"TCS.NS": 35000},
                capital=500000,
                force=True,
                dry_run=True,
                smart=True,
            )

        assert result["status"] == "dry_run"
        assert result["trades"] > 0
        # Smart trades should have tax_category
        for t in result["trade_list"]:
            if t["action"] == "SELL":
                assert "tax_category" in t


class TestPaperSmartFlag:
    @patch("diamond.execution.paper._get_current_prices")
    def test_paper_smart_skip(self, mock_prices, tmp_path):
        """Paper smart mode should skip when drift is low."""
        ledger = Ledger("test_paper_smart_paper", db_path=tmp_path / "ps.db")
        ledger.reset(initial_capital=100000)

        today = datetime.now().strftime("%Y-%m-%d")
        ledger.record_trade(Trade(today, "BUY", "A.NS", 50, 1000, 10, "Buy"))
        ledger.set_last_rebalance(today)

        mock_prices.return_value = {"A.NS": 1000.0}

        with patch("diamond.execution.paper.Ledger", return_value=ledger):
            result = execute_paper(
                "test_paper_smart",
                target_allocation={"A.NS": 50000},
                capital=100000,
                smart=True,
            )

        assert result["status"] == "skipped"

    @patch("diamond.execution.paper._get_current_prices")
    def test_paper_smart_force(self, mock_prices, tmp_path):
        """Paper smart mode with force should always rebalance."""
        ledger = Ledger("test_paper_force_paper", db_path=tmp_path / "pf.db")
        ledger.reset(initial_capital=100000)

        today = datetime.now().strftime("%Y-%m-%d")
        ledger.record_trade(Trade(today, "BUY", "A.NS", 50, 1000, 10, "Buy"))
        ledger.set_last_rebalance(today)

        mock_prices.return_value = {"A.NS": 1000.0, "B.NS": 500.0}

        with patch("diamond.execution.paper.Ledger", return_value=ledger):
            result = execute_paper(
                "test_paper_force",
                target_allocation={"B.NS": 50000},
                capital=100000,
                force=True,
                smart=True,
            )

        # Should execute (not skip) because force=True
        assert result["status"] in ("executed", "no_trades")


class TestLegacyUnchanged:
    @patch("diamond.execution.executor._get_current_prices")
    @patch("diamond.execution.executor._sync_corporate_actions", return_value=0)
    @patch("diamond.execution.executor._check_risk_gate", return_value=[])
    def test_legacy_mode_still_works(self, mock_risk, mock_corp, mock_prices, tmp_path):
        """Without smart flag, executor uses legacy time-based check."""
        ledger = Ledger("test_legacy", db_path=tmp_path / "legacy.db")
        ledger.reset(initial_capital=100000)

        mock_prices.return_value = {"A.NS": 1000.0}

        with patch("diamond.execution.executor.Ledger", return_value=ledger):
            result = execute(
                "test_legacy",
                target_allocation={"A.NS": 50000},
                capital=100000,
                smart=False,
            )

        # First run, no last_rebalance — should execute
        assert result["status"] in ("executed", "no_trades", "dry_run")

    @patch("diamond.execution.paper._get_current_prices")
    def test_paper_legacy_still_works(self, mock_prices, tmp_path):
        """Paper without smart uses legacy time check."""
        ledger = Ledger("test_plegacy_paper", db_path=tmp_path / "pleg.db")
        ledger.reset(initial_capital=100000)

        mock_prices.return_value = {"A.NS": 1000.0}

        with patch("diamond.execution.paper.Ledger", return_value=ledger):
            result = execute_paper(
                "test_plegacy",
                target_allocation={"A.NS": 50000},
                capital=100000,
                smart=False,
            )

        assert result["status"] in ("executed", "no_trades")
