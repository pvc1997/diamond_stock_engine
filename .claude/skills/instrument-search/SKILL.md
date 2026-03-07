---
name: instrument-search
description: Searches for tradeable instruments on Zerodha using the Kite MCP server. Enhances the ticker-resolver skill with real broker data. Activates when a stock cannot be found in the NSE 500 universe, when the user asks about IPOs, newly listed stocks, or any instrument not in Diamond's hardcoded universe.
user-invocable: false
allowed-tools: mcp__kite__*, mcp__diamond__*
---

# Instrument Search — Find Any Tradeable Stock

## When This Activates

- `ticker-resolver` skill can't find a match in NSE 500
- User mentions a recently listed stock (IPO)
- User asks about a stock that's on BSE but not NSE
- User mentions F&O instruments, indices, or commodities
- User says "is X listed?", "can I buy X?", "find X on Zerodha"

## Process

### Step 1: Search via Kite

Use `mcp__kite__search_instruments` with the user's query:
- Input: query string (company name, ticker, partial match)
- Returns: list of matching instruments with exchange, symbol, token, type

### Step 2: Filter Results

From the search results:
- **Prefer NSE over BSE** (higher liquidity for most stocks)
- **Filter to EQ segment** (equity, not F&O/derivatives)
- **Show instrument token** (needed for historical data and GTT)

### Step 3: Present Options

"Found these matches for 'Zomato':
1. NSE:ZOMATO (Zomato Ltd) — Equity, Token: 5097729
2. BSE:ZOMATO (Zomato Ltd) — Equity, Token: 5098241

Recommend: NSE:ZOMATO (higher liquidity)"

### Step 4: Provide Context

For the selected instrument:
- Fetch live price via `mcp__kite__get_ltp`
- Check if it's in Diamond's NSE 500 universe
- If NOT in universe: "This stock is not in Diamond's screening universe. You can still buy it manually, but it won't be picked up by strategy screens."

## Integration Points

- **ticker-resolver skill**: Falls back to this when NSE 500 lookup fails
- **stock-research skill**: Uses instrument_token for historical data via Kite
- **gtt-manager skill**: Needs instrument_token for GTT placement
- **live-quotes skill**: Needs exchange:symbol format for quotes

## Limitations

- Kite search may return F&O instruments — always filter to equity segment
- Newly listed stocks (< 30 days) may not have enough history for Diamond's screener
- Stocks outside NSE 500 won't get quality scores from Diamond's screener — warn the user