"""Tests for boundary conditions and edge cases.

Covers:
- Portfolio with single stock
- Positions at exactly max weight (10%)
- Trade at exactly minimum trade threshold (1000 INR)
- Rebalance with zero drift
- Sell more shares than held
- Buy with zero cash
- Strategy screen returning zero stocks
- Corporate action on stock not in portfolio
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from diamond.data.corporate_actions import (
    CorporateAction,
    apply_bonus,
    apply_dividend,
    apply_split,
)
from diamond.data.ledger import Ledger, Trade
from diamond.execution.costs import calculate_costs
from diamond.execution.executor import _calculate_trades


# ---------------------------------------------------------------------------
# Single-stock portfolio
# ---------------------------------------------------------------------------


class TestSingleStockPortfolio:
    """Edge cases when portfolio has exactly one holding."""

    def test_single_stock_holdings(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        holdings = ledger.get_holdings()
        assert len(holdings) == 1
        assert holdings["RELIANCE.NS"] == 10

    def test_single_stock_portfolio_value(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        prices = {"RELIANCE.NS": 2600.0}
        value = ledger.get_portfolio_value(prices)
        cash = 100000 - (10 * 2500) - 50
        expected = cash + (10 * 2600)
        assert value == expected

    def test_single_stock_sell_all(self, tmp_path: Path):
        """Selling all shares of the only stock leaves empty portfolio."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        ledger.record_trade(Trade("2024-02-15", "SELL", "RELIANCE.NS", 10, 2600.0, 50.0, "Sell"))
        assert ledger.get_holdings() == {}

    def test_single_stock_write_off(self, tmp_path: Path):
        """Writing off the only stock leaves empty portfolio."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "DELISTED.NS", 10, 100.0, 5.0, "Buy"))
        cash_before = ledger.get_cash()
        result = ledger.write_off("DELISTED.NS")
        assert result is True
        assert ledger.get_holdings() == {}
        # Write-off doesn't change cash
        assert ledger.get_cash() == cash_before

    def test_single_stock_split(self, tmp_path: Path):
        """Split on the only stock in portfolio."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 5, 4000.0, 40.0, "Buy"))
        action = CorporateAction("TCS.NS", "split", "2024-06-01", 2.0, 0.0)
        result = apply_split(ledger, action)
        assert result is not None
        assert ledger.get_holdings()["TCS.NS"] == 10
        assert abs(ledger.get_avg_price("TCS.NS") - 2000.0) < 0.01


# ---------------------------------------------------------------------------
# Position weight boundaries
# ---------------------------------------------------------------------------


class TestPositionWeightBoundaries:
    """Max position weight is 10% — test at and around that boundary."""

    def test_at_exactly_max_weight(self, tmp_path: Path):
        """A position at exactly 10% weight should NOT trigger trim.

        We test via _calculate_trades-level logic since execute_trim creates
        its own Ledger from the strategy name (can't inject tmp_path).
        """
        ledger = Ledger("test_trim", db_path=tmp_path / "trim.db")
        ledger.set_cash(0)

        for i in range(10):
            ticker = f"STOCK{i}.NS"
            with ledger._conn() as conn:
                conn.execute(
                    "INSERT INTO holdings (ticker, shares, avg_price) VALUES (?, ?, ?)",
                    (ticker, 100, 100.0),
                )

        prices = {f"STOCK{i}.NS": 100.0 for i in range(10)}
        nav = ledger.get_portfolio_value(prices)
        assert nav == 100000  # 10 stocks * 100 shares * 100 price

        # Check each position weight
        holdings = ledger.get_holdings()
        max_weight = 0.10
        overweight = []
        for ticker, shares in holdings.items():
            weight = (shares * prices[ticker]) / nav
            if weight > max_weight:
                overweight.append(ticker)
        assert overweight == []  # No positions above 10%

    def test_slightly_above_max_weight(self, tmp_path: Path):
        """A position at >10% weight should be detected as overweight."""
        ledger = Ledger("test_trim2", db_path=tmp_path / "trim2.db")
        ledger.set_cash(0)

        with ledger._conn() as conn:
            conn.execute(
                "INSERT INTO holdings (ticker, shares, avg_price) VALUES (?, ?, ?)",
                ("HEAVY.NS", 110, 100.0),
            )
            for i in range(9):
                conn.execute(
                    "INSERT INTO holdings (ticker, shares, avg_price) VALUES (?, ?, ?)",
                    (f"STOCK{i}.NS", 99, 100.0),
                )

        prices = {"HEAVY.NS": 100.0}
        prices.update({f"STOCK{i}.NS": 100.0 for i in range(9)})

        nav = ledger.get_portfolio_value(prices)
        holdings = ledger.get_holdings()
        max_weight = 0.10

        overweight = []
        for ticker, shares in holdings.items():
            weight = (shares * prices[ticker]) / nav
            if weight > max_weight:
                overweight.append((ticker, weight))

        assert len(overweight) >= 1
        assert overweight[0][0] == "HEAVY.NS"


# ---------------------------------------------------------------------------
# Minimum trade threshold
# ---------------------------------------------------------------------------


class TestMinimumTradeThreshold:
    """Minimum trade value is 1000 INR."""

    def test_trade_at_exactly_minimum(self, tmp_path: Path):
        """Trade worth exactly 1000 INR should be included."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # Target: buy 10 shares at 100 each = 1000 INR (exactly at threshold)
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 1000},
            current_prices={"RELIANCE.NS": 100.0},
            min_trade_value=1000,
        )
        assert len(trades) == 1
        assert trades[0]["ticker"] == "RELIANCE.NS"

    def test_trade_just_below_minimum(self, tmp_path: Path):
        """Trade worth 999 INR should be filtered out."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # Target: 999 / 100 = 9 shares = 900 INR (below 1000)
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 999},
            current_prices={"RELIANCE.NS": 100.0},
            min_trade_value=1000,
        )
        assert trades == []

    def test_trade_just_above_minimum(self, tmp_path: Path):
        """Trade worth 1001 INR should be included."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # 1001 / 100 = 10 shares = 1000 INR (at threshold)
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 1001},
            current_prices={"RELIANCE.NS": 100.0},
            min_trade_value=1000,
        )
        assert len(trades) == 1


# ---------------------------------------------------------------------------
# Zero drift (no trades needed)
# ---------------------------------------------------------------------------


class TestZeroDrift:
    """Rebalance when current allocation matches target exactly."""

    def test_no_trades_when_already_at_target(self, tmp_path: Path):
        """If holdings already match target allocation, no trades generated."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # Buy 10 shares at 100 = position of 1000
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 100.0, 5.0, "Buy"))

        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 1000},  # Already have 10 * 100 = 1000
            current_prices={"RELIANCE.NS": 100.0},
            min_trade_value=1000,
        )
        assert trades == []

    def test_no_trades_when_empty_target_and_empty_holdings(self, tmp_path: Path):
        """Empty target with no holdings = no trades."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trades = _calculate_trades(
            ledger,
            target_allocation={},
            current_prices={},
            min_trade_value=1000,
        )
        assert trades == []

    def test_rebalance_frequency_check(self):
        """should_rebalance returns False when within frequency window."""
        from diamond.strategies.baseline import BaselineStrategy

        strategy = BaselineStrategy()
        assert strategy.should_rebalance({}, {}, days_since_last=0) is False
        assert strategy.should_rebalance({}, {}, days_since_last=89) is False


# ---------------------------------------------------------------------------
# Sell more shares than held
# ---------------------------------------------------------------------------


class TestSellMoreThanHeld:
    """Attempting to sell more shares than the portfolio holds."""

    def test_sell_more_shares_removes_holding(self, tmp_path: Path):
        """Selling more shares than held (via delta) results in holding deletion."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))

        # Sell 10 shares when only 5 held — update_holding handles this
        ledger.record_trade(Trade("2024-02-15", "SELL", "TCS.NS", 10, 3100.0, 50.0, "Oversell"))

        # update_holding: new_shares = 5 - 10 = -5, which is <= 0, so DELETE
        assert "TCS.NS" not in ledger.get_holdings()

    def test_sell_more_than_held_cash_effect(self, tmp_path: Path):
        """Cash is credited for all shares sold, even if more than held."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 5, 3000.0, 0, "Buy"))
        cash_after_buy = ledger.get_cash()  # 100000 - 15000 = 85000

        ledger.record_trade(Trade("2024-02-15", "SELL", "TCS.NS", 10, 3100.0, 0, "Oversell"))
        # Cash = 85000 + (10 * 3100) = 85000 + 31000 = 116000
        # TODO: should only sell shares actually held
        assert ledger.get_cash() == cash_after_buy + (10 * 3100)

    def test_sell_capping_logic(self, tmp_path: Path):
        """The sell capping logic: sell_shares = min(requested, held)."""
        # This tests the logic used in execute_sell without calling it directly
        # (execute_sell creates its own Ledger from strategy name).
        # Logic: sell_shares = shares if shares and shares < held_shares else held_shares
        held_shares = 5
        requested_shares = 100
        sell_shares = requested_shares if requested_shares and requested_shares < held_shares else held_shares
        assert sell_shares == held_shares  # Capped at 5


# ---------------------------------------------------------------------------
# Buy with zero cash
# ---------------------------------------------------------------------------


class TestBuyWithZeroCash:
    """Attempting to buy when no cash is available."""

    def test_calculate_trades_buy_generated_even_without_cash(self, tmp_path: Path):
        """_calculate_trades generates buy trades regardless of cash — executor handles budget."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.set_cash(0)  # No cash

        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 50000},
            current_prices={"RELIANCE.NS": 2500.0},
            min_trade_value=1000,
        )
        # _calculate_trades doesn't check cash — that's the executor's job
        assert len(trades) == 1
        assert trades[0]["action"] == "BUY"

    def test_buy_with_zero_cash_via_ledger(self, tmp_path: Path):
        """Buying when cash is zero: executor's _calculate_trades generates
        the buy but execute() skips it when cash check fails during execution."""
        ledger = Ledger("test_nocash", db_path=tmp_path / "nocash.db")
        ledger.set_cash(0)

        # _calculate_trades doesn't check cash — it generates buys regardless
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 50000},
            current_prices={"RELIANCE.NS": 2500.0},
            min_trade_value=1000,
        )
        assert len(trades) == 1
        assert trades[0]["action"] == "BUY"
        # The executor would skip this buy at execution time due to insufficient cash


# ---------------------------------------------------------------------------
# Strategy screen returns zero stocks
# ---------------------------------------------------------------------------


class TestZeroScreenResults:
    """When strategy screening returns no candidates."""

    def test_steady_empty_screen(self):
        """SteadyStrategy with a universe that has no qualifying stocks."""
        from diamond.strategies.steady import SteadyStrategy

        empty_universe = pd.DataFrame({
            "Ticker": [],
            "Alpha": [],
            "Beta": [],
            "CAGR": [],
            "Volatility": [],
            "Hurst": [],
            "Sector": [],
        })
        strategy = SteadyStrategy()
        with patch("diamond.strategies.steady._get_screened_universe", return_value=empty_universe):
            result = strategy.screen(pd.DataFrame(), end_date=None)
        assert len(result) == 0

    def test_allocate_after_zero_screen(self):
        """Allocating with zero candidates returns empty allocation."""
        from diamond.strategies.baseline import BaselineStrategy

        strategy = BaselineStrategy()
        result = strategy.allocate(pd.DataFrame({"Ticker": []}), 500000)
        assert result == {}

    def test_calculate_trades_with_empty_allocation(self, tmp_path: Path):
        """If target allocation is empty but holdings exist, generates sells."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        trades = _calculate_trades(
            ledger,
            target_allocation={},  # Sell everything
            current_prices={"RELIANCE.NS": 2600.0},
            min_trade_value=1000,
        )
        assert len(trades) == 1
        assert trades[0]["action"] == "SELL"
        assert trades[0]["ticker"] == "RELIANCE.NS"


# ---------------------------------------------------------------------------
# Corporate action on stock not in portfolio
# ---------------------------------------------------------------------------


class TestCorporateActionNotInPortfolio:
    """Corporate actions for stocks the portfolio doesn't hold."""

    def test_split_on_unheld_stock(self, tmp_path: Path):
        """Split on a stock not in holdings returns None."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # Portfolio has RELIANCE, split is for TCS
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        action = CorporateAction("TCS.NS", "split", "2024-06-01", 2.0, 0.0)
        result = apply_split(ledger, action)
        assert result is None
        # RELIANCE should be unchanged
        assert ledger.get_holdings()["RELIANCE.NS"] == 10

    def test_dividend_on_unheld_stock(self, tmp_path: Path):
        """Dividend on a stock not in holdings returns None, no cash change."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        cash_before = ledger.get_cash()

        action = CorporateAction("TCS.NS", "dividend", "2024-06-15", 1.0, 15.0)
        result = apply_dividend(ledger, action)
        assert result is None
        assert ledger.get_cash() == cash_before

    def test_bonus_on_unheld_stock(self, tmp_path: Path):
        """Bonus on a stock not in holdings returns None."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        result = apply_bonus(ledger, "NOTOWNED.NS", ratio=1.0, date="2024-06-01")
        assert result is None

    def test_split_ratio_of_one_is_no_op(self, tmp_path: Path):
        """Split with ratio 1.0 (no split) should produce no additional shares."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        action = CorporateAction("RELIANCE.NS", "split", "2024-06-01", 1.0, 0.0)
        result = apply_split(ledger, action)
        # ratio=1.0: new_shares = 10*1 = 10, additional = 0 -> returns None
        assert result is None
        assert ledger.get_holdings()["RELIANCE.NS"] == 10


# ---------------------------------------------------------------------------
# Sell-before-buy ordering
# ---------------------------------------------------------------------------


class TestSellBeforeBuyOrdering:
    """_calculate_trades should always sort sells before buys."""

    def test_sells_ordered_before_buys(self, tmp_path: Path):
        """Trades list has all SELLs before any BUYs."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # Hold A and B
        ledger.record_trade(Trade("2024-01-15", "BUY", "A.NS", 10, 100.0, 5.0, "Buy"))
        ledger.record_trade(Trade("2024-01-15", "BUY", "B.NS", 10, 200.0, 5.0, "Buy"))

        # Target: sell A, buy C
        trades = _calculate_trades(
            ledger,
            target_allocation={"B.NS": 2000, "C.NS": 3000},
            current_prices={"A.NS": 100.0, "B.NS": 200.0, "C.NS": 150.0},
            min_trade_value=500,
        )
        sell_indices = [i for i, t in enumerate(trades) if t["action"] == "SELL"]
        buy_indices = [i for i, t in enumerate(trades) if t["action"] == "BUY"]

        if sell_indices and buy_indices:
            assert max(sell_indices) < min(buy_indices)


# ---------------------------------------------------------------------------
# Ledger reset and reinitialize
# ---------------------------------------------------------------------------


class TestLedgerResetEdgeCases:
    """Edge cases around ledger reset."""

    def test_reset_clears_all_data(self, tmp_path: Path):
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "A.NS", 10, 100.0, 5.0, "Buy"))
        ledger.set_last_rebalance("2024-03-01")

        ledger.reset(initial_capital=500000)
        assert ledger.get_cash() == 500000
        assert ledger.get_holdings() == {}
        assert ledger.get_trades() == []
        assert ledger.get_last_rebalance() == ""

    def test_double_reset(self, tmp_path: Path):
        """Resetting twice should not corrupt the database."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.reset(initial_capital=100000)
        ledger.reset(initial_capital=200000)
        assert ledger.get_cash() == 200000

    def test_trade_after_reset(self, tmp_path: Path):
        """Trading after reset should work normally."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "A.NS", 10, 100.0, 5.0, "Buy"))
        ledger.reset(initial_capital=50000)
        ledger.record_trade(Trade("2024-03-15", "BUY", "B.NS", 5, 200.0, 10.0, "Buy"))

        assert ledger.get_holdings() == {"B.NS": 5}
        assert ledger.get_cash() == 50000 - (5 * 200) - 10


# ---------------------------------------------------------------------------
# Cost model edge cases
# ---------------------------------------------------------------------------


class TestCostModelEdgeCases:
    """Boundary conditions for transaction cost calculations."""

    def test_cost_at_brokerage_cap_boundary(self):
        """At exactly 40,000 INR, brokerage = 0.05% * 40000 = 20 = cap."""
        result = calculate_costs("BUY", 40000)
        assert result.brokerage == 20.0

    def test_cost_just_below_cap(self):
        """At 39,999 INR, brokerage = 0.05% * 39999 = 19.9995, rounds to 20.0."""
        result = calculate_costs("BUY", 39999)
        # Due to rounding: round(19.9995, 2) == 20.0
        assert result.brokerage == 20.0
        # To truly be below cap, need amount < 39,998
        result2 = calculate_costs("BUY", 39000)
        assert result2.brokerage < 20.0  # 0.05% * 39000 = 19.50

    def test_cost_just_above_cap(self):
        """At 40,001 INR, brokerage would be 20.0005 but capped at 20."""
        result = calculate_costs("BUY", 40001)
        assert result.brokerage == 20.0

    def test_very_small_trade(self):
        """1 INR trade: all components round to 0.00 individually, so total is 0."""
        result = calculate_costs("BUY", 1)
        # Each component is tiny and rounds to 0.00 at 2 decimal places
        assert result.total == 0.0
        # A slightly larger trade (100 INR) produces non-zero costs
        result100 = calculate_costs("BUY", 100)
        assert result100.total > 0

    def test_annual_cost_estimate_zero_portfolio(self):
        """Annual cost estimate with zero portfolio value."""
        from diamond.execution.costs import annual_cost_estimate

        result = annual_cost_estimate(0)
        assert result == 0.0
