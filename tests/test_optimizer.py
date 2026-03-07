"""Tests for portfolio optimization algorithms."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from diamond.analysis.optimizer import (
    equal_weights,
    inverse_volatility_weights,
    market_cap_weights,
    monte_carlo_optimize,
)


@pytest.fixture
def returns_df():
    """Generate synthetic return data for 5 stocks."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2022-01-01", periods=300)
    data = {}
    for i, ticker in enumerate(["A.NS", "B.NS", "C.NS", "D.NS", "E.NS"]):
        # Different risk/return profiles
        mu = 0.0003 + i * 0.0001
        sigma = 0.015 + i * 0.005
        data[ticker] = rng.normal(mu, sigma, len(dates))
    return pd.DataFrame(data, index=dates)


class TestMonteCarloOptimize:
    def test_weights_sum_to_one(self, returns_df):
        weights = monte_carlo_optimize(returns_df, num_simulations=10_000)
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_respects_max_weight(self, returns_df):
        weights = monte_carlo_optimize(returns_df, num_simulations=10_000, max_weight=0.30)
        for w in weights.values():
            assert w <= 0.31  # Small tolerance for rounding

    def test_single_ticker(self):
        dates = pd.bdate_range("2022-01-01", periods=100)
        df = pd.DataFrame({"ONLY.NS": np.random.normal(0, 0.01, 100)}, index=dates)
        weights = monte_carlo_optimize(df, num_simulations=1000)
        assert weights == {"ONLY.NS": 1.0}

    def test_empty_returns(self):
        df = pd.DataFrame()
        weights = monte_carlo_optimize(df)
        assert weights == {}

    def test_all_weights_positive(self, returns_df):
        weights = monte_carlo_optimize(returns_df, num_simulations=10_000)
        for w in weights.values():
            assert w > 0


class TestInverseVolatilityWeights:
    def test_weights_sum_to_one(self, returns_df):
        weights = inverse_volatility_weights(returns_df)
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_low_vol_gets_higher_weight(self):
        """Stock with lower vol should get higher weight."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2022-01-01", periods=200)
        df = pd.DataFrame({
            "LOW_VOL.NS": rng.normal(0, 0.01, 200),    # Low vol
            "HIGH_VOL.NS": rng.normal(0, 0.05, 200),   # High vol
        }, index=dates)

        weights = inverse_volatility_weights(df, max_weight=1.0)
        assert weights["LOW_VOL.NS"] > weights["HIGH_VOL.NS"]

    def test_respects_max_weight(self, returns_df):
        weights = inverse_volatility_weights(returns_df, max_weight=0.25)
        for w in weights.values():
            assert w <= 0.26

    def test_single_ticker(self):
        dates = pd.bdate_range("2022-01-01", periods=100)
        df = pd.DataFrame({"X.NS": np.random.normal(0, 0.01, 100)}, index=dates)
        weights = inverse_volatility_weights(df)
        assert weights == {"X.NS": 1.0}


class TestEqualWeights:
    def test_equal_distribution(self):
        tickers = ["A.NS", "B.NS", "C.NS"]
        weights = equal_weights(tickers)
        for w in weights.values():
            assert abs(w - 1 / 3) < 0.001

    def test_empty(self):
        assert equal_weights([]) == {}


class TestMarketCapWeights:
    def test_proportional_to_cap(self):
        caps = {"BIG.NS": 1_000_000, "SMALL.NS": 100_000}
        weights = market_cap_weights(caps)
        assert weights["BIG.NS"] > weights["SMALL.NS"]
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_handles_zero_cap(self):
        caps = {"A.NS": 1000, "B.NS": 0, "C.NS": 500}
        weights = market_cap_weights(caps)
        assert "B.NS" not in weights

    def test_empty(self):
        assert market_cap_weights({}) == {}
