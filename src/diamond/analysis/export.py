"""Portfolio export and report generation.

Generates reports in Markdown, CSV, and JSON formats.
No external dependencies beyond the standard library and the diamond package.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from diamond.config import get_config
from diamond.data import market
from diamond.data.ledger import Ledger
from diamond.data.universe import get_sector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    path: Path
    format: str  # "md", "csv", "json"
    report_type: str  # "summary", "holdings", "trades", "full"
    rows: int  # Number of data rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_output_dir(strategy: str) -> Path:
    """Return default output directory for a strategy's reports."""
    d = get_config().reports_dir / strategy
    d.mkdir(parents=True, exist_ok=True)
    return d


def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _detect_mode(strategy: str) -> str:
    """Detect if a strategy is paper or live based on the name suffix."""
    return "paper" if strategy.endswith("_paper") else "live"


def _fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices for a list of tickers. Returns {ticker: price}."""
    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            series = market.download_single(ticker, period_days=5)
            if len(series) > 0:
                prices[ticker] = float(series.iloc[-1])
        except Exception:
            logger.warning("Failed to fetch price for %s", ticker)
    return prices


def _resolve_prices(
    ledger: Ledger,
    current_prices: dict[str, float] | None,
) -> dict[str, float]:
    """Resolve current prices: use provided dict or fetch from market."""
    holdings = ledger.get_holdings()
    if current_prices is not None:
        return current_prices
    if not holdings:
        return {}
    return _fetch_current_prices(list(holdings.keys()))


def _build_holdings_data(
    ledger: Ledger,
    current_prices: dict[str, float],
) -> list[dict]:
    """Build a list of per-holding dicts for reports."""
    holdings = ledger.get_holdings()
    rows = []
    for ticker, shares in sorted(holdings.items()):
        avg_price = ledger.get_avg_price(ticker)
        cur_price = current_prices.get(ticker, 0.0)
        value = shares * cur_price
        cost_basis = shares * avg_price
        pnl_inr = value - cost_basis
        pnl_pct = (pnl_inr / cost_basis * 100) if cost_basis > 0 else 0.0
        sector = get_sector(ticker)
        rows.append(
            {
                "ticker": ticker,
                "sector": sector,
                "shares": shares,
                "avg_price": round(avg_price, 2),
                "current_price": round(cur_price, 2),
                "value": round(value, 2),
                "weight": 0.0,  # filled below
                "pnl_pct": round(pnl_pct, 2),
                "pnl_inr": round(pnl_inr, 2),
            }
        )

    total_value = sum(r["value"] for r in rows)
    if total_value > 0:
        for r in rows:
            r["weight"] = round(r["value"] / total_value * 100, 2)

    return rows


def _build_sector_allocation(holdings_data: list[dict]) -> dict[str, float]:
    """Aggregate sector weights from holdings data. Returns {sector: weight%}."""
    sectors: dict[str, float] = {}
    for row in holdings_data:
        sector = row["sector"]
        sectors[sector] = sectors.get(sector, 0.0) + row["weight"]
    return {k: round(v, 2) for k, v in sorted(sectors.items(), key=lambda x: -x[1])}


def _try_tax_report(strategy: str, current_prices: dict[str, float]) -> dict | None:
    """Try to compute a tax report; return dict summary or None."""
    try:
        from diamond.analysis.tax import compute_tax_report

        report = compute_tax_report(strategy, current_prices=current_prices)
        return {
            "fiscal_year": report.fiscal_year,
            "total_stcg": report.total_stcg,
            "total_ltcg": report.total_ltcg,
            "ltcg_exemption": report.ltcg_exemption,
            "taxable_ltcg": report.taxable_ltcg,
            "estimated_stcg_tax": report.estimated_stcg_tax,
            "estimated_ltcg_tax": report.estimated_ltcg_tax,
            "total_estimated_tax": report.total_estimated_tax,
            "total_dividends": report.total_dividends,
            "total_transaction_costs": report.total_transaction_costs,
        }
    except Exception:
        logger.debug("Tax report unavailable for %s", strategy)
        return None


def _try_risk_summary(strategy: str, current_prices: dict[str, float]) -> dict | None:
    """Try to compute a risk report; return dict summary or None."""
    try:
        from diamond.monitoring.risk import compute_risk_report

        report = compute_risk_report(strategy, current_prices)
        return {
            "drawdown_pct": report.drawdown_pct,
            "var_95": report.var_95,
            "var_99": report.var_99,
            "cvar_95": report.cvar_95,
            "beta": report.beta,
            "volatility_annual": report.volatility_annual,
            "max_correlation": report.max_correlation,
            "avg_correlation": report.avg_correlation,
            "signals": report.signals,
        }
    except Exception:
        logger.debug("Risk report unavailable for %s", strategy)
        return None


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------


def export_portfolio_summary(
    strategy: str,
    output_dir: Path | None = None,
    current_prices: dict[str, float] | None = None,
) -> ExportResult:
    """Generate markdown portfolio summary report."""
    out = output_dir or _default_output_dir(strategy)
    out.mkdir(parents=True, exist_ok=True)

    ledger = Ledger(strategy)
    prices = _resolve_prices(ledger, current_prices)
    holdings = ledger.get_holdings()
    cash = ledger.get_cash()
    initial_capital = ledger.get_initial_capital()
    nav = ledger.get_portfolio_value(prices)
    invested_value = sum(shares * prices.get(ticker, 0.0) for ticker, shares in holdings.items())
    total_return = ((nav - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0.0

    holdings_data = _build_holdings_data(ledger, prices)
    sector_alloc = _build_sector_allocation(holdings_data)
    trades = ledger.get_trades()
    recent_trades = trades[-20:] if trades else []

    mode = _detect_mode(strategy)
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = []
    lines.append(f"# Portfolio Report: {strategy}")
    lines.append("")
    lines.append(f"**Date:** {date_str}  ")
    lines.append(f"**Mode:** {mode}  ")
    lines.append(f"**Strategy:** {strategy}")
    lines.append("")

    # --- Summary ---
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Initial Capital | {initial_capital:,.2f} INR |")
    lines.append(f"| NAV | {nav:,.2f} INR |")
    lines.append(f"| Cash | {cash:,.2f} INR |")
    lines.append(f"| Invested Value | {invested_value:,.2f} INR |")
    lines.append(f"| Total Return | {total_return:+.2f}% |")
    lines.append(f"| Holdings Count | {len(holdings)} |")
    lines.append(f"| Total Trades | {len(trades)} |")
    lines.append("")

    # --- Holdings ---
    lines.append("## Holdings")
    lines.append("")
    if holdings_data:
        lines.append("| Ticker | Sector | Shares | Avg Price | Current Price | Value | Weight% | P&L% | P&L INR |")
        lines.append("|--------|--------|--------|-----------|---------------|-------|---------|-------|---------|")
        for h in holdings_data:
            lines.append(
                f"| {h['ticker']} | {h['sector']} | {h['shares']} "
                f"| {h['avg_price']:,.2f} | {h['current_price']:,.2f} "
                f"| {h['value']:,.2f} | {h['weight']:.1f} "
                f"| {h['pnl_pct']:+.2f} | {h['pnl_inr']:+,.2f} |"
            )
        total_pnl = sum(h["pnl_inr"] for h in holdings_data)
        lines.append(f"| **Total** | | | | | **{invested_value:,.2f}** | **100.0** | | **{total_pnl:+,.2f}** |")
    else:
        lines.append("_No holdings._")
    lines.append("")

    # --- Sector Allocation ---
    lines.append("## Sector Allocation")
    lines.append("")
    if sector_alloc:
        lines.append("| Sector | Weight% |")
        lines.append("|--------|---------|")
        for sector, weight in sector_alloc.items():
            lines.append(f"| {sector} | {weight:.1f} |")
    else:
        lines.append("_No sector data._")
    lines.append("")

    # --- Recent Trades ---
    lines.append("## Recent Trades")
    lines.append("")
    if recent_trades:
        lines.append("| Date | Action | Ticker | Shares | Price | Value | Cost |")
        lines.append("|------|--------|--------|--------|-------|-------|------|")
        for t in recent_trades:
            value = t.shares * t.price
            lines.append(
                f"| {t.timestamp[:10]} | {t.action} | {t.ticker} "
                f"| {t.shares} | {t.price:,.2f} | {value:,.2f} | {t.total_cost:,.2f} |"
            )
    else:
        lines.append("_No trades recorded._")
    lines.append("")

    # --- Risk Metrics ---
    risk = _try_risk_summary(strategy, prices)
    lines.append("## Risk Metrics")
    lines.append("")
    if risk:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Drawdown | {risk['drawdown_pct']:.2f}% |")
        lines.append(f"| VaR 95% | {risk['var_95']:,.2f} INR |")
        lines.append(f"| VaR 99% | {risk['var_99']:,.2f} INR |")
        lines.append(f"| CVaR 95% | {risk['cvar_95']:,.2f} INR |")
        lines.append(f"| Beta | {risk['beta']:.4f} |")
        lines.append(f"| Volatility (annual) | {risk['volatility_annual']:.2f}% |")
        if risk["signals"]:
            lines.append("")
            lines.append("**Signals:**")
            for s in risk["signals"]:
                lines.append(f"- {s}")
    else:
        lines.append("_Risk data unavailable._")
    lines.append("")

    # --- Tax Summary ---
    tax = _try_tax_report(strategy, prices)
    lines.append("## Tax Summary")
    lines.append("")
    if tax:
        lines.append(f"**Fiscal Year:** {tax['fiscal_year']}")
        lines.append("")
        lines.append("| Category | Amount |")
        lines.append("|----------|--------|")
        lines.append(f"| STCG (realized) | {tax['total_stcg']:+,.2f} INR |")
        lines.append(f"| LTCG (realized) | {tax['total_ltcg']:+,.2f} INR |")
        lines.append(f"| LTCG Exemption | {tax['ltcg_exemption']:,.2f} INR |")
        lines.append(f"| Taxable LTCG | {tax['taxable_ltcg']:,.2f} INR |")
        lines.append(f"| Est. STCG Tax | {tax['estimated_stcg_tax']:,.2f} INR |")
        lines.append(f"| Est. LTCG Tax | {tax['estimated_ltcg_tax']:,.2f} INR |")
        lines.append(f"| **Total Est. Tax** | **{tax['total_estimated_tax']:,.2f} INR** |")
        lines.append(f"| Dividends | {tax['total_dividends']:,.2f} INR |")
        lines.append(f"| Transaction Costs | {tax['total_transaction_costs']:,.2f} INR |")
    else:
        lines.append("_Tax data unavailable._")
    lines.append("")

    content = "\n".join(lines) + "\n"
    filename = f"{strategy}_summary_{_today_str()}.md"
    path = out / filename
    path.write_text(content, encoding="utf-8")

    return ExportResult(
        path=path,
        format="md",
        report_type="summary",
        rows=len(holdings_data),
    )


# ---------------------------------------------------------------------------
# Holdings CSV
# ---------------------------------------------------------------------------


def export_holdings_csv(
    strategy: str,
    output_dir: Path | None = None,
    current_prices: dict[str, float] | None = None,
) -> ExportResult:
    """Export current holdings to CSV."""
    out = output_dir or _default_output_dir(strategy)
    out.mkdir(parents=True, exist_ok=True)

    ledger = Ledger(strategy)
    prices = _resolve_prices(ledger, current_prices)
    holdings_data = _build_holdings_data(ledger, prices)

    filename = f"{strategy}_holdings_{_today_str()}.csv"
    path = out / filename

    fieldnames = [
        "ticker",
        "sector",
        "shares",
        "avg_price",
        "current_price",
        "value",
        "weight",
        "pnl_pct",
        "pnl_inr",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in holdings_data:
            writer.writerow(row)

        # Summary row
        if holdings_data:
            total_value = sum(r["value"] for r in holdings_data)
            total_pnl = sum(r["pnl_inr"] for r in holdings_data)
            writer.writerow(
                {
                    "ticker": "TOTAL",
                    "sector": "",
                    "shares": "",
                    "avg_price": "",
                    "current_price": "",
                    "value": round(total_value, 2),
                    "weight": 100.0,
                    "pnl_pct": "",
                    "pnl_inr": round(total_pnl, 2),
                }
            )

    return ExportResult(
        path=path,
        format="csv",
        report_type="holdings",
        rows=len(holdings_data),
    )


# ---------------------------------------------------------------------------
# Trades CSV
# ---------------------------------------------------------------------------


def export_trades_csv(
    strategy: str,
    output_dir: Path | None = None,
    since: str | None = None,
) -> ExportResult:
    """Export trade history to CSV."""
    out = output_dir or _default_output_dir(strategy)
    out.mkdir(parents=True, exist_ok=True)

    ledger = Ledger(strategy)
    trades = ledger.get_trades(since=since)

    filename = f"{strategy}_trades_{_today_str()}.csv"
    path = out / filename

    fieldnames = ["date", "action", "ticker", "shares", "price", "value", "cost", "rationale"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in trades:
            writer.writerow(
                {
                    "date": t.timestamp[:10],
                    "action": t.action,
                    "ticker": t.ticker,
                    "shares": t.shares,
                    "price": round(t.price, 2),
                    "value": round(t.shares * t.price, 2),
                    "cost": round(t.total_cost, 2),
                    "rationale": t.rationale,
                }
            )

    return ExportResult(
        path=path,
        format="csv",
        report_type="trades",
        rows=len(trades),
    )


# ---------------------------------------------------------------------------
# Full JSON export
# ---------------------------------------------------------------------------


def export_full_json(
    strategy: str,
    output_dir: Path | None = None,
    current_prices: dict[str, float] | None = None,
) -> ExportResult:
    """Export complete portfolio state as JSON."""
    out = output_dir or _default_output_dir(strategy)
    out.mkdir(parents=True, exist_ok=True)

    ledger = Ledger(strategy)
    prices = _resolve_prices(ledger, current_prices)
    holdings_data = _build_holdings_data(ledger, prices)
    trades = ledger.get_trades()

    cash = ledger.get_cash()
    initial_capital = ledger.get_initial_capital()
    nav = ledger.get_portfolio_value(prices)
    total_return = ((nav - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0.0

    trades_list = [
        {
            "date": t.timestamp[:10],
            "action": t.action,
            "ticker": t.ticker,
            "shares": t.shares,
            "price": round(t.price, 2),
            "value": round(t.shares * t.price, 2),
            "cost": round(t.total_cost, 2),
            "rationale": t.rationale,
        }
        for t in trades
    ]

    cfg = get_config()
    config_snapshot = {
        "initial_capital": cfg.risk.initial_capital,
        "max_position_weight": cfg.portfolio.max_position_weight,
        "max_stocks_per_sector": cfg.portfolio.max_stocks_per_sector,
        "rebalance_frequency_days": cfg.rebalance.rebalance_frequency_days,
        "stop_loss_threshold": cfg.risk.stop_loss_threshold,
    }

    tax = _try_tax_report(strategy, prices)
    risk = _try_risk_summary(strategy, prices)

    payload = {
        "strategy": strategy,
        "mode": _detect_mode(strategy),
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "initial_capital": initial_capital,
            "nav": round(nav, 2),
            "cash": round(cash, 2),
            "invested_value": round(nav - cash, 2),
            "total_return_pct": round(total_return, 2),
            "holdings_count": len(holdings_data),
            "total_trades": len(trades),
            "total_fees": round(ledger.get_total_fees(), 2),
        },
        "holdings": holdings_data,
        "sector_allocation": _build_sector_allocation(holdings_data),
        "trades": trades_list,
        "config": config_snapshot,
    }

    if risk is not None:
        payload["risk"] = risk
    if tax is not None:
        payload["tax"] = tax

    filename = f"{strategy}_full_{_today_str()}.json"
    path = out / filename
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return ExportResult(
        path=path,
        format="json",
        report_type="full",
        rows=len(holdings_data),
    )


# ---------------------------------------------------------------------------
# Export all
# ---------------------------------------------------------------------------


def export_all(
    strategy: str,
    output_dir: Path | None = None,
    current_prices: dict[str, float] | None = None,
) -> list[ExportResult]:
    """Generate all export formats at once."""
    results: list[ExportResult] = []
    results.append(export_portfolio_summary(strategy, output_dir, current_prices))
    results.append(export_holdings_csv(strategy, output_dir, current_prices))
    results.append(export_trades_csv(strategy, output_dir))
    results.append(export_full_json(strategy, output_dir, current_prices))
    return results
