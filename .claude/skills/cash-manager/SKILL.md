---
name: cash-manager
description: Manages portfolio cash allocation and deployment schedule. Auto-activates when the user asks "how much cash?", "deploy cash", "too much cash idle", "cash drag", "when to invest?", or discusses cash management strategy.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Cash Manager — Idle Cash Optimizer

## Trigger Conditions

Activate when:
- User asks about cash position
- User wants to deploy idle cash
- Cash > 15% of portfolio (cash drag alert)
- User adds fresh capital and asks how to deploy

## What To Do

1. **Cash position** — use `cash_position` MCP tool
   - Current cash amount and % of portfolio
   - Is this too high (> 15%)? Too low (< 3%)?

2. **Market adjustment** — use `market_pulse` MCP tool
   - DEPLOY: deploy up to 70% of excess cash
   - WAIT: deploy up to 30%
   - DEFENSIVE: hold cash, deploy only 10% into defensive names

3. **Deployment plan** — use `accumulate_opportunities` MCP tool
   - Rank opportunities by quality score
   - Allocate cash across top picks
   - Respect position limits (max 10% per stock)

4. **Cash guidelines:**
   - Ideal cash: 5-10% of portfolio (buffer for opportunities)
   - Too much cash (> 15%): generating cash drag, deploy gradually
   - Too little cash (< 3%): may miss opportunities, consider trimming winners

## Output Format

**Cash Position:**
- Available: Rs [X] ([Y]% of portfolio)
- Status: OPTIMAL / TOO HIGH / TOO LOW
- Market verdict: [DEPLOY/WAIT/DEFENSIVE]

**Deployment Recommendation:**
- Deploy now: Rs [X] ([Y]% of cash)
- Hold as buffer: Rs [X]
- Timeline: Immediate / Stagger over [N] weeks

**Where to Deploy:**
| Stock | Amount | Reason |
|-------|--------|--------|
| ... | Rs X | Top-up existing / New quality entry |

To execute: `uv run diamond accumulate --deploy`
