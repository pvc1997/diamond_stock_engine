"""Paper-to-live promotion workflow.

Compares paper portfolio performance against live (or initial capital),
generates a confidence assessment, and optionally promotes the paper
allocation to the real executor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from diamond.data.ledger import Ledger
from diamond.execution.paper import PAPER_SUFFIX, _get_current_prices

logger = logging.getLogger(__name__)


@dataclass
class PromotionReport:
    """Assessment of paper portfolio readiness for live trading."""

    strategy: str
    paper_nav: float
    paper_return_pct: float
    paper_trades: int
    paper_days_active: int
    live_nav: float | None  # None if no live portfolio exists
    live_return_pct: float | None
    outperformance_pct: float | None  # Paper return - live return
    confidence: str  # "high", "medium", "low"
    reasons: list[str]
    recommended: bool


# Minimum thresholds for promotion
_MIN_DAYS = 30  # At least 30 days of paper trading
_MIN_TRADES = 1  # At least 1 rebalance cycle
_MIN_RETURN = -5.0  # Paper return must be > -5%
_OUTPERFORM_BONUS = 2.0  # Paper should outperform live by at least 2%


def assess_promotion(strategy: str) -> PromotionReport:
    """Assess whether a paper portfolio is ready for live promotion.

    Checks:
    - Paper portfolio has enough history (>30 days)
    - Paper return is acceptable (>-5%)
    - Paper outperforms live (if live exists)
    - No critical risk signals

    Args:
        strategy: Base strategy name (not paper-suffixed).

    Returns:
        PromotionReport with assessment.
    """
    paper_name = f"{strategy}{PAPER_SUFFIX}"

    paper_ledger = Ledger(paper_name)
    paper_holdings = paper_ledger.get_holdings()

    if not paper_holdings:
        return PromotionReport(
            strategy=strategy,
            paper_nav=0,
            paper_return_pct=0,
            paper_trades=0,
            paper_days_active=0,
            live_nav=None,
            live_return_pct=None,
            outperformance_pct=None,
            confidence="low",
            reasons=["No paper portfolio found — run `diamond paper` first"],
            recommended=False,
        )

    # Get current prices for paper holdings
    all_tickers = list(paper_holdings.keys())
    current_prices = _get_current_prices(all_tickers)

    paper_nav = paper_ledger.get_portfolio_value(current_prices)
    paper_capital = paper_ledger.get_initial_capital()
    paper_return = ((paper_nav / paper_capital) - 1) * 100 if paper_capital > 0 else 0
    paper_trades = len(paper_ledger.get_trades())

    # Calculate days active
    first_trade = paper_ledger.get_trades()
    if first_trade:
        first_date = datetime.strptime(first_trade[0].timestamp, "%Y-%m-%d")
        days_active = (datetime.now() - first_date).days
    else:
        days_active = 0

    # Check live portfolio
    live_ledger = Ledger(strategy)
    live_holdings = live_ledger.get_holdings()
    live_nav = None
    live_return = None
    outperformance = None

    if live_holdings:
        live_tickers = list(live_holdings.keys())
        live_prices = _get_current_prices(live_tickers)
        live_nav = live_ledger.get_portfolio_value(live_prices)
        live_capital = live_ledger.get_initial_capital()
        live_return = ((live_nav / live_capital) - 1) * 100 if live_capital > 0 else 0
        outperformance = paper_return - live_return

    # Score confidence
    reasons: list[str] = []
    score = 0

    if days_active >= _MIN_DAYS:
        score += 1
        reasons.append(f"Paper portfolio active {days_active} days (min: {_MIN_DAYS})")
    else:
        reasons.append(f"Paper portfolio only {days_active} days old (need {_MIN_DAYS}+)")

    if paper_trades >= _MIN_TRADES:
        score += 1
        reasons.append(f"Completed {paper_trades} trade(s)")
    else:
        reasons.append(f"Only {paper_trades} trade(s) — need at least {_MIN_TRADES}")

    if paper_return > _MIN_RETURN:
        score += 1
        reasons.append(f"Paper return: {paper_return:+.2f}%")
    else:
        reasons.append(f"Paper return {paper_return:+.2f}% below {_MIN_RETURN}% threshold")

    if outperformance is not None:
        if outperformance >= _OUTPERFORM_BONUS:
            score += 1
            reasons.append(f"Outperforms live by {outperformance:+.2f}%")
        elif outperformance >= 0:
            reasons.append(f"Matches live ({outperformance:+.2f}%)")
        else:
            reasons.append(f"Underperforms live by {abs(outperformance):.2f}%")

    # Risk check
    try:
        from diamond.monitoring.risk import compute_risk_report

        report = compute_risk_report(paper_name, current_prices)
        critical = [s for s in report.signals if s.startswith("CRITICAL")]
        if critical:
            reasons.append(f"RISK: {len(critical)} critical signal(s) on paper portfolio")
        else:
            score += 1
            reasons.append("No critical risk signals")
    except Exception:
        reasons.append("Risk check unavailable")

    # Determine confidence
    if score >= 4:
        confidence = "high"
    elif score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    recommended = confidence == "high"

    return PromotionReport(
        strategy=strategy,
        paper_nav=round(paper_nav, 2),
        paper_return_pct=round(paper_return, 2),
        paper_trades=paper_trades,
        paper_days_active=days_active,
        live_nav=round(live_nav, 2) if live_nav is not None else None,
        live_return_pct=round(live_return, 2) if live_return is not None else None,
        outperformance_pct=round(outperformance, 2) if outperformance is not None else None,
        confidence=confidence,
        reasons=reasons,
        recommended=recommended,
    )


def promote(strategy: str, capital: float | None = None) -> dict:
    """Promote paper portfolio allocation to live execution.

    Reads the paper portfolio's current holdings and converts them
    to a target allocation dict for the real executor.

    Args:
        strategy: Base strategy name.
        capital: Capital for live portfolio (defaults to paper's initial capital).

    Returns:
        Target allocation dict {ticker: amount_inr} ready for executor.execute().
    """
    paper_name = f"{strategy}{PAPER_SUFFIX}"
    paper_ledger = Ledger(paper_name)
    paper_holdings = paper_ledger.get_holdings()

    if not paper_holdings:
        return {}

    current_prices = _get_current_prices(list(paper_holdings.keys()))

    # Calculate paper weights
    paper_nav = paper_ledger.get_portfolio_value(current_prices)
    if paper_nav <= 0:
        return {}

    weights: dict[str, float] = {}
    for ticker, shares in paper_holdings.items():
        price = current_prices.get(ticker, 0)
        if price > 0:
            weights[ticker] = (shares * price) / paper_nav

    # Convert weights to allocation at the target capital
    if capital is None:
        capital = paper_ledger.get_initial_capital()

    allocation = {ticker: weight * capital for ticker, weight in weights.items()}
    return allocation
