---
name: exit-strategy
description: Creates exit plans for portfolio holdings. Auto-activates when the user asks "when should I sell?", "exit plan", "target price for X", "what's my exit?", "take profit?", or discusses selling criteria and profit targets.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*), mcp__kite__*
---

# Exit Strategy — Position Exit Planner

## Trigger Conditions

Activate when:
- User asks about exit plans or target prices
- User asks "when should I sell X?"
- User wants to set take-profit levels
- Composing with gtt-manager for automated exits

## What To Do

1. **Current position** — use `portfolio_holdings` MCP tool
   - Entry price, current price, P&L
   - Holding period (STCG vs LTCG threshold)

2. **Technical levels** — use `analyze_stock` MCP tool
   - Support levels (stop-loss candidates)
   - Resistance levels (take-profit candidates)
   - RSI, trend direction

3. **Exit criteria framework:**
   - **Stop-loss**: typically 10-15% below entry or key support
   - **Trailing stop**: 15-20% below 52-week high
   - **Target price**: next resistance level or fundamental fair value
   - **Time-based**: review after 1 year (LTCG benefit)
   - **Quality drop**: if stock falls out of screener top quartile

4. **Tax-aware timing** — use `tax_report` MCP tool
   - Days until LTCG qualification (1 year holding)
   - If close to 1Y mark: suggest waiting for tax benefit
   - STCG rate: 20% vs LTCG rate: 12.5%

5. **Automated exits** — suggest GTT orders via Kite
   - Stop-loss GTT at support level
   - Take-profit GTT at resistance level
   - Trailing stop via manual periodic review

## Output Format

**Exit Plan for [TICKER]:**
| Level | Price | Action | Reason |
|-------|-------|--------|--------|
| Stop-loss | Rs X | SELL ALL | Below key support |
| Trailing stop | Rs X | SELL ALL | 15% below 52W high |
| Take profit (partial) | Rs X | SELL 50% | Resistance level |
| Take profit (full) | Rs X | SELL ALL | 2x target |

**Tax Note:** Holding since [date] — [STCG/LTCG]. Tax impact of selling now: Rs [X]
**Days to LTCG:** [N] days remaining

**Automate:** `Set GTT stop-loss at Rs [X]` and `GTT take-profit at Rs [Y]`
