"""Diamond Dashboard - Rich terminal portfolio dashboard.

All-in-one view: action panel, holdings, market pulse, risk metrics.
Usage: diamond dashboard [strategy] [--capital N]
"""

from __future__ import annotations

import contextlib
import logging
from contextlib import contextmanager
from datetime import datetime

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from diamond.config import get_config
from diamond.data.ledger import Ledger
from diamond.data.universe import get_sector

logger = logging.getLogger(__name__)
console = Console()


@contextmanager
def _suppress_noisy_loggers():
    """Temporarily silence yfinance and urllib3 logs during dashboard render."""
    noisy = ["yfinance", "urllib3", "peewee"]
    old_levels = {name: logging.getLogger(name).level for name in noisy}
    for name in noisy:
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        for name, level in old_levels.items():
            logging.getLogger(name).setLevel(level)


# ---------------------------------------------------------------------------
# Data fetching helpers
# ---------------------------------------------------------------------------


def _fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices for tickers."""
    from diamond.data.market import download_prices

    prices: dict[str, float] = {}
    if not tickers:
        return prices
    try:
        df = download_prices(tickers, period_days=5, use_cache=True)
        for col in df.columns:
            series = df[col].dropna()
            if len(series) > 0:
                prices[col] = float(series.iloc[-1])
    except Exception as e:
        logger.warning(f"Failed to fetch prices: {e}")
    return prices


def _days_since_rebalance(ledger: Ledger) -> int | None:
    """Days since last rebalance, or None if never rebalanced."""
    last = ledger.get_last_rebalance()
    if not last:
        return None
    try:
        last_date = datetime.strptime(last[:10], "%Y-%m-%d")
        return (datetime.now() - last_date).days
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tier 1: Action Panel
# ---------------------------------------------------------------------------


def _build_action_panel(
    strategy: str,
    ledger: Ledger,
    holdings: dict[str, int],
    prices: dict[str, float],
    capital: float,
) -> Panel:
    """Build the top-level action summary panel."""
    days = _days_since_rebalance(ledger)
    cfg = get_config()

    # Determine rebalance frequency based on strategy
    if strategy == "gods_plan":
        rebal_freq = cfg.gods_plan.rebalance_days
    else:
        rebal_freq = cfg.rebalance.rebalance_frequency_days

    # Action determination
    action_text = Text()
    if not holdings:
        action_text.append("  SETUP REQUIRED", style="bold yellow")
        action_text.append(f" - Run: diamond paper {strategy} --capital {int(capital)}")
    elif days is not None and days >= rebal_freq:
        action_text.append("  REBALANCE DUE", style="bold red")
        action_text.append(f" - {days} days since last rebalance (target: {rebal_freq}d)")
    elif days is not None:
        days_left = rebal_freq - days
        action_text.append("  HOLD", style="bold green")
        action_text.append(f" - Rebalance in {days_left} days")
    else:
        action_text.append("  HOLD", style="bold green")
        action_text.append(" - No rebalance history")

    # Check for stop-loss breaches
    stop_loss_tickers = []
    threshold = cfg.risk.stop_loss_threshold
    for ticker, _shares in holdings.items():
        avg = ledger.get_avg_price(ticker)
        cmp = prices.get(ticker, 0)
        if avg > 0 and cmp > 0 and (avg - cmp) / avg >= threshold:
            stop_loss_tickers.append(ticker)

    if stop_loss_tickers:
        action_text.append("\n")
        action_text.append("  STOP LOSS TRIGGERED: ", style="bold red")
        action_text.append(", ".join(stop_loss_tickers), style="red")
        action_text.append(f" (>{threshold:.0%} loss from avg price)")

    return Panel(
        action_text,
        title="[bold]ACTION[/bold]",
        border_style="cyan",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tier 1: Holdings Table
# ---------------------------------------------------------------------------


def _build_holdings_table(
    ledger: Ledger,
    holdings: dict[str, int],
    prices: dict[str, float],
) -> Table:
    """Build detailed holdings table with P&L and signals."""
    table = Table(
        title="Holdings",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        pad_edge=False,
    )
    table.add_column("Stock", style="cyan", min_width=14)
    table.add_column("Sector", style="dim", min_width=12)
    table.add_column("Qty", justify="right", min_width=4)
    table.add_column("Avg", justify="right", min_width=8)
    table.add_column("CMP", justify="right", min_width=8)
    table.add_column("P&L %", justify="right", min_width=8)
    table.add_column("Value", justify="right", min_width=10)
    table.add_column("Wt %", justify="right", min_width=6)
    table.add_column("Signal", min_width=8)

    # Calculate total portfolio value
    nav = ledger.get_portfolio_value(prices)
    cfg = get_config()
    stop_threshold = cfg.risk.stop_loss_threshold

    rows = []
    for ticker, shares in sorted(holdings.items()):
        avg = ledger.get_avg_price(ticker)
        cmp = prices.get(ticker, 0)
        value = shares * cmp
        pnl_pct = ((cmp - avg) / avg * 100) if avg > 0 and cmp > 0 else 0
        weight = (value / nav * 100) if nav > 0 else 0
        sector = get_sector(ticker)

        # Signal
        if avg > 0 and cmp > 0 and (avg - cmp) / avg >= stop_threshold:
            signal = "[bold red]SELL[/bold red]"
        elif avg > 0 and cmp > 0 and (avg - cmp) / avg >= stop_threshold * 0.7:
            signal = "[yellow]WATCH[/yellow]"
        elif pnl_pct > 50:
            signal = "[green]BOOK[/green]"
        else:
            signal = "[dim]HOLD[/dim]"

        # P&L color
        if pnl_pct >= 0:
            pnl_str = f"[green]+{pnl_pct:.1f}%[/green]"
        else:
            pnl_str = f"[red]{pnl_pct:.1f}%[/red]"

        rows.append((ticker, sector, shares, avg, cmp, pnl_pct, pnl_str, value, weight, signal))

    # Sort by value descending
    rows.sort(key=lambda r: r[7], reverse=True)

    for ticker, sector, shares, avg, cmp, _pnl_pct, pnl_str, value, weight, signal in rows:
        table.add_row(
            ticker.replace(".NS", ""),
            sector[:12] if sector != "Unknown" else "-",
            str(shares),
            f"{avg:,.1f}",
            f"{cmp:,.1f}" if cmp > 0 else "-",
            pnl_str,
            f"{value:,.0f}",
            f"{weight:.1f}",
            signal,
        )

    return table


# ---------------------------------------------------------------------------
# Tier 1: Portfolio Summary
# ---------------------------------------------------------------------------


def _build_portfolio_summary(
    ledger: Ledger,
    holdings: dict[str, int],
    prices: dict[str, float],
    capital: float,
) -> Panel:
    """Build portfolio summary bar."""
    nav = ledger.get_portfolio_value(prices)
    cash = ledger.get_cash()
    initial = ledger.get_initial_capital()
    total_fees = ledger.get_total_fees()
    holdings_value = nav - cash
    total_return = ((nav - initial) / initial * 100) if initial > 0 else 0

    if total_return >= 0:
        ret_str = f"[green]+{total_return:.1f}%[/green]"
    else:
        ret_str = f"[red]{total_return:.1f}%[/red]"

    text = Text()
    text.append(f"  NAV: {nav:,.0f} INR", style="bold")
    text.append(f"  |  Holdings: {holdings_value:,.0f}")
    text.append(f"  |  Cash: {cash:,.0f}")
    text.append("  |  Return: ")
    # Can't mix Text and markup easily, so build plain
    summary = (
        f"  NAV: {nav:,.0f} INR  |  "
        f"Holdings: {holdings_value:,.0f}  |  "
        f"Cash: {cash:,.0f}  |  "
        f"Return: {ret_str}  |  "
        f"Fees: {total_fees:,.0f}  |  "
        f"Stocks: {len(holdings)}"
    )

    return Panel(
        summary,
        border_style="blue",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tier 2: Market Pulse Panel
# ---------------------------------------------------------------------------


def _build_market_pulse_panel() -> Panel:
    """Build market pulse panel with regime and verdict."""
    from diamond.monitoring.market_pulse import get_market_pulse

    try:
        pulse = get_market_pulse()
    except Exception as e:
        return Panel(
            f"  [red]Failed to fetch market data: {e}[/red]",
            title="[bold]MARKET PULSE[/bold]",
            border_style="yellow",
        )

    # Verdict styling
    verdict_styles = {
        "DEPLOY": "bold green",
        "WAIT": "bold yellow",
        "DEFENSIVE": "bold red",
    }
    verdict_style = verdict_styles.get(pulse.verdict, "bold white")

    # VIX styling
    vix_styles = {
        "LOW": "green",
        "NORMAL": "white",
        "HIGH": "yellow",
        "EXTREME": "bold red",
    }
    vix_style = vix_styles.get(pulse.vix_regime, "white")

    # Trend styling
    trend_styles = {
        "BULLISH": "green",
        "BEARISH": "red",
        "SIDEWAYS": "yellow",
    }
    trend_style = trend_styles.get(pulse.trend, "white")

    # Breadth styling
    breadth_styles = {
        "STRONG": "green",
        "HEALTHY": "white",
        "WEAK": "yellow",
        "WASHOUT": "red",
    }
    breadth_style = breadth_styles.get(pulse.breadth_regime, "white")

    # Build content
    nifty_chg = pulse.nifty_change_pct
    nifty_color = "green" if nifty_chg >= 0 else "red"

    lines = [
        f"  [{verdict_style}]TODAY: {pulse.verdict}[/{verdict_style}]  (Score: {pulse.score:+d}/100)    Regime: [{trend_style}]{pulse.regime}[/{trend_style}]",
        "",
        f"  Nifty 50:  {pulse.nifty_price:,.0f}  [{nifty_color}]{nifty_chg:+.2f}%[/{nifty_color}]    "
        f"50 DMA: {pulse.nifty_50dma:,.0f}    200 DMA: {pulse.nifty_200dma:,.0f}    "
        f"Dist: {pulse.nifty_distance_200dma_pct:+.1f}%",
        f"  VIX:       [{vix_style}]{pulse.vix:.1f} ({pulse.vix_regime})[/{vix_style}]        "
        f"Breadth: [{breadth_style}]{pulse.breadth_pct:.0f}% ({pulse.breadth_regime})[/{breadth_style}]    "
        f"RSI: {pulse.nifty_rsi_14:.0f} ({pulse.momentum_regime})",
        "",
    ]

    # Top 3 reasons
    for reason in pulse.verdict_reasons[:4]:
        lines.append(f"  - {reason}")

    return Panel(
        "\n".join(lines),
        title="[bold]MARKET PULSE[/bold]",
        border_style="yellow",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tier 3: Risk Panel
# ---------------------------------------------------------------------------


def _build_risk_panel(
    strategy: str,
    holdings: dict[str, int],
    prices: dict[str, float],
) -> Panel:
    """Build risk metrics panel."""
    from diamond.data import market
    from diamond.monitoring.risk import compute_risk_report

    # Fetch historical prices for VaR/correlation
    tickers = list(holdings.keys())
    prices_df = None
    benchmark_returns = None

    if tickers:
        with contextlib.suppress(Exception):
            prices_df = market.download_prices(tickers, period_days=252, use_cache=True)

        with contextlib.suppress(Exception):
            bench = market.download_single("^NSEI", period_days=252)
            benchmark_returns = market.calculate_returns(bench)

    try:
        report = compute_risk_report(strategy, prices, prices_df, benchmark_returns)
    except Exception as e:
        return Panel(f"  [red]Risk computation failed: {e}[/red]", title="[bold]RISK[/bold]")

    # Drawdown color
    dd = report.drawdown_pct
    if dd >= 15:
        dd_str = f"[bold red]{dd:.1f}%[/bold red]"
    elif dd >= 10:
        dd_str = f"[yellow]{dd:.1f}%[/yellow]"
    else:
        dd_str = f"[green]{dd:.1f}%[/green]"

    lines = [
        f"  Drawdown: {dd_str} from HWM ({report.high_water_mark:,.0f})    "
        f"VaR 95%: {report.var_95:,.0f}    VaR 99%: {report.var_99:,.0f}    "
        f"CVaR: {report.cvar_95:,.0f}",
        f"  Beta: {report.beta:.2f}    "
        f"Vol: {report.volatility_annual:.1f}%    "
        f"Max Corr: {report.max_correlation:.2f}    "
        f"Avg Corr: {report.avg_correlation:.2f}",
    ]

    if report.signals:
        lines.append("")
        for sig in report.signals:
            if "CRITICAL" in sig:
                lines.append(f"  [bold red]{sig}[/bold red]")
            else:
                lines.append(f"  [yellow]{sig}[/yellow]")

    return Panel(
        "\n".join(lines),
        title="[bold]RISK[/bold]",
        border_style="red",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tier 1: Rebalance Trades Panel
# ---------------------------------------------------------------------------


def _build_rebalance_panel(
    strategy: str,
    ledger_name: str,
    holdings: dict[str, int],
    prices: dict[str, float],
    capital: float,
) -> Panel | None:
    """Show what trades would happen if rebalancing now."""
    from diamond.cli import _resolve_strategy

    ledger = Ledger(ledger_name)
    days = _days_since_rebalance(ledger)
    cfg = get_config()

    if strategy == "gods_plan":
        rebal_freq = cfg.gods_plan.rebalance_days
    else:
        rebal_freq = cfg.rebalance.rebalance_frequency_days

    # Only show if rebalance is due or within 7 days
    if days is not None and days < rebal_freq - 7:
        return None

    try:
        strat = _resolve_strategy(strategy)
        candidates = strat.screen(None)
        if hasattr(candidates, "empty") and candidates.empty:
            return None
        nav = ledger.get_portfolio_value(prices)
        alloc_capital = nav if nav > capital else capital
        target = strat.allocate(candidates, alloc_capital)
        if not target:
            return None
    except Exception as e:
        logger.warning(f"Failed to compute rebalance: {e}")
        return None

    # Compute trades needed
    buys: list[tuple[str, float]] = []
    sells: list[tuple[str, float]] = []

    all_tickers = set(list(holdings.keys()) + list(target.keys()))
    for ticker in all_tickers:
        current_value = holdings.get(ticker, 0) * prices.get(ticker, 0)
        target_value = target.get(ticker, 0)
        delta = target_value - current_value

        if delta > cfg.rebalance.min_trade_value:
            buys.append((ticker, delta))
        elif delta < -cfg.rebalance.min_trade_value:
            sells.append((ticker, delta))

    if not buys and not sells:
        return Panel(
            "  Portfolio is on target - no trades needed.",
            title="[bold]REBALANCE PREVIEW[/bold]",
            border_style="green",
            padding=(0, 1),
        )

    table = Table(box=box.SIMPLE, show_header=True, pad_edge=False)
    table.add_column("Action", min_width=5)
    table.add_column("Stock", min_width=14)
    table.add_column("Amount", justify="right", min_width=10)
    table.add_column("Est. Shares", justify="right", min_width=8)

    for ticker, delta in sorted(sells, key=lambda x: x[1]):
        price = prices.get(ticker, 0)
        est_shares = int(abs(delta) / price) if price > 0 else 0
        table.add_row(
            "[red]SELL[/red]",
            ticker.replace(".NS", ""),
            f"[red]{abs(delta):,.0f}[/red]",
            str(est_shares),
        )

    for ticker, delta in sorted(buys, key=lambda x: -x[1]):
        price = prices.get(ticker, 0)
        est_shares = int(delta / price) if price > 0 else 0
        table.add_row(
            "[green]BUY[/green]",
            ticker.replace(".NS", ""),
            f"[green]{delta:,.0f}[/green]",
            str(est_shares),
        )

    return Panel(
        table,
        title=f"[bold]REBALANCE PREVIEW[/bold] ({len(sells)} sells, {len(buys)} buys)",
        border_style="magenta",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Tier: P&L Summary
# ---------------------------------------------------------------------------


def _build_pnl_summary_panel(
    ledger: Ledger,
    holdings: dict[str, int],
    prices: dict[str, float],
) -> Panel:
    """Build P&L breakdown panel."""
    nav = ledger.get_portfolio_value(prices)
    cash = ledger.get_cash()
    initial = ledger.get_initial_capital()
    total_fees = ledger.get_total_fees()

    # Invested = sum(shares * avg_price) for current holdings
    total_invested = sum(shares * ledger.get_avg_price(t) for t, shares in holdings.items())
    current_value = sum(shares * prices.get(t, 0) for t, shares in holdings.items())
    unrealized_pnl = current_value - total_invested

    # Realized P&L = total_return - unrealized
    total_return = nav - initial
    realized_pnl = total_return - unrealized_pnl

    unrealized_color = "green" if unrealized_pnl >= 0 else "red"
    realized_color = "green" if realized_pnl >= 0 else "red"
    total_color = "green" if total_return >= 0 else "red"

    lines = [
        f"  Invested:     {total_invested:>12,.0f}    Current Value: {current_value:>12,.0f}",
        f"  Unrealized:   [{unrealized_color}]{unrealized_pnl:>+12,.0f}[/{unrealized_color}]"
        f"    Realized:      [{realized_color}]{realized_pnl:>+12,.0f}[/{realized_color}]",
        f"  Total Fees:   {total_fees:>12,.0f}    Cash:          {cash:>12,.0f}",
        f"  [bold]Total P&L:  [{total_color}]{total_return:>+12,.0f}[/{total_color}]"
        f" ({total_return / initial * 100:+.1f}%)[/bold]"
        if initial > 0
        else f"  [bold]Total P&L:  [{total_color}]{total_return:>+12,.0f}[/{total_color}][/bold]",
    ]

    return Panel("\n".join(lines), title="[bold]P&L BREAKDOWN[/bold]", border_style="green", padding=(0, 1))


# ---------------------------------------------------------------------------
# Tier: Trade History
# ---------------------------------------------------------------------------


def _build_trade_history_table(ledger: Ledger, limit: int = 20) -> Table:
    """Build recent trade history table."""
    trades = ledger.get_trades()
    recent = trades[-limit:] if len(trades) > limit else trades
    recent.reverse()  # Most recent first

    table = Table(title=f"Recent Trades (last {len(recent)})", box=box.SIMPLE, pad_edge=False)
    table.add_column("Date", min_width=10)
    table.add_column("Action", min_width=5)
    table.add_column("Stock", min_width=12)
    table.add_column("Qty", justify="right", min_width=4)
    table.add_column("Price", justify="right", min_width=8)
    table.add_column("Value", justify="right", min_width=10)
    table.add_column("Cost", justify="right", min_width=6)
    table.add_column("Rationale", min_width=20, max_width=40, overflow="ellipsis")

    for trade in recent:
        action_color = "green" if trade.action == "BUY" else "red"
        value = trade.shares * trade.price
        table.add_row(
            trade.timestamp[:10],
            f"[{action_color}]{trade.action}[/{action_color}]",
            trade.ticker.replace(".NS", ""),
            str(trade.shares),
            f"{trade.price:,.1f}",
            f"{value:,.0f}",
            f"{trade.total_cost:,.0f}",
            (trade.rationale[:38] + "..") if len(trade.rationale) > 40 else trade.rationale,
        )

    return table


# ---------------------------------------------------------------------------
# Tier 4: Sector Breakdown
# ---------------------------------------------------------------------------


def _build_sector_table(
    holdings: dict[str, int],
    prices: dict[str, float],
    nav: float,
) -> Table:
    """Build sector concentration table."""
    sectors: dict[str, float] = {}
    sector_stocks: dict[str, int] = {}

    for ticker, shares in holdings.items():
        sector = get_sector(ticker)
        value = shares * prices.get(ticker, 0)
        sectors[sector] = sectors.get(sector, 0) + value
        sector_stocks[sector] = sector_stocks.get(sector, 0) + 1

    table = Table(
        title="Sector Exposure",
        box=box.SIMPLE,
        show_lines=False,
        pad_edge=False,
    )
    table.add_column("Sector", min_width=16)
    table.add_column("Value", justify="right", min_width=10)
    table.add_column("Weight", justify="right", min_width=8)
    table.add_column("Stocks", justify="right", min_width=6)

    cfg = get_config()
    max_sector = cfg.portfolio.max_sector_exposure

    for sector, value in sorted(sectors.items(), key=lambda x: -x[1]):
        weight = value / nav * 100 if nav > 0 else 0
        count = sector_stocks[sector]

        if weight > max_sector * 100:
            wt_str = f"[red]{weight:.1f}%[/red]"
        elif weight > max_sector * 80:
            wt_str = f"[yellow]{weight:.1f}%[/yellow]"
        else:
            wt_str = f"{weight:.1f}%"

        table.add_row(sector, f"{value:,.0f}", wt_str, str(count))

    return table


# ---------------------------------------------------------------------------
# Main dashboard renderer
# ---------------------------------------------------------------------------


def _build_dashboard_layout(
    strategy: str,
    capital: float,
    show_market: bool,
    show_risk: bool,
    show_rebalance: bool,
    show_sectors: bool,
    paper: bool,
    status_text: str = "",
    show_trades: bool = True,
    show_pnl: bool = True,
) -> Group:
    """Build the full dashboard as a single renderable Group."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Auto-detect paper portfolio
    ledger_name = strategy
    cfg = get_config()

    if paper:
        ledger_name = f"{strategy}_paper"
    else:
        live_ledger = Ledger(strategy)
        if not live_ledger.get_holdings():
            paper_db = cfg.ledger_dir / f"{strategy}_paper.db"
            if paper_db.exists():
                ledger_name = f"{strategy}_paper"
                paper = True

    mode_label = "[yellow]PAPER[/yellow] " if paper else ""

    renderables = []

    # Header
    header = Panel(
        f"  [bold white]DIAMOND[/bold white] - {mode_label}{strategy.upper()} Dashboard    {now}"
        + (f"    [dim]{status_text}[/dim]" if status_text else ""),
        border_style="bright_cyan",
        padding=(0, 1),
    )
    renderables.append(header)

    # Load ledger and data
    ledger = Ledger(ledger_name)
    holdings = ledger.get_holdings()

    if not holdings:
        renderables.append(Text())
        renderables.append(
            Panel(
                f"  No holdings found for [bold]{strategy}[/bold].\n\n"
                f"  Start paper trading:  [cyan]diamond paper {strategy} --capital {int(capital)}[/cyan]\n"
                f"  Or run live:          [cyan]diamond run {strategy} --capital {int(capital)}[/cyan]",
                title="[bold yellow]SETUP REQUIRED[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        )
        if show_market:
            renderables.append(Text())
            renderables.append(_build_market_pulse_panel())
        return Group(*renderables)

    # Fetch prices
    tickers = list(holdings.keys())
    prices = _fetch_current_prices(tickers)

    # Action Panel
    renderables.append(_build_action_panel(strategy, ledger, holdings, prices, capital))

    # Portfolio Summary
    renderables.append(_build_portfolio_summary(ledger, holdings, prices, capital))

    # P&L Breakdown
    if show_pnl:
        renderables.append(_build_pnl_summary_panel(ledger, holdings, prices))

    # Market Pulse
    if show_market:
        renderables.append(_build_market_pulse_panel())

    # Holdings Table
    renderables.append(_build_holdings_table(ledger, holdings, prices))

    # Sector Breakdown
    if show_sectors:
        nav = ledger.get_portfolio_value(prices)
        renderables.append(_build_sector_table(holdings, prices, nav))

    # Trade History
    if show_trades:
        renderables.append(_build_trade_history_table(ledger))

    # Risk Panel
    if show_risk:
        renderables.append(_build_risk_panel(strategy, holdings, prices))

    # Rebalance Preview
    if show_rebalance:
        rebal_panel = _build_rebalance_panel(strategy, ledger_name, holdings, prices, capital)
        if rebal_panel:
            renderables.append(rebal_panel)

    renderables.append(Text("  Press Ctrl+C to exit", style="dim"))

    return Group(*renderables)


def render_dashboard(
    strategy: str = "gods_plan",
    capital: float = 500000,
    show_market: bool = True,
    show_risk: bool = True,
    show_rebalance: bool = True,
    show_sectors: bool = True,
    paper: bool = False,
    refresh_interval: int = 60,
    show_trades: bool = True,
    show_pnl: bool = True,
) -> None:
    """Render the live dashboard to terminal.

    Refreshes every `refresh_interval` seconds. Press Ctrl+C to exit.
    """
    import time

    with _suppress_noisy_loggers():
        # Initial render
        layout = _build_dashboard_layout(
            strategy,
            capital,
            show_market,
            show_risk,
            show_rebalance,
            show_sectors,
            paper,
            status_text=f"Refreshes every {refresh_interval}s",
            show_trades=show_trades,
            show_pnl=show_pnl,
        )

        try:
            with Live(layout, console=console, screen=True, refresh_per_second=1) as live:
                while True:
                    time.sleep(refresh_interval)
                    layout = _build_dashboard_layout(
                        strategy,
                        capital,
                        show_market,
                        show_risk,
                        show_rebalance,
                        show_sectors,
                        paper,
                        status_text=f"Refreshes every {refresh_interval}s",
                        show_trades=show_trades,
                        show_pnl=show_pnl,
                    )
                    live.update(layout)
        except KeyboardInterrupt:
            pass
