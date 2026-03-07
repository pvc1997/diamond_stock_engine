Historical entry simulation. User input: $ARGUMENTS

Simulate what would have happened if the user started investing at a specific date.

Parse $ARGUMENTS for a date (e.g., "2020-03", "march 2020", "2022-01-01").
Default to 2020-03-23 (COVID bottom) if no date given.

1. Use `run_backtest` MCP tool with strategy=gods_plan, start_date=parsed date, end_date=today
2. Use `portfolio_status` MCP tool for current actual portfolio comparison

Present:
- "If you started gods_plan on [DATE] with Rs [capital]..."
- Hypothetical NAV today
- CAGR achieved
- Max drawdown experienced
- Comparison with Nifty 50 over same period
- Key insight: "The best time to invest was [date]. The second best time is today."

Keep it motivational but factual.