View and manage orders. User input: $ARGUMENTS

Default strategy: gods_plan.

1. Run `uv run diamond orders <strategy>` — show order book

Parse $ARGUMENTS:
- If empty or strategy name: show all orders
- If "cancel ORDER_ID": cancel a specific order
- If "cancel all": cancel all pending orders

Present:
- Pending orders with status, type, and age
- Filled orders from today
- Any failed/rejected orders with reason

If there are stale pending orders (>1 day old), flag them for cleanup.