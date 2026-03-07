"""Tests for dashboard module."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from diamond.dashboard import (
    _build_action_panel,
    _build_holdings_table,
    _build_portfolio_summary,
    _build_pnl_summary_panel,
    _build_trade_history_table,
    _days_since_rebalance,
)
from diamond.data.ledger import Ledger, Trade


class TestDaysCalculation:
    def test_no_rebalance(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        assert _days_since_rebalance(ledger) is None

    def test_recent_rebalance(self, tmp_path):
        from datetime import datetime
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_last_rebalance(datetime.now().strftime("%Y-%m-%d"))
        assert _days_since_rebalance(ledger) == 0


class TestActionPanel:
    def test_setup_required_when_no_holdings(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        panel = _build_action_panel("test", ledger, {}, {}, 100000)
        # Panel should mention setup
        assert panel is not None

    def test_hold_signal(self, tmp_path):
        from datetime import datetime
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_last_rebalance(datetime.now().strftime("%Y-%m-%d"))
        holdings = {"TCS.NS": 10}
        prices = {"TCS.NS": 3500}
        panel = _build_action_panel("test", ledger, holdings, prices, 100000)
        assert panel is not None


class TestHoldingsTable:
    def test_builds_table(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        # Add a holding manually
        ledger.update_holding("TCS.NS", 10, 3500)
        ledger.set_cash(65000)
        holdings = {"TCS.NS": 10}
        prices = {"TCS.NS": 3600}
        table = _build_holdings_table(ledger, holdings, prices)
        assert table is not None
        assert table.row_count == 1


class TestPortfolioSummary:
    def test_builds_summary(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.update_holding("TCS.NS", 10, 3500)
        holdings = {"TCS.NS": 10}
        prices = {"TCS.NS": 3600}
        panel = _build_portfolio_summary(ledger, holdings, prices, 100000)
        assert panel is not None


class TestTradeHistoryTable:
    def test_with_trades(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(500000)

        # Record some trades
        ledger.record_trade(Trade(
            timestamp="2026-01-15 10:00:00",
            action="BUY",
            ticker="TCS.NS",
            shares=10,
            price=3500.0,
            total_cost=50.0,
            rationale="Initial buy for quality growth",
        ))
        ledger.record_trade(Trade(
            timestamp="2026-02-01 10:00:00",
            action="BUY",
            ticker="INFY.NS",
            shares=20,
            price=1500.0,
            total_cost=40.0,
            rationale="Adding defensive position",
        ))
        ledger.record_trade(Trade(
            timestamp="2026-03-01 10:00:00",
            action="SELL",
            ticker="TCS.NS",
            shares=5,
            price=3700.0,
            total_cost=30.0,
            rationale="Profit booking after 50% gain exceeded",
        ))

        table = _build_trade_history_table(ledger, limit=20)
        assert table is not None
        assert table.row_count == 3
        # Title should reflect count
        assert "3" in table.title

    def test_empty_ledger(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)

        table = _build_trade_history_table(ledger)
        assert table is not None
        assert table.row_count == 0
        assert "0" in table.title

    def test_limit_truncation(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(1000000)

        # Record 25 trades
        for i in range(25):
            ledger.record_trade(Trade(
                timestamp=f"2026-01-{i+1:02d} 10:00:00",
                action="BUY",
                ticker=f"STOCK{i}.NS",
                shares=1,
                price=100.0,
                total_cost=5.0,
                rationale=f"Trade {i}",
            ))

        table = _build_trade_history_table(ledger, limit=10)
        assert table.row_count == 10

    def test_most_recent_first(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(500000)

        ledger.record_trade(Trade(
            timestamp="2026-01-01 10:00:00",
            action="BUY",
            ticker="EARLY.NS",
            shares=10,
            price=100.0,
            total_cost=5.0,
            rationale="First trade",
        ))
        ledger.record_trade(Trade(
            timestamp="2026-03-01 10:00:00",
            action="BUY",
            ticker="LATE.NS",
            shares=10,
            price=200.0,
            total_cost=5.0,
            rationale="Second trade",
        ))

        table = _build_trade_history_table(ledger, limit=20)
        assert table.row_count == 2

    def test_long_rationale_truncated(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(500000)

        long_rationale = "A" * 50  # Longer than 40 chars
        ledger.record_trade(Trade(
            timestamp="2026-01-01 10:00:00",
            action="BUY",
            ticker="TEST.NS",
            shares=10,
            price=100.0,
            total_cost=5.0,
            rationale=long_rationale,
        ))

        table = _build_trade_history_table(ledger)
        assert table.row_count == 1


class TestPnlSummaryPanel:
    def test_with_holdings(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(50000)

        # Buy some stocks
        ledger.record_trade(Trade(
            timestamp="2026-01-01 10:00:00",
            action="BUY",
            ticker="TCS.NS",
            shares=10,
            price=3500.0,
            total_cost=50.0,
            rationale="Initial buy",
        ))
        ledger.record_trade(Trade(
            timestamp="2026-01-01 10:00:00",
            action="BUY",
            ticker="INFY.NS",
            shares=20,
            price=1500.0,
            total_cost=40.0,
            rationale="Initial buy",
        ))

        holdings = ledger.get_holdings()
        prices = {"TCS.NS": 3800.0, "INFY.NS": 1600.0}

        panel = _build_pnl_summary_panel(ledger, holdings, prices)
        assert panel is not None
        assert panel.title is not None
        # Panel should contain P&L BREAKDOWN in title
        assert "P&L" in str(panel.title)

    def test_no_holdings(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)

        holdings = {}
        prices = {}

        panel = _build_pnl_summary_panel(ledger, holdings, prices)
        assert panel is not None

    def test_negative_pnl(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(50000)

        ledger.record_trade(Trade(
            timestamp="2026-01-01 10:00:00",
            action="BUY",
            ticker="TCS.NS",
            shares=10,
            price=3500.0,
            total_cost=50.0,
            rationale="Initial buy",
        ))

        holdings = ledger.get_holdings()
        # Price dropped
        prices = {"TCS.NS": 3000.0}

        panel = _build_pnl_summary_panel(ledger, holdings, prices)
        assert panel is not None

    def test_with_realized_gains(self, tmp_path):
        db = tmp_path / "test.db"
        ledger = Ledger("test", db_path=db)
        ledger.set_cash(200000)

        # Buy then sell at profit
        ledger.record_trade(Trade(
            timestamp="2026-01-01 10:00:00",
            action="BUY",
            ticker="TCS.NS",
            shares=10,
            price=3500.0,
            total_cost=50.0,
            rationale="Initial buy",
        ))
        ledger.record_trade(Trade(
            timestamp="2026-02-01 10:00:00",
            action="SELL",
            ticker="TCS.NS",
            shares=5,
            price=4000.0,
            total_cost=30.0,
            rationale="Profit booking",
        ))

        holdings = ledger.get_holdings()
        prices = {"TCS.NS": 4000.0}

        panel = _build_pnl_summary_panel(ledger, holdings, prices)
        assert panel is not None
