---
name: portfolio-overview
description: Shows a cross-strategy portfolio overview. Auto-activates when the user says "show all strategies", "all my portfolios", "overall status", "how are all my portfolios?", "strategy comparison", or asks for a bird's-eye view of everything.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Portfolio Overview — All Strategies at a Glance

## Trigger Conditions

Activate when:
- User asks "show all strategies", "all portfolios"
- User says "overall status", "big picture"
- User asks "how is everything?", "summary of all"
- User says "which strategy is winning?"

## What To Do

1. Run `uv run diamond status` or use `portfolio_status` MCP tool for each strategy
2. Check for: gods_plan, gods_plan_paper, steady, baseline, accumulate
3. For each active strategy, show: NAV, return, holdings count, last rebalance

## Output Format

**All Portfolios:**
| Strategy | Mode | NAV | Return | Stocks | Last Rebalance |
|----------|------|-----|--------|--------|----------------|
| gods_plan | Paper | Rs X | +Y% | 18 | 2026-03-06 |
| accumulate | Live | Rs X | +Y% | 12 | 2026-03-01 |
| steady | — | — | — | — | Never |

**Total Invested Capital:** Rs X
**Total NAV:** Rs X (+Y%)
**Best Performing:** [strategy] at +Z%

For details on any strategy: just say its name or use `/portfolio`.
