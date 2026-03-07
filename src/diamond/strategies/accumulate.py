"""Accumulate strategy - long-term capital deployment with active review.

Designed for fresh capital deployment over a 10-year horizon.
Key features:
- Gradual deployment: deploys in tranches, not all at once
- Market-aware: adjusts deployment pace based on market conditions
- Opportunity-based: ranks by long-term quality score
- Active review: flags deteriorating holdings, suggests swaps
- Capital recycling: sell proceeds go back into deploy pool
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from diamond.data.ledger import Ledger
from diamond.data.universe import get_sector
from diamond.strategies.constraints import apply_sector_cap

logger = logging.getLogger(__name__)

# Deployment config
MAX_DEPLOY_PCT_NORMAL = 0.30  # Deploy up to 30% of available cash normally
MAX_DEPLOY_PCT_DEPLOY = 0.50  # Deploy up to 50% when market pulse says DEPLOY
MAX_DEPLOY_PCT_DEFENSIVE = 0.15  # Deploy only 15% when DEFENSIVE
MIN_DEPLOY_AMOUNT = 5000  # Don't deploy less than 5K INR
MAX_POSITIONS = 20  # Max total positions in accumulate portfolio
MAX_POSITION_WEIGHT = 0.10  # Max 10% in any single stock
MIN_POSITION_SIZE = 10000  # Min position size 10K INR

# Review config
QUALITY_SELL_THRESHOLD = 20  # Flag sell when quality drops below this
QUALITY_WARN_THRESHOLD = 35  # Flag warning when quality drops below this
STOP_LOSS_PCT = 0.15  # Flag sell when stock drops 15% from avg price
REVIEW_FREQUENCY_DAYS = 90  # Quarterly review cadence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Opportunity:
    """A ranked buy opportunity."""

    ticker: str
    sector: str
    quality_score: float  # Composite quality score (0-100)
    suggested_amount: float  # Suggested INR amount to deploy
    reason: str  # Human-readable reason
    alpha: float
    cagr: float
    beta: float
    volatility: float


@dataclass(frozen=True)
class SellSignal:
    """A sell signal for a deteriorating holding."""

    ticker: str
    sector: str
    shares: int
    avg_price: float
    current_price: float
    pnl_pct: float  # Current P&L percentage
    quality_score: float  # Current quality score
    signal_type: str  # "QUALITY_DROP", "STOP_LOSS", "BOTH"
    severity: str  # "SELL", "WATCH"
    reason: str


@dataclass(frozen=True)
class SwapSuggestion:
    """Sell X, buy Y suggestion."""

    sell_ticker: str
    sell_reason: str
    sell_quality: float
    sell_pnl_pct: float
    buy_ticker: str
    buy_reason: str
    buy_quality: float
    freed_capital: float  # Estimated capital freed from sell
    quality_gain: float  # buy_quality - sell_quality


@dataclass
class AccumulatePlan:
    """Output of accumulate planning."""

    available_cash: float
    deploy_budget: float  # How much to deploy this cycle
    market_verdict: str  # DEPLOY / WAIT / DEFENSIVE
    deploy_pct: float  # What % of cash to deploy
    opportunities: list[Opportunity]
    existing_positions: int
    total_positions_after: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    """Output of portfolio review."""

    strategy: str
    review_date: str
    holdings_reviewed: int
    sell_signals: list[SellSignal]
    swap_suggestions: list[SwapSuggestion]
    healthy_count: int  # Holdings with no issues
    watch_count: int  # Holdings to watch (quality declining)
    sell_count: int  # Holdings flagged for sell
    days_since_last_review: int | None
    next_review_due: bool
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


def compute_quality_score(row: pd.Series) -> float:
    """Compute a composite long-term quality score (0-100).

    Weights:
    - CAGR contribution: 30% (growth is most important for 10yr horizon)
    - Alpha contribution: 25% (risk-adjusted outperformance)
    - Low volatility bonus: 20% (steadier compounding)
    - Beta sweetspot bonus: 15% (0.7-1.1 range ideal for long-term)
    - Hurst trending bonus: 10% (persistent trends = better entry)
    """
    score = 0.0

    # CAGR: 0 to 30 points (CAGR of 30%+ gets full marks)
    cagr = float(row.get("CAGR", 0) or 0)
    score += min(30, max(0, cagr * 100))

    # Alpha: 0 to 25 points (alpha of 0.5+ gets full marks)
    alpha = float(row.get("Alpha", 0) or 0)
    score += min(25, max(0, alpha * 50))

    # Low volatility: 0 to 20 points (vol of 15% gets full marks, 40%+ gets 0)
    vol = float(row.get("Volatility", 0.30) or 0.30)
    if vol > 0:
        vol_score = max(0, (0.40 - vol) / 0.25) * 20
        score += min(20, vol_score)

    # Beta sweetspot: 0 to 15 points (0.7-1.1 is ideal)
    beta = float(row.get("Beta", 1.0) or 1.0)
    if 0.7 <= beta <= 1.1:
        score += 15
    elif 0.5 <= beta <= 1.3:
        score += 8
    else:
        score += 3

    # Hurst trending: 0 to 10 points (> 0.5 means trending)
    hurst = float(row.get("Hurst", 0.5) or 0.5)
    if hurst > 0.5:
        score += min(10, (hurst - 0.5) * 40)

    return round(min(100, max(0, score)), 1)


# ---------------------------------------------------------------------------
# Market verdict helpers
# ---------------------------------------------------------------------------


def _get_market_verdict() -> str:
    """Get market pulse verdict, defaulting to WAIT."""
    try:
        from diamond.monitoring.market_pulse import get_market_pulse

        pulse = get_market_pulse()
        return pulse.verdict
    except Exception:
        return "WAIT"


def _get_deploy_pct(verdict: str) -> float:
    """Determine deployment percentage based on market conditions."""
    if verdict == "DEPLOY":
        return MAX_DEPLOY_PCT_DEPLOY
    elif verdict == "DEFENSIVE":
        return MAX_DEPLOY_PCT_DEFENSIVE
    return MAX_DEPLOY_PCT_NORMAL


# ---------------------------------------------------------------------------
# Review & sell signals
# ---------------------------------------------------------------------------


def review_holdings(
    strategy: str,
    current_prices: dict[str, float] | None = None,
    screener_df: pd.DataFrame | None = None,
) -> ReviewReport:
    """Review current holdings for quality deterioration and stop-loss.

    Args:
        strategy: Strategy name (ledger lookup).
        current_prices: Current prices {ticker: price}. Fetched if None.
        screener_df: Pre-computed screener data. Runs screener if None.

    Returns:
        ReviewReport with sell signals and swap suggestions.
    """
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()
    today = datetime.now().strftime("%Y-%m-%d")

    # Days since last review
    last_rebalance = ledger.get_last_rebalance()
    days_since: int | None = None
    next_review_due = True
    if last_rebalance:
        last_dt = datetime.strptime(last_rebalance, "%Y-%m-%d")
        days_since = (datetime.now() - last_dt).days
        next_review_due = days_since >= REVIEW_FREQUENCY_DAYS

    if not holdings:
        return ReviewReport(
            strategy=strategy,
            review_date=today,
            holdings_reviewed=0,
            sell_signals=[],
            swap_suggestions=[],
            healthy_count=0,
            watch_count=0,
            sell_count=0,
            days_since_last_review=days_since,
            next_review_due=next_review_due,
        )

    # Fetch current prices if not provided
    if current_prices is None:
        current_prices = _fetch_prices(list(holdings.keys()))

    # Get screener data for quality scoring
    if screener_df is None:
        from diamond.analysis.screener import screen

        screener_df = screen()

    # Compute quality for held tickers
    quality_map: dict[str, float] = {}
    if not screener_df.empty:
        screener_df = screener_df.copy()
        screener_df["_quality"] = screener_df.apply(compute_quality_score, axis=1)
        for _, row in screener_df.iterrows():
            quality_map[str(row["Ticker"])] = float(row["_quality"])

    # Scan holdings for signals
    sell_signals: list[SellSignal] = []
    healthy = 0
    watch = 0
    sell = 0

    for ticker, shares in holdings.items():
        avg_price = ledger.get_avg_price(ticker)
        cur_price = current_prices.get(ticker, 0)
        quality = quality_map.get(ticker, 50.0)  # Default to 50 if not in screener

        # P&L
        pnl_pct = ((cur_price - avg_price) / avg_price * 100) if avg_price > 0 and cur_price > 0 else 0

        # Check signals
        is_quality_drop = quality < QUALITY_SELL_THRESHOLD
        is_quality_warn = quality < QUALITY_WARN_THRESHOLD and not is_quality_drop
        is_stop_loss = avg_price > 0 and cur_price > 0 and (avg_price - cur_price) / avg_price >= STOP_LOSS_PCT

        if is_quality_drop and is_stop_loss:
            signal_type = "BOTH"
            severity = "SELL"
            reason = f"Quality={quality:.0f} (below {QUALITY_SELL_THRESHOLD}) + stop-loss ({pnl_pct:+.1f}%)"
        elif is_quality_drop:
            signal_type = "QUALITY_DROP"
            severity = "SELL"
            reason = f"Quality dropped to {quality:.0f} (threshold: {QUALITY_SELL_THRESHOLD})"
        elif is_stop_loss:
            signal_type = "STOP_LOSS"
            severity = "SELL"
            reason = f"Stop-loss triggered: {pnl_pct:+.1f}% (threshold: -{STOP_LOSS_PCT:.0%})"
        elif is_quality_warn:
            signal_type = "QUALITY_DROP"
            severity = "WATCH"
            reason = f"Quality declining: {quality:.0f} (watch threshold: {QUALITY_WARN_THRESHOLD})"
        else:
            healthy += 1
            continue

        if severity == "SELL":
            sell += 1
        else:
            watch += 1

        sell_signals.append(
            SellSignal(
                ticker=ticker,
                sector=get_sector(ticker),
                shares=shares,
                avg_price=round(avg_price, 2),
                current_price=round(cur_price, 2),
                pnl_pct=round(pnl_pct, 2),
                quality_score=quality,
                signal_type=signal_type,
                severity=severity,
                reason=reason,
            )
        )

    # Generate swap suggestions for SELL signals
    swap_suggestions = _generate_swaps(
        sell_signals,
        holdings,
        quality_map,
        screener_df,
        current_prices,
    )

    return ReviewReport(
        strategy=strategy,
        review_date=today,
        holdings_reviewed=len(holdings),
        sell_signals=sell_signals,
        swap_suggestions=swap_suggestions,
        healthy_count=healthy,
        watch_count=watch,
        sell_count=sell,
        days_since_last_review=days_since,
        next_review_due=next_review_due,
    )


def _generate_swaps(
    sell_signals: list[SellSignal],
    holdings: dict[str, int],
    quality_map: dict[str, float],
    screener_df: pd.DataFrame,
    current_prices: dict[str, float],
) -> list[SwapSuggestion]:
    """Generate swap suggestions: sell deteriorated, buy better alternatives."""
    sells = [s for s in sell_signals if s.severity == "SELL"]
    if not sells or screener_df.empty:
        return []

    # Find high-quality candidates not currently held
    held_tickers = set(holdings.keys())
    screener_with_q = screener_df.copy()
    if "_quality" not in screener_with_q.columns:
        screener_with_q["_quality"] = screener_with_q.apply(compute_quality_score, axis=1)

    candidates = pd.DataFrame(
        screener_with_q[
            (~screener_with_q["Ticker"].isin(list(held_tickers)))
            & (screener_with_q["_quality"] > QUALITY_WARN_THRESHOLD)
            & (screener_with_q["Alpha"] > 0)
            & (screener_with_q["CAGR"] > 0.10)
        ]
    ).sort_values("_quality", ascending=False)  # type: ignore[call-overload]

    if candidates.empty:
        return []

    # Apply sector cap to candidates
    candidate_tickers = apply_sector_cap(candidates["Ticker"].tolist())

    swaps: list[SwapSuggestion] = []
    used_buys: set[str] = set()

    for signal in sells:
        # Find best unused replacement
        best_buy = None
        for ticker in candidate_tickers:
            if ticker in used_buys:
                continue
            row = candidates[candidates["Ticker"] == ticker]
            if row.empty:
                continue
            best_buy = row.iloc[0]
            used_buys.add(ticker)
            break

        if best_buy is None:
            continue

        buy_quality = float(best_buy["_quality"])
        freed_capital = signal.shares * signal.current_price if signal.current_price > 0 else 0

        swaps.append(
            SwapSuggestion(
                sell_ticker=signal.ticker,
                sell_reason=signal.reason,
                sell_quality=signal.quality_score,
                sell_pnl_pct=signal.pnl_pct,
                buy_ticker=best_buy["Ticker"],
                buy_reason=(
                    f"Quality={buy_quality:.0f}, CAGR={float(best_buy['CAGR']):.0%}, "
                    f"Alpha={float(best_buy['Alpha']):.2f}"
                ),
                buy_quality=buy_quality,
                freed_capital=round(freed_capital, 0),
                quality_gain=round(buy_quality - signal.quality_score, 1),
            )
        )

    return swaps


def execute_review_sells(
    strategy: str,
    review: ReviewReport,
    dry_run: bool = False,
) -> dict:
    """Execute sell orders from review signals.

    Only sells holdings flagged with severity="SELL".
    Freed capital stays as cash in the ledger for future deployment.

    Args:
        strategy: Strategy name.
        review: ReviewReport from review_holdings().
        dry_run: Preview without executing.

    Returns:
        Execution summary dict.
    """
    from diamond.data.ledger import Trade
    from diamond.execution.costs import calculate_costs
    from diamond.execution.executor import _record_to_order_book

    sells_to_execute = [s for s in review.sell_signals if s.severity == "SELL"]
    if not sells_to_execute:
        return {"status": "no_sells", "trades": 0}

    ledger = Ledger(strategy)
    today = datetime.now().strftime("%Y-%m-%d")

    # Fetch fresh prices
    prices = _fetch_prices([s.ticker for s in sells_to_execute])

    trades: list[dict] = []

    for signal in sells_to_execute:
        price = prices.get(signal.ticker, signal.current_price)
        if not price or price <= 0:
            continue

        value = signal.shares * price

        trade_dict = {
            "ticker": signal.ticker,
            "action": "SELL",
            "shares": signal.shares,
            "price": price,
            "rationale": f"Review: {signal.reason}",
        }

        if dry_run:
            trades.append(trade_dict)
            logger.info(f"[DRY RUN] SELL {signal.shares} {signal.ticker} @ {price:.2f} = {value:,.0f}")
            continue

        costs = calculate_costs("SELL", value)
        trade = Trade(
            timestamp=today,
            action="SELL",
            ticker=signal.ticker,
            shares=signal.shares,
            price=price,
            total_cost=costs.total,
            rationale=f"Review: {signal.reason}",
        )
        ledger.record_trade(trade)
        trades.append(trade_dict)
        logger.info(f"SELL {signal.shares} {signal.ticker} @ {price:.2f} = {value:,.0f} (cost: {costs.total:.2f})")

    if trades:
        status = "PENDING" if dry_run else "FILLED"
        _record_to_order_book(strategy, trades, status=status)

    if dry_run:
        total_freed = sum(t["shares"] * t["price"] for t in trades)
        return {
            "status": "dry_run",
            "trades": len(trades),
            "trade_list": trades,
            "total_freed": round(total_freed, 0),
        }

    return {
        "status": "executed",
        "trades": len(trades),
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }


def execute_swaps(
    strategy: str,
    review: ReviewReport,
    dry_run: bool = False,
) -> dict:
    """Execute swap suggestions: sell deteriorated, buy replacements.

    Args:
        strategy: Strategy name.
        review: ReviewReport from review_holdings().
        dry_run: Preview without executing.

    Returns:
        Execution summary dict.
    """
    from diamond.data.ledger import Trade
    from diamond.execution.costs import calculate_costs
    from diamond.execution.executor import _record_to_order_book

    if not review.swap_suggestions:
        return {"status": "no_swaps", "trades": 0}

    ledger = Ledger(strategy)
    today = datetime.now().strftime("%Y-%m-%d")
    holdings = ledger.get_holdings()

    # Fetch prices for all tickers involved
    all_tickers = []
    for swap in review.swap_suggestions:
        all_tickers.extend([swap.sell_ticker, swap.buy_ticker])
    prices = _fetch_prices(list(set(all_tickers)))

    trades: list[dict] = []
    sells_done = 0
    buys_done = 0

    for swap in review.swap_suggestions:
        sell_price = prices.get(swap.sell_ticker, 0)
        buy_price = prices.get(swap.buy_ticker, 0)

        if not sell_price or sell_price <= 0 or not buy_price or buy_price <= 0:
            continue

        sell_shares = holdings.get(swap.sell_ticker, 0)
        if sell_shares <= 0:
            continue

        sell_value = sell_shares * sell_price

        # Sell trade
        sell_dict = {
            "ticker": swap.sell_ticker,
            "action": "SELL",
            "shares": sell_shares,
            "price": sell_price,
            "rationale": f"Swap out: {swap.sell_reason}",
        }

        # Buy trade — use freed capital minus costs
        sell_costs = calculate_costs("SELL", sell_value)
        buy_budget = sell_value - sell_costs.total
        buy_shares = int(buy_budget / buy_price)

        if buy_shares <= 0:
            continue

        buy_value = buy_shares * buy_price
        buy_dict = {
            "ticker": swap.buy_ticker,
            "action": "BUY",
            "shares": buy_shares,
            "price": buy_price,
            "rationale": f"Swap in: {swap.buy_reason}",
        }

        if dry_run:
            trades.extend([sell_dict, buy_dict])
            logger.info(
                f"[DRY RUN] SWAP {swap.sell_ticker} (Q={swap.sell_quality:.0f}) "
                f"-> {swap.buy_ticker} (Q={swap.buy_quality:.0f}), "
                f"quality gain: +{swap.quality_gain:.0f}"
            )
            sells_done += 1
            buys_done += 1
            continue

        # Execute sell
        sell_trade = Trade(
            timestamp=today,
            action="SELL",
            ticker=swap.sell_ticker,
            shares=sell_shares,
            price=sell_price,
            total_cost=sell_costs.total,
            rationale=f"Swap out: {swap.sell_reason}",
        )
        ledger.record_trade(sell_trade)
        sells_done += 1

        # Execute buy
        buy_costs = calculate_costs("BUY", buy_value)
        buy_trade = Trade(
            timestamp=today,
            action="BUY",
            ticker=swap.buy_ticker,
            shares=buy_shares,
            price=buy_price,
            total_cost=buy_costs.total,
            rationale=f"Swap in: {swap.buy_reason}",
        )
        ledger.record_trade(buy_trade)
        buys_done += 1

        trades.extend([sell_dict, buy_dict])
        logger.info(
            f"SWAP {swap.sell_ticker} -> {swap.buy_ticker}, quality: {swap.sell_quality:.0f} -> {swap.buy_quality:.0f}"
        )

    if trades:
        status = "PENDING" if dry_run else "FILLED"
        _record_to_order_book(strategy, trades, status=status)

    if dry_run:
        return {
            "status": "dry_run",
            "trades": len(trades),
            "sells": sells_done,
            "buys": buys_done,
            "trade_list": trades,
        }

    return {
        "status": "executed",
        "trades": len(trades),
        "sells": sells_done,
        "buys": buys_done,
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }


# ---------------------------------------------------------------------------
# Price helper
# ---------------------------------------------------------------------------


def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for tickers."""
    from diamond.data import market

    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception:
            logger.warning(f"Price fetch failed for {ticker}")
    return prices


# ---------------------------------------------------------------------------
# Buy planning (unchanged from original)
# ---------------------------------------------------------------------------


def plan_accumulation(
    strategy: str,
    available_cash: float | None = None,
    market_verdict: str | None = None,
    screener_df: pd.DataFrame | None = None,
    max_positions: int = MAX_POSITIONS,
) -> AccumulatePlan:
    """Plan what to buy with available cash.

    Args:
        strategy: Strategy name (ledger lookup).
        available_cash: Override available cash (otherwise reads from ledger).
        market_verdict: Override market verdict (otherwise fetches live).
        screener_df: Pre-computed screener data (otherwise runs screen).
        max_positions: Maximum portfolio positions.

    Returns:
        AccumulatePlan with ranked opportunities.
    """
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    # Determine available cash
    if available_cash is None:
        available_cash = ledger.get_cash()

    # Determine market conditions
    if market_verdict is None:
        market_verdict = _get_market_verdict()

    deploy_pct = _get_deploy_pct(market_verdict)
    deploy_budget = available_cash * deploy_pct

    warnings: list[str] = []

    if deploy_budget < MIN_DEPLOY_AMOUNT:
        warnings.append(f"Deploy budget ({deploy_budget:,.0f}) below minimum ({MIN_DEPLOY_AMOUNT:,.0f})")
        return AccumulatePlan(
            available_cash=available_cash,
            deploy_budget=deploy_budget,
            market_verdict=market_verdict,
            deploy_pct=deploy_pct,
            opportunities=[],
            existing_positions=len(holdings),
            total_positions_after=len(holdings),
            warnings=warnings,
        )

    # Get screener data
    if screener_df is None:
        from diamond.analysis.screener import screen

        screener_df = screen()

    if screener_df.empty:
        warnings.append("Screener returned no data")
        return AccumulatePlan(
            available_cash=available_cash,
            deploy_budget=deploy_budget,
            market_verdict=market_verdict,
            deploy_pct=deploy_pct,
            opportunities=[],
            existing_positions=len(holdings),
            total_positions_after=len(holdings),
            warnings=warnings,
        )

    # Compute quality scores
    screener_df = screener_df.copy()
    screener_df["_quality"] = screener_df.apply(compute_quality_score, axis=1)

    # Filter: only positive alpha and reasonable quality
    candidates = pd.DataFrame(
        screener_df[(screener_df["Alpha"] > 0) & (screener_df["CAGR"] > 0.10) & (screener_df["_quality"] > 30)]
    ).sort_values("_quality", ascending=False)  # type: ignore[call-overload]

    if candidates.empty:
        warnings.append("No candidates pass quality filters")
        return AccumulatePlan(
            available_cash=available_cash,
            deploy_budget=deploy_budget,
            market_verdict=market_verdict,
            deploy_pct=deploy_pct,
            opportunities=[],
            existing_positions=len(holdings),
            total_positions_after=len(holdings),
            warnings=warnings,
        )

    # Apply sector cap
    tickers_ordered = apply_sector_cap(candidates["Ticker"].tolist())

    # How many new positions can we add?
    current_count = len(holdings)
    slots_available = max(0, max_positions - current_count)

    if slots_available == 0:
        warnings.append(f"Already at max positions ({max_positions})")
        # Can still add to existing positions -- filter to held tickers
        tickers_ordered = [t for t in tickers_ordered if t in holdings]
        if not tickers_ordered:
            return AccumulatePlan(
                available_cash=available_cash,
                deploy_budget=deploy_budget,
                market_verdict=market_verdict,
                deploy_pct=deploy_pct,
                opportunities=[],
                existing_positions=current_count,
                total_positions_after=current_count,
                warnings=warnings,
            )

    # Build opportunities
    # Mix: prefer adding to existing high-quality positions + some new entries
    existing_tickers = [t for t in tickers_ordered if t in holdings]
    new_tickers = [t for t in tickers_ordered if t not in holdings][:slots_available]

    # Prioritize: top existing + top new, interleaved
    ordered = []
    ei, ni = 0, 0
    while len(ordered) < 10 and (ei < len(existing_tickers) or ni < len(new_tickers)):
        if ei < len(existing_tickers) and len(ordered) < 10:
            ordered.append(existing_tickers[ei])
            ei += 1
        if ni < len(new_tickers) and len(ordered) < 10:
            ordered.append(new_tickers[ni])
            ni += 1

    # Size each opportunity
    remaining_budget = deploy_budget
    opportunities: list[Opportunity] = []

    for ticker in ordered:
        if remaining_budget < MIN_POSITION_SIZE:
            break

        row = candidates[candidates["Ticker"] == ticker]
        if row.empty:
            continue
        row = row.iloc[0]

        quality = float(row["_quality"])

        base_amount = max(MIN_POSITION_SIZE, deploy_budget / min(len(ordered), 5))

        # Scale by quality tier
        if quality >= 70:
            amount = base_amount * 1.3
        elif quality >= 50:
            amount = base_amount * 1.0
        else:
            amount = base_amount * 0.7

        # Cap at max position weight of total portfolio
        total_nav = ledger.get_portfolio_value({})
        if total_nav > 0:
            max_amount = total_nav * MAX_POSITION_WEIGHT
            if ticker in holdings:
                current_value = holdings[ticker] * ledger.get_avg_price(ticker)
                max_amount = max(0, max_amount - current_value)
            amount = min(amount, max_amount)

        amount = min(amount, remaining_budget)
        if amount < MIN_POSITION_SIZE:
            continue

        is_topup = ticker in holdings
        reason_parts = []
        if is_topup:
            reason_parts.append("Top-up existing")
        else:
            reason_parts.append("New position")
        reason_parts.append(f"Quality={quality:.0f}")
        reason_parts.append(f"CAGR={float(row['CAGR']):.0%}")
        reason_parts.append(f"Alpha={float(row['Alpha']):.2f}")

        opportunities.append(
            Opportunity(
                ticker=ticker,
                sector=get_sector(ticker),
                quality_score=quality,
                suggested_amount=round(amount, 0),
                reason=", ".join(reason_parts),
                alpha=round(float(row["Alpha"]), 4),
                cagr=round(float(row["CAGR"]), 4),
                beta=round(float(row["Beta"]), 4),
                volatility=round(float(row["Volatility"]), 4),
            )
        )

        remaining_budget -= amount

    new_positions = sum(1 for o in opportunities if o.ticker not in holdings)

    return AccumulatePlan(
        available_cash=available_cash,
        deploy_budget=round(deploy_budget, 0),
        market_verdict=market_verdict,
        deploy_pct=deploy_pct,
        opportunities=opportunities,
        existing_positions=current_count,
        total_positions_after=current_count + new_positions,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_accumulation(
    strategy: str,
    plan: AccumulatePlan,
    dry_run: bool = False,
) -> dict:
    """Execute the accumulation plan — buys only.

    Args:
        strategy: Strategy name.
        plan: AccumulatePlan from plan_accumulation().
        dry_run: Show what would happen without executing.

    Returns:
        Execution summary dict.
    """
    from diamond.data import market
    from diamond.data.ledger import Ledger, Trade
    from diamond.execution.costs import calculate_costs
    from diamond.execution.executor import _record_to_order_book

    if not plan.opportunities:
        return {"status": "no_opportunities", "trades": 0}

    ledger = Ledger(strategy)
    today = datetime.now().strftime("%Y-%m-%d")

    # Fetch current prices for the opportunity tickers
    tickers = [o.ticker for o in plan.opportunities]
    current_prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                current_prices[ticker] = float(series.iloc[-1])
        except Exception:
            logger.warning(f"Price fetch failed for {ticker}")

    trades: list[dict] = []

    for opp in plan.opportunities:
        price = current_prices.get(opp.ticker)
        if not price or price <= 0:
            continue

        shares = int(opp.suggested_amount / price)
        if shares <= 0:
            continue

        value = shares * price
        costs = calculate_costs("BUY", value)
        required = value + costs.total

        # Check cash
        available = ledger.get_cash()
        if required > available:
            shares = int((available - costs.total) / price)
            if shares <= 0:
                logger.info(f"Insufficient cash for {opp.ticker}")
                continue
            value = shares * price
            costs = calculate_costs("BUY", value)

        trade_dict = {
            "ticker": opp.ticker,
            "action": "BUY",
            "shares": shares,
            "price": price,
            "rationale": f"Accumulate: {opp.reason}",
        }

        if dry_run:
            trades.append(trade_dict)
            logger.info(f"[DRY RUN] BUY {shares} {opp.ticker} @ {price:.2f} = {value:,.0f} ({opp.reason})")
            continue

        trade = Trade(
            timestamp=today,
            action="BUY",
            ticker=opp.ticker,
            shares=shares,
            price=price,
            total_cost=costs.total,
            rationale=f"Accumulate: {opp.reason}",
        )
        ledger.record_trade(trade)
        trades.append(trade_dict)

        logger.info(f"BUY {shares} {opp.ticker} @ {price:.2f} = {value:,.0f} (cost: {costs.total:.2f})")

    if not dry_run and trades:
        _record_to_order_book(strategy, trades, status="FILLED")
    elif dry_run and trades:
        _record_to_order_book(strategy, trades, status="PENDING")

    if dry_run:
        return {
            "status": "dry_run",
            "trades": len(trades),
            "trade_list": trades,
            "total_deploy": sum(t["shares"] * t["price"] for t in trades),
        }

    nav = ledger.get_portfolio_value(current_prices)
    return {
        "status": "executed",
        "trades": len(trades),
        "nav": round(nav, 2),
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }


# ---------------------------------------------------------------------------
# Cash management & status
# ---------------------------------------------------------------------------


def add_cash(strategy: str, amount: float) -> float:
    """Add cash to the accumulate ledger.

    Args:
        strategy: Strategy name.
        amount: Amount in INR to add.

    Returns:
        New cash balance.
    """
    ledger = Ledger(strategy)
    current = ledger.get_cash()
    ledger.set_cash(current + amount)
    new_balance = ledger.get_cash()
    logger.info(f"Added {amount:,.0f} INR to {strategy}. Balance: {new_balance:,.0f}")
    return new_balance


def get_accumulate_status(strategy: str) -> dict:
    """Get current accumulate portfolio status."""
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    return {
        "strategy": strategy,
        "holdings_count": len(holdings),
        "holdings": holdings,
        "cash": round(ledger.get_cash(), 2),
        "initial_capital": ledger.get_initial_capital(),
        "total_fees": round(ledger.get_total_fees(), 2),
        "trade_count": len(ledger.get_trades()),
        "last_rebalance": ledger.get_last_rebalance(),
    }
