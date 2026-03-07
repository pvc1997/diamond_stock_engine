"""Structured metrics logging for key portfolio events.

Emits JSON-formatted log entries that are machine-parseable for monitoring,
alerting, and dashboarding. Uses the standard logging library — no external
dependencies.

Usage:
    from diamond.monitoring.metrics import log_trade, log_rebalance, log_risk

Events are logged at INFO level to a dedicated 'diamond.metrics' logger.
Configure handlers as needed (file, stdout, external sink).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("diamond.metrics")


def _emit(event: str, **fields: Any) -> None:
    """Emit a structured JSON log entry."""
    record = {
        "event": event,
        "ts": time.time(),
        **fields,
    }
    logger.info(json.dumps(record, default=str))


# --- Trade events ---


def log_trade(
    strategy: str,
    action: str,
    ticker: str,
    shares: int,
    price: float,
    cost: float,
    reason: str = "",
) -> None:
    """Log a trade execution."""
    _emit(
        "trade",
        strategy=strategy,
        action=action,
        ticker=ticker,
        shares=shares,
        price=round(price, 2),
        value=round(shares * price, 2),
        cost=round(cost, 2),
        reason=reason,
    )


# --- Rebalance events ---


def log_rebalance(
    strategy: str,
    trades: int,
    total_fees: float,
    nav: float,
    cash: float,
    holdings: int,
    smart: bool = False,
) -> None:
    """Log a completed rebalance."""
    _emit(
        "rebalance",
        strategy=strategy,
        trades=trades,
        total_fees=round(total_fees, 2),
        nav=round(nav, 2),
        cash=round(cash, 2),
        holdings=holdings,
        smart=smart,
    )


# --- Risk events ---


def log_risk_signal(
    strategy: str,
    level: str,
    signal: str,
    value: float | None = None,
) -> None:
    """Log a risk signal (WARNING or CRITICAL)."""
    fields: dict[str, Any] = {
        "strategy": strategy,
        "level": level,
        "signal": signal,
    }
    if value is not None:
        fields["value"] = round(value, 4)
    _emit("risk_signal", **fields)


# --- Portfolio snapshot ---


def log_portfolio_snapshot(
    strategy: str,
    nav: float,
    cash: float,
    holdings: int,
    drawdown_pct: float = 0.0,
) -> None:
    """Log a portfolio state snapshot."""
    _emit(
        "portfolio_snapshot",
        strategy=strategy,
        nav=round(nav, 2),
        cash=round(cash, 2),
        holdings=holdings,
        drawdown_pct=round(drawdown_pct, 2),
    )


# --- Error events ---


def log_error(
    operation: str,
    error: str,
    strategy: str = "",
    ticker: str = "",
) -> None:
    """Log an operational error."""
    fields: dict[str, Any] = {
        "operation": operation,
        "error": error,
    }
    if strategy:
        fields["strategy"] = strategy
    if ticker:
        fields["ticker"] = ticker
    _emit("error", **fields)


# --- Backtest events ---


def log_backtest_complete(
    strategy: str,
    start: str,
    end: str,
    cagr: float,
    sharpe: float,
    max_drawdown: float,
    total_return: float,
) -> None:
    """Log a completed backtest run."""
    _emit(
        "backtest_complete",
        strategy=strategy,
        start=start,
        end=end,
        cagr=round(cagr, 2),
        sharpe=round(sharpe, 3),
        max_drawdown=round(max_drawdown, 2),
        total_return=round(total_return, 2),
    )
