"""Tests for liquidity checker."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from diamond.analysis.liquidity import (
    check_liquidity,
    check_portfolio_liquidity,
    suggest_stagger,
)


def _mock_history(avg_volume=1_000_000, avg_price=2000.0, rows=60):
    """Create a mock DataFrame like yf.Ticker.history() returns."""
    return pd.DataFrame({
        "Volume": [avg_volume] * rows,
        "Close": [avg_price] * rows,
        "Open": [avg_price] * rows,
        "High": [avg_price * 1.01] * rows,
        "Low": [avg_price * 0.99] * rows,
    })


class TestCheckLiquidity:
    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_small_trade_safe(self, mock_yf):
        """Trade < 5% of ADV is safe."""
        # ADV = 1M shares * 2000 = 2B. Trade = 50K = 0.0025% -> safe
        mock_yf.return_value.history.return_value = _mock_history()

        result = check_liquidity("RELIANCE.NS", 50_000)
        assert result["safe"] is True
        assert result["warning"] is None
        assert result["suggestion"] is None
        assert result["ticker"] == "RELIANCE.NS"

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_medium_trade_warning(self, mock_yf):
        """Trade 5-10% of ADV gets warning but still safe."""
        # ADV = 1000 * 100 = 100,000. Trade = 7,000 = 7%
        mock_yf.return_value.history.return_value = _mock_history(
            avg_volume=1000, avg_price=100.0
        )

        result = check_liquidity("SMALLCAP.NS", 7_000)
        assert result["safe"] is True
        assert result["warning"] is not None
        assert "slippage" in result["warning"]
        assert result["suggestion"] is not None

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_large_trade_stagger(self, mock_yf):
        """Trade 10-25% of ADV suggests staggering."""
        # ADV = 1000 * 100 = 100,000. Trade = 15,000 = 15%
        mock_yf.return_value.history.return_value = _mock_history(
            avg_volume=1000, avg_price=100.0
        )

        result = check_liquidity("ILLIQUID.NS", 15_000)
        assert result["safe"] is False
        assert "high market impact" in result["warning"]
        assert "Stagger" in result["suggestion"]

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_huge_trade_avoid(self, mock_yf):
        """Trade > 25% of ADV recommends avoidance."""
        # ADV = 1000 * 100 = 100,000. Trade = 30,000 = 30%
        mock_yf.return_value.history.return_value = _mock_history(
            avg_volume=1000, avg_price=100.0
        )

        result = check_liquidity("TINY.NS", 30_000)
        assert result["safe"] is False
        assert "illiquid" in result["warning"]
        assert "Avoid" in result["suggestion"]

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_no_volume_data(self, mock_yf):
        """Empty history handled gracefully."""
        mock_yf.return_value.history.return_value = pd.DataFrame()

        result = check_liquidity("EMPTY.NS", 10_000)
        assert result["safe"] is False
        assert "No volume data" in result.get("error", "")

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_appends_ns_suffix(self, mock_yf):
        """Appends .NS if not present."""
        mock_yf.return_value.history.return_value = _mock_history()

        result = check_liquidity("RELIANCE", 1_000)
        assert result["ticker"] == "RELIANCE.NS"

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_already_has_ns_suffix(self, mock_yf):
        """Does not double-append .NS."""
        mock_yf.return_value.history.return_value = _mock_history()

        result = check_liquidity("RELIANCE.NS", 1_000)
        assert result["ticker"] == "RELIANCE.NS"

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_yfinance_exception(self, mock_yf):
        """Graceful failure on yfinance error."""
        mock_yf.return_value.history.side_effect = Exception("Network error")

        result = check_liquidity("ERROR.NS", 10_000)
        assert result["safe"] is False
        assert "error" in result

    @patch("diamond.analysis.liquidity.yf.Ticker")
    def test_return_fields(self, mock_yf):
        """Check all expected fields are present."""
        mock_yf.return_value.history.return_value = _mock_history()

        result = check_liquidity("RELIANCE.NS", 50_000)
        assert "avg_daily_volume" in result
        assert "avg_daily_value" in result
        assert "trade_value" in result
        assert "trade_as_pct_of_adv" in result


class TestCheckPortfolioLiquidity:
    @patch("diamond.analysis.liquidity.check_liquidity")
    @patch("diamond.data.market.download_prices")
    @patch("diamond.analysis.liquidity.Ledger")
    def test_scans_all_holdings(self, mock_ledger_cls, mock_dl, mock_check):
        """Checks liquidity for every holding."""
        mock_ledger_cls.return_value.get_holdings.return_value = {
            "RELIANCE.NS": 10,
            "TCS.NS": 5,
        }
        mock_dl.return_value = pd.DataFrame({
            "RELIANCE.NS": [2500.0],
            "TCS.NS": [3000.0],
        })
        mock_check.return_value = {
            "ticker": "X",
            "safe": True,
            "trade_as_pct_of_adv": 1.0,
        }

        result = check_portfolio_liquidity("gods_plan")
        assert len(result) == 2
        assert mock_check.call_count == 2

    @patch("diamond.analysis.liquidity.Ledger")
    def test_empty_holdings(self, mock_ledger_cls):
        """Empty portfolio returns empty list."""
        mock_ledger_cls.return_value.get_holdings.return_value = {}

        result = check_portfolio_liquidity("gods_plan")
        assert result == []


class TestSuggestStagger:
    @patch("diamond.analysis.liquidity.check_liquidity")
    def test_small_trade_no_stagger(self, mock_check):
        """Small trade does not need staggering."""
        mock_check.return_value = {
            "ticker": "RELIANCE.NS",
            "trade_as_pct_of_adv": 2.0,
            "avg_daily_value": 1_000_000,
            "safe": True,
        }

        result = suggest_stagger("RELIANCE.NS", 20_000)
        assert result["stagger_needed"] is False

    @patch("diamond.analysis.liquidity.check_liquidity")
    def test_large_trade_stagger_plan(self, mock_check):
        """Large trade generates stagger plan with tranches."""
        mock_check.return_value = {
            "ticker": "SMALLCAP.NS",
            "trade_as_pct_of_adv": 15.0,
            "avg_daily_value": 100_000,
            "safe": False,
        }

        result = suggest_stagger("SMALLCAP.NS", 15_000)
        assert result["stagger_needed"] is True
        assert result["days"] >= 2
        assert len(result["tranches"]) == result["days"]
        assert result["total_value"] == 15_000
        # Each tranche should have amount and order_type
        for tranche in result["tranches"]:
            assert "amount" in tranche
            assert tranche["order_type"] == "LIMIT"

    @patch("diamond.analysis.liquidity.check_liquidity")
    def test_stagger_daily_amount(self, mock_check):
        """Daily amount sums to total trade value."""
        mock_check.return_value = {
            "ticker": "TEST.NS",
            "trade_as_pct_of_adv": 20.0,
            "avg_daily_value": 50_000,
            "safe": False,
        }

        result = suggest_stagger("TEST.NS", 10_000)
        total_from_tranches = sum(t["amount"] for t in result["tranches"])
        assert abs(total_from_tranches - 10_000) < 1.0
