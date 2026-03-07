"""Run backtest for a single strategy and print results."""

import sys
import logging

logging.basicConfig(level=logging.WARNING)

strategy_name = sys.argv[1]
start_date = sys.argv[2] if len(sys.argv) > 2 else "2010-01-01"
end_date = sys.argv[3] if len(sys.argv) > 3 else "2025-01-01"
capital = float(sys.argv[4]) if len(sys.argv) > 4 else 100000

# Resolve strategy
if strategy_name == "baseline":
    from diamond.strategies.baseline import BaselineStrategy
    strat = BaselineStrategy()
elif strategy_name == "steady":
    from diamond.strategies.steady import SteadyStrategy
    strat = SteadyStrategy()
elif strategy_name == "gods_plan":
    from diamond.strategies.gods_plan import GodsPlanStrategy
    strat = GodsPlanStrategy()
else:
    print(f"Unknown strategy: {strategy_name}")
    sys.exit(1)

from diamond.backtest.engine import run_backtest
from diamond.backtest.reporter import compute_metrics, generate_report

print(f"Running {strategy_name} backtest: {start_date} to {end_date}, capital={capital:,.0f}")

result = run_backtest(
    strategy=strat,
    strategy_name=strategy_name,
    start_date=start_date,
    end_date=end_date,
    initial_capital=capital,
    window_months=6,
    step_months=6,
)

metrics = compute_metrics(result)
report_path = generate_report(result)

print(f"\n{'='*50}")
print(f"  Strategy:     {strategy_name}")
print(f"  Period:       {start_date} to {end_date}")
print(f"  Windows:      {len(result.windows)}")
print(f"  Total Return: {metrics['total_return_pct']:+.2f}%")
print(f"  CAGR:         {metrics['cagr']:+.2f}%")
print(f"  Sharpe:       {metrics['sharpe']:.3f}")
print(f"  Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
print(f"  Win Rate:     {metrics['win_rate_pct']:.1f}%")
print(f"  Trades:       {metrics['total_trades']}")
print(f"  Fees:         {metrics['total_fees']:,.2f} INR")
print(f"  Final NAV:    {result.final_nav:,.2f} INR")
print(f"{'='*50}")
print(f"Report: {report_path}")
