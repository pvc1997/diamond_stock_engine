Manage the accumulate (buy-only) portfolio. User input: $ARGUMENTS

Parse $ARGUMENTS:
- empty or "status": Run `uv run diamond accumulate --status` — show current holdings + cash
- "opportunities" or "scan": Run `uv run diamond accumulate --opportunities` — quality-ranked buy candidates
- "deploy": Run `uv run diamond accumulate --deploy --dry-run` first, then confirm before `uv run diamond accumulate --deploy`
- "add AMOUNT" or "cash AMOUNT": Run `uv run diamond accumulate --add-cash <AMOUNT>` — top up cash
- "review": Run `uv run diamond accumulate --review` — flag quality drops + stop-losses
- "swap": Run `uv run diamond accumulate --swap --dry-run` first, then confirm before executing

For "deploy" and "swap", ALWAYS show the dry-run preview first and ask for confirmation.

Present accumulate dashboard:
- **NAV**: Current value + total return
- **Cash**: Available for deployment
- **Holdings**: Count + top 3 by weight
- **Market Pulse**: Current verdict affects deployment sizing (DEPLOY=50%, WAIT=30%, DEFENSIVE=15%)
- **Next Action**: What to do based on current state

If no accumulate portfolio exists, suggest: `uv run diamond accumulate --capital 500000` to start.