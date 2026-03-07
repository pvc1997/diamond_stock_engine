---
name: ticker-resolver
description: Resolves ambiguous stock names to exact NSE tickers. Auto-activates when the user mentions a stock name that could match multiple tickers (e.g., "HDFC", "Bajaj", "Tata"), uses a company name instead of ticker symbol, or misspells a ticker.
user-invocable: false
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Ticker Resolver — Smart Stock Name Matching

## When This Activates

- User says "HDFC" (could be HDFCBANK.NS, HDFCLIFE.NS, HDFCAMC.NS)
- User says "Bajaj" (could be BAJFINANCE.NS, BAJAJFINSV.NS, BAJAJ-AUTO.NS)
- User says "Tata" (could be TCS.NS, TATAMOTORS.NS, TATASTEEL.NS, TATAPOWER.NS, etc.)
- User misspells: "RELIACE" → suggest "RELIANCE.NS"
- User uses full name: "Infosys" → "INFY.NS"

## Resolution Strategy

### Step 1: Exact Match
If the input exactly matches an NSE 500 ticker (with or without .NS), use it directly.

### Step 2: Common Aliases
Known mappings (check these first):
- "Reliance" → RELIANCE.NS
- "Infosys" / "Infy" → INFY.NS
- "TCS" / "Tata Consultancy" → TCS.NS
- "HDFC Bank" → HDFCBANK.NS
- "ICICI Bank" → ICICIBANK.NS
- "Bajaj Finance" → BAJFINANCE.NS
- "Bajaj Auto" → BAJAJ-AUTO.NS
- "SBI" / "State Bank" → SBIN.NS
- "Kotak" / "Kotak Bank" → KOTAKBANK.NS
- "L&T" / "Larsen" → LT.NS
- "M&M" / "Mahindra" → M&M.NS
- "Maruti" → MARUTI.NS
- "Axis" / "Axis Bank" → AXISBANK.NS
- "ITC" → ITC.NS
- "HUL" / "Hindustan Unilever" → HINDUNILVR.NS
- "Asian Paints" → ASIANPAINT.NS
- "Titan" → TITAN.NS
- "Sun Pharma" → SUNPHARMA.NS

### Step 3: Prefix Match
Search NSE 500 universe for tickers starting with the input.
If multiple matches: present them and ask user to pick.

### Step 4: Fuzzy Match
If no prefix match, try:
- Levenshtein distance ≤ 2 from known tickers
- Substring match in company names

## Disambiguation Format

When multiple matches found:
"Did you mean:
1. HDFCBANK.NS — HDFC Bank (Financial Services)
2. HDFCLIFE.NS — HDFC Life Insurance (Insurance)
3. HDFCAMC.NS — HDFC AMC (Asset Management)

Which one? (enter number or full ticker)"

## Context Awareness

- If the user is discussing banking stocks, prefer HDFCBANK.NS over HDFCLIFE.NS
- If the user's portfolio holds one of the options, mention: "(you hold this)"
- If one match is in Nifty 50 and others aren't, prefer the Nifty 50 member