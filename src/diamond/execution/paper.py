"""Paper trading mode — simulates execution against live market data.

Uses a separate paper ledger (suffixed with '_paper') so real portfolios
are never affected. Records all trades, tracks NAV, and produces the
same execution summary as the real executor.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from diamond.config import get_config
from diamond.data.ledger import Ledger, Trade
from diamond.execution.costs import calculate_costs
from diamond.execution.executor import (
    _calculate_trades,
    _get_current_prices,
    _record_to_order_book,
)

logger = logging.getLogger(__name__)

PAPER_SUFFIX = "_paper"


def _paper_strategy_name(strategy: str) -> str:
    """Derive paper ledger name from strategy name."""
    if strategy.endswith(PAPER_SUFFIX):
        return strategy
    return f"{strategy}{PAPER_SUFFIX}"


def execute_paper(
    strategy: str,
    target_allocation: dict[str, float],
    capital: float,
    force: bool = False,
    screener_df: pd.DataFrame | None = None,
    smart: bool = False,
) -> dict:
    """Execute trades in paper trading mode.

    Identical flow to real executor but:
    - Uses a separate paper ledger ({strategy}_paper.db)
    - Never touches real holdings
    - Always "executes" (no dry_run needed — it IS the simulation)
    - Adds simulated slippage via cost model

    Args:
        strategy: Base strategy name (paper suffix added automatically).
        target_allocation: {ticker: amount_inr} from strategy.allocate().
        capital: Initial capital (used if paper ledger doesn't exist).
        force: Bypass rebalance frequency check.
        smart: Use smart rebalancing (drift + tax-aware ordering).

    Returns:
        Dict with execution summary (same shape as real executor).
    """
    cfg = get_config()
    paper_name = _paper_strategy_name(strategy)
    ledger = Ledger(paper_name)

    # Initialize capital on first run
    if (
        not ledger.get_holdings()
        and ledger.get_cash() == cfg.risk.initial_capital
        and capital != cfg.risk.initial_capital
    ):
        ledger.reset(initial_capital=capital)

    today = datetime.now().strftime("%Y-%m-%d")

    # Get current prices
    all_tickers = list(set(list(ledger.get_holdings().keys()) + list(target_allocation.keys())))
    current_prices = _get_current_prices(all_tickers)

    # Smart rebalance: combined time + drift check
    if smart and ledger.get_holdings():
        from diamond.execution.smart_rebalance import should_rebalance_smart

        should, drift_report = should_rebalance_smart(
            ledger,
            target_allocation,
            current_prices,
            force=force,
        )
        if not should:
            logger.info(f"[PAPER] Smart rebalance skipped: {drift_report.reason}")
            return {
                "status": "skipped",
                "mode": "paper",
                "reason": drift_report.reason,
                "max_drift": round(drift_report.max_drift, 4),
                "trades": 0,
            }
        logger.info(f"[PAPER] Smart rebalance triggered: {drift_report.reason}")
    elif not force:
        last_rebalance = ledger.get_last_rebalance()
        if last_rebalance:
            last_dt = datetime.strptime(last_rebalance, "%Y-%m-%d")
            days_since = (datetime.strptime(today, "%Y-%m-%d") - last_dt).days
            if days_since < cfg.rebalance.rebalance_frequency_days:
                return {
                    "status": "skipped",
                    "mode": "paper",
                    "reason": f"Next rebalance in {cfg.rebalance.rebalance_frequency_days - days_since} days",
                    "trades": 0,
                }

    # Calculate trades — smart or legacy
    if smart and ledger.get_holdings():
        from diamond.execution.smart_rebalance import plan_tax_aware_trades

        smart_trades = plan_tax_aware_trades(
            ledger,
            target_allocation,
            current_prices,
            cfg.rebalance.min_trade_value,
        )
        trades = [
            {
                "ticker": st.ticker,
                "action": st.action,
                "shares": st.shares,
                "price": st.price,
                "tax_category": st.tax_category,
                "tax_reason": st.reason,
            }
            for st in smart_trades
        ]
    else:
        trades = _calculate_trades(
            ledger,
            target_allocation,
            current_prices,
            cfg.rebalance.min_trade_value,
        )

    if not trades:
        return {"status": "no_trades", "mode": "paper", "trades": 0}

    # Generate rationales if screener data is available
    rationales = {}
    if screener_df is not None:
        try:
            from diamond.analysis.rationale import format_rationale, generate_batch_rationale

            rationales = generate_batch_rationale(
                target_allocation=target_allocation,
                capital=capital,
                screener_df=screener_df,
                strategy_name=strategy,
                holdings=ledger.get_holdings(),
                current_prices=current_prices,
            )
        except Exception as e:
            logger.warning(f"Rationale generation failed (proceeding): {e}")

    # Execute paper trades
    executed = 0
    total_fees = 0.0

    for t in trades:
        value = t["shares"] * t["price"]
        costs = calculate_costs(t["action"], value)

        if t["action"] == "BUY":
            required = value + costs.total
            available = ledger.get_cash()
            if required > available:
                affordable = int((available - costs.total) / t["price"])
                if affordable <= 0:
                    logger.info(f"[PAPER] Insufficient cash for {t['ticker']}")
                    continue
                t["shares"] = affordable
                value = t["shares"] * t["price"]
                costs = calculate_costs(t["action"], value)

        # Build rationale string
        rationale_str = "Paper rebalance"
        if t["ticker"] in rationales:
            try:
                from diamond.analysis.rationale import format_rationale

                rationale_str = format_rationale(rationales[t["ticker"]])
            except Exception:
                pass

        trade = Trade(
            timestamp=today,
            action=t["action"],
            ticker=t["ticker"],
            shares=t["shares"],
            price=t["price"],
            total_cost=costs.total,
            rationale=rationale_str,
        )
        ledger.record_trade(trade)
        total_fees += costs.total
        executed += 1

        logger.info(f"[PAPER] {t['action']} {t['shares']} {t['ticker']} @ {t['price']:.2f} (cost: {costs.total:.2f})")

    ledger.set_last_rebalance(today)

    # Record to order book
    _record_to_order_book(paper_name, trades, status="FILLED")

    nav = ledger.get_portfolio_value(current_prices)
    summary = {
        "status": "executed",
        "mode": "paper",
        "trades": executed,
        "total_fees": round(total_fees, 2),
        "nav": round(nav, 2),
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }

    logger.info(
        f"[PAPER] Complete: {executed} trades, fees={total_fees:.2f}, NAV={nav:,.2f}, cash={ledger.get_cash():,.2f}"
    )

    return summary


def get_paper_status(strategy: str) -> dict:
    """Get current paper portfolio status.

    Args:
        strategy: Base strategy name.

    Returns:
        Dict with holdings, cash, trade count, fees.
    """
    paper_name = _paper_strategy_name(strategy)
    ledger = Ledger(paper_name)
    holdings = ledger.get_holdings()

    return {
        "strategy": paper_name,
        "holdings": holdings,
        "holdings_count": len(holdings),
        "cash": round(ledger.get_cash(), 2),
        "total_fees": round(ledger.get_total_fees(), 2),
        "trade_count": len(ledger.get_trades()),
        "last_rebalance": ledger.get_last_rebalance(),
        "initial_capital": ledger.get_initial_capital(),
    }


def get_paper_nav(strategy: str, current_prices: dict[str, float] | None = None) -> float:
    """Get current paper portfolio NAV.

    If current_prices not provided, fetches live prices.
    """
    paper_name = _paper_strategy_name(strategy)
    ledger = Ledger(paper_name)
    holdings = ledger.get_holdings()

    if current_prices is None:
        current_prices = _get_current_prices(list(holdings.keys()))

    return ledger.get_portfolio_value(current_prices)


def reset_paper(strategy: str, capital: float | None = None) -> None:
    """Reset paper portfolio to initial state."""
    paper_name = _paper_strategy_name(strategy)
    ledger = Ledger(paper_name)
    ledger.reset(initial_capital=capital)
    logger.info(f"[PAPER] Reset {paper_name} to {capital or get_config().risk.initial_capital} INR")
