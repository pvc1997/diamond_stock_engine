---
name: investment-journal
description: Investment journal for recording and retrieving thesis notes, trade reflections, and investment reasoning. Activates when the user says "note that...", "remember that I...", "my thesis on X is...", "journal entry", "why did I buy X", "what was my reasoning", or wants to record/retrieve investment thoughts.
argument-hint: [ticker or note]
allowed-tools: mcp__diamond__*, Read, Write, Grep
---

# Investment Journal — Your Trading Diary

## What Gets Recorded

### Trade Thesis (per stock)
- Why you bought: "Undervalued after earnings miss, strong balance sheet"
- Conviction level: High / Medium / Low
- Exit criteria: "Sell if drops below 2500" or "Hold until P/B normalizes to 3x"
- Time horizon: "12-18 months"

### Trade Reflections (post-trade)
- "Sold TCS too early — should have held through the dip"
- "Good call on RELIANCE — thesis played out exactly"
- "TATATECH was a mistake — overpaid at IPO hype"

### Market Observations
- "Market feels toppy — VIX rising, breadth narrowing"
- "Financials rotating in — watch HDFCBANK for entry"

### Personal Rules
- "Never buy on IPO listing day"
- "Always paper trade for 30 days first"
- "Don't add to losers unless thesis is intact"

## Storage

Store journal in `data/journal.json`:
```json
{
  "entries": [
    {
      "date": "2026-03-07",
      "type": "thesis",
      "ticker": "TCS.NS",
      "content": "Strong IT recovery play, AI tailwinds, attractive after 30% correction",
      "conviction": "high",
      "exit_criteria": "Sell if drops below 2200 or P/E exceeds 35"
    },
    {
      "date": "2026-03-07",
      "type": "reflection",
      "ticker": "TATATECH.NS",
      "content": "Lesson: avoid IPO hype. Should have waited 6 months for price discovery."
    },
    {
      "date": "2026-03-07",
      "type": "observation",
      "content": "Market breadth collapsed to 36% — staying cautious, WAIT mode."
    }
  ]
}
```

## Recording (when user wants to save a note)

Parse the user's message:
1. Detect ticker if mentioned
2. Classify type: thesis / reflection / observation / rule
3. Extract key content
4. Write to journal file
5. Confirm: "Noted. Your thesis on TCS: 'Strong IT recovery play...'. Tagged as high conviction."

## Retrieval (when user asks about past reasoning)

- "Why did I buy TCS?" → search journal for TCS.NS thesis entries
- "My notes on financials" → search for sector-related entries
- "What lessons have I learned?" → show all reflection entries
- "My journal" / "recent notes" → show last 10 entries
- "My rules" → show all rule entries

## Integration with Other Skills

When `stock-research` or `trade-guard` activates for a stock that has journal entries:
- Surface the stored thesis: "Your thesis on TCS (recorded Mar 7): 'Strong IT recovery play...'"
- Check if exit criteria are met: "Your exit trigger was price below 2200 — currently at 2557. Not triggered."
- Show conviction level: "You rated this HIGH conviction on entry."

When `explain-trade` activates:
- Include journal entries alongside system-generated rationale
- Show reflections if the trade was reviewed later