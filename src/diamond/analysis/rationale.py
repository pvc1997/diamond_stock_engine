"""Trade rationale engine — explains every trade decision.

Generates human-readable rationale for each trade including:
- Why the stock was selected (screener metrics)
- Why this weight (allocation method)
- Why now (timing context)
- Risk considerations

Rationale is stored in the ledger's trade.rationale field for audit trail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from diamond.config import get_config
from diamond.data.universe import get_sector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TradeRationale:
    ticker: str
    action: str  # BUY or SELL
    # Selection
    selection_reason: str
    screener_summary: str  # "Alpha=0.45, Beta=0.85, CAGR=22%"
    component: str  # quality_growth / defensive / value / etc.
    # Weight
    weight_pct: float
    weight_method: str  # inverse_volatility / equal / alpha_proportional
    weight_reason: str
    # Timing
    timing_reason: str
    market_context: str
    # Risk
    risk_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_market_context() -> str:
    """Fetch market pulse and summarize in one line. Fail-open."""
    try:
        from diamond.monitoring.market_pulse import get_market_pulse

        pulse = get_market_pulse()
        return (
            f"Market: {pulse.verdict} (Score {pulse.score:+d}), "
            f"VIX={pulse.vix:.1f}, Nifty={pulse.nifty_price:,.0f} "
            f"({pulse.nifty_change_pct:+.1f}%), Regime={pulse.regime}"
        )
    except Exception:
        return "Market context unavailable"


def _screener_summary(row: pd.Series) -> str:
    """Format screener metrics from a DataFrame row."""
    parts = []
    if "Alpha" in row.index:
        parts.append(f"Alpha={row['Alpha']:.2f}")
    if "Beta" in row.index:
        parts.append(f"Beta={row['Beta']:.2f}")
    if "CAGR" in row.index:
        parts.append(f"CAGR={row['CAGR']:.1%}")
    if "Volatility" in row.index:
        parts.append(f"Vol={row['Volatility']:.1%}")
    if "Hurst" in row.index:
        parts.append(f"Hurst={row['Hurst']:.2f}")
    return ", ".join(parts) if parts else "N/A"


def _detect_component(
    ticker: str,
    row: pd.Series,
    strategy_name: str,
) -> tuple[str, str]:
    """Detect which strategy component selected this stock and why.

    Returns (component_name, selection_reason).
    """
    if strategy_name == "gods_plan":
        alpha = float(row.get("Alpha", 0) or 0)
        beta = float(row.get("Beta", 1) or 1)
        cagr = float(row.get("CAGR", 0) or 0)
        hurst = float(row.get("Hurst", 0.5) or 0.5)
        vol = float(row.get("Volatility", 0.3) or 0.3)

        # Quality Growth tier
        cfg = get_config()
        gp = cfg.gods_plan
        if (
            alpha >= gp.core_min_alpha
            and cagr >= gp.core_min_cagr
            and hurst >= gp.core_min_hurst
            and gp.core_min_beta <= beta <= gp.core_max_beta
        ):
            return "quality_growth", (
                f"Quality Growth: Alpha={alpha:.2f} (>{gp.core_min_alpha:.2f}), "
                f"CAGR={cagr:.1%} (>{gp.core_min_cagr:.0%}), "
                f"Hurst={hurst:.2f} (trending)"
            )

        # Defensive tier
        if beta < 0.8 and alpha > 0 and cagr > 0.10 and vol < 0.30:
            return "defensive", (
                f"Defensive: Beta={beta:.2f} (<0.8), Alpha={alpha:.2f} (positive), Vol={vol:.1%} (<30%)"
            )

        # Value tier
        if alpha > 0 and cagr > 0:
            return "value", (
                f"Value: Positive alpha={alpha:.2f}, CAGR/Vol ratio={cagr / vol:.2f}"
                if vol > 0
                else f"Value: Alpha={alpha:.2f}"
            )

        return "general", f"Selected by screener: Alpha={alpha:.2f}, CAGR={cagr:.1%}"

    elif strategy_name == "steady":
        beta = float(row.get("Beta", 1) or 1)
        alpha = float(row.get("Alpha", 0) or 0)
        vol = float(row.get("Volatility", 0.3) or 0.3)
        return "steady_quality", (f"Low-beta quality: Beta={beta:.2f}, Alpha={alpha:.2f}, Vol={vol:.1%}")

    elif strategy_name == "baseline":
        return "nifty50", "Nifty 50 constituent — equal weight benchmark"

    return "general", f"Selected by {strategy_name} screener"


def _detect_weight_method(strategy_name: str, component: str) -> tuple[str, str]:
    """Detect the weighting method used by the strategy/component."""
    if strategy_name == "baseline":
        return "equal", "Equal weight across all Nifty 50 stocks"

    if strategy_name == "steady":
        return "inverse_volatility", "Lower volatility -> higher weight (capital protection)"

    if strategy_name == "gods_plan":
        if component == "quality_growth":  # noqa: SIM116
            return "inverse_volatility", "Inverse-volatility within 55% quality growth allocation"
        elif component == "defensive":
            return "inverse_volatility", "Inverse-volatility within 25% defensive allocation"
        elif component == "value":
            return "alpha_proportional", "Alpha-proportional within 20% value allocation"

    return "strategy_specific", f"Weight assigned by {strategy_name} allocator"


def _compute_risk_notes(
    ticker: str,
    weight_pct: float,
    holdings: dict[str, int],
    current_prices: dict[str, float],
    target_allocation: dict[str, float],
) -> list[str]:
    """Compute risk context for a trade."""
    notes = []
    cfg = get_config()

    # Position weight check
    if weight_pct > cfg.portfolio.max_position_weight * 100:
        notes.append(
            f"Position weight {weight_pct:.1f}% exceeds max {cfg.portfolio.max_position_weight:.0%} — will be capped"
        )

    # Sector concentration
    sector = get_sector(ticker)
    if sector != "Unknown":
        same_sector = [t for t in target_allocation if get_sector(t) == sector]
        if len(same_sector) > cfg.portfolio.max_stocks_per_sector:
            notes.append(
                f"Sector '{sector}' has {len(same_sector)} stocks (cap: {cfg.portfolio.max_stocks_per_sector})"
            )

        # Sector weight
        sector_weight = sum(target_allocation.get(t, 0) for t in same_sector)
        total_alloc = sum(target_allocation.values())
        if total_alloc > 0:
            sector_pct = sector_weight / total_alloc * 100
            max_sector_pct = cfg.portfolio.max_sector_exposure * 100
            if sector_pct > max_sector_pct * 0.8:
                notes.append(f"Sector '{sector}' at {sector_pct:.0f}% (limit: {max_sector_pct:.0f}%)")

    # Stop-loss proximity for existing holdings
    if ticker in holdings and ticker in current_prices:
        # Can't easily get avg price here without ledger name,
        # so we skip this check in batch mode
        pass

    return notes


def _get_timing_reason(strategy_name: str) -> str:
    """Explain why the trade is happening now."""
    cfg = get_config()
    if strategy_name == "gods_plan":
        freq = cfg.gods_plan.rebalance_days
    else:
        freq = cfg.rebalance.rebalance_frequency_days
    return f"Scheduled {freq}-day rebalance cycle"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_rationale(
    ticker: str,
    action: str,
    target_weight: float,
    screener_df: pd.DataFrame,
    strategy_name: str,
    target_allocation: dict[str, float],
    holdings: dict[str, int],
    current_prices: dict[str, float],
) -> TradeRationale:
    """Generate detailed rationale for a single trade.

    Args:
        ticker: Stock ticker.
        action: 'BUY' or 'SELL'.
        target_weight: Target portfolio weight (0 to 1).
        screener_df: Screener results DataFrame.
        strategy_name: Name of the strategy.
        target_allocation: Full target allocation dict.
        holdings: Current holdings dict.
        current_prices: Current prices dict.

    Returns:
        TradeRationale with all fields populated.
    """
    # Find this ticker in screener results
    row = None
    if not screener_df.empty and "Ticker" in screener_df.columns:
        matches = screener_df[screener_df["Ticker"] == ticker]
        if not matches.empty:
            row = matches.iloc[0]

    if row is not None:
        component, selection_reason = _detect_component(ticker, row, strategy_name)
        summary = _screener_summary(row)
    else:
        if action == "SELL":
            component = "exit"
            selection_reason = "No longer in target allocation — position being closed"
            summary = "N/A (exiting position)"
        else:
            component = "general"
            selection_reason = f"Selected by {strategy_name} strategy"
            summary = "N/A"

    weight_method, weight_reason = _detect_weight_method(strategy_name, component)
    weight_pct = target_weight * 100

    timing = _get_timing_reason(strategy_name)
    market_ctx = _get_market_context()

    risk_notes = _compute_risk_notes(
        ticker,
        weight_pct,
        holdings,
        current_prices,
        target_allocation,
    )

    return TradeRationale(
        ticker=ticker,
        action=action,
        selection_reason=selection_reason,
        screener_summary=summary,
        component=component,
        weight_pct=weight_pct,
        weight_method=weight_method,
        weight_reason=weight_reason,
        timing_reason=timing,
        market_context=market_ctx,
        risk_notes=risk_notes,
    )


def generate_batch_rationale(
    target_allocation: dict[str, float],
    capital: float,
    screener_df: pd.DataFrame,
    strategy_name: str,
    holdings: dict[str, int],
    current_prices: dict[str, float],
) -> dict[str, TradeRationale]:
    """Generate rationales for all trades in an allocation.

    Returns {ticker: TradeRationale} for every ticker that has a trade
    (either in target or in current holdings).
    """
    total = sum(target_allocation.values())
    if total <= 0:
        total = capital

    # Fetch market context once for all trades
    market_ctx = _get_market_context()
    timing = _get_timing_reason(strategy_name)

    all_tickers = set(list(holdings.keys()) + list(target_allocation.keys()))
    rationales = {}

    for ticker in all_tickers:
        target_amount = target_allocation.get(ticker, 0)
        current_shares = holdings.get(ticker, 0)
        price = current_prices.get(ticker, 0)
        current_value = current_shares * price if price > 0 else 0

        # Determine action
        if target_amount > current_value:
            action = "BUY"
        elif target_amount < current_value:
            action = "SELL"
        else:
            continue  # No trade needed

        target_weight = target_amount / total if total > 0 else 0

        # Find screener data
        row = None
        if not screener_df.empty and "Ticker" in screener_df.columns:
            matches = screener_df[screener_df["Ticker"] == ticker]
            if not matches.empty:
                row = matches.iloc[0]

        if row is not None:
            component, selection_reason = _detect_component(ticker, row, strategy_name)
            summary = _screener_summary(row)
        else:
            if action == "SELL" and target_amount == 0:
                component = "exit"
                selection_reason = "No longer in target allocation — position being closed"
                summary = "N/A"
            else:
                component = "general"
                selection_reason = f"Selected by {strategy_name} strategy"
                summary = "N/A"

        weight_method, weight_reason = _detect_weight_method(strategy_name, component)

        risk_notes = _compute_risk_notes(
            ticker,
            target_weight * 100,
            holdings,
            current_prices,
            target_allocation,
        )

        rationales[ticker] = TradeRationale(
            ticker=ticker,
            action=action,
            selection_reason=selection_reason,
            screener_summary=summary,
            component=component,
            weight_pct=round(target_weight * 100, 1),
            weight_method=weight_method,
            weight_reason=weight_reason,
            timing_reason=timing,
            market_context=market_ctx,
            risk_notes=risk_notes,
        )

    return rationales


def format_rationale(rationale: TradeRationale) -> str:
    """Format rationale as a compact string for ledger storage.

    Produces a one-line summary suitable for the Trade.rationale TEXT field.
    """
    parts = [rationale.selection_reason]

    if rationale.screener_summary != "N/A":
        parts.append(f"[{rationale.screener_summary}]")

    parts.append(f"Wt: {rationale.weight_pct:.1f}% ({rationale.weight_method})")

    if rationale.risk_notes:
        parts.append(f"Risk: {'; '.join(rationale.risk_notes)}")

    return " | ".join(parts)


def format_rationale_verbose(rationale: TradeRationale) -> str:
    """Format rationale as a multi-line verbose string for display."""
    lines = [
        f"  {rationale.action} {rationale.ticker}",
        f"    Selection: {rationale.selection_reason}",
        f"    Metrics:   {rationale.screener_summary}",
        f"    Weight:    {rationale.weight_pct:.1f}% — {rationale.weight_reason}",
        f"    Timing:    {rationale.timing_reason}",
        f"    Market:    {rationale.market_context}",
    ]
    if rationale.risk_notes:
        for note in rationale.risk_notes:
            lines.append(f"    Risk:      {note}")
    return "\n".join(lines)
