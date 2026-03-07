Weekly portfolio review. Run all of these for a comprehensive weekly check-in:

1. Run `uv run diamond dashboard gods_plan` — full dashboard
2. Run `uv run diamond attribution gods_plan --period 1W` — this week's attribution
3. Run `uv run diamond risk gods_plan` — current risk metrics
4. Run `uv run diamond drift gods_plan` — drift from targets
5. Run `uv run diamond compare gods_plan baseline` — vs Nifty 50 benchmark
6. Run `uv run diamond health gods_plan` — health alerts

Present a structured weekly report:
- **Week Summary**: NAV change this week (INR + %), vs Nifty performance
- **Top Contributors**: Best and worst 3 stocks this week with attribution
- **Risk Check**: VaR, drawdown, beta — any changes from last week?
- **Drift Status**: Any positions beyond threshold?
- **Sector Rotation**: Which sectors led/lagged this week?
- **Action Items**: Rebalance needed? Sells triggered? Opportunities?
- **Next Week Outlook**: Based on momentum, RSI, VIX regime

End with: "For detailed export, use `/export gods_plan`"