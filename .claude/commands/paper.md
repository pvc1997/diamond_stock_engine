Paper trading management. User input: $ARGUMENTS

Parse $ARGUMENTS:
- empty or "status": Run `uv run diamond paper gods_plan --status` — show paper portfolio
- "start" or "init": Run `uv run diamond paper gods_plan --capital 500000` — start new paper portfolio
- "reset": Run `uv run diamond paper gods_plan --reset` — reset paper portfolio (CONFIRM first)
- "promote" or "assess": Run `uv run diamond promote gods_plan` — assess readiness for live trading
- "go-live" or "execute": Run `uv run diamond promote gods_plan --execute` — promote to live (CONFIRM first)
- "run" or "rebalance": Run `uv run diamond paper gods_plan` — run paper rebalance

For "reset" and "go-live", ALWAYS ask for explicit confirmation before executing.

Present paper trading dashboard:
- **NAV**: Current paper value + return since start
- **Holdings**: Stock count, top 3 by weight
- **Track Record**: Days active, trades executed, win rate
- **vs Live**: How paper compares to live portfolio (if both exist)
- **Promotion Readiness**: 30+ days? Positive returns? Outperforming baseline?

If no paper portfolio exists, suggest starting one:
"Start with: `uv run diamond paper gods_plan --capital 500000`
Paper trade for 30 days before going live. This is the safe way to validate strategy changes."