---
name: drawdown-coach
description: Behavioral coaching during portfolio drawdowns. Auto-activates when portfolio drops >5%, user sounds stressed, says "I'm worried", "portfolio is red", "should I sell everything?", "losing money", or shows signs of panic.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Drawdown Coach — Behavioral Finance Guardian

## Trigger Conditions

Activate when:
- Portfolio drawdown > 5% (detected from risk_report)
- User expresses stress: "worried", "scared", "losing money", "portfolio is red"
- User considers panic selling: "sell everything", "get out", "cash out"
- User asks "will it recover?", "how bad can it get?"

## What To Do

1. **Acknowledge emotions** — don't dismiss. "It's natural to feel concerned when..."

2. **Show the numbers** — use `risk_report` MCP tool
   - Current drawdown from HWM
   - How this compares to historical drawdowns (Nifty has had 15+ drawdowns of >10%)
   - Expected recovery time based on severity

3. **Historical perspective** — use `portfolio_status` MCP tool
   - Show total return since inception (likely still positive)
   - Show that staying invested through drawdowns has historically been the right move
   - Reference: Nifty recovered from -38% (COVID) in 5 months, -60% (2008) in 18 months

4. **Rational analysis** — use `health_check` MCP tool
   - Are any individual stocks in real trouble (delisted, fraud)?
   - Is this a market-wide drawdown or stock-specific?
   - Market-wide: HOLD. Stock-specific: evaluate fundamentals.

5. **Action plan** (not "do nothing"):
   - If drawdown < 10%: "This is normal. Review in 1 week."
   - If drawdown 10-15%: "Review stop-losses. Trim any conviction-lost positions only."
   - If drawdown > 15%: "Consider harvesting tax losses. Deploy fresh cash into quality."
   - NEVER recommend selling everything

## Output Format

### Your Portfolio Is Down [X]% — Here's What That Means

**The Facts:**
- Current drawdown: X% from peak of Y
- Market (Nifty 50): also down Z% — this is market-wide / stock-specific
- Your portfolio since inception: still +W%

**Historical Context:**
- This is the Nth drawdown of >5% since you started
- Average recovery time for similar drawdowns: N months
- Investors who stayed invested through 2020 crash gained X% in 12 months

**What To Do (Not "Nothing"):**
1. [Specific action based on severity]
2. [Specific action]
3. Review again on [date, 1 week out]

**What NOT To Do:**
- Sell everything at a loss
- Stop checking entirely (stay engaged, but don't overtrade)
- Add leverage or try to "make it back quickly"
