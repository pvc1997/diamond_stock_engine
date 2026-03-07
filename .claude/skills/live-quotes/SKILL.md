---
name: live-quotes
description: Fetches real-time market data from Zerodha Kite for live portfolio valuation and trading decisions. Auto-activates when the user asks for current price, live NAV, real-time data, intraday movement, or during any live trading session. Prefers Kite quotes over yfinance when a Kite session is active.
user-invocable: false
allowed-tools: mcp__kite__*, mcp__diamond__*
---

# Live Quotes — Real-Time Market Data via Zerodha

## When to Use Kite Quotes vs yfinance

| Scenario | Data Source | Why |
|----------|-----------|-----|
| Live trading session active | **Kite MCP** | Real-time, exchange-direct |
| Paper trading / backtesting | yfinance (Diamond MCP) | No Kite session needed |
| Market closed | yfinance (Diamond MCP) | Kite returns last close anyway |
| Intraday candles needed | **Kite MCP** | yfinance has 15-min delay |
| Historical daily data | yfinance (Diamond MCP) | Better for long-term analysis |

## Available Kite Quote Tools

### Quick Price Check
`mcp__kite__get_ltp` — just the last traded price
- Input: `instruments: ["NSE:RELIANCE", "NSE:TCS"]`
- Fastest, use for portfolio valuation

### Full Quote
`mcp__kite__get_quotes` — LTP + bid/ask + volume + OHLC + change
- Input: `instruments: ["NSE:RELIANCE"]`
- Use when user asks "how is RELIANCE doing right now?"

### OHLC Data
`mcp__kite__get_ohlc` — today's open, high, low, close
- Use for intraday range analysis

### Historical Candles
`mcp__kite__get_historical_data` — OHLC candles at various intervals
- Intervals: minute, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute, day, week, month
- Use for technical analysis, support/resistance calculation
- Input: instrument_token (get from search_instruments first), interval, from_date, to_date

## Instrument Format

Kite uses `EXCHANGE:SYMBOL` format:
- NSE equities: `NSE:RELIANCE`, `NSE:TCS`, `NSE:INFY`
- BSE equities: `BSE:RELIANCE`
- Indices: `NSE:NIFTY 50`, `NSE:NIFTY BANK`

Diamond uses `.NS` suffix: `RELIANCE.NS`

Conversion: strip `.NS`, prepend `NSE:` → `RELIANCE.NS` becomes `NSE:RELIANCE`

## Real-Time Portfolio Valuation

When user asks "what's my portfolio worth right now?":
1. Get holdings from `mcp__diamond__portfolio_holdings`
2. Convert tickers to Kite format
3. Batch fetch via `mcp__kite__get_ltp` (all tickers at once)
4. Calculate live NAV = sum(shares * LTP) + cash
5. Compare to last known NAV from Diamond

Show: "Live NAV: INR X,XX,XXX (up/down INR Y,YYY from last close)"

## Intraday Context

When discussing a stock during market hours:
- Show live price + day change + volume
- Show intraday high/low range
- Show where price is relative to the range (near high = caution, near low = opportunity)
- Bid-ask spread if relevant (wide spread = low liquidity)