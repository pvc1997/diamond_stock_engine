Check if rebalancing is needed and preview the trades:

1. Run `uv run diamond health gods_plan` — check drift alerts
2. Run `uv run diamond risk gods_plan` — check risk signals
3. Run `uv run diamond run gods_plan --dry-run` — preview what trades would execute
4. Run `uv run diamond tax gods_plan` — tax impact of potential trades

Summarize:
- Is rebalance due? (last rebalance date vs 90-day cycle)
- Drift level — which positions drifted most?
- Proposed trades: sells first, then buys, with INR amounts
- Estimated transaction costs
- Tax implications of the sells
- Risk gate status (any CRITICAL signals blocking?)

If rebalance is needed, end with:
"Ready to execute? Run: `uv run diamond run gods_plan`"
"Or paper-test first: `uv run diamond paper gods_plan`"

If not due yet, say when the next rebalance window opens.
