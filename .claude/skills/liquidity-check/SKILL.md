---
name: liquidity-check
description: Checks stock liquidity before large trades. Auto-activates before any trade exceeding Rs 50,000, when the user mentions "volume", "liquidity", "illiquid", "can I sell this easily?", or when stagger entry is being considered.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Liquidity Check — Volume & Slippage Guard

## Trigger Conditions

Activate when:
- Any buy/sell trade > Rs 50,000
- User asks about volume, liquidity, or slippage
- User mentions "can I exit this easily?"
- Small/mid-cap stocks being considered (higher liquidity risk)

## What To Do

1. **Check volume** — use `liquidity_check` MCP tool
   - Average daily volume (ADV) over 3 months
   - Average daily value traded
   - Trade amount as % of ADV

2. **Assess impact:**
   - < 5% of ADV: SAFE — normal execution
   - 5-10% of ADV: CAUTION — may cause 0.5-1% slippage
   - 10-25% of ADV: STAGGER — split across 2-5 days
   - > 25% of ADV: AVOID — too illiquid for this trade size

3. **Stagger plan** if needed — use `stagger_entry` MCP tool
   - Calculate daily tranches
   - Suggest limit orders instead of market orders

## Output Format

**Liquidity Check for [TICKER]:**
- Avg Daily Volume: [X] shares ([Rs Y] value)
- Your trade: [Rs Z] = [P]% of daily value
- Verdict: SAFE / CAUTION / STAGGER / AVOID
- Estimated slippage: [X]%

If STAGGER:
| Day | Amount | Shares | Order Type |
|-----|--------|--------|------------|
| Day 1 | Rs X | ~N | LIMIT |
| Day 2 | Rs X | ~N | LIMIT |
