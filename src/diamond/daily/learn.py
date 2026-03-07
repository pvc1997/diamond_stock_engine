"""Daily learning engine — contextual market education using YOUR portfolio.

Each day surfaces a different concept, explained with real examples from
your holdings, making abstract market concepts tangible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class LessonExample:
    """A concrete example using portfolio data."""

    ticker: str
    value: str
    interpretation: str


@dataclass
class DailyLesson:
    """A single learning topic for today."""

    topic: str
    concept: str  # One-sentence definition
    explanation: str  # 2-3 sentence explanation
    examples: list[LessonExample] = field(default_factory=list)
    takeaway: str = ""  # Actionable takeaway
    category: str = ""  # RISK / VALUATION / TECHNICAL / PORTFOLIO


# ---------------------------------------------------------------------------
# Topic generators — each returns a DailyLesson using live portfolio data
# ---------------------------------------------------------------------------


def _lesson_beta(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    examples = []
    for ticker in list(holdings.keys())[:3]:
        data = screener_data.get(ticker, {})
        beta = data.get("Beta", None)
        if beta is not None:
            if beta < 0.8:
                interp = "defensive — moves less than the market"
            elif beta > 1.2:
                interp = "aggressive — amplifies market moves"
            else:
                interp = "moves roughly in line with the market"
            examples.append(
                LessonExample(
                    ticker=ticker.replace(".NS", ""),
                    value=f"Beta = {beta:.2f}",
                    interpretation=interp,
                )
            )

    return DailyLesson(
        topic="Beta — Your Portfolio's Market Sensitivity",
        concept="Beta measures how much a stock moves relative to the overall market (Nifty 50).",
        explanation=(
            "A beta of 1.0 means the stock moves 1:1 with Nifty. "
            "Beta of 0.7 means if Nifty falls 10%, this stock typically falls only 7%. "
            "Beta of 1.3 means it falls 13%. For long-term investors, a portfolio beta "
            "of 0.8-1.0 balances growth with downside protection."
        ),
        examples=examples,
        takeaway="Check your portfolio beta in `diamond risk`. Below 1.0 means you're more protected in crashes.",
        category="RISK",
    )


def _lesson_alpha(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    examples = []
    for ticker in list(holdings.keys())[:3]:
        data = screener_data.get(ticker, {})
        alpha = data.get("Alpha", None)
        if alpha is not None:
            if alpha > 0.3:
                interp = "strong outperformer — generating excess returns"
            elif alpha > 0:
                interp = "slight outperformer"
            else:
                interp = "underperforming vs the market on a risk-adjusted basis"
            examples.append(
                LessonExample(
                    ticker=ticker.replace(".NS", ""),
                    value=f"Alpha = {alpha:.2f}",
                    interpretation=interp,
                )
            )

    return DailyLesson(
        topic="Alpha — Are Your Stocks Earning Their Keep?",
        concept="Alpha is the return a stock generates beyond what its risk level (beta) would predict.",
        explanation=(
            "If a stock has beta 1.0 and Nifty returned 12%, a stock returning 15% has alpha of 3%. "
            "Positive alpha means the stock is outperforming expectations. "
            "It's the value added beyond just riding the market wave."
        ),
        examples=examples,
        takeaway="Stocks with negative alpha for 2+ quarters are candidates for review in `diamond accumulate --review`.",
        category="PORTFOLIO",
    )


def _lesson_volatility(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    examples = []
    for ticker in list(holdings.keys())[:3]:
        data = screener_data.get(ticker, {})
        vol = data.get("Volatility", None)
        if vol is not None:
            daily_move = vol / (252**0.5) * 100
            if vol < 0.25:
                interp = f"low volatility — typical daily move: {daily_move:.1f}%"
            elif vol < 0.35:
                interp = f"moderate volatility — daily move: {daily_move:.1f}%"
            else:
                interp = f"high volatility — daily move: {daily_move:.1f}%, expect big swings"
            examples.append(
                LessonExample(
                    ticker=ticker.replace(".NS", ""),
                    value=f"Annual Vol = {vol:.0%}",
                    interpretation=interp,
                )
            )

    return DailyLesson(
        topic="Volatility — The Price of Returns",
        concept="Volatility is the standard deviation of returns — how much a stock's price typically swings.",
        explanation=(
            "A stock with 30% annual volatility will have typical daily moves of about 1.9%. "
            "Higher volatility isn't necessarily bad — it means bigger moves in both directions. "
            "But for long-term compounding, lower volatility stocks tend to compound more reliably "
            "because big drawdowns take disproportionately long to recover from."
        ),
        examples=examples,
        takeaway="A 50% drop requires a 100% gain to recover. Lower volatility = smoother compounding.",
        category="RISK",
    )


def _lesson_hurst(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    examples = []
    for ticker in list(holdings.keys())[:3]:
        data = screener_data.get(ticker, {})
        hurst = data.get("Hurst", None)
        if hurst is not None:
            if hurst > 0.55:
                interp = "trending — price movements tend to persist"
            elif hurst < 0.45:
                interp = "mean-reverting — tends to snap back after moves"
            else:
                interp = "random walk — no clear persistence pattern"
            examples.append(
                LessonExample(
                    ticker=ticker.replace(".NS", ""),
                    value=f"Hurst = {hurst:.2f}",
                    interpretation=interp,
                )
            )

    return DailyLesson(
        topic="Hurst Exponent — Does This Stock Trend?",
        concept="The Hurst exponent measures whether price movements tend to persist (trend) or reverse (mean-revert).",
        explanation=(
            "H > 0.5 means the stock trends — if it went up yesterday, it's more likely to go up today. "
            "H < 0.5 means mean reversion — moves tend to reverse. H = 0.5 is a pure random walk. "
            "For buy-and-hold investing, trending stocks (H > 0.5) are preferable because "
            "momentum works in your favor."
        ),
        examples=examples,
        takeaway="Diamond's quality score gives trending stocks (high Hurst) a bonus for this reason.",
        category="TECHNICAL",
    )


def _lesson_cagr(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    examples = []
    for ticker in list(holdings.keys())[:3]:
        data = screener_data.get(ticker, {})
        cagr = data.get("CAGR", None)
        if cagr is not None:
            # Show what 1L grows to in 10 years
            final_value = 100000 * (1 + cagr) ** 10
            examples.append(
                LessonExample(
                    ticker=ticker.replace(".NS", ""),
                    value=f"CAGR = {cagr:.0%}",
                    interpretation=f"1L invested 10 years ago would be {final_value / 100000:.1f}L today",
                )
            )

    return DailyLesson(
        topic="CAGR — The Only Return Metric That Matters",
        concept="CAGR (Compound Annual Growth Rate) is the steady annual return needed to grow from start to end value.",
        explanation=(
            "Unlike simple returns, CAGR accounts for compounding. "
            "15% CAGR doubles your money every ~5 years. 20% CAGR does it in ~3.8 years. "
            "For your 10-year horizon, even a 2% difference in CAGR compounds dramatically — "
            "15% turns 5L into 20L, while 17% turns it into 24L."
        ),
        examples=examples,
        takeaway="Focus on CAGR over short-term returns. Run `diamond backtest` to see historical CAGR.",
        category="PORTFOLIO",
    )


def _lesson_vix(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    return DailyLesson(
        topic="India VIX — The Fear Gauge",
        concept="VIX measures expected market volatility over the next 30 days, derived from option prices.",
        explanation=(
            "VIX below 13 = calm, above 20 = nervous, above 28 = panic. "
            "High VIX often means good buying opportunities because fear is priced in. "
            "Historically, investing when VIX is above 20 has generated better long-term returns "
            "than investing when VIX is below 13."
        ),
        examples=[],
        takeaway="Check VIX with `diamond pulse`. Don't fear high VIX — it often signals opportunity.",
        category="RISK",
    )


def _lesson_sector_diversification(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    from diamond.data.universe import get_sector

    sector_counts: dict[str, int] = {}
    for ticker in holdings:
        sector = get_sector(ticker)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    examples = []
    for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1])[:3]:
        if count >= 3:
            interp = "concentrated — consider if this is intentional"
        elif count == 2:
            interp = "moderate exposure"
        else:
            interp = "single stock exposure to this sector"
        examples.append(
            LessonExample(
                ticker=sector,
                value=f"{count} stocks",
                interpretation=interp,
            )
        )

    return DailyLesson(
        topic="Sector Diversification — Don't Put All Eggs in One Basket",
        concept="Spreading investments across sectors reduces the impact of sector-specific risks.",
        explanation=(
            "If you hold 5 IT stocks, a single IT sector downturn hits 5 positions at once. "
            "Diamond caps sectors at 4 stocks and 25% weight for this reason. "
            "True diversification means your stocks don't all fall together — "
            "check correlation with `diamond risk`."
        ),
        examples=examples,
        takeaway="Run `diamond accumulate --review` to check if any sector is over-concentrated.",
        category="PORTFOLIO",
    )


def _lesson_drawdown(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    return DailyLesson(
        topic="Drawdown — The Real Test of Your Strategy",
        concept="Drawdown is the peak-to-trough decline in your portfolio value.",
        explanation=(
            "A 20% drawdown means your portfolio dropped 20% from its highest point. "
            "Drawdowns are inevitable — Nifty has had 30%+ drawdowns in 2008, 2020. "
            "What matters is recovery time. A well-diversified low-beta portfolio "
            "typically recovers faster because it falls less."
        ),
        examples=[],
        takeaway="Diamond tracks your high-water mark automatically. Check with `diamond risk`.",
        category="RISK",
    )


def _lesson_position_sizing(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    return DailyLesson(
        topic="Position Sizing — How Much to Put in Each Stock",
        concept="Position sizing determines what percentage of your portfolio goes into each stock.",
        explanation=(
            "Diamond caps individual positions at 10% of portfolio. "
            "Too little (1-2%) and winners don't move the needle. "
            "Too much (15%+) and one bad stock can wreck your portfolio. "
            "The sweet spot is 5-10% per position with 15-20 total stocks."
        ),
        examples=[],
        takeaway="Diamond's accumulate strategy auto-sizes positions. Use `diamond accumulate --opportunities` to see sizing.",
        category="PORTFOLIO",
    )


def _lesson_quality_score(holdings: dict[str, int], screener_data: dict) -> DailyLesson:
    examples = []
    import pandas as pd

    from diamond.strategies.accumulate import compute_quality_score

    for ticker in list(holdings.keys())[:3]:
        data = screener_data.get(ticker, {})
        if data:
            row = pd.Series(data)
            score = compute_quality_score(row)
            if score >= 60:
                interp = "high quality — strong all-round metrics"
            elif score >= 35:
                interp = "moderate — some weaknesses"
            else:
                interp = "low quality — may need review"
            examples.append(
                LessonExample(
                    ticker=ticker.replace(".NS", ""),
                    value=f"Quality = {score:.0f}/100",
                    interpretation=interp,
                )
            )

    return DailyLesson(
        topic="Quality Score — Diamond's Stock Rating System",
        concept="Quality score is a 0-100 composite of CAGR (30%), Alpha (25%), Volatility (20%), Beta (15%), and Hurst (10%).",
        explanation=(
            "It captures what matters for long-term buy-and-hold: growth, risk-adjusted performance, "
            "steady compounding, market sensitivity, and trend persistence. "
            "Stocks scoring above 60 are strong candidates. Below 20 triggers a sell review."
        ),
        examples=examples,
        takeaway="Quality scores refresh with every screener run. Track yours with `diamond accumulate --review`.",
        category="PORTFOLIO",
    )


# All available lessons
_LESSON_GENERATORS = [
    _lesson_beta,
    _lesson_alpha,
    _lesson_volatility,
    _lesson_hurst,
    _lesson_cagr,
    _lesson_vix,
    _lesson_sector_diversification,
    _lesson_drawdown,
    _lesson_position_sizing,
    _lesson_quality_score,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_daily_lesson(
    strategy: str = "accumulate",
    topic_index: int | None = None,
) -> DailyLesson:
    """Get today's learning topic, personalized with portfolio data.

    Args:
        strategy: Which portfolio to use for examples.
        topic_index: Force a specific topic (0-based). None = rotate by day.

    Returns:
        DailyLesson with concept, explanation, and portfolio examples.
    """
    # Load holdings and screener data for examples
    holdings: dict[str, int] = {}
    screener_data: dict[str, dict] = {}

    try:
        from diamond.data.ledger import Ledger

        ledger = Ledger(strategy)
        holdings = ledger.get_holdings()
    except Exception:
        pass

    if holdings:
        try:
            from diamond.analysis.screener import screen

            df = screen()
            if not df.empty:
                for _, row in df.iterrows():
                    ticker = str(row["Ticker"])
                    if ticker in holdings:
                        screener_data[ticker] = row.to_dict()
        except Exception:
            pass

    # Pick lesson (rotate daily or use forced index)
    if topic_index is not None:
        idx = topic_index % len(_LESSON_GENERATORS)
    else:
        day_of_year = datetime.now().timetuple().tm_yday
        idx = day_of_year % len(_LESSON_GENERATORS)

    return _LESSON_GENERATORS[idx](holdings, screener_data)


def list_topics() -> list[str]:
    """Return all available lesson topics for the --list flag."""
    # Generate each lesson with empty data to get topic names
    topics = []
    for fn in _LESSON_GENERATORS:
        lesson = fn({}, {})
        topics.append(lesson.topic)
    return topics
