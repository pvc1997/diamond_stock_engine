---
name: peer-compare
description: Compares stocks head-to-head for portfolio decisions. Activates when the user asks "X vs Y", "which is better, X or Y?", "compare X and Y", "should I swap X for Y?", "replace X with Y", or discusses choosing between stocks.
argument-hint: [ticker1] [ticker2]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Peer Compare — Head-to-Head Stock Comparison

## Data Gathering (parallel for both stocks)

For each ticker (append .NS if missing):
1. `analyze_stock` — technicals + fundamentals + quality score
2. `stock_sentiment` — AI sentiment verdict
3. `stock_sector` — sector classification
4. `stock_prices` — recent price action

Also:
5. `portfolio_holdings` — are either/both held?
6. `sector_exposure` — sector impact of a swap

## Comparison Table

| Metric | Stock A | Stock B | Edge |
|--------|---------|---------|------|
| Quality Score | | | |
| CAGR (3Y) | | | |
| Alpha | | | |
| Beta | | | |
| Volatility | | | |
| Hurst Exponent | | | |
| RSI (14) | | | |
| P/B Ratio | | | |
| Sector | | | |
| Sentiment | | | |
| Currently Held? | | | |

## Context-Aware Analysis

### If comparing for a NEW buy:
- Which stock improves portfolio diversification more?
- Which has better risk-adjusted returns (Alpha/Vol ratio)?
- Which fits the strategy tier better (Quality Growth / Defensive / Value)?

### If comparing for a SWAP (replace A with B):
- Tax impact of selling A (STCG vs LTCG, gain/loss)
- Transaction costs of the round-trip (sell A + buy B)
- Net expected improvement after costs
- Use `whatif_simulation` to model the swap

## Verdict

"Between STOCK_A and STOCK_B:
- **Winner**: STOCK_X (reason in 1 sentence)
- **For your portfolio**: [specific recommendation considering current holdings]
- **If swapping**: Net cost of swap = INR X (tax) + INR Y (fees). Worth it if [condition]."

If the comparison is close (within 10% on quality), say so: "These are comparable. Prefer the one with better sector diversification for your portfolio."