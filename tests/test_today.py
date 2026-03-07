"""Tests for the daily briefing engine."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from diamond.daily.today import (
    TodayBriefing,
    MarketSnapshot,
    PortfolioSnapshot,
    SectorMove,
    OpportunitySummary,
    _greeting,
    _build_market_snapshot,
    _build_portfolio_snapshot,
    _build_sector_moves,
    _pick_insight,
    get_today_briefing,
)


class TestGreeting:
    @patch("diamond.daily.today.datetime")
    def test_morning(self, mock_dt):
        mock_dt.now.return_value.hour = 9
        assert _greeting() == "Good morning"

    @patch("diamond.daily.today.datetime")
    def test_afternoon(self, mock_dt):
        mock_dt.now.return_value.hour = 14
        assert _greeting() == "Good afternoon"

    @patch("diamond.daily.today.datetime")
    def test_evening(self, mock_dt):
        mock_dt.now.return_value.hour = 20
        assert _greeting() == "Good evening"


class TestBuildMarketSnapshot:
    @patch("diamond.monitoring.market_pulse.get_market_pulse")
    def test_returns_snapshot(self, mock_pulse):
        mock_pulse.return_value = MagicMock(
            nifty_price=22500, nifty_change_pct=0.5,
            vix=14.5, vix_regime="NORMAL",
            breadth_pct=62, breadth_regime="HEALTHY",
            trend="BULLISH", nifty_rsi_14=55,
            momentum_regime="NEUTRAL", verdict="WAIT",
            score=15, nifty_distance_200dma_pct=3.2,
        )
        result = _build_market_snapshot()
        assert result is not None
        assert result.nifty_price == 22500
        assert result.verdict == "WAIT"

    @patch("diamond.monitoring.market_pulse.get_market_pulse", side_effect=Exception("fail"))
    def test_returns_none_on_error(self, mock_pulse):
        assert _build_market_snapshot() is None


class TestBuildPortfolioSnapshot:
    @patch("diamond.data.ledger.Ledger")
    def test_no_holdings_returns_none(self, MockLedger):
        MockLedger.return_value.get_holdings.return_value = {}
        result = _build_portfolio_snapshot("test", {})
        assert result is None

    @patch("diamond.monitoring.alerts.run_health_check", return_value=[])
    @patch("diamond.data.market.download_prices")
    @patch("diamond.data.ledger.Ledger")
    def test_with_holdings(self, MockLedger, mock_dl, mock_health):
        ledger = MockLedger.return_value
        ledger.get_holdings.return_value = {"RELIANCE.NS": 10}
        ledger.get_cash.return_value = 100000
        ledger.get_initial_capital.return_value = 500000
        ledger.get_portfolio_value.return_value = 450000

        mock_dl.return_value = pd.DataFrame({
            "RELIANCE.NS": [2400, 2450, 2500],
        })

        result = _build_portfolio_snapshot("test", {"RELIANCE.NS": 2500})
        assert result is not None
        assert result.holdings_count == 1
        assert result.nav == 450000


class TestBuildSectorMoves:
    @patch("diamond.data.universe.get_sector", return_value="Technology")
    @patch("diamond.data.universe.get_nifty50", return_value=["TCS.NS"])
    @patch("diamond.data.market.download_prices")
    def test_returns_moves(self, mock_dl, mock_nifty, mock_sector):
        mock_dl.return_value = pd.DataFrame({
            "TCS.NS": [3500, 3550, 3600],
        })
        moves = _build_sector_moves()
        assert len(moves) >= 1
        assert moves[0].sector == "Technology"

    @patch("diamond.data.market.download_prices", side_effect=Exception("fail"))
    def test_returns_empty_on_error(self, mock_dl):
        assert _build_sector_moves() == []


class TestPickInsight:
    def test_returns_string_with_market(self):
        market = MarketSnapshot(
            nifty_price=22000, nifty_change_pct=-1.5, vix=18, vix_regime="NORMAL",
            breadth_pct=55, breadth_regime="HEALTHY", trend="SIDEWAYS", rsi=48,
            momentum="NEUTRAL", verdict="WAIT", score=10, distance_200dma_pct=2.5,
        )
        result = _pick_insight(market, None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_default_without_data(self):
        result = _pick_insight(None, None)
        assert "marathon" in result.lower() or len(result) > 0


class TestGetTodayBriefing:
    @patch("diamond.daily.today._build_opportunities", return_value=[])
    @patch("diamond.daily.today._build_sector_moves", return_value=[])
    @patch("diamond.daily.today._build_portfolio_snapshot", return_value=None)
    @patch("diamond.daily.today._build_market_snapshot", return_value=None)
    @patch("diamond.data.ledger.Ledger")
    def test_returns_briefing_shape(self, MockLedger, mock_market, mock_port, mock_sec, mock_opp):
        MockLedger.return_value.get_holdings.return_value = {}
        briefing = get_today_briefing("test", skip_market=True, skip_opportunities=True)
        assert isinstance(briefing, TodayBriefing)
        assert briefing.greeting in ("Good morning", "Good afternoon", "Good evening")
