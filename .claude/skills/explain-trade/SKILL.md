---
name: explain-trade
description: Explains why a trade was made or recommended. Use when the user asks "why did we buy/sell X?", "what's the rationale?", "why is X in the portfolio?", "when did we buy X?", or wants to understand any past or proposed trade.
argument-hint: [ticker]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Explain Trade — Trade Rationale & History

## Data Gathering

Given ticker (append .NS if missing):

1. `portfolio_holdings` — current position details (shares, avg cost, weight)
2. `portfolio_trades` — full trade history for this stock
3. `trade_rationale` — stored rationale from when the trade was made
4. `analyze_stock` — current state of the stock
5. `performance_attribution` — how this stock has contributed to portfolio returns

## Explain the Story

### Entry
- **When**: Date of first purchase
- **Why**: Original rationale (from stored rationale or strategy screen criteria)
- **At what price**: Entry price vs current price
- **Strategy fit**: Which tier of god's plan (Quality Growth / Defensive / Value)?

### Performance Since Entry
- **Return**: Total return % and INR
- **vs Nifty**: Outperformed or underperformed the index?
- **Contribution**: How much did this stock add/subtract from portfolio return?
- **Volatility**: Has it been a smooth or volatile ride?

### Current Thesis
- **Still valid?**: Does the stock still pass the strategy screen?
- **Quality score change**: Improved or deteriorated since entry?
- **Key risks**: What could go wrong from here?

### All Trades
Show chronological trade history:
| Date | Action | Shares | Price | Rationale |
|------|--------|--------|-------|-----------|

If the user asks about a proposed (future) trade, explain:
- Why the strategy is recommending it
- What metrics drove the selection
- How it compares to alternatives that were NOT selected