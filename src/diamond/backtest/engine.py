"""Walk-forward backtest engine.

Simulates strategy execution over historical periods with:
  - Temporal isolation: screener only sees data up to screen_end (no look-ahead)
  - Survivorship filter: skips tickers with no data before window start
  - Position continuity: carries positions across windows, only trades the delta
  - Calendar-month windows: uses relativedelta for proper month alignment
  - Realistic costs: applies Indian market transaction costs on every trade
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from diamond.data import market
from diamond.execution.costs import calculate_costs

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Result of a single backtest window."""

    window_id: int
    start: str
    end: str
    initial_nav: float
    final_nav: float
    return_pct: float
    num_trades: int
    total_fees: float
    holdings_count: int
    nav_history: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class BacktestResult:
    """Aggregate result across all windows."""

    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_nav: float
    windows: list[WindowResult] = field(default_factory=list)
    nav_history: list[tuple[str, float]] = field(default_factory=list)
    benchmark_nav: list[tuple[str, float]] = field(default_factory=list)
    survivorship_filtered: int = 0  # tickers removed due to no data in window


def _get_hold_data(
    tickers: list[str],
    hold_start: str,
    hold_end: str,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Download prices and compute ADV for the holding period.

    Returns:
        (prices_df, adv_dict) where adv_dict maps ticker -> avg daily traded value in INR.
    """
    hold_start_dt = datetime.strptime(hold_start, "%Y-%m-%d")
    hold_end_dt = datetime.strptime(hold_end, "%Y-%m-%d")
    buffer_start = (hold_start_dt - relativedelta(days=7)).strftime("%Y-%m-%d")
    buffer_end = (hold_end_dt + relativedelta(days=7)).strftime("%Y-%m-%d")

    try:
        prices_df, volume_df = market.download_ohlcv_daterange(
            tickers,
            start=buffer_start,
            end=buffer_end,
            use_cache=True,
        )
    except Exception:
        # Fallback: price-only download (volume unavailable)
        prices_df = market.download_prices_daterange(
            tickers,
            start=buffer_start,
            end=buffer_end,
            use_cache=True,
        )
        volume_df = pd.DataFrame()

    prices_df.index = pd.to_datetime(prices_df.index)
    mask = (prices_df.index >= hold_start) & (prices_df.index <= hold_end)
    prices_df = prices_df.loc[mask]

    # Compute average daily value (price * volume) for each ticker
    adv: dict[str, float] = {}
    if not volume_df.empty:
        volume_df.index = pd.to_datetime(volume_df.index)
        vol_mask = (volume_df.index >= hold_start) & (volume_df.index <= hold_end)
        vol_window = volume_df.loc[vol_mask]
        for ticker in tickers:
            if ticker in prices_df.columns and ticker in vol_window.columns:
                daily_value = (prices_df[ticker] * vol_window[ticker]).dropna()
                if len(daily_value) > 0:
                    adv[ticker] = float(daily_value.mean())

    return prices_df, adv


def _compute_target_shares(
    allocation: dict[str, float],
    prices: dict[str, float],
) -> dict[str, int]:
    """Convert INR allocation to share counts using given prices."""
    shares: dict[str, int] = {}
    for ticker, amount in allocation.items():
        price = prices.get(ticker)
        if price and price > 0:
            n = int(amount / price)
            if n > 0:
                shares[ticker] = n
    return shares


def _simulate_window(
    strategy: object,
    window_id: int,
    screen_end: str,
    hold_start: str,
    hold_end: str,
    capital: float,
    prev_shares: dict[str, int],
    prev_cash: float | None,
) -> tuple[WindowResult, dict[str, int], float, int]:
    """Simulate a single walk-forward window.

    Args:
        strategy: Strategy implementing screen() + allocate().
        window_id: Numeric window identifier.
        screen_end: Date up to which screening data is available (prevents look-ahead).
        hold_start: Start of holding period.
        hold_end: End of holding period.
        capital: Total NAV (cash + holdings) at start of window.
        prev_shares: Shares carried from previous window.
        prev_cash: Cash carried from previous window (None for first window).

    Returns:
        (WindowResult, ending_shares, ending_cash, survivorship_dropped_count)
    """
    logger.info(f"Window {window_id}: screen<={screen_end}, hold {hold_start}->{hold_end}")

    empty_result = WindowResult(
        window_id=window_id,
        start=hold_start,
        end=hold_end,
        initial_nav=capital,
        final_nav=capital,
        return_pct=0.0,
        num_trades=0,
        total_fees=0.0,
        holdings_count=0,
    )

    # --- Screen phase ---
    # Pass end_date to strategy.screen() for temporal isolation.
    # Strategies that use the screener forward it to prevent look-ahead bias.
    # Strategies with a fixed universe (e.g. baseline) ignore it.
    try:
        candidates = strategy.screen(pd.DataFrame(), end_date=screen_end)  # type: ignore
    except TypeError:
        # Strategy doesn't accept end_date — call without it
        candidates = strategy.screen(pd.DataFrame())  # type: ignore
    except Exception as e:
        logger.error(f"Window {window_id}: screening failed: {e}")
        candidates = pd.DataFrame()

    if hasattr(candidates, "empty") and candidates.empty:
        logger.warning(f"Window {window_id}: screening produced no candidates")
        return empty_result, prev_shares, prev_cash if prev_cash is not None else capital, 0

    # --- Allocate phase ---
    allocation = strategy.allocate(candidates, capital)  # type: ignore
    if not allocation:
        logger.warning(f"Window {window_id}: allocation produced no positions")
        return empty_result, prev_shares, prev_cash if prev_cash is not None else capital, 0

    # --- Download holding period prices + volume ---
    all_tickers = list(set(list(allocation.keys()) + list(prev_shares.keys())))
    try:
        hold_prices, adv = _get_hold_data(all_tickers, hold_start, hold_end)
    except Exception as e:
        logger.error(f"Window {window_id}: price download failed: {e}")
        return empty_result, prev_shares, prev_cash if prev_cash is not None else capital, 0

    if hold_prices.empty or len(hold_prices) < 2:
        logger.warning(f"Window {window_id}: insufficient price data")
        return empty_result, prev_shares, prev_cash if prev_cash is not None else capital, 0

    # --- Get entry-day prices + survivorship filter ---
    entry_prices: dict[str, float] = {}
    survivorship_dropped: list[str] = []
    for ticker in all_tickers:
        if ticker in hold_prices.columns:
            col = hold_prices[ticker].dropna()
            if len(col) > 0:
                entry_prices[ticker] = float(col.iloc[0])
            elif ticker in allocation:
                survivorship_dropped.append(ticker)
        elif ticker in allocation:
            survivorship_dropped.append(ticker)

    if survivorship_dropped:
        logger.info(
            f"Window {window_id}: survivorship filter dropped "
            f"{len(survivorship_dropped)} tickers with no data: "
            f"{survivorship_dropped[:5]}{'...' if len(survivorship_dropped) > 5 else ''}"
        )
        # Remove from allocation so we don't try to buy them
        for t in survivorship_dropped:
            allocation.pop(t, None)

    # --- Determine starting cash ---
    if prev_cash is not None:
        cash = prev_cash
    else:
        # First window: all capital is cash
        cash = capital

    # --- Compute target shares from allocation ---
    target_shares = _compute_target_shares(allocation, entry_prices)

    # --- Trade the delta (sell what we don't need, buy what we need) ---
    total_fees = 0.0
    num_trades = 0

    # Track actual shares held after trading
    current_shares: dict[str, int] = dict(prev_shares)

    # Sells first (frees cash)
    for ticker in list(current_shares.keys()):
        target_qty = target_shares.get(ticker, 0)
        held_qty = current_shares[ticker]
        if held_qty > target_qty:
            sell_qty = held_qty - target_qty
            price = entry_prices.get(ticker)
            if price and price > 0:
                sell_value = sell_qty * price
                costs = calculate_costs("SELL", sell_value, adv.get(ticker))
                cash += sell_value - costs.total
                total_fees += costs.total
                num_trades += 1
                if target_qty > 0:
                    current_shares[ticker] = target_qty
                else:
                    del current_shares[ticker]

    # Then buys
    for ticker, target_qty in target_shares.items():
        held_qty = current_shares.get(ticker, 0)
        if target_qty > held_qty:
            buy_qty = target_qty - held_qty
            price = entry_prices.get(ticker)
            if price and price > 0:
                buy_value = buy_qty * price
                ticker_adv = adv.get(ticker)
                costs = calculate_costs("BUY", buy_value, ticker_adv)
                total_cost = buy_value + costs.total
                if total_cost > cash:
                    buy_qty = int((cash - costs.total) / price)
                    if buy_qty <= 0:
                        continue
                    buy_value = buy_qty * price
                    costs = calculate_costs("BUY", buy_value, ticker_adv)
                    total_cost = buy_value + costs.total
                cash -= total_cost
                total_fees += costs.total
                num_trades += 1
                current_shares[ticker] = held_qty + buy_qty

    # --- Track NAV through holding period ---
    nav_history: list[tuple[str, float]] = []
    held_tickers = [t for t in current_shares if t in hold_prices.columns]
    for date, row in hold_prices.iterrows():
        # Count how many held tickers have valid prices on this day
        valid_count = sum(1 for t in held_tickers if bool(pd.notna(row.get(t))))
        # Skip days where less than half of holdings have prices (weekend/holiday artifacts)
        if held_tickers and valid_count < len(held_tickers) * 0.5:
            continue
        holdings_value = sum(
            current_shares.get(t, 0) * float(row.get(t) or 0) for t in held_tickers if bool(pd.notna(row.get(t)))
        )
        nav = cash + holdings_value
        nav_history.append((date.strftime("%Y-%m-%d"), round(nav, 2)))  # type: ignore

    # --- Compute final NAV (no liquidation — positions carry forward) ---
    exit_prices: dict[str, float] = {}
    for ticker in current_shares:
        if ticker in hold_prices.columns:
            col = hold_prices[ticker].dropna()
            if len(col) > 0:
                exit_prices[ticker] = float(col.iloc[-1])

    final_holdings_value = sum(current_shares.get(t, 0) * exit_prices.get(t, 0) for t in current_shares)
    final_nav = round(cash + final_holdings_value, 2)
    return_pct = round((final_nav / capital - 1) * 100, 2) if capital > 0 else 0.0

    logger.info(
        f"Window {window_id}: {return_pct:+.2f}% return, "
        f"{num_trades} trades, fees={total_fees:.2f}, "
        f"{len(current_shares)} holdings"
    )

    result = WindowResult(
        window_id=window_id,
        start=hold_start,
        end=hold_end,
        initial_nav=round(capital, 2),
        final_nav=final_nav,
        return_pct=return_pct,
        num_trades=num_trades,
        total_fees=round(total_fees, 2),
        holdings_count=len(current_shares),
        nav_history=nav_history,
    )
    return result, current_shares, cash, len(survivorship_dropped)


def _compute_benchmark_nav(
    start_date: str,
    end_date: str,
    initial_capital: float,
) -> list[tuple[str, float]]:
    """Compute buy-and-hold Nifty 50 benchmark NAV for comparison.

    Downloads Nifty 50 index prices and normalizes to the same starting capital.
    Returns empty list on failure (fail-open — benchmark is optional).
    """
    try:
        from diamond.config import get_config

        benchmark_ticker = get_config().passive.index_ticker

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        buffer_start = (start_dt - relativedelta(days=7)).strftime("%Y-%m-%d")
        buffer_end = (end_dt + relativedelta(days=7)).strftime("%Y-%m-%d")

        bench_prices = market.download_prices_daterange(
            [benchmark_ticker],
            start=buffer_start,
            end=buffer_end,
            use_cache=True,
        )
        bench_prices.index = pd.to_datetime(bench_prices.index)
        mask = (bench_prices.index >= start_date) & (bench_prices.index <= end_date)
        bench_prices = bench_prices.loc[mask]

        if bench_prices.empty or len(bench_prices) < 2:
            return []

        col = bench_prices.iloc[:, 0].dropna()
        if len(col) < 2:
            return []

        # Normalize: NAV = initial_capital * (price / first_price)
        first_price = float(col.iloc[0])
        if first_price <= 0:
            return []

        nav_history: list[tuple[str, float]] = []
        for dt, price in col.items():
            nav = round(initial_capital * (float(price) / first_price), 2)
            date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
            nav_history.append((date_str, nav))

        logger.info(
            f"Benchmark ({benchmark_ticker}): {len(nav_history)} data points, final NAV {nav_history[-1][1]:,.2f}"
        )
        return nav_history

    except Exception as e:
        logger.warning(f"Benchmark computation failed (non-fatal): {e}")
        return []


def run_backtest(
    strategy: object,
    strategy_name: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100_000,
    window_months: int = 6,
    step_months: int = 6,
    screener_lookback_days: int = 504,
) -> BacktestResult:
    """Run walk-forward backtest over a date range.

    Divides the period into non-overlapping windows of `window_months`.
    Each window: screen -> allocate -> trade delta -> hold -> measure.
    Positions carry across windows — only the delta is traded.

    Args:
        strategy: Strategy implementing screen() + allocate().
        strategy_name: Name for reporting.
        start_date: Backtest start (YYYY-MM-DD).
        end_date: Backtest end (YYYY-MM-DD).
        initial_capital: Starting capital in INR.
        window_months: Holding period per window in months.
        step_months: Step size between windows (usually == window_months).
        screener_lookback_days: Historical data available for screening.

    Returns:
        BacktestResult with per-window and aggregate metrics.
    """
    result = BacktestResult(
        strategy=strategy_name,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        final_nav=initial_capital,
    )

    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    capital = initial_capital
    window_id = 0
    total_survivorship_filtered = 0

    # Position continuity across windows
    carried_shares: dict[str, int] = {}
    carried_cash: float | None = None

    while current_date < end_dt:
        # Use calendar months instead of days*30
        window_end_dt = current_date + relativedelta(months=window_months)
        if window_end_dt > end_dt:
            window_end_dt = end_dt

        if (window_end_dt - current_date).days < 20:
            break

        screen_end = current_date.strftime("%Y-%m-%d")
        hold_start = current_date.strftime("%Y-%m-%d")
        hold_end = window_end_dt.strftime("%Y-%m-%d")

        window_result, carried_shares, carried_cash, surv_dropped = _simulate_window(
            strategy=strategy,
            window_id=window_id,
            screen_end=screen_end,
            hold_start=hold_start,
            hold_end=hold_end,
            capital=capital,
            prev_shares=carried_shares,
            prev_cash=carried_cash,
        )

        result.windows.append(window_result)
        result.nav_history.extend(window_result.nav_history)
        total_survivorship_filtered += surv_dropped

        capital = window_result.final_nav
        window_id += 1
        current_date = window_end_dt

    result.final_nav = capital
    result.survivorship_filtered = total_survivorship_filtered

    # --- Benchmark: buy-and-hold Nifty 50 ---
    result.benchmark_nav = _compute_benchmark_nav(
        start_date,
        end_date,
        initial_capital,
    )

    logger.info(
        f"Backtest complete: {strategy_name}, {len(result.windows)} windows, "
        f"final NAV={capital:,.2f} from {initial_capital:,.2f}"
        f"{f', survivorship filtered {total_survivorship_filtered} tickers' if total_survivorship_filtered else ''}"
    )

    return result
