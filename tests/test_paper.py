"""Tests for paper trading mode."""

from pathlib import Path
from unittest.mock import patch

from diamond.data.ledger import Ledger, Trade
from diamond.execution.paper import (
    PAPER_SUFFIX,
    _paper_strategy_name,
    execute_paper,
    get_paper_nav,
    get_paper_status,
    reset_paper,
)


class TestPaperNaming:
    def test_adds_suffix(self):
        assert _paper_strategy_name("passive") == "passive_paper"

    def test_no_double_suffix(self):
        assert _paper_strategy_name("passive_paper") == "passive_paper"


class TestPaperStatus:
    def test_fresh_status(self, tmp_path: Path):
        with patch("diamond.execution.paper.Ledger") as MockLedger:
            mock = MockLedger.return_value
            mock.get_holdings.return_value = {}
            mock.get_cash.return_value = 100_000.0
            mock.get_total_fees.return_value = 0.0
            mock.get_trades.return_value = []
            mock.get_last_rebalance.return_value = ""
            mock.get_initial_capital.return_value = 100_000.0

            status = get_paper_status("passive")
            assert status["strategy"] == "passive_paper"
            assert status["cash"] == 100_000.0
            assert status["holdings_count"] == 0


class TestPaperTrading:
    def test_paper_ledger_isolation(self, tmp_path: Path):
        """Paper ledger should be separate from real ledger."""
        real = Ledger("test_iso", db_path=tmp_path / "test_iso.db")
        paper = Ledger("test_iso_paper", db_path=tmp_path / "test_iso_paper.db")

        # Trade on paper
        paper.record_trade(Trade(
            "2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Paper buy",
        ))

        # Real ledger should be untouched
        assert real.get_holdings() == {}
        assert paper.get_holdings() == {"RELIANCE.NS": 10}

    def test_paper_nav(self, tmp_path: Path):
        """Paper NAV uses ledger portfolio value."""
        with patch("diamond.execution.paper.Ledger") as MockLedger:
            mock = MockLedger.return_value
            mock.get_holdings.return_value = {"RELIANCE.NS": 10}
            mock.get_portfolio_value.return_value = 125_000.0

            nav = get_paper_nav("passive", {"RELIANCE.NS": 2500.0})
            assert nav == 125_000.0

    def test_reset_paper(self, tmp_path: Path):
        """Reset should clear paper portfolio."""
        paper = Ledger("test_reset_paper", db_path=tmp_path / "test_reset_paper.db")
        paper.record_trade(Trade(
            "2024-01-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Paper buy",
        ))

        paper.reset(initial_capital=200_000)
        assert paper.get_holdings() == {}
        assert paper.get_cash() == 200_000
