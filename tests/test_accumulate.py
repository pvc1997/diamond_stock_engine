"""Tests for the Accumulate strategy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from diamond.data.ledger import Ledger, Trade
from diamond.strategies.accumulate import (
    AccumulatePlan,
    Opportunity,
    SellSignal,
    SwapSuggestion,
    ReviewReport,
    compute_quality_score,
    plan_accumulation,
    execute_accumulation,
    add_cash,
    get_accumulate_status,
    review_holdings,
    execute_review_sells,
    execute_swaps,
    _get_deploy_pct,
    _generate_swaps,
    MAX_POSITIONS,
    MIN_DEPLOY_AMOUNT,
    MIN_POSITION_SIZE,
    QUALITY_SELL_THRESHOLD,
    QUALITY_WARN_THRESHOLD,
    STOP_LOSS_PCT,
    REVIEW_FREQUENCY_DAYS,
)


# --- Helpers ---

def _make_screener_df(n: int = 10) -> pd.DataFrame:
    """Create a mock screener DataFrame with quality candidates."""
    tickers = [f"STOCK{i}.NS" for i in range(n)]
    np.random.seed(42)
    return pd.DataFrame({
        "Ticker": tickers,
        "Alpha": np.linspace(1.0, 0.05, n).round(4),
        "Beta": np.random.uniform(0.6, 1.2, n).round(4),
        "CAGR": np.linspace(0.30, 0.12, n).round(4),
        "Volatility": np.random.uniform(0.15, 0.28, n).round(4),
        "Hurst": np.random.uniform(0.45, 0.65, n).round(4),
    })


def _make_low_quality_df() -> pd.DataFrame:
    """Create screener data that fails quality filters."""
    return pd.DataFrame({
        "Ticker": ["BAD1.NS", "BAD2.NS"],
        "Alpha": [-0.1, -0.2],
        "Beta": [1.8, 2.0],
        "CAGR": [0.02, 0.01],
        "Volatility": [0.50, 0.60],
        "Hurst": [0.3, 0.25],
    })


def _make_ledger(tmp_path: Path, strategy: str = "accumulate", capital: float = 500000) -> Ledger:
    """Create an isolated test ledger."""
    ledger = Ledger(strategy, db_path=tmp_path / f"{strategy}.db")
    ledger.reset(initial_capital=capital)
    return ledger


# --- compute_quality_score ---

class TestComputeQualityScore:
    def test_high_quality_stock(self):
        row = pd.Series({
            "CAGR": 0.25,
            "Alpha": 0.6,
            "Volatility": 0.18,
            "Beta": 0.9,
            "Hurst": 0.6,
        })
        score = compute_quality_score(row)
        assert score >= 70, f"High-quality stock should score >= 70, got {score}"

    def test_low_quality_stock(self):
        row = pd.Series({
            "CAGR": 0.05,
            "Alpha": -0.1,
            "Volatility": 0.45,
            "Beta": 1.8,
            "Hurst": 0.3,
        })
        score = compute_quality_score(row)
        assert score <= 20, f"Low-quality stock should score <= 20, got {score}"

    def test_moderate_quality_stock(self):
        row = pd.Series({
            "CAGR": 0.15,
            "Alpha": 0.3,
            "Volatility": 0.25,
            "Beta": 1.0,
            "Hurst": 0.52,
        })
        score = compute_quality_score(row)
        assert 30 <= score <= 70, f"Moderate stock should score 30-70, got {score}"

    def test_missing_columns_use_defaults(self):
        row = pd.Series({"CAGR": 0.20, "Alpha": 0.4})
        score = compute_quality_score(row)
        # Should not crash; uses defaults for missing keys
        assert 0 <= score <= 100

    def test_zero_values(self):
        row = pd.Series({
            "CAGR": 0,
            "Alpha": 0,
            "Volatility": 0.30,
            "Beta": 1.0,
            "Hurst": 0.5,
        })
        score = compute_quality_score(row)
        assert score >= 0

    def test_score_capped_at_100(self):
        row = pd.Series({
            "CAGR": 0.50,
            "Alpha": 1.0,
            "Volatility": 0.10,
            "Beta": 0.9,
            "Hurst": 0.8,
        })
        score = compute_quality_score(row)
        assert score <= 100

    def test_cagr_contribution(self):
        """Higher CAGR should yield higher score."""
        low = pd.Series({"CAGR": 0.05, "Alpha": 0.3, "Volatility": 0.20, "Beta": 0.9, "Hurst": 0.5})
        high = pd.Series({"CAGR": 0.25, "Alpha": 0.3, "Volatility": 0.20, "Beta": 0.9, "Hurst": 0.5})
        assert compute_quality_score(high) > compute_quality_score(low)

    def test_beta_sweetspot_bonus(self):
        """Beta in 0.7-1.1 range should get full bonus."""
        good_beta = pd.Series({"CAGR": 0.15, "Alpha": 0.3, "Volatility": 0.20, "Beta": 0.9, "Hurst": 0.5})
        bad_beta = pd.Series({"CAGR": 0.15, "Alpha": 0.3, "Volatility": 0.20, "Beta": 0.3, "Hurst": 0.5})
        assert compute_quality_score(good_beta) > compute_quality_score(bad_beta)


# --- _get_deploy_pct ---

class TestGetDeployPct:
    def test_deploy_verdict(self):
        assert _get_deploy_pct("DEPLOY") == 0.50

    def test_wait_verdict(self):
        assert _get_deploy_pct("WAIT") == 0.30

    def test_defensive_verdict(self):
        assert _get_deploy_pct("DEFENSIVE") == 0.15

    def test_unknown_verdict_defaults_to_normal(self):
        assert _get_deploy_pct("UNKNOWN") == 0.30


# --- plan_accumulation ---

class TestPlanAccumulation:
    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_with_available_cash_and_candidates(self, mock_sector_cap, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0
        mock_ledger.get_portfolio_value.return_value = 500000.0
        mock_ledger.get_avg_price.return_value = 0.0

        screener_df = _make_screener_df()
        # Sector cap returns all tickers unchanged
        mock_sector_cap.side_effect = lambda x: x

        plan = plan_accumulation(
            "accumulate",
            available_cash=500000.0,
            market_verdict="WAIT",
            screener_df=screener_df,
        )

        assert plan.available_cash == 500000.0
        assert plan.market_verdict == "WAIT"
        assert plan.deploy_pct == 0.30
        assert len(plan.opportunities) > 0
        assert all(isinstance(o, Opportunity) for o in plan.opportunities)

    @patch("diamond.strategies.accumulate.Ledger")
    def test_low_cash_warning(self, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 5000.0

        plan = plan_accumulation(
            "accumulate",
            available_cash=5000.0,
            market_verdict="DEFENSIVE",
            screener_df=_make_screener_df(),
        )

        # 5000 * 0.15 = 750 < MIN_DEPLOY_AMOUNT
        assert len(plan.opportunities) == 0
        assert any("below minimum" in w for w in plan.warnings)

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_max_positions_reached_only_topups(self, mock_sector_cap, MockLedger):
        # Fill MAX_POSITIONS worth of holdings
        holdings = {f"STOCK{i}.NS": 10 for i in range(MAX_POSITIONS)}
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = holdings
        mock_ledger.get_cash.return_value = 200000.0
        mock_ledger.get_portfolio_value.return_value = 700000.0
        mock_ledger.get_avg_price.return_value = 1000.0

        screener_df = _make_screener_df(MAX_POSITIONS + 5)
        mock_sector_cap.side_effect = lambda x: x

        plan = plan_accumulation(
            "accumulate",
            available_cash=200000.0,
            market_verdict="WAIT",
            screener_df=screener_df,
            max_positions=MAX_POSITIONS,
        )

        assert any("max positions" in w.lower() for w in plan.warnings)
        # All opportunities should be for existing positions
        for opp in plan.opportunities:
            assert opp.ticker in holdings

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_deploy_verdict_higher_budget(self, mock_sector_cap, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0
        mock_ledger.get_portfolio_value.return_value = 500000.0
        mock_ledger.get_avg_price.return_value = 0.0
        mock_sector_cap.side_effect = lambda x: x

        plan = plan_accumulation(
            "accumulate",
            available_cash=500000.0,
            market_verdict="DEPLOY",
            screener_df=_make_screener_df(),
        )

        assert plan.deploy_pct == 0.50
        assert plan.deploy_budget == 250000.0

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_defensive_verdict_lower_budget(self, mock_sector_cap, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0
        mock_ledger.get_portfolio_value.return_value = 500000.0
        mock_ledger.get_avg_price.return_value = 0.0
        mock_sector_cap.side_effect = lambda x: x

        plan = plan_accumulation(
            "accumulate",
            available_cash=500000.0,
            market_verdict="DEFENSIVE",
            screener_df=_make_screener_df(),
        )

        assert plan.deploy_pct == 0.15
        assert plan.deploy_budget == 75000.0

    @patch("diamond.strategies.accumulate.Ledger")
    def test_empty_screener(self, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0

        plan = plan_accumulation(
            "accumulate",
            available_cash=500000.0,
            market_verdict="WAIT",
            screener_df=pd.DataFrame(),
        )

        assert len(plan.opportunities) == 0
        assert any("no data" in w.lower() for w in plan.warnings)

    @patch("diamond.strategies.accumulate.Ledger")
    def test_no_quality_candidates(self, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_cash.return_value = 500000.0

        plan = plan_accumulation(
            "accumulate",
            available_cash=500000.0,
            market_verdict="WAIT",
            screener_df=_make_low_quality_df(),
        )

        assert len(plan.opportunities) == 0
        assert any("quality" in w.lower() for w in plan.warnings)


# --- execute_accumulation ---

class TestExecuteAccumulation:
    def test_no_opportunities(self):
        plan = AccumulatePlan(
            available_cash=500000,
            deploy_budget=150000,
            market_verdict="WAIT",
            deploy_pct=0.30,
            opportunities=[],
            existing_positions=0,
            total_positions_after=0,
        )
        result = execute_accumulation("accumulate", plan)
        assert result["status"] == "no_opportunities"
        assert result["trades"] == 0

    @patch("diamond.execution.executor._record_to_order_book")
    @patch("diamond.data.market.download_single")
    @patch("diamond.data.ledger.Ledger")
    def test_dry_run_no_trades_recorded(self, MockLedger, mock_download, mock_order_book):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_cash.return_value = 500000.0

        # Mock price
        mock_download.return_value = pd.Series([1000.0])

        plan = AccumulatePlan(
            available_cash=500000,
            deploy_budget=150000,
            market_verdict="WAIT",
            deploy_pct=0.30,
            opportunities=[
                Opportunity(
                    ticker="STOCK0.NS", sector="Technology", quality_score=80.0,
                    suggested_amount=50000, reason="New position, Quality=80",
                    alpha=0.5, cagr=0.20, beta=0.9, volatility=0.18,
                ),
            ],
            existing_positions=0,
            total_positions_after=1,
        )

        result = execute_accumulation("accumulate", plan, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["trades"] == 1
        assert "total_deploy" in result
        # Should NOT have called record_trade
        mock_ledger.record_trade.assert_not_called()

    @patch("diamond.execution.executor._record_to_order_book")
    @patch("diamond.data.market.download_single")
    @patch("diamond.data.ledger.Ledger")
    def test_execute_records_trades(self, MockLedger, mock_download, mock_order_book):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_cash.return_value = 500000.0
        mock_ledger.get_portfolio_value.return_value = 450000.0
        mock_ledger.get_holdings.return_value = {"STOCK0.NS": 50}

        mock_download.return_value = pd.Series([1000.0])

        plan = AccumulatePlan(
            available_cash=500000,
            deploy_budget=150000,
            market_verdict="WAIT",
            deploy_pct=0.30,
            opportunities=[
                Opportunity(
                    ticker="STOCK0.NS", sector="Technology", quality_score=75.0,
                    suggested_amount=50000, reason="Top-up existing, Quality=75",
                    alpha=0.5, cagr=0.20, beta=0.9, volatility=0.18,
                ),
            ],
            existing_positions=1,
            total_positions_after=1,
        )

        result = execute_accumulation("accumulate", plan, dry_run=False)
        assert result["status"] == "executed"
        assert result["trades"] == 1
        mock_ledger.record_trade.assert_called_once()


# --- add_cash ---

class TestAddCash:
    def test_increases_balance(self, tmp_path: Path):
        ledger = _make_ledger(tmp_path, capital=100000)

        with patch("diamond.strategies.accumulate.Ledger", return_value=ledger):
            new_balance = add_cash("accumulate", 50000)
            assert new_balance == 150000.0

    def test_multiple_topups(self, tmp_path: Path):
        ledger = _make_ledger(tmp_path, capital=100000)

        with patch("diamond.strategies.accumulate.Ledger", return_value=ledger):
            add_cash("accumulate", 25000)
            new_balance = add_cash("accumulate", 25000)
            assert new_balance == 150000.0


# --- get_accumulate_status ---

class TestGetAccumulateStatus:
    def test_fresh_status_shape(self):
        with patch("diamond.strategies.accumulate.Ledger") as MockLedger:
            mock = MockLedger.return_value
            mock.get_holdings.return_value = {}
            mock.get_cash.return_value = 500000.0
            mock.get_initial_capital.return_value = 500000.0
            mock.get_total_fees.return_value = 0.0
            mock.get_trades.return_value = []
            mock.get_last_rebalance.return_value = ""

            status = get_accumulate_status("accumulate")

            assert status["strategy"] == "accumulate"
            assert status["holdings_count"] == 0
            assert status["cash"] == 500000.0
            assert status["initial_capital"] == 500000.0
            assert status["total_fees"] == 0.0
            assert status["trade_count"] == 0
            assert status["last_rebalance"] == ""

    def test_status_with_holdings(self, tmp_path: Path):
        ledger = _make_ledger(tmp_path, capital=500000)
        ledger.record_trade(Trade(
            "2024-06-01", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Accumulate",
        ))

        with patch("diamond.strategies.accumulate.Ledger", return_value=ledger):
            status = get_accumulate_status("accumulate")

            assert status["holdings_count"] == 1
            assert status["holdings"] == {"RELIANCE.NS": 10}
            assert status["trade_count"] == 1
            assert status["total_fees"] == 50.0
            # Cash should be reduced by trade value + cost
            assert status["cash"] == 500000.0 - (10 * 2500.0) - 50.0


# --- Helpers for review tests ---

def _make_review_screener_df(tickers: list[str], qualities: list[float]) -> pd.DataFrame:
    """Create screener df with controlled quality scores."""
    n = len(tickers)
    # Reverse-engineer screener fields from desired quality scores
    rows = []
    for i, (ticker, q) in enumerate(zip(tickers, qualities)):
        if q >= 70:
            rows.append({"Ticker": ticker, "Alpha": 0.6, "Beta": 0.9, "CAGR": 0.25, "Volatility": 0.18, "Hurst": 0.6})
        elif q >= 35:
            rows.append({"Ticker": ticker, "Alpha": 0.2, "Beta": 1.0, "CAGR": 0.12, "Volatility": 0.28, "Hurst": 0.52})
        else:
            rows.append({"Ticker": ticker, "Alpha": -0.1, "Beta": 1.8, "CAGR": 0.03, "Volatility": 0.45, "Hurst": 0.3})
    return pd.DataFrame(rows)


# --- review_holdings ---

class TestReviewHoldings:
    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_no_holdings_empty_report(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_last_rebalance.return_value = ""

        report = review_holdings("accumulate", current_prices={}, screener_df=pd.DataFrame())
        assert report.holdings_reviewed == 0
        assert report.sell_signals == []
        assert report.swap_suggestions == []

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_healthy_holdings_no_signals(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"GOOD1.NS": 10, "GOOD2.NS": 20}
        mock_ledger.get_avg_price.return_value = 1000.0
        mock_ledger.get_last_rebalance.return_value = "2026-01-01"

        # High quality + price above avg = healthy
        screener_df = _make_review_screener_df(["GOOD1.NS", "GOOD2.NS"], [75, 80])
        prices = {"GOOD1.NS": 1200.0, "GOOD2.NS": 1100.0}

        report = review_holdings("accumulate", current_prices=prices, screener_df=screener_df)
        assert report.holdings_reviewed == 2
        assert report.healthy_count == 2
        assert report.sell_count == 0
        assert report.watch_count == 0
        assert len(report.sell_signals) == 0

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_quality_drop_triggers_sell(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"BAD1.NS": 10}
        mock_ledger.get_avg_price.return_value = 1000.0
        mock_ledger.get_last_rebalance.return_value = ""

        # Quality below QUALITY_SELL_THRESHOLD (20)
        screener_df = _make_review_screener_df(["BAD1.NS"], [10])
        prices = {"BAD1.NS": 950.0}  # Not a stop-loss, just quality drop

        mock_cap.side_effect = lambda x: x

        report = review_holdings("accumulate", current_prices=prices, screener_df=screener_df)
        assert report.sell_count == 1
        assert report.sell_signals[0].signal_type == "QUALITY_DROP"
        assert report.sell_signals[0].severity == "SELL"

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_stop_loss_triggers_sell(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"DROP1.NS": 10}
        mock_ledger.get_avg_price.return_value = 1000.0
        mock_ledger.get_last_rebalance.return_value = ""

        # Quality fine but price dropped 15%+
        screener_df = _make_review_screener_df(["DROP1.NS"], [60])
        prices = {"DROP1.NS": 840.0}  # -16% from avg

        mock_cap.side_effect = lambda x: x

        report = review_holdings("accumulate", current_prices=prices, screener_df=screener_df)
        assert report.sell_count == 1
        assert report.sell_signals[0].signal_type == "STOP_LOSS"
        assert report.sell_signals[0].severity == "SELL"

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_both_quality_and_stop_loss(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"WORST.NS": 10}
        mock_ledger.get_avg_price.return_value = 1000.0
        mock_ledger.get_last_rebalance.return_value = ""

        screener_df = _make_review_screener_df(["WORST.NS"], [10])
        prices = {"WORST.NS": 800.0}  # -20% + low quality

        mock_cap.side_effect = lambda x: x

        report = review_holdings("accumulate", current_prices=prices, screener_df=screener_df)
        assert report.sell_count == 1
        assert report.sell_signals[0].signal_type == "BOTH"

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_quality_warn_is_watch(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"WARN1.NS": 10}
        mock_ledger.get_avg_price.return_value = 1000.0
        mock_ledger.get_last_rebalance.return_value = ""

        # Quality between SELL (20) and WARN (35) thresholds
        # Alpha=0.1, Beta=1.3, CAGR=0.08, Vol=0.32, Hurst=0.48 -> quality ~27
        screener_df = pd.DataFrame({
            "Ticker": ["WARN1.NS"],
            "Alpha": [0.1], "Beta": [1.3], "CAGR": [0.08],
            "Volatility": [0.32], "Hurst": [0.48],
        })
        prices = {"WARN1.NS": 950.0}  # No stop-loss

        mock_cap.side_effect = lambda x: x

        report = review_holdings("accumulate", current_prices=prices, screener_df=screener_df)
        assert report.watch_count == 1
        assert report.sell_count == 0
        assert report.sell_signals[0].severity == "WATCH"

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_review_due_after_90_days(self, mock_cap, mock_prices, MockLedger):
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_last_rebalance.return_value = "2025-12-01"  # >90 days ago

        report = review_holdings("accumulate", current_prices={}, screener_df=pd.DataFrame())
        assert report.next_review_due is True
        assert report.days_since_last_review is not None
        assert report.days_since_last_review >= 90

    @patch("diamond.strategies.accumulate.Ledger")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.apply_sector_cap")
    def test_review_not_due_recent(self, mock_cap, mock_prices, MockLedger):
        from datetime import datetime, timedelta

        recent = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {}
        mock_ledger.get_last_rebalance.return_value = recent

        report = review_holdings("accumulate", current_prices={}, screener_df=pd.DataFrame())
        assert report.next_review_due is False


# --- _generate_swaps ---

class TestGenerateSwaps:
    def test_no_sell_signals_no_swaps(self):
        result = _generate_swaps([], {}, {}, pd.DataFrame(), {})
        assert result == []

    def test_swap_matches_sell_with_replacement(self):
        sell_signal = SellSignal(
            ticker="BAD.NS", sector="Technology", shares=10, avg_price=1000,
            current_price=800, pnl_pct=-20.0, quality_score=15,
            signal_type="QUALITY_DROP", severity="SELL", reason="test",
        )
        holdings = {"BAD.NS": 10}
        quality_map = {"BAD.NS": 15, "GOOD.NS": 80}

        screener_df = pd.DataFrame({
            "Ticker": ["BAD.NS", "GOOD.NS"],
            "Alpha": [-0.1, 0.5],
            "Beta": [1.5, 0.9],
            "CAGR": [0.03, 0.25],
            "Volatility": [0.40, 0.18],
            "Hurst": [0.3, 0.6],
        })
        prices = {"BAD.NS": 800, "GOOD.NS": 1500}

        with patch("diamond.strategies.accumulate.apply_sector_cap", side_effect=lambda x: x):
            swaps = _generate_swaps([sell_signal], holdings, quality_map, screener_df, prices)

        assert len(swaps) == 1
        assert swaps[0].sell_ticker == "BAD.NS"
        assert swaps[0].buy_ticker == "GOOD.NS"
        assert swaps[0].quality_gain > 0

    def test_watch_signals_ignored_for_swaps(self):
        watch_signal = SellSignal(
            ticker="WARN.NS", sector="Banking", shares=5, avg_price=500,
            current_price=480, pnl_pct=-4.0, quality_score=30,
            signal_type="QUALITY_DROP", severity="WATCH", reason="test",
        )
        screener_df = _make_screener_df()

        with patch("diamond.strategies.accumulate.apply_sector_cap", side_effect=lambda x: x):
            swaps = _generate_swaps([watch_signal], {"WARN.NS": 5}, {}, screener_df, {})

        assert swaps == []


# --- execute_review_sells ---

class TestExecuteReviewSells:
    def test_no_sells_returns_early(self):
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=5, sell_signals=[], swap_suggestions=[],
            healthy_count=5, watch_count=0, sell_count=0,
            days_since_last_review=None, next_review_due=True,
        )
        result = execute_review_sells("accumulate", report)
        assert result["status"] == "no_sells"

    def test_only_watch_signals_no_execution(self):
        watch = SellSignal(
            ticker="WATCH.NS", sector="IT", shares=10, avg_price=1000,
            current_price=950, pnl_pct=-5.0, quality_score=30,
            signal_type="QUALITY_DROP", severity="WATCH", reason="test",
        )
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=1, sell_signals=[watch], swap_suggestions=[],
            healthy_count=0, watch_count=1, sell_count=0,
            days_since_last_review=None, next_review_due=True,
        )
        result = execute_review_sells("accumulate", report)
        assert result["status"] == "no_sells"

    @patch("diamond.execution.executor._record_to_order_book")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.Ledger")
    def test_dry_run_no_trade_recorded(self, MockLedger, mock_prices, mock_order_book):
        mock_prices.return_value = {"SELL1.NS": 900.0}
        mock_ledger = MockLedger.return_value

        sell = SellSignal(
            ticker="SELL1.NS", sector="Auto", shares=10, avg_price=1000,
            current_price=900, pnl_pct=-10.0, quality_score=15,
            signal_type="QUALITY_DROP", severity="SELL", reason="test",
        )
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=1, sell_signals=[sell], swap_suggestions=[],
            healthy_count=0, watch_count=0, sell_count=1,
            days_since_last_review=None, next_review_due=True,
        )

        result = execute_review_sells("accumulate", report, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["trades"] == 1
        assert result["total_freed"] == 9000.0
        mock_ledger.record_trade.assert_not_called()

    @patch("diamond.execution.executor._record_to_order_book")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.Ledger")
    def test_execute_records_sell_trade(self, MockLedger, mock_prices, mock_order_book):
        mock_prices.return_value = {"SELL1.NS": 900.0}
        mock_ledger = MockLedger.return_value
        mock_ledger.get_cash.return_value = 9000.0
        mock_ledger.get_holdings.return_value = {}

        sell = SellSignal(
            ticker="SELL1.NS", sector="Auto", shares=10, avg_price=1000,
            current_price=900, pnl_pct=-10.0, quality_score=15,
            signal_type="QUALITY_DROP", severity="SELL", reason="test",
        )
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=1, sell_signals=[sell], swap_suggestions=[],
            healthy_count=0, watch_count=0, sell_count=1,
            days_since_last_review=None, next_review_due=True,
        )

        result = execute_review_sells("accumulate", report, dry_run=False)
        assert result["status"] == "executed"
        assert result["trades"] == 1
        mock_ledger.record_trade.assert_called_once()


# --- execute_swaps ---

class TestExecuteSwaps:
    def test_no_swaps_returns_early(self):
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=1, sell_signals=[], swap_suggestions=[],
            healthy_count=1, watch_count=0, sell_count=0,
            days_since_last_review=None, next_review_due=True,
        )
        result = execute_swaps("accumulate", report)
        assert result["status"] == "no_swaps"

    @patch("diamond.execution.executor._record_to_order_book")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.Ledger")
    def test_dry_run_swap(self, MockLedger, mock_prices, mock_order_book):
        mock_prices.return_value = {"BAD.NS": 800.0, "GOOD.NS": 1500.0}
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"BAD.NS": 10}

        swap = SwapSuggestion(
            sell_ticker="BAD.NS", sell_reason="Quality drop",
            sell_quality=15, sell_pnl_pct=-20.0,
            buy_ticker="GOOD.NS", buy_reason="Quality=80",
            buy_quality=80, freed_capital=8000, quality_gain=65,
        )
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=1, sell_signals=[], swap_suggestions=[swap],
            healthy_count=0, watch_count=0, sell_count=1,
            days_since_last_review=None, next_review_due=True,
        )

        result = execute_swaps("accumulate", report, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["sells"] == 1
        assert result["buys"] == 1
        mock_ledger.record_trade.assert_not_called()

    @patch("diamond.execution.executor._record_to_order_book")
    @patch("diamond.strategies.accumulate._fetch_prices")
    @patch("diamond.strategies.accumulate.Ledger")
    def test_execute_swap_records_both_trades(self, MockLedger, mock_prices, mock_order_book):
        mock_prices.return_value = {"BAD.NS": 800.0, "GOOD.NS": 500.0}
        mock_ledger = MockLedger.return_value
        mock_ledger.get_holdings.return_value = {"BAD.NS": 10}
        mock_ledger.get_cash.return_value = 50000.0

        swap = SwapSuggestion(
            sell_ticker="BAD.NS", sell_reason="Quality drop",
            sell_quality=15, sell_pnl_pct=-20.0,
            buy_ticker="GOOD.NS", buy_reason="Quality=80",
            buy_quality=80, freed_capital=8000, quality_gain=65,
        )
        report = ReviewReport(
            strategy="accumulate", review_date="2026-03-06",
            holdings_reviewed=1, sell_signals=[], swap_suggestions=[swap],
            healthy_count=0, watch_count=0, sell_count=1,
            days_since_last_review=None, next_review_due=True,
        )

        result = execute_swaps("accumulate", report, dry_run=False)
        assert result["status"] == "executed"
        assert result["sells"] == 1
        assert result["buys"] == 1
        # Should record both sell and buy trades
        assert mock_ledger.record_trade.call_count == 2
