Evaluate what to sell or trim. User input: $ARGUMENTS

1. Run `uv run diamond risk gods_plan` — risk metrics (VaR, drawdown, correlation)
2. Run `uv run diamond health gods_plan` — health alerts
3. Run `uv run diamond accumulate --review` — quality drop flags + stop-loss triggers
4. Run `uv run diamond tax gods_plan` — tax implications of selling

If the user named a specific stock in $ARGUMENTS (e.g., `/sell TCS`), focus the analysis on that stock — its weight, P&L, tax lot, and whether the data supports selling.

Based on the results, recommend:
- **Immediate sells**: Stocks hitting stop-loss or with CRITICAL risk signals
- **Trim candidates**: Overweight positions (>10%), high-correlation pairs
- **Quality drops**: Stocks flagged by --review that no longer meet quality criteria
- **Tax-smart ordering**: Which sells are most tax-efficient (short-term vs long-term gains)

For each sell recommendation:
- Ticker, current weight, reason
- Estimated tax impact
- What to do with freed cash (redeploy or hold)

If nothing needs selling, say "Portfolio is clean — no sells needed."

End with the execution command: `uv run diamond accumulate --swap` or `uv run diamond run gods_plan`.