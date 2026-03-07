---
name: income-tracker
description: Tracks all investment income — dividends, realized gains, and projected yield. Auto-activates when the user asks "how much income?", "dividend income", "what have I earned?", "realized gains", "portfolio yield", "passive income from stocks", or discusses investment returns as income.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Income Tracker — Investment Income Report

## Trigger Conditions

Activate when:
- User asks "how much income?", "what have I earned?"
- User mentions "dividend income", "passive income"
- User asks "portfolio yield", "realized gains"
- User says "income from my stocks", "total earnings"

## What To Do

1. Use `tax_report` MCP tool — realized gains (STCG + LTCG)
2. Use `corporate_actions` MCP tool — dividend history
3. Use `dividend_yield_portfolio` MCP tool — projected income
4. Use `portfolio_status` MCP tool — unrealized gains

## Output Format

**Investment Income Report:**

| Source | Amount | Notes |
|--------|--------|-------|
| Realized Gains | Rs X | STCG: Rs Y, LTCG: Rs Z |
| Dividends Received | Rs X | From N stocks |
| Unrealized Gains | Rs X | Paper profit in portfolio |
| **Total Return** | **Rs X** | Realized + unrealized + dividends |

**Projected Annual Income:**
- Dividend yield: X% (Rs Y/year, Rs Z/month)
- Top yielders: [top 3 dividend stocks]

**Tax Liability:** Rs X on realized gains
