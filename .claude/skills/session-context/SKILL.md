---
name: session-context
description: Maintains conversational context across messages. Auto-activates when the user refers to "it", "that stock", "the same one", "this position", uses pronouns for stocks, or says "now buy/sell it" after discussing a ticker. Also activates when strategy is not specified — defaults intelligently.
user-invocable: false
allowed-tools: mcp__diamond__*, Read, Write, Grep
---

# Session Context — Conversational Memory

You maintain an implicit context of what the user is discussing. Track these across messages:

## What to Track

1. **Last ticker discussed**: When user mentions or analyzes a stock, remember it
2. **Last strategy discussed**: Default to gods_plan if not specified
3. **Last action intent**: Were they considering buying, selling, analyzing?
4. **Last amount mentioned**: If they said "50k" earlier, carry it forward
5. **Active comparison**: If they compared X vs Y, remember both

## Pronoun Resolution

When the user says:
- "Buy it" / "Sell it" / "Analyze it" → use last ticker discussed
- "That stock" / "The same one" → use last ticker discussed
- "Do it" / "Go ahead" / "Execute" → repeat last proposed action
- "The other one" → if comparing X vs Y, use the one NOT just discussed
- "Both" / "All of them" → apply to all tickers in active context

## Strategy Default Resolution

When strategy is not specified, resolve in this order:
1. If user mentioned a strategy in this conversation → use that
2. If only one strategy has holdings → use that
3. Default → gods_plan

## Ticker Format Normalization

When user mentions a stock name:
- Bare name (e.g., "RELIANCE") → append .NS → "RELIANCE.NS"
- Already suffixed ("RELIANCE.NS") → use as-is
- Common abbreviations: "Reliance" → "RELIANCE.NS", "TCS" → "TCS.NS"

## Implementation

Do NOT write to any files. Simply maintain this context in your conversation memory.
When another skill needs the current ticker or strategy, provide it from your tracked context.

## Example Flow

```
User: "How is TCS doing?"
→ Context: ticker=TCS.NS, intent=analyze

User: "What about INFY?"
→ Context: ticker=INFY.NS, prev_ticker=TCS.NS, intent=analyze

User: "Compare them"
→ Context: comparing TCS.NS vs INFY.NS → trigger peer-compare skill

User: "Buy the first one"
→ Context: ticker=TCS.NS, intent=buy → trigger trade-guard + position-sizer

User: "Actually, put 50k into the second one instead"
→ Context: ticker=INFY.NS, amount=50000, intent=buy
```