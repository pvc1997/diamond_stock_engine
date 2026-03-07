---
name: sector-rotation
description: Identifies sector rotation opportunities and trends. Activates when the user asks about sector performance, "which sectors are hot?", "sector rotation", "where is money flowing?", "defensive sectors", "cyclical vs defensive", or discusses sector-level strategy.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Sector Rotation — Follow the Money

## Data Gathering (parallel)

1. `market_pulse` — today's sector moves with direction
2. `sector_exposure` — current portfolio sector weights
3. `sector_list` — all available sectors
4. `market_screener` — top stocks by sector with momentum

## Rotation Analysis

### Current Sector Performance
| Sector | Today | Trend | Portfolio Weight | Over/Under |
|--------|-------|-------|-----------------|------------|

Classify each sector:
- **Leading**: Positive momentum, above average performance
- **Weakening**: Was strong, now losing momentum
- **Lagging**: Negative momentum, underperforming
- **Improving**: Was weak, now gaining momentum

### Rotation Signal
Based on the sector cycle (Leading -> Weakening -> Lagging -> Improving):

**Risk-On Rotation** (economy expanding):
- Favor: Technology, Consumer Discretionary, Industrials, Financials
- Reduce: Utilities, Consumer Staples, Healthcare

**Risk-Off Rotation** (economy slowing):
- Favor: Healthcare, Consumer Staples, Utilities
- Reduce: Metals, Automobile, Consumer Discretionary

### Portfolio Implications

1. **Overweight in weakening sectors**: Flag for trimming
2. **Underweight in improving sectors**: Flag for adding
3. **Concentration in one cycle phase**: Diversification risk

## Actionable Output

"Sectors rotating INTO strength: [list]. Consider: /buy STOCK from these sectors."
"Sectors rotating OUT: [list]. If you hold [stocks], monitor for trim signals."
"Your portfolio is [balanced/tilted risk-on/tilted risk-off] vs current rotation."