---
name: market-context
description: Provides market awareness for any investing conversation. Auto-activates when the user asks about market timing, "is it a good time?", "how's the market?", "should I invest now?", "market crash", "market rally", or any question about current market conditions.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Market Context — Always-On Market Awareness

## Data Gathering (run in parallel)

1. `market_pulse` — verdict, Nifty, VIX, breadth, RSI, trend
2. `today_briefing` — full daily snapshot with sector rotation

## Market Regime Interpretation

### DEPLOY (score > 0)
- Nifty above 200 DMA, breadth > 50%, RSI 40-60
- "Market is healthy. Deploy up to 50% of available cash."
- Highlight sectors showing relative strength

### WAIT (score = 0)
- Sideways trend, mixed signals, breadth 30-50%
- "No clear edge. Hold current positions, wait for clarity."
- Note what would flip the signal (e.g., "Breadth needs to cross 50%")

### DEFENSIVE (score < 0)
- Below 200 DMA, VIX elevated, breadth < 30%, RSI < 30 or > 70
- "Market is stressed. Raise cash, trim laggards, no new entries."
- Show how much portfolio would lose in a further 10% drop

## Context for Timing Questions

When user asks "is it a good time?":
1. Show the verdict with key metrics
2. Compare to historical regime (where are we in the cycle?)
3. Show what your portfolio would need (any cash to deploy? drift to fix?)
4. Give a clear YES/NO/WAIT with conditions for changing the answer

## VIX Interpretation
- VIX < 15: Low fear, complacency risk, good for steady deployment
- VIX 15-20: Normal, healthy conditions
- VIX 20-30: Elevated uncertainty, reduce position sizes
- VIX > 30: Fear spike, historically a buying opportunity (contrarian)

Always end with: the single most relevant action given current conditions.