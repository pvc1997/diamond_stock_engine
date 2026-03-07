"""Tests for portfolio executor logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from diamond.data.ledger import Ledger
from diamond.execution.executor import _calculate_trades


class TestCalculateTrades:
    def test_buy_new_positions(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")

        allocation = {"RELIANCE.NS": 25000, "TCS.NS": 15000}
        prices = {"RELIANCE.NS": 2500.0, "TCS.NS": 3000.0}

        trades = _calculate_trades(ledger, allocation, prices, min_trade_value=1000)

        assert len(trades) == 2
        # All should be BUY
        actions = {t["ticker"]: t["action"] for t in trades}
        assert actions["RELIANCE.NS"] == "BUY"
        assert actions["TCS.NS"] == "BUY"

        # Check share counts (floor division)
        shares = {t["ticker"]: t["shares"] for t in trades}
        assert shares["RELIANCE.NS"] == 10  # 25000/2500
        assert shares["TCS.NS"] == 5        # 15000/3000

    def test_sell_removed_positions(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # Manually add holding
        ledger.update_holding("OLD.NS", 10, 100.0)

        allocation = {}  # Target has no OLD.NS
        prices = {"OLD.NS": 100.0}

        trades = _calculate_trades(ledger, allocation, prices, min_trade_value=100)

        assert len(trades) == 1
        assert trades[0]["action"] == "SELL"
        assert trades[0]["ticker"] == "OLD.NS"
        assert trades[0]["shares"] == 10

    def test_rebalance_adjusts_position(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("INFY.NS", 10, 1500.0)

        # Target wants 20 shares worth
        allocation = {"INFY.NS": 30000}  # 30000/1500 = 20 shares
        prices = {"INFY.NS": 1500.0}

        trades = _calculate_trades(ledger, allocation, prices, min_trade_value=1000)

        assert len(trades) == 1
        assert trades[0]["action"] == "BUY"
        assert trades[0]["shares"] == 10  # 20 - 10 = 10 more

    def test_skips_dust_trades(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("WIPRO.NS", 10, 400.0)

        # Target very close to current - trade value under threshold
        allocation = {"WIPRO.NS": 4200}  # 4200/400 = 10.5 -> 10 shares, delta=0
        prices = {"WIPRO.NS": 400.0}

        trades = _calculate_trades(ledger, allocation, prices, min_trade_value=1000)
        assert len(trades) == 0

    def test_sells_before_buys(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.update_holding("SELL_ME.NS", 10, 100.0)

        allocation = {"BUY_ME.NS": 5000}
        prices = {"SELL_ME.NS": 100.0, "BUY_ME.NS": 500.0}

        trades = _calculate_trades(ledger, allocation, prices, min_trade_value=100)

        assert trades[0]["action"] == "SELL"
        assert trades[1]["action"] == "BUY"
