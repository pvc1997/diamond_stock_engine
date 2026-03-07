"""Portfolio executor - converts target allocation to trades and executes them.

Handles: risk gate checks, corporate action sync, drift checking,
sell-before-buy ordering, share rounding, minimum trade filtering,
turnover tracking, transaction costs, smart rebalancing, and order tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from diamond.config import get_config
from diamond.data import market
from diamond.data.ledger import Ledger, Trade
from diamond.execution.costs import calculate_costs
from diamond.monitoring.metrics import log_rebalance, log_trade

logger = logging.getLogger(__name__)


def _log_force_override(strategy: str, signals: list[str]) -> None:
    """Append a --force override entry to the audit log. Fail-open."""
    try:
        cfg = get_config()
        log_path = cfg.data_dir / "force_audit.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat()
        with open(log_path, "a") as f:
            for signal in signals:
                f.write(f"{timestamp} | strategy={strategy} | overridden={signal}\n")
        logger.info(f"Force override logged to {log_path}")
    except Exception as e:
        logger.warning(f"Failed to write force audit log: {e}")


def _record_to_order_book(
    strategy: str,
    trades: list[dict],
    status: str = "FILLED",
) -> None:
    """Record executed trades to order book for lifecycle tracking. Fail-open."""
    try:
        from diamond.execution.orders import Order, OrderBook, generate_order_id

        book = OrderBook(strategy)
        for t in trades:
            order = Order(
                id=generate_order_id(strategy, t["ticker"]),
                strategy=strategy,
                ticker=t["ticker"],
                action=t["action"],
                shares=t["shares"],
                filled_shares=t["shares"],
                price=t["price"],
                filled_price=t["price"],
                order_type="MARKET",
                status=status,
                rationale=t.get("rationale", ""),
            )
            book.create_order(order)
    except Exception as e:
        logger.warning(f"Order book recording failed (proceeding): {e}")


def _check_risk_gate(strategy: str, current_prices: dict[str, float]) -> list[str]:
    """Run risk checks and return critical signals that should block execution.

    Returns empty list if safe to proceed.
    """
    try:
        from diamond.monitoring.risk import compute_risk_report

        report = compute_risk_report(strategy, current_prices)
        return [s for s in report.signals if s.startswith("CRITICAL")]
    except Exception as e:
        logger.warning(f"Risk gate check failed (proceeding): {e}")
        return []


def _sync_corporate_actions(strategy: str) -> int:
    """Apply any pending corporate actions before trade calculation.

    Returns number of actions applied.
    """
    try:
        from diamond.data.corporate_actions import process_actions

        applied = process_actions(strategy)
        return len(applied)
    except Exception as e:
        logger.warning(f"Corporate action sync failed (proceeding): {e}")
        return 0


def _get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for a list of tickers."""
    prices = {}
    for ticker in tickers:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception as e:
            logger.warning(f"Price fetch failed for {ticker}: {e}")
    return prices


def _calculate_trades(
    ledger: Ledger,
    target_allocation: dict[str, float],
    current_prices: dict[str, float],
    min_trade_value: float,
) -> list[dict]:
    """Calculate trades needed to reach target allocation.

    Returns list of {ticker, action, shares, price} dicts.
    Sells come before buys.
    """
    holdings = ledger.get_holdings()
    trades = []

    # All tickers involved (current + target)
    all_tickers = set(list(holdings.keys()) + list(target_allocation.keys()))

    for ticker in all_tickers:
        price = current_prices.get(ticker)
        if not price or price <= 0:
            continue

        current_shares = holdings.get(ticker, 0)
        target_amount = target_allocation.get(ticker, 0)
        target_shares = int(target_amount / price)  # Round down

        delta = target_shares - current_shares

        if delta == 0:
            continue

        trade_value = abs(delta * price)
        if trade_value < min_trade_value:
            continue

        action = "BUY" if delta > 0 else "SELL"
        trades.append(
            {
                "ticker": ticker,
                "action": action,
                "shares": abs(delta),
                "price": price,
            }
        )

    # Sort: sells first (free up cash), then buys
    trades.sort(key=lambda t: (0 if t["action"] == "SELL" else 1, t["ticker"]))
    return trades


def execute_sell(
    strategy: str,
    ticker: str,
    shares: int | None = None,
    reason: str = "Manual sell",
    dry_run: bool = False,
    paper: bool = False,
) -> dict:
    """Sell a specific stock from a strategy portfolio.

    Args:
        strategy: Strategy name.
        ticker: Stock ticker to sell.
        shares: Number of shares to sell. None = sell all.
        reason: Rationale for the trade.
        dry_run: Preview without executing.
        paper: Use paper ledger.

    Returns:
        Execution summary dict.
    """
    if paper:
        from diamond.execution.paper import _paper_strategy_name

        strategy = _paper_strategy_name(strategy)

    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    if ticker not in holdings:
        return {"status": "error", "reason": f"{ticker} not in holdings"}

    held_shares = holdings[ticker]
    sell_shares = shares if shares and shares < held_shares else held_shares

    # Fetch current price
    prices = _get_current_prices([ticker])
    price = prices.get(ticker, 0)
    if price <= 0:
        return {"status": "error", "reason": f"Cannot fetch price for {ticker}"}

    value = sell_shares * price
    costs = calculate_costs("SELL", value)

    if dry_run:
        logger.info(f"DRY RUN: SELL {sell_shares} {ticker} @ {price:.2f} = {value:.2f} (cost: {costs.total:.2f})")
        return {
            "status": "dry_run",
            "ticker": ticker,
            "action": "SELL",
            "shares": sell_shares,
            "price": round(price, 2),
            "value": round(value, 2),
            "est_cost": round(costs.total, 2),
            "proceeds": round(value - costs.total, 2),
        }

    ledger.backup()
    trade = Trade(
        timestamp=datetime.now().strftime("%Y-%m-%d"),
        action="SELL",
        ticker=ticker,
        shares=sell_shares,
        price=price,
        total_cost=costs.total,
        rationale=reason,
    )
    ledger.record_trade(trade)
    _record_to_order_book(strategy, [{"ticker": ticker, "action": "SELL", "shares": sell_shares, "price": price}])

    logger.info(f"SELL {sell_shares} {ticker} @ {price:.2f} (cost: {costs.total:.2f})")
    log_trade(strategy, "SELL", ticker, sell_shares, price, costs.total, reason)
    return {
        "status": "executed",
        "ticker": ticker,
        "action": "SELL",
        "shares": sell_shares,
        "price": round(price, 2),
        "value": round(value, 2),
        "cost": round(costs.total, 2),
        "proceeds": round(value - costs.total, 2),
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }


def execute_buy(
    strategy: str,
    ticker: str,
    amount: float | None = None,
    shares: int | None = None,
    reason: str = "Manual buy",
    dry_run: bool = False,
    paper: bool = False,
) -> dict:
    """Buy a specific stock into a strategy portfolio.

    Args:
        strategy: Strategy name.
        ticker: Stock ticker to buy.
        amount: INR amount to invest (calculates shares). Mutually exclusive with shares.
        shares: Exact number of shares to buy.
        reason: Rationale for the trade.
        dry_run: Preview without executing.
        paper: Use paper ledger.

    Returns:
        Execution summary dict.
    """
    if paper:
        from diamond.execution.paper import _paper_strategy_name

        strategy = _paper_strategy_name(strategy)

    ledger = Ledger(strategy)
    cfg = get_config()

    # Fetch current price
    prices = _get_current_prices([ticker])
    price = prices.get(ticker, 0)
    if price <= 0:
        return {"status": "error", "reason": f"Cannot fetch price for {ticker}"}

    cash = ledger.get_cash()

    if shares:
        buy_shares = shares
    elif amount:
        buy_shares = int(amount / price)
    else:
        return {"status": "error", "reason": "Specify --amount or --shares"}

    if buy_shares <= 0:
        return {
            "status": "error",
            "reason": "Calculated 0 shares (price too high or amount too low)",
        }

    value = buy_shares * price
    costs = calculate_costs("BUY", value)
    required = value + costs.total

    if required > cash:
        # Try reducing shares to fit
        buy_shares = int((cash - costs.total) / price)
        if buy_shares <= 0:
            return {
                "status": "error",
                "reason": f"Insufficient cash: need {required:.0f}, have {cash:.0f}",
            }
        value = buy_shares * price
        costs = calculate_costs("BUY", value)
        required = value + costs.total

    # Check position limit
    nav = ledger.get_portfolio_value(prices)
    if nav > 0:
        max_weight = cfg.portfolio.max_position_weight
        existing = ledger.get_holdings().get(ticker, 0) * price
        total_weight = (existing + value) / nav
        if total_weight > max_weight * 1.5:
            return {
                "status": "error",
                "reason": f"Would put {ticker} at {total_weight:.1%} weight (limit: {max_weight:.0%})",
            }

    if dry_run:
        logger.info(f"DRY RUN: BUY {buy_shares} {ticker} @ {price:.2f} = {value:.2f} (cost: {costs.total:.2f})")
        return {
            "status": "dry_run",
            "ticker": ticker,
            "action": "BUY",
            "shares": buy_shares,
            "price": round(price, 2),
            "value": round(value, 2),
            "est_cost": round(costs.total, 2),
            "total_required": round(required, 2),
            "cash_available": round(cash, 2),
        }

    ledger.backup()
    trade = Trade(
        timestamp=datetime.now().strftime("%Y-%m-%d"),
        action="BUY",
        ticker=ticker,
        shares=buy_shares,
        price=price,
        total_cost=costs.total,
        rationale=reason,
    )
    ledger.record_trade(trade)
    _record_to_order_book(strategy, [{"ticker": ticker, "action": "BUY", "shares": buy_shares, "price": price}])

    logger.info(f"BUY {buy_shares} {ticker} @ {price:.2f} (cost: {costs.total:.2f})")
    log_trade(strategy, "BUY", ticker, buy_shares, price, costs.total, reason)
    return {
        "status": "executed",
        "ticker": ticker,
        "action": "BUY",
        "shares": buy_shares,
        "price": round(price, 2),
        "value": round(value, 2),
        "cost": round(costs.total, 2),
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }


def execute_cleanup(
    strategy: str,
    dry_run: bool = False,
    paper: bool = False,
) -> dict:
    """Detect and write off delisted stocks from a portfolio.

    Returns:
        Dict with list of written-off tickers.
    """
    if paper:
        from diamond.execution.paper import _paper_strategy_name

        strategy = _paper_strategy_name(strategy)

    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()
    if not holdings:
        return {"status": "no_holdings", "written_off": []}

    prices = _get_current_prices(list(holdings.keys()))

    written_off = []
    cleanup_backed_up = False
    for ticker, shares in holdings.items():
        if ticker not in prices or prices.get(ticker, 0) <= 0:
            if dry_run:
                logger.info(f"DRY RUN: Would write off {shares} shares of {ticker} (no price data)")
                written_off.append({"ticker": ticker, "shares": shares, "status": "would_write_off"})
            else:
                if not cleanup_backed_up:
                    ledger.backup()
                    cleanup_backed_up = True
                success = ledger.write_off(ticker, "Delisted / no price data")
                if success:
                    logger.info(f"Written off {shares} shares of {ticker}")
                    written_off.append({"ticker": ticker, "shares": shares, "status": "written_off"})

    return {
        "status": "dry_run" if dry_run else "executed",
        "written_off": written_off,
        "count": len(written_off),
    }


def execute_trim(
    strategy: str,
    current_prices: dict[str, float] | None = None,
    dry_run: bool = False,
    paper: bool = False,
) -> dict:
    """Trim positions that exceed concentration limits.

    Returns:
        Dict with list of trim trades.
    """
    if paper:
        from diamond.execution.paper import _paper_strategy_name

        strategy = _paper_strategy_name(strategy)

    cfg = get_config()
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()
    if not holdings:
        return {"status": "no_holdings", "trims": []}

    if current_prices is None:
        current_prices = _get_current_prices(list(holdings.keys()))

    nav = ledger.get_portfolio_value(current_prices)
    if nav <= 0:
        return {"status": "error", "reason": "NAV is zero"}

    max_weight = cfg.portfolio.max_position_weight
    trims = []
    backed_up = False

    for ticker, shares in holdings.items():
        price = current_prices.get(ticker, 0)
        if price <= 0:
            continue
        weight = (shares * price) / nav
        if weight > max_weight:
            target_value = nav * max_weight
            target_shares = int(target_value / price)
            sell_shares = shares - target_shares
            if sell_shares <= 0:
                continue
            value = sell_shares * price
            costs = calculate_costs("SELL", value)

            trim = {
                "ticker": ticker,
                "current_weight": round(weight * 100, 2),
                "target_weight": round(max_weight * 100, 2),
                "sell_shares": sell_shares,
                "price": round(price, 2),
                "value": round(value, 2),
                "est_cost": round(costs.total, 2),
            }

            if not dry_run:
                if not backed_up:
                    ledger.backup()
                    backed_up = True
                trade = Trade(
                    timestamp=datetime.now().strftime("%Y-%m-%d"),
                    action="SELL",
                    ticker=ticker,
                    shares=sell_shares,
                    price=price,
                    total_cost=costs.total,
                    rationale=f"Auto-trim: {weight:.1%} -> {max_weight:.0%}",
                )
                ledger.record_trade(trade)
                _record_to_order_book(
                    strategy,
                    [{"ticker": ticker, "action": "SELL", "shares": sell_shares, "price": price}],
                )
                trim["status"] = "executed"
            else:
                trim["status"] = "dry_run"

            trims.append(trim)

    return {
        "status": "dry_run" if dry_run else "executed",
        "trims": trims,
        "count": len(trims),
        "cash": round(ledger.get_cash(), 2),
    }


def execute(
    strategy: str,
    target_allocation: dict[str, float],
    capital: float,
    force: bool = False,
    dry_run: bool = False,
    screener_df: pd.DataFrame | None = None,
    smart: bool = False,
) -> dict:
    """Execute trades to reach target allocation.

    Args:
        strategy: Strategy name (used for ledger file).
        target_allocation: {ticker: amount_inr} from strategy.allocate().
        capital: Initial capital (used if ledger doesn't exist).
        force: Bypass rebalance frequency check.
        dry_run: Show trades without executing.
        smart: Use smart rebalancing (drift + tax-aware ordering).

    Returns:
        Dict with execution summary.
    """
    cfg = get_config()
    ledger = Ledger(strategy)

    # Check if first run - set initial capital
    if (
        not ledger.get_holdings()
        and ledger.get_cash() == cfg.risk.initial_capital
        and capital != cfg.risk.initial_capital
    ):
        ledger.reset(initial_capital=capital)

    today = datetime.now().strftime("%Y-%m-%d")

    # Get current prices for all relevant tickers
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
            logger.info(f"Smart rebalance skipped: {drift_report.reason}")
            return {
                "status": "skipped",
                "reason": drift_report.reason,
                "max_drift": round(drift_report.max_drift, 4),
                "trades": 0,
            }
        logger.info(f"Smart rebalance triggered: {drift_report.reason}")
    elif not force:
        # Legacy time-based check
        last_rebalance = ledger.get_last_rebalance()
        if last_rebalance:
            from datetime import datetime as dt

            last_dt = dt.strptime(last_rebalance, "%Y-%m-%d")
            days_since = (dt.strptime(today, "%Y-%m-%d") - last_dt).days
            if days_since < cfg.rebalance.rebalance_frequency_days:
                logger.info(
                    f"Skipping rebalance: {days_since}d since last "
                    f"(next due in {cfg.rebalance.rebalance_frequency_days - days_since}d)"
                )
                return {
                    "status": "skipped",
                    "reason": f"Next rebalance in {cfg.rebalance.rebalance_frequency_days - days_since} days",
                    "trades": 0,
                }

    # Pre-execution: backup ledger before any mutations
    if not dry_run and ledger.get_holdings():
        ledger.backup()

    # Pre-execution: sync corporate actions (splits, dividends)
    if ledger.get_holdings():
        actions_applied = _sync_corporate_actions(strategy)
        if actions_applied:
            logger.info(f"Applied {actions_applied} corporate action(s) before rebalance")

    # Pre-execution: risk gate — block on critical signals
    if not dry_run and ledger.get_holdings():
        critical_signals = _check_risk_gate(strategy, current_prices)
        if critical_signals:
            if force:
                logger.warning("Risk gate overridden with --force:")
                for sig in critical_signals:
                    logger.warning(f"  {sig}")
                _log_force_override(strategy, critical_signals)
            else:
                logger.warning("Risk gate BLOCKED execution:")
                for sig in critical_signals:
                    logger.warning(f"  {sig}")
                return {
                    "status": "blocked",
                    "reason": "Risk gate triggered",
                    "signals": critical_signals,
                    "trades": 0,
                }

    # Calculate trades — smart or legacy
    if smart and ledger.get_holdings():
        from diamond.execution.smart_rebalance import plan_tax_aware_trades

        smart_trades = plan_tax_aware_trades(ledger, target_allocation, current_prices, cfg.rebalance.min_trade_value)
        # Convert SmartTrade to dict format for compatibility
        trades = [
            {
                "ticker": st.ticker,
                "action": st.action,
                "shares": st.shares,
                "price": st.price,
                "tax_category": st.tax_category,
                "tax_reason": st.reason,
                "priority": st.priority,
            }
            for st in smart_trades
        ]
    else:
        trades = _calculate_trades(ledger, target_allocation, current_prices, cfg.rebalance.min_trade_value)

    if not trades:
        logger.info("No trades needed - portfolio within drift threshold")
        return {"status": "no_trades", "trades": 0}

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

    # Dry run: just show what would happen
    if dry_run:
        logger.info(f"DRY RUN: {len(trades)} trades planned")
        for t in trades:
            value = t["shares"] * t["price"]
            tax_info = ""
            if t.get("tax_reason"):
                tax_info = f" [{t['tax_category']}: {t['tax_reason']}]"
            logger.info(f"  {t['action']} {t['shares']} {t['ticker']} @ {t['price']:.2f} = {value:.2f}{tax_info}")
            if t["ticker"] in rationales:
                from diamond.analysis.rationale import format_rationale_verbose

                logger.info(format_rationale_verbose(rationales[t["ticker"]]))
        _record_to_order_book(strategy, trades, status="PENDING")
        return {
            "status": "dry_run",
            "trades": len(trades),
            "trade_list": trades,
            "rationales": rationales,
        }

    # Execute trades
    executed = 0
    total_fees = 0.0

    for t in trades:
        value = t["shares"] * t["price"]
        costs = calculate_costs(t["action"], value)

        # Check sufficient cash for buys
        if t["action"] == "BUY":
            required = value + costs.total
            available = ledger.get_cash()
            if required > available:
                # Reduce shares to fit budget
                affordable = int((available - costs.total) / t["price"])
                if affordable <= 0:
                    logger.warning(f"Insufficient cash for {t['ticker']}: need {required:.0f}, have {available:.0f}")
                    continue
                t["shares"] = affordable
                value = t["shares"] * t["price"]
                costs = calculate_costs(t["action"], value)

        # Build rationale string
        rationale_str = "Rebalance"
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

        logger.info(f"  {t['action']} {t['shares']} {t['ticker']} @ {t['price']:.2f} (cost: {costs.total:.2f})")

    # Update rebalance date
    ledger.set_last_rebalance(today)

    # Record to order book
    _record_to_order_book(strategy, trades, status="FILLED")

    # Summary
    nav = ledger.get_portfolio_value(current_prices)
    summary = {
        "status": "executed",
        "trades": executed,
        "total_fees": round(total_fees, 2),
        "nav": round(nav, 2),
        "cash": round(ledger.get_cash(), 2),
        "holdings": len(ledger.get_holdings()),
    }

    logger.info(
        f"Execution complete: {executed} trades, fees={total_fees:.2f}, NAV={nav:,.2f}, cash={ledger.get_cash():,.2f}"
    )

    log_rebalance(
        strategy=strategy,
        trades=executed,
        total_fees=total_fees,
        nav=nav,
        cash=ledger.get_cash(),
        holdings=len(ledger.get_holdings()),
        smart=smart,
    )

    return summary
