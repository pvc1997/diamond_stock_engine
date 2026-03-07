Capital gains tax report. User input: $ARGUMENTS

Default strategy is gods_plan. If $ARGUMENTS specifies a different strategy, use that.

1. Run `uv run diamond tax <strategy>` — FIFO lot matching, STCG/LTCG breakdown

Present clearly:
- **Realized Gains**: Short-term (STCG at 20%) vs Long-term (LTCG at 12.5%, exempt up to 1.25L)
- **Unrealized Gains**: Current holdings with holding period and projected tax treatment
- **Tax-Loss Harvesting**: Any positions with unrealized losses that could offset gains
- **Estimated Tax Liability**: Total estimated tax on realized gains

If approaching financial year end (Jan-Mar), flag:
- "Consider harvesting losses before March 31 to offset STCG"
- Specific stocks that are candidates for tax-loss harvesting