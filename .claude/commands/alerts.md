Show and act on portfolio alerts. User input: $ARGUMENTS

1. Run `uv run diamond alerts gods_plan` — get all actionable alerts
2. Run `uv run diamond health gods_plan` — health check for context

Present alerts grouped by severity:
- **CRITICAL**: Stop-losses hit, delisted stocks, risk gate triggers
- **WARNING**: Concentration breaches, high drift, quality drops
- **INFO**: Approaching limits, watchlist triggers

For each alert, show:
- What's wrong (1 line)
- Recommended action (specific command to fix it)
- Risk of inaction (what happens if you ignore it)

If $ARGUMENTS contains "fix" or "act":
- Run `uv run diamond alerts gods_plan --act` to interactively resolve alerts
- For delisted stocks: suggest `uv run diamond cleanup gods_plan`
- For overweight: suggest `uv run diamond trim gods_plan`
- For stop-losses: suggest `/sell TICKER`

If no alerts: "All clear — portfolio is healthy. Next check recommended: tomorrow's /morning"