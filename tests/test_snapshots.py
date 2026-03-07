"""Tests for portfolio snapshots."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import diamond.data.snapshots as snap_mod
from diamond.data.snapshots import (
    delete_snapshot,
    diff_snapshots,
    diff_with_current,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    """Redirect snapshot storage to tmp_path."""
    snap_file = tmp_path / "snapshots.json"
    monkeypatch.setattr(snap_mod, "_SNAPSHOTS_FILE", snap_file)
    return snap_file


def _mock_ledger(holdings, cash=50000.0):
    """Create a mock Ledger with given holdings and cash."""
    ledger = MagicMock()
    ledger.get_holdings.return_value = holdings
    ledger.get_cash.return_value = cash
    return ledger


def _mock_prices_df(prices_map):
    """Create a DataFrame like download_prices returns."""
    return pd.DataFrame(prices_map, index=[0])


class TestSaveSnapshot:
    @patch("diamond.data.snapshots.download_prices")
    @patch("diamond.data.snapshots.Ledger")
    def test_save_creates_snapshot(self, mock_ledger_cls, mock_dl, snap_dir):
        """save_snapshot creates a snapshot with all required fields."""
        mock_ledger_cls.return_value = _mock_ledger(
            {"RELIANCE.NS": 10, "TCS.NS": 5}, cash=20000.0
        )
        mock_dl.return_value = _mock_prices_df(
            {"RELIANCE.NS": [2500.0], "TCS.NS": [3500.0]}
        )

        result = save_snapshot("test_snap", "gods_plan", notes="test notes")

        assert result["name"] == "test_snap"
        assert result["strategy"] == "gods_plan"
        assert result["notes"] == "test notes"
        assert result["cash"] == 20000.0
        assert "timestamp" in result
        assert "holdings" in result
        assert "prices" in result
        assert "nav" in result
        # NAV = cash + 10*2500 + 5*3500 = 20000 + 25000 + 17500 = 62500
        assert result["nav"] == 62500.0

    @patch("diamond.data.snapshots.download_prices")
    @patch("diamond.data.snapshots.Ledger")
    def test_save_no_holdings_returns_error(self, mock_ledger_cls, mock_dl, snap_dir):
        """Empty holdings returns error dict."""
        mock_ledger_cls.return_value = _mock_ledger({})

        result = save_snapshot("empty_snap", "gods_plan")
        assert "error" in result


class TestLoadSnapshot:
    @patch("diamond.data.snapshots.download_prices")
    @patch("diamond.data.snapshots.Ledger")
    def test_load_existing(self, mock_ledger_cls, mock_dl, snap_dir):
        """Load a previously saved snapshot."""
        mock_ledger_cls.return_value = _mock_ledger({"RELIANCE.NS": 10}, cash=10000.0)
        mock_dl.return_value = _mock_prices_df({"RELIANCE.NS": [2500.0]})

        save_snapshot("my_snap", "gods_plan")
        loaded = load_snapshot("my_snap")

        assert loaded is not None
        assert loaded["name"] == "my_snap"
        assert loaded["holdings"]["RELIANCE.NS"] == 10

    def test_load_nonexistent_returns_none(self, snap_dir):
        """Non-existent snapshot returns None."""
        result = load_snapshot("does_not_exist")
        assert result is None


class TestListSnapshots:
    @patch("diamond.data.snapshots.download_prices")
    @patch("diamond.data.snapshots.Ledger")
    def test_list_returns_summaries(self, mock_ledger_cls, mock_dl, snap_dir):
        """list_snapshots returns summary info."""
        mock_ledger_cls.return_value = _mock_ledger({"RELIANCE.NS": 10}, cash=5000.0)
        mock_dl.return_value = _mock_prices_df({"RELIANCE.NS": [2000.0]})

        save_snapshot("snap_a", "gods_plan", notes="first")
        save_snapshot("snap_b", "gods_plan", notes="second")

        result = list_snapshots()
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"snap_a", "snap_b"}
        # Check summary fields
        for s in result:
            assert "nav" in s
            assert "holdings_count" in s
            assert "timestamp" in s

    def test_list_empty(self, snap_dir):
        result = list_snapshots()
        assert result == []


class TestDeleteSnapshot:
    @patch("diamond.data.snapshots.download_prices")
    @patch("diamond.data.snapshots.Ledger")
    def test_delete_removes_snapshot(self, mock_ledger_cls, mock_dl, snap_dir):
        mock_ledger_cls.return_value = _mock_ledger({"TCS.NS": 5}, cash=1000.0)
        mock_dl.return_value = _mock_prices_df({"TCS.NS": [3000.0]})

        save_snapshot("to_delete", "gods_plan")
        assert delete_snapshot("to_delete") is True
        assert load_snapshot("to_delete") is None

    def test_delete_nonexistent_returns_false(self, snap_dir):
        assert delete_snapshot("nope") is False


class TestDiffSnapshots:
    def test_diff_shows_added_removed_changed(self, snap_dir):
        """diff_snapshots computes added, removed, and changed stocks."""
        snap_data = {
            "snap1": {
                "holdings": {"RELIANCE.NS": 10, "TCS.NS": 5},
                "prices": {"RELIANCE.NS": 2500, "TCS.NS": 3000},
                "nav": 40000,
                "cash": 0,
            },
            "snap2": {
                "holdings": {"RELIANCE.NS": 15, "INFY.NS": 8},
                "prices": {"RELIANCE.NS": 2500, "INFY.NS": 1500},
                "nav": 49500,
                "cash": 0,
            },
        }
        snap_dir.write_text(json.dumps(snap_data, indent=2))

        result = diff_snapshots("snap1", "snap2")

        assert result["from"] == "snap1"
        assert result["to"] == "snap2"
        # TCS removed, INFY added, RELIANCE changed
        removed_tickers = [r["ticker"] for r in result["removed"]]
        added_tickers = [a["ticker"] for a in result["added"]]
        changed_tickers = [c["ticker"] for c in result["changed"]]

        assert "TCS.NS" in removed_tickers
        assert "INFY.NS" in added_tickers
        assert "RELIANCE.NS" in changed_tickers
        assert result["nav_before"] == 40000
        assert result["nav_after"] == 49500

    def test_diff_nonexistent_snapshot_error(self, snap_dir):
        """Non-existent snapshot returns error."""
        # Create one snapshot in file
        snap_data = {
            "exists": {
                "holdings": {"A.NS": 1},
                "prices": {"A.NS": 100},
                "nav": 100,
            }
        }
        snap_dir.write_text(json.dumps(snap_data))

        result = diff_snapshots("exists", "missing")
        assert "error" in result

        result2 = diff_snapshots("missing", "exists")
        assert "error" in result2


class TestDiffWithCurrent:
    @patch("diamond.data.snapshots.download_prices")
    @patch("diamond.data.snapshots.Ledger")
    def test_diff_with_current_portfolio(self, mock_ledger_cls, mock_dl, snap_dir):
        """Compare snapshot to live portfolio."""
        # Save a past snapshot manually
        snap_data = {
            "old_snap": {
                "holdings": {"RELIANCE.NS": 10},
                "prices": {"RELIANCE.NS": 2000},
                "nav": 20000,
                "cash": 0,
            }
        }
        snap_dir.write_text(json.dumps(snap_data))

        # Mock current portfolio
        mock_ledger_cls.return_value = _mock_ledger(
            {"RELIANCE.NS": 15, "TCS.NS": 5}, cash=5000.0
        )
        mock_dl.return_value = _mock_prices_df(
            {"RELIANCE.NS": [2500.0], "TCS.NS": [3000.0]}
        )

        result = diff_with_current("old_snap", "gods_plan")

        assert result["from"] == "old_snap"
        assert result["to"] == "current"
        assert "added" in result
        assert "changed" in result

    def test_diff_with_current_missing_snapshot(self, snap_dir):
        result = diff_with_current("nonexistent", "gods_plan")
        assert "error" in result
