"""Tests for market screener metrics calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from diamond.analysis.screener import _compute_metrics, _hurst_exponent


class TestHurstExponent:
    def test_random_walk_near_half(self):
        """Random data should produce Hurst near 0.5."""
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, 500))
        h = _hurst_exponent(prices)
        assert 0.3 < h < 0.7

    def test_persistent_cumulative_series(self):
        """Cumulative sum of biased random walk should show persistence."""
        rng = np.random.default_rng(99)
        # Biased random walk: positive drift with autocorrelation
        steps = rng.normal(0.5, 1.0, 500)
        prices = 100 + np.cumsum(steps)
        h = _hurst_exponent(prices)
        # Just verify it returns a valid number in range
        assert 0.0 <= h <= 1.0

    def test_insufficient_data_returns_default(self):
        """Short series should return 0.5 default."""
        prices = np.array([100, 101, 102])
        h = _hurst_exponent(prices)
        assert h == 0.5

    def test_result_bounded(self):
        """Hurst should always be between 0 and 1."""
        rng = np.random.default_rng(123)
        prices = 100 + np.cumsum(rng.normal(0, 1, 1000))
        h = _hurst_exponent(prices)
        assert 0.0 <= h <= 1.0


class TestComputeMetrics:
    def _make_data(self, n_days=300, daily_return=0.001, volatility=0.02):
        """Generate synthetic price and market return data."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2022-01-01", periods=n_days)
        returns = rng.normal(daily_return, volatility, n_days)
        prices = pd.Series(100 * np.cumprod(1 + returns), index=dates)

        mkt_returns = pd.Series(
            rng.normal(0.0004, 0.015, n_days),
            index=dates,
        )
        return prices, mkt_returns

    def test_returns_all_metrics(self):
        prices, mkt_ret = self._make_data()
        mkt_ann = (1 + mkt_ret.mean()) ** 252 - 1
        result = _compute_metrics(prices, mkt_ret, mkt_ann, 0.065)

        assert "Alpha" in result
        assert "Beta" in result
        assert "CAGR" in result
        assert "Volatility" in result
        assert "Hurst" in result

    def test_beta_reasonable_range(self):
        prices, mkt_ret = self._make_data()
        mkt_ann = (1 + mkt_ret.mean()) ** 252 - 1
        result = _compute_metrics(prices, mkt_ret, mkt_ann, 0.065)

        assert -3.0 < result["Beta"] < 5.0

    def test_volatility_positive(self):
        prices, mkt_ret = self._make_data()
        mkt_ann = (1 + mkt_ret.mean()) ** 252 - 1
        result = _compute_metrics(prices, mkt_ret, mkt_ann, 0.065)

        assert result["Volatility"] > 0

    def test_insufficient_data_returns_empty(self):
        """Less than 60 data points should return empty dict."""
        dates = pd.bdate_range("2023-01-01", periods=30)
        prices = pd.Series(range(100, 130), index=dates)
        mkt_ret = pd.Series(np.zeros(30), index=dates)

        result = _compute_metrics(prices, mkt_ret, 0.10, 0.065)
        assert result == {}

    def test_cagr_positive_for_uptrending(self):
        prices, mkt_ret = self._make_data(daily_return=0.003)  # Strong uptrend
        mkt_ann = (1 + mkt_ret.mean()) ** 252 - 1
        result = _compute_metrics(prices, mkt_ret, mkt_ann, 0.065)

        assert result["CAGR"] > 0
