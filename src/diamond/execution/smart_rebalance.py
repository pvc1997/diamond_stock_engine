"""Smart rebalancing with drift detection, volatility adjustment, and tax awareness.

Enhances the basic executor by:
1. Drift-based triggers: only trade when weight drift exceeds threshold
2. Volatility-adjusted sizing: scale positions inversely with recent volatility
3. Tax-aware trade ordering: harvest losses first, defer gains near LTCG boundary
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from diamond.config import get_config
from diamond.data.ledger import Ledger

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """Portfolio drift analysis."""

    max_drift: float  # Largest absolute weight drift
    mean_drift: float  # Average absolute drift
    drifted_tickers: list[tuple[str, float, float]]  # (ticker, current_wt, target_wt)
    needs_rebalance: bool  # True if max_drift > threshold
    reason: str


@dataclass
class SmartTrade:
    """Enhanced trade with tax and priority info."""

    ticker: str
    action: str  # BUY or SELL
    shares: int
    price: float
    priority: int  # Lower = execute first
    tax_category: str  # STCG, LTCG, N/A (for buys)
    holding_days: int  # Days held (0 for buys)
    estimated_gain: float  # Per-share gain/loss
    reason: str  # Why this trade


def compute_drift(
    holdings: dict[str, int],
    target_allocation: dict[str, float],
    current_prices: dict[str, float],
) -> DriftReport:
    """Compute portfolio weight drift from target allocation.

    Returns DriftReport with per-ticker drift and recommendation.
    """
    cfg = get_config()
    nav = sum(shares * current_prices.get(t, 0) for t, shares in holdings.items())

    if nav <= 0:
        return DriftReport(0, 0, [], False, "No portfolio value")

    total_target = sum(target_allocation.values())
    all_tickers = set(list(holdings.keys()) + list(target_allocation.keys()))

    drifts: list[tuple[str, float, float]] = []
    for ticker in all_tickers:
        current_value = holdings.get(ticker, 0) * current_prices.get(ticker, 0)
        current_weight = current_value / nav if nav > 0 else 0
        target_weight = target_allocation.get(ticker, 0) / total_target if total_target > 0 else 0
        drift = abs(current_weight - target_weight)
        if drift > 0.001:  # Ignore tiny drifts
            drifts.append((ticker, current_weight, target_weight))

    drifts.sort(key=lambda x: abs(x[1] - x[2]), reverse=True)
    max_drift = max((abs(cw - tw) for _, cw, tw in drifts), default=0)
    mean_drift = sum(abs(cw - tw) for _, cw, tw in drifts) / len(drifts) if drifts else 0

    threshold = cfg.rebalance.drift_threshold
    needs_rebalance = max_drift > threshold

    if needs_rebalance:
        worst = drifts[0] if drifts else ("", 0, 0)
        reason = (
            f"Max drift {max_drift:.1%} > {threshold:.1%} threshold "
            f"({worst[0].replace('.NS', '')} at {worst[1]:.1%} vs target {worst[2]:.1%})"
        )
    else:
        reason = f"Max drift {max_drift:.1%} within {threshold:.1%} threshold"

    return DriftReport(max_drift, mean_drift, drifts, needs_rebalance, reason)


def adjust_for_volatility(
    target_allocation: dict[str, float],
    volatilities: dict[str, float],
    scale_factor: float = 0.5,
) -> dict[str, float]:
    """Adjust position sizes based on recent volatility.

    Higher volatility -> smaller position. Redistributes to maintain total capital.

    Args:
        target_allocation: {ticker: amount_inr} base allocation
        volatilities: {ticker: annualized_vol_pct} from screener
        scale_factor: 0=no adjustment, 1=full inverse-vol scaling
    """
    if not volatilities or not target_allocation:
        return dict(target_allocation)

    total = sum(target_allocation.values())
    adjusted: dict[str, float] = {}

    # Compute inverse-vol weights
    inv_vols: dict[str, float] = {}
    for ticker in target_allocation:
        vol = volatilities.get(ticker, 25.0)  # Default 25% if unknown
        vol = max(vol, 5.0)  # Floor at 5%
        inv_vols[ticker] = 1.0 / vol

    inv_vol_sum = sum(inv_vols.values())

    for ticker, amount in target_allocation.items():
        base_weight = amount / total if total > 0 else 0
        vol_weight = inv_vols[ticker] / inv_vol_sum if inv_vol_sum > 0 else base_weight

        # Blend base and vol-adjusted weights
        blended = base_weight * (1 - scale_factor) + vol_weight * scale_factor
        adjusted[ticker] = blended * total

    return adjusted


def plan_tax_aware_trades(
    ledger: Ledger,
    target_allocation: dict[str, float],
    current_prices: dict[str, float],
    min_trade_value: float,
) -> list[SmartTrade]:
    """Generate tax-optimized trade list.

    Priorities:
    1. Sell losers first (tax-loss harvesting)
    2. Sell LTCG gainers (12.5% rate, lower than STCG 20%)
    3. Sell holdings near LTCG boundary (>300 days held, defer if possible)
    4. Sell STCG gainers (higher 20% rate)
    5. Buys last (after cash freed from sells)

    Returns SmartTrade list sorted by priority.
    """
    holdings = ledger.get_holdings()
    today = datetime.now()
    trades: list[SmartTrade] = []

    all_tickers = set(list(holdings.keys()) + list(target_allocation.keys()))

    for ticker in all_tickers:
        price = current_prices.get(ticker)
        if not price or price <= 0:
            continue

        current_shares = holdings.get(ticker, 0)
        target_amount = target_allocation.get(ticker, 0)
        target_shares = int(target_amount / price)

        delta = target_shares - current_shares
        if delta == 0:
            continue

        trade_value = abs(delta * price)
        if trade_value < min_trade_value:
            continue

        if delta < 0:
            # SELL
            avg_price = ledger.get_avg_price(ticker)
            gain_per_share = price - avg_price if avg_price > 0 else 0

            # Estimate holding days from trades
            ticker_trades = [t for t in ledger.get_trades() if t.ticker == ticker and t.action == "BUY"]
            if ticker_trades:
                first_buy = ticker_trades[0].timestamp[:10]
                try:
                    buy_date = datetime.strptime(first_buy, "%Y-%m-%d")
                    holding_days = (today - buy_date).days
                except ValueError:
                    holding_days = 0
            else:
                holding_days = 0

            tax_cat = "LTCG" if holding_days >= 365 else "STCG"

            # Priority: lower number = execute first
            if gain_per_share <= 0:
                # Loss -- sell first (tax-loss harvesting)
                priority = 10
                reason = f"Tax-loss harvest ({gain_per_share:+.1f}/share)"
            elif tax_cat == "LTCG":
                # Long-term gain -- lower tax rate, sell after losses
                priority = 30
                reason = f"LTCG ({holding_days}d held, {gain_per_share:+.1f}/share)"
            elif holding_days >= 300:
                # Near LTCG boundary -- defer if possible
                days_to_ltcg = 365 - holding_days
                priority = 50
                reason = f"Near LTCG ({days_to_ltcg}d away) -- consider deferring"
            else:
                # Short-term gain -- higher tax
                priority = 40
                reason = f"STCG ({holding_days}d held, {gain_per_share:+.1f}/share)"

            trades.append(
                SmartTrade(
                    ticker=ticker,
                    action="SELL",
                    shares=abs(delta),
                    price=price,
                    priority=priority,
                    tax_category=tax_cat,
                    holding_days=holding_days,
                    estimated_gain=gain_per_share * abs(delta),
                    reason=reason,
                )
            )
        else:
            # BUY
            trades.append(
                SmartTrade(
                    ticker=ticker,
                    action="BUY",
                    shares=delta,
                    price=price,
                    priority=100,  # Buys always after sells
                    tax_category="N/A",
                    holding_days=0,
                    estimated_gain=0,
                    reason=("New position" if ticker not in holdings else "Add to position"),
                )
            )

    trades.sort(key=lambda t: t.priority)
    return trades


def should_rebalance_smart(
    ledger: Ledger,
    target_allocation: dict[str, float],
    current_prices: dict[str, float],
    force: bool = False,
) -> tuple[bool, DriftReport]:
    """Smart rebalance decision combining time and drift.

    Returns (should_rebalance, drift_report).
    Rebalance if:
    - force=True
    - Time-based: days since last >= frequency
    - Drift-based: max weight drift > threshold
    """
    cfg = get_config()

    if force:
        drift = compute_drift(ledger.get_holdings(), target_allocation, current_prices)
        return True, drift

    # Time check
    last = ledger.get_last_rebalance()
    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d")
            days_since = (datetime.now() - last_dt).days
            if days_since < cfg.rebalance.rebalance_frequency_days:
                # Not time yet -- check drift as override
                drift = compute_drift(ledger.get_holdings(), target_allocation, current_prices)
                if drift.needs_rebalance:
                    return True, drift
                return False, drift
        except ValueError:
            pass

    # Time-based trigger (or first run)
    drift = compute_drift(ledger.get_holdings(), target_allocation, current_prices)
    return True, drift
