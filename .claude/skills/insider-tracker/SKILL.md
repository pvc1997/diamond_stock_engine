---
name: insider-tracker
description: Tracks insider and promoter activity for portfolio stocks. Auto-activates when the user asks "insider buying?", "promoter holding", "bulk deals", "who's buying?", "institutional activity", or mentions insider trading signals.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*), mcp__kite__*
---

# Insider Tracker — Promoter & Institutional Activity Monitor

## Trigger Conditions

Activate when:
- User asks about insider/promoter buying or selling
- User asks "who's buying X?", "any bulk deals?"
- As part of stock research (composing with stock-research skill)
- User asks about institutional holdings

## What To Do

1. **Insider activity** — use `insider_activity` MCP tool
   - Recent insider transactions (buys/sells)
   - Net insider sentiment (buying/selling/neutral)
   - Promoter holding percentage

2. **Portfolio scan** — use `portfolio_insider_signals` MCP tool
   - Scan all holdings for insider activity
   - Flag stocks with promoter selling > 1%
   - Highlight stocks with promoter buying (bullish)

3. **Institutional holdings** — from analysis
   - FII/DII holding changes
   - Mutual fund holding changes

## Output Format

**Insider Activity for [TICKER]:**
- Promoter Holding: [X]% (change: [+/-Y]% in 3 months)
- Recent Insider Trades:
  | Date | Insider | Action | Shares | Value |
  |------|---------|--------|--------|-------|
  | ... | ... | BUY/SELL | ... | ... |
- Net Sentiment: BUYING / SELLING / NEUTRAL
- Signal: BULLISH (promoters buying) / BEARISH (promoters selling) / NEUTRAL

**Portfolio Insider Scan:**
- Promoter buying: [list of stocks] — positive signal
- Promoter selling: [list of stocks] — investigate further
- No change: [list of stocks]
