"""Shared test fixtures.

Mock market data so tests never hit real APIs.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_prices() -> pd.DataFrame:
    """Generate realistic-looking price data for testing."""
    np.random.seed(42)
    dates = pd.bdate_range("2023-01-01", periods=252)  # ~1 year trading days
    tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

    data = {}
    for ticker in tickers:
        base = np.random.uniform(500, 3000)
        returns = np.random.normal(0.0005, 0.02, len(dates))
        prices = base * np.cumprod(1 + returns)
        data[ticker] = prices

    return pd.DataFrame(data, index=dates)


@pytest.fixture
def sample_universe() -> pd.DataFrame:
    """Generate a screened universe DataFrame for testing."""
    return pd.DataFrame({
        "Ticker": [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "BHARTIARTL.NS", "SBIN.NS", "BAJFINANCE.NS", "MARUTI.NS", "DRREDDY.NS",
        ],
        "Alpha": [0.8, 1.2, 0.5, 0.9, 0.6, 1.1, 0.4, 0.7, 0.3, 0.85],
        "Beta": [1.1, 0.9, 1.0, 0.85, 1.05, 0.95, 1.2, 1.3, 0.8, 0.7],
        "CAGR": [0.15, 0.22, 0.12, 0.18, 0.14, 0.20, 0.10, 0.16, 0.08, 0.19],
        "Volatility": [0.25, 0.20, 0.22, 0.18, 0.24, 0.21, 0.28, 0.30, 0.19, 0.17],
        "Sector": [
            "Energy", "Technology", "Financial Services", "Technology",
            "Financial Services", "Telecom", "Financial Services",
            "Financial Services", "Automobile", "Healthcare",
        ],
    })


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Provide a temporary data directory for tests."""
    (tmp_path / "cache").mkdir()
    (tmp_path / "ledgers").mkdir()
    return tmp_path
