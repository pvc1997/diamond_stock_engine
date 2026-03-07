---
name: natural-screen
description: Translates natural language stock screening criteria into structured screens. Activates when the user says "find me stocks that...", "show me high dividend stocks", "low PE stocks", "stocks under 500", "quality stocks in IT", "defensive picks", "momentum plays", or describes characteristics they want in a stock.
argument-hint: [criteria]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Natural Screen — Plain English Stock Screener

## Pattern Matching

Translate natural language to screener parameters:

### Quality / Growth
- "quality stocks" → Alpha > 0.1, CAGR > 15%, Quality Score > 60
- "high growth" → CAGR > 25%, Alpha > 0.2
- "compounders" → CAGR > 20%, Hurst > 0.55 (trending)
- "consistent growers" → CAGR > 15%, Volatility < 25%

### Value
- "cheap stocks" / "undervalued" → P/B < 2.0, Alpha > 0 (not value traps)
- "low PE" → use P/B as proxy (P/E not in screener), P/B < 1.5
- "value picks" → P/B < 2.0, CAGR > 10% (growing AND cheap)
- "beaten down" → Price near 52-week low, Alpha still positive

### Defensive / Low Risk
- "safe stocks" / "defensive" → Beta < 0.8, Volatility < 20%
- "low volatility" → Volatility < 20%, sorted by lowest vol
- "stable" → Beta < 0.9, Volatility < 25%, CAGR > 10%
- "capital protection" → Beta < 0.7, drawdown < 15%

### Momentum
- "trending stocks" → Hurst > 0.55, Alpha > 0.15
- "momentum plays" → CAGR > 30%, Hurst > 0.5
- "stocks going up" → RSI 50-70, Alpha > 0 (not overbought)

### Income
- "dividend stocks" / "high dividend" → focus on Consumer Staples, Utilities, Energy sectors
- "income picks" → low beta + large cap sectors known for dividends

### Sector Specific
- "IT stocks" / "tech" → filter Technology sector
- "bank stocks" / "financials" → filter Financial Services sector
- "pharma" / "healthcare" → filter Healthcare sector
- "auto stocks" → filter Automobile sector
- "metal stocks" → filter Metals sector

### Price Range
- "stocks under 500" → filter by current price < 500
- "penny stocks" → AVOID — warn user about risk
- "blue chips" → Nifty 50 members only
- "large cap" → Nifty 100 members
- "mid cap" → Nifty Midcap 150 members

## Execution

1. Parse the natural language criteria
2. Map to `custom_screen` MCP tool parameters OR `market_screener`
3. If criteria map well to an existing strategy's screen: mention it ("This is basically what the Steady strategy does")
4. Run the screen
5. Present top 10 results sorted by quality score

## Output Format

"Found X stocks matching 'defensive quality picks in IT':

| # | Stock | Quality | CAGR | Alpha | Beta | Vol | Sector |
|---|-------|---------|------|-------|------|-----|--------|
| 1 | INFY.NS | 82 | 22% | 0.18 | 0.85 | 18% | Technology |
| ... | | | | | | | |

Top pick: INFY.NS — quality score 82, low beta, consistent growth.
Want to analyze any of these? Or add to watchlist?"

## Safety

- Never screen for penny stocks or F&O-only strategies
- If criteria are contradictory ("high growth + low risk + cheap"), explain the impossible triangle
- Maximum 10 results to avoid overwhelm