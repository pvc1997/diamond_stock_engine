"""Backtest performance reporter.

Computes aggregate metrics from backtest results and generates markdown reports.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from diamond.backtest.engine import BacktestResult
from diamond.config import get_config
from diamond.monitoring.metrics import log_backtest_complete

logger = logging.getLogger(__name__)


def compute_metrics(result: BacktestResult) -> dict:
    """Compute aggregate performance metrics from backtest results.

    Returns dict with: total_return_pct, cagr, sharpe, max_drawdown,
    win_rate, total_trades, total_fees, volatility.
    """
    initial = result.initial_capital
    final = result.final_nav

    # Total return
    total_return_pct = (final / initial - 1) * 100 if initial > 0 else 0.0

    # CAGR
    start_dt = datetime.strptime(result.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(result.end_date, "%Y-%m-%d")
    years = (end_dt - start_dt).days / 365.25
    if years > 0 and final > 0 and initial > 0:
        cagr = (final / initial) ** (1 / years) - 1
    else:
        cagr = 0.0

    # Max drawdown from NAV history
    nav_values = [nav for _, nav in result.nav_history]
    max_drawdown = 0.0
    if nav_values:
        peak = nav_values[0]
        for nav in nav_values:
            if nav > peak:
                peak = nav
            dd = (peak - nav) / peak if peak > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd

    # Daily returns for Sharpe and volatility
    sharpe = 0.0
    volatility = 0.0
    if len(nav_values) > 10:
        arr = np.array(nav_values, dtype=float)
        daily_returns = np.diff(arr) / arr[:-1]
        daily_returns = daily_returns[np.isfinite(daily_returns)]
        if len(daily_returns) > 5:
            rf_daily = get_config().screener.risk_free_rate / 252
            mean_ret = float(np.mean(daily_returns))
            std_ret = float(np.std(daily_returns))
            volatility = std_ret * np.sqrt(252)
            if std_ret > 1e-10:
                sharpe = (mean_ret - rf_daily) / std_ret * np.sqrt(252)

    # Win rate (windows with positive returns)
    wins = sum(1 for w in result.windows if w.return_pct > 0)
    total_windows = len(result.windows)
    win_rate = wins / total_windows * 100 if total_windows > 0 else 0.0

    # Aggregate trades and fees
    total_trades = sum(w.num_trades for w in result.windows)
    total_fees = sum(w.total_fees for w in result.windows)

    # Benchmark metrics (if available)
    bench_return_pct = 0.0
    bench_cagr = 0.0
    if result.benchmark_nav and len(result.benchmark_nav) >= 2:
        bench_start = result.benchmark_nav[0][1]
        bench_end = result.benchmark_nav[-1][1]
        if bench_start > 0:
            bench_return_pct = round((bench_end / bench_start - 1) * 100, 2)
            if years > 0:
                bench_cagr = round(((bench_end / bench_start) ** (1 / years) - 1) * 100, 2)

    excess_return = round(total_return_pct - bench_return_pct, 2) if bench_return_pct else 0.0

    return {
        "total_return_pct": round(total_return_pct, 2),
        "cagr": round(cagr * 100, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "volatility_pct": round(volatility * 100, 2),
        "win_rate_pct": round(win_rate, 1),
        "total_trades": total_trades,
        "total_fees": round(total_fees, 2),
        "total_windows": total_windows,
        "years": round(years, 2),
        "initial_capital": result.initial_capital,
        "final_nav": round(result.final_nav, 2),
        "benchmark_return_pct": bench_return_pct,
        "benchmark_cagr": bench_cagr,
        "excess_return_pct": excess_return,
        "survivorship_filtered": result.survivorship_filtered,
    }


def generate_report(result: BacktestResult, output_dir: Path | None = None) -> Path:
    """Generate markdown backtest report and save JSON results.

    Args:
        result: BacktestResult from engine.run_backtest().
        output_dir: Directory for output files. Defaults to reports/backtest/{strategy}.

    Returns:
        Path to the generated markdown report.
    """
    cfg = get_config()
    if output_dir is None:
        output_dir = cfg.reports_dir / "backtest" / result.strategy
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = compute_metrics(result)

    # --- Save JSON results ---
    json_data = {
        "strategy": result.strategy,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "metrics": metrics,
        "windows": [
            {
                "id": w.window_id,
                "start": w.start,
                "end": w.end,
                "return_pct": w.return_pct,
                "num_trades": w.num_trades,
                "total_fees": w.total_fees,
                "holdings": w.holdings_count,
            }
            for w in result.windows
        ],
    }

    json_path = output_dir / "backtest_results.json"
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)

    # --- Generate markdown report ---
    m = metrics
    lines = [
        f"# Backtest Report: {result.strategy.upper()}",
        "",
        f"**Period:** {result.start_date} to {result.end_date} ({m['years']:.1f} years)",
        f"**Initial Capital:** {m['initial_capital']:,.0f} INR",
        f"**Final NAV:** {m['final_nav']:,.0f} INR",
        "",
        "## Performance Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Return | {m['total_return_pct']:+.2f}% |",
        f"| CAGR | {m['cagr']:+.2f}% |",
        f"| Sharpe Ratio | {m['sharpe']:.3f} |",
        f"| Max Drawdown | {m['max_drawdown_pct']:.2f}% |",
        f"| Volatility (ann.) | {m['volatility_pct']:.2f}% |",
        f"| Win Rate | {m['win_rate_pct']:.1f}% "
        f"({sum(1 for w in result.windows if w.return_pct > 0)}/{m['total_windows']} windows) |",
        f"| Total Trades | {m['total_trades']} |",
        f"| Total Fees | {m['total_fees']:,.2f} INR |",
        f"| Benchmark Return | {m['benchmark_return_pct']:+.2f}% |",
        f"| Benchmark CAGR | {m['benchmark_cagr']:+.2f}% |",
        f"| **Excess Return** | **{m['excess_return_pct']:+.2f}%** |",
        f"| Survivorship Filtered | {m['survivorship_filtered']} tickers |",
        "",
        "## Window Results",
        "",
        "| # | Period | Return | Trades | Fees | Holdings |",
        "|---|--------|--------|--------|------|----------|",
    ]

    for w in result.windows:
        lines.append(
            f"| {w.window_id} | {w.start} → {w.end} | {w.return_pct:+.2f}% | "
            f"{w.num_trades} | {w.total_fees:,.0f} | {w.holdings_count} |"
        )

    lines.extend(
        [
            "",
            f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        ]
    )

    md_path = output_dir / "Backtest_Report.md"
    md_path.write_text("\n".join(lines))

    logger.info(f"Report saved to {md_path}")
    logger.info(f"JSON results saved to {json_path}")

    log_backtest_complete(
        strategy=result.strategy,
        start=result.start_date,
        end=result.end_date,
        cagr=metrics["cagr"],
        sharpe=metrics["sharpe"],
        max_drawdown=metrics["max_drawdown_pct"],
        total_return=metrics["total_return_pct"],
    )

    return md_path
