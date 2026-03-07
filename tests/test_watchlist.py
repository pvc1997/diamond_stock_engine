"""Tests for stock watchlist."""

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from diamond.data.watchlist import (
    WatchlistEntry,
    WatchlistSignal,
    add_ticker,
    remove_ticker,
    load_watchlist,
    save_watchlist,
    check_signals,
    fetch_watchlist_prices,
    _compute_rsi,
)


@pytest.fixture
def watchlist_dir(tmp_path, monkeypatch):
    """Redirect watchlist storage to tmp_path."""
    monkeypatch.setattr(
        "diamond.data.watchlist._watchlist_path",
        lambda: tmp_path / "watchlist.json",
    )
    # Also redirect for add/remove which call load/save
    monkeypatch.setattr(
        "diamond.data.watchlist.get_config",
        lambda: type("C", (), {"data_dir": tmp_path})(),
    )
    return tmp_path


class TestCRUD:
    def test_add_ticker(self, watchlist_dir):
        entry = add_ticker("RELIANCE.NS", notes="tracking")
        assert entry.ticker == "RELIANCE.NS"
        assert entry.notes == "tracking"

        entries = load_watchlist()
        assert "RELIANCE.NS" in entries

    def test_add_normalizes_ticker(self, watchlist_dir):
        entry = add_ticker("RELIANCE")
        assert entry.ticker == "RELIANCE.NS"

    def test_add_with_alerts(self, watchlist_dir):
        entry = add_ticker("TCS.NS", price_above=4000, price_below=3000)
        assert entry.price_above == 4000
        assert entry.price_below == 3000

    def test_remove_ticker(self, watchlist_dir):
        add_ticker("RELIANCE.NS")
        assert remove_ticker("RELIANCE.NS") is True
        entries = load_watchlist()
        assert "RELIANCE.NS" not in entries

    def test_remove_normalizes(self, watchlist_dir):
        add_ticker("RELIANCE")
        assert remove_ticker("RELIANCE") is True

    def test_remove_nonexistent(self, watchlist_dir):
        assert remove_ticker("UNKNOWN.NS") is False

    def test_load_empty(self, watchlist_dir):
        entries = load_watchlist()
        assert entries == {}

    def test_load_corrupt(self, watchlist_dir):
        path = watchlist_dir / "watchlist.json"
        path.write_text("not valid json{{{")
        entries = load_watchlist()
        assert entries == {}


class TestSignals:
    @patch("diamond.data.market.download_prices", return_value=pd.DataFrame())
    def test_price_above_signal(self, mock_dl, watchlist_dir):
        entries = {
            "RELIANCE.NS": WatchlistEntry("RELIANCE.NS", "2026-01-01", price_above=2800),
        }
        prices = {"RELIANCE.NS": {"price": 2900, "change_pct": 1.0, "sector": "Energy"}}

        signals = check_signals(entries, prices)

        price_signals = [s for s in signals if s.signal_type == "price_above"]
        assert len(price_signals) == 1
        assert "2,800" in price_signals[0].message

    @patch("diamond.data.market.download_prices", return_value=pd.DataFrame())
    def test_price_below_signal(self, mock_dl, watchlist_dir):
        entries = {
            "TCS.NS": WatchlistEntry("TCS.NS", "2026-01-01", price_below=3000),
        }
        prices = {"TCS.NS": {"price": 2900, "change_pct": -2.0, "sector": "Technology"}}

        signals = check_signals(entries, prices)

        price_signals = [s for s in signals if s.signal_type == "price_below"]
        assert len(price_signals) == 1

    @patch("diamond.data.market.download_prices", return_value=pd.DataFrame())
    def test_no_signal_when_within_range(self, mock_dl, watchlist_dir):
        entries = {
            "RELIANCE.NS": WatchlistEntry("RELIANCE.NS", "2026-01-01", price_above=3000, price_below=2000),
        }
        prices = {"RELIANCE.NS": {"price": 2500, "change_pct": 0, "sector": "Energy"}}

        signals = check_signals(entries, prices)

        price_signals = [s for s in signals if s.signal_type in ("price_above", "price_below")]
        assert len(price_signals) == 0


class TestRSI:
    def test_rsi_rising_prices(self):
        prices = list(np.linspace(100, 200, 30))
        rsi = _compute_rsi(prices)
        assert rsi > 60

    def test_rsi_falling_prices(self):
        prices = list(np.linspace(200, 100, 30))
        rsi = _compute_rsi(prices)
        assert rsi < 40

    def test_rsi_short_series(self):
        rsi = _compute_rsi([100, 101, 102])
        assert rsi == 50.0  # Default for insufficient data
