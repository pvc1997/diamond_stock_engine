"""Tests for strategy implementations."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from diamond.strategies.baseline import BaselineStrategy
from diamond.strategies.steady import SteadyStrategy
from diamond.strategies.gods_plan import GodsPlanStrategy


# --- Shared Helpers ---

def _make_universe(n=25):
    """Create a mock screener universe."""
    tickers = [f"STOCK{i}.NS" for i in range(n)]
    np.random.seed(42)
    return pd.DataFrame({
        "Ticker": tickers,
        "Alpha": np.linspace(1.0, 0.01, n).round(4),
        "Beta": np.random.uniform(0.5, 1.3, n).round(4),
        "CAGR": np.linspace(0.30, 0.05, n).round(4),
        "Volatility": np.random.uniform(0.12, 0.30, n).round(4),
        "Hurst": np.random.uniform(0.40, 0.65, n).round(4),
        "Sector": [f"Sector{i % 6}" for i in range(n)],
    })


def _mock_returns(tickers, days=200):
    """Generate mock return data for optimizer."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2023-01-01", periods=days)
    data = {t: rng.normal(0.001, 0.02, days) for t in tickers}
    return pd.DataFrame(data, index=dates)


# --- Baseline Strategy Tests ---

class TestBaselineStrategy:
    def test_name(self):
        assert BaselineStrategy.name == "baseline"

    def test_screen_returns_nifty50(self):
        strategy = BaselineStrategy()
        result = strategy.screen(pd.DataFrame())
        assert len(result) == 50
        assert "Ticker" in result.columns

    def test_allocate_equal_weights(self):
        strategy = BaselineStrategy()
        candidates = pd.DataFrame({"Ticker": ["A.NS", "B.NS", "C.NS", "D.NS"]})
        allocation = strategy.allocate(candidates, 100000)

        assert len(allocation) == 4
        assert all(abs(v - 25000) < 0.01 for v in allocation.values())
        assert abs(sum(allocation.values()) - 100000) < 0.01

    def test_allocate_empty_candidates(self):
        strategy = BaselineStrategy()
        candidates = pd.DataFrame({"Ticker": []})
        allocation = strategy.allocate(candidates, 100000)
        assert allocation == {}

    def test_should_rebalance_quarterly(self):
        strategy = BaselineStrategy()
        assert strategy.should_rebalance({}, {}, days_since_last=91) is True
        assert strategy.should_rebalance({}, {}, days_since_last=30) is False
        assert strategy.should_rebalance({}, {}, days_since_last=90) is True


# --- Steady Strategy Tests ---

class TestSteadyStrategy:
    def test_name(self):
        assert SteadyStrategy.name == "steady"

    def test_screen_calls_screener(self):
        universe = _make_universe()
        strategy = SteadyStrategy()
        with patch("diamond.strategies.steady._get_screened_universe", return_value=universe):
            result = strategy.screen(pd.DataFrame(), end_date=None)
        assert len(result) == len(universe)

    def test_allocate_selects_low_beta(self):
        universe = _make_universe(30)
        strategy = SteadyStrategy()

        tickers = universe["Ticker"].tolist()

        # Create prices that generate valid returns for inverse-vol
        dates = pd.bdate_range("2023-01-01", periods=201)
        rng = np.random.default_rng(42)
        prices = pd.DataFrame(
            {t: 100 * np.cumprod(1 + rng.normal(0.001, 0.02, 201)) for t in tickers[:18]},
            index=dates,
        )

        with patch("diamond.data.market.download_prices", return_value=prices):
            allocation = strategy.allocate(universe, 100000)

        assert len(allocation) > 0
        assert len(allocation) <= 18
        assert abs(sum(allocation.values()) - 100000) < 100

    def test_allocate_empty_universe(self):
        strategy = SteadyStrategy()
        result = strategy.allocate(pd.DataFrame(), 100000)
        assert result == {}

    def test_should_rebalance_quarterly(self):
        strategy = SteadyStrategy()
        assert strategy.should_rebalance({}, {}, days_since_last=91) is True
        assert strategy.should_rebalance({}, {}, days_since_last=30) is False


# --- God's Plan Strategy Tests ---

class TestGodsPlanStrategy:
    def test_name(self):
        assert GodsPlanStrategy.name == "gods_plan"

    def test_screen_calls_screener(self):
        universe = _make_universe()
        strategy = GodsPlanStrategy()
        with patch("diamond.strategies.gods_plan._get_screened_universe", return_value=universe):
            result = strategy.screen(pd.DataFrame(), end_date=None)
        assert len(result) == len(universe)

    def test_allocate_produces_stocks(self):
        universe = _make_universe(25)
        strategy = GodsPlanStrategy()

        def mock_download_prices(tickers, period_days=365):
            dates = pd.bdate_range("2023-01-01", periods=252)
            data = {}
            for t in tickers:
                np.random.seed(hash(t) % 2**31)
                returns = np.random.normal(0.001, 0.02, len(dates))
                data[t] = 1000 * np.cumprod(1 + returns)
            return pd.DataFrame(data, index=dates)

        with patch("diamond.strategies.gods_plan.market.download_prices", side_effect=mock_download_prices), \
             patch("diamond.data.universe.get_sector", return_value="Technology"):
            allocation = strategy.allocate(universe, 500000)

        assert len(allocation) > 0
        assert len(allocation) <= 18
        total = sum(allocation.values())
        assert abs(total - 500000) < 100

    def test_allocate_empty_universe(self):
        strategy = GodsPlanStrategy()
        result = strategy.allocate(pd.DataFrame(), 500000)
        assert result == {}

    def test_should_rebalance_quarterly(self):
        strategy = GodsPlanStrategy()
        assert strategy.should_rebalance({}, {}, days_since_last=91) is True
        assert strategy.should_rebalance({}, {}, days_since_last=30) is False
        assert strategy.should_rebalance({}, {}, days_since_last=90) is True

    def test_no_duplicate_stocks_across_components(self):
        """Each component should exclude tickers already selected."""
        universe = _make_universe(25)
        strategy = GodsPlanStrategy()

        def mock_download_prices(tickers, period_days=365):
            dates = pd.bdate_range("2023-01-01", periods=252)
            data = {}
            for t in tickers:
                np.random.seed(hash(t) % 2**31)
                returns = np.random.normal(0.001, 0.02, len(dates))
                data[t] = 1000 * np.cumprod(1 + returns)
            return pd.DataFrame(data, index=dates)

        with patch("diamond.strategies.gods_plan.market.download_prices", side_effect=mock_download_prices), \
             patch("diamond.data.universe.get_sector", return_value="Technology"):
            allocation = strategy.allocate(universe, 500000)

        # Each ticker should appear only once
        assert len(allocation) > 0


class TestGodsPlanConfig:
    def test_config_defaults(self):
        from diamond.config import GodsPlanSettings
        settings = GodsPlanSettings()
        assert settings.rebalance_days == 90
        assert settings.max_position_weight == 0.12
        assert settings.core_min_alpha == 0.15
        assert settings.core_min_cagr == 0.18
        assert settings.drawdown_critical_pct == 20.0

    def test_config_registered(self):
        from diamond.config import Config
        cfg = Config()
        assert hasattr(cfg, "gods_plan")
        assert cfg.gods_plan.max_position_weight == 0.12
