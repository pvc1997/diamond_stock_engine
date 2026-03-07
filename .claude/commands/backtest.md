Run walk-forward backtest. User input: $ARGUMENTS

Parse $ARGUMENTS for:
- Strategy name (default: gods_plan)
- Start date (default: 2020-01-01)
- End date (default: today)
- Example: `/backtest steady 2015-01-01 2025-01-01`

Run `uv run diamond backtest <strategy> --start <start> --end <end>`

This takes time. After completion, present:
- **CAGR**: Annualized return
- **Sharpe Ratio**: Risk-adjusted performance
- **Max Drawdown**: Worst peak-to-trough decline
- **Win Rate**: Percentage of positive rebalance windows
- **vs Nifty**: How it compares to the baseline

If the user didn't specify dates, ask: "Want a specific date range? Default is 2020-01-01 to today."