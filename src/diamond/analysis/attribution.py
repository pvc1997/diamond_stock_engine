"""Performance attribution - stock-level and sector-level (Brinson) decomposition.

Computes contribution analysis for portfolio holdings against a benchmark,
with support for multiple lookback windows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from diamond.data import market
from diamond.data.ledger import Ledger
from diamond.data.universe import NIFTY_50, get_sector

logger = logging.getLogger(__name__)

ANN_FACTOR = 252  # Trading days per year


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockAttribution:
    ticker: str
    sector: str
    weight: float  # Portfolio weight (0-1)
    stock_return: float  # Return over period
    contribution: float  # Weight x return contribution to portfolio
    benchmark_weight: float  # Weight in benchmark (0 if not in benchmark)
    active_weight: float  # Portfolio weight - benchmark weight


@dataclass(frozen=True)
class SectorAttribution:
    sector: str
    portfolio_weight: float
    benchmark_weight: float
    portfolio_return: float
    benchmark_return: float
    allocation_effect: float
    selection_effect: float
    interaction_effect: float
    total_effect: float
    stock_count: int


@dataclass
class AttributionReport:
    strategy: str
    period: str  # e.g., "3M", "1Y", "2025-01-01 to 2025-03-01"
    start_date: str
    end_date: str
    portfolio_return: float
    benchmark_return: float
    active_return: float  # portfolio - benchmark
    stock_attributions: list[StockAttribution] = field(default_factory=list)
    sector_attributions: list[SectorAttribution] = field(default_factory=list)
    top_contributors: list[StockAttribution] = field(default_factory=list)
    bottom_contributors: list[StockAttribution] = field(default_factory=list)
    tracking_error: float = 0.0


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

_PERIOD_DAYS = {
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
}


def _parse_period(period: str) -> tuple[str, str, str]:
    """Parse period string into (start_date, end_date, label).

    Supported formats:
        1M, 3M, 6M, 1Y  - calendar days lookback from today
        YTD              - Jan 1 of current year to today
        YYYY-MM-DD:YYYY-MM-DD - custom date range

    Returns:
        (start_date, end_date, human_label)  all dates as YYYY-MM-DD strings.
    """
    today = date.today()
    end_str = today.isoformat()

    upper = period.upper()
    if upper in _PERIOD_DAYS:
        start = today - timedelta(days=_PERIOD_DAYS[upper])
        return start.isoformat(), end_str, upper

    if upper == "YTD":
        start = date(today.year, 1, 1)
        return start.isoformat(), end_str, "YTD"

    # Custom range: YYYY-MM-DD:YYYY-MM-DD
    if ":" in period:
        parts = period.split(":")
        if len(parts) == 2:
            start_str, custom_end = parts[0].strip(), parts[1].strip()
            # Validate date format
            datetime.strptime(start_str, "%Y-%m-%d")
            datetime.strptime(custom_end, "%Y-%m-%d")
            label = f"{start_str} to {custom_end}"
            return start_str, custom_end, label

    raise ValueError(f"Invalid period '{period}'. Use 1M, 3M, 6M, 1Y, YTD, or YYYY-MM-DD:YYYY-MM-DD")


# ---------------------------------------------------------------------------
# Core computation helpers (pure functions)
# ---------------------------------------------------------------------------


def _benchmark_weights(benchmark_tickers: list[str]) -> dict[str, float]:
    """Equal-weight benchmark weights for Nifty 50 constituents."""
    if not benchmark_tickers:
        return {}
    w = round(1.0 / len(benchmark_tickers), 4)
    return {t: w for t in benchmark_tickers}


def _compute_stock_attributions(
    holdings: dict[str, int],
    start_prices: dict[str, float],
    end_prices: dict[str, float],
    bm_weights: dict[str, float],
) -> list[StockAttribution]:
    """Compute per-stock attribution from known prices."""
    # Portfolio value at start (holdings * start_price)
    port_value_start = sum(
        shares * start_prices.get(t, 0.0) for t, shares in holdings.items() if start_prices.get(t, 0.0) > 0
    )
    if port_value_start == 0:
        return []

    results: list[StockAttribution] = []
    for ticker, shares in holdings.items():
        p_start = start_prices.get(ticker, 0.0)
        p_end = end_prices.get(ticker, 0.0)
        if p_start <= 0:
            continue

        weight = round((shares * p_start) / port_value_start, 4)
        stock_ret = round((p_end - p_start) / p_start, 4)
        contribution = round(weight * stock_ret, 4)
        bm_w = bm_weights.get(ticker, 0.0)
        active_w = round(weight - bm_w, 4)

        results.append(
            StockAttribution(
                ticker=ticker,
                sector=get_sector(ticker),
                weight=weight,
                stock_return=stock_ret,
                contribution=contribution,
                benchmark_weight=bm_w,
                active_weight=active_w,
            )
        )

    return results


def _compute_sector_attributions(
    stock_attrs: list[StockAttribution],
    bm_weights: dict[str, float],
    bm_returns: dict[str, float],
    benchmark_total_return: float,
) -> list[SectorAttribution]:
    """Brinson-style sector attribution.

    allocation  = (Wp_s - Wb_s) * (Rb_s - Rb)
    selection   = Wp_s * (Rp_s - Rb_s)
    interaction = (Wp_s - Wb_s) * (Rp_s - Rb_s)
    total       = allocation + selection + interaction
    """
    # Aggregate portfolio by sector
    port_sector_weight: dict[str, float] = {}
    port_sector_contrib: dict[str, float] = {}
    port_sector_count: dict[str, int] = {}

    for sa in stock_attrs:
        sec = sa.sector
        port_sector_weight[sec] = port_sector_weight.get(sec, 0.0) + sa.weight
        port_sector_contrib[sec] = port_sector_contrib.get(sec, 0.0) + sa.contribution
        port_sector_count[sec] = port_sector_count.get(sec, 0) + 1

    # Portfolio sector return = contribution / weight
    port_sector_return: dict[str, float] = {}
    for sec in port_sector_weight:
        w = port_sector_weight[sec]
        port_sector_return[sec] = round(port_sector_contrib[sec] / w, 4) if w > 0 else 0.0

    # Aggregate benchmark by sector
    bm_sector_weight: dict[str, float] = {}
    bm_sector_contrib: dict[str, float] = {}

    for ticker, w in bm_weights.items():
        sec = get_sector(ticker)
        ret = bm_returns.get(ticker, 0.0)
        bm_sector_weight[sec] = bm_sector_weight.get(sec, 0.0) + w
        bm_sector_contrib[sec] = bm_sector_contrib.get(sec, 0.0) + w * ret

    bm_sector_return: dict[str, float] = {}
    for sec in bm_sector_weight:
        w = bm_sector_weight[sec]
        bm_sector_return[sec] = round(bm_sector_contrib[sec] / w, 4) if w > 0 else 0.0

    # All sectors across both portfolio and benchmark
    all_sectors = set(port_sector_weight.keys()) | set(bm_sector_weight.keys())

    results: list[SectorAttribution] = []
    for sec in sorted(all_sectors):
        wp = round(port_sector_weight.get(sec, 0.0), 4)
        wb = round(bm_sector_weight.get(sec, 0.0), 4)
        rp = round(port_sector_return.get(sec, 0.0), 4)
        rb = round(bm_sector_return.get(sec, 0.0), 4)
        rb_total = benchmark_total_return

        allocation = round((wp - wb) * (rb - rb_total), 4)
        selection = round(wp * (rp - rb), 4)
        interaction = round((wp - wb) * (rp - rb), 4)
        total = round(allocation + selection + interaction, 4)

        results.append(
            SectorAttribution(
                sector=sec,
                portfolio_weight=wp,
                benchmark_weight=wb,
                portfolio_return=rp,
                benchmark_return=rb,
                allocation_effect=allocation,
                selection_effect=selection,
                interaction_effect=interaction,
                total_effect=total,
                stock_count=port_sector_count.get(sec, 0),
            )
        )

    return results


def _compute_tracking_error(
    portfolio_daily: pd.Series,
    benchmark_daily: pd.Series,
) -> float:
    """Annualized tracking error = std(active_daily_returns) * sqrt(252)."""
    # Align on common dates
    common = portfolio_daily.index.intersection(benchmark_daily.index)
    if len(common) < 2:
        return 0.0
    active = portfolio_daily.loc[common] - benchmark_daily.loc[common]
    te = float(active.std() * np.sqrt(ANN_FACTOR))
    return round(te, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_attribution(
    strategy: str,
    period: str = "3M",
    benchmark: str = "^NSEI",
    current_prices: dict[str, float] | None = None,
) -> AttributionReport:
    """Compute stock-level and sector-level performance attribution.

    Args:
        strategy: Strategy name (used to load ledger).
        period: Lookback window - 1M, 3M, 6M, 1Y, YTD, or YYYY-MM-DD:YYYY-MM-DD.
        benchmark: Benchmark ticker (default Nifty 50 index).
        current_prices: Optional dict of current prices to avoid re-fetching.

    Returns:
        AttributionReport with full decomposition.
    """
    start_date, end_date, label = _parse_period(period)
    logger.info("Attribution: %s %s (%s to %s)", strategy, label, start_date, end_date)

    # Load holdings from ledger
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    # Empty portfolio edge case
    if not holdings:
        logger.warning("No holdings for strategy '%s'", strategy)
        return AttributionReport(
            strategy=strategy,
            period=label,
            start_date=start_date,
            end_date=end_date,
            portfolio_return=0.0,
            benchmark_return=0.0,
            active_return=0.0,
        )

    tickers = list(holdings.keys())

    # Benchmark constituents (Nifty 50)
    bm_tickers = list(NIFTY_50)
    bm_weights = _benchmark_weights(bm_tickers)

    # All tickers we need prices for (portfolio + benchmark + index)
    all_tickers = sorted(set(tickers + bm_tickers))

    # Download price history for the period
    logger.info("Downloading prices for %d tickers (%s to %s)", len(all_tickers), start_date, end_date)
    prices_df = market.download_prices_daterange(
        all_tickers,
        start=start_date,
        end=end_date,
        use_cache=True,
    )

    # Also download the benchmark index for tracking error
    bm_index_prices = market.download_prices_daterange(
        [benchmark],
        start=start_date,
        end=end_date,
        use_cache=True,
    )

    # Extract start and end prices
    if prices_df.empty:
        logger.warning("No price data available for period %s to %s", start_date, end_date)
        return AttributionReport(
            strategy=strategy,
            period=label,
            start_date=start_date,
            end_date=end_date,
            portfolio_return=0.0,
            benchmark_return=0.0,
            active_return=0.0,
        )

    start_prices: dict[str, float] = {}
    end_prices: dict[str, float] = {}
    for col in prices_df.columns:
        series = prices_df[col].dropna()
        if len(series) >= 2:
            start_prices[col] = float(series.iloc[0])
            end_prices[col] = float(series.iloc[-1])

    # Override end prices with current_prices if provided
    if current_prices:
        for t, p in current_prices.items():
            if t in end_prices or t in holdings:
                end_prices[t] = p

    # Stock-level attribution
    stock_attrs = _compute_stock_attributions(holdings, start_prices, end_prices, bm_weights)

    # Portfolio return = sum of contributions
    portfolio_return = round(sum(sa.contribution for sa in stock_attrs), 4)

    # Benchmark return (equal-weight)
    bm_returns: dict[str, float] = {}
    bm_total_contribs = 0.0
    bm_total_weight = 0.0
    for ticker, w in bm_weights.items():
        p_s = start_prices.get(ticker, 0.0)
        p_e = end_prices.get(ticker, 0.0)
        if p_s > 0:
            ret = round((p_e - p_s) / p_s, 4)
            bm_returns[ticker] = ret
            bm_total_contribs += w * ret
            bm_total_weight += w

    benchmark_return = round(bm_total_contribs, 4) if bm_total_weight > 0 else 0.0
    active_return = round(portfolio_return - benchmark_return, 4)

    # Sector-level attribution (Brinson)
    sector_attrs = _compute_sector_attributions(
        stock_attrs,
        bm_weights,
        bm_returns,
        benchmark_return,
    )

    # Top / bottom contributors
    sorted_by_contrib = sorted(stock_attrs, key=lambda s: s.contribution, reverse=True)
    top_5 = sorted_by_contrib[:5]
    bottom_5 = sorted(stock_attrs, key=lambda s: s.contribution)[:5]

    # Tracking error
    tracking_error = 0.0
    if not bm_index_prices.empty and len(prices_df) >= 2:
        # Build portfolio daily returns (equal to weighted sum of stock daily returns)
        port_tickers_in_prices = [t for t in tickers if t in prices_df.columns]
        if port_tickers_in_prices:
            port_prices = prices_df[port_tickers_in_prices]
            # Weights for each ticker (based on start value)
            port_value_start = sum(holdings[t] * start_prices.get(t, 0.0) for t in port_tickers_in_prices)
            if port_value_start > 0:
                weights_series = pd.Series(
                    {t: (holdings[t] * start_prices.get(t, 0.0)) / port_value_start for t in port_tickers_in_prices}
                )
                # Daily returns
                daily_ret = port_prices.pct_change().dropna()
                port_daily = daily_ret.multiply(weights_series).sum(axis=1)

                bm_col = bm_index_prices.columns[0]
                bm_daily = bm_index_prices[bm_col].pct_change().dropna()

                tracking_error = _compute_tracking_error(port_daily, pd.Series(bm_daily))

    return AttributionReport(
        strategy=strategy,
        period=label,
        start_date=start_date,
        end_date=end_date,
        portfolio_return=portfolio_return,
        benchmark_return=benchmark_return,
        active_return=active_return,
        stock_attributions=stock_attrs,
        sector_attributions=sector_attrs,
        top_contributors=top_5,
        bottom_contributors=bottom_5,
        tracking_error=tracking_error,
    )
