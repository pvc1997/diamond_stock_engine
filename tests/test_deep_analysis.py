"""Tests for deep stock analysis module."""

from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_prices():
    """Generate a realistic price series for testing."""
    dates = pd.date_range(end=datetime.now(), periods=300, freq="B")
    np.random.seed(42)
    # Start at 1000, random walk with slight upward drift
    returns = np.random.normal(0.0005, 0.015, len(dates))
    prices = 1000 * np.cumprod(1 + returns)
    return pd.Series(prices, index=dates, name="RELIANCE.NS")


@pytest.fixture
def sample_info():
    """Sample yfinance .info dict."""
    return {
        "shortName": "Reliance Industries",
        "trailingPE": 25.5,
        "priceToBook": 2.8,
        "returnOnEquity": 0.15,
        "debtToEquity": 45.0,
        "dividendYield": 0.005,
        "revenueGrowth": 0.12,
        "earningsGrowth": 0.18,
        "marketCap": 1800000000000,
        "sector": "Energy",
        "industry": "Oil & Gas Refining & Marketing",
        "recommendationKey": "buy",
        "freeCashflow": 50000000000,
        "bookValue": 1100.0,
        "trailingEps": 85.0,
    }


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

class TestTechnicals:
    def test_compute_rsi(self, sample_prices):
        from diamond.analysis.deep import _compute_rsi
        rsi = _compute_rsi(sample_prices)
        assert 0 <= rsi <= 100

    def test_compute_rsi_rising(self):
        """Steadily rising prices should give RSI > 60."""
        from diamond.analysis.deep import _compute_rsi
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        prices = pd.Series(np.linspace(100, 200, 50), index=dates)
        rsi = _compute_rsi(prices)
        assert rsi > 60

    def test_compute_rsi_falling(self):
        """Steadily falling prices should give RSI < 40."""
        from diamond.analysis.deep import _compute_rsi
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        prices = pd.Series(np.linspace(200, 100, 50), index=dates)
        rsi = _compute_rsi(prices)
        assert rsi < 40

    def test_compute_technicals(self, sample_prices):
        from diamond.analysis.deep import _compute_technicals
        t = _compute_technicals(sample_prices)

        assert t.current_price > 0
        assert 0 <= t.rsi_14 <= 100
        assert t.bb_lower <= t.bb_middle <= t.bb_upper
        assert t.dma_trend in ("GOLDEN_CROSS", "DEATH_CROSS", "NEUTRAL")
        assert t.bb_position in ("ABOVE", "WITHIN", "BELOW")
        assert t.support <= t.resistance

    def test_technicals_short_series(self):
        """Short series should not crash, use defaults."""
        from diamond.analysis.deep import _compute_technicals
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        prices = pd.Series(np.linspace(100, 110, 30), index=dates)
        t = _compute_technicals(prices)
        assert t.current_price > 0


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

class TestFundamentals:
    @patch("diamond.analysis.deep.market.get_stock_info")
    def test_fetch_fundamentals(self, mock_info, sample_info):
        from diamond.analysis.deep import _fetch_fundamentals
        mock_info.return_value = sample_info

        f = _fetch_fundamentals("RELIANCE.NS")
        assert f.pe_ratio == 25.5
        assert f.pb_ratio == 2.8
        assert f.roe == 0.15
        assert f.sector == "Energy"
        assert f.recommendation == "buy"

    @patch("diamond.analysis.deep.market.get_stock_info")
    def test_missing_fundamentals(self, mock_info):
        """Missing fields should default to 0 or 'Unknown'."""
        from diamond.analysis.deep import _fetch_fundamentals
        mock_info.return_value = {}

        f = _fetch_fundamentals("UNKNOWN.NS")
        assert f.pe_ratio == 0.0
        assert f.sector == "Unknown"
        assert f.recommendation == "none"


# ---------------------------------------------------------------------------
# Rule-based verdict
# ---------------------------------------------------------------------------

class TestRuleBasedVerdict:
    def test_bullish_signals(self):
        from diamond.analysis.deep import (
            _rule_based_verdict, TechnicalIndicators,
            FundamentalData, ScreenerMetrics,
        )

        t = TechnicalIndicators(
            current_price=1000, rsi_14=25, macd_line=5, macd_signal=3,
            macd_histogram=2, bb_upper=1050, bb_middle=1000, bb_lower=950,
            bb_position="BELOW", dma_50=1010, dma_200=990, dma_trend="GOLDEN_CROSS",
            support=950, resistance=1050, price_change_1d=1.0,
            price_change_1w=3.0, price_change_1m=5.0,
        )
        f = FundamentalData(
            pe_ratio=12, pb_ratio=1.5, roe=0.22, debt_to_equity=30,
            dividend_yield=0.02, revenue_growth=0.20, profit_growth=0.25,
            market_cap=1e12, sector="Energy", industry="Oil",
            recommendation="buy", free_cash_flow=1e10, book_value=500, eps=80,
        )
        s = ScreenerMetrics(alpha=0.20, beta=0.85, cagr=0.25, volatility=0.20, hurst=0.60)
        sent = {"score": 5.0, "sentiment": "Bullish"}

        verdict, confidence, reasons = _rule_based_verdict(t, f, s, sent)
        assert verdict == "BUY"
        assert confidence > 0.3
        assert len(reasons) > 0

    def test_bearish_signals(self):
        from diamond.analysis.deep import (
            _rule_based_verdict, TechnicalIndicators,
            FundamentalData, ScreenerMetrics,
        )

        t = TechnicalIndicators(
            current_price=500, rsi_14=75, macd_line=-5, macd_signal=-3,
            macd_histogram=-2, bb_upper=550, bb_middle=500, bb_lower=450,
            bb_position="ABOVE", dma_50=480, dma_200=520, dma_trend="DEATH_CROSS",
            support=450, resistance=550, price_change_1d=-2.0,
            price_change_1w=-5.0, price_change_1m=-10.0,
        )
        f = FundamentalData(
            pe_ratio=60, pb_ratio=5, roe=-0.05, debt_to_equity=200,
            dividend_yield=0, revenue_growth=-0.10, profit_growth=-0.15,
            market_cap=1e11, sector="Tech", industry="IT",
            recommendation="sell", free_cash_flow=0, book_value=100, eps=5,
        )
        s = ScreenerMetrics(alpha=-0.10, beta=1.5, cagr=-0.05, volatility=0.40, hurst=0.40)
        sent = {"score": -5.0, "sentiment": "Bearish"}

        verdict, confidence, reasons = _rule_based_verdict(t, f, s, sent)
        assert verdict == "SELL"
        assert len(reasons) > 0


# ---------------------------------------------------------------------------
# Full analysis integration
# ---------------------------------------------------------------------------

class TestAnalyzeDeep:
    @patch("diamond.analysis.deep.market.get_stock_info")
    @patch("diamond.analysis.deep.market.download_single")
    @patch("diamond.analysis.sentiment.analyze_stock")
    def test_analyze_deep_no_ai(self, mock_sentiment, mock_download, mock_info, sample_prices, sample_info):
        from diamond.analysis.deep import analyze_deep

        mock_download.return_value = sample_prices
        mock_info.return_value = sample_info
        mock_sentiment.return_value = {
            "score": 3.0, "sentiment": "Positive",
            "multiplier": 1.1, "rationale": "Good news", "source": "heuristic",
        }

        result = analyze_deep("RELIANCE.NS", use_ai=False)

        assert result.ticker == "RELIANCE.NS"
        assert result.verdict in ("BUY", "SELL", "HOLD")
        assert 0 <= result.confidence <= 1.0
        assert result.technicals.current_price > 0
        assert result.fundamentals.pe_ratio == 25.5
        assert result.screener.alpha is not None
        assert len(result.ai_narrative) > 0

    @patch("diamond.analysis.deep.market.get_stock_info")
    @patch("diamond.analysis.deep.market.download_single")
    @patch("diamond.analysis.sentiment.analyze_stock")
    def test_analyze_normalizes_ticker(self, mock_sentiment, mock_download, mock_info, sample_prices, sample_info):
        from diamond.analysis.deep import analyze_deep

        mock_download.return_value = sample_prices
        mock_info.return_value = sample_info
        mock_sentiment.return_value = {"score": 0, "sentiment": "Neutral", "multiplier": 1.0, "rationale": "", "source": "none"}

        result = analyze_deep("RELIANCE", use_ai=False)
        assert result.ticker == "RELIANCE.NS"

    @patch("diamond.analysis.deep.market.download_single")
    def test_analyze_insufficient_data(self, mock_download):
        from diamond.analysis.deep import analyze_deep

        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        mock_download.return_value = pd.Series(range(10), index=dates)

        from diamond.exceptions import InsufficientDataError
        with pytest.raises(InsufficientDataError, match="Insufficient"):
            analyze_deep("TINY.NS", use_ai=False)
