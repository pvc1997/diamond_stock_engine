"""Tests for live execution engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from diamond.data.ledger import Ledger
from diamond.execution.live import (
    _compute_trade_plan,
    reconcile_with_kite,
)
from diamond.execution.kite import KiteClient


class TestComputeTradePlan:
    def test_new_portfolio_all_buys(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        target = {"RELIANCE.NS": 25000, "TCS.NS": 17000}
        prices = {"RELIANCE.NS": 2500.0, "TCS.NS": 3400.0}

        sells, buys = _compute_trade_plan(ledger, target, prices, 1000)

        assert len(sells) == 0
        assert len(buys) == 2
        # Check fields exist
        for b in buys:
            assert "ticker" in b
            assert "kite_symbol" in b
            assert "shares" in b
            assert "price" in b
            assert "value" in b
            assert "est_cost" in b

    def test_full_exit_all_sells(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("RELIANCE.NS", 10, 2500)
        ledger.update_holding("TCS.NS", 5, 3400)

        target = {}  # Exit all
        prices = {"RELIANCE.NS": 2500.0, "TCS.NS": 3400.0}

        sells, buys = _compute_trade_plan(ledger, target, prices, 1000)

        assert len(sells) == 2
        assert len(buys) == 0
        tickers = {s["ticker"] for s in sells}
        assert "RELIANCE.NS" in tickers
        assert "TCS.NS" in tickers

    def test_rebalance_mix(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("RELIANCE.NS", 20, 2500)  # Too many
        ledger.update_holding("OLD.NS", 10, 100)  # To be removed

        target = {"RELIANCE.NS": 25000, "NEW.NS": 10000}
        prices = {"RELIANCE.NS": 2500.0, "OLD.NS": 100.0, "NEW.NS": 1000.0}

        sells, buys = _compute_trade_plan(ledger, target, prices, 100)

        sell_tickers = {s["ticker"] for s in sells}
        buy_tickers = {b["ticker"] for b in buys}

        assert "OLD.NS" in sell_tickers  # Removed position
        assert "RELIANCE.NS" in sell_tickers  # Reduced from 20 to 10
        assert "NEW.NS" in buy_tickers  # New position

    def test_kite_symbols_correct(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        target = {"M&M.NS": 20000}
        prices = {"M&M.NS": 2000.0}

        sells, buys = _compute_trade_plan(ledger, target, prices, 1000)

        assert buys[0]["kite_symbol"] == "M&M"

    def test_skips_dust_trades(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("WIPRO.NS", 10, 400)

        target = {"WIPRO.NS": 4200}  # 10.5 shares -> 10, delta=0
        prices = {"WIPRO.NS": 400.0}

        sells, buys = _compute_trade_plan(ledger, target, prices, 1000)

        assert len(sells) == 0
        assert len(buys) == 0

    def test_sells_sorted_by_value_desc(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("SMALL.NS", 5, 100)
        ledger.update_holding("BIG.NS", 10, 5000)

        target = {}
        prices = {"SMALL.NS": 100.0, "BIG.NS": 5000.0}

        sells, buys = _compute_trade_plan(ledger, target, prices, 100)

        assert sells[0]["ticker"] == "BIG.NS"  # Biggest first


class TestReconcile:
    def test_in_sync(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.get_holdings_mapped.return_value = {
            "RELIANCE.NS": {"shares": 10, "avg_price": 2500},
        }

        with patch("diamond.execution.live.Ledger") as MockLedger:
            mock_ledger = MagicMock()
            mock_ledger.get_holdings.return_value = {"RELIANCE.NS": 10}
            MockLedger.return_value = mock_ledger

            result = reconcile_with_kite("test", mock_client)

        assert result["in_sync"] is True
        assert len(result["matches"]) == 1
        assert len(result["discrepancies"]) == 0

    def test_quantity_discrepancy(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.get_holdings_mapped.return_value = {
            "RELIANCE.NS": {"shares": 15, "avg_price": 2500},
        }

        with patch("diamond.execution.live.Ledger") as MockLedger:
            mock_ledger = MagicMock()
            mock_ledger.get_holdings.return_value = {"RELIANCE.NS": 10}
            MockLedger.return_value = mock_ledger

            result = reconcile_with_kite("test", mock_client)

        assert result["in_sync"] is False
        assert len(result["discrepancies"]) == 1
        assert result["discrepancies"][0]["delta"] == 5

    def test_kite_only_holdings(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.get_holdings_mapped.return_value = {
            "RELIANCE.NS": {"shares": 10, "avg_price": 2500},
            "TCS.NS": {"shares": 5, "avg_price": 3400},
        }

        with patch("diamond.execution.live.Ledger") as MockLedger:
            mock_ledger = MagicMock()
            mock_ledger.get_holdings.return_value = {"RELIANCE.NS": 10}
            MockLedger.return_value = mock_ledger

            result = reconcile_with_kite("test", mock_client)

        assert result["in_sync"] is False
        assert len(result["kite_only"]) == 1
        assert result["kite_only"][0]["ticker"] == "TCS.NS"

    def test_ledger_only_holdings(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.get_holdings_mapped.return_value = {
            "RELIANCE.NS": {"shares": 10, "avg_price": 2500},
        }

        with patch("diamond.execution.live.Ledger") as MockLedger:
            mock_ledger = MagicMock()
            mock_ledger.get_holdings.return_value = {
                "RELIANCE.NS": 10,
                "OLD.NS": 5,
            }
            MockLedger.return_value = mock_ledger

            result = reconcile_with_kite("test", mock_client)

        assert result["in_sync"] is False
        assert len(result["ledger_only"]) == 1

    def test_requires_auth(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = False

        from diamond.exceptions import AuthenticationError
        with pytest.raises(AuthenticationError):
            reconcile_with_kite("test", mock_client)

    def test_empty_both_sides(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.get_holdings_mapped.return_value = {}

        with patch("diamond.execution.live.Ledger") as MockLedger:
            mock_ledger = MagicMock()
            mock_ledger.get_holdings.return_value = {}
            MockLedger.return_value = mock_ledger

            result = reconcile_with_kite("test", mock_client)

        assert result["in_sync"] is True
