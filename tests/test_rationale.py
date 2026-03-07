"""Tests for trade rationale engine."""

from unittest.mock import patch

import pandas as pd
import pytest

from diamond.analysis.rationale import (
    TradeRationale,
    generate_rationale,
    generate_batch_rationale,
    format_rationale,
    format_rationale_verbose,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_screener_df():
    """Sample screener results DataFrame."""
    return pd.DataFrame([
        {"Ticker": "RELIANCE.NS", "Alpha": 0.25, "Beta": 0.90, "CAGR": 0.18, "Volatility": 0.22, "Hurst": 0.58, "Sector": "Energy"},
        {"Ticker": "TCS.NS", "Alpha": 0.10, "Beta": 1.10, "CAGR": 0.12, "Volatility": 0.25, "Hurst": 0.52, "Sector": "Technology"},
        {"Ticker": "HDFCBANK.NS", "Alpha": 0.05, "Beta": 0.70, "CAGR": 0.14, "Volatility": 0.18, "Hurst": 0.48, "Sector": "Financial Services"},
        {"Ticker": "SAIL.NS", "Alpha": 0.30, "Beta": 1.20, "CAGR": 0.22, "Volatility": 0.35, "Hurst": 0.62, "Sector": "Metals"},
    ])


@pytest.fixture
def sample_allocation():
    return {
        "RELIANCE.NS": 80000,
        "TCS.NS": 60000,
        "HDFCBANK.NS": 50000,
        "SAIL.NS": 40000,
    }


@pytest.fixture
def sample_holdings():
    return {"RELIANCE.NS": 30, "INFY.NS": 20}


@pytest.fixture
def sample_prices():
    return {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600, "SAIL.NS": 100, "INFY.NS": 1500}


# ---------------------------------------------------------------------------
# Single rationale
# ---------------------------------------------------------------------------

class TestGenerateRationale:
    @patch("diamond.analysis.rationale._get_market_context", return_value="Market: WAIT")
    def test_buy_rationale(self, mock_ctx, sample_screener_df, sample_allocation, sample_holdings, sample_prices):
        r = generate_rationale(
            ticker="TCS.NS",
            action="BUY",
            target_weight=0.12,
            screener_df=sample_screener_df,
            strategy_name="gods_plan",
            target_allocation=sample_allocation,
            holdings=sample_holdings,
            current_prices=sample_prices,
        )
        assert r.ticker == "TCS.NS"
        assert r.action == "BUY"
        assert r.weight_pct == 12.0
        assert len(r.selection_reason) > 0
        assert len(r.screener_summary) > 0

    @patch("diamond.analysis.rationale._get_market_context", return_value="Market: WAIT")
    def test_sell_rationale_exiting(self, mock_ctx, sample_screener_df, sample_allocation, sample_holdings, sample_prices):
        """Selling a stock not in target allocation."""
        r = generate_rationale(
            ticker="INFY.NS",
            action="SELL",
            target_weight=0.0,
            screener_df=sample_screener_df,
            strategy_name="gods_plan",
            target_allocation=sample_allocation,
            holdings=sample_holdings,
            current_prices=sample_prices,
        )
        assert r.action == "SELL"
        assert "exit" in r.component or "No longer" in r.selection_reason

    @patch("diamond.analysis.rationale._get_market_context", return_value="Market: WAIT")
    def test_baseline_rationale(self, mock_ctx, sample_screener_df, sample_allocation, sample_holdings, sample_prices):
        r = generate_rationale(
            ticker="RELIANCE.NS",
            action="BUY",
            target_weight=0.02,
            screener_df=sample_screener_df,
            strategy_name="baseline",
            target_allocation=sample_allocation,
            holdings={},
            current_prices=sample_prices,
        )
        assert r.component == "nifty50"
        assert r.weight_method == "equal"


# ---------------------------------------------------------------------------
# Batch rationale
# ---------------------------------------------------------------------------

class TestBatchRationale:
    @patch("diamond.analysis.rationale._get_market_context", return_value="Market: WAIT")
    def test_batch_generates_for_all(self, mock_ctx, sample_screener_df, sample_allocation, sample_holdings, sample_prices):
        rationales = generate_batch_rationale(
            target_allocation=sample_allocation,
            capital=500000,
            screener_df=sample_screener_df,
            strategy_name="gods_plan",
            holdings=sample_holdings,
            current_prices=sample_prices,
        )
        # Should have rationales for new buys and the exit (INFY)
        assert len(rationales) > 0
        # INFY should be a SELL (in holdings but not in target)
        if "INFY.NS" in rationales:
            assert rationales["INFY.NS"].action == "SELL"

    @patch("diamond.analysis.rationale._get_market_context", return_value="Market: DEPLOY")
    def test_batch_with_empty_screener(self, mock_ctx, sample_allocation, sample_holdings, sample_prices):
        rationales = generate_batch_rationale(
            target_allocation=sample_allocation,
            capital=500000,
            screener_df=pd.DataFrame(),
            strategy_name="gods_plan",
            holdings=sample_holdings,
            current_prices=sample_prices,
        )
        # Should still produce rationales, just with generic reasons
        assert len(rationales) > 0


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_format_rationale_compact(self):
        r = TradeRationale(
            ticker="RELIANCE.NS",
            action="BUY",
            selection_reason="Quality Growth: Alpha=0.25",
            screener_summary="Alpha=0.25, Beta=0.90",
            component="quality_growth",
            weight_pct=8.5,
            weight_method="inverse_volatility",
            weight_reason="Lower vol -> higher weight",
            timing_reason="90-day rebalance",
            market_context="Market: WAIT",
        )
        formatted = format_rationale(r)
        assert "Quality Growth" in formatted
        assert "Alpha=0.25" in formatted
        assert "8.5%" in formatted

    def test_format_rationale_with_risk(self):
        r = TradeRationale(
            ticker="SAIL.NS",
            action="BUY",
            selection_reason="Value pick",
            screener_summary="Alpha=0.30",
            component="value",
            weight_pct=5.0,
            weight_method="alpha_proportional",
            weight_reason="Alpha-weighted",
            timing_reason="Rebalance",
            market_context="Market: WAIT",
            risk_notes=["Sector Metals at 12% (limit: 25%)"],
        )
        formatted = format_rationale(r)
        assert "Risk:" in formatted

    def test_format_verbose(self):
        r = TradeRationale(
            ticker="TCS.NS",
            action="SELL",
            selection_reason="No longer in target",
            screener_summary="N/A",
            component="exit",
            weight_pct=0.0,
            weight_method="N/A",
            weight_reason="Position being closed",
            timing_reason="Quarterly rebalance",
            market_context="Market: DEFENSIVE",
            risk_notes=["Stop-loss proximity: 8%"],
        )
        verbose = format_rationale_verbose(r)
        assert "SELL TCS.NS" in verbose
        assert "No longer in target" in verbose
        assert "DEFENSIVE" in verbose


# ---------------------------------------------------------------------------
# Market context failure
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_market_context_fails_gracefully(self):
        """_get_market_context should return a string even on failure."""
        from diamond.analysis.rationale import _get_market_context

        with patch("diamond.monitoring.market_pulse.get_market_pulse", side_effect=Exception("API down")):
            ctx = _get_market_context()
            assert "unavailable" in ctx.lower()
