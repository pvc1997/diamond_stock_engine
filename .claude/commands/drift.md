Quick portfolio drift check. User input: $ARGUMENTS

Default strategy: gods_plan. Override with $ARGUMENTS if provided.

1. Run `uv run diamond drift <strategy>` — check drift from target weights

Present:
- **Max Drift**: Which position drifted most and by how much
- **Threshold**: Is any position beyond the 5% rebalance trigger?
- **Action**: "Rebalance needed" or "Within tolerance — no action"
- If rebalance needed, show: `uv run diamond run <strategy> --dry-run` to preview trades