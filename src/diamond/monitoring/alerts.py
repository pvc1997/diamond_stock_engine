"""Portfolio health monitoring and alerts.

Checks for drawdown breaches, position drift, stop-loss triggers,
and generates actionable alerts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from diamond.config import get_config
from diamond.data.ledger import Ledger

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """A portfolio health alert."""

    level: str  # "info", "warning", "critical"
    category: str  # "drawdown", "drift", "stop_loss", "concentration"
    message: str
    details: dict


def check_drawdown(
    ledger: Ledger,
    current_prices: dict[str, float],
) -> list[Alert]:
    """Check if portfolio drawdown exceeds thresholds.

    Returns alerts if current NAV is significantly below initial capital.
    """
    alerts = []
    initial = ledger.get_initial_capital()
    nav = ledger.get_portfolio_value(current_prices)

    if initial <= 0:
        return alerts

    drawdown = (initial - nav) / initial

    if drawdown >= 0.15:
        alerts.append(
            Alert(
                level="critical",
                category="drawdown",
                message=f"CRITICAL: Portfolio drawdown {drawdown:.1%} exceeds 15% circuit breaker",
                details={
                    "drawdown_pct": round(drawdown * 100, 2),
                    "nav": round(nav, 2),
                    "initial": initial,
                },
            )
        )
    elif drawdown >= 0.10:
        alerts.append(
            Alert(
                level="warning",
                category="drawdown",
                message=f"WARNING: Portfolio drawdown {drawdown:.1%} approaching circuit breaker",
                details={
                    "drawdown_pct": round(drawdown * 100, 2),
                    "nav": round(nav, 2),
                    "initial": initial,
                },
            )
        )

    return alerts


def check_position_drift(
    ledger: Ledger,
    target_allocation: dict[str, float],
    current_prices: dict[str, float],
) -> list[Alert]:
    """Check if positions have drifted from target weights.

    Returns alerts for positions that deviate more than the configured threshold.
    """
    cfg = get_config()
    threshold = cfg.rebalance.drift_threshold
    alerts = []

    nav = ledger.get_portfolio_value(current_prices)
    if nav <= 0:
        return alerts

    holdings = ledger.get_holdings()
    total_target = sum(target_allocation.values())

    for ticker in set(list(holdings.keys()) + list(target_allocation.keys())):
        # Current weight
        shares = holdings.get(ticker, 0)
        price = current_prices.get(ticker, 0)
        current_value = shares * price
        current_weight = current_value / nav if nav > 0 else 0

        # Target weight
        target_value = target_allocation.get(ticker, 0)
        target_weight = target_value / total_target if total_target > 0 else 0

        drift = abs(current_weight - target_weight)
        if drift > threshold:
            alerts.append(
                Alert(
                    level="warning",
                    category="drift",
                    message=(
                        f"{ticker}: drifted {drift:.1%} from target "
                        f"(current={current_weight:.1%}, target={target_weight:.1%})"
                    ),
                    details={
                        "ticker": ticker,
                        "current_weight_pct": round(current_weight * 100, 2),
                        "target_weight_pct": round(target_weight * 100, 2),
                        "drift_pct": round(drift * 100, 2),
                    },
                )
            )

    return alerts


def check_stop_loss(
    ledger: Ledger,
    current_prices: dict[str, float],
) -> list[Alert]:
    """Check if any position has breached the stop-loss threshold.

    Compares current price against average purchase price.
    """
    cfg = get_config()
    threshold = cfg.risk.stop_loss_threshold
    alerts = []

    holdings = ledger.get_holdings()

    for ticker, shares in holdings.items():
        avg_price = ledger.get_avg_price(ticker)
        current_price = current_prices.get(ticker, 0)

        if avg_price <= 0 or current_price <= 0:
            continue

        loss = (avg_price - current_price) / avg_price
        if loss >= threshold:
            alerts.append(
                Alert(
                    level="critical",
                    category="stop_loss",
                    message=f"STOP LOSS: {ticker} down {loss:.1%} (avg={avg_price:.2f}, current={current_price:.2f})",
                    details={
                        "ticker": ticker,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "loss_pct": round(loss * 100, 2),
                        "shares": shares,
                    },
                )
            )

    return alerts


def check_concentration(
    ledger: Ledger,
    current_prices: dict[str, float],
) -> list[Alert]:
    """Check if any single position exceeds the max position weight.

    Tiered alerts: WARNING at 1.25x limit, CRITICAL at 1.5x limit.
    """
    cfg = get_config()
    max_weight = cfg.portfolio.max_position_weight
    alerts = []

    nav = ledger.get_portfolio_value(current_prices)
    if nav <= 0:
        return alerts

    holdings = ledger.get_holdings()

    for ticker, shares in holdings.items():
        price = current_prices.get(ticker, 0)
        weight = (shares * price) / nav

        if weight > max_weight * 1.5:
            alerts.append(
                Alert(
                    level="critical",
                    category="concentration",
                    message=f"CONCENTRATION: {ticker} at {weight:.1%} (limit {max_weight:.0%}, trim needed)",
                    details={
                        "ticker": ticker,
                        "weight_pct": round(weight * 100, 2),
                        "limit_pct": round(max_weight * 100, 2),
                        "action": "trim",
                    },
                )
            )
        elif weight > max_weight * 1.25:
            alerts.append(
                Alert(
                    level="warning",
                    category="concentration",
                    message=f"{ticker}: position weight {weight:.1%} approaching limit ({max_weight:.0%})",
                    details={
                        "ticker": ticker,
                        "weight_pct": round(weight * 100, 2),
                        "limit_pct": round(max_weight * 100, 2),
                    },
                )
            )

    return alerts


def check_delisted(
    ledger: Ledger,
    current_prices: dict[str, float],
) -> list[Alert]:
    """Detect holdings with no price data (likely delisted or suspended)."""
    alerts = []
    holdings = ledger.get_holdings()

    for ticker, shares in holdings.items():
        if ticker not in current_prices or current_prices.get(ticker, 0) <= 0:
            alerts.append(
                Alert(
                    level="critical",
                    category="delisted",
                    message=f"DELISTED: {ticker} ({shares} shares) — no price data, consider write-off",
                    details={
                        "ticker": ticker,
                        "shares": shares,
                        "action": "cleanup",
                    },
                )
            )

    return alerts


def get_actionable_alerts(
    strategy: str,
    current_prices: dict[str, float],
) -> list[Alert]:
    """Return only alerts that have a suggested action (stop-loss, concentration, delisted)."""
    ledger = Ledger(strategy)
    alerts: list[Alert] = []

    alerts.extend(check_stop_loss(ledger, current_prices))
    alerts.extend(check_concentration(ledger, current_prices))
    alerts.extend(check_delisted(ledger, current_prices))

    # Only return alerts that suggest an action
    actionable = [a for a in alerts if a.details.get("action") or a.category in ("stop_loss", "delisted")]
    actionable.sort(key=lambda a: {"critical": 0, "warning": 1, "info": 2}.get(a.level, 9))
    return actionable


def run_health_check(
    strategy: str,
    current_prices: dict[str, float],
    target_allocation: dict[str, float] | None = None,
) -> list[Alert]:
    """Run all health checks for a strategy.

    Args:
        strategy: Strategy name (used for ledger lookup).
        current_prices: {ticker: price} for all relevant stocks.
        target_allocation: Optional target allocation for drift checks.

    Returns:
        List of Alert objects, sorted by severity.
    """
    ledger = Ledger(strategy)
    alerts: list[Alert] = []

    alerts.extend(check_drawdown(ledger, current_prices))
    alerts.extend(check_stop_loss(ledger, current_prices))
    alerts.extend(check_concentration(ledger, current_prices))
    alerts.extend(check_delisted(ledger, current_prices))

    if target_allocation:
        alerts.extend(check_position_drift(ledger, target_allocation, current_prices))

    # Sort: critical first, then warning, then info
    level_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: level_order.get(a.level, 9))

    return alerts
