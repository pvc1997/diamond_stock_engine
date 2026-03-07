"""Live execution engine with Kite Connect integration.

Handles the full live trading flow:
1. Fetch real holdings from Kite
2. Compute target allocation from strategy
3. Calculate trade deltas
4. Show trade plan with cost estimates
5. Get user confirmation (sells and buys separately)
6. Execute via Kite API
7. Track order status and record to ledger
"""

import logging
import time
from datetime import datetime
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from diamond.config import get_config
from diamond.data.ledger import Ledger, Trade
from diamond.exceptions import AuthenticationError
from diamond.execution.costs import calculate_costs
from diamond.execution.executor import _record_to_order_book
from diamond.execution.kite import KiteClient, yf_to_kite

logger = logging.getLogger(__name__)
console = Console()


def _fetch_live_prices(tickers: list[str], kite_client: KiteClient) -> dict[str, float]:
    """Fetch current prices — prefer Kite, fallback to yfinance."""
    from diamond.data import market

    prices: dict[str, float] = {}
    for ticker in tickers:
        # Try Kite quote first
        kite_sym = yf_to_kite(ticker)
        quote = kite_client.get_quote(kite_sym)
        if quote and quote.get("last_price"):
            prices[ticker] = float(quote["last_price"])
        else:
            # Fallback to yfinance
            try:
                series = market.download_single(ticker, period_days=5)
                if len(series) > 0:
                    prices[ticker] = float(series.iloc[-1])
            except Exception:
                pass
    return prices


def _compute_trade_plan(
    ledger: Ledger,
    target_allocation: dict[str, float],
    current_prices: dict[str, float],
    min_trade_value: float,
) -> tuple[list[dict], list[dict]]:
    """Compute sells and buys needed to reach target allocation.

    Returns:
        (sells, buys) — each a list of {ticker, shares, price, value, est_cost}
    """
    holdings = ledger.get_holdings()
    all_tickers = set(list(holdings.keys()) + list(target_allocation.keys()))

    sells = []
    buys = []

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

        costs = calculate_costs("SELL" if delta < 0 else "BUY", trade_value)

        trade = {
            "ticker": ticker,
            "kite_symbol": yf_to_kite(ticker),
            "shares": abs(delta),
            "price": price,
            "value": trade_value,
            "est_cost": costs.total,
        }

        if delta < 0:
            sells.append(trade)
        else:
            buys.append(trade)

    # Sort sells by value desc (free cash first), buys by value desc (biggest first)
    sells.sort(key=lambda t: -t["value"])
    buys.sort(key=lambda t: -t["value"])

    return sells, buys


def _display_trade_table(trades: list[dict], action: str, total_label: str) -> None:
    """Display a rich table of planned trades."""
    color = "red" if action == "SELL" else "green"

    table = Table(
        title=f"[bold {color}]{action} Orders[/bold {color}]",
        box=box.ROUNDED,
        show_footer=True,
    )
    table.add_column("Stock", min_width=14)
    table.add_column("Kite Symbol", min_width=14)
    table.add_column("Qty", justify="right", min_width=6)
    table.add_column("Price", justify="right", min_width=10)
    table.add_column("Value", justify="right", min_width=12, footer_style="bold")
    table.add_column("Est. Fees", justify="right", min_width=10, footer_style="bold")

    total_value = 0.0
    total_fees = 0.0

    for t in trades:
        total_value += t["value"]
        total_fees += t["est_cost"]
        table.add_row(
            t["ticker"].replace(".NS", ""),
            t["kite_symbol"],
            str(t["shares"]),
            f"{t['price']:,.2f}",
            f"[{color}]{t['value']:,.0f}[/{color}]",
            f"{t['est_cost']:,.0f}",
        )

    # Footer
    table.columns[4].footer = f"[bold]{total_value:,.0f}[/bold]"
    table.columns[5].footer = f"[bold]{total_fees:,.0f}[/bold]"

    console.print(table)
    console.print(
        f"  {total_label}: [bold]{total_value:,.0f} INR[/bold]"
        f"  |  Est. fees: [bold]{total_fees:,.0f} INR[/bold]"
        f"  |  {len(trades)} orders"
    )
    console.print()


def _confirm(prompt: str) -> bool:
    """Ask user for Y/N confirmation."""
    try:
        response = input(f"  {prompt} [y/N]: ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _execute_orders(
    kite_client: KiteClient,
    trades: list[dict],
    action: str,
    ledger: Ledger,
    dry_run: bool = False,
) -> list[dict]:
    """Execute a batch of orders via Kite and record to ledger.

    Returns list of execution results.
    """
    results = []
    today = datetime.now().strftime("%Y-%m-%d")

    for t in trades:
        symbol = t["kite_symbol"]
        shares = t["shares"]

        if dry_run:
            console.print(f"  [dim][DRY RUN][/dim] {action} {shares} {symbol}")
            results.append(
                {
                    **t,
                    "status": "dry_run",
                    "order_id": None,
                }
            )
            continue

        try:
            order_id = kite_client.place_order(
                ticker=symbol,
                action=action,
                quantity=shares,
                order_type="MARKET",
            )

            # Record to ledger at current price (will reconcile actual fill later)
            costs = calculate_costs(action, t["value"])
            trade = Trade(
                timestamp=today,
                action=action,
                ticker=t["ticker"],
                shares=shares,
                price=t["price"],
                total_cost=costs.total,
                rationale=f"Live rebalance (order: {order_id})",
            )
            ledger.record_trade(trade)

            status = "placed"
            console.print(f"  [green]OK[/green] {action} {shares} {symbol}  (order: {order_id})")

            results.append(
                {
                    **t,
                    "status": status,
                    "order_id": order_id,
                }
            )

        except RuntimeError as e:
            error_msg = str(e).lower()
            # Session/auth error — abort entire batch
            if "session expired" in error_msg or "not authenticated" in error_msg:
                console.print(
                    "\n  [bold red]Session expired during execution.[/bold red]"
                    "\n  Aborting remaining orders to prevent partial state."
                    "\n  Run: [cyan]diamond kite --auth[/cyan] to re-authenticate."
                )
                results.append(
                    {
                        **t,
                        "status": "blocked",
                        "order_id": None,
                        "error": str(e),
                    }
                )
                # Mark all remaining trades as aborted
                remaining_idx = trades.index(t) + 1
                for remaining in trades[remaining_idx:]:
                    results.append(
                        {
                            **remaining,
                            "status": "aborted",
                            "order_id": None,
                            "error": "Batch aborted: session expired",
                        }
                    )
                break

            # CDSL/auth error — stop all sells
            console.print(f"  [bold red]BLOCKED[/bold red] {symbol}: {e}")
            results.append(
                {
                    **t,
                    "status": "blocked",
                    "order_id": None,
                    "error": str(e),
                }
            )
            if action == "SELL":
                console.print(
                    "\n  [bold red]Sell authorization required.[/bold red]"
                    "\n  Run: [cyan]diamond kite --authorize-sells[/cyan]"
                )
                break

        except Exception as e:
            error_msg = str(e).lower()
            # Catch session/token errors from the Kite SDK itself
            if "token" in error_msg or "session" in error_msg or "auth" in error_msg:
                console.print(
                    f"\n  [bold red]Kite session/auth error: {e}[/bold red]"
                    f"\n  Aborting remaining orders."
                    f"\n  Run: [cyan]diamond kite --auth[/cyan] to re-authenticate."
                )
                results.append(
                    {
                        **t,
                        "status": "blocked",
                        "order_id": None,
                        "error": str(e),
                    }
                )
                remaining_idx = trades.index(t) + 1
                for remaining in trades[remaining_idx:]:
                    results.append(
                        {
                            **remaining,
                            "status": "aborted",
                            "order_id": None,
                            "error": "Batch aborted: auth error",
                        }
                    )
                break

            console.print(f"  [red]FAILED[/red] {action} {shares} {symbol}: {e}")
            results.append(
                {
                    **t,
                    "status": "failed",
                    "order_id": None,
                    "error": str(e),
                }
            )

    return results


def _check_order_fills(
    kite_client: KiteClient,
    order_results: list[dict],
    ledger: Ledger,
    max_wait: int = 30,
) -> list[dict]:
    """Poll Kite for order fill status and update ledger with actual prices.

    Args:
        kite_client: Authenticated client.
        order_results: Results from _execute_orders.
        ledger: Ledger to update.
        max_wait: Maximum seconds to wait for fills.

    Returns:
        Updated results with fill information.
    """
    placed_orders = [r for r in order_results if r.get("order_id") and r["status"] == "placed"]
    if not placed_orders:
        return order_results

    console.print(f"\n  Waiting for {len(placed_orders)} order(s) to fill...")

    start = time.time()
    pending = {r["order_id"]: r for r in placed_orders}

    while pending and (time.time() - start) < max_wait:
        for order_id in list(pending.keys()):
            status = kite_client.get_order_status(order_id)
            if not status:
                continue

            kite_status = status.get("status", "").upper()

            if kite_status == "COMPLETE":
                fill_price = status.get("average_price", pending[order_id]["price"])
                fill_qty = status.get("filled_quantity", pending[order_id]["shares"])
                pending[order_id]["fill_price"] = fill_price
                pending[order_id]["fill_qty"] = fill_qty
                pending[order_id]["status"] = "filled"

                console.print(
                    f"  [green]FILLED[/green] {pending[order_id]['kite_symbol']}  {fill_qty} @ {fill_price:,.2f}"
                )
                del pending[order_id]

            elif kite_status in ("CANCELLED", "REJECTED"):
                reason = status.get("status_message", "Unknown")
                pending[order_id]["status"] = kite_status.lower()
                pending[order_id]["error"] = reason
                console.print(f"  [red]{kite_status}[/red] {pending[order_id]['kite_symbol']}: {reason}")
                del pending[order_id]

        if pending:
            time.sleep(2)

    # Flag remaining as pending
    for order_id, result in pending.items():
        result["status"] = "pending"
        console.print(f"  [yellow]PENDING[/yellow] {result['kite_symbol']} (order: {order_id}) — check manually")

    return order_results


def execute_live(
    strategy: str,
    target_allocation: dict[str, float],
    capital: float,
    force: bool = False,
    dry_run: bool = False,
    kite_client: Optional[KiteClient] = None,
    force_after_hours: bool = False,
) -> dict:
    """Full live execution flow with interactive confirmation.

    Args:
        strategy: Strategy name.
        target_allocation: {yf_ticker: amount_inr} from strategy.
        capital: Capital amount.
        force: Bypass rebalance frequency check.
        dry_run: Show everything but don't place real orders.
        kite_client: Optional pre-authenticated client.
        force_after_hours: Allow placing orders when market is closed (AMO).

    Returns:
        Execution summary dict.
    """
    cfg = get_config()

    # Initialize Kite client
    if kite_client is None:
        kite_client = KiteClient()

    if not kite_client.authenticated:
        console.print("[bold red]Not authenticated with Kite.[/bold red]\nRun: [cyan]diamond kite --auth[/cyan]")
        return {"status": "error", "reason": "Not authenticated"}

    # Validate session is still alive (file age + API ping)
    if not kite_client.is_session_valid():
        console.print(
            "[bold red]Kite session expired or invalid.[/bold red]\n"
            "Run: [cyan]diamond kite --auth[/cyan] to re-authenticate."
        )
        return {"status": "error", "reason": "Session expired"}

    # Market hours guard — only for real (non-dry-run) orders
    if not dry_run and not force_after_hours:
        from diamond.data.market import is_market_open, next_market_open

        if not is_market_open():
            next_open = next_market_open()
            console.print(
                "\n  [bold yellow]Market is closed.[/bold yellow]"
                f"\n  NSE trading hours: Mon-Fri 9:15 AM - 3:30 PM IST"
                f"\n  Next open: [bold]{next_open.strftime('%a %d %b %Y, %I:%M %p IST')}[/bold]"
                "\n"
                "\n  Use [cyan]--force-after-hours[/cyan] to place AMO (After Market Orders)."
            )
            return {
                "status": "blocked",
                "reason": "Market closed",
                "next_open": next_open.isoformat(),
            }

    console.print(f"\n  [bold]Live Execution[/bold] — {strategy.upper()}  |  User: {kite_client.user_name}")
    if dry_run:
        console.print("  [yellow][DRY RUN MODE — no real orders will be placed][/yellow]")
    console.print()

    # Load ledger
    ledger = Ledger(strategy)

    # Check rebalance timing
    today = datetime.now().strftime("%Y-%m-%d")
    last_rebalance = ledger.get_last_rebalance()

    if last_rebalance and not force:
        last_dt = datetime.strptime(last_rebalance, "%Y-%m-%d")
        days_since = (datetime.strptime(today, "%Y-%m-%d") - last_dt).days

        if strategy == "gods_plan":
            freq = cfg.gods_plan.rebalance_days
        else:
            freq = cfg.rebalance.rebalance_frequency_days

        if days_since < freq:
            console.print(
                f"  Rebalance not due — {days_since}d since last"
                f" (next in {freq - days_since}d). Use --force to override."
            )
            return {
                "status": "skipped",
                "reason": f"Next rebalance in {freq - days_since} days",
            }

    # Fetch current prices
    all_tickers = list(set(list(ledger.get_holdings().keys()) + list(target_allocation.keys())))
    console.print("  Fetching live prices...", end="\r")
    current_prices = _fetch_live_prices(all_tickers, kite_client)

    missing = [t for t in all_tickers if t not in current_prices]
    if missing:
        console.print(f"  [yellow]Warning: No price for {', '.join(missing)}[/yellow]")

    # Pre-execution: risk gate
    if ledger.get_holdings() and not dry_run:
        try:
            from diamond.monitoring.risk import compute_risk_report

            report = compute_risk_report(strategy, current_prices)
            critical = [s for s in report.signals if s.startswith("CRITICAL")]
            if critical:
                if force:
                    console.print("\n  [bold yellow]RISK GATE OVERRIDDEN (--force):[/bold yellow]")
                    for sig in critical:
                        console.print(f"    {sig}")
                    try:
                        from diamond.execution.executor import _log_force_override

                        _log_force_override(strategy, critical)
                    except Exception:
                        pass
                else:
                    console.print("\n  [bold red]RISK GATE BLOCKED:[/bold red]")
                    for sig in critical:
                        console.print(f"    {sig}")
                    console.print("\n  Use --force to override.")
                    return {"status": "blocked", "signals": critical}
        except Exception as e:
            logger.warning(f"Risk gate check failed (proceeding): {e}")

    # Compute trade plan
    sells, buys = _compute_trade_plan(ledger, target_allocation, current_prices, cfg.rebalance.min_trade_value)

    if not sells and not buys:
        console.print("\n  Portfolio is on target — no trades needed.")
        return {"status": "no_trades"}

    # --- Phase 1: SELLS ---
    sell_results = []
    if sells:
        _display_trade_table(sells, "SELL", "Total to sell")

        if _confirm("Execute SELL orders?"):
            sell_results = _execute_orders(kite_client, sells, "SELL", ledger, dry_run)

            # Check fills for sells
            if not dry_run:
                sell_results = _check_order_fills(kite_client, sell_results, ledger)
        else:
            console.print("  [dim]Sells skipped by user[/dim]")
            sell_results = [{"status": "skipped_by_user", **s} for s in sells]

    # --- Phase 2: BUYS ---
    buy_results = []
    if buys:
        console.print()
        _display_trade_table(buys, "BUY", "Total to buy")

        # Show available cash after sells
        current_cash = ledger.get_cash()
        total_buy_value = sum(b["value"] + b["est_cost"] for b in buys)
        console.print(f"  Available cash: [bold]{current_cash:,.0f} INR[/bold]")
        if total_buy_value > current_cash:
            console.print(
                f"  [yellow]Warning: Buy total ({total_buy_value:,.0f}) exceeds"
                f" cash ({current_cash:,.0f}). Orders will be adjusted.[/yellow]"
            )

        if _confirm("Execute BUY orders?"):
            # Adjust buy quantities if insufficient cash
            available = ledger.get_cash()
            adjusted_buys = []
            for b in buys:
                needed = b["value"] + b["est_cost"]
                if needed <= available:
                    adjusted_buys.append(b)
                    available -= needed
                else:
                    # Reduce quantity to fit
                    affordable_shares = int(
                        (available * 0.98) / b["price"]  # 2% buffer for fees
                    )
                    if affordable_shares > 0:
                        new_value = affordable_shares * b["price"]
                        new_costs = calculate_costs("BUY", new_value)
                        b["shares"] = affordable_shares
                        b["value"] = new_value
                        b["est_cost"] = new_costs.total
                        adjusted_buys.append(b)
                        console.print(
                            f"  [yellow]Reduced {b['kite_symbol']} to {affordable_shares} shares (cash limit)[/yellow]"
                        )
                        available -= new_value + new_costs.total
                    else:
                        console.print(f"  [yellow]Skipping {b['kite_symbol']} — insufficient cash[/yellow]")

            buy_results = _execute_orders(kite_client, adjusted_buys, "BUY", ledger, dry_run)

            # Check fills for buys
            if not dry_run:
                buy_results = _check_order_fills(kite_client, buy_results, ledger)
        else:
            console.print("  [dim]Buys skipped by user[/dim]")
            buy_results = [{"status": "skipped_by_user", **b} for b in buys]

    # Update rebalance date
    any_executed = any(r["status"] in ("placed", "filled", "dry_run") for r in sell_results + buy_results)
    if any_executed:
        ledger.set_last_rebalance(today)

    # Record to order book
    executed_trades = [r for r in sell_results + buy_results if r.get("status") in ("placed", "filled")]
    if executed_trades:
        book_trades = [
            {
                "ticker": r["ticker"],
                "action": "SELL" if r in sell_results else "BUY",
                "shares": r["shares"],
                "price": r["price"],
            }
            for r in executed_trades
        ]
        _record_to_order_book(strategy, book_trades, status="PLACED")

    # --- Summary ---
    all_results = sell_results + buy_results
    executed = [r for r in all_results if r["status"] in ("placed", "filled", "dry_run")]
    failed = [r for r in all_results if r["status"] in ("failed", "blocked")]
    skipped = [r for r in all_results if r["status"] == "skipped_by_user"]

    console.print()
    console.print(
        Panel(
            f"  Executed: [bold]{len(executed)}[/bold]"
            f"  |  Failed: [bold red]{len(failed)}[/bold red]"
            f"  |  Skipped: [bold yellow]{len(skipped)}[/bold yellow]"
            f"  |  Cash: [bold]{ledger.get_cash():,.0f} INR[/bold]",
            title="[bold]Execution Summary[/bold]",
            border_style="cyan",
        )
    )

    if failed:
        console.print("\n  [bold red]Failed orders:[/bold red]")
        for r in failed:
            console.print(f"    {r['kite_symbol']}: {r.get('error', 'Unknown')}")

    return {
        "status": "executed" if executed else "no_action",
        "sells_executed": len([r for r in sell_results if r["status"] in ("placed", "filled", "dry_run")]),
        "buys_executed": len([r for r in buy_results if r["status"] in ("placed", "filled", "dry_run")]),
        "total_executed": len(executed),
        "total_failed": len(failed),
        "total_skipped": len(skipped),
        "cash": round(ledger.get_cash(), 2),
        "results": all_results,
    }


def reconcile_with_kite(
    strategy: str,
    kite_client: Optional[KiteClient] = None,
) -> dict:
    """Compare ledger holdings with actual Kite holdings.

    Returns discrepancy report.
    """
    if kite_client is None:
        kite_client = KiteClient()

    if not kite_client.authenticated:
        raise AuthenticationError()

    ledger = Ledger(strategy)
    ledger_holdings = ledger.get_holdings()
    kite_holdings = kite_client.get_holdings_mapped()

    all_tickers = set(list(ledger_holdings.keys()) + list(kite_holdings.keys()))

    matches = []
    discrepancies = []
    ledger_only = []
    kite_only = []

    for ticker in sorted(all_tickers):
        ledger_qty = ledger_holdings.get(ticker, 0)
        kite_info = kite_holdings.get(ticker, {})
        kite_qty = kite_info.get("shares", 0)

        if ledger_qty == kite_qty:
            if ledger_qty > 0:
                matches.append({"ticker": ticker, "shares": ledger_qty})
        elif ledger_qty > 0 and kite_qty > 0:
            discrepancies.append(
                {
                    "ticker": ticker,
                    "ledger_qty": ledger_qty,
                    "kite_qty": kite_qty,
                    "delta": kite_qty - ledger_qty,
                }
            )
        elif ledger_qty > 0 and kite_qty == 0:
            ledger_only.append({"ticker": ticker, "shares": ledger_qty})
        elif kite_qty > 0 and ledger_qty == 0:
            kite_only.append(
                {
                    "ticker": ticker,
                    "shares": kite_qty,
                    "avg_price": kite_info.get("avg_price", 0),
                }
            )

    return {
        "strategy": strategy,
        "matches": matches,
        "discrepancies": discrepancies,
        "ledger_only": ledger_only,
        "kite_only": kite_only,
        "in_sync": len(discrepancies) == 0 and len(ledger_only) == 0 and len(kite_only) == 0,
    }
