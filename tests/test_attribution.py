"""Tests for performance attribution module."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from diamond.analysis.attribution import (
    AttributionReport,
    SectorAttribution,
    StockAttribution,
    _benchmark_weights,
    _compute_sector_attributions,
    _compute_stock_attributions,
    _compute_tracking_error,
    _parse_period,
    compute_attribution,
)
from diamond.data.ledger import Ledger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices_df(tickers: list[str], start_price: dict[str, float], end_price: dict[str, float], days: int = 60) -> pd.DataFrame:
    """Build a simple price DataFrame with linear interpolation."""
    dates = pd.bdate_range(date.today() - timedelta(days=days + 30), periods=days)
    data = {}
    for t in tickers:
        s = start_price.get(t, 100.0)
        e = end_price.get(t, 100.0)
        data[t] = np.linspace(s, e, len(dates))
    return pd.DataFrame(data, index=dates)


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

class TestParsePeriod:
    def test_1m(self):
        start, end, label = _parse_period("1M")
        assert label == "1M"
        expected_start = (date.today() - timedelta(days=30)).isoformat()
        assert start == expected_start
        assert end == date.today().isoformat()

    def test_3m(self):
        start, end, label = _parse_period("3M")
        assert label == "3M"
        expected_start = (date.today() - timedelta(days=90)).isoformat()
        assert start == expected_start

    def test_6m(self):
        start, _, label = _parse_period("6M")
        assert label == "6M"
        expected_start = (date.today() - timedelta(days=180)).isoformat()
        assert start == expected_start

    def test_1y(self):
        start, _, label = _parse_period("1Y")
        assert label == "1Y"
        expected_start = (date.today() - timedelta(days=365)).isoformat()
        assert start == expected_start

    def test_ytd(self):
        start, end, label = _parse_period("YTD")
        assert label == "YTD"
        assert start == date(date.today().year, 1, 1).isoformat()
        assert end == date.today().isoformat()

    def test_custom_range(self):
        start, end, label = _parse_period("2025-01-01:2025-06-30")
        assert start == "2025-01-01"
        assert end == "2025-06-30"
        assert "2025-01-01" in label
        assert "2025-06-30" in label

    def test_case_insensitive(self):
        s1, _, _ = _parse_period("3m")
        s2, _, _ = _parse_period("3M")
        assert s1 == s2

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError, match="Invalid period"):
            _parse_period("2W")

    def test_invalid_date_format_raises(self):
        with pytest.raises(ValueError):
            _parse_period("01-01-2025:06-30-2025")


# ---------------------------------------------------------------------------
# Benchmark weights
# ---------------------------------------------------------------------------

class TestBenchmarkWeights:
    def test_equal_weight(self):
        tickers = ["A.NS", "B.NS", "C.NS", "D.NS"]
        weights = _benchmark_weights(tickers)
        assert len(weights) == 4
        assert all(abs(w - 0.25) < 0.001 for w in weights.values())

    def test_empty_list(self):
        assert _benchmark_weights([]) == {}

    def test_nifty50_weight(self):
        from diamond.data.universe import NIFTY_50
        weights = _benchmark_weights(NIFTY_50)
        assert len(weights) == len(NIFTY_50)
        expected = round(1.0 / len(NIFTY_50), 4)
        assert all(w == expected for w in weights.values())


# ---------------------------------------------------------------------------
# Stock-level attribution
# ---------------------------------------------------------------------------

class TestStockAttribution:
    def test_basic_two_stock(self):
        holdings = {"RELIANCE.NS": 10, "TCS.NS": 5}
        start_prices = {"RELIANCE.NS": 100.0, "TCS.NS": 200.0}
        end_prices = {"RELIANCE.NS": 110.0, "TCS.NS": 190.0}
        bm_weights = {"RELIANCE.NS": 0.02, "TCS.NS": 0.02}

        attrs = _compute_stock_attributions(holdings, start_prices, end_prices, bm_weights)

        assert len(attrs) == 2

        # Portfolio start value: 10*100 + 5*200 = 2000
        rel = next(a for a in attrs if a.ticker == "RELIANCE.NS")
        tcs = next(a for a in attrs if a.ticker == "TCS.NS")

        # Weights: RELIANCE = 1000/2000 = 0.5, TCS = 1000/2000 = 0.5
        assert rel.weight == 0.5
        assert tcs.weight == 0.5

        # Returns: RELIANCE = 10%, TCS = -5%
        assert rel.stock_return == 0.1
        assert tcs.stock_return == -0.05

        # Contributions: 0.5 * 0.1 = 0.05, 0.5 * -0.05 = -0.025
        assert rel.contribution == 0.05
        assert tcs.contribution == -0.025

        # Active weights
        assert rel.active_weight == round(0.5 - 0.02, 4)
        assert tcs.active_weight == round(0.5 - 0.02, 4)

    def test_non_benchmark_stock(self):
        holdings = {"AARTIIND.NS": 10}
        start_prices = {"AARTIIND.NS": 500.0}
        end_prices = {"AARTIIND.NS": 550.0}
        bm_weights = {}  # Not in benchmark

        attrs = _compute_stock_attributions(holdings, start_prices, end_prices, bm_weights)
        assert len(attrs) == 1
        assert attrs[0].benchmark_weight == 0.0
        assert attrs[0].active_weight == attrs[0].weight

    def test_empty_holdings(self):
        attrs = _compute_stock_attributions({}, {}, {}, {})
        assert attrs == []

    def test_missing_start_price_skips(self):
        holdings = {"RELIANCE.NS": 10}
        start_prices = {}  # No start price
        end_prices = {"RELIANCE.NS": 110.0}
        attrs = _compute_stock_attributions(holdings, start_prices, end_prices, {})
        assert attrs == []

    def test_contributions_sum_to_portfolio_return(self):
        holdings = {"RELIANCE.NS": 20, "TCS.NS": 10, "INFY.NS": 15}
        start_prices = {"RELIANCE.NS": 100.0, "TCS.NS": 200.0, "INFY.NS": 150.0}
        end_prices = {"RELIANCE.NS": 112.0, "TCS.NS": 210.0, "INFY.NS": 140.0}
        bm_weights = {}

        attrs = _compute_stock_attributions(holdings, start_prices, end_prices, bm_weights)
        total_contrib = sum(a.contribution for a in attrs)

        # Manual portfolio return:
        # Start: 20*100 + 10*200 + 15*150 = 2000 + 2000 + 2250 = 6250
        # End:   20*112 + 10*210 + 15*140 = 2240 + 2100 + 2100 = 6440
        # Return = (6440-6250)/6250 = 0.0304
        assert abs(total_contrib - 0.0304) < 0.001


# ---------------------------------------------------------------------------
# Sector-level attribution (Brinson)
# ---------------------------------------------------------------------------

class TestSectorAttribution:
    def _make_stock_attrs(self):
        """Two sectors: Technology and Energy."""
        return [
            StockAttribution("TCS.NS", "Technology", 0.4, 0.10, 0.04, 0.02, 0.38),
            StockAttribution("INFY.NS", "Technology", 0.2, 0.05, 0.01, 0.02, 0.18),
            StockAttribution("RELIANCE.NS", "Energy", 0.4, -0.05, -0.02, 0.02, 0.38),
        ]

    def test_brinson_decomposition_sums(self):
        stock_attrs = self._make_stock_attrs()
        bm_weights = {
            "TCS.NS": 0.02, "INFY.NS": 0.02,
            "RELIANCE.NS": 0.02, "HDFCBANK.NS": 0.02,
        }
        bm_returns = {
            "TCS.NS": 0.08, "INFY.NS": 0.06,
            "RELIANCE.NS": -0.03, "HDFCBANK.NS": 0.02,
        }
        bm_total_return = sum(bm_weights[t] * bm_returns[t] for t in bm_weights)

        sector_attrs = _compute_sector_attributions(
            stock_attrs, bm_weights, bm_returns, bm_total_return,
        )

        # Each sector: total = allocation + selection + interaction
        for sa in sector_attrs:
            assert abs(sa.total_effect - (sa.allocation_effect + sa.selection_effect + sa.interaction_effect)) < 0.0001

    def test_sector_stock_counts(self):
        stock_attrs = self._make_stock_attrs()
        bm_weights = {"TCS.NS": 0.02, "INFY.NS": 0.02, "RELIANCE.NS": 0.02}
        bm_returns = {"TCS.NS": 0.08, "INFY.NS": 0.06, "RELIANCE.NS": -0.03}

        sector_attrs = _compute_sector_attributions(stock_attrs, bm_weights, bm_returns, 0.01)
        tech = next(s for s in sector_attrs if s.sector == "Technology")
        energy = next(s for s in sector_attrs if s.sector == "Energy")

        assert tech.stock_count == 2
        assert energy.stock_count == 1

    def test_benchmark_only_sector(self):
        """Sector present in benchmark but not portfolio."""
        stock_attrs = [
            StockAttribution("TCS.NS", "Technology", 1.0, 0.10, 0.10, 0.02, 0.98),
        ]
        bm_weights = {"TCS.NS": 0.5, "HDFCBANK.NS": 0.5}
        bm_returns = {"TCS.NS": 0.08, "HDFCBANK.NS": 0.05}
        bm_total = 0.065

        sector_attrs = _compute_sector_attributions(stock_attrs, bm_weights, bm_returns, bm_total)
        fin = next(s for s in sector_attrs if s.sector == "Financial Services")

        # Portfolio has 0 weight in Financial Services
        assert fin.portfolio_weight == 0.0
        assert fin.stock_count == 0


# ---------------------------------------------------------------------------
# Tracking error
# ---------------------------------------------------------------------------

class TestTrackingError:
    def test_identical_returns_zero_te(self):
        idx = pd.bdate_range("2024-01-01", periods=60)
        returns = pd.Series(np.random.normal(0.001, 0.01, 60), index=idx)
        te = _compute_tracking_error(returns, returns)
        assert te == 0.0

    def test_different_returns_positive_te(self):
        idx = pd.bdate_range("2024-01-01", periods=60)
        np.random.seed(42)
        port = pd.Series(np.random.normal(0.001, 0.02, 60), index=idx)
        bm = pd.Series(np.random.normal(0.0005, 0.015, 60), index=idx)
        te = _compute_tracking_error(port, bm)
        assert te > 0

    def test_short_series_returns_zero(self):
        idx = pd.bdate_range("2024-01-01", periods=1)
        port = pd.Series([0.01], index=idx)
        bm = pd.Series([0.005], index=idx)
        te = _compute_tracking_error(port, bm)
        assert te == 0.0


# ---------------------------------------------------------------------------
# Top / bottom contributors
# ---------------------------------------------------------------------------

class TestContributorSorting:
    @patch("diamond.analysis.attribution.market")
    def test_top_bottom_sorted(self, mock_market, tmp_path):
        """Top contributors sorted descending, bottom sorted ascending."""
        # Set up ledger
        ledger = Ledger("test_sort", db_path=tmp_path / "test_sort.db")
        ledger.set_cash(0)
        for ticker, shares in [
            ("RELIANCE.NS", 10), ("TCS.NS", 10), ("INFY.NS", 10),
            ("HDFCBANK.NS", 10), ("ICICIBANK.NS", 10), ("SBIN.NS", 10),
        ]:
            ledger.update_holding(ticker, shares, 100.0)

        # Prices: each stock has a distinct return
        tickers_all = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"]
        start_p = {t: 100.0 for t in tickers_all}
        # Returns: +20%, +15%, +5%, -3%, -10%, -15%
        end_p = {"RELIANCE.NS": 120, "TCS.NS": 115, "INFY.NS": 105, "HDFCBANK.NS": 97, "ICICIBANK.NS": 90, "SBIN.NS": 85}

        from diamond.data.universe import NIFTY_50
        all_tickers = sorted(set(tickers_all + list(NIFTY_50)))
        for t in all_tickers:
            if t not in start_p:
                start_p[t] = 100.0
            if t not in end_p:
                end_p[t] = 102.0

        dates = pd.bdate_range("2024-10-01", periods=60)
        df_data = {}
        for t in all_tickers:
            df_data[t] = np.linspace(start_p[t], end_p[t], len(dates))
        prices_df = pd.DataFrame(df_data, index=dates)

        bm_idx_df = pd.DataFrame({"^NSEI": np.linspace(20000, 20500, len(dates))}, index=dates)

        mock_market.download_prices_daterange.side_effect = [prices_df, bm_idx_df]

        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution("test_sort", period="2024-10-01:2024-12-20")

        # Top contributors should be ordered by contribution descending
        top_contribs = [t.contribution for t in report.top_contributors]
        assert top_contribs == sorted(top_contribs, reverse=True)

        # Bottom contributors should be ordered by contribution ascending
        bottom_contribs = [t.contribution for t in report.bottom_contributors]
        assert bottom_contribs == sorted(bottom_contribs)

        # Top 5 first element should be RELIANCE (highest return, equal weight)
        assert report.top_contributors[0].ticker == "RELIANCE.NS"
        # Bottom first should be SBIN (worst return)
        assert report.bottom_contributors[0].ticker == "SBIN.NS"


# ---------------------------------------------------------------------------
# Integration: compute_attribution with mocked market data
# ---------------------------------------------------------------------------

class TestComputeAttribution:
    @patch("diamond.analysis.attribution.market")
    def test_basic_attribution(self, mock_market, tmp_path):
        """Full attribution with 2 stocks, known returns."""
        ledger = Ledger("test_basic", db_path=tmp_path / "test_basic.db")
        ledger.set_cash(0)
        ledger.update_holding("RELIANCE.NS", 10, 100.0)
        ledger.update_holding("TCS.NS", 10, 200.0)

        from diamond.data.universe import NIFTY_50
        all_tickers = sorted(set(["RELIANCE.NS", "TCS.NS"] + list(NIFTY_50)))

        dates = pd.bdate_range("2024-10-01", periods=60)
        data = {}
        for t in all_tickers:
            if t == "RELIANCE.NS":
                data[t] = np.linspace(100, 110, len(dates))
            elif t == "TCS.NS":
                data[t] = np.linspace(200, 190, len(dates))
            else:
                data[t] = np.linspace(100, 102, len(dates))
        prices_df = pd.DataFrame(data, index=dates)
        bm_idx_df = pd.DataFrame({"^NSEI": np.linspace(20000, 20400, len(dates))}, index=dates)

        mock_market.download_prices_daterange.side_effect = [prices_df, bm_idx_df]

        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution("test_basic", period="2024-10-01:2024-12-20")

        assert isinstance(report, AttributionReport)
        assert report.strategy == "test_basic"
        assert report.start_date == "2024-10-01"
        assert report.end_date == "2024-12-20"

        # Portfolio: RELIANCE 10*100=1000, TCS 10*200=2000 => total 3000
        # RELIANCE: w=1/3, ret=10% => contrib=3.33%
        # TCS: w=2/3, ret=-5% => contrib=-3.33%
        # Total ~ 0%
        assert abs(report.portfolio_return) < 0.01

        # Active return should differ from 0 since benchmark has different returns
        assert isinstance(report.active_return, float)

        # Sector attributions should exist
        assert len(report.sector_attributions) > 0

    @patch("diamond.analysis.attribution.market")
    def test_empty_portfolio(self, mock_market, tmp_path):
        """Empty portfolio returns zeroed report."""
        ledger = Ledger("test_empty", db_path=tmp_path / "test_empty.db")
        ledger.set_cash(50000)
        # No holdings

        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution("test_empty", period="3M")

        assert report.portfolio_return == 0.0
        assert report.benchmark_return == 0.0
        assert report.active_return == 0.0
        assert report.stock_attributions == []
        assert report.sector_attributions == []
        # Market data should not be fetched
        mock_market.download_prices_daterange.assert_not_called()

    @patch("diamond.analysis.attribution.market")
    def test_single_stock_portfolio(self, mock_market, tmp_path):
        """Single stock: contribution equals portfolio return."""
        ledger = Ledger("test_single", db_path=tmp_path / "test_single.db")
        ledger.set_cash(0)
        ledger.update_holding("RELIANCE.NS", 10, 100.0)

        from diamond.data.universe import NIFTY_50
        all_tickers = sorted(set(["RELIANCE.NS"] + list(NIFTY_50)))

        dates = pd.bdate_range("2024-10-01", periods=60)
        data = {}
        for t in all_tickers:
            if t == "RELIANCE.NS":
                data[t] = np.linspace(100, 115, len(dates))  # +15%
            else:
                data[t] = np.linspace(100, 102, len(dates))
        prices_df = pd.DataFrame(data, index=dates)
        bm_idx_df = pd.DataFrame({"^NSEI": np.linspace(20000, 20400, len(dates))}, index=dates)

        mock_market.download_prices_daterange.side_effect = [prices_df, bm_idx_df]

        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution("test_single", period="2024-10-01:2024-12-20")

        assert len(report.stock_attributions) == 1
        sa = report.stock_attributions[0]
        assert sa.weight == 1.0
        assert sa.stock_return == 0.15
        assert sa.contribution == 0.15
        assert report.portfolio_return == 0.15

    @patch("diamond.analysis.attribution.market")
    def test_current_prices_override(self, mock_market, tmp_path):
        """current_prices overrides end prices from market data."""
        ledger = Ledger("test_override", db_path=tmp_path / "test_override.db")
        ledger.set_cash(0)
        ledger.update_holding("RELIANCE.NS", 10, 100.0)

        from diamond.data.universe import NIFTY_50
        all_tickers = sorted(set(["RELIANCE.NS"] + list(NIFTY_50)))

        dates = pd.bdate_range("2024-10-01", periods=60)
        data = {}
        for t in all_tickers:
            data[t] = np.linspace(100, 110, len(dates))
        prices_df = pd.DataFrame(data, index=dates)
        bm_idx_df = pd.DataFrame({"^NSEI": np.linspace(20000, 20400, len(dates))}, index=dates)

        mock_market.download_prices_daterange.side_effect = [prices_df, bm_idx_df]

        # Override RELIANCE end price to 120 (instead of 110 from market data)
        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution(
                "test_override", period="2024-10-01:2024-12-20",
                current_prices={"RELIANCE.NS": 120.0},
            )

        # Single stock with start=100, end=120 => return = 20%
        assert report.portfolio_return == 0.2

    @patch("diamond.analysis.attribution.market")
    def test_tracking_error_computed(self, mock_market, tmp_path):
        """Tracking error should be a non-negative float."""
        ledger = Ledger("test_te", db_path=tmp_path / "test_te.db")
        ledger.set_cash(0)
        ledger.update_holding("RELIANCE.NS", 10, 100.0)

        from diamond.data.universe import NIFTY_50
        all_tickers = sorted(set(["RELIANCE.NS"] + list(NIFTY_50)))

        np.random.seed(99)
        dates = pd.bdate_range("2024-10-01", periods=60)
        data = {}
        for t in all_tickers:
            base = 100
            returns = np.random.normal(0.001, 0.02, len(dates))
            data[t] = base * np.cumprod(1 + returns)
        prices_df = pd.DataFrame(data, index=dates)

        bm_returns = np.random.normal(0.0005, 0.015, len(dates))
        bm_prices = 20000 * np.cumprod(1 + bm_returns)
        bm_idx_df = pd.DataFrame({"^NSEI": bm_prices}, index=dates)

        mock_market.download_prices_daterange.side_effect = [prices_df, bm_idx_df]

        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution("test_te", period="2024-10-01:2024-12-20")

        assert report.tracking_error >= 0.0
        assert isinstance(report.tracking_error, float)

    @patch("diamond.analysis.attribution.market")
    def test_empty_price_data(self, mock_market, tmp_path):
        """If market returns empty DataFrame, report is zeroed."""
        ledger = Ledger("test_no_prices", db_path=tmp_path / "test_no_prices.db")
        ledger.set_cash(0)
        ledger.update_holding("RELIANCE.NS", 10, 100.0)

        mock_market.download_prices_daterange.return_value = pd.DataFrame()

        with patch("diamond.analysis.attribution.Ledger", return_value=ledger):
            report = compute_attribution("test_no_prices", period="3M")

        assert report.portfolio_return == 0.0
        assert report.benchmark_return == 0.0


# ---------------------------------------------------------------------------
# Frozen dataclass checks
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_stock_attribution_frozen(self):
        sa = StockAttribution("TCS.NS", "Technology", 0.5, 0.1, 0.05, 0.02, 0.48)
        with pytest.raises(AttributeError):
            sa.weight = 0.9  # type: ignore

    def test_sector_attribution_frozen(self):
        sa = SectorAttribution("Tech", 0.5, 0.3, 0.1, 0.08, 0.01, 0.005, 0.002, 0.017, 3)
        with pytest.raises(AttributeError):
            sa.total_effect = 0.0  # type: ignore

    def test_attribution_report_mutable(self):
        """AttributionReport is mutable (not frozen)."""
        report = AttributionReport(
            strategy="test", period="3M", start_date="2024-01-01",
            end_date="2024-03-31", portfolio_return=0.05,
            benchmark_return=0.03, active_return=0.02,
        )
        report.tracking_error = 0.15  # Should work - not frozen
        assert report.tracking_error == 0.15
