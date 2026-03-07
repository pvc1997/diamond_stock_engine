Quick risk snapshot. User input: $ARGUMENTS

1. Run `uv run diamond risk gods_plan` — full risk report
2. Run `uv run diamond health gods_plan` — health check alerts

Present a focused risk dashboard:
- **Drawdown**: Current vs HWM, distance to WARNING (10%) and CRITICAL (15%)
- **VaR**: 1-day 95% and 99% Value-at-Risk in INR
- **Beta**: Portfolio beta vs Nifty 50
- **Volatility**: Annualized, flag if >30%
- **Correlation**: Average pairwise, flag if >0.80
- **Top Risk Contributors**: 3 stocks adding most portfolio risk

If $ARGUMENTS contains a strategy name (e.g., `/risk steady`), use that instead of gods_plan.

End with risk verdict:
- GREEN: All metrics within limits
- YELLOW: 1-2 warnings, monitor closely
- RED: Critical signals present, action needed

Keep it concise — 15-20 lines max. For full portfolio context, suggest `/portfolio`.