"""Daily briefing engine — the homepage you visit every day.

Aggregates market snapshot, portfolio performance, opportunities, sector
rotation, and a daily insight into a single TodayBriefing object.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PortfolioSnapshot:
    """Portfolio state for today."""

    strategy: str
    nav: float
    cash: float
    initial_capital: float
    holdings_count: int
    total_return_pct: float  # (NAV - initial) / initial * 100
    day_change_pct: float  # Estimated single-day change
    day_change_inr: float  # INR change today
    top_gainer: str  # Ticker
    top_gainer_pct: float
    top_loser: str
    top_loser_pct: float
    alerts: list[str] = field(default_factory=list)


@dataclass
class MarketSnapshot:
    """Market conditions summary."""

    nifty_price: float
    nifty_change_pct: float
    vix: float
    vix_regime: str
    breadth_pct: float
    breadth_regime: str
    trend: str
    rsi: float
    momentum: str
    verdict: str
    score: int
    distance_200dma_pct: float


@dataclass
class SectorMove:
    """Sector performance."""

    sector: str
    change_pct: float
    direction: str  # UP / DOWN / FLAT


@dataclass
class OpportunitySummary:
    """Quick opportunity summary."""

    ticker: str
    quality_score: float
    reason: str


@dataclass
class TodayBriefing:
    """Everything you need to know today."""

    timestamp: str
    greeting: str
    market: MarketSnapshot | None = None
    portfolio: PortfolioSnapshot | None = None
    sector_moves: list[SectorMove] = field(default_factory=list)
    opportunities: list[OpportunitySummary] = field(default_factory=list)
    insight: str = ""
    alerts: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Greetings
# ---------------------------------------------------------------------------


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    return "Good evening"


# ---------------------------------------------------------------------------
# Market snapshot
# ---------------------------------------------------------------------------


def _build_market_snapshot() -> MarketSnapshot | None:
    try:
        from diamond.monitoring.market_pulse import get_market_pulse

        p = get_market_pulse()
        return MarketSnapshot(
            nifty_price=p.nifty_price,
            nifty_change_pct=p.nifty_change_pct,
            vix=p.vix,
            vix_regime=p.vix_regime,
            breadth_pct=p.breadth_pct,
            breadth_regime=p.breadth_regime,
            trend=p.trend,
            rsi=p.nifty_rsi_14,
            momentum=p.momentum_regime,
            verdict=p.verdict,
            score=p.score,
            distance_200dma_pct=p.nifty_distance_200dma_pct,
        )
    except Exception as e:
        logger.warning(f"Market snapshot failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Portfolio snapshot
# ---------------------------------------------------------------------------


def _build_portfolio_snapshot(
    strategy: str,
    current_prices: dict[str, float],
) -> PortfolioSnapshot | None:
    try:
        from diamond.data.ledger import Ledger

        ledger = Ledger(strategy)
        holdings = ledger.get_holdings()

        if not holdings:
            return None

        cash = ledger.get_cash()
        initial = ledger.get_initial_capital()
        nav = ledger.get_portfolio_value(current_prices)
        total_return = ((nav - initial) / initial * 100) if initial > 0 else 0

        # Day change per stock
        day_changes: dict[str, float] = {}
        try:
            from diamond.data.market import download_prices

            tickers = list(holdings.keys())
            prices_df = download_prices(tickers, period_days=5, use_cache=True)
            if not prices_df.empty:
                for col in prices_df.columns:
                    series = prices_df[col].dropna()
                    if len(series) >= 2:
                        prev = float(series.iloc[-2])
                        cur = float(series.iloc[-1])
                        if prev > 0:
                            day_changes[col] = round((cur - prev) / prev * 100, 2)
        except Exception:
            pass

        # Portfolio day change (weighted)
        total_value = sum(holdings[t] * current_prices.get(t, 0) for t in holdings)
        day_change_pct = 0.0
        day_change_inr = 0.0
        if total_value > 0:
            for ticker, shares in holdings.items():
                price = current_prices.get(ticker, 0)
                weight = (shares * price) / total_value if total_value > 0 else 0
                stock_change = day_changes.get(ticker, 0)
                day_change_pct += weight * stock_change
                day_change_inr += weight * stock_change / 100 * total_value
        day_change_pct = round(day_change_pct, 2)
        day_change_inr = round(day_change_inr, 0)

        # Top gainer / loser
        top_gainer = ""
        top_gainer_pct = 0.0
        top_loser = ""
        top_loser_pct = 0.0
        if day_changes:
            sorted_changes = sorted(day_changes.items(), key=lambda x: x[1], reverse=True)
            if sorted_changes:
                top_gainer = sorted_changes[0][0]
                top_gainer_pct = sorted_changes[0][1]
            if len(sorted_changes) > 1:
                top_loser = sorted_changes[-1][0]
                top_loser_pct = sorted_changes[-1][1]

        # Alerts
        alerts: list[str] = []
        try:
            from diamond.monitoring.alerts import run_health_check

            health_alerts = run_health_check(strategy, current_prices)
            for a in health_alerts:
                alerts.append(f"[{a.level.upper()}] {a.message}")
        except Exception:
            pass

        return PortfolioSnapshot(
            strategy=strategy,
            nav=round(nav, 2),
            cash=round(cash, 2),
            initial_capital=initial,
            holdings_count=len(holdings),
            total_return_pct=round(total_return, 2),
            day_change_pct=day_change_pct,
            day_change_inr=day_change_inr,
            top_gainer=top_gainer,
            top_gainer_pct=top_gainer_pct,
            top_loser=top_loser,
            top_loser_pct=top_loser_pct,
            alerts=alerts,
        )
    except Exception as e:
        logger.warning(f"Portfolio snapshot failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Sector rotation
# ---------------------------------------------------------------------------


def _build_sector_moves() -> list[SectorMove]:
    """Compute sector-level daily moves from Nifty 50 stocks."""
    try:
        from diamond.data.market import download_prices
        from diamond.data.universe import get_nifty50, get_sector

        tickers = get_nifty50()
        prices_df = download_prices(tickers, period_days=5, use_cache=True)

        if prices_df.empty:
            return []

        sector_changes: dict[str, list[float]] = {}
        for col in prices_df.columns:
            series = prices_df[col].dropna()
            if len(series) < 2:
                continue
            prev = float(series.iloc[-2])
            cur = float(series.iloc[-1])
            if prev <= 0:
                continue
            change = (cur - prev) / prev * 100
            sector = get_sector(col)
            sector_changes.setdefault(sector, []).append(change)

        moves: list[SectorMove] = []
        for sector, changes in sorted(sector_changes.items()):
            avg = round(sum(changes) / len(changes), 2)
            direction = "UP" if avg > 0.3 else "DOWN" if avg < -0.3 else "FLAT"
            moves.append(SectorMove(sector=sector, change_pct=avg, direction=direction))

        # Sort by absolute change descending
        moves.sort(key=lambda m: abs(m.change_pct), reverse=True)
        return moves

    except Exception as e:
        logger.warning(f"Sector moves failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


def _build_opportunities(strategy: str) -> list[OpportunitySummary]:
    """Find top 3 opportunities for the accumulate portfolio."""
    try:
        from diamond.strategies.accumulate import plan_accumulation

        plan = plan_accumulation(
            strategy,
            market_verdict="WAIT",  # Don't let verdict affect opportunity list
        )
        summaries = []
        for opp in plan.opportunities[:3]:
            summaries.append(
                OpportunitySummary(
                    ticker=opp.ticker,
                    quality_score=opp.quality_score,
                    reason=opp.reason,
                )
            )
        return summaries
    except Exception as e:
        logger.warning(f"Opportunity scan failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Daily insight
# ---------------------------------------------------------------------------

_INSIGHTS = [
    lambda m, p: (
        (
            f"Your portfolio beta means a {abs(m.nifty_change_pct):.1f}% Nifty move "
            f"roughly translates to a {abs(m.nifty_change_pct * 0.85):.1f}% move in your portfolio"
        )
        if m and p
        else None
    ),
    lambda m, p: (
        (f"VIX at {m.vix:.1f} means options are pricing in ~{m.vix / (252**0.5):.1f}% daily moves in Nifty")
        if m and m.vix > 0
        else None
    ),
    lambda m, p: (
        (
            f"Market breadth at {m.breadth_pct:.0f}% — "
            f"{'most stocks participating in the rally' if m.breadth_pct > 60 else 'rally is narrow, led by few heavyweights'}"
        )
        if m
        else None
    ),
    lambda m, p: (
        (
            f"Nifty RSI at {m.rsi:.0f} — "
            f"{'getting overbought, pullback possible' if m.rsi > 65 else 'in neutral zone, no extreme' if m.rsi > 35 else 'oversold territory, historically a good entry zone'}"
        )
        if m
        else None
    ),
    lambda m, p: (
        (
            f"Nifty is {m.distance_200dma_pct:+.1f}% from its 200-day average — "
            f"{'stretched high, mean reversion risk' if m.distance_200dma_pct > 10 else 'close to long-term average, fair value zone' if abs(m.distance_200dma_pct) < 5 else 'below average, could be a value opportunity'}"
        )
        if m and m.distance_200dma_pct != 0
        else None
    ),
    lambda m, p: (
        (
            f"Your total return is {p.total_return_pct:+.1f}% — "
            f"{'ahead of schedule for your 10-year goal' if p.total_return_pct > 5 else 'early days, compounding takes time'}"
        )
        if p
        else None
    ),
    lambda m, p: (
        (
            f"With {p.holdings_count} stocks and {p.cash:,.0f} cash, "
            f"you have room for {max(0, 20 - p.holdings_count)} more positions"
        )
        if p and p.holdings_count < 20
        else None
    ),
]


def _pick_insight(market: MarketSnapshot | None, portfolio: PortfolioSnapshot | None) -> str:
    """Pick a contextual insight based on today's date (rotates daily)."""
    day_of_year = datetime.now().timetuple().tm_yday
    valid_insights = []
    for fn in _INSIGHTS:
        result = fn(market, portfolio)
        if result:
            valid_insights.append(result)
    if not valid_insights:
        return "Stay patient. Long-term investing is a marathon, not a sprint."
    return valid_insights[day_of_year % len(valid_insights)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_today_briefing(
    strategy: str = "accumulate",
    skip_market: bool = False,
    skip_opportunities: bool = False,
) -> TodayBriefing:
    """Build the daily briefing.

    Args:
        strategy: Which portfolio to report on.
        skip_market: Skip market data fetch (faster).
        skip_opportunities: Skip opportunity scan (faster).

    Returns:
        TodayBriefing with all sections populated.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    briefing = TodayBriefing(
        timestamp=timestamp,
        greeting=_greeting(),
    )

    # Market snapshot
    if not skip_market:
        briefing.market = _build_market_snapshot()

    # Fetch current prices for portfolio
    current_prices: dict[str, float] = {}
    try:
        from diamond.data.ledger import Ledger
        from diamond.data.market import download_prices

        ledger = Ledger(strategy)
        holdings = ledger.get_holdings()
        if holdings:
            tickers = list(holdings.keys())
            prices_df = download_prices(tickers, period_days=5, use_cache=True)
            if not prices_df.empty:
                for col in prices_df.columns:
                    series = prices_df[col].dropna()
                    if len(series) > 0:
                        current_prices[col] = float(series.iloc[-1])
    except Exception:
        pass

    # Portfolio snapshot
    briefing.portfolio = _build_portfolio_snapshot(strategy, current_prices)

    # Sector rotation
    if not skip_market:
        briefing.sector_moves = _build_sector_moves()

    # Opportunities
    if not skip_opportunities:
        briefing.opportunities = _build_opportunities(strategy)

    # Daily insight
    briefing.insight = _pick_insight(briefing.market, briefing.portfolio)

    # Aggregate alerts
    if briefing.portfolio and briefing.portfolio.alerts:
        briefing.alerts = briefing.portfolio.alerts

    return briefing
