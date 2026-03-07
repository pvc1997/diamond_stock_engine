"""Diamond Stock Engine CLI.

Single entry point for all operations.
Usage: diamond <command> [options]
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Optional

import typer

from diamond.config import get_config
from diamond.monitoring import configure_metrics_logging

app = typer.Typer(
    name="diamond",
    help="Systematic Indian equity portfolio management engine.",
    no_args_is_help=False,
    invoke_without_command=True,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("diamond")

# Configure structured metrics logging (JSON events to file)
configure_metrics_logging()


@app.callback()
def _main(ctx: typer.Context):
    """Systematic Indian equity portfolio management engine."""
    if ctx.invoked_subcommand is None:
        from diamond.menu import navigate

        navigate()


VALID_STRATEGIES = ["baseline", "steady", "gods_plan", "accumulate"]


def _resolve_strategy(name: str) -> Any:
    """Resolve strategy name to implementation instance."""
    if name == "baseline":
        from diamond.strategies.baseline import BaselineStrategy

        return BaselineStrategy()
    elif name == "steady":
        from diamond.strategies.steady import SteadyStrategy

        return SteadyStrategy()
    elif name == "gods_plan":
        from diamond.strategies.gods_plan import GodsPlanStrategy

        return GodsPlanStrategy()
    else:
        typer.echo(f"Unknown strategy '{name}'. Choose from: {', '.join(VALID_STRATEGIES)}")
        raise typer.Exit(1)


# --- Targeted Sell Command ---


@app.command()
def sell(
    strategy: Annotated[str, typer.Argument(help="Strategy name")] = "gods_plan",
    ticker: Annotated[Optional[str], typer.Argument(help="Stock ticker to sell (e.g., TATATECH.NS)")] = None,
    shares: Annotated[Optional[int], typer.Option("--shares", "-n", help="Number of shares (default: all)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without executing")] = False,
    paper: Annotated[bool, typer.Option("--paper", "-p", help="Sell from paper portfolio")] = False,
    reason: Annotated[str, typer.Option("--reason", "-r", help="Sell rationale")] = "Manual sell",
):
    """Sell a specific stock from a portfolio.

    Examples:
      diamond sell gods_plan TATATECH.NS          # Sell all TATATECH shares
      diamond sell gods_plan TATATECH.NS -n 10    # Sell 10 shares
      diamond sell gods_plan TATATECH.NS --dry-run # Preview only
      diamond sell gods_plan TATATECH.NS --paper   # Sell from paper portfolio
    """
    from diamond.execution.executor import execute_sell

    if not ticker:
        # Show current holdings and let user pick
        from diamond.data.ledger import Ledger
        from diamond.execution.paper import _paper_strategy_name

        ledger_name = _paper_strategy_name(strategy) if paper else strategy
        ledger = Ledger(ledger_name)
        holdings = ledger.get_holdings()
        if not holdings:
            typer.echo(f"No holdings in {ledger_name}.")
            raise typer.Exit(1)
        typer.echo(f"\n  Holdings in {ledger_name}:")
        for t, s in sorted(holdings.items()):
            avg = ledger.get_avg_price(t)
            typer.echo(f"    {t:>20s}  shares={s:>4d}  avg={avg:>8,.2f}")
        typer.echo(f"\n  Usage: diamond sell {strategy} <TICKER> [--shares N]")
        return

    # Normalize ticker
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    result = execute_sell(
        strategy=strategy,
        ticker=ticker,
        shares=shares,
        reason=reason,
        dry_run=dry_run,
        paper=paper,
    )

    if result["status"] == "error":
        typer.echo(f"Error: {result['reason']}")
        raise typer.Exit(1)
    elif result["status"] == "dry_run":
        typer.echo(f"DRY RUN: SELL {result['shares']} {ticker} @ {result['price']:,.2f}")
        typer.echo(f"  Value:    {result['value']:,.2f} INR")
        typer.echo(f"  Est cost: {result['est_cost']:,.2f} INR")
        typer.echo(f"  Proceeds: {result['proceeds']:,.2f} INR")
    else:
        typer.echo(f"SOLD {result['shares']} {ticker} @ {result['price']:,.2f}")
        typer.echo(f"  Value:    {result['value']:,.2f} INR")
        typer.echo(f"  Cost:     {result['cost']:,.2f} INR")
        typer.echo(f"  Proceeds: {result['proceeds']:,.2f} INR")
        typer.echo(f"  Cash:     {result['cash']:,.2f} INR")
        typer.echo(f"  Holdings: {result['holdings']} stocks")


# --- Targeted Buy Command ---


@app.command()
def buy(
    strategy: Annotated[str, typer.Argument(help="Strategy name")] = "gods_plan",
    ticker: Annotated[Optional[str], typer.Argument(help="Stock ticker to buy (e.g., RELIANCE.NS)")] = None,
    amount: Annotated[Optional[float], typer.Option("--amount", "-a", help="INR amount to invest")] = None,
    shares: Annotated[Optional[int], typer.Option("--shares", "-n", help="Number of shares to buy")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without executing")] = False,
    paper: Annotated[bool, typer.Option("--paper", "-p", help="Buy in paper portfolio")] = False,
    reason: Annotated[str, typer.Option("--reason", "-r", help="Buy rationale")] = "Manual buy",
):
    """Buy a specific stock into a portfolio.

    Examples:
      diamond buy gods_plan RELIANCE.NS --amount 50000   # Buy ~50K worth
      diamond buy gods_plan RELIANCE.NS --shares 10      # Buy exactly 10
      diamond buy gods_plan RELIANCE.NS -a 50000 --paper # Paper buy
    """
    from diamond.execution.executor import execute_buy

    if not ticker:
        typer.echo("Usage: diamond buy <strategy> <TICKER> --amount <INR> [--shares N]")
        raise typer.Exit(1)

    if not amount and not shares:
        typer.echo("Specify --amount <INR> or --shares <N>")
        raise typer.Exit(1)

    # Normalize ticker
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    result = execute_buy(
        strategy=strategy,
        ticker=ticker,
        amount=amount,
        shares=shares,
        reason=reason,
        dry_run=dry_run,
        paper=paper,
    )

    if result["status"] == "error":
        typer.echo(f"Error: {result['reason']}")
        raise typer.Exit(1)
    elif result["status"] == "dry_run":
        typer.echo(f"DRY RUN: BUY {result['shares']} {ticker} @ {result['price']:,.2f}")
        typer.echo(f"  Value:     {result['value']:,.2f} INR")
        typer.echo(f"  Est cost:  {result['est_cost']:,.2f} INR")
        typer.echo(f"  Required:  {result['total_required']:,.2f} INR")
        typer.echo(f"  Available: {result['cash_available']:,.2f} INR")
    else:
        typer.echo(f"BOUGHT {result['shares']} {ticker} @ {result['price']:,.2f}")
        typer.echo(f"  Value: {result['value']:,.2f} INR")
        typer.echo(f"  Cost:  {result['cost']:,.2f} INR")
        typer.echo(f"  Cash:  {result['cash']:,.2f} INR")
        typer.echo(f"  Holdings: {result['holdings']} stocks")


# --- Cleanup Command ---


@app.command()
def cleanup(
    strategy: Annotated[str, typer.Argument(help="Strategy to clean up")] = "gods_plan",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without executing")] = False,
    paper: Annotated[bool, typer.Option("--paper", "-p", help="Clean up paper portfolio")] = False,
):
    """Detect and write off delisted stocks from a portfolio.

    Scans all holdings for stocks with no price data (delisted/suspended)
    and removes them from the ledger as a write-off (no cash credit).
    """
    from diamond.execution.executor import execute_cleanup

    result = execute_cleanup(strategy=strategy, dry_run=dry_run, paper=paper)

    if not result["written_off"]:
        typer.echo("No delisted stocks found — portfolio is clean.")
        return

    prefix = "Would write off" if dry_run else "Written off"
    for item in result["written_off"]:
        typer.echo(f"  {prefix}: {item['ticker']} ({item['shares']} shares)")

    typer.echo(f"\n{result['count']} stock(s) {'would be ' if dry_run else ''}written off.")


# --- Trim Command ---


@app.command()
def trim(
    strategy: Annotated[str, typer.Argument(help="Strategy to trim")] = "gods_plan",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without executing")] = False,
    paper: Annotated[bool, typer.Option("--paper", "-p", help="Trim paper portfolio")] = False,
):
    """Trim positions that exceed the max position weight (10%).

    Sells enough shares to bring overweight positions back to the limit.
    """
    from diamond.execution.executor import execute_trim

    result = execute_trim(strategy=strategy, dry_run=dry_run, paper=paper)

    if not result["trims"]:
        typer.echo("All positions within concentration limits — no trims needed.")
        return

    for t in result["trims"]:
        prefix = "Would trim" if dry_run else "Trimmed"
        typer.echo(
            f"  {prefix}: {t['ticker']} {t['current_weight']:.1f}% -> {t['target_weight']:.1f}%"
            f"  (SELL {t['sell_shares']} @ {t['price']:,.2f} = {t['value']:,.0f} INR)"
        )

    typer.echo(f"\n{result['count']} position(s) {'would be ' if dry_run else ''}trimmed.")
    if not dry_run:
        typer.echo(f"  Cash: {result['cash']:,.2f} INR")


# --- Actionable Alerts Command ---


@app.command("alerts")
def alerts_cmd(
    strategy: Annotated[str, typer.Argument(help="Strategy to check")] = "gods_plan",
    act: Annotated[bool, typer.Option("--act", help="Execute suggested actions (interactive)")] = False,
    paper: Annotated[bool, typer.Option("--paper", "-p", help="Check/act on paper portfolio")] = False,
):
    """Show actionable alerts (stop-loss, concentration, delisted) and optionally act on them.

    Use --act to interactively execute stop-loss exits, trims, and write-offs.
    """
    from diamond.data import market
    from diamond.data.ledger import Ledger
    from diamond.execution.executor import execute_cleanup, execute_sell, execute_trim
    from diamond.monitoring.alerts import get_actionable_alerts

    if paper:
        from diamond.execution.paper import _paper_strategy_name

        display_name = _paper_strategy_name(strategy)
    else:
        display_name = strategy

    ledger = Ledger(display_name)
    holdings = ledger.get_holdings()

    if not holdings:
        typer.echo(f"No holdings in {display_name}.")
        raise typer.Exit(1)

    # Fetch prices
    prices: dict[str, float] = {}
    for ticker in holdings:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception:
            pass

    alerts = get_actionable_alerts(display_name, prices)

    if not alerts:
        typer.echo("No actionable alerts — portfolio is healthy.")
        return

    typer.echo(f"\n  {len(alerts)} actionable alert(s) for {display_name}:")
    for i, alert in enumerate(alerts, 1):
        prefix = {"critical": "!!!", "warning": "!!"}.get(alert.level, "i")
        typer.echo(f"  {i}. [{prefix}] {alert.message}")

    if not act:
        typer.echo("\n  Use --act to execute suggested actions.")
        return

    typer.echo("")

    for alert in alerts:
        ticker = alert.details.get("ticker", "")
        if alert.category == "stop_loss":
            response = input(f"  SELL all {ticker}? [y/N]: ").strip().lower()
            if response in ("y", "yes"):
                result = execute_sell(
                    strategy=strategy,
                    ticker=ticker,
                    reason=f"Stop-loss exit: {alert.message}",
                    paper=paper,
                )
                if result["status"] == "executed":
                    typer.echo(f"    Sold {result['shares']} {ticker} @ {result['price']:,.2f}")
                else:
                    typer.echo(f"    Failed: {result.get('reason', result['status'])}")
            else:
                typer.echo(f"    Skipped {ticker}")

        elif alert.category == "delisted":
            response = input(f"  Write off {ticker}? [y/N]: ").strip().lower()
            if response in ("y", "yes"):
                result = execute_cleanup(strategy=strategy, paper=paper)
                written = [w for w in result["written_off"] if w["ticker"] == ticker]
                if written:
                    typer.echo(f"    Written off {ticker}")
                else:
                    typer.echo(f"    Failed to write off {ticker}")
            else:
                typer.echo(f"    Skipped {ticker}")

        elif alert.category == "concentration" and alert.details.get("action") == "trim":
            response = input(f"  Trim {ticker} to {alert.details.get('limit_pct', 10)}%? [y/N]: ").strip().lower()
            if response in ("y", "yes"):
                result = execute_trim(strategy=strategy, current_prices=prices, paper=paper)
                trims = [t for t in result["trims"] if t["ticker"] == ticker]
                if trims:
                    t = trims[0]
                    typer.echo(f"    Trimmed {ticker}: sold {t['sell_shares']} shares")
                else:
                    typer.echo(f"    No trim executed for {ticker}")
            else:
                typer.echo(f"    Skipped {ticker}")

    typer.echo("")


# --- Run Command ---


@app.command()
def run(
    strategy: Annotated[str, typer.Argument(help="Strategy to run: baseline, steady, gods_plan")] = "baseline",
    capital: Annotated[float, typer.Option("--capital", "-c", help="Initial capital in INR")] = 100000,
    force: Annotated[bool, typer.Option("--force", "-f", help="Bypass rebalance timing check")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show trades without executing")] = False,
    live: Annotated[bool, typer.Option("--live", "-l", help="Execute via Kite Connect (interactive)")] = False,
    force_after_hours: Annotated[
        bool,
        typer.Option("--force-after-hours", help="Allow live orders when market is closed (AMO)"),
    ] = False,
    smart: Annotated[bool, typer.Option("--smart", help="Smart rebalancing (drift + tax-aware)")] = False,
):
    """Run a portfolio strategy (screen -> allocate -> execute).

    Modes:
      diamond run gods_plan -c 500000              # Offline execution (ledger only)
      diamond run gods_plan -c 500000 --dry-run    # Preview trades, no execution
      diamond run gods_plan -c 500000 --live       # Live via Kite (interactive confirmation)
      diamond run gods_plan --live --dry-run       # Live preview (no real orders)
      diamond run gods_plan --smart                # Smart rebalancing (drift + tax-aware)
    """
    if strategy not in VALID_STRATEGIES:
        typer.echo(f"Unknown strategy '{strategy}'. Choose from: {', '.join(VALID_STRATEGIES)}")
        raise typer.Exit(1)

    logger.info(f"Running strategy={strategy} capital={capital} force={force} dry_run={dry_run} live={live}")

    strat = _resolve_strategy(strategy)

    typer.echo(f"Screening {strategy} strategy...")
    candidates = strat.screen(None)  # type: ignore
    if hasattr(candidates, "empty") and candidates.empty:
        typer.echo("Screening produced no candidates. Aborting.")
        raise typer.Exit(1)

    allocation = strat.allocate(candidates, capital)  # type: ignore
    if not allocation:
        typer.echo("Allocation produced no positions. Aborting.")
        raise typer.Exit(1)

    # --- Live mode: execute via Kite with interactive confirmation ---
    if live:
        from diamond.execution.live import execute_live

        result = execute_live(
            strategy=strategy,
            target_allocation=allocation,
            capital=capital,
            force=force,
            dry_run=dry_run,
            force_after_hours=force_after_hours,
        )
        # Result is displayed by execute_live via rich console
        return

    # --- Offline mode: execute against local ledger ---
    typer.echo(f"Running {strategy} with {capital:,.0f} INR capital...")
    from diamond.execution import executor

    result = executor.execute(
        strategy=strategy,
        target_allocation=allocation,
        capital=capital,
        force=force,
        dry_run=dry_run,
        screener_df=candidates,
        smart=smart,
    )

    if result["status"] == "skipped":
        typer.echo(f"Rebalance skipped: {result['reason']}")
    elif result["status"] == "blocked":
        typer.echo("EXECUTION BLOCKED by risk gate:")
        for sig in result.get("signals", []):
            typer.echo(f"  {sig}")
        typer.echo("\nUse --force to override (not recommended).")
    elif result["status"] == "no_trades":
        typer.echo("Portfolio is on target - no trades needed.")
    elif result["status"] == "dry_run":
        typer.echo(f"DRY RUN: {result['trades']} trades planned (not executed)")
    else:
        typer.echo(f"Executed {result['trades']} trades")
        typer.echo(f"  Fees: {result['total_fees']:,.2f} INR")
        typer.echo(f"  NAV:  {result['nav']:,.2f} INR")
        typer.echo(f"  Cash: {result['cash']:,.2f} INR")
        typer.echo(f"  Holdings: {result['holdings']} stocks")


# --- Backtest Command ---


@app.command()
def backtest(
    strategy: Annotated[str, typer.Argument(help="Strategy to backtest")] = "baseline",
    start: Annotated[str, typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)")] = "2020-01-01",
    end: Annotated[str, typer.Option("--end", "-e", help="End date (YYYY-MM-DD)")] = "2024-12-31",
    capital: Annotated[float, typer.Option("--capital", "-c", help="Initial capital in INR")] = 100000,
    window: Annotated[int, typer.Option("--window", "-w", help="Window size in months")] = 6,
):
    """Run walk-forward backtest for a strategy."""
    if strategy not in VALID_STRATEGIES:
        typer.echo(f"Unknown strategy '{strategy}'. Choose from: {', '.join(VALID_STRATEGIES)}")
        raise typer.Exit(1)

    logger.info(f"Backtesting strategy={strategy} from {start} to {end}")
    typer.echo(f"Backtesting {strategy} from {start} to {end} ({window}-month windows)...")

    strat = _resolve_strategy(strategy)

    from diamond.backtest.engine import run_backtest
    from diamond.backtest.reporter import compute_metrics, generate_report

    result = run_backtest(
        strategy=strat,
        strategy_name=strategy,
        start_date=start,
        end_date=end,
        initial_capital=capital,
        window_months=window,
        step_months=window,
    )

    metrics = compute_metrics(result)
    report_path = generate_report(result)

    typer.echo("")
    typer.echo(f"  Total Return: {metrics['total_return_pct']:+.2f}%")
    typer.echo(f"  CAGR:         {metrics['cagr']:+.2f}%")
    typer.echo(f"  Sharpe:       {metrics['sharpe']:.3f}")
    typer.echo(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
    typer.echo(f"  Win Rate:     {metrics['win_rate_pct']:.1f}%")
    typer.echo(f"  Trades:       {metrics['total_trades']}")
    typer.echo(f"  Fees:         {metrics['total_fees']:,.2f} INR")
    typer.echo("")
    typer.echo(f"Report: {report_path}")


# --- Status Command ---


@app.command()
def status():
    """Show current portfolio status across all strategies."""
    cfg = get_config()

    typer.echo("=" * 50)
    typer.echo("DIAMOND STOCK ENGINE - Portfolio Status")
    typer.echo("=" * 50)

    # Check which ledgers exist
    ledger_files = list(cfg.ledger_dir.glob("*.db"))
    if not ledger_files:
        typer.echo("No active portfolios found. Run `diamond run <strategy>` to start.")
        return

    from diamond.data.ledger import Ledger

    for db_file in sorted(ledger_files):
        strategy_name = db_file.stem
        ledger = Ledger(strategy_name, db_path=db_file)
        holdings = ledger.get_holdings()
        cash = ledger.get_cash()
        total_fees = ledger.get_total_fees()
        trade_count = len(ledger.get_trades())

        typer.echo(f"\n  {strategy_name.upper()}")
        typer.echo(f"    Holdings: {len(holdings)} stocks")
        typer.echo(f"    Cash: {cash:,.2f} INR")
        typer.echo(f"    Total fees: {total_fees:,.2f} INR")
        typer.echo(f"    Trades: {trade_count}")

    typer.echo("")


# --- Screen Command ---


@app.command()
def screen(
    subset: Annotated[Optional[str], typer.Option("--subset", help="Comma-separated tickers")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Bypass cache")] = False,
):
    """Run market screener on NSE 500 universe."""
    logger.info(f"Screening universe subset={subset} force={force}")

    from diamond.analysis.screener import screen as run_screen

    tickers = subset.split(",") if subset else None
    df = run_screen(tickers=tickers, force=force)

    if df.empty:
        typer.echo("Screening produced no results.")
        raise typer.Exit(1)

    typer.echo(f"Screened {len(df)} stocks. Top 20 by Alpha:")
    typer.echo("")
    top = df.head(20).to_string(index=False)
    typer.echo(top)
    typer.echo("\nFull results cached to data/universe_cache.csv")


# --- Sentiment Command ---


@app.command()
def sentiment(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g., RELIANCE.NS)")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Bypass cache")] = False,
):
    """Analyze sentiment for a stock using AI + heuristics."""
    from diamond.analysis.sentiment import analyze_stock

    typer.echo(f"Analyzing sentiment for {ticker}...")
    result = analyze_stock(ticker, force=force)

    typer.echo(f"\n  Score:     {result['score']:+.1f} / 10")
    typer.echo(f"  Sentiment: {result['sentiment']}")
    typer.echo(f"  Multiplier:{result['multiplier']:.2f}")
    typer.echo(f"  Source:    {result['source']}")
    typer.echo(f"  Rationale: {result['rationale']}")


# --- Deep Analysis Command ---


@app.command()
def analyze(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g., RELIANCE.NS or RELIANCE)")],
    no_ai: Annotated[bool, typer.Option("--no-ai", help="Skip AI narrative, use rule-based only")] = False,
    no_peers: Annotated[bool, typer.Option("--no-peers", help="Skip peer comparison (faster)")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """Deep analysis of a single stock — technicals, fundamentals, AI verdict."""
    import json as json_mod
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.analysis.deep import analyze_deep

    # Suppress noisy loggers during analysis
    noisy = ["yfinance", "urllib3", "peewee"]
    for name in noisy:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    # Normalize ticker
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    console.print(f"\n  [dim]Analyzing {ticker}...[/dim]")

    try:
        result = analyze_deep(ticker, use_ai=not no_ai)
    except RuntimeError as e:
        typer.echo(f"Analysis failed: {e}")
        raise typer.Exit(1) from e

    # --- JSON output ---
    if json_output:
        data = {
            "ticker": result.ticker,
            "name": result.name,
            "timestamp": result.timestamp,
            "verdict": result.verdict,
            "confidence": result.confidence,
            "narrative": result.ai_narrative,
            "reasons": result.verdict_reasons,
            "technicals": {
                "price": result.technicals.current_price,
                "rsi_14": result.technicals.rsi_14,
                "macd_histogram": result.technicals.macd_histogram,
                "bb_position": result.technicals.bb_position,
                "dma_trend": result.technicals.dma_trend,
                "support": result.technicals.support,
                "resistance": result.technicals.resistance,
            },
            "fundamentals": {
                "pe": result.fundamentals.pe_ratio,
                "pb": result.fundamentals.pb_ratio,
                "roe": result.fundamentals.roe,
                "de": result.fundamentals.debt_to_equity,
                "dividend_yield": result.fundamentals.dividend_yield,
            },
            "screener": {
                "alpha": result.screener.alpha,
                "beta": result.screener.beta,
                "cagr": result.screener.cagr,
                "volatility": result.screener.volatility,
                "hurst": result.screener.hurst,
            },
            "sentiment": result.sentiment,
        }
        typer.echo(json_mod.dumps(data, indent=2))
        return

    # --- Rich output ---

    # Verdict panel
    verdict_styles = {"BUY": "bold green", "SELL": "bold red", "HOLD": "bold yellow"}
    v_style = verdict_styles.get(result.verdict, "bold white")
    conf_bar = "█" * int(result.confidence * 20) + "░" * (20 - int(result.confidence * 20))

    verdict_text = (
        f"  [{v_style}]{result.verdict}[/{v_style}]  "
        f"Confidence: [{v_style}]{conf_bar}[/{v_style}] {result.confidence:.0%}\n\n"
        f"  {result.ai_narrative}"
    )
    if result.verdict_reasons:
        verdict_text += "\n"
        for reason in result.verdict_reasons[:6]:
            verdict_text += f"\n  - {reason}"

    console.print()
    console.print(
        Panel(
            verdict_text,
            title=f"[bold]{result.name}[/bold] ({result.ticker})  —  {result.timestamp}",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    # Technical indicators
    t = result.technicals
    rsi_color = "red" if t.rsi_14 > 70 else ("green" if t.rsi_14 < 30 else "white")
    macd_color = "green" if t.macd_histogram > 0 else "red"
    trend_color = "green" if t.dma_trend == "GOLDEN_CROSS" else ("red" if t.dma_trend == "DEATH_CROSS" else "yellow")

    tech_text = (
        f"  Price: [bold]{t.current_price:,.2f}[/bold]  "
        f"1D: {'[green]' if t.price_change_1d >= 0 else '[red]'}{t.price_change_1d:+.1f}%{'[/green]' if t.price_change_1d >= 0 else '[/red]'}  "
        f"1W: {'[green]' if t.price_change_1w >= 0 else '[red]'}{t.price_change_1w:+.1f}%{'[/green]' if t.price_change_1w >= 0 else '[/red]'}  "
        f"1M: {'[green]' if t.price_change_1m >= 0 else '[red]'}{t.price_change_1m:+.1f}%{'[/green]' if t.price_change_1m >= 0 else '[/red]'}\n"
        f"\n"
        f"  RSI(14): [{rsi_color}]{t.rsi_14:.0f}[/{rsi_color}]    "
        f"MACD: [{macd_color}]{t.macd_histogram:+.2f}[/{macd_color}] "
        f"(Line={t.macd_line:.2f}, Sig={t.macd_signal:.2f})\n"
        f"  Bollinger: {t.bb_position} "
        f"(Lower={t.bb_lower:,.0f} | Mid={t.bb_middle:,.0f} | Upper={t.bb_upper:,.0f})\n"
        f"  50 DMA: {t.dma_50:,.0f}    200 DMA: {t.dma_200:,.0f}    "
        f"Trend: [{trend_color}]{t.dma_trend}[/{trend_color}]\n"
        f"  Support: {t.support:,.0f}    Resistance: {t.resistance:,.0f}"
    )
    console.print(Panel(tech_text, title="[bold]TECHNICALS[/bold]", border_style="blue", padding=(0, 1)))

    # Fundamentals
    f = result.fundamentals
    fund_text = (
        f"  P/E: {f.pe_ratio:.1f}    P/B: {f.pb_ratio:.2f}    EPS: {f.eps:.2f}\n"
        f"  ROE: {f.roe:.1%}    D/E: {f.debt_to_equity:.0f}    Div Yield: {f.dividend_yield:.2%}\n"
        f"  Revenue Growth: {f.revenue_growth:.1%}    Profit Growth: {f.profit_growth:.1%}\n"
        f"  Market Cap: {f.market_cap / 1e7:,.0f} Cr    Book Value: {f.book_value:,.2f}\n"
        f"  Sector: {f.sector}    Industry: {f.industry}\n"
        f"  Analyst: {f.recommendation}"
    )
    console.print(Panel(fund_text, title="[bold]FUNDAMENTALS[/bold]", border_style="green", padding=(0, 1)))

    # Screener metrics
    s = result.screener
    alpha_color = "green" if s.alpha > 0 else "red"
    screener_text = (
        f"  Alpha: [{alpha_color}]{s.alpha:.4f}[/{alpha_color}]    "
        f"Beta: {s.beta:.2f}    "
        f"CAGR: {'[green]' if s.cagr > 0.12 else '[red]'}{s.cagr:.1%}{'[/green]' if s.cagr > 0.12 else '[/red]'}\n"
        f"  Volatility: {s.volatility:.1%}    "
        f"Hurst: {s.hurst:.2f} ({'[green]trending[/green]' if s.hurst > 0.5 else '[yellow]mean-reverting[/yellow]'})"
    )
    console.print(
        Panel(
            screener_text,
            title="[bold]SCREENER METRICS[/bold]",
            border_style="magenta",
            padding=(0, 1),
        )
    )

    # Sentiment
    sent = result.sentiment
    sent_score = sent.get("score", 0)
    sent_color = "green" if sent_score > 0 else ("red" if sent_score < 0 else "yellow")
    sent_text = (
        f"  Score: [{sent_color}]{sent_score:+.1f}[/{sent_color}] / 10    "
        f"Label: {sent.get('sentiment', 'N/A')}    "
        f"Source: {sent.get('source', 'N/A')}\n"
        f"  {sent.get('rationale', '')}"
    )
    console.print(Panel(sent_text, title="[bold]SENTIMENT[/bold]", border_style="yellow", padding=(0, 1)))

    # Peer comparison
    if result.peers:
        peer_table = Table(title="Sector Peers", box=box.SIMPLE, pad_edge=False)
        peer_table.add_column("Stock", min_width=14)
        peer_table.add_column("Alpha", justify="right")
        peer_table.add_column("Beta", justify="right")
        peer_table.add_column("CAGR", justify="right")
        peer_table.add_column("P/E", justify="right")
        peer_table.add_column("Mkt Cap (Cr)", justify="right")

        for p in result.peers:
            a_color = "green" if p.alpha > 0 else "red"
            peer_table.add_row(
                p.name[:20],
                f"[{a_color}]{p.alpha:.2f}[/{a_color}]",
                f"{p.beta:.2f}",
                f"{p.cagr:.1%}",
                f"{p.pe_ratio:.1f}" if p.pe_ratio > 0 else "-",
                f"{p.market_cap / 1e7:,.0f}" if p.market_cap > 0 else "-",
            )
        console.print(peer_table)

    console.print()


# --- Health Check Command ---


@app.command()
def health(
    strategy: Annotated[str, typer.Argument(help="Strategy to check")] = "baseline",
):
    """Run portfolio health checks (drawdown, drift, stop-loss)."""
    from diamond.data import market
    from diamond.data.ledger import Ledger
    from diamond.monitoring.alerts import run_health_check

    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    if not holdings:
        typer.echo(f"No holdings found for strategy '{strategy}'.")
        raise typer.Exit(1)

    typer.echo(f"Running health checks for {strategy}...")

    # Fetch current prices
    prices: dict[str, float] = {}
    for ticker in holdings:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception:
            pass

    alerts = run_health_check(strategy, prices)

    if not alerts:
        typer.echo("All clear - no alerts.")
        return

    for alert in alerts:
        prefix = {"critical": "!!!", "warning": "!!", "info": "i"}.get(alert.level, "?")
        typer.echo(f"  [{prefix}] {alert.message}")

    typer.echo(f"\n{len(alerts)} alert(s) found.")


# --- Kite Command ---


@app.command()
def kite(
    auth: Annotated[bool, typer.Option("--auth", help="Start Kite authentication flow")] = False,
    token: Annotated[Optional[str], typer.Option("--token", help="Request token from OAuth redirect")] = None,
    authorize_sells: Annotated[
        bool, typer.Option("--authorize-sells", help="Initiate CDSL TPIN authorization for selling")
    ] = False,
    holdings: Annotated[bool, typer.Option("--holdings", help="Show Kite holdings")] = False,
    session_status: Annotated[bool, typer.Option("--status", help="Show Kite session status")] = False,
    import_to: Annotated[Optional[str], typer.Option("--import", help="Import holdings to a strategy ledger")] = None,
    capital: Annotated[
        Optional[float],
        typer.Option("--capital", "-c", help="Capital for import (auto-detects from Kite if omitted)"),
    ] = None,
):
    """Zerodha Kite Connect integration.

    Daily workflow:
      diamond kite --auth                    # Login (opens browser)
      diamond kite --authorize-sells         # CDSL TPIN for selling
      diamond kite --status                  # Check session
      diamond kite --holdings                # View holdings
      diamond kite --import gods_plan -c 500000  # Import to ledger
    """
    from diamond.execution.kite import KiteClient, import_holdings_from_kite

    client = KiteClient()

    if not client.available:
        typer.echo("Kite Connect not available. Install: pip install kiteconnect")
        typer.echo("Then set KITE_API_KEY and KITE_API_SECRET in .env")
        raise typer.Exit(1)

    # --- Session status ---
    if session_status:
        status = client.session_status()
        typer.echo("")
        typer.echo("  Kite Session Status:")
        typer.echo(f"    Available:      {status['available']}")
        typer.echo(f"    Authenticated:  {status['authenticated']}")
        if status["authenticated"]:
            typer.echo(f"    User:           {status['user_name']} ({status['user_id']})")
            typer.echo(f"    Expires:        {status['expires']}")
        else:
            typer.echo("    Run: diamond kite --auth")
        typer.echo("")
        return

    # --- Authentication ---
    if auth:
        if client.authenticated:
            typer.echo(f"Already authenticated as {client.user_name}.")
            typer.echo("Session still valid. Use --status to check expiry.")
            return
        url = client.login_url()
        typer.echo("Opening Kite login in browser...")
        typer.echo(f"URL: {url}")
        typer.echo("")
        typer.echo("After login, you'll be redirected. Copy the 'request_token' from the URL.")
        typer.echo("Then run: diamond kite --token <request_token>")
        import webbrowser

        webbrowser.open(url)
        return

    if token:
        if client.authenticate(token):
            typer.echo(f"Authentication successful! Logged in as {client.user_name}.")
            typer.echo("Session saved — valid until ~6 AM tomorrow.")
        else:
            typer.echo("Authentication failed. Check your token and try again.")
            raise typer.Exit(1)
        return

    # --- CDSL TPIN Authorization ---
    if authorize_sells:
        if not client.authenticated:
            typer.echo("Not authenticated. Run: diamond kite --auth")
            raise typer.Exit(1)
        typer.echo("Initiating CDSL TPIN authorization for sell orders...")
        typer.echo("")
        typer.echo("This will open CDSL's portal. You need to:")
        typer.echo("  1. Enter your TPIN (received via SMS/email from CDSL)")
        typer.echo("  2. Complete OTP verification")
        typer.echo("  3. Authorize all holdings")
        typer.echo("")
        try:
            request_id = client.authorize_holdings()
            url = client.authorization_url(request_id)
            typer.echo("Opening authorization page...")
            import webbrowser

            webbrowser.open(url)
            typer.echo("")
            typer.echo("After authorization, sell orders will work for today.")
            typer.echo("Note: TPIN authorization expires daily — repeat each trading day.")
        except Exception as e:
            typer.echo(f"Failed to initiate authorization: {e}")
            raise typer.Exit(1) from e
        return

    # --- Show holdings ---
    if holdings:
        if not client.authenticated:
            typer.echo("Not authenticated. Run: diamond kite --auth")
            raise typer.Exit(1)
        kite_holdings = client.get_holdings_mapped()
        if not kite_holdings:
            typer.echo("No holdings found in Kite account.")
            return
        typer.echo(f"\n  Kite Holdings ({len(kite_holdings)} stocks):")
        total = 0.0
        for ticker, info in sorted(kite_holdings.items()):
            value = info["shares"] * info["avg_price"]
            total += value
            typer.echo(
                f"    {ticker.replace('.NS', ''):>15s}  "
                f"qty={info['shares']:>4d}  "
                f"avg={info['avg_price']:>8,.2f}  "
                f"value={value:>10,.0f}"
            )
        typer.echo(f"\n  Total invested: {total:,.0f} INR")
        typer.echo("")
        return

    # --- Import holdings to strategy ---
    if import_to:
        if not client.authenticated:
            typer.echo("Not authenticated. Run: diamond kite --auth")
            raise typer.Exit(1)
        if import_to not in VALID_STRATEGIES:
            typer.echo(f"Unknown strategy '{import_to}'. Choose from: {', '.join(VALID_STRATEGIES)}")
            raise typer.Exit(1)

        if capital is None:
            kite_holdings = client.get_holdings_mapped()
            holdings_value = sum(h["shares"] * h["avg_price"] for h in kite_holdings.values())
            available_cash = client.get_available_cash()
            capital = holdings_value + available_cash
            typer.echo(f"Auto-detected capital: {capital:,.0f} INR")
            typer.echo(f"  Holdings value: {holdings_value:,.0f} INR")
            typer.echo(f"  Available cash: {available_cash:,.0f} INR")

        typer.echo(f"Importing Kite holdings to {import_to} with {capital:,.0f} INR capital...")
        try:
            result = import_holdings_from_kite(import_to, capital, client)
        except Exception as e:
            typer.echo(f"Import failed: {e}")
            raise typer.Exit(1) from e

        typer.echo(f"\n  Imported {result['holdings_count']} holdings:")
        for h in result["holdings"]:
            typer.echo(
                f"    {h['ticker'].replace('.NS', ''):>15s}  "
                f"qty={h['shares']:>4d}  "
                f"avg={h['avg_price']:>8,.2f}  "
                f"value={h['value']:>10,.0f}"
            )
        typer.echo(f"\n  Total invested: {result['total_invested']:,.0f} INR")
        typer.echo(f"  Transaction fees: {result['total_fees']:,.0f} INR")
        typer.echo(f"  Remaining cash: {result['remaining_cash']:,.0f} INR")
        typer.echo(f"\n  Ledger created for {import_to}. Run 'diamond dashboard {import_to}' to view.")
        typer.echo("")
        return

    # Default: show help
    typer.echo("Kite Connect commands:")
    typer.echo("  diamond kite --auth               Login to Zerodha")
    typer.echo("  diamond kite --token <TOKEN>       Complete login with token")
    typer.echo("  diamond kite --status              Check session status")
    typer.echo("  diamond kite --holdings            View account holdings")
    typer.echo("  diamond kite --authorize-sells     CDSL TPIN for selling")
    typer.echo("  diamond kite --import gods_plan    Import holdings to strategy")


# --- Risk Report Command ---


@app.command()
def risk(
    strategy: Annotated[str, typer.Argument(help="Strategy to analyze")] = "baseline",
):
    """Compute portfolio risk metrics (VaR, CVaR, drawdown, correlation)."""
    from diamond.data import market
    from diamond.data.ledger import Ledger
    from diamond.monitoring.risk import compute_risk_report

    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    if not holdings:
        typer.echo(f"No holdings found for strategy '{strategy}'.")
        raise typer.Exit(1)

    typer.echo(f"Computing risk report for {strategy}...")

    # Fetch current prices and historical data
    tickers = list(holdings.keys())
    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception:
            pass

    # Get historical prices for VaR/correlation
    try:
        prices_df = market.download_prices(tickers, period_days=252)
    except Exception:
        prices_df = None

    # Get benchmark returns for beta
    benchmark_returns = None
    try:
        bench = market.download_single("^NSEI", period_days=252)
        benchmark_returns = market.calculate_returns(bench)
    except Exception:
        pass

    report = compute_risk_report(strategy, prices, prices_df, benchmark_returns)

    typer.echo("")
    typer.echo(f"  NAV:              {report.nav:,.2f} INR")
    typer.echo(f"  High Water Mark:  {report.high_water_mark:,.2f} INR")
    typer.echo(f"  Drawdown:         {report.drawdown_pct:.2f}%")
    typer.echo(f"  VaR (95%):        {report.var_95:,.2f} INR")
    typer.echo(f"  VaR (99%):        {report.var_99:,.2f} INR")
    typer.echo(f"  CVaR (95%):       {report.cvar_95:,.2f} INR")
    typer.echo(f"  Beta:             {report.beta:.3f}")
    typer.echo(f"  Volatility (ann): {report.volatility_annual:.1f}%")
    typer.echo(f"  Max Correlation:  {report.max_correlation:.3f}")
    typer.echo(f"  Avg Correlation:  {report.avg_correlation:.3f}")

    if report.signals:
        typer.echo("")
        typer.echo("  Signals:")
        for signal in report.signals:
            typer.echo(f"    {signal}")

    typer.echo("")


# --- Paper Trading Command ---


@app.command()
def paper(
    strategy: Annotated[str, typer.Argument(help="Strategy to paper trade")] = "baseline",
    capital: Annotated[float, typer.Option("--capital", "-c", help="Initial capital in INR")] = 100000,
    force: Annotated[bool, typer.Option("--force", "-f", help="Bypass rebalance timing")] = False,
    status_only: Annotated[bool, typer.Option("--status", help="Show paper portfolio status")] = False,
    reset: Annotated[bool, typer.Option("--reset", help="Reset paper portfolio")] = False,
    smart: Annotated[bool, typer.Option("--smart", help="Smart rebalancing (drift + tax-aware)")] = False,
):
    """Run strategy in paper trading mode (simulated execution)."""
    from diamond.execution.paper import execute_paper, get_paper_status, reset_paper

    if reset:
        reset_paper(strategy, capital)
        typer.echo(f"Paper portfolio for {strategy} reset to {capital:,.0f} INR")
        return

    if status_only:
        st = get_paper_status(strategy)
        typer.echo(f"\n  {st['strategy'].upper()}")
        typer.echo(f"    Holdings:  {st['holdings_count']} stocks")
        typer.echo(f"    Cash:      {st['cash']:,.2f} INR")
        typer.echo(f"    Fees:      {st['total_fees']:,.2f} INR")
        typer.echo(f"    Trades:    {st['trade_count']}")
        typer.echo(f"    Last rebal:{st['last_rebalance'] or 'never'}")
        typer.echo("")
        return

    if strategy not in VALID_STRATEGIES:
        typer.echo(f"Unknown strategy '{strategy}'. Choose from: {', '.join(VALID_STRATEGIES)}")
        raise typer.Exit(1)

    typer.echo(f"Paper trading {strategy} with {capital:,.0f} INR capital...")

    strat = _resolve_strategy(strategy)

    candidates = strat.screen(None)  # type: ignore
    if hasattr(candidates, "empty") and candidates.empty:
        typer.echo("Screening produced no candidates. Aborting.")
        raise typer.Exit(1)

    allocation = strat.allocate(candidates, capital)  # type: ignore
    if not allocation:
        typer.echo("Allocation produced no positions. Aborting.")
        raise typer.Exit(1)

    result = execute_paper(
        strategy=strategy,
        target_allocation=allocation,
        capital=capital,
        force=force,
        screener_df=candidates,
        smart=smart,
    )

    if result["status"] == "skipped":
        typer.echo(f"Rebalance skipped: {result['reason']}")
    elif result["status"] == "no_trades":
        typer.echo("Paper portfolio on target - no trades needed.")
    else:
        typer.echo(f"[PAPER] Executed {result['trades']} trades")
        typer.echo(f"  Fees: {result['total_fees']:,.2f} INR")
        typer.echo(f"  NAV:  {result['nav']:,.2f} INR")
        typer.echo(f"  Cash: {result['cash']:,.2f} INR")
        typer.echo(f"  Holdings: {result['holdings']} stocks")


# --- Corporate Actions Command ---


@app.command()
def actions(
    strategy: Annotated[str, typer.Argument(help="Strategy to check for corporate actions")] = "baseline",
    since: Annotated[Optional[str], typer.Option("--since", help="Check actions since date (YYYY-MM-DD)")] = None,
):
    """Scan holdings for corporate actions (splits, dividends) and apply them."""
    from diamond.data.corporate_actions import process_actions

    typer.echo(f"Scanning {strategy} holdings for corporate actions...")

    applied = process_actions(strategy, since=since)

    if not applied:
        typer.echo("No pending corporate actions found.")
        return

    typer.echo(f"\nApplied {len(applied)} corporate action(s):")
    for action in applied:
        if action.action_type == "split":
            typer.echo(f"  SPLIT  {action.ticker}  {action.ratio}:1  ({action.date})")
        elif action.action_type == "dividend":
            typer.echo(f"  DIV    {action.ticker}  {action.value:.2f}/share  ({action.date})")
        elif action.action_type == "bonus":
            typer.echo(f"  BONUS  {action.ticker}  {action.ratio}:1  ({action.date})")

    typer.echo("")


# --- Promote Command ---


@app.command()
def promote(
    strategy: Annotated[str, typer.Argument(help="Strategy to promote from paper to live")] = "baseline",
    capital: Annotated[float, typer.Option("--capital", "-c", help="Capital for live portfolio")] = 100000,
    execute_now: Annotated[bool, typer.Option("--execute", help="Execute promotion immediately")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confidence check")] = False,
):
    """Promote paper portfolio to live trading."""
    from diamond.execution.promote import assess_promotion
    from diamond.execution.promote import promote as do_promote

    report = assess_promotion(strategy)

    typer.echo("")
    typer.echo(f"  Strategy:         {report.strategy}")
    typer.echo(f"  Paper NAV:        {report.paper_nav:,.2f} INR")
    typer.echo(f"  Paper Return:     {report.paper_return_pct:+.2f}%")
    typer.echo(f"  Paper Trades:     {report.paper_trades}")
    typer.echo(f"  Days Active:      {report.paper_days_active}")

    if report.live_nav is not None:
        typer.echo(f"  Live NAV:         {report.live_nav:,.2f} INR")
        typer.echo(f"  Live Return:      {report.live_return_pct:+.2f}%")
        typer.echo(f"  Outperformance:   {report.outperformance_pct:+.2f}%")

    typer.echo(f"  Confidence:       {report.confidence.upper()}")
    typer.echo(f"  Recommended:      {'Yes' if report.recommended else 'No'}")
    typer.echo("")
    typer.echo("  Assessment:")
    for reason in report.reasons:
        typer.echo(f"    - {reason}")
    typer.echo("")

    if not execute_now:
        typer.echo("Use --execute to promote paper allocation to live.")
        return

    if not report.recommended and not force:
        typer.echo(f"Promotion not recommended (confidence: {report.confidence}).")
        typer.echo("Use --force to override.")
        return

    # Get paper allocation and execute live
    allocation = do_promote(strategy, capital)
    if not allocation:
        typer.echo("Paper portfolio has no positions to promote.")
        return

    typer.echo(f"Promoting {len(allocation)} positions to live with {capital:,.0f} INR...")

    from diamond.execution import executor

    result = executor.execute(
        strategy=strategy,
        target_allocation=allocation,
        capital=capital,
        force=True,
    )

    if result["status"] == "blocked":
        typer.echo("BLOCKED by risk gate:")
        for sig in result.get("signals", []):
            typer.echo(f"  {sig}")
    elif result["status"] == "executed":
        typer.echo(f"Promoted! {result['trades']} trades executed")
        typer.echo(f"  Fees: {result['total_fees']:,.2f} INR")
        typer.echo(f"  NAV:  {result['nav']:,.2f} INR")
    else:
        typer.echo(f"Result: {result['status']}")


# --- Reconcile Command ---


@app.command()
def reconcile(
    strategy: Annotated[str, typer.Argument(help="Strategy to reconcile")] = "gods_plan",
):
    """Compare ledger holdings with actual Kite account holdings.

    Shows matches, discrepancies, and holdings missing from either side.
    Requires Kite authentication.
    """
    from diamond.execution.live import reconcile_with_kite

    try:
        result = reconcile_with_kite(strategy)
    except RuntimeError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1) from e

    typer.echo(f"\n  Reconciliation: {strategy}")
    typer.echo(f"  {'=' * 50}")

    if result["in_sync"]:
        typer.echo(f"\n  [OK] Ledger and Kite are in sync ({len(result['matches'])} holdings match)")
    else:
        if result["matches"]:
            typer.echo(f"\n  Matching ({len(result['matches'])}):")
            for m in result["matches"]:
                typer.echo(f"    {m['ticker'].replace('.NS', ''):>15s}  qty={m['shares']}")

        if result["discrepancies"]:
            typer.echo(f"\n  DISCREPANCIES ({len(result['discrepancies'])}):")
            for d in result["discrepancies"]:
                typer.echo(
                    f"    {d['ticker'].replace('.NS', ''):>15s}  "
                    f"ledger={d['ledger_qty']}  kite={d['kite_qty']}  "
                    f"delta={d['delta']:+d}"
                )

        if result["ledger_only"]:
            typer.echo(f"\n  In ledger only ({len(result['ledger_only'])}):")
            for h in result["ledger_only"]:
                typer.echo(f"    {h['ticker'].replace('.NS', ''):>15s}  qty={h['shares']}")

        if result["kite_only"]:
            typer.echo(f"\n  In Kite only ({len(result['kite_only'])}):")
            for h in result["kite_only"]:
                typer.echo(f"    {h['ticker'].replace('.NS', ''):>15s}  qty={h['shares']}  avg={h['avg_price']:,.2f}")

    typer.echo("")


# --- Dashboard Command ---


@app.command()
def dashboard(
    strategy: Annotated[str, typer.Argument(help="Strategy to display")] = "gods_plan",
    capital: Annotated[float, typer.Option("--capital", "-c", help="Capital for rebalance preview")] = 500000,
    no_market: Annotated[bool, typer.Option("--no-market", help="Skip market pulse (faster)")] = False,
    no_risk: Annotated[bool, typer.Option("--no-risk", help="Skip risk metrics (faster)")] = False,
    no_rebalance: Annotated[bool, typer.Option("--no-rebalance", help="Skip rebalance preview")] = False,
    no_trades: Annotated[bool, typer.Option("--no-trades", help="Skip trade history")] = False,
    no_pnl: Annotated[bool, typer.Option("--no-pnl", help="Skip P&L breakdown")] = False,
    paper: Annotated[bool, typer.Option("--paper", "-p", help="Show paper portfolio")] = False,
    refresh: Annotated[int, typer.Option("--refresh", "-r", help="Auto-refresh interval in seconds")] = 60,
):
    """Open the live portfolio dashboard. Press Ctrl+C to exit."""
    from diamond.dashboard import render_dashboard

    render_dashboard(
        strategy=strategy,
        capital=capital,
        show_market=not no_market,
        show_risk=not no_risk,
        show_rebalance=not no_rebalance,
        paper=paper,
        refresh_interval=refresh,
        show_trades=not no_trades,
        show_pnl=not no_pnl,
    )


# --- Market Pulse Command ---


@app.command()
def pulse():
    """Show market pulse - regime detection and daily verdict."""
    from diamond.monitoring.market_pulse import get_market_pulse

    typer.echo("Fetching market data...")
    p = get_market_pulse()

    verdict_icons = {"DEPLOY": "+", "WAIT": "~", "DEFENSIVE": "!"}
    icon = verdict_icons.get(p.verdict, "?")

    typer.echo("")
    typer.echo(f"  [{icon}] TODAY'S VERDICT: {p.verdict}  (Score: {p.score:+d}/100)")
    typer.echo(f"      Regime: {p.regime}  |  Trend: {p.trend}")
    typer.echo("")
    typer.echo(f"  Nifty 50:  {p.nifty_price:,.0f}  ({p.nifty_change_pct:+.2f}%)")
    typer.echo(
        f"  50 DMA:    {p.nifty_50dma:,.0f}  |  200 DMA: {p.nifty_200dma:,.0f}  |  Dist: {p.nifty_distance_200dma_pct:+.1f}%"
    )
    typer.echo(f"  VIX:       {p.vix:.1f} ({p.vix_regime})")
    typer.echo(f"  Breadth:   {p.breadth_pct:.0f}% ({p.breadth_regime})")
    typer.echo(f"  RSI:       {p.nifty_rsi_14:.0f} ({p.momentum_regime})")
    typer.echo("")
    typer.echo("  Reasons:")
    for reason in p.verdict_reasons:
        typer.echo(f"    - {reason}")
    typer.echo("")


# --- Tax Report Command ---


@app.command()
def tax(
    strategy: Annotated[str, typer.Argument(help="Strategy for tax report")] = "gods_plan",
    fy: Annotated[Optional[str], typer.Option("--fy", help="Fiscal year (e.g., 2025-26)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """Generate capital gains tax report for Indian tax filing."""
    import json as json_mod
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.analysis.tax import compute_tax_report

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()
    console.print(f"\n  [dim]Computing tax report for {strategy}...[/dim]")

    report = compute_tax_report(strategy, fiscal_year=fy)

    if json_output:
        data = {
            "fiscal_year": report.fiscal_year,
            "total_stcg": report.total_stcg,
            "total_ltcg": report.total_ltcg,
            "ltcg_exemption": report.ltcg_exemption,
            "taxable_ltcg": report.taxable_ltcg,
            "estimated_stcg_tax": report.estimated_stcg_tax,
            "estimated_ltcg_tax": report.estimated_ltcg_tax,
            "total_estimated_tax": report.total_estimated_tax,
            "total_dividends": report.total_dividends,
            "realized_count": len(report.realized_lots),
            "unrealized_count": len(report.unrealized_lots),
        }
        typer.echo(json_mod.dumps(data, indent=2))
        return

    # Header
    console.print(
        Panel(
            f"  [bold]Capital Gains Tax Report — {report.fiscal_year}[/bold]  ({strategy})",
            border_style="cyan",
            padding=(0, 1),
        )
    )

    # Realized gains table
    if report.realized_lots:
        table = Table(title="Realized Capital Gains", box=box.SIMPLE_HEAVY, pad_edge=False)
        table.add_column("Stock", min_width=12)
        table.add_column("Buy Date", min_width=10)
        table.add_column("Sell Date", min_width=10)
        table.add_column("Days", justify="right", min_width=5)
        table.add_column("Qty", justify="right", min_width=4)
        table.add_column("Buy", justify="right", min_width=8)
        table.add_column("Sell", justify="right", min_width=8)
        table.add_column("Gain/Loss", justify="right", min_width=10)
        table.add_column("Type", min_width=5)

        for lot in report.realized_lots:
            gain_color = "green" if lot.gain >= 0 else "red"
            type_color = "yellow" if lot.tax_category == "STCG" else "green"
            table.add_row(
                lot.ticker.replace(".NS", ""),
                lot.buy_date,
                lot.sell_date,
                str(lot.holding_days),
                str(lot.shares),
                f"{lot.buy_price:,.1f}",
                f"{lot.sell_price:,.1f}",
                f"[{gain_color}]{lot.gain:+,.0f}[/{gain_color}]",
                f"[{type_color}]{lot.tax_category}[/{type_color}]",
            )
        console.print(table)
    else:
        console.print("  [dim]No realized gains in this fiscal year.[/dim]")

    # Tax summary
    stcg_color = "red" if report.total_stcg > 0 else "green"
    ltcg_color = "red" if report.taxable_ltcg > 0 else "green"

    summary = (
        f"  [bold]STCG[/bold] (20%):  [{stcg_color}]{report.total_stcg:+,.0f}[/{stcg_color}]"
        f"    Tax: {report.estimated_stcg_tax:,.0f}\n"
        f"  [bold]LTCG[/bold] (12.5%): [{ltcg_color}]{report.total_ltcg:+,.0f}[/{ltcg_color}]"
        f"    Exemption: {report.ltcg_exemption:,.0f}"
        f"    Taxable: {report.taxable_ltcg:,.0f}"
        f"    Tax: {report.estimated_ltcg_tax:,.0f}\n"
        f"\n  [bold]Total Estimated Tax: {report.total_estimated_tax:,.0f} INR[/bold]\n"
        f"  Transaction Costs (STT etc.): {report.total_transaction_costs:,.0f}"
    )
    if report.total_dividends > 0:
        summary += f"\n  Dividend Income: {report.total_dividends:,.0f}"

    console.print(Panel(summary, title="[bold]TAX SUMMARY[/bold]", border_style="red", padding=(0, 1)))

    # Unrealized gains
    if report.unrealized_lots:
        table = Table(title="Unrealized Holdings (Projected Tax Category)", box=box.SIMPLE, pad_edge=False)
        table.add_column("Stock", min_width=12)
        table.add_column("Buy Date", min_width=10)
        table.add_column("Days", justify="right", min_width=5)
        table.add_column("Qty", justify="right", min_width=4)
        table.add_column("Buy", justify="right", min_width=8)
        table.add_column("CMP", justify="right", min_width=8)
        table.add_column("Unrealized", justify="right", min_width=10)
        table.add_column("Type", min_width=5)

        for lot in sorted(report.unrealized_lots, key=lambda x: -abs(x.unrealized_gain)):
            gain_color = "green" if lot.unrealized_gain >= 0 else "red"
            type_color = "yellow" if lot.projected_category == "STCG" else "green"
            table.add_row(
                lot.ticker.replace(".NS", ""),
                lot.buy_date,
                str(lot.holding_days),
                str(lot.shares),
                f"{lot.buy_price:,.1f}",
                f"{lot.current_price:,.1f}" if lot.current_price > 0 else "-",
                f"[{gain_color}]{lot.unrealized_gain:+,.0f}[/{gain_color}]",
                f"[{type_color}]{lot.projected_category}[/{type_color}]",
            )
        console.print(table)

    console.print()


# --- Watchlist Commands ---

watch_app = typer.Typer(name="watch", help="Manage stock watchlist and alerts.")


@watch_app.callback(invoke_without_command=True)
def watch_list(
    ctx: typer.Context,
    alerts: Annotated[bool, typer.Option("--alerts", "-a", help="Show only stocks with signals")] = False,
):
    """Show watchlist with current prices and signals."""
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.table import Table

    from diamond.data.watchlist import check_signals, fetch_watchlist_prices, load_watchlist

    if ctx.invoked_subcommand is not None:
        return

    for name in ["yfinance", "urllib3"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()
    entries = load_watchlist()

    if not entries:
        console.print("\n  Watchlist is empty. Add stocks with: [cyan]diamond watch add RELIANCE.NS[/cyan]\n")
        return

    console.print(f"\n  [dim]Fetching prices for {len(entries)} stocks...[/dim]")
    prices = fetch_watchlist_prices(entries)
    signals = check_signals(entries, prices)

    # Build signal map
    signal_map: dict[str, list[str]] = {}
    for sig in signals:
        signal_map.setdefault(sig.ticker, []).append(sig.message)

    # Filter to alerts only if requested
    if alerts:
        entries = {t: e for t, e in entries.items() if t in signal_map}
        if not entries:
            console.print("\n  No active signals on watchlist.\n")
            return

    table = Table(title=f"Watchlist ({len(entries)} stocks)", box=box.SIMPLE_HEAVY, pad_edge=False)
    table.add_column("Stock", min_width=14)
    table.add_column("Sector", style="dim", min_width=12)
    table.add_column("CMP", justify="right", min_width=8)
    table.add_column("Chg%", justify="right", min_width=6)
    table.add_column("Alerts", min_width=8)
    table.add_column("Signals", min_width=30)

    for ticker, entry in sorted(entries.items()):
        pd = prices.get(ticker, {})
        price = pd.get("price", 0)
        change = pd.get("change_pct", 0)
        sector = pd.get("sector", "-")

        change_color = "green" if change >= 0 else "red"

        # Alert thresholds
        alert_parts = []
        if entry.price_above:
            alert_parts.append(f">{entry.price_above:,.0f}")
        if entry.price_below:
            alert_parts.append(f"<{entry.price_below:,.0f}")

        # Signals
        sig_list = signal_map.get(ticker, [])
        sig_str = "; ".join(sig_list) if sig_list else "[dim]-[/dim]"
        if sig_list:
            sig_str = f"[yellow]{sig_str}[/yellow]"

        table.add_row(
            ticker.replace(".NS", ""),
            sector[:12] if sector != "Unknown" else "-",
            f"{price:,.1f}" if price > 0 else "-",
            f"[{change_color}]{change:+.1f}%[/{change_color}]",
            " ".join(alert_parts) if alert_parts else "-",
            sig_str,
        )

    console.print(table)
    console.print()


@watch_app.command("add")
def watch_add(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g., RELIANCE.NS)")],
    note: Annotated[str, typer.Option("--note", "-n", help="Optional note")] = "",
    above: Annotated[Optional[float], typer.Option("--above", help="Alert when price crosses above")] = None,
    below: Annotated[Optional[float], typer.Option("--below", help="Alert when price crosses below")] = None,
):
    """Add a stock to the watchlist."""
    from diamond.data.watchlist import add_ticker

    entry = add_ticker(ticker, notes=note, price_above=above, price_below=below)
    typer.echo(f"Added {entry.ticker} to watchlist")
    if above:
        typer.echo(f"  Alert when price > {above:,.0f}")
    if below:
        typer.echo(f"  Alert when price < {below:,.0f}")


@watch_app.command("remove")
def watch_remove(
    ticker: Annotated[str, typer.Argument(help="Stock ticker to remove")],
):
    """Remove a stock from the watchlist."""
    from diamond.data.watchlist import remove_ticker

    if remove_ticker(ticker):
        if not ticker.endswith(".NS"):
            ticker = f"{ticker}.NS"
        typer.echo(f"Removed {ticker} from watchlist")
    else:
        typer.echo(f"{ticker} not found in watchlist")


app.add_typer(watch_app, name="watch")


# --- Compare Command ---


@app.command()
def compare(
    strategies: Annotated[list[str], typer.Argument(help="Strategies to compare")],
    no_risk: Annotated[bool, typer.Option("--no-risk", help="Skip risk metrics (faster)")] = False,
):
    """Side-by-side comparison of portfolio strategies."""
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.table import Table

    from diamond.analysis.compare import compare_strategies

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()
    console.print(f"\n  [dim]Comparing {', '.join(strategies)}...[/dim]")

    snapshots = compare_strategies(strategies, include_risk=not no_risk)

    table = Table(title="Strategy Comparison", box=box.SIMPLE_HEAVY, pad_edge=False)
    table.add_column("Metric", style="bold", min_width=16)
    for s in snapshots:
        mode_tag = f" ({s.mode})" if s.mode != "live" else ""
        table.add_column(f"{s.name.upper()}{mode_tag}", justify="right", min_width=14)

    def _add_row(label: str, values: list[str]) -> None:
        table.add_row(label, *values)

    _add_row("NAV", [f"{s.nav:,.0f}" for s in snapshots])
    _add_row(
        "Return",
        [
            f"[{'green' if s.return_pct >= 0 else 'red'}]{s.return_pct:+.1f}%[/{'green' if s.return_pct >= 0 else 'red'}]"
            for s in snapshots
        ],
    )
    _add_row("Cash", [f"{s.cash:,.0f}" for s in snapshots])
    _add_row("Holdings", [str(s.holdings_count) for s in snapshots])
    _add_row("Fees", [f"{s.total_fees:,.0f}" for s in snapshots])
    _add_row("Last Rebalance", [s.last_rebalance or "never" for s in snapshots])

    if not no_risk:
        _add_row("Beta", [f"{s.beta:.2f}" for s in snapshots])
        _add_row("Volatility", [f"{s.volatility:.1f}%" for s in snapshots])
        _add_row("Drawdown", [f"{s.max_drawdown:.1f}%" for s in snapshots])

    _add_row("", ["" for _ in snapshots])  # separator

    # Top holdings
    max_top = max((len(s.top_holdings) for s in snapshots), default=0)
    for i in range(min(max_top, 5)):
        label = f"Top {i + 1}"
        vals = []
        for s in snapshots:
            if i < len(s.top_holdings):
                t, v, w = s.top_holdings[i]
                vals.append(f"{t.replace('.NS', '')[:10]} ({w:.0f}%)")
            else:
                vals.append("-")
        _add_row(label, vals)

    console.print(table)

    # Sector comparison
    all_sectors = set()
    for s in snapshots:
        all_sectors.update(s.sector_exposure.keys())

    if all_sectors:
        sec_table = Table(title="Sector Exposure (%)", box=box.SIMPLE, pad_edge=False)
        sec_table.add_column("Sector", min_width=16)
        for s in snapshots:
            sec_table.add_column(s.name.upper(), justify="right", min_width=10)

        for sector in sorted(all_sectors):
            vals = [f"{s.sector_exposure.get(sector, 0):.1f}%" for s in snapshots]
            sec_table.add_row(sector, *vals)

        console.print(sec_table)

    console.print()


# --- What-If Command ---


@app.command()
def whatif(
    strategy: Annotated[str, typer.Argument(help="Strategy to simulate on")] = "gods_plan",
    add: Annotated[Optional[list[str]], typer.Option("--add", help="Tickers to add")] = None,
    remove: Annotated[Optional[list[str]], typer.Option("--remove", help="Tickers to remove")] = None,
):
    """Simulate portfolio changes and show impact."""
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.analysis.compare import simulate_whatif

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    add_list = add or []
    remove_list = remove or []

    if not add_list and not remove_list:
        typer.echo("Specify --add and/or --remove tickers.")
        typer.echo("Example: diamond whatif gods_plan --add RELIANCE.NS --remove TCS.NS")
        raise typer.Exit(1)

    console.print(f"\n  [dim]Simulating changes on {strategy}...[/dim]")

    result = simulate_whatif(strategy, add_list, remove_list)

    # Before/After table
    table = Table(title="What-If Analysis", box=box.SIMPLE_HEAVY, pad_edge=False)
    table.add_column("Metric", style="bold", min_width=16)
    table.add_column("Before", justify="right", min_width=14)
    table.add_column("After", justify="right", min_width=14)
    table.add_column("Delta", justify="right", min_width=10)

    b, a, d = result.before, result.after, result.delta

    table.add_row("NAV", f"{b['nav']:,.0f}", f"{a['nav']:,.0f}", f"{d['nav']:+,.0f}")
    table.add_row("Cash", f"{b['cash']:,.0f}", f"{a['cash']:,.0f}", f"{d['cash']:+,.0f}")
    table.add_row("Holdings", str(b["holdings_count"]), str(a["holdings_count"]), f"{d['holdings_count']:+d}")

    console.print(table)

    # Sector changes
    all_sectors = set(list(b.get("sector_exposure", {}).keys()) + list(a.get("sector_exposure", {}).keys()))
    if all_sectors:
        sec_table = Table(title="Sector Exposure (%)", box=box.SIMPLE, pad_edge=False)
        sec_table.add_column("Sector", min_width=16)
        sec_table.add_column("Before", justify="right", min_width=8)
        sec_table.add_column("After", justify="right", min_width=8)

        for sector in sorted(all_sectors):
            before_pct = b.get("sector_exposure", {}).get(sector, 0)
            after_pct = a.get("sector_exposure", {}).get(sector, 0)
            if before_pct > 0 or after_pct > 0:
                sec_table.add_row(sector, f"{before_pct:.1f}%", f"{after_pct:.1f}%")

        console.print(sec_table)

    # Warnings
    if result.warnings:
        warning_text = "\n".join(f"  - {w}" for w in result.warnings)
        console.print(
            Panel(
                warning_text,
                title="[bold yellow]WARNINGS[/bold yellow]",
                border_style="yellow",
                padding=(0, 1),
            )
        )

    console.print()


# --- Orders Command ---


@app.command()
def orders(
    strategy: Annotated[str, typer.Argument(help="Strategy to show orders for")] = "gods_plan",
    status_filter: Annotated[
        Optional[str],
        typer.Option(
            "--status",
            "-s",
            help="Filter by status: PENDING,PLACED,FILLED,PARTIAL,FAILED,CANCELLED",
        ),
    ] = None,
    cancel: Annotated[Optional[str], typer.Option("--cancel", help="Cancel order by ID")] = None,
    cancel_all: Annotated[bool, typer.Option("--cancel-all", help="Cancel all pending orders")] = False,
    since: Annotated[Optional[str], typer.Option("--since", help="Show orders since date (YYYY-MM-DD)")] = None,
):
    """View and manage order book."""
    from rich import box
    from rich.console import Console
    from rich.table import Table

    from diamond.execution.orders import OrderBook, get_order_summary

    console = Console()
    book = OrderBook(strategy)

    if cancel:
        if book.cancel_order(cancel):
            typer.echo(f"Order {cancel} cancelled.")
        else:
            typer.echo(f"Could not cancel order {cancel} (not found or already completed).")
        return

    if cancel_all:
        count = book.cancel_all_pending()
        typer.echo(f"Cancelled {count} pending order(s).")
        return

    # Show order list
    order_list = book.get_orders(status=status_filter, since=since)

    if not order_list:
        typer.echo(f"No orders found for {strategy}.")
        return

    table = Table(title=f"Orders — {strategy} ({len(order_list)} total)", box=box.SIMPLE_HEAVY, pad_edge=False)
    table.add_column("ID", min_width=20, max_width=30, overflow="ellipsis")
    table.add_column("Action", min_width=5)
    table.add_column("Stock", min_width=12)
    table.add_column("Qty", justify="right", min_width=5)
    table.add_column("Filled", justify="right", min_width=5)
    table.add_column("Price", justify="right", min_width=8)
    table.add_column("Type", min_width=6)
    table.add_column("Status", min_width=8)
    table.add_column("Created", min_width=16)

    status_colors = {
        "PENDING": "yellow",
        "PLACED": "blue",
        "FILLED": "green",
        "PARTIAL": "cyan",
        "FAILED": "red",
        "CANCELLED": "dim",
    }

    for order in order_list:
        action_color = "green" if order.action == "BUY" else "red"
        s_color = status_colors.get(order.status, "white")

        table.add_row(
            order.id[-25:],
            f"[{action_color}]{order.action}[/{action_color}]",
            order.ticker.replace(".NS", ""),
            str(order.shares),
            str(order.filled_shares),
            f"{order.price:,.1f}",
            order.order_type,
            f"[{s_color}]{order.status}[/{s_color}]",
            order.created_at[:16],
        )

    console.print(table)

    # Summary
    summary = get_order_summary(book)
    typer.echo(
        f"\n  Filled: {summary['filled']}  Partial: {summary['partial']}  "
        f"Pending: {summary['pending']}  Failed: {summary['failed']}  "
        f"Cancelled: {summary['cancelled']}"
    )
    typer.echo(f"  Total Value: {summary['total_value']:,.0f}  Filled Value: {summary['filled_value']:,.0f}")
    typer.echo("")


# --- Attribution Command ---


@app.command()
def attribution(
    strategy: Annotated[str, typer.Argument(help="Strategy for attribution analysis")] = "gods_plan",
    period: Annotated[
        str,
        typer.Option("--period", "-p", help="Lookback: 1M, 3M, 6M, 1Y, YTD, or YYYY-MM-DD:YYYY-MM-DD"),
    ] = "3M",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """Performance attribution — stock & sector contribution analysis."""
    import json as json_mod
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.analysis.attribution import compute_attribution

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()
    console.print(f"\n  [dim]Computing {period} attribution for {strategy}...[/dim]")

    report = compute_attribution(strategy, period=period)

    if json_output:
        data = {
            "strategy": report.strategy,
            "period": report.period,
            "start_date": report.start_date,
            "end_date": report.end_date,
            "portfolio_return": report.portfolio_return,
            "benchmark_return": report.benchmark_return,
            "active_return": report.active_return,
            "tracking_error": report.tracking_error,
            "stocks": [
                {
                    "ticker": s.ticker,
                    "sector": s.sector,
                    "weight": s.weight,
                    "return": s.stock_return,
                    "contribution": s.contribution,
                    "active_weight": s.active_weight,
                }
                for s in report.stock_attributions
            ],
            "sectors": [
                {
                    "sector": s.sector,
                    "portfolio_weight": s.portfolio_weight,
                    "benchmark_weight": s.benchmark_weight,
                    "allocation": s.allocation_effect,
                    "selection": s.selection_effect,
                    "interaction": s.interaction_effect,
                    "total": s.total_effect,
                }
                for s in report.sector_attributions
            ],
        }
        typer.echo(json_mod.dumps(data, indent=2))
        return

    if not report.stock_attributions:
        typer.echo(f"No attribution data — portfolio may be empty or no price data for {period}.")
        return

    # Summary
    port_color = "green" if report.portfolio_return >= 0 else "red"
    bm_color = "green" if report.benchmark_return >= 0 else "red"
    active_color = "green" if report.active_return >= 0 else "red"

    console.print(
        Panel(
            f"  Period: {report.period}  ({report.start_date} → {report.end_date})\n"
            f"  Portfolio: [{port_color}]{report.portfolio_return:+.2%}[/{port_color}]    "
            f"Benchmark: [{bm_color}]{report.benchmark_return:+.2%}[/{bm_color}]    "
            f"Active: [{active_color}]{report.active_return:+.2%}[/{active_color}]    "
            f"Tracking Error: {report.tracking_error:.2%}",
            title="[bold]PERFORMANCE ATTRIBUTION[/bold]",
            border_style="cyan",
            padding=(0, 1),
        )
    )

    # Top / Bottom contributors
    table = Table(title="Top Contributors", box=box.SIMPLE, pad_edge=False)
    table.add_column("Stock", min_width=14)
    table.add_column("Sector", style="dim", min_width=12)
    table.add_column("Weight", justify="right", min_width=8)
    table.add_column("Return", justify="right", min_width=8)
    table.add_column("Contribution", justify="right", min_width=10)
    table.add_column("Active Wt", justify="right", min_width=8)

    for s in report.top_contributors:
        ret_color = "green" if s.stock_return >= 0 else "red"
        c_color = "green" if s.contribution >= 0 else "red"
        table.add_row(
            s.ticker.replace(".NS", ""),
            s.sector[:12],
            f"{s.weight:.1%}",
            f"[{ret_color}]{s.stock_return:+.1%}[/{ret_color}]",
            f"[{c_color}]{s.contribution:+.2%}[/{c_color}]",
            f"{s.active_weight:+.1%}",
        )
    console.print(table)

    if report.bottom_contributors:
        table2 = Table(title="Bottom Contributors", box=box.SIMPLE, pad_edge=False)
        table2.add_column("Stock", min_width=14)
        table2.add_column("Sector", style="dim", min_width=12)
        table2.add_column("Weight", justify="right", min_width=8)
        table2.add_column("Return", justify="right", min_width=8)
        table2.add_column("Contribution", justify="right", min_width=10)
        table2.add_column("Active Wt", justify="right", min_width=8)

        for s in report.bottom_contributors:
            ret_color = "green" if s.stock_return >= 0 else "red"
            c_color = "green" if s.contribution >= 0 else "red"
            table2.add_row(
                s.ticker.replace(".NS", ""),
                s.sector[:12],
                f"{s.weight:.1%}",
                f"[{ret_color}]{s.stock_return:+.1%}[/{ret_color}]",
                f"[{c_color}]{s.contribution:+.2%}[/{c_color}]",
                f"{s.active_weight:+.1%}",
            )
        console.print(table2)

    # Sector attribution (Brinson)
    if report.sector_attributions:
        sec_table = Table(title="Sector Attribution (Brinson)", box=box.SIMPLE_HEAVY, pad_edge=False)
        sec_table.add_column("Sector", min_width=16)
        sec_table.add_column("Port Wt", justify="right", min_width=8)
        sec_table.add_column("BM Wt", justify="right", min_width=8)
        sec_table.add_column("Allocation", justify="right", min_width=10)
        sec_table.add_column("Selection", justify="right", min_width=10)
        sec_table.add_column("Total", justify="right", min_width=10)

        for s in sorted(report.sector_attributions, key=lambda x: -abs(x.total_effect)):
            t_color = "green" if s.total_effect >= 0 else "red"
            sec_table.add_row(
                s.sector,
                f"{s.portfolio_weight:.1%}",
                f"{s.benchmark_weight:.1%}",
                f"{s.allocation_effect:+.2%}",
                f"{s.selection_effect:+.2%}",
                f"[{t_color}]{s.total_effect:+.2%}[/{t_color}]",
            )
        console.print(sec_table)

    console.print()


# --- Export Command ---


@app.command("export")
def export_cmd(
    strategy: Annotated[str, typer.Argument(help="Strategy to export")] = "gods_plan",
    fmt: Annotated[str, typer.Option("--format", "-f", help="Format: all, md, csv-holdings, csv-trades, json")] = "all",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output directory path")] = None,
    since: Annotated[Optional[str], typer.Option("--since", help="Trade export since date (YYYY-MM-DD)")] = None,
):
    """Export portfolio reports (Markdown, CSV, JSON)."""
    from pathlib import Path

    from diamond.analysis.export import (
        export_all,
        export_full_json,
        export_holdings_csv,
        export_portfolio_summary,
        export_trades_csv,
    )

    out_dir = Path(output) if output else None

    if fmt == "all":
        results = export_all(strategy, out_dir)
        for r in results:
            typer.echo(f"  {r.format.upper():>4s}  {r.report_type:<10s}  {r.rows} rows  → {r.path}")
    elif fmt == "md":
        r = export_portfolio_summary(strategy, out_dir)
        typer.echo(f"  Summary → {r.path}")
    elif fmt == "csv-holdings":
        r = export_holdings_csv(strategy, out_dir)
        typer.echo(f"  Holdings CSV ({r.rows} rows) → {r.path}")
    elif fmt == "csv-trades":
        r = export_trades_csv(strategy, out_dir, since=since)
        typer.echo(f"  Trades CSV ({r.rows} rows) → {r.path}")
    elif fmt == "json":
        r = export_full_json(strategy, out_dir)
        typer.echo(f"  Full JSON → {r.path}")
    else:
        typer.echo(f"Unknown format '{fmt}'. Use: all, md, csv-holdings, csv-trades, json")
        raise typer.Exit(1)

    typer.echo("")


# --- Accumulate Command ---


@app.command()
def accumulate(
    capital: Annotated[float, typer.Option("--capital", "-c", help="Initial capital to deploy")] = 500000,
    add_cash_amount: Annotated[
        Optional[float], typer.Option("--add-cash", help="Add cash to accumulate portfolio")
    ] = None,
    status_only: Annotated[bool, typer.Option("--status", help="Show accumulate portfolio status")] = False,
    opportunities: Annotated[
        bool, typer.Option("--opportunities", help="Show buy opportunities without executing")
    ] = False,
    deploy: Annotated[bool, typer.Option("--deploy", help="Execute deployment of available cash")] = False,
    review: Annotated[bool, typer.Option("--review", help="Review holdings for quality drops and stop-losses")] = False,
    swap: Annotated[bool, typer.Option("--swap", help="Execute swap suggestions from review")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be bought without executing")] = False,
    force_verdict: Annotated[
        Optional[str],
        typer.Option("--verdict", help="Override market verdict: DEPLOY, WAIT, DEFENSIVE"),
    ] = None,
    reset: Annotated[bool, typer.Option("--reset", help="Reset accumulate portfolio")] = False,
):
    """Long-term capital accumulation with active review.

    Deploy fresh capital into quality stocks for a 10-year horizon.
    Quarterly review flags deteriorating holdings and suggests swaps.

    Examples:
        diamond accumulate --capital 500000              # Initialize with 5L
        diamond accumulate --status                      # Show portfolio
        diamond accumulate --opportunities               # See what to buy
        diamond accumulate --deploy                      # Execute buys
        diamond accumulate --deploy --dry-run            # Preview without buying
        diamond accumulate --add-cash 50000              # Top up cash
        diamond accumulate --deploy --verdict DEPLOY     # Force aggressive deployment
        diamond accumulate --review                      # Review holdings quality
        diamond accumulate --review --swap               # Review + execute swaps
        diamond accumulate --review --swap --dry-run     # Preview swaps
    """
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.data.ledger import Ledger
    from diamond.strategies.accumulate import (
        add_cash as do_add_cash,
    )
    from diamond.strategies.accumulate import (
        execute_accumulation,
        execute_swaps,
        get_accumulate_status,
        plan_accumulation,
        review_holdings,
    )

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()
    strategy_name = "accumulate"

    if reset:
        ledger = Ledger(strategy_name)
        ledger.reset(initial_capital=capital)
        typer.echo(f"Accumulate portfolio reset to {capital:,.0f} INR")
        return

    if add_cash_amount:
        new_balance = do_add_cash(strategy_name, add_cash_amount)
        typer.echo(f"Added {add_cash_amount:,.0f} INR. New cash balance: {new_balance:,.0f} INR")
        return

    # Initialize ledger if first run
    ledger = Ledger(strategy_name)
    if (
        not ledger.get_holdings()
        and ledger.get_cash() == get_config().risk.initial_capital
        and capital != get_config().risk.initial_capital
    ):
        ledger.reset(initial_capital=capital)
        typer.echo(f"Initialized accumulate portfolio with {capital:,.0f} INR")

    if status_only:
        st = get_accumulate_status(strategy_name)
        console.print(
            Panel(
                f"  Holdings:  {st['holdings_count']} stocks\n"
                f"  Cash:      {st['cash']:,.2f} INR\n"
                f"  Capital:   {st['initial_capital']:,.2f} INR\n"
                f"  Fees:      {st['total_fees']:,.2f} INR\n"
                f"  Trades:    {st['trade_count']}",
                title="[bold]ACCUMULATE PORTFOLIO[/bold]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

        if st["holdings"]:
            table = Table(box=box.SIMPLE, pad_edge=False)
            table.add_column("Stock", min_width=14)
            table.add_column("Qty", justify="right", min_width=5)
            table.add_column("Avg Price", justify="right", min_width=10)

            for ticker, shares in sorted(st["holdings"].items()):
                avg = ledger.get_avg_price(ticker)
                table.add_row(
                    ticker.replace(".NS", ""),
                    str(shares),
                    f"{avg:,.1f}",
                )
            console.print(table)
        console.print()
        return

    if review:
        console.print("\n  [dim]Reviewing holdings...[/dim]")

        report = review_holdings(strategy_name)

        # Summary panel
        console.print(
            Panel(
                f"  Reviewed:  {report.holdings_reviewed} holdings\n"
                f"  Healthy:   [green]{report.healthy_count}[/green]\n"
                f"  Watch:     [yellow]{report.watch_count}[/yellow]\n"
                f"  Sell:      [red]{report.sell_count}[/red]\n"
                f"  Last Review: {report.days_since_last_review or 'Never'} days ago\n"
                f"  Due:       {'Yes' if report.next_review_due else 'No'}",
                title="[bold]PORTFOLIO REVIEW[/bold]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

        if report.warnings:
            for w in report.warnings:
                console.print(f"  [yellow]! {w}[/yellow]")

        # Sell signals table
        if report.sell_signals:
            table = Table(title="Sell Signals", box=box.SIMPLE_HEAVY, pad_edge=False)
            table.add_column("Stock", min_width=14)
            table.add_column("Sector", style="dim", min_width=12)
            table.add_column("Qty", justify="right", min_width=5)
            table.add_column("Avg", justify="right", min_width=8)
            table.add_column("CMP", justify="right", min_width=8)
            table.add_column("P&L%", justify="right", min_width=7)
            table.add_column("Quality", justify="right", min_width=7)
            table.add_column("Signal", min_width=14)
            table.add_column("Action", min_width=6)

            for s in report.sell_signals:
                pnl_color = "green" if s.pnl_pct >= 0 else "red"
                sev_color = "red" if s.severity == "SELL" else "yellow"
                table.add_row(
                    s.ticker.replace(".NS", ""),
                    s.sector[:12],
                    str(s.shares),
                    f"{s.avg_price:,.1f}",
                    f"{s.current_price:,.1f}",
                    f"[{pnl_color}]{s.pnl_pct:+.1f}%[/{pnl_color}]",
                    f"{s.quality_score:.0f}",
                    s.signal_type,
                    f"[{sev_color}]{s.severity}[/{sev_color}]",
                )
            console.print(table)
        else:
            console.print("  [green]All holdings healthy.[/green]")

        # Swap suggestions table
        if report.swap_suggestions:
            table = Table(title="Swap Suggestions", box=box.SIMPLE_HEAVY, pad_edge=False)
            table.add_column("Sell", min_width=14)
            table.add_column("Q", justify="right", min_width=4)
            table.add_column("P&L%", justify="right", min_width=7)
            table.add_column("", min_width=3)
            table.add_column("Buy", min_width=14)
            table.add_column("Q", justify="right", min_width=4)
            table.add_column("Q Gain", justify="right", min_width=6)
            table.add_column("Capital", justify="right", min_width=10)

            for sw in report.swap_suggestions:
                table.add_row(
                    sw.sell_ticker.replace(".NS", ""),
                    f"{sw.sell_quality:.0f}",
                    f"{sw.sell_pnl_pct:+.1f}%",
                    "->",
                    sw.buy_ticker.replace(".NS", ""),
                    f"{sw.buy_quality:.0f}",
                    f"[green]+{sw.quality_gain:.0f}[/green]",
                    f"{sw.freed_capital:,.0f}",
                )
            console.print(table)

        # Execute swaps if --swap
        if swap and report.swap_suggestions:
            if dry_run:
                console.print("\n  [dim]DRY RUN -- no swaps executed[/dim]")
                result = execute_swaps(strategy_name, report, dry_run=True)
                console.print(f"  Would execute {result['sells']} sells + {result['buys']} buys")
            else:
                console.print(f"\n  [bold]Executing {len(report.swap_suggestions)} swaps...[/bold]")
                result = execute_swaps(strategy_name, report)
                if result["status"] == "executed":
                    console.print(f"  Executed {result['sells']} sells + {result['buys']} buys")
                    console.print(f"  Cash: {result['cash']:,.2f} INR")
                    console.print(f"  Holdings: {result['holdings']} stocks")
                else:
                    console.print(f"  Result: {result['status']}")
        elif swap and not report.swap_suggestions:
            console.print("  No swaps to execute.")

        # Execute review sells (non-swap) if sell signals but no --swap
        if not swap and report.sell_count > 0:
            console.print("\n  [dim]Use --swap to execute swap suggestions, or manually sell flagged holdings.[/dim]")

        console.print()
        return

    if opportunities or deploy:
        console.print("\n  [dim]Scanning for opportunities...[/dim]")

        plan = plan_accumulation(
            strategy_name,
            market_verdict=force_verdict,
        )

        # Show plan
        verdict_colors = {"DEPLOY": "green", "WAIT": "yellow", "DEFENSIVE": "red"}
        v_color = verdict_colors.get(plan.market_verdict, "white")

        console.print(
            Panel(
                f"  Market: [{v_color}]{plan.market_verdict}[/{v_color}]    "
                f"Cash: {plan.available_cash:,.0f}    "
                f"Deploy Budget: {plan.deploy_budget:,.0f} ({plan.deploy_pct:.0%})    "
                f"Positions: {plan.existing_positions}/20",
                title="[bold]ACCUMULATE PLAN[/bold]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

        if plan.warnings:
            for w in plan.warnings:
                console.print(f"  [yellow]! {w}[/yellow]")

        if plan.opportunities:
            table = Table(title="Buy Opportunities", box=box.SIMPLE_HEAVY, pad_edge=False)
            table.add_column("#", justify="right", min_width=3)
            table.add_column("Stock", min_width=14)
            table.add_column("Sector", style="dim", min_width=12)
            table.add_column("Quality", justify="right", min_width=7)
            table.add_column("CAGR", justify="right", min_width=6)
            table.add_column("Alpha", justify="right", min_width=6)
            table.add_column("Beta", justify="right", min_width=5)
            table.add_column("Amount", justify="right", min_width=10)
            table.add_column("Type", min_width=8)

            for i, opp in enumerate(plan.opportunities, 1):
                is_topup = opp.ticker in ledger.get_holdings()
                type_label = "[cyan]TOP-UP[/cyan]" if is_topup else "[green]NEW[/green]"

                q_color = "green" if opp.quality_score >= 60 else "yellow" if opp.quality_score >= 40 else "white"

                table.add_row(
                    str(i),
                    opp.ticker.replace(".NS", ""),
                    opp.sector[:12],
                    f"[{q_color}]{opp.quality_score:.0f}[/{q_color}]",
                    f"{opp.cagr:.0%}",
                    f"{opp.alpha:.2f}",
                    f"{opp.beta:.2f}",
                    f"{opp.suggested_amount:,.0f}",
                    type_label,
                )

            total_deploy = sum(o.suggested_amount for o in plan.opportunities)
            console.print(table)
            console.print(f"\n  Total deployment: {total_deploy:,.0f} INR across {len(plan.opportunities)} positions")
        else:
            console.print("  No opportunities found matching quality criteria.")

        # Execute if --deploy
        if deploy and plan.opportunities:
            if dry_run:
                console.print("\n  [dim]DRY RUN -- no trades executed[/dim]")
                result = execute_accumulation(strategy_name, plan, dry_run=True)
                console.print(
                    f"  Would deploy: {result.get('total_deploy', 0):,.0f} INR across {result['trades']} trades"
                )
            else:
                console.print(f"\n  [bold]Executing {len(plan.opportunities)} buys...[/bold]")
                result = execute_accumulation(strategy_name, plan)
                if result["status"] == "executed":
                    console.print(f"  Executed {result['trades']} trades")
                    console.print(f"  NAV:  {result['nav']:,.2f} INR")
                    console.print(f"  Cash: {result['cash']:,.2f} INR")
                    console.print(f"  Holdings: {result['holdings']} stocks")
                else:
                    console.print(f"  Result: {result['status']}")

        console.print()
        return

    # Default: show help
    typer.echo("Use --status, --opportunities, --deploy, --review, or --add-cash.")
    typer.echo("Run 'diamond accumulate --help' for full options.")


# --- Drift Check Command ---


@app.command()
def drift(
    strategy: Annotated[str, typer.Argument(help="Strategy to check drift for")] = "gods_plan",
    capital: Annotated[float, typer.Option("--capital", "-c", help="Capital for target computation")] = 500000,
    rebalance: Annotated[
        bool, typer.Option("--rebalance", help="Execute partial rebalance for drifted positions")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview rebalance trades")] = False,
):
    """Check portfolio drift from target allocation, optionally rebalance.

    Use --rebalance to execute trades for positions that have drifted beyond threshold.
    """
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.data.ledger import Ledger
    from diamond.execution.smart_rebalance import compute_drift

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    if strategy not in VALID_STRATEGIES:
        typer.echo(f"Unknown strategy '{strategy}'. Choose from: {', '.join(VALID_STRATEGIES)}")
        raise typer.Exit(1)

    # Auto-detect paper
    cfg = get_config()
    ledger_name = strategy
    live_ledger = Ledger(strategy)
    mode = "live"
    if not live_ledger.get_holdings():
        paper_db = cfg.ledger_dir / f"{strategy}_paper.db"
        if paper_db.exists():
            ledger_name = f"{strategy}_paper"
            mode = "paper"
        else:
            typer.echo(f"No holdings found for {strategy}.")
            raise typer.Exit(1)

    ledger = Ledger(ledger_name)
    holdings = ledger.get_holdings()

    console.print(f"\n  [dim]Checking drift for {strategy} ({mode})...[/dim]")

    # Get target allocation
    strat = _resolve_strategy(strategy)
    candidates = strat.screen(None)
    if hasattr(candidates, "empty") and candidates.empty:
        typer.echo("Screening produced no candidates.")
        raise typer.Exit(1)

    nav = ledger.get_portfolio_value({})  # Will use prices below
    alloc_capital = max(nav, capital)
    target = strat.allocate(candidates, alloc_capital)

    # Fetch prices
    from diamond.data.market import download_prices

    all_tickers = list(set(list(holdings.keys()) + list(target.keys())))
    prices = {}
    try:
        df = download_prices(all_tickers, period_days=5, use_cache=True)
        for col in df.columns:
            series = df[col].dropna()
            if len(series) > 0:
                prices[col] = float(series.iloc[-1])
    except Exception:
        pass

    report = compute_drift(holdings, target, prices)

    # Display
    verdict_color = "red" if report.needs_rebalance else "green"
    verdict = "REBALANCE NEEDED" if report.needs_rebalance else "WITHIN THRESHOLD"

    console.print(
        Panel(
            f"  [{verdict_color}]{verdict}[/{verdict_color}]  —  {report.reason}",
            title="[bold]DRIFT ANALYSIS[/bold]",
            border_style=verdict_color,
            padding=(0, 1),
        )
    )

    if report.drifted_tickers:
        table = Table(title="Position Drift", box=box.SIMPLE, pad_edge=False)
        table.add_column("Stock", min_width=14)
        table.add_column("Current Wt", justify="right", min_width=10)
        table.add_column("Target Wt", justify="right", min_width=10)
        table.add_column("Drift", justify="right", min_width=8)

        for ticker, cur_wt, tgt_wt in report.drifted_tickers[:15]:
            d = abs(cur_wt - tgt_wt)
            d_color = (
                "red"
                if d > cfg.rebalance.drift_threshold
                else "yellow"
                if d > cfg.rebalance.drift_threshold * 0.5
                else "green"
            )
            table.add_row(
                ticker.replace(".NS", ""),
                f"{cur_wt:.1%}",
                f"{tgt_wt:.1%}",
                f"[{d_color}]{d:.1%}[/{d_color}]",
            )

        console.print(table)

    console.print(f"\n  Max drift: {report.max_drift:.2%}  |  Mean drift: {report.mean_drift:.2%}")
    console.print(f"  Threshold: {cfg.rebalance.drift_threshold:.2%}")

    if report.needs_rebalance and rebalance:
        from diamond.execution.executor import execute

        console.print("\n  [bold]Executing partial rebalance...[/bold]")

        # Build target allocation only for drifted positions
        result = execute(
            strategy=ledger_name,
            target_allocation=target,
            capital=alloc_capital,
            force=True,
            dry_run=dry_run,
            smart=True,
        )

        if result["status"] == "dry_run":
            console.print(f"  DRY RUN: {result['trades']} trades planned")
        elif result["status"] == "executed":
            console.print(f"  Executed {result['trades']} trades")
            console.print(f"  Cash: {result['cash']:,.2f} INR  |  NAV: {result['nav']:,.2f} INR")
        elif result["status"] == "no_trades":
            console.print("  No trades needed after smart filtering")
        else:
            console.print(f"  Result: {result['status']}")
    elif report.needs_rebalance and not rebalance:
        console.print("\n  Use [cyan]--rebalance[/cyan] to act on drift  |  Add [cyan]--dry-run[/cyan] to preview\n")
    else:
        console.print()


# --- Today Command ---


@app.command()
def today(
    strategy: Annotated[str, typer.Argument(help="Strategy to report on")] = "accumulate",
    fast: Annotated[bool, typer.Option("--fast", "-f", help="Skip slow data fetches")] = False,
):
    """Your daily briefing — market, portfolio, opportunities, and insights."""
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.daily.today import get_today_briefing

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    console.print("\n  [dim]Loading your daily briefing...[/dim]")

    briefing = get_today_briefing(
        strategy=strategy,
        skip_market=False,
        skip_opportunities=fast,
    )

    # Header
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    console.print(
        Panel(
            f"  {briefing.greeting}! Here's your market brief for [bold]{date_str}[/bold]",
            border_style="bright_cyan",
            padding=(0, 1),
        )
    )

    # Market snapshot
    if briefing.market:
        m = briefing.market
        v_colors = {"DEPLOY": "green", "WAIT": "yellow", "DEFENSIVE": "red"}
        v_color = v_colors.get(m.verdict, "white")
        nifty_color = "green" if m.nifty_change_pct >= 0 else "red"

        market_text = (
            f"  Nifty 50    [{nifty_color}]{m.nifty_price:,.0f}  ({m.nifty_change_pct:+.2f}%)[/{nifty_color}]\n"
            f"  VIX         {m.vix:.1f} ({m.vix_regime})\n"
            f"  Breadth     {m.breadth_pct:.0f}% ({m.breadth_regime})\n"
            f"  RSI         {m.rsi:.0f} ({m.momentum})\n"
            f"  Trend       {m.trend}  |  200 DMA dist: {m.distance_200dma_pct:+.1f}%\n"
            f"  Verdict     [{v_color}]{m.verdict}[/{v_color}] (score: {m.score:+d}/100)"
        )
        console.print(Panel(market_text, title="[bold]MARKET[/bold]", border_style="blue", padding=(0, 1)))

    # Portfolio snapshot
    if briefing.portfolio:
        p = briefing.portfolio
        day_color = "green" if p.day_change_pct >= 0 else "red"
        total_color = "green" if p.total_return_pct >= 0 else "red"

        port_text = (
            f"  NAV         {p.nav:,.0f} INR  [{day_color}]{p.day_change_pct:+.2f}% today ({p.day_change_inr:+,.0f})[/{day_color}]\n"
            f"  Cash        {p.cash:,.0f} INR\n"
            f"  Holdings    {p.holdings_count} stocks\n"
            f"  Total P&L   [{total_color}]{p.total_return_pct:+.1f}%[/{total_color}] since inception"
        )
        if p.top_gainer:
            gainer_color = "green" if p.top_gainer_pct >= 0 else "red"
            loser_color = "green" if p.top_loser_pct >= 0 else "red"
            port_text += (
                f"\n  Top         [{gainer_color}]{p.top_gainer.replace('.NS', '')} {p.top_gainer_pct:+.1f}%[/{gainer_color}]"
                f"  |  Bottom  [{loser_color}]{p.top_loser.replace('.NS', '')} {p.top_loser_pct:+.1f}%[/{loser_color}]"
            )
        console.print(Panel(port_text, title="[bold]PORTFOLIO[/bold]", border_style="green", padding=(0, 1)))

    elif not briefing.portfolio:
        console.print(
            Panel(
                f"  No holdings found for '{strategy}'. Run `diamond accumulate --deploy` to start.",
                title="[bold]PORTFOLIO[/bold]",
                border_style="dim",
                padding=(0, 1),
            )
        )

    # Sector rotation
    if briefing.sector_moves:
        sec_table = Table(box=box.SIMPLE, pad_edge=False, show_header=True, title="Sector Rotation (today)")
        sec_table.add_column("Sector", min_width=16)
        sec_table.add_column("Change", justify="right", min_width=8)
        sec_table.add_column("", min_width=6)

        for sm in briefing.sector_moves[:8]:
            color = "green" if sm.direction == "UP" else "red" if sm.direction == "DOWN" else "dim"
            arrow = "^" if sm.direction == "UP" else "v" if sm.direction == "DOWN" else "-"
            sec_table.add_row(
                sm.sector,
                f"[{color}]{sm.change_pct:+.2f}%[/{color}]",
                f"[{color}]{arrow}[/{color}]",
            )
        console.print(sec_table)

    # Opportunities
    if briefing.opportunities:
        opp_parts = []
        for opp in briefing.opportunities:
            opp_parts.append(f"  {opp.ticker.replace('.NS', '')} (Q={opp.quality_score:.0f}) — {opp.reason}")
        console.print(
            Panel(
                "\n".join(opp_parts),
                title="[bold]OPPORTUNITIES[/bold]",
                border_style="yellow",
                padding=(0, 1),
            )
        )

    # Alerts
    if briefing.alerts:
        alert_text = "\n".join(f"  {a}" for a in briefing.alerts)
        console.print(Panel(alert_text, title="[bold red]ALERTS[/bold red]", border_style="red", padding=(0, 1)))

    # Daily insight
    if briefing.insight:
        console.print(
            Panel(
                f"  {briefing.insight}",
                title="[bold]INSIGHT OF THE DAY[/bold]",
                border_style="bright_magenta",
                padding=(0, 1),
            )
        )

    console.print()


# --- Learn Command ---


@app.command()
def learn(
    topic: Annotated[
        Optional[int],
        typer.Option("--topic", "-t", help="Topic number (0-9). Default: rotates daily."),
    ] = None,
    list_topics: Annotated[bool, typer.Option("--list", "-l", help="List all available topics")] = False,
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="Portfolio for examples")] = "accumulate",
):
    """Daily market education — concepts explained using YOUR portfolio."""
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.daily.learn import get_daily_lesson
    from diamond.daily.learn import list_topics as do_list_topics

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    if list_topics:
        topics = do_list_topics()
        console.print("\n  [bold]Available Topics:[/bold]\n")
        for i, t in enumerate(topics):
            console.print(f"  {i}. {t}")
        console.print("\n  Use `diamond learn --topic N` to pick one.\n")
        return

    console.print("\n  [dim]Preparing today's lesson...[/dim]")

    lesson = get_daily_lesson(strategy=strategy, topic_index=topic)

    # Topic header
    console.print(
        Panel(
            f"  [bold]{lesson.topic}[/bold]\n\n  [italic]{lesson.concept}[/italic]",
            title=f"[bold]TODAY'S LESSON[/bold]  [{lesson.category}]",
            border_style="bright_cyan",
            padding=(0, 1),
        )
    )

    # Explanation
    console.print(
        Panel(
            f"  {lesson.explanation}",
            title="[bold]HOW IT WORKS[/bold]",
            border_style="blue",
            padding=(0, 1),
        )
    )

    # Examples from YOUR portfolio
    if lesson.examples:
        table = Table(title="In Your Portfolio", box=box.SIMPLE_HEAVY, pad_edge=False)
        table.add_column("Stock", min_width=14)
        table.add_column("Value", min_width=16)
        table.add_column("What It Means", min_width=40)

        for ex in lesson.examples:
            table.add_row(ex.ticker, ex.value, ex.interpretation)
        console.print(table)
    else:
        console.print("  [dim]No portfolio examples available — deploy some capital first.[/dim]")

    # Takeaway
    if lesson.takeaway:
        console.print(
            Panel(
                f"  {lesson.takeaway}",
                title="[bold]TAKEAWAY[/bold]",
                border_style="green",
                padding=(0, 1),
            )
        )

    console.print()


# --- Streak Command ---


@app.command()
def streak(
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="Portfolio for milestones")] = "accumulate",
):
    """Track your daily check-in streak and portfolio milestones."""
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.daily.streak import get_streak_report

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    report = get_streak_report(strategy=strategy)
    s = report.streak

    # Streak panel
    console.print(
        Panel(
            f"  {s.checkin_message}\n\n"
            f"  Current Streak:  [bold]{s.current_streak}[/bold] days\n"
            f"  Longest Streak:  {s.longest_streak} days\n"
            f"  Total Check-ins: {s.total_checkins}",
            title="[bold]STREAK[/bold]",
            border_style="bright_cyan",
            padding=(0, 1),
        )
    )

    # Milestones
    if report.milestones:
        table = Table(title="Milestones", box=box.SIMPLE, pad_edge=False)
        table.add_column("", min_width=3)
        table.add_column("Milestone", min_width=20)
        table.add_column("Value", justify="right", min_width=12)
        table.add_column("Date", min_width=12)

        for m in report.milestones:
            icon = "[green]v[/green]" if m.achieved else "[dim]o[/dim]"
            val = m.value if m.achieved else "—"
            date = m.date_achieved if m.achieved else ""
            name_style = "" if m.achieved else "[dim]"
            name_end = "" if m.achieved else "[/dim]"
            table.add_row(icon, f"{name_style}{m.label}{name_end}", val, date)
        console.print(table)

    # Fun fact
    if report.fun_fact:
        console.print(
            Panel(
                f"  {report.fun_fact}",
                title="[bold]DID YOU KNOW?[/bold]",
                border_style="bright_magenta",
                padding=(0, 1),
            )
        )

    console.print()


# --- Scenario Command ---


@app.command()
def scenario(
    crash: Annotated[
        Optional[float],
        typer.Option("--crash", help="Simulate market crash/rally (e.g., -10 for 10%% drop)"),
    ] = None,
    add_cash: Annotated[Optional[float], typer.Option("--add", help="Simulate adding cash (INR)")] = None,
    compare: Annotated[
        Optional[str],
        typer.Option("--compare", help="Compare held stock vs alternative (HELD:ALT)"),
    ] = None,
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="Portfolio to simulate on")] = "accumulate",
    lookback: Annotated[int, typer.Option("--lookback", help="Lookback days for comparison")] = 90,
):
    """What-if scenarios — stress test, add cash, or compare alternatives.

    Examples:
        diamond scenario --crash -10              # What if Nifty drops 10%?
        diamond scenario --crash 5                # What if Nifty rallies 5%?
        diamond scenario --add 50000              # What if I add 50K?
        diamond scenario --compare RELIANCE:TCS   # What if I'd bought TCS instead?
    """
    import logging as _logging

    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from diamond.daily.whatif import simulate_add_cash, simulate_alternative, simulate_market_crash

    for name in ["yfinance", "urllib3", "peewee"]:
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    console = Console()

    if crash is not None:
        console.print(f"\n  [dim]Simulating Nifty {crash:+.1f}%...[/dim]")

        result = simulate_market_crash(strategy, crash)

        # Summary
        change_color = "green" if result.change_inr >= 0 else "red"
        console.print(
            Panel(
                f"  Scenario:   Nifty {crash:+.1f}%\n"
                f"  Current:    {result.current_nav:,.0f} INR\n"
                f"  Projected:  [{change_color}]{result.projected_nav:,.0f} INR ({result.change_pct:+.1f}%)[/{change_color}]\n"
                f"  Impact:     [{change_color}]{result.change_inr:+,.0f} INR[/{change_color}]",
                title="[bold]STRESS TEST[/bold]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

        # Per-stock impact
        if result.stock_impacts:
            table = Table(title="Stock-Level Impact", box=box.SIMPLE, pad_edge=False)
            table.add_column("Stock", min_width=14)
            table.add_column("Beta", justify="right", min_width=6)
            table.add_column("Current", justify="right", min_width=10)
            table.add_column("Projected", justify="right", min_width=10)
            table.add_column("Impact", justify="right", min_width=10)

            for si in result.stock_impacts[:15]:
                beta = abs(si.change_pct / crash) if crash != 0 else 1.0
                color = "green" if si.change_inr >= 0 else "red"
                table.add_row(
                    si.ticker.replace(".NS", ""),
                    f"{beta:.2f}",
                    f"{si.current_value:,.0f}",
                    f"{si.projected_value:,.0f}",
                    f"[{color}]{si.change_inr:+,.0f}[/{color}]",
                )
            console.print(table)

        console.print(Panel(f"  {result.commentary}", border_style="dim", padding=(0, 1)))
        console.print()
        return

    if add_cash is not None:
        console.print(f"\n  [dim]Simulating adding {add_cash:,.0f} INR...[/dim]")

        result = simulate_add_cash(strategy, add_cash)

        console.print(
            Panel(
                f"  Adding:          {result.amount:,.0f} INR\n"
                f"  Current NAV:     {result.current_nav:,.0f} INR\n"
                f"  Projected NAV:   {result.projected_nav:,.0f} INR\n"
                f"  Positions After: {result.new_positions_after}",
                title="[bold]ADD CASH SIMULATION[/bold]",
                border_style="green",
                padding=(0, 1),
            )
        )

        if result.would_buy:
            table = Table(title="Would Buy", box=box.SIMPLE_HEAVY, pad_edge=False)
            table.add_column("Stock", min_width=14)
            table.add_column("Amount", justify="right", min_width=10)
            table.add_column("Quality", justify="right", min_width=7)
            table.add_column("Reason", min_width=30)

            for buy in result.would_buy:
                table.add_row(
                    buy["ticker"],
                    f"{buy['amount']:,.0f}",
                    f"{buy['quality']:.0f}",
                    buy["reason"][:40],
                )
            console.print(table)
        else:
            console.print("  No buy opportunities at current quality thresholds.")
        console.print()
        return

    if compare is not None:
        parts = compare.split(":")
        if len(parts) != 2:
            typer.echo("Use format: --compare HELD:ALT (e.g., RELIANCE:TCS)")
            raise typer.Exit(1)

        held, alt = parts[0].strip(), parts[1].strip()
        console.print(f"\n  [dim]Comparing {held} vs {alt} over {lookback} days...[/dim]")

        result = simulate_alternative(strategy, held, alt, lookback)

        held_color = "green" if result.held_return_pct >= 0 else "red"
        alt_color = "green" if result.alt_return_pct >= 0 else "red"
        diff_color = "green" if result.difference_inr >= 0 else "red"

        console.print(
            Panel(
                f"  You Hold:    {result.held_ticker}  [{held_color}]{result.held_return_pct:+.1f}%[/{held_color}]  ({result.held_value:,.0f} INR)\n"
                f"  Alternative: {result.alt_ticker}  [{alt_color}]{result.alt_return_pct:+.1f}%[/{alt_color}]  ({result.alt_value:,.0f} INR)\n"
                f"  Difference:  [{diff_color}]{result.difference_inr:+,.0f} INR ({result.difference_pct:+.1f}%)[/{diff_color}]\n"
                f"  Verdict:     {result.verdict}",
                title=f"[bold]{result.held_ticker} vs {result.alt_ticker}[/bold]  ({lookback}d lookback)",
                border_style="cyan",
                padding=(0, 1),
            )
        )
        console.print()
        return

    typer.echo("Specify a scenario: --crash, --add, or --compare")
    typer.echo("Run 'diamond scenario --help' for examples.")


if __name__ == "__main__":
    app()
