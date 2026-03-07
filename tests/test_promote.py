"""Tests for paper-to-live promotion workflow."""

from pathlib import Path
from unittest.mock import patch

from diamond.data.ledger import Ledger, Trade
from diamond.execution.promote import (
    PromotionReport,
    assess_promotion,
    promote,
    _MIN_DAYS,
    _MIN_TRADES,
)


class TestAssessPromotion:
    def test_no_paper_portfolio(self, tmp_path: Path):
        with patch("diamond.execution.promote.Ledger") as MockLedger:
            mock = MockLedger.return_value
            mock.get_holdings.return_value = {}

            report = assess_promotion("test")
            assert report.confidence == "low"
            assert report.recommended is False
            assert "No paper portfolio" in report.reasons[0]

    def test_returns_promotion_report(self, tmp_path: Path):
        with patch("diamond.execution.promote.Ledger") as MockLedger, \
             patch("diamond.execution.promote._get_current_prices") as mock_prices:
            paper_mock = MockLedger.return_value
            paper_mock.get_holdings.return_value = {"RELIANCE.NS": 10}
            paper_mock.get_portfolio_value.return_value = 110_000.0
            paper_mock.get_initial_capital.return_value = 100_000.0
            paper_mock.get_trades.return_value = [
                Trade("2024-01-01", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Paper"),
                Trade("2024-04-01", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Paper"),
            ]
            mock_prices.return_value = {"RELIANCE.NS": 2600.0}

            report = assess_promotion("test")
            assert isinstance(report, PromotionReport)
            assert report.paper_nav == 110_000.0
            assert report.paper_return_pct == 10.0


class TestPromote:
    def test_extracts_weights_from_paper(self, tmp_path: Path):
        with patch("diamond.execution.promote.Ledger") as MockLedger, \
             patch("diamond.execution.promote._get_current_prices") as mock_prices:
            mock = MockLedger.return_value
            mock.get_holdings.return_value = {"A.NS": 10, "B.NS": 20}
            mock.get_portfolio_value.return_value = 100_000.0
            mock.get_initial_capital.return_value = 100_000.0
            mock_prices.return_value = {"A.NS": 5000.0, "B.NS": 2500.0}

            allocation = promote("test", capital=200_000)

            # A: 10 * 5000 = 50000 -> 50% of 100k -> 100k of 200k
            # B: 20 * 2500 = 50000 -> 50% of 100k -> 100k of 200k
            assert abs(allocation["A.NS"] - 100_000) < 1
            assert abs(allocation["B.NS"] - 100_000) < 1

    def test_empty_paper_returns_empty(self):
        with patch("diamond.execution.promote.Ledger") as MockLedger:
            mock = MockLedger.return_value
            mock.get_holdings.return_value = {}

            assert promote("test") == {}
