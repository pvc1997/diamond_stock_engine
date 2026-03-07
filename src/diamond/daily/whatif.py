"""What-if scenario engine — interactive portfolio stress testing.

Answers questions like:
- "What if Nifty drops 10%?"
- "What if I add 50K today?"
- "What if I had bought X instead of Y?"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StockImpact:
    """Impact on a single stock in a scenario."""

    ticker: str
    current_price: float
    projected_price: float
    shares: int
    current_value: float
    projected_value: float
    change_inr: float
    change_pct: float


@dataclass
class ScenarioResult:
    """Result of a what-if scenario."""

    scenario: str  # Description
    current_nav: float
    projected_nav: float
    change_inr: float
    change_pct: float
    stock_impacts: list[StockImpact] = field(default_factory=list)
    worst_hit: str = ""  # Most affected stock
    best_protected: str = ""  # Least affected stock
    commentary: str = ""


@dataclass
class AddCashResult:
    """Result of add-cash what-if."""

    amount: float
    current_nav: float
    projected_nav: float  # NAV + new amount
    would_buy: list[dict] = field(default_factory=list)  # {ticker, shares, amount}
    new_positions_after: int = 0


@dataclass
class AlternativeResult:
    """What if you had bought X instead of Y."""

    held_ticker: str
    held_return_pct: float
    held_value: float
    alt_ticker: str
    alt_return_pct: float
    alt_value: float
    difference_inr: float
    difference_pct: float
    verdict: str  # "Better off" / "Worse off"


# ---------------------------------------------------------------------------
# Market crash scenario
# ---------------------------------------------------------------------------


def simulate_market_crash(
    strategy: str,
    crash_pct: float,
    current_prices: dict[str, float] | None = None,
) -> ScenarioResult:
    """What if the market drops/rises by X%?

    Uses each stock's beta to estimate individual impact.

    Args:
        strategy: Portfolio to stress test.
        crash_pct: Market change in % (e.g., -10 for 10% crash, +5 for rally).
        current_prices: Current prices. Fetched if None.

    Returns:
        ScenarioResult with per-stock breakdown.
    """
    from diamond.data.ledger import Ledger

    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    if not holdings:
        return ScenarioResult(
            scenario=f"Nifty {crash_pct:+.1f}%",
            current_nav=ledger.get_cash(),
            projected_nav=ledger.get_cash(),
            change_inr=0,
            change_pct=0,
            commentary="No holdings to stress test.",
        )

    # Fetch prices if needed
    if current_prices is None:
        current_prices = _fetch_portfolio_prices(list(holdings.keys()))

    # Get betas from screener
    betas = _get_betas(list(holdings.keys()))

    cash = ledger.get_cash()
    market_change = crash_pct / 100

    impacts: list[StockImpact] = []
    total_current = 0.0
    total_projected = 0.0

    for ticker, shares in holdings.items():
        price = current_prices.get(ticker, 0)
        if price <= 0:
            continue

        beta = betas.get(ticker, 1.0)
        stock_change = market_change * beta
        projected_price = price * (1 + stock_change)

        current_value = shares * price
        projected_value = shares * projected_price
        change_inr = projected_value - current_value

        total_current += current_value
        total_projected += projected_value

        impacts.append(
            StockImpact(
                ticker=ticker,
                current_price=round(price, 2),
                projected_price=round(projected_price, 2),
                shares=shares,
                current_value=round(current_value, 0),
                projected_value=round(projected_value, 0),
                change_inr=round(change_inr, 0),
                change_pct=round(stock_change * 100, 2),
            )
        )

    # Sort by impact
    impacts.sort(key=lambda x: x.change_inr)

    current_nav = total_current + cash
    projected_nav = total_projected + cash
    nav_change = projected_nav - current_nav
    nav_change_pct = (nav_change / current_nav * 100) if current_nav > 0 else 0

    worst = impacts[0].ticker.replace(".NS", "") if impacts else ""
    best = impacts[-1].ticker.replace(".NS", "") if impacts else ""

    direction = "drops" if crash_pct < 0 else "rises"
    commentary = (
        f"If Nifty {direction} {abs(crash_pct):.0f}%, your portfolio would "
        f"{'lose' if nav_change < 0 else 'gain'} {abs(nav_change):,.0f} INR "
        f"({nav_change_pct:+.1f}%). "
    )
    if crash_pct < 0:
        avg_beta = sum(betas.get(t, 1) for t in holdings) / len(holdings)
        commentary += f"Portfolio beta ~{avg_beta:.2f} provides {'cushion' if avg_beta < 0.9 else 'moderate' if avg_beta < 1.1 else 'no'} downside protection."
    else:
        commentary += "Cash is uninvested and doesn't participate in the rally."

    return ScenarioResult(
        scenario=f"Nifty {crash_pct:+.1f}%",
        current_nav=round(current_nav, 0),
        projected_nav=round(projected_nav, 0),
        change_inr=round(nav_change, 0),
        change_pct=round(nav_change_pct, 2),
        stock_impacts=impacts,
        worst_hit=worst,
        best_protected=best,
        commentary=commentary,
    )


# ---------------------------------------------------------------------------
# Add cash scenario
# ---------------------------------------------------------------------------


def simulate_add_cash(
    strategy: str,
    amount: float,
) -> AddCashResult:
    """What if I add X amount today?

    Shows what the accumulate strategy would buy.

    Args:
        strategy: Portfolio to simulate.
        amount: Amount in INR to add.

    Returns:
        AddCashResult with projected purchases.
    """
    from diamond.data.ledger import Ledger
    from diamond.strategies.accumulate import plan_accumulation

    ledger = Ledger(strategy)
    current_cash = ledger.get_cash()
    holdings = ledger.get_holdings()

    current_nav = ledger.get_portfolio_value(_fetch_portfolio_prices(list(holdings.keys())) if holdings else {})

    # Plan what we'd buy with the extra cash
    plan = plan_accumulation(
        strategy,
        available_cash=current_cash + amount,
        market_verdict="WAIT",
    )

    would_buy = []
    for opp in plan.opportunities:
        would_buy.append(
            {
                "ticker": opp.ticker.replace(".NS", ""),
                "amount": round(opp.suggested_amount, 0),
                "quality": opp.quality_score,
                "reason": opp.reason,
            }
        )

    return AddCashResult(
        amount=amount,
        current_nav=round(current_nav, 0),
        projected_nav=round(current_nav + amount, 0),
        would_buy=would_buy,
        new_positions_after=plan.total_positions_after,
    )


# ---------------------------------------------------------------------------
# Alternative stock comparison
# ---------------------------------------------------------------------------


def simulate_alternative(
    strategy: str,
    held_ticker: str,
    alt_ticker: str,
    lookback_days: int = 90,
) -> AlternativeResult:
    """What if I had bought X instead of Y?

    Compares returns over a lookback period.

    Args:
        strategy: Portfolio (for held ticker shares/value).
        held_ticker: Ticker you currently hold.
        alt_ticker: Alternative ticker to compare.
        lookback_days: How far back to compare.

    Returns:
        AlternativeResult with comparison.
    """
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices

    # Ensure .NS suffix
    if not held_ticker.endswith(".NS"):
        held_ticker += ".NS"
    if not alt_ticker.endswith(".NS"):
        alt_ticker += ".NS"

    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()
    shares = holdings.get(held_ticker, 0)
    avg_price = ledger.get_avg_price(held_ticker)

    # Download prices for both
    prices_df = download_prices(
        [held_ticker, alt_ticker],
        period_days=lookback_days,
        use_cache=True,
    )

    if prices_df.empty:
        return AlternativeResult(
            held_ticker=held_ticker,
            held_return_pct=0,
            held_value=0,
            alt_ticker=alt_ticker,
            alt_return_pct=0,
            alt_value=0,
            difference_inr=0,
            difference_pct=0,
            verdict="No data",
        )

    # Compute returns
    held_series = prices_df[held_ticker].dropna() if held_ticker in prices_df.columns else None
    alt_series = prices_df[alt_ticker].dropna() if alt_ticker in prices_df.columns else None

    if held_series is None or alt_series is None or len(held_series) < 2 or len(alt_series) < 2:
        return AlternativeResult(
            held_ticker=held_ticker,
            held_return_pct=0,
            held_value=0,
            alt_ticker=alt_ticker,
            alt_return_pct=0,
            alt_value=0,
            difference_inr=0,
            difference_pct=0,
            verdict="Insufficient data",
        )

    held_start = float(held_series.iloc[0])
    held_end = float(held_series.iloc[-1])
    alt_start = float(alt_series.iloc[0])
    alt_end = float(alt_series.iloc[-1])

    held_return = (held_end - held_start) / held_start * 100 if held_start > 0 else 0
    alt_return = (alt_end - alt_start) / alt_start * 100 if alt_start > 0 else 0

    # Value comparison: if you'd invested the same amount
    invested = shares * avg_price if shares > 0 and avg_price > 0 else 50000
    held_value = invested * (1 + held_return / 100)
    alt_value = invested * (1 + alt_return / 100)
    diff_inr = alt_value - held_value
    diff_pct = alt_return - held_return

    verdict = "Better off with current" if diff_inr < 0 else "Would have been better"

    return AlternativeResult(
        held_ticker=held_ticker.replace(".NS", ""),
        held_return_pct=round(held_return, 2),
        held_value=round(held_value, 0),
        alt_ticker=alt_ticker.replace(".NS", ""),
        alt_return_pct=round(alt_return, 2),
        alt_value=round(alt_value, 0),
        difference_inr=round(diff_inr, 0),
        difference_pct=round(diff_pct, 2),
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_portfolio_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for tickers."""
    prices: dict[str, float] = {}
    if not tickers:
        return prices
    try:
        from diamond.data.market import download_prices

        df = download_prices(tickers, period_days=5, use_cache=True)
        if not df.empty:
            for col in df.columns:
                series = df[col].dropna()
                if len(series) > 0:
                    prices[col] = float(series.iloc[-1])
    except Exception:
        pass
    return prices


def _get_betas(tickers: list[str]) -> dict[str, float]:
    """Get beta values for tickers from screener cache."""
    betas: dict[str, float] = {}
    try:
        from diamond.analysis.screener import screen

        df = screen()
        if not df.empty:
            for _, row in df.iterrows():
                t = str(row["Ticker"])
                if t in tickers:
                    betas[t] = float(row["Beta"])
    except Exception:
        pass
    # Default to 1.0 for missing
    for t in tickers:
        if t not in betas:
            betas[t] = 1.0
    return betas
