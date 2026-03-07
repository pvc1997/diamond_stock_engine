---
name: sip-planner
description: Plans systematic monthly investment deployments. Auto-activates when the user mentions "SIP", "monthly investment", "systematic", "auto-invest", "every month", "regular investment", or discusses DCA strategy.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# SIP Planner — Systematic Investment Planner

## Trigger Conditions

Activate when:
- User mentions SIP, monthly investment, systematic investing
- User asks "how much should I invest monthly?"
- User wants to set up a regular deployment schedule
- User asks about DCA (dollar cost averaging)

## What To Do

1. **Determine monthly amount** — use `portfolio_status` MCP tool
   - If user specifies amount: use it
   - If not: suggest 10-20% of estimated monthly savings
   - Parse natural language amounts ("5k per month", "50 thousand monthly")

2. **Create deployment plan** — use `accumulate_opportunities` MCP tool
   - Get quality-ranked stocks
   - Allocate monthly SIP across top opportunities
   - Rules:
     - Min allocation per stock: Rs 2,000
     - Max stocks per month: 5 (focus over spray)
     - Prefer existing holdings for top-up (reduces stock count)
     - Rotate into new names only when existing are fully sized

3. **Market adjustment** — use `market_pulse` MCP tool
   - DEPLOY: invest full SIP amount
   - WAIT: invest 50% now, hold 50% in cash
   - DEFENSIVE: invest only 25%, rest in cash for next month

4. **Calendar** — show monthly deployment schedule
   - Best days: typically 1st-5th of month (salary credit timing)
   - Avoid: expiry weeks (last Thursday), budget day, RBI policy days

## Output Format

### Monthly SIP Plan — Rs [AMOUNT]/month

**This Month's Deployment:**
| Stock | Amount | Shares (~) | Type |
|-------|--------|-----------|------|
| RELIANCE.NS | Rs 10,000 | ~4 | Top-up |
| INFY.NS | Rs 8,000 | ~5 | New entry |

**Market Adjustment:** [DEPLOY/WAIT/DEFENSIVE] — deploying [X]% this month

**Annual Projection:**
- Total annual investment: Rs [12 * monthly]
- Expected portfolio value in 1Y: Rs [projected] (at [CAGR]% CAGR)
- Expected portfolio value in 5Y: Rs [projected]

To execute: `uv run diamond accumulate --deploy` or `/buy` for individual stocks
