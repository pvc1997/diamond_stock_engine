"""Portfolio comparison and what-if simulation.

Compare strategies side-by-side or simulate adding/removing stocks.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field

from diamond.config import get_config
from diamond.data.ledger import Ledger
from diamond.data.universe import get_sector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StrategySnapshot:
    name: str
    mode: str  # live / paper / none
    nav: float
    cash: float
    initial_capital: float
    return_pct: float
    holdings_count: int
    total_fees: float
    top_holdings: list[tuple[str, float, float]]  # (ticker, value, weight_pct)
    sector_exposure: dict[str, float]  # {sector: weight_pct}
    beta: float
    volatility: float
    max_drawdown: float
    last_rebalance: str


@dataclass
class WhatIfResult:
    before: dict
    after: dict
    delta: dict
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for tickers."""
    from diamond.data import market

    prices = {}
    if not tickers:
        return prices
    try:
        df = market.download_prices(tickers, period_days=5, use_cache=True)
        for col in df.columns:
            series = df[col].dropna()
            if len(series) > 0:
                prices[col] = float(series.iloc[-1])
    except Exception as e:
        logger.warning(f"Price fetch failed: {e}")
    return prices


def build_snapshot(
    strategy: str,
    include_risk: bool = True,
) -> StrategySnapshot:
    """Build a complete snapshot of a strategy's current state.

    Auto-detects paper portfolio if live has no holdings.
    """
    cfg = get_config()

    # Auto-detect mode
    ledger_name = strategy
    mode = "live"
    live_ledger = Ledger(strategy)
    if not live_ledger.get_holdings():
        paper_db = cfg.ledger_dir / f"{strategy}_paper.db"
        if paper_db.exists():
            ledger_name = f"{strategy}_paper"
            mode = "paper"
        else:
            # No data at all
            return StrategySnapshot(
                name=strategy,
                mode="none",
                nav=0,
                cash=0,
                initial_capital=0,
                return_pct=0,
                holdings_count=0,
                total_fees=0,
                top_holdings=[],
                sector_exposure={},
                beta=0,
                volatility=0,
                max_drawdown=0,
                last_rebalance="",
            )

    ledger = Ledger(ledger_name)
    holdings = ledger.get_holdings()
    initial = ledger.get_initial_capital()
    cash = ledger.get_cash()

    # Fetch prices
    prices = _fetch_prices(list(holdings.keys()))
    nav = ledger.get_portfolio_value(prices)
    return_pct = ((nav - initial) / initial * 100) if initial > 0 else 0

    # Top holdings by value
    holding_values = []
    for ticker, shares in holdings.items():
        value = shares * prices.get(ticker, 0)
        weight = (value / nav * 100) if nav > 0 else 0
        holding_values.append((ticker, value, weight))
    holding_values.sort(key=lambda x: -x[1])
    top = holding_values[:5]

    # Sector exposure
    sectors: dict[str, float] = {}
    for ticker, shares in holdings.items():
        sector = get_sector(ticker)
        value = shares * prices.get(ticker, 0)
        weight = (value / nav * 100) if nav > 0 else 0
        sectors[sector] = sectors.get(sector, 0) + weight

    # Risk metrics
    beta = 0.0
    volatility = 0.0
    max_dd = 0.0

    if include_risk and holdings:
        try:
            from diamond.data import market
            from diamond.monitoring.risk import compute_risk_report

            prices_df = None
            bench_returns = None
            tickers = list(holdings.keys())

            with contextlib.suppress(Exception):
                prices_df = market.download_prices(tickers, period_days=252, use_cache=True)
            with contextlib.suppress(Exception):
                bench = market.download_single("^NSEI", period_days=252)
                bench_returns = market.calculate_returns(bench)

            report = compute_risk_report(strategy, prices, prices_df, bench_returns)
            beta = report.beta
            volatility = report.volatility_annual
            max_dd = report.drawdown_pct
        except Exception as e:
            logger.warning(f"Risk computation failed for {strategy}: {e}")

    return StrategySnapshot(
        name=strategy,
        mode=mode,
        nav=round(nav, 0),
        cash=round(cash, 0),
        initial_capital=round(initial, 0),
        return_pct=round(return_pct, 1),
        holdings_count=len(holdings),
        total_fees=round(ledger.get_total_fees(), 0),
        top_holdings=top,
        sector_exposure=dict(sorted(sectors.items(), key=lambda x: -x[1])),
        beta=round(beta, 2),
        volatility=round(volatility, 1),
        max_drawdown=round(max_dd, 1),
        last_rebalance=ledger.get_last_rebalance(),
    )


def compare_strategies(
    names: list[str],
    include_risk: bool = True,
) -> list[StrategySnapshot]:
    """Build snapshots for multiple strategies."""
    return [build_snapshot(name, include_risk=include_risk) for name in names]


# ---------------------------------------------------------------------------
# What-if simulation
# ---------------------------------------------------------------------------


def simulate_whatif(
    strategy: str,
    add_tickers: list[str],
    remove_tickers: list[str],
) -> WhatIfResult:
    """Simulate adding/removing stocks from a portfolio.

    For removals: sells all shares at current price.
    For additions: distributes freed cash equally among new stocks.
    """
    cfg = get_config()

    # Load current state
    ledger_name = strategy
    live_ledger = Ledger(strategy)
    if not live_ledger.get_holdings():
        paper_db = cfg.ledger_dir / f"{strategy}_paper.db"
        if paper_db.exists():
            ledger_name = f"{strategy}_paper"

    ledger = Ledger(ledger_name)
    holdings = dict(ledger.get_holdings())
    cash = ledger.get_cash()

    # Normalize tickers
    add_tickers = [t if t.endswith(".NS") else f"{t}.NS" for t in add_tickers]
    remove_tickers = [t if t.endswith(".NS") else f"{t}.NS" for t in remove_tickers]

    # Fetch all prices
    all_tickers = list(set(list(holdings.keys()) + add_tickers))
    prices = _fetch_prices(all_tickers)

    # Before state
    nav_before = cash + sum(s * prices.get(t, 0) for t, s in holdings.items())
    sectors_before = {}
    for t, s in holdings.items():
        sector = get_sector(t)
        val = s * prices.get(t, 0)
        sectors_before[sector] = sectors_before.get(sector, 0) + val

    before = {
        "nav": round(nav_before, 0),
        "cash": round(cash, 0),
        "holdings_count": len(holdings),
        "sector_exposure": {
            k: round(v / nav_before * 100, 1) if nav_before > 0 else 0
            for k, v in sorted(sectors_before.items(), key=lambda x: -x[1])
        },
    }

    # Apply removals
    freed_cash = 0.0
    sim_holdings = dict(holdings)
    for ticker in remove_tickers:
        if ticker in sim_holdings:
            shares = sim_holdings.pop(ticker)
            freed_cash += shares * prices.get(ticker, 0)

    available_cash = cash + freed_cash

    # Apply additions
    warnings = []
    if add_tickers:
        cash_per_stock = available_cash / len(add_tickers) if add_tickers else 0
        for ticker in add_tickers:
            price = prices.get(ticker, 0)
            if price <= 0:
                warnings.append(f"No price data for {ticker} — skipped")
                continue
            shares = int(cash_per_stock / price)
            if shares > 0:
                sim_holdings[ticker] = sim_holdings.get(ticker, 0) + shares
                available_cash -= shares * price

    # After state
    nav_after = available_cash + sum(s * prices.get(t, 0) for t, s in sim_holdings.items())
    sectors_after = {}
    for t, s in sim_holdings.items():
        sector = get_sector(t)
        val = s * prices.get(t, 0)
        sectors_after[sector] = sectors_after.get(sector, 0) + val

    after = {
        "nav": round(nav_after, 0),
        "cash": round(available_cash, 0),
        "holdings_count": len(sim_holdings),
        "sector_exposure": {
            k: round(v / nav_after * 100, 1) if nav_after > 0 else 0
            for k, v in sorted(sectors_after.items(), key=lambda x: -x[1])
        },
    }

    # Check constraints
    max_sector_pct = cfg.portfolio.max_sector_exposure * 100
    for sector, pct in after["sector_exposure"].items():
        if pct > max_sector_pct:
            warnings.append(f"Sector '{sector}' at {pct:.0f}% exceeds {max_sector_pct:.0f}% cap")

    max_pos_pct = cfg.portfolio.max_position_weight * 100
    for ticker, shares in sim_holdings.items():
        value = shares * prices.get(ticker, 0)
        weight = (value / nav_after * 100) if nav_after > 0 else 0
        if weight > max_pos_pct:
            warnings.append(f"{ticker.replace('.NS', '')} at {weight:.1f}% exceeds {max_pos_pct:.0f}% position limit")

    # Delta
    delta = {
        "nav": round(nav_after - nav_before, 0),
        "cash": round(available_cash - cash, 0),
        "holdings_count": len(sim_holdings) - len(holdings),
    }

    return WhatIfResult(before=before, after=after, delta=delta, warnings=warnings)
