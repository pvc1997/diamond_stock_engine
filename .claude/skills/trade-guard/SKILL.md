---
name: trade-guard
description: Safety gate that activates before any buy or sell action. Use when the user wants to execute a trade, place an order, deploy capital, or rebalance. Ensures market conditions, risk levels, and portfolio constraints are checked before proceeding.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Trade Guard — Pre-Trade Safety Check

This skill MUST activate before any trade execution. It is the last line of defense.

## Trigger Conditions

Activate when the user:
- Asks to buy or sell any stock
- Wants to deploy cash or rebalance
- Says "execute", "place order", "go ahead", "do it"
- Runs /buy, /sell, /rebalance with intent to execute (not just preview)

## Pre-Trade Checklist (run in parallel)

1. **Market Pulse** — use `market_pulse` MCP tool
   - If verdict is DEFENSIVE: BLOCK the trade. Explain why.
   - If verdict is WAIT: WARN and reduce sizing to 30% of requested amount
   - If verdict is DEPLOY: Proceed with full sizing

2. **Risk Report** — use `risk_report` MCP tool
   - If any CRITICAL signals: BLOCK unless user explicitly says --force
   - If drawdown > 10%: WARN about catching a falling knife

3. **Portfolio Status** — use `portfolio_status` MCP tool
   - Check cash available (can we afford this trade?)
   - Check position count (are we at max 18 stocks?)

4. **For BUY trades** — use `analyze_stock` MCP tool on the ticker
   - Position weight after buy must stay < 10%
   - Sector weight after buy must stay < 25% (use `sector_exposure`)
   - Check if stock is already held (top-up vs new entry)

5. **For SELL trades** — use `tax_report` MCP tool
   - Flag STCG vs LTCG impact
   - Suggest tax-loss harvesting if applicable
   - Check if this is a stop-loss sell (different urgency)

## Output Format

Present a traffic light:
- GREEN: All checks pass. "Safe to proceed. Command: `uv run diamond buy/sell ...`"
- YELLOW: Warnings present. Show each warning. Ask: "Proceed anyway?"
- RED: Critical block. Explain what must be resolved first.

Never silently let a trade through. Always show the checklist result.