---
name: historical-replay
description: Simulates what-if historical entry scenarios. Auto-activates when the user says "what if I started in 2020?", "if I invested during COVID", "replay from march 2020", "what would have happened?", "hindsight", or asks about hypothetical past investments.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Historical Replay — "What If I Started Then?"

## Trigger Conditions

Activate when:
- User asks "what if I started in [date]?"
- User says "if I invested during COVID", "replay"
- User asks "what would have happened?", "hindsight"
- User mentions a past date with investing intent

## What To Do

1. Parse the date from the request (default: 2020-03-23, COVID bottom)
2. Use `run_backtest` MCP tool with strategy=gods_plan, start=parsed date
3. Use `portfolio_status` for current actual comparison
4. Present the hypothetical outcome

## Output Format

**If you started gods_plan on [DATE] with Rs 5,00,000...**

| Metric | Hypothetical | Nifty 50 |
|--------|-------------|----------|
| NAV Today | Rs X | Rs Y |
| CAGR | X% | Y% |
| Max Drawdown | -X% | -Y% |
| Total Return | +X% | +Y% |

**Key Insight:** The best time to invest was [date]. The second best time is today.

**What you would have survived:**
- COVID crash (-38%, recovered in 5 months)
- [Other major events in the period]

Keep it motivational but factual.
