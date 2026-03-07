"""Tests for the what-if scenario engine."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from diamond.daily.whatif import (
    ScenarioResult,
    StockImpact,
    AddCashResult,
    AlternativeResult,
    simulate_market_crash,
    simulate_add_cash,
    simulate_alternative,
    _fetch_portfolio_prices,
    _get_betas,
)


class TestSimulateMarketCrash:
    @patch("diamond.daily.whatif._get_betas")
    @patch("diamond.daily.whatif._fetch_portfolio_prices")
    @patch("diamond.data.ledger.Ledger")
    def test_crash_10pct(self, MockLedger, mock_prices, mock_betas):
        MockLedger.return_value.get_holdings.return_value = {"RELIANCE.NS": 10, "TCS.NS": 5}
        MockLedger.return_value.get_cash.return_value = 50000

        mock_prices.return_value = {"RELIANCE.NS": 2500, "TCS.NS": 3500}
        mock_betas.return_value = {"RELIANCE.NS": 1.0, "TCS.NS": 0.8}

        result = simulate_market_crash("test", crash_pct=-10, current_prices={"RELIANCE.NS": 2500, "TCS.NS": 3500})

        assert isinstance(result, ScenarioResult)
        assert result.change_inr < 0
        assert result.change_pct < 0
        assert len(result.stock_impacts) == 2

    @patch("diamond.daily.whatif._get_betas")
    @patch("diamond.data.ledger.Ledger")
    def test_rally_5pct(self, MockLedger, mock_betas):
        MockLedger.return_value.get_holdings.return_value = {"INFY.NS": 20}
        MockLedger.return_value.get_cash.return_value = 100000

        mock_betas.return_value = {"INFY.NS": 1.2}

        result = simulate_market_crash("test", crash_pct=5, current_prices={"INFY.NS": 1500})

        assert result.change_inr > 0
        assert result.change_pct > 0

    @patch("diamond.data.ledger.Ledger")
    def test_no_holdings(self, MockLedger):
        MockLedger.return_value.get_holdings.return_value = {}
        MockLedger.return_value.get_cash.return_value = 500000

        result = simulate_market_crash("test", crash_pct=-10)
        assert result.change_inr == 0
        assert "No holdings" in result.commentary

    @patch("diamond.daily.whatif._get_betas")
    @patch("diamond.data.ledger.Ledger")
    def test_beta_affects_impact(self, MockLedger, mock_betas):
        MockLedger.return_value.get_holdings.return_value = {"LOW.NS": 100, "HIGH.NS": 100}
        MockLedger.return_value.get_cash.return_value = 0

        mock_betas.return_value = {"LOW.NS": 0.5, "HIGH.NS": 1.5}
        prices = {"LOW.NS": 100, "HIGH.NS": 100}

        result = simulate_market_crash("test", crash_pct=-10, current_prices=prices)

        # HIGH beta stock should be hit harder
        low_impact = next(s for s in result.stock_impacts if s.ticker == "LOW.NS")
        high_impact = next(s for s in result.stock_impacts if s.ticker == "HIGH.NS")
        assert abs(high_impact.change_pct) > abs(low_impact.change_pct)


class TestSimulateAddCash:
    @patch("diamond.strategies.accumulate.plan_accumulation")
    @patch("diamond.daily.whatif._fetch_portfolio_prices", return_value={})
    @patch("diamond.data.ledger.Ledger")
    def test_add_50k(self, MockLedger, mock_prices, mock_plan):
        MockLedger.return_value.get_cash.return_value = 100000
        MockLedger.return_value.get_holdings.return_value = {}
        MockLedger.return_value.get_portfolio_value.return_value = 100000

        mock_plan.return_value = MagicMock(
            opportunities=[],
            total_positions_after=0,
        )

        result = simulate_add_cash("test", 50000)
        assert isinstance(result, AddCashResult)
        assert result.amount == 50000
        assert result.projected_nav == 150000

    @patch("diamond.strategies.accumulate.plan_accumulation")
    @patch("diamond.daily.whatif._fetch_portfolio_prices", return_value={})
    @patch("diamond.data.ledger.Ledger")
    def test_shows_buy_opportunities(self, MockLedger, mock_prices, mock_plan):
        MockLedger.return_value.get_cash.return_value = 50000
        MockLedger.return_value.get_holdings.return_value = {}
        MockLedger.return_value.get_portfolio_value.return_value = 50000

        opp = MagicMock()
        opp.ticker = "RELIANCE.NS"
        opp.suggested_amount = 30000
        opp.quality_score = 75
        opp.reason = "New position, Quality=75"

        mock_plan.return_value = MagicMock(
            opportunities=[opp],
            total_positions_after=1,
        )

        result = simulate_add_cash("test", 100000)
        assert len(result.would_buy) == 1
        assert result.would_buy[0]["ticker"] == "RELIANCE"


class TestSimulateAlternative:
    @patch("diamond.data.market.download_prices")
    @patch("diamond.data.ledger.Ledger")
    def test_compare_two_stocks(self, MockLedger, mock_dl):
        MockLedger.return_value.get_holdings.return_value = {"RELIANCE.NS": 10}
        MockLedger.return_value.get_avg_price.return_value = 2000

        mock_dl.return_value = pd.DataFrame({
            "RELIANCE.NS": [2000, 2100, 2200],  # +10%
            "TCS.NS": [3000, 3300, 3600],        # +20%
        })

        result = simulate_alternative("test", "RELIANCE", "TCS", lookback_days=90)

        assert isinstance(result, AlternativeResult)
        assert result.held_return_pct > 0
        assert result.alt_return_pct > result.held_return_pct
        assert result.difference_inr > 0
        assert "better" in result.verdict.lower()

    @patch("diamond.data.market.download_prices")
    @patch("diamond.data.ledger.Ledger")
    def test_held_outperforms(self, MockLedger, mock_dl):
        MockLedger.return_value.get_holdings.return_value = {"WINNER.NS": 10}
        MockLedger.return_value.get_avg_price.return_value = 1000

        mock_dl.return_value = pd.DataFrame({
            "WINNER.NS": [1000, 1100, 1200],  # +20%
            "LOSER.NS": [500, 480, 450],       # -10%
        })

        result = simulate_alternative("test", "WINNER", "LOSER")
        assert result.difference_inr < 0
        assert "current" in result.verdict.lower()

    @patch("diamond.data.market.download_prices")
    @patch("diamond.data.ledger.Ledger")
    def test_adds_ns_suffix(self, MockLedger, mock_dl):
        MockLedger.return_value.get_holdings.return_value = {"RELIANCE.NS": 10}
        MockLedger.return_value.get_avg_price.return_value = 2000

        mock_dl.return_value = pd.DataFrame({
            "RELIANCE.NS": [2000, 2100],
            "TCS.NS": [3000, 3100],
        })

        result = simulate_alternative("test", "RELIANCE", "TCS")
        assert result.held_ticker == "RELIANCE"
        assert result.alt_ticker == "TCS"

    @patch("diamond.data.market.download_prices")
    @patch("diamond.data.ledger.Ledger")
    def test_empty_prices(self, MockLedger, mock_dl):
        MockLedger.return_value.get_holdings.return_value = {}
        MockLedger.return_value.get_avg_price.return_value = 0

        mock_dl.return_value = pd.DataFrame()
        result = simulate_alternative("test", "A", "B")
        assert result.verdict == "No data"


class TestHelpers:
    @patch("diamond.data.market.download_prices")
    def test_fetch_portfolio_prices(self, mock_dl):
        mock_dl.return_value = pd.DataFrame({"RELIANCE.NS": [2500]})
        result = _fetch_portfolio_prices(["RELIANCE.NS"])
        assert result["RELIANCE.NS"] == 2500

    def test_fetch_portfolio_prices_empty(self):
        assert _fetch_portfolio_prices([]) == {}

    @patch("diamond.analysis.screener.screen")
    def test_get_betas_from_screener(self, mock_screen):
        mock_screen.return_value = pd.DataFrame({
            "Ticker": ["RELIANCE.NS"],
            "Beta": [0.85],
        })
        betas = _get_betas(["RELIANCE.NS", "UNKNOWN.NS"])
        assert betas["RELIANCE.NS"] == 0.85
        assert betas["UNKNOWN.NS"] == 1.0  # Default
