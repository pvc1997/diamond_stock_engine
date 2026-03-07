"""Tests for portfolio risk management engine."""

from pathlib import Path

import numpy as np
import pandas as pd

from diamond.monitoring.risk import (
    RiskReport,
    calculate_cvar,
    calculate_var,
    correlation_matrix,
    generate_signals,
    portfolio_beta,
    portfolio_returns,
)


class TestPortfolioReturns:
    def test_basic_returns(self, sample_prices: pd.DataFrame):
        holdings = {"RELIANCE.NS": 10, "TCS.NS": 5}
        ret = portfolio_returns(holdings, sample_prices)
        assert len(ret) > 0
        assert not ret.isna().all()

    def test_empty_holdings(self, sample_prices: pd.DataFrame):
        ret = portfolio_returns({}, sample_prices)
        assert ret.empty

    def test_missing_tickers(self, sample_prices: pd.DataFrame):
        holdings = {"FAKECO.NS": 100}
        ret = portfolio_returns(holdings, sample_prices)
        assert ret.empty

    def test_returns_are_weighted(self, sample_prices: pd.DataFrame):
        # Single stock portfolio should match that stock's returns
        holdings = {"RELIANCE.NS": 100}
        ret = portfolio_returns(holdings, sample_prices)
        stock_ret = sample_prices["RELIANCE.NS"].pct_change().dropna()
        # Should be very close (slight alignment differences possible)
        assert len(ret) == len(stock_ret)
        assert abs(ret.mean() - stock_ret.mean()) < 0.001


class TestVaR:
    def _make_returns(self, n=500, seed=42):
        np.random.seed(seed)
        return pd.Series(np.random.normal(0.0005, 0.02, n))

    def test_var_95_positive(self):
        ret = self._make_returns()
        var = calculate_var(ret, 0.95, 100_000)
        assert var > 0

    def test_var_99_greater_than_95(self):
        ret = self._make_returns()
        var95 = calculate_var(ret, 0.95, 100_000)
        var99 = calculate_var(ret, 0.99, 100_000)
        assert var99 >= var95

    def test_var_scales_with_portfolio(self):
        ret = self._make_returns()
        var_small = calculate_var(ret, 0.95, 100_000)
        var_large = calculate_var(ret, 0.95, 1_000_000)
        assert abs(var_large / var_small - 10) < 0.1

    def test_var_empty_returns(self):
        assert calculate_var(pd.Series(dtype=float), 0.95, 100_000) == 0.0

    def test_var_insufficient_data(self):
        ret = pd.Series([0.01, 0.02, -0.01])
        assert calculate_var(ret, 0.95, 100_000) == 0.0


class TestCVaR:
    def test_cvar_greater_than_var(self):
        np.random.seed(42)
        ret = pd.Series(np.random.normal(0.0005, 0.02, 500))
        var = calculate_var(ret, 0.95, 100_000)
        cvar = calculate_cvar(ret, 0.95, 100_000)
        assert cvar >= var

    def test_cvar_empty(self):
        assert calculate_cvar(pd.Series(dtype=float), 0.95, 100_000) == 0.0


class TestCorrelation:
    def test_correlation_shape(self, sample_prices: pd.DataFrame):
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
        corr = correlation_matrix(sample_prices, tickers)
        assert corr.shape == (3, 3)

    def test_diagonal_is_one(self, sample_prices: pd.DataFrame):
        tickers = ["RELIANCE.NS", "TCS.NS"]
        corr = correlation_matrix(sample_prices, tickers)
        for t in tickers:
            assert abs(corr.loc[t, t] - 1.0) < 0.001

    def test_single_ticker_returns_empty(self, sample_prices: pd.DataFrame):
        corr = correlation_matrix(sample_prices, ["RELIANCE.NS"])
        assert corr.empty


class TestPortfolioBeta:
    def test_beta_near_one_for_benchmark(self):
        np.random.seed(42)
        ret = pd.Series(np.random.normal(0.0005, 0.02, 252))
        beta = portfolio_beta(ret, ret)
        assert abs(beta - 1.0) < 0.001

    def test_beta_with_different_series(self):
        np.random.seed(42)
        bench = pd.Series(np.random.normal(0.0005, 0.02, 252))
        port = bench * 1.5 + pd.Series(np.random.normal(0, 0.005, 252))
        beta = portfolio_beta(port, bench)
        assert beta > 1.0  # Should be ~1.5


class TestSignals:
    def _make_report(self, **overrides) -> RiskReport:
        defaults = dict(
            timestamp="2024-01-01 10:00:00",
            nav=100_000,
            high_water_mark=100_000,
            drawdown_pct=0.0,
            var_95=1500,
            var_99=2500,
            cvar_95=2000,
            max_correlation=0.5,
            avg_correlation=0.3,
            beta=1.0,
            volatility_annual=20.0,
        )
        defaults.update(overrides)
        return RiskReport(**defaults)

    def test_no_signals_healthy(self):
        report = self._make_report()
        assert generate_signals(report) == []

    def test_drawdown_warning(self):
        report = self._make_report(drawdown_pct=12.0)
        signals = generate_signals(report)
        assert len(signals) == 1
        assert "WARNING" in signals[0]

    def test_drawdown_critical(self):
        report = self._make_report(drawdown_pct=16.0)
        signals = generate_signals(report)
        assert any("CRITICAL" in s for s in signals)

    def test_var_warning(self):
        # VaR > 3% of NAV
        report = self._make_report(nav=100_000, var_95=4000)
        signals = generate_signals(report)
        assert any("VaR" in s for s in signals)

    def test_correlation_warning(self):
        report = self._make_report(avg_correlation=0.85)
        signals = generate_signals(report)
        assert any("correlation" in s for s in signals)

    def test_volatility_warning(self):
        report = self._make_report(volatility_annual=35.0)
        signals = generate_signals(report)
        assert any("volatility" in s.lower() for s in signals)
