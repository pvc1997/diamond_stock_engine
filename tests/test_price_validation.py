"""Tests for price outlier detection and sanity checks."""

import logging

import numpy as np
import pandas as pd

from diamond.data.market import sanity_check_price, validate_prices


class TestValidatePrices:
    """Tests for validate_prices() — rolling z-score outlier detection."""

    def _make_prices(self, n=100, base=1000.0, seed=42):
        """Generate stable price series for testing."""
        np.random.seed(seed)
        dates = pd.bdate_range("2024-01-01", periods=n)
        returns = np.random.normal(0.001, 0.015, n)
        prices = base * np.cumprod(1 + returns)
        return pd.DataFrame({"TEST.NS": prices}, index=dates)

    def test_normal_prices_no_warnings(self, caplog):
        """Normal price data should produce no warnings."""
        df = self._make_prices()
        with caplog.at_level(logging.WARNING):
            result = validate_prices(df)
        assert "outlier" not in caplog.text.lower()
        # Returns the same DataFrame unmodified
        pd.testing.assert_frame_equal(result, df)

    def test_spike_flagged(self, caplog):
        """A 10x price spike should be flagged as an outlier."""
        df = self._make_prices(n=100)
        # Inject a massive spike at row 50
        df.iloc[50, 0] = df.iloc[49, 0] * 10
        with caplog.at_level(logging.WARNING):
            result = validate_prices(df)
        assert "outlier" in caplog.text.lower()
        assert "TEST.NS" in caplog.text
        # Data is NOT removed (fail-open)
        pd.testing.assert_frame_equal(result, df)

    def test_returns_dataframe_unchanged(self):
        """validate_prices must return the exact same DataFrame object."""
        df = self._make_prices()
        result = validate_prices(df)
        assert result is df

    def test_short_series_skipped(self, caplog):
        """Series shorter than 21 rows should be silently skipped."""
        dates = pd.bdate_range("2024-01-01", periods=15)
        df = pd.DataFrame({"SHORT.NS": np.linspace(100, 200, 15)}, index=dates)
        with caplog.at_level(logging.WARNING):
            validate_prices(df)
        assert "outlier" not in caplog.text.lower()

    def test_multi_ticker(self, caplog):
        """Outlier detection works per-column for multi-ticker DataFrames."""
        df = self._make_prices(n=100)
        df["CLEAN.NS"] = self._make_prices(n=100, base=500, seed=99)["TEST.NS"].values
        # Spike only in TEST.NS
        df.iloc[60, 0] = df.iloc[59, 0] * 8
        with caplog.at_level(logging.WARNING):
            validate_prices(df)
        assert "TEST.NS" in caplog.text
        assert "CLEAN.NS" not in caplog.text


class TestSanityCheckPrice:
    """Tests for sanity_check_price() — single-day move >50% detection."""

    def test_normal_move_passes(self):
        """A 5% daily move is normal and should pass."""
        assert sanity_check_price("RELIANCE.NS", 2625.0, 2500.0) is True

    def test_large_but_below_threshold(self):
        """A 49% move should still pass (just under threshold)."""
        assert sanity_check_price("TCS.NS", 1490.0, 1000.0) is True

    def test_50pct_spike_fails(self):
        """A 50%+ move should be flagged as likely data error."""
        assert sanity_check_price("INFY.NS", 1510.0, 1000.0) is False

    def test_10x_spike_fails(self):
        """A 10x spike is obviously bad data."""
        assert sanity_check_price("SBIN.NS", 5000.0, 500.0) is False

    def test_crash_50pct_fails(self):
        """A >50% drop should also be flagged."""
        assert sanity_check_price("HDFC.NS", 400.0, 1000.0) is False

    def test_zero_last_known_passes(self):
        """If last_known is 0 or negative, we can't compare — pass through."""
        assert sanity_check_price("NEW.NS", 100.0, 0.0) is True
        assert sanity_check_price("NEW.NS", 100.0, -5.0) is True

    def test_logs_warning_on_failure(self, caplog):
        """Failing sanity check should log a warning."""
        with caplog.at_level(logging.WARNING):
            sanity_check_price("BAD.NS", 5000.0, 500.0)
        assert "sanity check failed" in caplog.text.lower()
        assert "BAD.NS" in caplog.text
