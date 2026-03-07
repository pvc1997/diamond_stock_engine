Clean up portfolio issues. User input: $ARGUMENTS

Run these diagnostics first:
1. Run `uv run diamond alerts gods_plan` — find all issues
2. Run `uv run diamond health gods_plan` — health check

Then handle based on what's found:

**Delisted stocks:**
- Run `uv run diamond cleanup gods_plan` — write off delisted at price 0
- Show which stocks were cleaned up and the impact on NAV

**Overweight positions:**
- Run `uv run diamond trim gods_plan` — trim positions above 10% weight
- Show what would be sold and estimated proceeds

**Stop-loss breaches:**
- List stocks below stop-loss threshold (10% loss)
- Suggest: `uv run diamond sell gods_plan TICKER.NS` for each
- Flag tax implications (STCG vs LTCG)

If $ARGUMENTS contains "dry-run" or "preview":
- Run `uv run diamond cleanup gods_plan --dry-run` and `uv run diamond trim gods_plan --dry-run`
- Show what WOULD happen without executing

If $ARGUMENTS contains a strategy name, use that instead of gods_plan.

Present a before/after summary: holdings count, NAV impact, cash freed.