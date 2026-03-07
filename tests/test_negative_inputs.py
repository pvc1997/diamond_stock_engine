"""Tests for malformed and invalid inputs across the Diamond engine.

Validates that the system handles bad data gracefully:
- Malformed tickers
- Invalid capital amounts
- Invalid strategy names
- Empty DataFrames
- NaN/Inf values in price data
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.execution.costs import CostBreakdown, calculate_costs, round_trip_cost_pct


# ---------------------------------------------------------------------------
# Malformed tickers
# ---------------------------------------------------------------------------


class TestMalformedTickers:
    """Tickers without .NS suffix, empty strings, special characters."""

    def test_ledger_accepts_ticker_without_ns_suffix(self, tmp_path: Path):
        """Ledger doesn't validate ticker format — it stores whatever string is given."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade("2024-01-15", "BUY", "RELIANCE", 10, 2500.0, 50.0, "Buy")
        ledger.record_trade(trade)
        assert ledger.get_holdings()["RELIANCE"] == 10

    def test_ledger_accepts_empty_ticker(self, tmp_path: Path):
        """Ledger accepts empty string as ticker — no validation at this layer."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade("2024-01-15", "BUY", "", 10, 100.0, 5.0, "Buy")
        ledger.record_trade(trade)
        assert ledger.get_holdings()[""] == 10

    def test_ledger_accepts_special_characters_in_ticker(self, tmp_path: Path):
        """Tickers with hyphens, ampersands etc. should work (e.g., M&M.NS, BAJAJ-AUTO.NS)."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        for ticker in ["M&M.NS", "BAJAJ-AUTO.NS", "STOCK@#$.NS"]:
            trade = Trade("2024-01-15", "BUY", ticker, 5, 500.0, 10.0, "Buy")
            ledger.record_trade(trade)
        holdings = ledger.get_holdings()
        assert "M&M.NS" in holdings
        assert "BAJAJ-AUTO.NS" in holdings
        assert "STOCK@#$.NS" in holdings

    def test_portfolio_value_missing_ticker_prices(self, tmp_path: Path):
        """If current_prices doesn't include a held ticker, it's valued at 0."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "GHOST.NS", 10, 100.0, 5.0, "Buy"))
        value = ledger.get_portfolio_value({})  # No prices provided
        # Value = cash only, holdings valued at 0
        expected_cash = 100000 - (10 * 100) - 5
        assert value == expected_cash

    def test_avg_price_for_nonexistent_ticker(self, tmp_path: Path):
        """get_avg_price for a ticker not in holdings returns 0."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        assert ledger.get_avg_price("DOESNOTEXIST.NS") == 0.0

    def test_write_off_nonexistent_ticker(self, tmp_path: Path):
        """Writing off a ticker not in holdings returns False."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        assert ledger.write_off("NOSTOCK.NS") is False

    def test_sector_cap_with_unknown_tickers(self):
        """apply_sector_cap should handle tickers where get_sector returns a default."""
        from diamond.strategies.constraints import apply_sector_cap

        tickers = ["UNKNOWN1.NS", "UNKNOWN2.NS", "UNKNOWN3.NS"]
        with patch("diamond.strategies.constraints.get_sector", return_value="Unknown"):
            result = apply_sector_cap(tickers, max_per_sector=2)
        assert len(result) == 2  # Capped at 2 per sector


# ---------------------------------------------------------------------------
# Invalid capital amounts
# ---------------------------------------------------------------------------


class TestInvalidCapitalAmounts:
    """Negative, zero, and very large capital values."""

    def test_calculate_costs_negative_amount(self):
        """Negative amounts should be treated as zero (returns all-zero costs)."""
        result = calculate_costs("BUY", -10000)
        assert result.total == 0

    def test_calculate_costs_very_large_amount(self):
        """Very large amounts should still produce valid costs."""
        result = calculate_costs("BUY", 1_000_000_000)  # 1 billion INR
        assert result.total > 0
        assert result.brokerage == 20.0  # Capped at 20 INR
        assert np.isfinite(result.total)

    def test_round_trip_negative_amount(self):
        """round_trip_cost_pct with negative amount returns 0."""
        assert round_trip_cost_pct(-5000) == 0.0

    def test_baseline_allocate_zero_capital(self):
        """Allocating zero capital should give zero per stock."""
        from diamond.strategies.baseline import BaselineStrategy

        strategy = BaselineStrategy()
        candidates = pd.DataFrame({"Ticker": ["A.NS", "B.NS"]})
        allocation = strategy.allocate(candidates, 0)
        assert all(v == 0 for v in allocation.values())

    def test_baseline_allocate_negative_capital(self):
        """Allocating negative capital produces negative per-stock values (no guard)."""
        from diamond.strategies.baseline import BaselineStrategy

        strategy = BaselineStrategy()
        candidates = pd.DataFrame({"Ticker": ["A.NS", "B.NS"]})
        allocation = strategy.allocate(candidates, -100000)
        # BaselineStrategy does simple division — will produce negative values
        assert all(v < 0 for v in allocation.values())

    def test_ledger_set_negative_cash(self, tmp_path: Path):
        """Ledger allows setting negative cash (can happen if costs exceed balance)."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.set_cash(-500.0)
        assert ledger.get_cash() == -500.0

    def test_ledger_reset_with_zero_capital_falls_back_to_default(self, tmp_path: Path):
        """Resetting with zero capital falls back to config default (0 is falsy)."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # reset: capital = initial_capital or get_config().risk.initial_capital
        # 0 is falsy, so it uses the config default (100000)
        ledger.reset(initial_capital=0)
        assert ledger.get_cash() == 100000  # Falls back to default


# ---------------------------------------------------------------------------
# Invalid strategy names
# ---------------------------------------------------------------------------


class TestInvalidStrategyNames:
    """Strategy names that are unusual or potentially problematic."""

    def test_ledger_with_empty_strategy_name(self, tmp_path: Path):
        """Empty strategy name should still create a valid ledger."""
        ledger = Ledger("", db_path=tmp_path / "empty.db")
        assert ledger.get_cash() == 100000

    def test_ledger_with_special_chars_strategy(self, tmp_path: Path):
        """Strategy name with special characters works since db_path is explicit."""
        ledger = Ledger("test-special_v2", db_path=tmp_path / "special.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy"))
        assert ledger.get_holdings()["TCS.NS"] == 5

    def test_ledger_with_very_long_strategy_name(self, tmp_path: Path):
        """Very long strategy name should work with explicit db_path."""
        name = "a" * 500
        ledger = Ledger(name, db_path=tmp_path / "long.db")
        assert ledger.strategy == name


# ---------------------------------------------------------------------------
# Empty DataFrames
# ---------------------------------------------------------------------------


class TestEmptyDataFrames:
    """Empty DataFrames passed to analysis/strategy functions."""

    def test_baseline_screen_ignores_empty_universe(self):
        """BaselineStrategy.screen() ignores the universe arg, returns Nifty 50."""
        from diamond.strategies.baseline import BaselineStrategy

        strategy = BaselineStrategy()
        result = strategy.screen(pd.DataFrame())
        assert len(result) == 50

    def test_baseline_allocate_empty_ticker_column(self):
        """Empty Ticker column returns empty allocation."""
        from diamond.strategies.baseline import BaselineStrategy

        strategy = BaselineStrategy()
        result = strategy.allocate(pd.DataFrame({"Ticker": []}), 100000)
        assert result == {}

    def test_steady_allocate_empty_df(self):
        """SteadyStrategy.allocate with empty DF returns empty dict."""
        from diamond.strategies.steady import SteadyStrategy

        strategy = SteadyStrategy()
        result = strategy.allocate(pd.DataFrame(), 100000)
        assert result == {}

    def test_gods_plan_allocate_empty_df(self):
        """GodsPlanStrategy.allocate with empty DF returns empty dict."""
        from diamond.strategies.gods_plan import GodsPlanStrategy

        strategy = GodsPlanStrategy()
        result = strategy.allocate(pd.DataFrame(), 500000)
        assert result == {}

    def test_cap_sector_weights_empty_dict(self):
        """cap_sector_weights with empty weights returns empty."""
        from diamond.strategies.constraints import cap_sector_weights

        result = cap_sector_weights({}, max_sector_pct=0.25)
        assert result == {}

    def test_calculate_trades_no_prices(self, tmp_path: Path):
        """_calculate_trades with empty prices dict produces no trades."""
        from diamond.execution.executor import _calculate_trades

        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 50000},
            current_prices={},
            min_trade_value=1000,
        )
        assert trades == []

    def test_calculate_trades_no_allocation(self, tmp_path: Path):
        """_calculate_trades with empty target and no holdings produces no trades."""
        from diamond.execution.executor import _calculate_trades

        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trades = _calculate_trades(
            ledger,
            target_allocation={},
            current_prices={},
            min_trade_value=1000,
        )
        assert trades == []


# ---------------------------------------------------------------------------
# NaN / Inf values in price data
# ---------------------------------------------------------------------------


class TestNanInfPrices:
    """NaN and Inf values in price data."""

    def test_portfolio_value_with_nan_price(self, tmp_path: Path):
        """NaN price produces NaN portfolio value (no guard in code)."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        value = ledger.get_portfolio_value({"RELIANCE.NS": float("nan")})
        # NaN * 10 = NaN, cash + NaN = NaN
        assert np.isnan(value)  # TODO: should handle gracefully (treat NaN as 0)

    def test_portfolio_value_with_inf_price(self, tmp_path: Path):
        """Inf price produces Inf portfolio value (no guard in code)."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))
        value = ledger.get_portfolio_value({"RELIANCE.NS": float("inf")})
        assert np.isinf(value)  # TODO: should handle gracefully

    def test_calculate_costs_nan_amount(self):
        """NaN amount should be treated as <= 0 (returns zero costs)."""
        result = calculate_costs("BUY", float("nan"))
        # NaN <= 0 is False in Python, so it won't hit the early return
        # This means it will produce NaN costs
        assert np.isnan(result.total) or result.total == 0  # TODO: should handle gracefully

    def test_calculate_costs_inf_amount(self):
        """Inf amount produces finite brokerage (capped) but inf other costs."""
        result = calculate_costs("BUY", float("inf"))
        assert result.brokerage == 20.0  # Capped
        assert np.isinf(result.stt)  # 0.1% of inf = inf
        # TODO: should handle gracefully

    def test_calculate_trades_nan_price_raises(self, tmp_path: Path):
        """Tickers with NaN price cause ValueError (NaN passes the guard check).

        The guard `if not price or price <= 0` does not catch NaN because:
        - `not float('nan')` is False (NaN is truthy)
        - `float('nan') <= 0` is False (NaN comparisons return False)
        So int(amount / nan) = int(nan) raises ValueError.
        """
        from diamond.execution.executor import _calculate_trades

        ledger = Ledger("test", db_path=tmp_path / "test.db")
        # TODO: should handle NaN gracefully (skip ticker instead of raising)
        with pytest.raises(ValueError):
            _calculate_trades(
                ledger,
                target_allocation={"RELIANCE.NS": 50000},
                current_prices={"RELIANCE.NS": float("nan")},
                min_trade_value=1000,
            )

    def test_calculate_trades_zero_price_skipped(self, tmp_path: Path):
        """Tickers with zero price are explicitly skipped."""
        from diamond.execution.executor import _calculate_trades

        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 50000},
            current_prices={"RELIANCE.NS": 0},
            min_trade_value=1000,
        )
        assert trades == []

    def test_calculate_trades_negative_price_skipped(self, tmp_path: Path):
        """Tickers with negative price are skipped."""
        from diamond.execution.executor import _calculate_trades

        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trades = _calculate_trades(
            ledger,
            target_allocation={"RELIANCE.NS": 50000},
            current_prices={"RELIANCE.NS": -100},
            min_trade_value=1000,
        )
        assert trades == []

    def test_hurst_exponent_all_nan(self):
        """Hurst exponent with all-NaN prices returns default 0.5."""
        from diamond.analysis.screener import _hurst_exponent

        prices = np.full(200, np.nan)
        result = _hurst_exponent(prices)
        # With all NaN, np.std will return NaN, valid_lags will be empty
        assert 0.0 <= result <= 1.0

    def test_hurst_exponent_constant_prices(self):
        """Hurst exponent with constant prices (zero variance) returns default 0.5."""
        from diamond.analysis.screener import _hurst_exponent

        prices = np.full(200, 100.0)
        result = _hurst_exponent(prices)
        # All diffs are zero, std=0, so no valid lags -> returns 0.5
        assert result == 0.5

    def test_hurst_exponent_too_short(self):
        """Hurst exponent with very short array returns default 0.5."""
        from diamond.analysis.screener import _hurst_exponent

        prices = np.array([100.0, 101.0, 99.0])
        result = _hurst_exponent(prices)
        assert result == 0.5


# ---------------------------------------------------------------------------
# Invalid action types for costs
# ---------------------------------------------------------------------------


class TestInvalidCostActions:
    """Invalid action parameter for calculate_costs."""

    def test_unknown_action_defaults_to_sell_stamp_duty(self):
        """Unknown action type hits the else branch for stamp duty (sell rate)."""
        result = calculate_costs("HOLD", 10000)
        # The code checks `if action == "BUY"` else sell stamp duty
        sell_result = calculate_costs("SELL", 10000)
        assert result.stamp_duty == sell_result.stamp_duty

    def test_empty_string_action(self):
        """Empty string action uses sell stamp duty rate."""
        result = calculate_costs("", 10000)
        assert result.total > 0


# ---------------------------------------------------------------------------
# Invalid trade data in ledger
# ---------------------------------------------------------------------------


class TestInvalidTradeData:
    """Edge cases in trade recording."""

    def test_zero_shares_trade(self, tmp_path: Path):
        """Trading zero shares records the trade but doesn't change holdings."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade("2024-01-15", "BUY", "TCS.NS", 0, 3000.0, 0, "Zero shares")
        ledger.record_trade(trade)
        # Zero delta means no holdings entry created
        # update_holding with delta=0: row doesn't exist, delta=0 is not > 0, so no insert
        assert ledger.get_holdings() == {}

    def test_zero_price_trade(self, tmp_path: Path):
        """Trading at price 0 records trade, adjusts cash by just the cost."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade("2024-01-15", "BUY", "FREE.NS", 10, 0.0, 5.0, "Free shares")
        ledger.record_trade(trade)
        assert ledger.get_holdings()["FREE.NS"] == 10
        # Cash = 100000 - (10 * 0) - 5 = 99995
        assert ledger.get_cash() == 99995.0

    def test_negative_price_trade(self, tmp_path: Path):
        """Negative price trade records and adjusts cash (no guard)."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade("2024-01-15", "BUY", "NEG.NS", 10, -100.0, 0, "Negative price")
        ledger.record_trade(trade)
        assert ledger.get_holdings()["NEG.NS"] == 10
        # Cash = 100000 - (10 * -100) = 100000 + 1000 = 101000
        assert ledger.get_cash() == 101000.0
        # TODO: should validate price >= 0

    def test_invalid_action_in_ledger(self, tmp_path: Path):
        """Invalid action type should be rejected by SQLite CHECK constraint."""
        ledger = Ledger("test", db_path=tmp_path / "test.db")
        trade = Trade("2024-01-15", "HOLD", "TCS.NS", 10, 3000.0, 30.0, "Invalid")
        with pytest.raises(Exception):
            # SQLite CHECK(action IN ('BUY', 'SELL')) should reject this
            ledger.record_trade(trade)
