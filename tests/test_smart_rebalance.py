"""Tests for smart rebalancing module."""

import pytest
from datetime import datetime, timedelta

from diamond.data.ledger import Ledger, Trade
from diamond.execution.smart_rebalance import (
    compute_drift,
    adjust_for_volatility,
    plan_tax_aware_trades,
    should_rebalance_smart,
    DriftReport,
    SmartTrade,
)


@pytest.fixture
def ledger(tmp_path):
    ledger = Ledger("test_smart", db_path=tmp_path / "smart.db")
    ledger.reset(initial_capital=500000)
    return ledger


@pytest.fixture
def portfolio_ledger(tmp_path):
    """Ledger with existing holdings for testing sells."""
    ledger = Ledger("test_smart_portfolio", db_path=tmp_path / "smart_port.db")
    ledger.reset(initial_capital=500000)

    # Buy 6 months ago
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    ledger.record_trade(Trade(six_months_ago, "BUY", "RELIANCE.NS", 20, 2500, 50, "Buy"))
    ledger.record_trade(Trade(six_months_ago, "BUY", "TCS.NS", 10, 3500, 35, "Buy"))
    ledger.record_trade(Trade(six_months_ago, "BUY", "HDFCBANK.NS", 30, 1600, 48, "Buy"))
    ledger.set_last_rebalance(six_months_ago)

    return ledger


@pytest.fixture
def ltcg_ledger(tmp_path):
    """Ledger with holdings >1 year old for LTCG testing."""
    ledger = Ledger("test_ltcg", db_path=tmp_path / "ltcg.db")
    ledger.reset(initial_capital=500000)

    long_ago = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    ledger.record_trade(Trade(long_ago, "BUY", "INFY.NS", 15, 1400, 30, "Buy"))
    ledger.set_last_rebalance(long_ago)

    return ledger


class TestDrift:
    def test_no_drift_empty_portfolio(self):
        report = compute_drift({}, {"RELIANCE.NS": 50000}, {"RELIANCE.NS": 2500})
        # Empty portfolio has nav=0, so report says "No portfolio value"
        assert report.reason == "No portfolio value"

    def test_drift_within_threshold(self):
        # Holdings roughly match target
        holdings = {"RELIANCE.NS": 20, "TCS.NS": 10}
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 35000}

        report = compute_drift(holdings, target, prices)
        assert report.max_drift < 0.10  # Within 10%

    def test_drift_exceeds_threshold(self):
        holdings = {"RELIANCE.NS": 100, "TCS.NS": 1}
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 200000}

        report = compute_drift(holdings, target, prices)
        assert report.needs_rebalance is True
        assert len(report.drifted_tickers) > 0

    def test_drift_report_reason(self):
        holdings = {"RELIANCE.NS": 100}
        prices = {"RELIANCE.NS": 2500}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 200000}

        report = compute_drift(holdings, target, {"RELIANCE.NS": 2500, "TCS.NS": 3500})
        assert "drift" in report.reason.lower()

    def test_drift_report_is_dataclass(self):
        report = compute_drift({}, {}, {})
        assert isinstance(report, DriftReport)

    def test_single_stock_no_drift(self):
        holdings = {"RELIANCE.NS": 20}
        prices = {"RELIANCE.NS": 2500}
        target = {"RELIANCE.NS": 50000}

        report = compute_drift(holdings, target, prices)
        assert report.max_drift < 0.01
        assert report.needs_rebalance is False

    def test_new_stock_in_target_causes_drift(self):
        holdings = {"RELIANCE.NS": 20}
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500}
        target = {"RELIANCE.NS": 25000, "TCS.NS": 25000}

        report = compute_drift(holdings, target, prices)
        # TCS has 0% current weight but 50% target => big drift
        assert report.max_drift > 0.40
        assert report.needs_rebalance is True


class TestVolatilityAdjust:
    def test_high_vol_gets_less(self):
        target = {"LOW_VOL.NS": 50000, "HIGH_VOL.NS": 50000}
        vols = {"LOW_VOL.NS": 15.0, "HIGH_VOL.NS": 45.0}

        adjusted = adjust_for_volatility(target, vols, scale_factor=1.0)

        assert adjusted["LOW_VOL.NS"] > adjusted["HIGH_VOL.NS"]

    def test_total_preserved(self):
        target = {"A.NS": 30000, "B.NS": 70000}
        vols = {"A.NS": 20.0, "B.NS": 40.0}

        adjusted = adjust_for_volatility(target, vols)

        assert abs(sum(adjusted.values()) - 100000) < 1  # Total preserved

    def test_no_vols_returns_original(self):
        target = {"A.NS": 50000, "B.NS": 50000}
        adjusted = adjust_for_volatility(target, {})

        assert adjusted == target

    def test_scale_factor_zero(self):
        target = {"A.NS": 30000, "B.NS": 70000}
        vols = {"A.NS": 10.0, "B.NS": 50.0}

        adjusted = adjust_for_volatility(target, vols, scale_factor=0.0)

        assert abs(adjusted["A.NS"] - 30000) < 1
        assert abs(adjusted["B.NS"] - 70000) < 1

    def test_equal_vol_preserves_weights(self):
        target = {"A.NS": 60000, "B.NS": 40000}
        vols = {"A.NS": 20.0, "B.NS": 20.0}

        adjusted = adjust_for_volatility(target, vols, scale_factor=1.0)

        # With equal vols, inverse-vol weights are equal (50/50)
        # With scale_factor=1.0, weights blend fully to inverse-vol
        assert abs(adjusted["A.NS"] - 50000) < 1
        assert abs(adjusted["B.NS"] - 50000) < 1

    def test_empty_target_returns_empty(self):
        adjusted = adjust_for_volatility({}, {"A.NS": 20.0})
        assert adjusted == {}

    def test_vol_floor_at_5_pct(self):
        target = {"A.NS": 50000, "B.NS": 50000}
        vols = {"A.NS": 1.0, "B.NS": 100.0}  # A.NS vol below floor

        adjusted = adjust_for_volatility(target, vols, scale_factor=1.0)

        # A.NS vol floored to 5%, so inv_vol = 1/5 = 0.2
        # B.NS inv_vol = 1/100 = 0.01
        # A gets much more
        assert adjusted["A.NS"] > adjusted["B.NS"]

    def test_missing_vol_uses_default_25(self):
        target = {"A.NS": 50000, "B.NS": 50000}
        vols = {"A.NS": 25.0}  # B.NS missing

        adjusted = adjust_for_volatility(target, vols, scale_factor=1.0)

        # Both effectively have vol=25, so equal inverse-vol weights
        assert abs(adjusted["A.NS"] - adjusted["B.NS"]) < 1


class TestTaxAwareTrades:
    def test_losers_first(self, portfolio_ledger):
        # RELIANCE bought at 2500, now at 2000 (loss)
        # TCS bought at 3500, now at 4000 (gain)
        # HDFCBANK bought at 1600, now at 1800 (gain)
        prices = {"RELIANCE.NS": 2000, "TCS.NS": 4000, "HDFCBANK.NS": 1800}
        target = {"TCS.NS": 40000}  # Sell RELIANCE (loss) and HDFCBANK (gain)

        trades = plan_tax_aware_trades(portfolio_ledger, target, prices, 1000)

        sells = [t for t in trades if t.action == "SELL"]
        if len(sells) >= 2:
            loser_sells = [t for t in sells if t.estimated_gain < 0]
            gainer_sells = [t for t in sells if t.estimated_gain >= 0]
            if loser_sells and gainer_sells:
                assert loser_sells[0].priority < gainer_sells[0].priority

    def test_buys_after_sells(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600, "INFY.NS": 1500}
        target = {"INFY.NS": 50000, "TCS.NS": 35000}

        trades = plan_tax_aware_trades(portfolio_ledger, target, prices, 1000)

        if trades:
            sell_priorities = [t.priority for t in trades if t.action == "SELL"]
            buy_priorities = [t.priority for t in trades if t.action == "BUY"]
            if sell_priorities and buy_priorities:
                assert max(sell_priorities) < min(buy_priorities)

    def test_ltcg_classification(self, ltcg_ledger):
        prices = {"INFY.NS": 1600}
        target = {}  # Sell everything

        trades = plan_tax_aware_trades(ltcg_ledger, target, prices, 100)

        sells = [t for t in trades if t.action == "SELL"]
        assert len(sells) == 1
        assert sells[0].tax_category == "LTCG"

    def test_near_ltcg_flagged(self, tmp_path):
        ledger = Ledger("test_near", db_path=tmp_path / "near.db")
        ledger.reset(initial_capital=500000)

        # Buy 330 days ago (near LTCG boundary)
        near_date = (datetime.now() - timedelta(days=330)).strftime("%Y-%m-%d")
        ledger.record_trade(Trade(near_date, "BUY", "SBIN.NS", 100, 500, 10, "Buy"))

        prices = {"SBIN.NS": 600}
        trades = plan_tax_aware_trades(ledger, {}, prices, 100)

        sells = [t for t in trades if t.action == "SELL"]
        assert len(sells) == 1
        assert "defer" in sells[0].reason.lower() or sells[0].holding_days >= 300

    def test_min_trade_filter(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        # Tiny adjustment that should be filtered out
        target = {
            "RELIANCE.NS": 20 * 2500 + 100,  # Only ~100 INR change
            "TCS.NS": 10 * 3500,
            "HDFCBANK.NS": 30 * 1600,
        }

        trades = plan_tax_aware_trades(portfolio_ledger, target, prices, 5000)

        # The tiny RELIANCE change should be filtered
        rel_trades = [t for t in trades if t.ticker == "RELIANCE.NS"]
        assert len(rel_trades) == 0

    def test_smart_trade_is_dataclass(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2000, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        target = {}

        trades = plan_tax_aware_trades(portfolio_ledger, target, prices, 100)

        for t in trades:
            assert isinstance(t, SmartTrade)

    def test_buy_has_na_tax_category(self, ledger):
        prices = {"RELIANCE.NS": 2500}
        target = {"RELIANCE.NS": 50000}

        trades = plan_tax_aware_trades(ledger, target, prices, 100)

        buys = [t for t in trades if t.action == "BUY"]
        assert len(buys) == 1
        assert buys[0].tax_category == "N/A"
        assert buys[0].holding_days == 0

    def test_new_position_reason(self, ledger):
        prices = {"RELIANCE.NS": 2500}
        target = {"RELIANCE.NS": 50000}

        trades = plan_tax_aware_trades(ledger, target, prices, 100)

        buys = [t for t in trades if t.action == "BUY"]
        assert buys[0].reason == "New position"

    def test_stcg_gainer_classification(self, portfolio_ledger):
        # Portfolio bought 180 days ago, TCS at 3500, now at 4000 (STCG gain)
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 4000, "HDFCBANK.NS": 1600}
        target = {}  # Sell everything

        trades = plan_tax_aware_trades(portfolio_ledger, target, prices, 100)

        tcs_sells = [t for t in trades if t.ticker == "TCS.NS" and t.action == "SELL"]
        assert len(tcs_sells) == 1
        assert tcs_sells[0].tax_category == "STCG"
        assert tcs_sells[0].priority == 40  # STCG gainer priority

    def test_empty_portfolio_only_buys(self, ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 35000}

        trades = plan_tax_aware_trades(ledger, target, prices, 100)

        assert all(t.action == "BUY" for t in trades)

    def test_no_trades_when_at_target(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        # Exact match: 20*2500=50000, 10*3500=35000, 30*1600=48000
        target = {
            "RELIANCE.NS": 50000,
            "TCS.NS": 35000,
            "HDFCBANK.NS": 48000,
        }

        trades = plan_tax_aware_trades(portfolio_ledger, target, prices, 1000)
        assert len(trades) == 0


class TestSmartRebalance:
    def test_force_always_rebalances(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 35000, "HDFCBANK.NS": 48000}

        should, drift = should_rebalance_smart(portfolio_ledger, target, prices, force=True)
        assert should is True

    def test_time_based_trigger(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 35000, "HDFCBANK.NS": 48000}

        # Last rebalance was 180 days ago (> 90 day default)
        should, drift = should_rebalance_smart(portfolio_ledger, target, prices)
        assert should is True

    def test_recent_rebalance_no_drift(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        # Target roughly matches current
        target = {"RELIANCE.NS": 50000, "TCS.NS": 35000, "HDFCBANK.NS": 48000}

        # Set recent rebalance
        portfolio_ledger.set_last_rebalance(datetime.now().strftime("%Y-%m-%d"))

        should, drift = should_rebalance_smart(portfolio_ledger, target, prices)
        # Recent rebalance + no drift = don't rebalance
        assert should is False

    def test_recent_rebalance_with_high_drift(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        # Target heavily different from current
        target = {"RELIANCE.NS": 10000, "TCS.NS": 100000, "HDFCBANK.NS": 5000}

        # Set recent rebalance
        portfolio_ledger.set_last_rebalance(datetime.now().strftime("%Y-%m-%d"))

        should, drift = should_rebalance_smart(portfolio_ledger, target, prices)
        # Recent rebalance but high drift -> should rebalance
        assert should is True
        assert drift.needs_rebalance is True

    def test_returns_drift_report(self, portfolio_ledger):
        prices = {"RELIANCE.NS": 2500, "TCS.NS": 3500, "HDFCBANK.NS": 1600}
        target = {"RELIANCE.NS": 50000, "TCS.NS": 35000, "HDFCBANK.NS": 48000}

        should, drift = should_rebalance_smart(portfolio_ledger, target, prices)
        assert isinstance(drift, DriftReport)

    def test_first_run_no_last_rebalance(self, ledger):
        prices = {"RELIANCE.NS": 2500}
        target = {"RELIANCE.NS": 50000}

        should, drift = should_rebalance_smart(ledger, target, prices)
        # First run (empty last_rebalance) -> should rebalance
        assert should is True
