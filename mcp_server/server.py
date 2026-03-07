"""Diamond Stock Engine MCP Server.

Exposes portfolio management, market analysis, and trading tools
as structured MCP tools for Claude Code and other MCP clients.
"""

import dataclasses
import json
import logging
import os
import sys
from typing import Any

# Add diamond source to path
_DIAMOND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _DIAMOND_ROOT not in sys.path:
    sys.path.insert(0, _DIAMOND_ROOT)

# Also ensure .env is loaded from the project root
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(_PROJECT_ROOT)

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Diamond Stock Engine",
    instructions=(
        "You are a daily investing guide for an Indian equity portfolio. "
        "Use these tools to check market conditions, analyze stocks, "
        "manage portfolios, and make trading decisions. "
        "Default strategy is 'gods_plan'. Be conservative — WAIT is the default."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dc_to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses to dicts for JSON serialization."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dc_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dc_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _dc_to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _json(obj: Any) -> str:
    """Serialize to compact JSON."""
    return json.dumps(_dc_to_dict(obj), indent=2, default=str)


def _get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices for a list of tickers."""
    from diamond.data.market import download_prices

    prices: dict[str, float] = {}
    try:
        df = download_prices(tickers, period_days=5, use_cache=True)
        if not df.empty:
            for col in df.columns:
                series = df[col].dropna()
                if len(series) > 0:
                    prices[col] = float(series.iloc[-1])
    except Exception as e:
        logger.warning(f"Price fetch failed: {e}")
    return prices


# ===========================================================================
# MARKET TOOLS
# ===========================================================================


@mcp.tool()
def market_pulse() -> str:
    """Get current market conditions — Nifty level, VIX, breadth, RSI, trend,
    and verdict (DEPLOY/WAIT/DEFENSIVE). Use this first before any trading decision."""
    from diamond.monitoring.market_pulse import get_market_pulse

    pulse = get_market_pulse()
    return _json(pulse)


@mcp.tool()
def market_screener(force: bool = False) -> str:
    """Screen the NSE 500 universe for Alpha, Beta, CAGR, Volatility, and Hurst.
    Returns ranked stocks with quality metrics. Cached for 24h unless force=True."""
    from diamond.analysis.screener import screen

    df = screen(force=force)
    # Return top 30 by Alpha descending
    top = df.nlargest(30, "Alpha") if "Alpha" in df.columns else df.head(30)
    return top.to_json(orient="records", indent=2)


@mcp.tool()
def sector_list() -> str:
    """Get the Nifty 50 ticker list and NSE 500 screening universe."""
    from diamond.data.universe import get_nifty50, get_screening_universe

    return _json({
        "nifty50": get_nifty50(),
        "nifty50_count": len(get_nifty50()),
        "screening_universe_count": len(get_screening_universe()),
    })


@mcp.tool()
def stock_sector(ticker: str) -> str:
    """Get the sector for a given ticker (e.g., RELIANCE.NS)."""
    from diamond.data.universe import get_sector

    return _json({"ticker": ticker, "sector": get_sector(ticker)})


# ===========================================================================
# STOCK ANALYSIS TOOLS
# ===========================================================================


@mcp.tool()
def analyze_stock(ticker: str, use_ai: bool = True) -> str:
    """Deep analysis of a single stock — technicals (RSI, MACD, Bollinger, support/resistance),
    fundamentals (PE, PB, ROE, growth), screener metrics, peer comparison, and AI verdict.
    Append .NS if not present (e.g., RELIANCE.NS)."""
    from diamond.analysis.deep import analyze_deep

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"
    result = analyze_deep(ticker, use_ai=use_ai)
    return _json(result)


@mcp.tool()
def stock_sentiment(ticker: str) -> str:
    """AI-powered sentiment analysis for a stock. Returns score (-10 to +10),
    sentiment label, and rationale. Uses Gemini AI with heuristic fallback."""
    from diamond.analysis.sentiment import analyze_stock

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"
    result = analyze_stock(ticker)
    return _json(result)


@mcp.tool()
def stock_prices(tickers: str, period_days: int = 30) -> str:
    """Fetch historical closing prices for one or more tickers.
    Pass comma-separated tickers (e.g., 'RELIANCE.NS,TCS.NS').
    Returns last N days of prices."""
    from diamond.data.market import download_prices

    ticker_list = [t.strip() for t in tickers.split(",")]
    df = download_prices(ticker_list, period_days=period_days, use_cache=True)
    if df.empty:
        return _json({"error": "No price data found", "tickers": ticker_list})
    # Return last 10 rows as records
    recent = df.tail(10)
    result = {
        "tickers": ticker_list,
        "period_days": period_days,
        "rows": len(df),
        "latest_prices": {col: round(float(df[col].dropna().iloc[-1]), 2) for col in df.columns if not df[col].dropna().empty},
        "recent": json.loads(recent.to_json(orient="index", date_format="iso")),
    }
    return _json(result)


@mcp.tool()
def transaction_costs(action: str, amount: float) -> str:
    """Calculate Indian market transaction costs for a BUY or SELL.
    Returns breakdown: brokerage, GST, STT, exchange fees, SEBI, stamp duty, slippage, total.
    Pure calculation — no side effects."""
    from diamond.execution.costs import calculate_costs

    costs = calculate_costs(action.upper(), amount)
    return _json(costs)


# ===========================================================================
# PORTFOLIO TOOLS
# ===========================================================================


@mcp.tool()
def portfolio_status(strategy: str = "gods_plan") -> str:
    """Get portfolio status — holdings, cash, NAV, fees, trade count, last rebalance.
    Works for both live and paper portfolios. Tries paper if live is empty."""
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            current_prices = _get_current_prices(list(holdings.keys()))
            nav = ledger.get_portfolio_value(current_prices)
            initial = ledger.get_initial_capital()
            return _json({
                "strategy": s,
                "mode": "paper" if "_paper" in s else "live",
                "holdings": holdings,
                "holdings_count": len(holdings),
                "cash": round(ledger.get_cash(), 2),
                "nav": round(nav, 2),
                "initial_capital": initial,
                "total_return_pct": round((nav - initial) / initial * 100, 2) if initial > 0 else 0,
                "total_fees": round(ledger.get_total_fees(), 2),
                "trade_count": len(ledger.get_trades()),
                "last_rebalance": ledger.get_last_rebalance(),
            })
        except Exception:
            continue
    return _json({"error": f"No holdings found for strategy '{strategy}'"})


@mcp.tool()
def portfolio_holdings(strategy: str = "gods_plan") -> str:
    """Get detailed holdings with current prices, values, weights, and day changes."""
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            tickers = list(holdings.keys())
            prices_df = download_prices(tickers, period_days=5, use_cache=True)
            details = []
            total_value = 0
            for ticker, shares in holdings.items():
                series = prices_df[ticker].dropna() if ticker in prices_df.columns else None
                current = float(series.iloc[-1]) if series is not None and len(series) > 0 else 0
                prev = float(series.iloc[-2]) if series is not None and len(series) >= 2 else current
                avg_price = ledger.get_avg_price(ticker)
                value = shares * current
                total_value += value
                details.append({
                    "ticker": ticker,
                    "shares": shares,
                    "avg_price": round(avg_price, 2),
                    "current_price": round(current, 2),
                    "value": round(value, 2),
                    "pnl_pct": round((current - avg_price) / avg_price * 100, 2) if avg_price > 0 else 0,
                    "day_change_pct": round((current - prev) / prev * 100, 2) if prev > 0 else 0,
                })
            # Add weights
            for d in details:
                d["weight_pct"] = round(d["value"] / total_value * 100, 2) if total_value > 0 else 0
            details.sort(key=lambda x: x["value"], reverse=True)
            return _json({"strategy": s, "holdings": details, "total_value": round(total_value, 2)})
        except Exception:
            continue
    return _json({"error": f"No holdings found for strategy '{strategy}'"})


@mcp.tool()
def portfolio_trades(strategy: str = "gods_plan", since: str | None = None) -> str:
    """Get trade history for a strategy. Optionally filter by date (YYYY-MM-DD)."""
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            trades = ledger.get_trades(since=since)
            if not trades:
                continue
            return _json({
                "strategy": s,
                "trade_count": len(trades),
                "trades": [_dc_to_dict(t) for t in trades[-20:]],  # Last 20
            })
        except Exception:
            continue
    return _json({"error": f"No trades found for strategy '{strategy}'"})


# ===========================================================================
# RISK & MONITORING TOOLS
# ===========================================================================


@mcp.tool()
def risk_report(strategy: str = "gods_plan") -> str:
    """Compute portfolio risk metrics — VaR (95%/99%), CVaR, drawdown from HWM,
    portfolio beta, annualized volatility, correlation, and de-risking signals.
    Signals: WARNING/CRITICAL for drawdown, VaR, correlation, volatility."""
    from diamond.monitoring.risk import compute_risk_report
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            current_prices = _get_current_prices(list(holdings.keys()))
            report = compute_risk_report(s, current_prices)
            return _json(report)
        except Exception:
            continue
    return _json({"error": f"No holdings found for strategy '{strategy}'"})


@mcp.tool()
def health_check(strategy: str = "gods_plan") -> str:
    """Run portfolio health checks — drawdown alerts, stop-loss triggers,
    position drift, and concentration warnings. Returns list of alerts with severity."""
    from diamond.monitoring.alerts import run_health_check
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            current_prices = _get_current_prices(list(holdings.keys()))
            alerts = run_health_check(s, current_prices)
            return _json({
                "strategy": s,
                "alert_count": len(alerts),
                "alerts": [_dc_to_dict(a) for a in alerts],
            })
        except Exception:
            continue
    return _json({"error": f"No holdings found for strategy '{strategy}'"})


@mcp.tool()
def performance_attribution(strategy: str = "gods_plan", period: str = "3M") -> str:
    """Brinson sector decomposition — stock-level and sector-level attribution.
    Shows top/bottom contributors, allocation/selection effects, tracking error.
    Period: 1W, 1M, 3M, 6M, 1Y."""
    from diamond.analysis.attribution import compute_attribution

    report = compute_attribution(strategy, period=period)
    return _json(report)


# ===========================================================================
# WATCHLIST TOOLS
# ===========================================================================


@mcp.tool()
def watchlist_view() -> str:
    """View the current stock watchlist with price alerts and RSI signals."""
    from diamond.data.watchlist import load_watchlist, check_signals, fetch_watchlist_prices

    entries = load_watchlist()
    if not entries:
        return _json({"watchlist": [], "signals": [], "message": "Watchlist is empty"})
    prices = fetch_watchlist_prices(entries)
    signals = check_signals(entries, prices)
    return _json({
        "entries": {k: _dc_to_dict(v) for k, v in entries.items()},
        "prices": prices,
        "signals": [_dc_to_dict(s) for s in signals],
    })


@mcp.tool()
def watchlist_add(ticker: str, price_above: float | None = None, price_below: float | None = None, notes: str = "") -> str:
    """Add a stock to the watchlist with optional price alerts.
    price_above: alert when price goes above this level.
    price_below: alert when price drops below this level."""
    from diamond.data.watchlist import add_ticker

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"
    entry = add_ticker(ticker, notes=notes, price_above=price_above, price_below=price_below)
    return _json({"added": _dc_to_dict(entry)})


@mcp.tool()
def watchlist_remove(ticker: str) -> str:
    """Remove a stock from the watchlist."""
    from diamond.data.watchlist import remove_ticker

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"
    removed = remove_ticker(ticker)
    return _json({"ticker": ticker, "removed": removed})


# ===========================================================================
# TAX & COMPARISON TOOLS
# ===========================================================================


@mcp.tool()
def tax_report(strategy: str = "gods_plan") -> str:
    """Capital gains tax report — FIFO lot matching, STCG/LTCG classification,
    estimated tax liability. Indian tax rates: STCG 20%, LTCG 12.5% (exempt up to 1.25L)."""
    from diamond.analysis.tax import compute_tax_report

    report = compute_tax_report(strategy)
    return _json(report)


@mcp.tool()
def compare_strategies(strategies: str = "gods_plan,steady") -> str:
    """Side-by-side comparison of two or more strategies.
    Pass comma-separated names (e.g., 'gods_plan,steady,baseline').
    Returns NAV, returns, risk metrics, sector exposure for each."""
    from diamond.analysis.compare import compare_strategies as _compare

    names = [s.strip() for s in strategies.split(",")]
    snapshots = _compare(names, include_risk=True)
    return _json([_dc_to_dict(s) for s in snapshots])


@mcp.tool()
def whatif_simulation(strategy: str = "gods_plan", add_tickers: str = "", remove_tickers: str = "") -> str:
    """Simulate adding or removing stocks from a portfolio.
    Pass comma-separated tickers. Shows before/after impact on beta, sector concentration, returns."""
    from diamond.analysis.compare import simulate_whatif

    add_list = [t.strip() for t in add_tickers.split(",") if t.strip()]
    remove_list = [t.strip() for t in remove_tickers.split(",") if t.strip()]
    # Auto-append .NS
    add_list = [t if t.endswith(".NS") else f"{t}.NS" for t in add_list]
    remove_list = [t if t.endswith(".NS") else f"{t}.NS" for t in remove_list]
    result = simulate_whatif(strategy, add_list, remove_list)
    return _json(result)


# ===========================================================================
# DAILY BRIEFING TOOLS
# ===========================================================================


@mcp.tool()
def today_briefing(strategy: str = "gods_plan") -> str:
    """Full daily briefing — market snapshot, portfolio snapshot, sector rotation,
    top opportunities, daily insight, and active alerts. The 'homepage' of your portfolio."""
    from diamond.daily.today import get_today_briefing

    briefing = get_today_briefing(strategy=strategy)
    return _json(briefing)


@mcp.tool()
def daily_streak(strategy: str = "accumulate") -> str:
    """Log and check daily check-in streak. Returns current streak, milestones, and fun facts."""
    from diamond.daily.streak import get_streak_report

    report = get_streak_report(strategy=strategy)
    return _json(report)


# ===========================================================================
# ACCUMULATE STRATEGY TOOLS
# ===========================================================================


@mcp.tool()
def accumulate_opportunities(strategy: str = "accumulate") -> str:
    """Find quality-ranked buy opportunities for the accumulate strategy.
    Considers market verdict, available cash, and quality scores.
    Quality = CAGR 30% + Alpha 25% + Low-vol 20% + Beta 15% + Hurst 10%."""
    from diamond.strategies.accumulate import plan_accumulation

    plan = plan_accumulation(strategy)
    return _json(plan)


@mcp.tool()
def accumulate_review(strategy: str = "accumulate") -> str:
    """Review current holdings for quality drops, stop-loss triggers, and swap suggestions.
    Flags stocks that no longer meet quality criteria and suggests replacements."""
    from diamond.strategies.accumulate import review_holdings

    review = review_holdings(strategy)
    return _json(review)


@mcp.tool()
def accumulate_status(strategy: str = "accumulate") -> str:
    """Get accumulate portfolio status — positions, cash, quality scores."""
    from diamond.strategies.accumulate import get_accumulate_status

    status = get_accumulate_status(strategy)
    return _json(status)


@mcp.tool()
def accumulate_add_cash(strategy: str = "accumulate", amount: float = 50000) -> str:
    """Add cash to the accumulate portfolio for future deployment."""
    from diamond.strategies.accumulate import add_cash

    new_cash = add_cash(strategy, amount)
    return _json({"strategy": strategy, "added": amount, "new_cash_balance": new_cash})


# ===========================================================================
# EXECUTION TOOLS (read-only by default)
# ===========================================================================


@mcp.tool()
def preview_rebalance(strategy: str = "gods_plan", capital: float = 500000) -> str:
    """DRY-RUN: Preview what trades a rebalance would execute.
    Shows sells and buys with amounts, but does NOT execute them.
    Always runs in dry-run mode for safety."""
    from diamond.analysis.screener import screen
    from diamond.strategies.gods_plan import GodsPlanStrategy
    from diamond.strategies.steady import SteadyStrategy
    from diamond.strategies.baseline import BaselineStrategy
    from diamond.execution.executor import execute

    strategy_map = {
        "gods_plan": GodsPlanStrategy,
        "steady": SteadyStrategy,
        "baseline": BaselineStrategy,
    }
    strat_name = strategy.replace("_paper", "")
    strat_cls = strategy_map.get(strat_name)
    if not strat_cls:
        return _json({"error": f"Unknown strategy: {strategy}"})

    screener_df = screen()
    strat = strat_cls()
    candidates = strat.screen(screener_df)
    allocation = strat.allocate(candidates, capital)
    result = execute(strategy, allocation, capital, dry_run=True, screener_df=screener_df)
    return _json(result)


@mcp.tool()
def estimate_costs_portfolio(strategy: str = "gods_plan", turnover_pct: float = 0.5) -> str:
    """Estimate annual transaction costs for a portfolio given a turnover rate."""
    from diamond.execution.costs import annual_cost_estimate
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            current_prices = _get_current_prices(list(holdings.keys()))
            nav = ledger.get_portfolio_value(current_prices)
            estimate = annual_cost_estimate(nav, turnover_pct)
            return _json({
                "strategy": s,
                "nav": round(nav, 2),
                "turnover_pct": turnover_pct,
                "estimated_annual_cost": round(estimate, 2),
                "cost_as_pct_of_nav": round(estimate / nav * 100, 3) if nav > 0 else 0,
            })
        except Exception:
            continue
    return _json({"error": f"No holdings found for strategy '{strategy}'"})


# ===========================================================================
# BEGINNER TOOLS
# ===========================================================================


@mcp.tool()
def learn_topic(topic: str = "") -> str:
    """Get an investing lesson using YOUR portfolio as examples.
    Leave topic empty for today's lesson, or specify: beta, alpha, diversification,
    rebalancing, costs, momentum, value, volatility, correlation, compounding."""
    from diamond.daily.learn import get_daily_lesson, list_topics

    # Map topic names to indices in _LESSON_GENERATORS
    topic_map = {
        "beta": 0,
        "alpha": 1,
        "volatility": 2,
        "hurst": 3,
        "momentum": 3,
        "cagr": 4,
        "compounding": 4,
        "vix": 5,
        "diversification": 6,
        "drawdown": 7,
        "rebalancing": 8,
        "costs": 8,
        "position sizing": 8,
        "value": 9,
        "quality": 9,
        "correlation": 6,
    }

    if topic:
        idx = topic_map.get(topic.lower().strip())
        if idx is not None:
            lesson = get_daily_lesson(topic_index=idx)
        else:
            # Try matching partial topic name against available topics
            all_topics = list_topics()
            matched = None
            for i, t in enumerate(all_topics):
                if topic.lower() in t.lower():
                    matched = i
                    break
            if matched is not None:
                lesson = get_daily_lesson(topic_index=matched)
            else:
                lesson = get_daily_lesson()
    else:
        lesson = get_daily_lesson()
    return _json(lesson)


@mcp.tool()
def portfolio_summary(strategy: str = "gods_plan") -> str:
    """Plain-English portfolio snapshot — total value, day change, best/worst stock,
    cash percentage, and a one-liner verdict. Great for quick checks."""
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            prices = _get_current_prices(list(holdings.keys()))
            nav = ledger.get_portfolio_value(prices)
            initial = ledger.get_initial_capital()
            cash = ledger.get_cash()
            cash_pct = cash / nav * 100 if nav > 0 else 0
            total_return = (nav - initial) / initial * 100 if initial > 0 else 0

            # Find best/worst by P&L %
            stock_pnl = []
            for ticker, shares in holdings.items():
                avg = ledger.get_avg_price(ticker)
                curr = prices.get(ticker, 0)
                if avg > 0 and curr > 0:
                    pnl_pct = (curr - avg) / avg * 100
                    stock_pnl.append({"ticker": ticker, "pnl_pct": round(pnl_pct, 2)})

            stock_pnl.sort(key=lambda x: x["pnl_pct"], reverse=True)
            best = stock_pnl[0] if stock_pnl else None
            worst = stock_pnl[-1] if stock_pnl else None

            # Simple verdict
            if total_return > 5:
                verdict = "Portfolio is doing well — stay the course"
            elif total_return > 0:
                verdict = "Small gains — patience, let compounding work"
            elif total_return > -5:
                verdict = "Slightly down — normal volatility, no action needed"
            elif total_return > -15:
                verdict = "Notable drawdown — review holdings but avoid panic selling"
            else:
                verdict = "Significant drawdown — check stop-losses and risk alerts"

            return _json({
                "strategy": s,
                "nav": round(nav, 2),
                "cash": round(cash, 2),
                "cash_pct": round(cash_pct, 1),
                "holdings_count": len(holdings),
                "total_return_pct": round(total_return, 2),
                "best_stock": best,
                "worst_stock": worst,
                "verdict": verdict,
            })
        except Exception:
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


# ===========================================================================
# INTERMEDIATE TOOLS
# ===========================================================================


@mcp.tool()
def drift_analysis(strategy: str = "gods_plan", capital: float = 500000) -> str:
    """Analyze how far each position has drifted from its target weight.
    Shows per-ticker drift, max/mean drift, and whether rebalancing is recommended."""
    from diamond.data.ledger import Ledger
    from diamond.execution.smart_rebalance import compute_drift

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            # Get target allocation
            strat_name = s.replace("_paper", "")
            if strat_name == "gods_plan":
                from diamond.strategies.gods_plan import GodsPlanStrategy
                strat = GodsPlanStrategy()
            elif strat_name == "steady":
                from diamond.strategies.steady import SteadyStrategy
                strat = SteadyStrategy()
            elif strat_name == "baseline":
                from diamond.strategies.baseline import BaselineStrategy
                strat = BaselineStrategy()
            else:
                return _json({"error": f"Unknown strategy: {strat_name}"})

            candidates = strat.screen(None)
            if hasattr(candidates, "empty") and candidates.empty:
                return _json({"error": "Screening produced no candidates"})

            prices = _get_current_prices(
                list(set(list(holdings.keys()) + list(
                    candidates.index.tolist() if hasattr(candidates, "index") else []
                )))
            )
            nav = ledger.get_portfolio_value(prices)
            alloc_capital = max(nav, capital)
            target = strat.allocate(candidates, alloc_capital)

            all_tickers = list(set(list(holdings.keys()) + list(target.keys())))
            missing = [t for t in all_tickers if t not in prices]
            if missing:
                more_prices = _get_current_prices(missing)
                prices.update(more_prices)

            report = compute_drift(holdings, target, prices)
            return _json(report)
        except Exception as e:
            logger.warning(f"Drift analysis failed for {s}: {e}")
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


@mcp.tool()
def rebalance_check(strategy: str = "gods_plan") -> str:
    """Should you rebalance today? Checks time since last rebalance, position drift,
    and market conditions. Returns yes/no with reasoning."""
    from diamond.data.ledger import Ledger
    from diamond.config import get_config
    from datetime import datetime

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            cfg = get_config()

            last = ledger.get_last_rebalance()
            days_since = 0
            if last:
                last_dt = datetime.strptime(last, "%Y-%m-%d")
                days_since = (datetime.now() - last_dt).days

            freq = cfg.rebalance.rebalance_frequency_days
            time_due = days_since >= freq

            reasons = []
            should = False

            if time_due:
                reasons.append(f"Time-based: {days_since}d since last rebalance (threshold: {freq}d)")
                should = True
            else:
                reasons.append(f"Time: {days_since}d since last ({freq - days_since}d until due)")

            # Check market pulse
            try:
                from diamond.monitoring.market_pulse import get_market_pulse
                pulse = get_market_pulse()
                if pulse.verdict == "DEFENSIVE":
                    reasons.append("Market: DEFENSIVE — avoid rebalancing into weakness")
                    should = False
                else:
                    reasons.append(f"Market: {pulse.verdict} (score {pulse.score})")
            except Exception:
                reasons.append("Market: Unable to fetch pulse")

            return _json({
                "strategy": s,
                "should_rebalance": should,
                "days_since_last": days_since,
                "rebalance_frequency": freq,
                "reasons": reasons,
                "last_rebalance": last or "never",
            })
        except Exception:
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


@mcp.tool()
def tax_aware_trades(strategy: str = "gods_plan", capital: float = 500000) -> str:
    """Preview rebalance trades ordered to minimize tax impact.
    Shows STCG vs LTCG classification, tax-loss harvesting opportunities,
    and priority ordering (harvest losses first, defer gains)."""
    from diamond.data.ledger import Ledger
    from diamond.execution.smart_rebalance import plan_tax_aware_trades
    from diamond.config import get_config

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            strat_name = s.replace("_paper", "")
            if strat_name == "gods_plan":
                from diamond.strategies.gods_plan import GodsPlanStrategy
                strat = GodsPlanStrategy()
            elif strat_name == "steady":
                from diamond.strategies.steady import SteadyStrategy
                strat = SteadyStrategy()
            elif strat_name == "baseline":
                from diamond.strategies.baseline import BaselineStrategy
                strat = BaselineStrategy()
            else:
                return _json({"error": f"Unknown strategy: {strat_name}"})

            candidates = strat.screen(None)
            if hasattr(candidates, "empty") and candidates.empty:
                return _json({"error": "Screening produced no candidates"})

            prices = _get_current_prices(list(holdings.keys()))
            nav = ledger.get_portfolio_value(prices)
            alloc_capital = max(nav, capital)
            target = strat.allocate(candidates, alloc_capital)

            all_tickers = list(set(list(holdings.keys()) + list(target.keys())))
            missing = [t for t in all_tickers if t not in prices]
            if missing:
                more_prices = _get_current_prices(missing)
                prices.update(more_prices)

            cfg = get_config()
            smart_trades = plan_tax_aware_trades(
                ledger, target, prices, cfg.rebalance.min_trade_value
            )

            return _json({
                "strategy": s,
                "trade_count": len(smart_trades),
                "trades": [_dc_to_dict(t) for t in smart_trades],
            })
        except Exception as e:
            logger.warning(f"Tax-aware trades failed for {s}: {e}")
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


@mcp.tool()
def correlation_matrix(strategy: str = "gods_plan", period_days: int = 252) -> str:
    """Pairwise correlation matrix of portfolio holdings.
    Shows which stocks move together — high correlation = less diversification.
    Avg > 0.6 is concerning, > 0.8 is critical."""
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            tickers = list(holdings.keys())
            if len(tickers) < 2:
                return _json({"strategy": s, "message": "Need at least 2 holdings for correlation"})

            df = download_prices(tickers, period_days=period_days, use_cache=True)
            if df.empty:
                return _json({"error": "No price data"})

            returns = df.pct_change().dropna()
            corr = returns.corr()

            # Extract pairs
            pairs = []
            for i, t1 in enumerate(corr.columns):
                for j, t2 in enumerate(corr.columns):
                    if i < j:
                        pairs.append({
                            "stock_1": t1,
                            "stock_2": t2,
                            "correlation": round(float(corr.iloc[i, j]), 3),
                        })
            pairs.sort(key=lambda x: -abs(x["correlation"]))

            avg_corr = sum(abs(p["correlation"]) for p in pairs) / len(pairs) if pairs else 0
            max_corr = max((abs(p["correlation"]) for p in pairs), default=0)

            return _json({
                "strategy": s,
                "holdings_count": len(tickers),
                "avg_correlation": round(avg_corr, 3),
                "max_correlation": round(max_corr, 3),
                "diversification": "good" if avg_corr < 0.4 else ("moderate" if avg_corr < 0.6 else "poor"),
                "top_pairs": pairs[:10],
            })
        except Exception as e:
            logger.warning(f"Correlation failed for {s}: {e}")
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


@mcp.tool()
def volatility_sizing(strategy: str = "gods_plan") -> str:
    """Show current position sizes vs volatility-adjusted optimal sizes.
    Higher volatility stocks should have smaller positions. Helps identify
    positions that are too large relative to their risk."""
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices
    import math

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            tickers = list(holdings.keys())
            prices = _get_current_prices(tickers)
            nav = ledger.get_portfolio_value(prices)

            # Get volatilities
            df = download_prices(tickers, period_days=252, use_cache=True)
            if df.empty:
                return _json({"error": "No price data for volatility calculation"})

            returns = df.pct_change().dropna()
            vols = {}
            for t in tickers:
                if t in returns.columns:
                    vols[t] = float(returns[t].std() * math.sqrt(252))

            if not vols:
                return _json({"error": "Could not calculate volatilities"})

            # Inverse-vol weights
            inv_vols = {t: 1 / v for t, v in vols.items() if v > 0}
            total_inv = sum(inv_vols.values())
            optimal = {t: round(iv / total_inv * 100, 2) for t, iv in inv_vols.items()}

            result = []
            for t in tickers:
                price = prices.get(t, 0)
                current_wt = round(holdings[t] * price / nav * 100, 2) if nav > 0 and price > 0 else 0
                opt_wt = optimal.get(t, 0)
                vol = round(vols.get(t, 0) * 100, 1)
                result.append({
                    "ticker": t,
                    "current_weight_pct": current_wt,
                    "optimal_weight_pct": opt_wt,
                    "delta_pct": round(current_wt - opt_wt, 2),
                    "annualized_vol_pct": vol,
                    "sizing": "oversized" if current_wt > opt_wt * 1.5 else ("undersized" if current_wt < opt_wt * 0.5 else "ok"),
                })

            result.sort(key=lambda x: -abs(x["delta_pct"]))
            return _json({"strategy": s, "positions": result})
        except Exception as e:
            logger.warning(f"Volatility sizing failed for {s}: {e}")
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


@mcp.tool()
def watchlist_signals() -> str:
    """Get all active signals from your watchlist — price alerts (above/below targets),
    RSI oversold/overbought, and quality score changes. Only returns stocks with signals."""
    from diamond.data.watchlist import load_watchlist, check_signals, fetch_watchlist_prices

    entries = load_watchlist()
    if not entries:
        return _json({"signals": [], "message": "Watchlist is empty. Add stocks with watchlist_add."})

    prices = fetch_watchlist_prices(entries)
    signals = check_signals(entries, prices)

    triggered = [_dc_to_dict(s) for s in signals]
    return _json({
        "total_watched": len(entries),
        "signals_triggered": len(triggered),
        "signals": triggered,
    })


@mcp.tool()
def order_book(strategy: str = "gods_plan") -> str:
    """View the order book — pending, filled, and failed orders.
    Shows order lifecycle and execution status."""
    from diamond.execution.orders import OrderBook

    for s in [strategy, f"{strategy}_paper"]:
        try:
            book = OrderBook(s)
            orders = book.get_orders()
            if not orders:
                continue

            summary = {"pending": [], "filled": [], "cancelled": [], "failed": []}
            for o in orders:
                entry = _dc_to_dict(o)
                status = o.status.lower()
                if status == "pending":
                    summary["pending"].append(entry)
                elif status == "filled":
                    summary["filled"].append(entry)
                elif status == "cancelled":
                    summary["cancelled"].append(entry)
                else:
                    summary["failed"].append(entry)

            return _json({
                "strategy": s,
                "total_orders": len(orders),
                "pending": len(summary["pending"]),
                "filled": len(summary["filled"]),
                "orders": summary,
            })
        except Exception:
            continue
    return _json({"strategy": strategy, "total_orders": 0, "message": "No orders found"})


@mcp.tool()
def corporate_actions(strategy: str = "gods_plan", since: str = "") -> str:
    """Detect splits, dividends, and bonus issues for portfolio holdings.
    Shows pending actions and their impact on share counts and prices."""
    from diamond.data.corporate_actions import detect_all
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            all_actions = []
            since_date = since if since else None
            for ticker in holdings:
                actions = detect_all(ticker, since=since_date)
                all_actions.extend(actions)

            return _json({
                "strategy": s,
                "holdings_checked": len(holdings),
                "actions_found": len(all_actions),
                "actions": [_dc_to_dict(a) for a in all_actions],
            })
        except Exception as e:
            logger.warning(f"Corporate actions check failed for {s}: {e}")
            continue
    return _json({"error": f"No holdings found for '{strategy}'"})


# ===========================================================================
# TARGETED TRADE TOOLS
# ===========================================================================


@mcp.tool()
def sell_stock(
    ticker: str,
    strategy: str = "gods_plan",
    shares: int = 0,
    dry_run: bool = True,
    reason: str = "Manual sell",
) -> str:
    """Sell a specific stock from a portfolio. Set shares=0 to sell all.
    dry_run=True by default for safety — set False to execute."""
    from diamond.execution.executor import execute_sell

    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    result = execute_sell(
        strategy=strategy,
        ticker=ticker,
        shares=shares if shares > 0 else None,
        reason=reason,
        dry_run=dry_run,
    )
    return _json(result)


@mcp.tool()
def buy_stock(
    ticker: str,
    strategy: str = "gods_plan",
    amount: float = 0,
    shares: int = 0,
    dry_run: bool = True,
    reason: str = "Manual buy",
) -> str:
    """Buy a specific stock into a portfolio. Specify amount (INR) or shares.
    dry_run=True by default for safety — set False to execute."""
    from diamond.execution.executor import execute_buy

    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    result = execute_buy(
        strategy=strategy,
        ticker=ticker,
        amount=amount if amount > 0 else None,
        shares=shares if shares > 0 else None,
        reason=reason,
        dry_run=dry_run,
    )
    return _json(result)


@mcp.tool()
def cleanup_delisted(strategy: str = "gods_plan", dry_run: bool = True) -> str:
    """Detect and write off delisted stocks from a portfolio.
    Scans for holdings with no price data. dry_run=True by default."""
    from diamond.execution.executor import execute_cleanup

    result = execute_cleanup(strategy=strategy, dry_run=dry_run)
    return _json(result)


@mcp.tool()
def trim_positions(strategy: str = "gods_plan", dry_run: bool = True) -> str:
    """Trim positions exceeding the 10% max weight back to limit.
    dry_run=True by default for safety."""
    from diamond.execution.executor import execute_trim

    result = execute_trim(strategy=strategy, dry_run=dry_run)
    return _json(result)


@mcp.tool()
def actionable_alerts(strategy: str = "gods_plan") -> str:
    """Get stop-loss, concentration, and delisted alerts that need action.
    Returns alerts with suggested actions (sell, trim, cleanup)."""
    from diamond.monitoring.alerts import get_actionable_alerts

    ledger_name = strategy
    # Try paper if live is empty
    from diamond.data.ledger import Ledger
    ledger = Ledger(strategy)
    if not ledger.get_holdings():
        ledger_name = f"{strategy}_paper"
        ledger = Ledger(ledger_name)
        if not ledger.get_holdings():
            return _json({"error": f"No holdings found for '{strategy}'"})

    holdings = ledger.get_holdings()
    prices = _get_current_prices(list(holdings.keys()))
    alerts = get_actionable_alerts(ledger_name, prices)

    return _json({
        "strategy": ledger_name,
        "alert_count": len(alerts),
        "alerts": alerts,
    })


# ===========================================================================
# ADVANCED TOOLS (Part 1)
# ===========================================================================


def _normalize_tickers(tickers_csv: str) -> list[str]:
    """Parse comma-separated tickers and ensure .NS suffix."""
    tickers = [t.strip() for t in tickers_csv.split(",") if t.strip()]
    return [t if t.endswith(".NS") or t.endswith(".BO") else f"{t}.NS" for t in tickers]


def _get_returns_df(tickers: list[str], period_days: int = 504) -> "pd.DataFrame":
    """Download prices and compute daily returns DataFrame for optimizer functions."""
    import pandas as pd
    from diamond.data.market import download_prices

    prices_df = download_prices(tickers, period_days=period_days, use_cache=True)
    if prices_df.empty:
        return pd.DataFrame()
    returns_df = prices_df.pct_change().dropna()
    return returns_df


@mcp.tool()
def optimize_weights(tickers: str, simulations: int = 5000, max_weight: float = 0.10) -> str:
    """Monte Carlo Sharpe-optimal portfolio weights.
    Pass comma-separated tickers (e.g., 'RELIANCE.NS,TCS.NS,INFY.NS').
    Returns {ticker: weight} with expected return, volatility, and Sharpe ratio."""
    import numpy as np
    from diamond.analysis.optimizer import monte_carlo_optimize

    ticker_list = _normalize_tickers(tickers)
    if len(ticker_list) < 2:
        return _json({"error": "Need at least 2 tickers for optimization"})

    try:
        returns_df = _get_returns_df(ticker_list)
        if returns_df.empty or len(returns_df) < 60:
            return _json({"error": "Insufficient price data for optimization"})

        weights = monte_carlo_optimize(returns_df, num_simulations=simulations, max_weight=max_weight)

        # Compute portfolio metrics for the optimal weights
        from diamond.config import get_config
        rf = get_config().screener.risk_free_rate
        mean_returns = returns_df.mean()
        cov_matrix = returns_df.cov()
        w_arr = np.array([weights.get(t, 0) for t in returns_df.columns])
        port_return = float(w_arr @ mean_returns.values * 252)
        port_vol = float(np.sqrt(w_arr @ cov_matrix.values @ w_arr * 252))
        sharpe = (port_return - rf) / port_vol if port_vol > 0 else 0

        return _json({
            "weights": {t: round(w, 4) for t, w in weights.items()},
            "simulations": simulations,
            "max_weight": max_weight,
            "expected_return_pct": round(port_return * 100, 2),
            "volatility_pct": round(port_vol * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "tickers_used": len(weights),
        })
    except Exception as e:
        return _json({"error": f"Optimization failed: {e}"})


@mcp.tool()
def inverse_vol_weights(tickers: str) -> str:
    """Inverse-volatility weighted allocation — lower volatility stocks get higher weights.
    Pass comma-separated tickers (e.g., 'RELIANCE.NS,TCS.NS')."""
    from diamond.analysis.optimizer import inverse_volatility_weights

    ticker_list = _normalize_tickers(tickers)
    if not ticker_list:
        return _json({"error": "No tickers provided"})

    try:
        returns_df = _get_returns_df(ticker_list)
        if returns_df.empty:
            return _json({"error": "Insufficient price data"})

        weights = inverse_volatility_weights(returns_df)
        return _json({
            "weights": {t: round(w, 4) for t, w in weights.items()},
            "method": "inverse_volatility",
            "tickers_used": len(weights),
        })
    except Exception as e:
        return _json({"error": f"Inverse-vol weighting failed: {e}"})


@mcp.tool()
def equal_weight_allocation(tickers: str) -> str:
    """Equal-weight allocation across tickers.
    Pass comma-separated tickers (e.g., 'RELIANCE.NS,TCS.NS')."""
    from diamond.analysis.optimizer import equal_weights as _equal_weights

    ticker_list = _normalize_tickers(tickers)
    if not ticker_list:
        return _json({"error": "No tickers provided"})

    weights = _equal_weights(ticker_list)
    return _json({
        "weights": {t: round(w, 4) for t, w in weights.items()},
        "method": "equal_weight",
        "tickers_used": len(weights),
    })


@mcp.tool()
def market_cap_weight_allocation(tickers: str) -> str:
    """Market-cap weighted allocation — larger companies get higher weights.
    Pass comma-separated tickers (e.g., 'RELIANCE.NS,TCS.NS').
    Fetches live market caps from Yahoo Finance."""
    from diamond.analysis.optimizer import market_cap_weights as _mcap_weights
    from diamond.data.market import get_market_cap

    ticker_list = _normalize_tickers(tickers)
    if not ticker_list:
        return _json({"error": "No tickers provided"})

    try:
        caps: dict[str, float] = {}
        failed: list[str] = []
        for t in ticker_list:
            cap = get_market_cap(t)
            if cap and cap > 0:
                caps[t] = cap
            else:
                failed.append(t)

        if not caps:
            return _json({"error": "Could not fetch market cap for any ticker"})

        weights = _mcap_weights(caps)
        result: dict = {
            "weights": {t: round(w, 4) for t, w in weights.items()},
            "method": "market_cap",
            "tickers_used": len(weights),
            "market_caps_cr": {t: round(c / 1e7, 2) for t, c in caps.items()},
        }
        if failed:
            result["failed_tickers"] = failed
        return _json(result)
    except Exception as e:
        return _json({"error": f"Market-cap weighting failed: {e}"})


@mcp.tool()
def trade_rationale(ticker: str, strategy: str = "gods_plan") -> str:
    """Explain why a stock would be bought/sold by a strategy.
    Returns selection reason, weight method, timing, market context, and risk notes.
    Runs screener + allocation to generate rationale with real data."""
    from diamond.analysis.rationale import generate_rationale, format_rationale_verbose
    from diamond.analysis.screener import screen
    from diamond.data.ledger import Ledger

    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    try:
        # Get screener data
        screener_df = screen()

        # Get current holdings
        ledger_name = strategy
        for s in [strategy, f"{strategy}_paper"]:
            try:
                ledger = Ledger(s)
                if ledger.get_holdings():
                    ledger_name = s
                    break
            except Exception:
                continue

        ledger = Ledger(ledger_name)
        holdings = ledger.get_holdings()
        current_prices = _get_current_prices(
            list(set(list(holdings.keys()) + [ticker]))
        )

        # Determine action and weight
        is_held = ticker in holdings
        action = "SELL" if is_held else "BUY"
        target_weight = 0.06 if action == "BUY" else 0.0
        target_allocation = {ticker: target_weight}

        rationale = generate_rationale(
            ticker=ticker,
            action=action,
            target_weight=target_weight,
            screener_df=screener_df,
            strategy_name=strategy.replace("_paper", ""),
            target_allocation=target_allocation,
            holdings=holdings,
            current_prices=current_prices,
        )

        return _json({
            "ticker": ticker,
            "strategy": ledger_name,
            "action": rationale.action,
            "is_currently_held": is_held,
            "component": rationale.component,
            "selection_reason": rationale.selection_reason,
            "screener_metrics": rationale.screener_summary,
            "weight_pct": rationale.weight_pct,
            "weight_method": rationale.weight_method,
            "weight_reason": rationale.weight_reason,
            "timing": rationale.timing_reason,
            "market_context": rationale.market_context,
            "risk_notes": rationale.risk_notes,
            "verbose": format_rationale_verbose(rationale),
        })
    except Exception as e:
        return _json({"error": f"Rationale generation failed: {e}"})


@mcp.tool()
def run_backtest(
    strategy: str = "gods_plan",
    start_date: str = "2020-01-01",
    end_date: str = "2025-01-01",
    capital: float = 500000,
    window_months: int = 6,
) -> str:
    """Walk-forward backtest a strategy over a date range.
    Returns CAGR, Sharpe, max drawdown, win rate, total trades, fees.
    WARNING: This is HEAVY — may take 30-60 seconds depending on period length.
    Strategies: gods_plan, steady, baseline."""
    from diamond.backtest.engine import run_backtest as _run_backtest
    from diamond.backtest.reporter import compute_metrics
    from diamond.strategies.gods_plan import GodsPlanStrategy
    from diamond.strategies.steady import SteadyStrategy
    from diamond.strategies.baseline import BaselineStrategy

    strategy_map = {
        "gods_plan": GodsPlanStrategy,
        "steady": SteadyStrategy,
        "baseline": BaselineStrategy,
    }
    strat_name = strategy.replace("_paper", "")
    strat_cls = strategy_map.get(strat_name)
    if not strat_cls:
        return _json({"error": f"Unknown strategy: {strategy}. Use: gods_plan, steady, baseline"})

    try:
        strat = strat_cls()
        result = _run_backtest(
            strategy=strat,
            strategy_name=strat_name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=capital,
            window_months=window_months,
            step_months=window_months,
        )
        metrics = compute_metrics(result)

        windows = [
            {
                "id": w.window_id,
                "period": f"{w.start} -> {w.end}",
                "return_pct": w.return_pct,
                "trades": w.num_trades,
                "fees": round(w.total_fees, 2),
                "holdings": w.holdings_count,
            }
            for w in result.windows
        ]

        return _json({
            "strategy": strat_name,
            "period": f"{start_date} to {end_date}",
            "metrics": metrics,
            "windows": windows,
        })
    except Exception as e:
        return _json({"error": f"Backtest failed: {e}"})


@mcp.tool()
def export_reports(strategy: str = "gods_plan", format: str = "all") -> str:
    """Generate portfolio reports — markdown summary, CSV holdings, CSV trades, JSON full export.
    Format: 'all', 'md', 'csv', 'json'. Returns list of generated file paths."""
    from diamond.analysis.export import (
        export_all,
        export_portfolio_summary,
        export_holdings_csv,
        export_trades_csv,
        export_full_json,
    )
    from diamond.data.ledger import Ledger

    # Try paper if live has no holdings
    ledger_name = strategy
    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            if ledger.get_holdings():
                ledger_name = s
                break
        except Exception:
            continue

    try:
        fmt = format.lower()
        if fmt == "all":
            results = export_all(ledger_name)
        elif fmt == "md":
            results = [export_portfolio_summary(ledger_name)]
        elif fmt == "csv":
            results = [
                export_holdings_csv(ledger_name),
                export_trades_csv(ledger_name),
            ]
        elif fmt == "json":
            results = [export_full_json(ledger_name)]
        else:
            return _json({"error": f"Unknown format: {format}. Use: all, md, csv, json"})

        return _json({
            "strategy": ledger_name,
            "format": fmt,
            "files": [
                {
                    "path": str(r.path),
                    "format": r.format,
                    "report_type": r.report_type,
                    "rows": r.rows,
                }
                for r in results
            ],
        })
    except Exception as e:
        return _json({"error": f"Export failed: {e}"})


@mcp.tool()
def custom_screen(
    min_alpha: float | None = None,
    max_beta: float | None = None,
    min_cagr: float | None = None,
    max_volatility: float | None = None,
    min_hurst: float | None = None,
) -> str:
    """Screen the NSE 500 with custom filters. All parameters are optional.
    Returns stocks matching ALL specified criteria, sorted by Alpha descending.
    Example: min_alpha=0.1, max_beta=0.9, min_cagr=0.12 finds low-beta quality stocks."""
    from diamond.analysis.screener import screen

    try:
        df = screen()
        if df.empty:
            return _json({"error": "Screener returned no data"})

        original_count = len(df)

        # Apply filters
        if min_alpha is not None and "Alpha" in df.columns:
            df = df[df["Alpha"] >= min_alpha]
        if max_beta is not None and "Beta" in df.columns:
            df = df[df["Beta"] <= max_beta]
        if min_cagr is not None and "CAGR" in df.columns:
            df = df[df["CAGR"] >= min_cagr]
        if max_volatility is not None and "Volatility" in df.columns:
            df = df[df["Volatility"] <= max_volatility]
        if min_hurst is not None and "Hurst" in df.columns:
            df = df[df["Hurst"] >= min_hurst]

        df = df.sort_values("Alpha", ascending=False).reset_index(drop=True)

        filters_applied = {
            k: v for k, v in {
                "min_alpha": min_alpha,
                "max_beta": max_beta,
                "min_cagr": min_cagr,
                "max_volatility": max_volatility,
                "min_hurst": min_hurst,
            }.items() if v is not None
        }

        # Return top 50 matches
        top = df.head(50)
        records = json.loads(top.to_json(orient="records"))

        return _json({
            "filters": filters_applied,
            "universe_size": original_count,
            "matches": len(df),
            "showing": len(top),
            "stocks": records,
        })
    except Exception as e:
        return _json({"error": f"Custom screen failed: {e}"})


# ===========================================================================
# ADVANCED TOOLS (Part 2)
# ===========================================================================


def _resolve_strategy(strategy: str) -> tuple[str, "Ledger"]:
    """Resolve strategy name to one with holdings (tries live, then paper).

    Returns (resolved_name, ledger) or raises ValueError.
    """
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        ledger = Ledger(s)
        if ledger.get_holdings():
            return s, ledger
    raise ValueError(f"No holdings found for strategy '{strategy}'")


@mcp.tool()
def risk_decomposition(strategy: str = "gods_plan") -> str:
    """Per-position risk breakdown — each stock's beta, volatility, VaR contribution,
    and weight. Plus portfolio-level CVaR, beta, and annualized volatility.
    Use this to find which stocks contribute the most risk."""
    from diamond.data.market import download_prices
    from diamond.monitoring.risk import (
        compute_risk_report,
        calculate_var,
    )
    import numpy as np

    try:
        resolved, ledger = _resolve_strategy(strategy)
    except ValueError as e:
        return _json({"error": str(e)})

    try:
        holdings = ledger.get_holdings()
        tickers = list(holdings.keys())
        current_prices = _get_current_prices(tickers)

        # Fetch historical prices for per-stock metrics
        prices_df = download_prices(tickers, period_days=252, use_cache=True)

        # Fetch benchmark for beta calculation
        bench_df = None
        bench_ret = None
        try:
            bench_df = download_prices(["^NSEI"], period_days=252, use_cache=True)
            if not bench_df.empty and "^NSEI" in bench_df.columns:
                bench_ret = bench_df["^NSEI"].pct_change().dropna()
        except Exception:
            pass

        # Compute portfolio-level risk report
        report = compute_risk_report(
            resolved, current_prices, prices_df=prices_df, benchmark_returns=bench_ret
        )

        # Per-stock decomposition
        nav = ledger.get_portfolio_value(current_prices)
        stock_risks = []

        for ticker, shares in holdings.items():
            price = current_prices.get(ticker, 0)
            value = shares * price
            weight = (value / nav * 100) if nav > 0 else 0

            stock_beta = 1.0
            stock_vol = 0.0
            stock_var = 0.0

            if ticker in prices_df.columns:
                series = prices_df[ticker].dropna()
                if len(series) >= 20:
                    returns = series.pct_change().dropna()
                    stock_vol = round(float(returns.std() * np.sqrt(252) * 100), 2)
                    stock_var = round(calculate_var(returns, 0.95, value), 2)

                    # Stock beta vs Nifty
                    if bench_ret is not None:
                        aligned = returns.to_frame("stock").join(
                            bench_ret.to_frame("bench"), how="inner"
                        ).dropna()
                        if len(aligned) >= 20:
                            cov = aligned["stock"].cov(aligned["bench"])
                            var = aligned["bench"].var()
                            if var > 0:
                                stock_beta = round(cov / var, 4)

            stock_risks.append({
                "ticker": ticker,
                "shares": shares,
                "price": round(price, 2),
                "value": round(value, 2),
                "weight_pct": round(weight, 2),
                "beta": stock_beta,
                "volatility_annual_pct": stock_vol,
                "var_95_inr": stock_var,
            })

        stock_risks.sort(key=lambda x: x["var_95_inr"], reverse=True)

        return _json({
            "strategy": resolved,
            "nav": round(nav, 2),
            "portfolio_beta": report.beta,
            "portfolio_volatility_pct": report.volatility_annual,
            "portfolio_var_95_inr": report.var_95,
            "portfolio_var_99_inr": report.var_99,
            "portfolio_cvar_95_inr": report.cvar_95,
            "drawdown_pct": report.drawdown_pct,
            "signals": report.signals,
            "positions": stock_risks,
        })
    except Exception as e:
        return _json({"error": f"Risk decomposition failed: {e}"})


@mcp.tool()
def assess_promotion(strategy: str = "gods_plan") -> str:
    """Assess whether a paper portfolio is ready for live trading.
    Returns confidence score (high/medium/low), recommendations, paper vs live comparison,
    and minimum thresholds (30 days, >-5% return, outperformance)."""
    from diamond.execution.promote import assess_promotion as _assess

    try:
        report = _assess(strategy)
        return _json(report)
    except Exception as e:
        return _json({"error": f"Promotion assessment failed: {e}"})


@mcp.tool()
def scenario_stress(strategy: str = "gods_plan", crash_pct: float = -10.0) -> str:
    """Stress test: what if Nifty moves by X%? Uses per-stock beta to estimate impact.
    crash_pct: negative for crash (e.g., -10), positive for rally (e.g., +5).
    Returns per-stock projected values and portfolio-level loss/gain estimate."""
    from diamond.daily.whatif import simulate_market_crash

    try:
        resolved, _ = _resolve_strategy(strategy)
    except ValueError as e:
        return _json({"error": str(e)})

    try:
        result = simulate_market_crash(resolved, crash_pct)
        return _json(result)
    except Exception as e:
        return _json({"error": f"Stress test failed: {e}"})


@mcp.tool()
def scenario_cash(strategy: str = "gods_plan", amount: float = 50000.0) -> str:
    """Simulate adding cash to a portfolio. Shows what the accumulate engine would buy,
    deployment plan based on current market verdict (DEPLOY/WAIT/DEFENSIVE),
    and projected new NAV."""
    from diamond.daily.whatif import simulate_add_cash

    try:
        resolved, _ = _resolve_strategy(strategy)
    except ValueError:
        # Even without holdings, cash simulation can work
        resolved = strategy

    try:
        result = simulate_add_cash(resolved, amount)
        return _json(result)
    except Exception as e:
        return _json({"error": f"Cash simulation failed: {e}"})


@mcp.tool()
def stagger_entry(
    strategy: str,
    ticker: str,
    total_shares: int,
    num_tranches: int = 3,
) -> str:
    """Break a large buy into multiple staggered tranches to reduce market impact.
    Creates PENDING orders in the order book. Returns planned order details.
    Does NOT execute — use the order book to manage lifecycle."""
    from diamond.execution.orders import create_staggered_orders, OrderBook

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    try:
        # Get current price for the order
        prices = _get_current_prices([ticker])
        current_price = prices.get(ticker, 0)
        if current_price <= 0:
            return _json({"error": f"Could not fetch price for {ticker}"})

        orders = create_staggered_orders(
            strategy=strategy,
            ticker=ticker,
            action="BUY",
            total_shares=total_shares,
            current_price=current_price,
            tranches=num_tranches,
            rationale="Staggered entry via MCP",
        )

        # Persist to order book
        book = OrderBook(strategy)
        for order in orders:
            book.create_order(order)

        return _json({
            "strategy": strategy,
            "ticker": ticker,
            "total_shares": total_shares,
            "num_tranches": len(orders),
            "current_price": round(current_price, 2),
            "total_value": round(total_shares * current_price, 2),
            "orders": [_dc_to_dict(o) for o in orders],
        })
    except Exception as e:
        return _json({"error": f"Stagger entry failed: {e}"})


@mcp.tool()
def limit_order(
    strategy: str,
    ticker: str,
    action: str,
    shares: int,
    limit_price: float,
) -> str:
    """Create a limit order at a specific target price.
    action: BUY or SELL. The order is saved as PENDING in the order book.
    Does NOT execute — tracks lifecycle for later fill/cancel."""
    from diamond.execution.orders import Order, OrderBook, generate_order_id, OrderType, OrderStatus

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    action = action.upper()
    if action not in ("BUY", "SELL"):
        return _json({"error": f"Invalid action '{action}' — must be BUY or SELL"})

    try:
        prices = _get_current_prices([ticker])
        current_price = prices.get(ticker, 0)

        order = Order(
            id=generate_order_id(strategy, ticker),
            strategy=strategy,
            ticker=ticker,
            action=action,
            shares=shares,
            price=limit_price,
            order_type=OrderType.LIMIT,
            status=OrderStatus.PENDING,
            rationale=f"Limit {action} at {limit_price} via MCP",
        )

        book = OrderBook(strategy)
        book.create_order(order)

        result = {
            "order": _dc_to_dict(order),
            "current_price": round(current_price, 2) if current_price > 0 else "unavailable",
        }
        if current_price > 0:
            if action == "BUY":
                result["discount_pct"] = round((current_price - limit_price) / current_price * 100, 2)
            else:
                result["premium_pct"] = round((limit_price - current_price) / current_price * 100, 2)

        return _json(result)
    except Exception as e:
        return _json({"error": f"Limit order creation failed: {e}"})


@mcp.tool()
def sector_exposure(strategy: str = "gods_plan") -> str:
    """Sector weight breakdown with concentration warnings and diversification score.
    Shows each sector's weight, stock count, and flags over-concentrated sectors
    (>25% weight or >4 stocks). Diversification score 0-100."""
    from diamond.data.universe import get_sector
    from diamond.config import get_config

    try:
        resolved, ledger = _resolve_strategy(strategy)
    except ValueError as e:
        return _json({"error": str(e)})

    try:
        holdings = ledger.get_holdings()
        tickers = list(holdings.keys())
        current_prices = _get_current_prices(tickers)

        nav = ledger.get_portfolio_value(current_prices)

        # Build sector breakdown
        sector_data: dict[str, dict] = {}
        for ticker, shares in holdings.items():
            price = current_prices.get(ticker, 0)
            value = shares * price
            sector = get_sector(ticker)

            if sector not in sector_data:
                sector_data[sector] = {"weight": 0.0, "value": 0.0, "stocks": [], "count": 0}
            sector_data[sector]["value"] += value
            sector_data[sector]["count"] += 1
            sector_data[sector]["stocks"].append({
                "ticker": ticker,
                "value": round(value, 2),
                "weight_pct": round(value / nav * 100, 2) if nav > 0 else 0,
            })

        # Compute weights
        for sector in sector_data:
            sector_data[sector]["weight"] = round(
                sector_data[sector]["value"] / nav * 100, 2
            ) if nav > 0 else 0

        cfg = get_config()
        max_sector_weight = getattr(cfg, "max_sector_weight_pct", 25.0)
        max_sector_stocks = getattr(cfg, "max_sector_stocks", 4)

        # Warnings
        warnings = []
        for sector, data in sector_data.items():
            if data["weight"] > max_sector_weight:
                warnings.append(
                    f"{sector}: {data['weight']:.1f}% weight exceeds {max_sector_weight}% cap"
                )
            if data["count"] > max_sector_stocks:
                warnings.append(
                    f"{sector}: {data['count']} stocks exceeds {max_sector_stocks} stock cap"
                )

        # Diversification score (0-100)
        n_sectors = len(sector_data)
        weights = [d["weight"] / 100 for d in sector_data.values() if d["weight"] > 0]
        hhi = sum(w ** 2 for w in weights) if weights else 1.0
        ideal_hhi = 1 / n_sectors if n_sectors > 0 else 1.0
        evenness_score = max(0, min(100, round((1 - (hhi - ideal_hhi) / (1 - ideal_hhi)) * 100))) if ideal_hhi < 1 else 100
        sector_breadth = min(100, round(n_sectors / 8 * 100))  # 8+ sectors = full marks
        warning_penalty = min(30, len(warnings) * 10)
        diversification_score = max(0, round((evenness_score * 0.5 + sector_breadth * 0.5) - warning_penalty))

        # Sort sectors by weight descending
        sorted_sectors = dict(
            sorted(sector_data.items(), key=lambda x: x[1]["weight"], reverse=True)
        )

        return _json({
            "strategy": resolved,
            "nav": round(nav, 2),
            "num_sectors": n_sectors,
            "num_positions": len(holdings),
            "diversification_score": diversification_score,
            "sectors": sorted_sectors,
            "warnings": warnings,
        })
    except Exception as e:
        return _json({"error": f"Sector exposure failed: {e}"})


# ===========================================================================
# EARNINGS CALENDAR TOOLS
# ===========================================================================


@mcp.tool()
def earnings_calendar(strategy: str = "gods_plan") -> str:
    """Get upcoming earnings/quarterly results dates for portfolio stocks.
    Shows stocks sorted by soonest earnings date, with days until event.
    Use before any trade to avoid earnings surprise risk."""
    try:
        from diamond.data.earnings import get_portfolio_earnings

        events = get_portfolio_earnings(strategy)
        urgent = [e for e in events if e.get("days_until", 999) <= 3]
        upcoming = [e for e in events if 3 < e.get("days_until", 999) <= 14]
        later = [e for e in events if e.get("days_until", 999) > 14]
        return _json({
            "strategy": strategy,
            "total_events": len(events),
            "urgent": urgent,
            "upcoming": upcoming,
            "later": later,
            "warning": f"{len(urgent)} stock(s) have earnings within 3 days — avoid trading these" if urgent else None,
        })
    except Exception as e:
        return _json({"error": f"Earnings calendar failed: {e}"})


@mcp.tool()
def earnings_check(ticker: str) -> str:
    """Check if a specific stock has upcoming earnings. Use before buying
    to avoid pre-earnings volatility."""
    try:
        from diamond.data.earnings import get_earnings_calendar

        if not ticker.endswith(".NS"):
            ticker = f"{ticker}.NS"
        events = get_earnings_calendar([ticker])
        if events:
            e = events[0]
            days = e.get("days_until", None)
            warning = None
            if days is not None and days <= 3:
                warning = "AVOID TRADING — earnings imminent"
            elif days is not None and days <= 7:
                warning = "CAUTION — earnings within a week"
            e["warning"] = warning
            return _json(e)
        return _json({"ticker": ticker, "earnings_date": None, "message": "No earnings date found"})
    except Exception as e:
        return _json({"error": f"Earnings check failed: {e}"})


# ===========================================================================
# PERSONAL RULES TOOLS
# ===========================================================================


@mcp.tool()
def personal_rules(category: str | None = None) -> str:
    """List personal investment rules. Optionally filter by category: buy, sell, risk, general.
    These are user-defined guardrails that guide trading decisions."""
    try:
        from diamond.data.rules import get_rules

        rules = get_rules(category)
        return _json({
            "rules": rules,
            "count": len(rules),
            "category_filter": category,
        })
    except Exception as e:
        return _json({"error": f"Rules fetch failed: {e}"})


@mcp.tool()
def add_personal_rule(text: str, category: str = "general") -> str:
    """Add a new personal investment rule. Categories: buy, sell, risk, general.
    Example: 'Never chase a stock up more than 5% in a day' (category: buy)."""
    try:
        from diamond.data.rules import add_rule

        rule = add_rule(text, category)
        return _json({"added": rule, "message": f"Rule added to '{category}' category"})
    except Exception as e:
        return _json({"error": f"Add rule failed: {e}"})


@mcp.tool()
def remove_personal_rule(rule_id: str) -> str:
    """Remove a personal investment rule by its ID."""
    try:
        from diamond.data.rules import remove_rule

        success = remove_rule(rule_id)
        return _json({"removed": success, "rule_id": rule_id})
    except Exception as e:
        return _json({"error": f"Remove rule failed: {e}"})


@mcp.tool()
def check_rules_before_trade(action: str) -> str:
    """Check personal rules that apply to a buy or sell action.
    Returns matching rules as pre-trade reminders."""
    try:
        from diamond.data.rules import check_rules

        rules = check_rules(action)
        return _json({
            "action": action,
            "applicable_rules": rules,
            "count": len(rules),
        })
    except Exception as e:
        return _json({"error": f"Rules check failed: {e}"})


# ===========================================================================
# PORTFOLIO SNAPSHOT TOOLS
# ===========================================================================


@mcp.tool()
def portfolio_snapshot(name: str = "", strategy: str = "gods_plan", notes: str = "") -> str:
    """Save a snapshot of the current portfolio state. Auto-names as YYYY-MM-DD if no name given.
    Use to create checkpoints for later comparison."""
    try:
        from diamond.data.snapshots import save_snapshot
        from datetime import date

        if not name:
            name = date.today().isoformat()
        snapshot = save_snapshot(name, strategy, notes)
        return _json({
            "saved": True,
            "name": name,
            "nav": snapshot.get("nav"),
            "holdings_count": len(snapshot.get("holdings", {})),
            "message": f"Snapshot '{name}' saved successfully",
        })
    except Exception as e:
        return _json({"error": f"Snapshot save failed: {e}"})


@mcp.tool()
def list_snapshots() -> str:
    """List all saved portfolio snapshots with date, NAV, and stock count."""
    try:
        from diamond.data.snapshots import list_snapshots as _list

        snapshots = _list()
        return _json({"snapshots": snapshots, "count": len(snapshots)})
    except Exception as e:
        return _json({"error": f"List snapshots failed: {e}"})


@mcp.tool()
def portfolio_diff(name1: str, name2: str = "") -> str:
    """Compare two portfolio snapshots, or compare a snapshot to the current live portfolio.
    If name2 is empty, compares name1 to current portfolio.
    Shows added/removed stocks, weight changes, and NAV change."""
    try:
        from diamond.data.snapshots import diff_snapshots, diff_with_current

        if name2:
            diff = diff_snapshots(name1, name2)
        else:
            diff = diff_with_current(name1, "gods_plan")
        return _json(diff)
    except Exception as e:
        return _json({"error": f"Portfolio diff failed: {e}"})


# ===========================================================================
# LIQUIDITY CHECK TOOLS
# ===========================================================================


@mcp.tool()
def liquidity_check(ticker: str, trade_value: float = 50000) -> str:
    """Check stock liquidity before trading. Returns average daily volume,
    trade as % of ADV, safety verdict, and stagger suggestion if needed.
    Essential for trades > Rs 50,000 or small/mid-cap stocks."""
    try:
        from diamond.analysis.liquidity import check_liquidity

        if not ticker.endswith(".NS"):
            ticker = f"{ticker}.NS"
        result = check_liquidity(ticker, trade_value)
        return _json(result)
    except Exception as e:
        return _json({"error": f"Liquidity check failed: {e}"})


@mcp.tool()
def portfolio_liquidity(strategy: str = "gods_plan") -> str:
    """Check liquidity for all portfolio holdings. Flags any illiquid positions
    that would be hard to exit quickly."""
    try:
        from diamond.analysis.liquidity import check_portfolio_liquidity

        results = check_portfolio_liquidity(strategy)
        illiquid = [r for r in results if not r.get("safe", True)]
        return _json({
            "strategy": strategy,
            "holdings_checked": len(results),
            "illiquid_count": len(illiquid),
            "illiquid": illiquid,
            "all_results": results,
        })
    except Exception as e:
        return _json({"error": f"Portfolio liquidity check failed: {e}"})


# ===========================================================================
# INSIDER ACTIVITY TOOLS
# ===========================================================================


@mcp.tool()
def insider_activity(ticker: str) -> str:
    """Get insider/promoter trading activity for a stock. Shows recent transactions,
    promoter holding %, and net insider sentiment (buying/selling/neutral).
    Useful for detecting smart money signals."""
    try:
        from diamond.analysis.insider import get_insider_activity

        if not ticker.endswith(".NS"):
            ticker = f"{ticker}.NS"
        result = get_insider_activity(ticker)
        return _json(result)
    except Exception as e:
        return _json({"error": f"Insider activity failed: {e}"})


@mcp.tool()
def portfolio_insider_signals(strategy: str = "gods_plan") -> str:
    """Scan all portfolio holdings for insider activity signals.
    Flags stocks where insiders are net selling (bearish) or buying (bullish)."""
    try:
        from diamond.analysis.insider import get_portfolio_insider_signals

        signals = get_portfolio_insider_signals(strategy)
        bullish = [s for s in signals if s.get("net_insider_sentiment") == "buying"]
        bearish = [s for s in signals if s.get("net_insider_sentiment") == "selling"]
        return _json({
            "strategy": strategy,
            "stocks_scanned": len(signals),
            "insider_buying": bullish,
            "insider_selling": bearish,
            "all_signals": signals,
        })
    except Exception as e:
        return _json({"error": f"Portfolio insider scan failed: {e}"})


# ===========================================================================
# COST BREAKDOWN TOOLS
# ===========================================================================


@mcp.tool()
def cost_breakdown(strategy: str = "gods_plan") -> str:
    """Get a detailed breakdown of all transaction costs paid. Shows brokerage, STT,
    GST, exchange fees, SEBI charges, stamp duty, and slippage — total and per-trade.
    Compares to mutual fund expense ratios."""
    from diamond.data.ledger import Ledger
    from diamond.execution.costs import calculate_costs

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            trades = ledger.get_trades()
            if not trades:
                continue

            total_costs = {
                "brokerage": 0, "gst": 0, "stt": 0, "exchange_fees": 0,
                "sebi": 0, "stamp_duty": 0, "slippage": 0, "total": 0,
            }
            total_traded = 0

            for trade in trades:
                amount = abs(trade.shares * trade.price)
                total_traded += amount
                costs = calculate_costs(trade.action, amount)
                for key in total_costs:
                    if key in costs:
                        total_costs[key] += costs[key]

            initial = ledger.get_initial_capital()
            cost_pct = (total_costs["total"] / initial * 100) if initial > 0 else 0
            cost_per_trade = total_costs["total"] / len(trades) if trades else 0

            return _json({
                "strategy": s,
                "total_costs": {k: round(v, 2) for k, v in total_costs.items()},
                "total_traded_value": round(total_traded, 2),
                "trade_count": len(trades),
                "cost_as_pct_of_capital": round(cost_pct, 2),
                "cost_per_trade_avg": round(cost_per_trade, 2),
                "cost_per_rs_traded": round(total_costs["total"] / total_traded * 100, 4) if total_traded > 0 else 0,
                "vs_mutual_fund": f"Your cost: {cost_pct:.2f}% vs typical MF expense: 1.0-2.0%",
            })
        except Exception:
            continue
    return _json({"error": f"No trades found for strategy '{strategy}'"})


# ===========================================================================
# INDEX MEMBERSHIP TOOLS
# ===========================================================================


@mcp.tool()
def index_membership(ticker: str) -> str:
    """Check which major indices a stock belongs to (Nifty 50, Nifty Next 50, etc.).
    Useful for gauging passive fund flow impact."""
    from diamond.data.universe import get_nifty50, get_screening_universe

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    nifty50 = get_nifty50()
    universe = get_screening_universe()

    in_nifty50 = ticker in nifty50
    in_universe = ticker in universe

    result = {
        "ticker": ticker,
        "nifty_50": in_nifty50,
        "nse_500_universe": in_universe,
        "index_impact": "HIGH — Nifty 50 inclusion means significant passive fund tracking" if in_nifty50
            else "MODERATE — in NSE 500 screening universe" if in_universe
            else "LOW — not in major indices, limited passive flow",
    }
    return _json(result)


# ===========================================================================
# CASH POSITION TOOLS
# ===========================================================================


@mcp.tool()
def cash_position(strategy: str = "gods_plan") -> str:
    """Get detailed cash position analysis — amount, percentage, and whether it's
    too high (cash drag) or too low (no opportunity buffer). Includes deployment suggestion."""
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            cash = ledger.get_cash()
            prices = _get_current_prices(list(holdings.keys()))
            nav = ledger.get_portfolio_value(prices)
            cash_pct = (cash / nav * 100) if nav > 0 else 0

            if cash_pct > 15:
                status = "TOO_HIGH"
                suggestion = f"Deploy Rs {round(cash * 0.5):,} (50% of cash) to reduce cash drag"
            elif cash_pct < 3:
                status = "TOO_LOW"
                suggestion = "Consider trimming a winner to build cash buffer (target 5-10%)"
            else:
                status = "OPTIMAL"
                suggestion = "Cash level is healthy. No action needed."

            return _json({
                "strategy": s,
                "cash": round(cash, 2),
                "nav": round(nav, 2),
                "cash_pct": round(cash_pct, 2),
                "status": status,
                "ideal_range": "5-10%",
                "suggestion": suggestion,
            })
        except Exception:
            continue
    return _json({"error": f"No portfolio found for strategy '{strategy}'"})


# ===========================================================================
# PORTFOLIO NAV HISTORY TOOLS
# ===========================================================================


@mcp.tool()
def historical_nav(strategy: str = "gods_plan", days: int = 90) -> str:
    """Get portfolio NAV time series. Shows how portfolio value has changed over time.
    Useful for charting portfolio growth."""
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices
    import pandas as pd

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue
            tickers = list(holdings.keys())
            prices_df = download_prices(tickers, period_days=days, use_cache=True)
            if prices_df.empty:
                continue

            nav_series = []
            cash = ledger.get_cash()
            for date_idx in prices_df.index:
                day_nav = cash
                for ticker, shares in holdings.items():
                    if ticker in prices_df.columns:
                        price = prices_df.loc[date_idx, ticker]
                        if pd.notna(price):
                            day_nav += shares * float(price)
                nav_series.append({
                    "date": date_idx.isoformat() if hasattr(date_idx, "isoformat") else str(date_idx),
                    "nav": round(day_nav, 2),
                })

            if not nav_series:
                continue

            first_nav = nav_series[0]["nav"]
            last_nav = nav_series[-1]["nav"]
            peak_nav = max(n["nav"] for n in nav_series)
            trough_nav = min(n["nav"] for n in nav_series)

            return _json({
                "strategy": s,
                "period_days": days,
                "data_points": len(nav_series),
                "first_nav": first_nav,
                "last_nav": last_nav,
                "peak_nav": peak_nav,
                "trough_nav": trough_nav,
                "period_return_pct": round((last_nav - first_nav) / first_nav * 100, 2) if first_nav > 0 else 0,
                "max_drawdown_pct": round((trough_nav - peak_nav) / peak_nav * 100, 2) if peak_nav > 0 else 0,
                "nav_series": nav_series[-30:],  # Last 30 data points
            })
        except Exception:
            continue
    return _json({"error": f"No portfolio found for strategy '{strategy}'"})


# ===========================================================================
# CORRELATION CHECK TOOL
# ===========================================================================


@mcp.tool()
def correlation_check(ticker: str, strategy: str = "gods_plan") -> str:
    """Check how a proposed stock correlates with existing portfolio holdings.
    Use before buying to avoid hidden concentration from correlated stocks.
    Returns the most correlated holding and whether adding this stock is safe."""
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices
    import pandas as pd

    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            all_tickers = list(holdings.keys()) + [ticker]
            prices_df = download_prices(all_tickers, period_days=252, use_cache=True)
            if prices_df.empty or ticker not in prices_df.columns:
                continue

            returns_df = prices_df.pct_change().dropna()
            if ticker not in returns_df.columns:
                continue

            correlations = {}
            for held in holdings:
                if held in returns_df.columns and held != ticker:
                    corr = returns_df[ticker].corr(returns_df[held])
                    if pd.notna(corr):
                        correlations[held] = round(float(corr), 3)

            if not correlations:
                continue

            max_corr_ticker = max(correlations, key=correlations.get)
            max_corr = correlations[max_corr_ticker]
            avg_corr = round(sum(correlations.values()) / len(correlations), 3)

            if max_corr > 0.80:
                verdict = "HIGH_CORRELATION_RISK"
                message = f"{ticker} is highly correlated (r={max_corr}) with {max_corr_ticker}. Consider an alternative."
            elif max_corr > 0.60:
                verdict = "MODERATE_OVERLAP"
                message = f"Moderate correlation with {max_corr_ticker} (r={max_corr}). Proceed with awareness."
            else:
                verdict = "SAFE"
                message = f"Low correlation with existing holdings. Good diversification add."

            return _json({
                "ticker": ticker,
                "strategy": s,
                "most_correlated": {"ticker": max_corr_ticker, "correlation": max_corr},
                "avg_correlation": avg_corr,
                "all_correlations": correlations,
                "verdict": verdict,
                "message": message,
            })
        except Exception:
            continue
    return _json({"error": f"Could not compute correlations for {ticker}"})


# ===========================================================================
# DIVIDEND YIELD TOOL
# ===========================================================================


@mcp.tool()
def dividend_yield_portfolio(strategy: str = "gods_plan") -> str:
    """Calculate weighted portfolio dividend yield and projected annual dividend income.
    Uses trailing 12-month dividend data from yfinance."""
    import yfinance as yf
    from diamond.data.ledger import Ledger

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            prices = _get_current_prices(list(holdings.keys()))
            nav = ledger.get_portfolio_value(prices)
            total_annual_div = 0
            stock_yields = []

            for ticker, shares in holdings.items():
                try:
                    info = yf.Ticker(ticker).info
                    div_yield = info.get("dividendYield", 0) or 0
                    div_rate = info.get("dividendRate", 0) or 0
                    price = prices.get(ticker, 0)
                    value = shares * price
                    annual_div = shares * div_rate
                    total_annual_div += annual_div
                    stock_yields.append({
                        "ticker": ticker,
                        "dividend_yield_pct": round(div_yield * 100, 2),
                        "annual_dividend_per_share": round(div_rate, 2),
                        "annual_dividend_total": round(annual_div, 2),
                        "value": round(value, 2),
                    })
                except Exception:
                    stock_yields.append({"ticker": ticker, "dividend_yield_pct": 0, "error": "data unavailable"})

            portfolio_yield = (total_annual_div / nav * 100) if nav > 0 else 0
            stock_yields.sort(key=lambda x: x.get("dividend_yield_pct", 0), reverse=True)

            return _json({
                "strategy": s,
                "portfolio_dividend_yield_pct": round(portfolio_yield, 2),
                "projected_annual_income": round(total_annual_div, 2),
                "projected_monthly_income": round(total_annual_div / 12, 2),
                "top_yielders": stock_yields[:5],
                "all_stocks": stock_yields,
            })
        except Exception:
            continue
    return _json({"error": f"No portfolio found for strategy '{strategy}'"})


# ===========================================================================
# PORTFOLIO HEATMAP TOOL
# ===========================================================================


@mcp.tool()
def portfolio_heatmap(strategy: str = "gods_plan", period: str = "total") -> str:
    """Generate a text-based portfolio heatmap grouped by sector.
    Period: 'day', 'week', 'month', or 'total' (default).
    Returns stocks sorted by return within each sector."""
    from diamond.data.ledger import Ledger
    from diamond.data.market import download_prices
    from diamond.data.universe import get_sector

    period_days = {"day": 2, "week": 7, "month": 30, "total": 365}.get(period, 365)

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            tickers = list(holdings.keys())
            prices_df = download_prices(tickers, period_days=period_days, use_cache=True)
            prices = _get_current_prices(tickers)
            nav = ledger.get_portfolio_value(prices)

            sectors = {}
            for ticker, shares in holdings.items():
                sector = get_sector(ticker)
                current = prices.get(ticker, 0)
                value = shares * current

                if period == "total":
                    avg_price = ledger.get_avg_price(ticker)
                    ret = ((current - avg_price) / avg_price * 100) if avg_price > 0 else 0
                else:
                    series = prices_df[ticker].dropna() if ticker in prices_df.columns else None
                    if series is not None and len(series) >= 2:
                        start_price = float(series.iloc[0])
                        ret = ((current - start_price) / start_price * 100) if start_price > 0 else 0
                    else:
                        ret = 0

                if sector not in sectors:
                    sectors[sector] = {"stocks": [], "total_value": 0}
                sectors[sector]["stocks"].append({
                    "ticker": ticker,
                    "return_pct": round(ret, 2),
                    "value": round(value, 2),
                    "weight_pct": round(value / nav * 100, 2) if nav > 0 else 0,
                })
                sectors[sector]["total_value"] += value

            # Sort stocks within each sector by return
            for sector in sectors:
                sectors[sector]["stocks"].sort(key=lambda x: x["return_pct"], reverse=True)
                sectors[sector]["weight_pct"] = round(sectors[sector]["total_value"] / nav * 100, 2) if nav > 0 else 0

            # Sort sectors by weight
            sorted_sectors = dict(sorted(sectors.items(), key=lambda x: x[1]["total_value"], reverse=True))

            return _json({
                "strategy": s,
                "period": period,
                "nav": round(nav, 2),
                "sectors": sorted_sectors,
            })
        except Exception:
            continue
    return _json({"error": f"No portfolio found for strategy '{strategy}'"})


# ===========================================================================
# RUN
# ===========================================================================

if __name__ == "__main__":
    mcp.run()
