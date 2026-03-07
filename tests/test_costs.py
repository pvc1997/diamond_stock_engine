"""Tests for Indian market transaction cost model."""

from diamond.execution.costs import (
    CostBreakdown,
    calculate_costs,
    estimate_slippage,
    round_trip_cost_pct,
)


class TestEstimateSlippage:
    def test_zero_amount(self):
        assert estimate_slippage(0) == 0.0

    def test_negative_amount(self):
        assert estimate_slippage(-100) == 0.0

    def test_no_adv_flat_fallback(self):
        """Without ADV, falls back to flat 0.05%."""
        result = estimate_slippage(100_000)
        assert abs(result - 50.0) < 0.01  # 0.05% of 1L

    def test_none_adv_flat_fallback(self):
        result = estimate_slippage(100_000, avg_daily_value=None)
        assert abs(result - 50.0) < 0.01

    def test_zero_adv_flat_fallback(self):
        result = estimate_slippage(100_000, avg_daily_value=0)
        assert abs(result - 50.0) < 0.01

    def test_large_cap_low_slippage(self):
        """RELIANCE-like: 50K trade vs 5B ADV -> very low slippage."""
        result = estimate_slippage(50_000, avg_daily_value=5_000_000_000)
        # participation = 50K/5B = 1e-5, sqrt = 0.00316, * 0.1 = 0.000316 -> 0.0316%
        # Much less than flat 0.05%
        flat = 50_000 * 0.0005
        assert result < flat

    def test_small_cap_high_slippage(self):
        """Illiquid stock: 50K trade vs 200K ADV -> high slippage."""
        result = estimate_slippage(50_000, avg_daily_value=200_000)
        # participation = 0.25, sqrt = 0.5, * 0.1 = 0.05 -> 5%
        # Capped at 2%
        assert result == 50_000 * 0.02  # cap applies

    def test_mid_cap_moderate_slippage(self):
        """Mid-cap: 50K trade vs 50M ADV -> moderate slippage."""
        result = estimate_slippage(50_000, avg_daily_value=50_000_000)
        # participation = 0.001, sqrt = 0.0316, * 0.1 = 0.00316
        expected = 50_000 * 0.00316
        assert abs(result - expected) < 1.0

    def test_slippage_increases_with_trade_size(self):
        """Larger trade -> higher slippage (absolute and as %)."""
        adv = 10_000_000
        small = estimate_slippage(10_000, avg_daily_value=adv)
        large = estimate_slippage(1_000_000, avg_daily_value=adv)
        assert large > small
        # Also check % increases
        small_pct = small / 10_000
        large_pct = large / 1_000_000
        assert large_pct > small_pct

    def test_slippage_capped_at_2_pct(self):
        """Even for extremely illiquid stocks, slippage caps at 2%."""
        result = estimate_slippage(100_000, avg_daily_value=100)
        assert result == 100_000 * 0.02

    def test_slippage_floored_at_0_02_pct(self):
        """Even for tiny trades in liquid stocks, minimum 0.02%."""
        result = estimate_slippage(100, avg_daily_value=100_000_000_000)
        assert result == 100 * 0.0002


class TestCalculateCosts:
    def test_zero_amount(self):
        result = calculate_costs("BUY", 0)
        assert result.total == 0

    def test_buy_costs_positive(self):
        result = calculate_costs("BUY", 10000)
        assert result.total > 0
        assert result.brokerage > 0
        assert result.gst > 0
        assert result.stt > 0

    def test_sell_costs_positive(self):
        result = calculate_costs("SELL", 10000)
        assert result.total > 0

    def test_brokerage_capped_at_20(self):
        # For large trades, brokerage should cap at 20 INR
        result = calculate_costs("BUY", 1_000_000)
        assert result.brokerage == 20.0

    def test_brokerage_uncapped_for_small_trades(self):
        # For 10,000 INR: 0.05% = 5 INR (under cap)
        result = calculate_costs("BUY", 10000)
        assert result.brokerage == 5.0

    def test_gst_is_18_pct_of_brokerage(self):
        result = calculate_costs("BUY", 10000)
        assert abs(result.gst - result.brokerage * 0.18) < 0.01

    def test_stamp_duty_higher_for_buy(self):
        buy = calculate_costs("BUY", 100000)
        sell = calculate_costs("SELL", 100000)
        assert buy.stamp_duty > sell.stamp_duty

    def test_returns_cost_breakdown_type(self):
        result = calculate_costs("BUY", 50000)
        assert isinstance(result, CostBreakdown)

    def test_total_is_sum_of_components(self):
        result = calculate_costs("BUY", 25000)
        component_sum = (
            result.brokerage + result.gst + result.stt +
            result.exchange_fees + result.sebi_charges +
            result.stamp_duty + result.slippage
        )
        assert abs(result.total - component_sum) < 0.02  # rounding tolerance

    def test_cost_breakdown_is_frozen(self):
        result = calculate_costs("BUY", 10000)
        try:
            result.total = 999  # type: ignore
            assert False, "Should not allow mutation"
        except AttributeError:
            pass

    def test_backward_compat_no_adv(self):
        """Calling without avg_daily_value works identically to old flat model."""
        result = calculate_costs("BUY", 100_000)
        assert result.slippage == 50.0  # flat 0.05%

    def test_with_adv_changes_slippage(self):
        """Providing ADV changes the slippage component."""
        flat = calculate_costs("BUY", 100_000)
        liquid = calculate_costs("BUY", 100_000, avg_daily_value=10_000_000_000)
        illiquid = calculate_costs("BUY", 100_000, avg_daily_value=500_000)

        # Liquid stock: less slippage than flat
        assert liquid.slippage < flat.slippage
        # Illiquid stock: more slippage than flat
        assert illiquid.slippage > flat.slippage

    def test_illiquid_stock_higher_total(self):
        """Illiquid stock has higher total cost."""
        liquid = calculate_costs("BUY", 100_000, avg_daily_value=5_000_000_000)
        illiquid = calculate_costs("BUY", 100_000, avg_daily_value=300_000)
        assert illiquid.total > liquid.total


class TestRoundTripCost:
    def test_round_trip_positive(self):
        pct = round_trip_cost_pct(100000)
        assert pct > 0

    def test_round_trip_typical_range(self):
        # Round trip for 1L should be roughly 0.3-0.5%
        pct = round_trip_cost_pct(100000)
        assert 0.2 < pct < 1.0

    def test_round_trip_zero_amount(self):
        assert round_trip_cost_pct(0) == 0.0
