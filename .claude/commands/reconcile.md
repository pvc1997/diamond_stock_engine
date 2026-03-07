Reconcile ledger with Zerodha Kite holdings. User input: $ARGUMENTS

1. Run `uv run diamond reconcile gods_plan` — compare ledger vs broker

Present discrepancies clearly:
- **In ledger but not in Kite**: May be delisted or transferred out
- **In Kite but not in ledger**: May need to import or was bought outside Diamond
- **Quantity mismatch**: Flag exact difference per stock
- **Price mismatch**: Ledger avg cost vs Kite avg cost (minor differences expected)

For each discrepancy, suggest a fix:
- Missing from Kite: `uv run diamond cleanup gods_plan` if delisted
- Missing from ledger: `uv run diamond kite --import gods_plan -c <CAPITAL>`
- Quantity off: May indicate unrecorded corporate action — check `uv run diamond actions gods_plan`

If $ARGUMENTS contains a strategy name, use that instead of gods_plan.

Remind: Kite session must be active. If expired, run `/kite auth` first.
Suggest running this weekly to catch drift between ledger and broker.