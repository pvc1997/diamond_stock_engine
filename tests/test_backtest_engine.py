"""Tests for the walk-forward backtest engine."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from diamond.backtest.engine import run_backtest, _simulate_window, WindowResult


# --- Helpers ---

def _make_prices(tickers, start="2023-01-01", periods=200, base=100):
    """Create synthetic price DataFrame."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(start, periods=periods)
    data = {}
    for t in tickers:
        returns = rng.normal(0.001, 0.02, periods)
        data[t] = base * np.cumprod(1 + returns)
    return pd.DataFrame(data, index=dates)


def _make_screener_result(tickers):
    """Create a screener-style DataFrame."""
    n = len(tickers)
    return pd.DataFrame({
        "Ticker": tickers,
        "Alpha": [0.3 - i * 0.1 for i in range(n)],
        "Beta": [0.8 + i * 0.1 for i in range(n)],
        "CAGR": [0.20 - i * 0.05 for i in range(n)],
        "Volatility": [0.20 + i * 0.05 for i in range(n)],
        "Hurst": [0.5] * n,
        "Sector": ["Tech", "Finance", "Health"][:n],
    })


class FakeStrategy:
    """Minimal strategy for testing."""

    name = "fake"

    def __init__(self, tickers=None):
        self._tickers = tickers or ["A.NS", "B.NS", "C.NS"]

    def screen(self, universe):
        return _make_screener_result(self._tickers)

    def allocate(self, candidates, capital):
        tickers = candidates["Ticker"].tolist()
        per_stock = capital / len(tickers)
        return {t: per_stock for t in tickers}

    def should_rebalance(self, current, target, days):
        return days >= 90


class EmptyStrategy:
    """Strategy that produces no candidates."""

    name = "empty"

    def screen(self, universe):
        return pd.DataFrame()

    def allocate(self, candidates, capital):
        return {}

    def should_rebalance(self, current, target, days):
        return True


# --- Engine Tests ---

class TestSimulateWindow:
    def test_returns_window_result(self):
        tickers = ["A.NS", "B.NS", "C.NS"]
        prices = _make_prices(tickers, start="2023-06-01", periods=150)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result, shares, cash, _surv = _simulate_window(
                strategy=FakeStrategy(tickers),
                window_id=0,
                screen_end="2023-06-01",
                hold_start="2023-06-01",
                hold_end="2023-12-31",
                capital=100000,
                prev_shares={},
                prev_cash=None,
            )

        assert isinstance(result, WindowResult)
        assert result.window_id == 0
        assert result.num_trades > 0
        assert result.holdings_count > 0
        assert result.total_fees > 0
        assert len(result.nav_history) > 0
        assert isinstance(shares, dict)
        assert isinstance(cash, float)

    def test_empty_strategy_returns_zero(self):
        with patch("diamond.analysis.screener.screen", return_value=pd.DataFrame()):
            result, shares, cash, _surv = _simulate_window(
                strategy=EmptyStrategy(),
                window_id=0,
                screen_end="2023-01-01",
                hold_start="2023-01-01",
                hold_end="2023-06-30",
                capital=100000,
                prev_shares={},
                prev_cash=None,
            )

        assert result.return_pct == 0.0
        assert result.num_trades == 0
        assert result.final_nav == 100000

    def test_applies_transaction_costs(self):
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-06-01", periods=150, base=1000)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result, shares, cash, _surv = _simulate_window(
                strategy=FakeStrategy(tickers),
                window_id=0,
                screen_end="2023-06-01",
                hold_start="2023-06-01",
                hold_end="2023-12-31",
                capital=100000,
                prev_shares={},
                prev_cash=None,
            )

        # Buy costs only (no sell — positions carry forward)
        assert result.total_fees > 0
        assert result.num_trades >= 1

    def test_price_download_failure_returns_flat(self):
        screener_df = _make_screener_result(["A.NS", "B.NS", "C.NS"])

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", side_effect=RuntimeError("network error")), \
             patch("diamond.backtest.engine.market.download_prices_daterange", side_effect=RuntimeError("network error")), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result, shares, cash, _surv = _simulate_window(
                strategy=FakeStrategy(),
                window_id=0,
                screen_end="2023-01-01",
                hold_start="2023-01-01",
                hold_end="2023-06-30",
                capital=100000,
                prev_shares={},
                prev_cash=None,
            )

        assert result.return_pct == 0.0
        assert result.final_nav == 100000

    def test_carries_positions_forward(self):
        """Positions from window N should be carried into window N+1."""
        tickers = ["A.NS", "B.NS"]
        prices = _make_prices(tickers, start="2023-06-01", periods=150, base=500)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            # First window: buy from scratch
            result1, shares1, cash1, _surv1 = _simulate_window(
                strategy=FakeStrategy(tickers),
                window_id=0,
                screen_end="2023-06-01",
                hold_start="2023-06-01",
                hold_end="2023-09-01",
                capital=100000,
                prev_shares={},
                prev_cash=None,
            )
            assert len(shares1) > 0
            first_trades = result1.num_trades

            # Second window with same allocation: should trade less (delta only)
            result2, shares2, cash2, _surv2 = _simulate_window(
                strategy=FakeStrategy(tickers),
                window_id=1,
                screen_end="2023-09-01",
                hold_start="2023-09-01",
                hold_end="2023-12-01",
                capital=result1.final_nav,
                prev_shares=shares1,
                prev_cash=cash1,
            )

        # Second window should have fewer or equal trades since positions carry
        assert result2.num_trades <= first_trades

    def test_delta_trading_reduces_fees(self):
        """When target allocation is similar, delta trading should cost less than full rebalance."""
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-01-01", periods=300, base=1000)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            # First window: full buy
            r1, s1, c1, _ = _simulate_window(
                strategy=FakeStrategy(tickers),
                window_id=0,
                screen_end="2023-01-01",
                hold_start="2023-01-01",
                hold_end="2023-06-01",
                capital=100000,
                prev_shares={},
                prev_cash=None,
            )
            # Second window: same stock, should need minimal trading
            r2, s2, c2, _ = _simulate_window(
                strategy=FakeStrategy(tickers),
                window_id=1,
                screen_end="2023-06-01",
                hold_start="2023-06-01",
                hold_end="2023-12-01",
                capital=r1.final_nav,
                prev_shares=s1,
                prev_cash=c1,
            )

        # Second window fees should be less than first (no full liquidation + rebuy)
        assert r2.total_fees <= r1.total_fees


def _make_benchmark(start="2023-01-01", periods=300, base=100):
    """Create synthetic benchmark price DataFrame."""
    dates = pd.bdate_range(start, periods=periods)
    prices = np.linspace(base, base * 1.15, periods)
    return pd.DataFrame({"^NSEI": prices}, index=dates)


class TestRunBacktest:
    def test_produces_windows(self):
        tickers = ["A.NS", "B.NS"]
        prices = _make_prices(tickers, start="2023-01-01", periods=300)
        bench = _make_benchmark(start="2023-01-01", periods=300)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="test",
                start_date="2023-01-01",
                end_date="2024-01-01",
                initial_capital=100000,
                window_months=6,
            )

        assert result.strategy == "test"
        assert len(result.windows) == 2  # 12 months / 6-month windows
        assert result.initial_capital == 100000
        assert result.final_nav > 0

    def test_capital_compounds_across_windows(self):
        tickers = ["A.NS"]
        dates = pd.bdate_range("2023-01-01", periods=400)
        prices = pd.DataFrame(
            {"A.NS": np.linspace(100, 150, 400)},
            index=dates,
        )
        bench = _make_benchmark(start="2023-01-01", periods=400)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="compound_test",
                start_date="2023-01-01",
                end_date="2024-06-30",
                initial_capital=100000,
                window_months=6,
            )

        # Window 1's final NAV should be Window 2's initial NAV
        if len(result.windows) >= 2:
            w0_final = result.windows[0].final_nav
            w1_initial = result.windows[1].initial_nav
            assert abs(w0_final - w1_initial) < 1.0

    def test_nav_history_aggregated(self):
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-01-01", periods=300)
        bench = _make_benchmark(start="2023-01-01", periods=300)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="nav_test",
                start_date="2023-01-01",
                end_date="2024-01-01",
                initial_capital=100000,
                window_months=6,
            )

        assert len(result.nav_history) > 0
        total_entries = sum(len(w.nav_history) for w in result.windows)
        assert len(result.nav_history) == total_entries

    def test_short_period_skips_tiny_window(self):
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-12-01", periods=30)
        bench = _make_benchmark(start="2023-12-01", periods=30)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="short_test",
                start_date="2023-12-01",
                end_date="2023-12-20",
                initial_capital=100000,
                window_months=6,
            )

        assert len(result.windows) == 0
        assert result.final_nav == 100000

    def test_empty_strategy_all_windows_flat(self):
        bench = _make_benchmark(start="2023-01-01", periods=300)
        with patch("diamond.analysis.screener.screen", return_value=pd.DataFrame()), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench):
            result = run_backtest(
                strategy=EmptyStrategy(),
                strategy_name="empty_test",
                start_date="2023-01-01",
                end_date="2024-01-01",
                initial_capital=100000,
                window_months=6,
            )

        for w in result.windows:
            assert w.return_pct == 0.0
        assert result.final_nav == 100000

    def test_benchmark_nav_populated(self):
        """Backtest result should include benchmark NAV history."""
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-01-01", periods=300)
        bench = _make_benchmark(start="2023-01-01", periods=300)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="bench_test",
                start_date="2023-01-01",
                end_date="2024-01-01",
                initial_capital=100000,
                window_months=6,
            )

        assert len(result.benchmark_nav) > 0
        # Benchmark should start near initial capital
        assert abs(result.benchmark_nav[0][1] - 100000) < 1.0

    def test_benchmark_failure_is_non_fatal(self):
        """If benchmark download fails, backtest still completes."""
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-01-01", periods=300)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", side_effect=RuntimeError("no data")), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="no_bench_test",
                start_date="2023-01-01",
                end_date="2024-01-01",
                initial_capital=100000,
                window_months=6,
            )

        # Backtest should still work, benchmark just empty
        assert len(result.windows) > 0
        assert result.benchmark_nav == []

    def test_survivorship_count_tracked(self):
        """Result should track how many tickers were survivorship-filtered."""
        tickers = ["A.NS"]
        prices = _make_prices(tickers, start="2023-01-01", periods=300)
        bench = _make_benchmark(start="2023-01-01", periods=300)
        screener_df = _make_screener_result(tickers)

        with patch("diamond.backtest.engine.market.download_ohlcv_daterange", return_value=(prices, pd.DataFrame())), \
             patch("diamond.backtest.engine.market.download_prices_daterange", return_value=bench), \
             patch("diamond.analysis.screener.screen", return_value=screener_df):
            result = run_backtest(
                strategy=FakeStrategy(tickers),
                strategy_name="surv_test",
                start_date="2023-01-01",
                end_date="2024-01-01",
                initial_capital=100000,
                window_months=6,
            )

        # No survivorship filtering expected (all tickers have data)
        assert result.survivorship_filtered == 0
