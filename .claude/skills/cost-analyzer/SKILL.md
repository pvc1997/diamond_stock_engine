---
name: cost-analyzer
description: Analyzes transaction costs and trading expenses. Auto-activates when the user asks "how much have I paid in fees?", "trading costs", "brokerage charges", "cost of trading", "am I paying too much?", "STT charges", or discusses transaction expenses.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Cost Analyzer — Transaction Expense Tracker

## Trigger Conditions

Activate when:
- User asks "how much have I paid in fees?", "total costs?"
- User mentions "brokerage", "STT", "trading charges"
- User asks "am I paying too much?", "cost efficiency"
- User says "compare my costs to mutual funds"

## What To Do

1. Use `cost_breakdown` MCP tool
2. Show total costs, breakdown by type, cost per trade
3. Compare to mutual fund expense ratios
4. Show impact on returns

## Output Format

**Transaction Costs Summary:**
| Cost Type | Amount | % of Total |
|-----------|--------|------------|
| Brokerage | Rs X | Y% |
| STT | Rs X | Y% |
| GST | Rs X | Y% |
| Others | Rs X | Y% |
| **Total** | **Rs X** | — |

**Efficiency:** Rs X cost per Rs Y traded (Z%)
**vs Mutual Fund:** Your Z% vs typical MF 1-2% expense ratio
**Return Impact:** Costs reduced your CAGR by ~X bps
