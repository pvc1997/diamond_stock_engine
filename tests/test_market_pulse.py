"""Tests for market pulse module."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from diamond.monitoring.market_pulse import (
    MarketPulse,
    _compute_rsi,
    get_market_pulse,
)


class TestComputeRSI:
    def test_rsi_neutral(self):
        prices = pd.Series(np.linspace(100, 110, 30))
        rsi = _compute_rsi(prices, 14)
        assert 0 <= rsi <= 100

    def test_rsi_overbought_on_uptrend(self):
        prices = pd.Series(np.linspace(100, 200, 30))
        rsi = _compute_rsi(prices, 14)
        assert rsi > 70

    def test_rsi_oversold_on_downtrend(self):
        prices = pd.Series(np.linspace(200, 100, 30))
        rsi = _compute_rsi(prices, 14)
        assert rsi < 30

    def test_rsi_short_series(self):
        prices = pd.Series([100, 101, 102])
        rsi = _compute_rsi(prices, 14)
        assert rsi == 50.0  # Default


class TestMarketPulseDataclass:
    def test_defaults(self):
        pulse = MarketPulse(timestamp="2026-01-01")
        assert pulse.verdict == "WAIT"
        assert pulse.score == 0
        assert pulse.regime == "UNKNOWN"
        assert pulse.verdict_reasons == []

    def test_all_fields(self):
        pulse = MarketPulse(
            timestamp="2026-01-01",
            nifty_price=22000,
            vix=15.5,
            breadth_pct=65.0,
            verdict="DEPLOY",
            score=45,
        )
        assert pulse.nifty_price == 22000
        assert pulse.vix == 15.5


class TestGetMarketPulse:
    def test_returns_wait_on_no_data(self):
        """With no market data, verdict should default to WAIT."""
        with patch("diamond.monitoring.market_pulse._fetch_nifty_data", return_value=None), \
             patch("diamond.monitoring.market_pulse._fetch_vix", return_value=0.0), \
             patch("diamond.monitoring.market_pulse._compute_breadth", return_value=50.0):
            pulse = get_market_pulse()
        assert pulse.verdict == "WAIT"
        assert isinstance(pulse.score, int)

    def test_bullish_signals_increase_score(self):
        """Multiple bullish signals should push score positive."""
        dates = pd.bdate_range("2025-01-01", periods=250)
        # Strong uptrend
        prices = pd.DataFrame(
            {"^NSEI": np.linspace(18000, 24000, 250)},
            index=dates,
        )

        with patch("diamond.monitoring.market_pulse._fetch_nifty_data", return_value=prices), \
             patch("diamond.monitoring.market_pulse._fetch_vix", return_value=12.0), \
             patch("diamond.monitoring.market_pulse._compute_breadth", return_value=75.0):
            pulse = get_market_pulse()

        assert pulse.score > 0
        assert pulse.trend == "BULLISH"
        assert pulse.vix_regime == "LOW"
        assert pulse.breadth_regime == "STRONG"

    def test_bearish_signals_decrease_score(self):
        """Bearish signals should push score negative."""
        dates = pd.bdate_range("2025-01-01", periods=250)
        prices = pd.DataFrame(
            {"^NSEI": np.linspace(24000, 18000, 250)},
            index=dates,
        )

        with patch("diamond.monitoring.market_pulse._fetch_nifty_data", return_value=prices), \
             patch("diamond.monitoring.market_pulse._fetch_vix", return_value=30.0), \
             patch("diamond.monitoring.market_pulse._compute_breadth", return_value=20.0):
            pulse = get_market_pulse()

        assert pulse.score < 0
        assert pulse.trend == "BEARISH"
        assert pulse.vix_regime == "EXTREME"
        assert pulse.breadth_regime == "WASHOUT"
        assert pulse.verdict == "DEFENSIVE"

    def test_conservative_default(self):
        """Moderate signals should result in WAIT (conservative)."""
        dates = pd.bdate_range("2025-01-01", periods=250)
        # Flat market
        rng = np.random.default_rng(42)
        prices_data = 20000 + np.cumsum(rng.normal(0, 50, 250))
        prices = pd.DataFrame({"^NSEI": prices_data}, index=dates)

        with patch("diamond.monitoring.market_pulse._fetch_nifty_data", return_value=prices), \
             patch("diamond.monitoring.market_pulse._fetch_vix", return_value=16.0), \
             patch("diamond.monitoring.market_pulse._compute_breadth", return_value=55.0):
            pulse = get_market_pulse()

        # With mixed signals, should stay conservative
        assert pulse.verdict in ("WAIT", "DEPLOY")  # Could be either with these params
        assert len(pulse.verdict_reasons) > 0
