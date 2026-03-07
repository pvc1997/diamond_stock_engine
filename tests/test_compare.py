"""Tests for portfolio comparison and what-if simulation."""

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.analysis.compare import build_snapshot, compare_strategies, simulate_whatif


@pytest.fixture
def strategy_ledger(tmp_path):
    """Create a ledger with some trades."""
    ledger = Ledger("test_compare", db_path=tmp_path / "compare.db")
    ledger.reset(initial_capital=500000)

    ledger.record_trade(Trade("2025-06-01", "BUY", "RELIANCE.NS", 20, 2500, 50, "Buy"))
    ledger.record_trade(Trade("2025-06-01", "BUY", "TCS.NS", 10, 3500, 35, "Buy"))
    ledger.record_trade(Trade("2025-06-01", "BUY", "HDFCBANK.NS", 30, 1600, 48, "Buy"))
    ledger.set_last_rebalance("2025-06-01")

    return ledger


class TestBuildSnapshot:
    @patch("diamond.analysis.compare._fetch_prices")
    def test_snapshot_with_holdings(self, mock_prices, strategy_ledger):
        mock_prices.return_value = {
            "RELIANCE.NS": 2600,
            "TCS.NS": 3600,
            "HDFCBANK.NS": 1650,
        }

        # Patch Ledger to use our test ledger
        with patch("diamond.analysis.compare.Ledger") as MockLedger:
            MockLedger.return_value = strategy_ledger
            snapshot = build_snapshot("test_compare", include_risk=False)

        assert snapshot.holdings_count == 3
        assert snapshot.nav > 0
        assert snapshot.return_pct != 0 or snapshot.nav > 0
        assert len(snapshot.top_holdings) <= 5

    @patch("diamond.analysis.compare.Ledger")
    def test_snapshot_empty_strategy(self, MockLedger):
        mock_ledger = MagicMock()
        mock_ledger.get_holdings.return_value = {}
        MockLedger.return_value = mock_ledger

        with patch("diamond.analysis.compare.get_config") as mock_cfg:
            mock_cfg.return_value.ledger_dir = "/tmp/nonexistent"
            from pathlib import Path
            mock_cfg.return_value.ledger_dir = Path("/tmp/nonexistent_dir")
            snapshot = build_snapshot("empty", include_risk=False)

        assert snapshot.mode == "none"
        assert snapshot.nav == 0


class TestCompare:
    @patch("diamond.analysis.compare.build_snapshot")
    def test_compare_two(self, mock_build):
        mock_build.side_effect = [
            MagicMock(name="gods_plan", mode="paper", nav=500000, return_pct=5.0,
                     holdings_count=15, cash=20000, total_fees=500,
                     top_holdings=[], sector_exposure={}, beta=1.1,
                     volatility=18.0, max_drawdown=5.0, last_rebalance="2025-06-01",
                     initial_capital=500000),
            MagicMock(name="steady", mode="paper", nav=480000, return_pct=3.0,
                     holdings_count=18, cash=30000, total_fees=400,
                     top_holdings=[], sector_exposure={}, beta=0.8,
                     volatility=12.0, max_drawdown=3.0, last_rebalance="2025-06-01",
                     initial_capital=480000),
        ]
        snapshots = compare_strategies(["gods_plan", "steady"])
        assert len(snapshots) == 2


class TestWhatIf:
    @patch("diamond.analysis.compare._fetch_prices")
    def test_whatif_add_remove(self, mock_prices, strategy_ledger):
        mock_prices.return_value = {
            "RELIANCE.NS": 2600,
            "TCS.NS": 3600,
            "HDFCBANK.NS": 1650,
            "INFY.NS": 1500,
        }

        with patch("diamond.analysis.compare.Ledger") as MockLedger:
            MockLedger.return_value = strategy_ledger
            result = simulate_whatif("test_compare", add_tickers=["INFY.NS"], remove_tickers=["TCS.NS"])

        assert result.before["holdings_count"] == 3
        assert result.after["holdings_count"] == 3  # removed 1, added 1
        # Cash should change (sold TCS, bought INFY)
        assert result.delta["holdings_count"] == 0

    @patch("diamond.analysis.compare._fetch_prices")
    def test_whatif_normalizes_tickers(self, mock_prices, strategy_ledger):
        mock_prices.return_value = {
            "RELIANCE.NS": 2600,
            "TCS.NS": 3600,
            "HDFCBANK.NS": 1650,
            "SBIN.NS": 800,
        }

        with patch("diamond.analysis.compare.Ledger") as MockLedger:
            MockLedger.return_value = strategy_ledger
            result = simulate_whatif("test_compare", add_tickers=["SBIN"], remove_tickers=[])

        # SBIN should be normalized to SBIN.NS
        assert result.after["holdings_count"] == 4

    @patch("diamond.analysis.compare._fetch_prices")
    def test_whatif_no_changes(self, mock_prices, strategy_ledger):
        mock_prices.return_value = {
            "RELIANCE.NS": 2600,
            "TCS.NS": 3600,
            "HDFCBANK.NS": 1650,
        }

        with patch("diamond.analysis.compare.Ledger") as MockLedger:
            MockLedger.return_value = strategy_ledger
            result = simulate_whatif("test_compare", add_tickers=[], remove_tickers=[])

        assert result.delta["holdings_count"] == 0
        assert result.delta["nav"] == 0
