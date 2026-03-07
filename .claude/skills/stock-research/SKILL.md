---
name: stock-research
description: Deep stock research and analysis. Use when the user mentions a specific ticker, asks "should I buy X?", "what about X?", "how is X doing?", "tell me about X", or any question about a specific stock's fundamentals, technicals, or outlook.
argument-hint: [ticker]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Stock Research — Deep Dive Analysis

## Process

Given ticker from conversation (append .NS if missing):

### Step 1: Gather Data (run in parallel)

Use MCP tools for structured data:
- `analyze_stock` — technicals + fundamentals + quality score
- `stock_sentiment` — AI sentiment verdict
- `stock_prices` — recent price action
- `portfolio_holdings` — check if already held
- `sector_exposure` — sector concentration context

### Step 2: Technical Picture

From the analysis data, present:
- **Trend**: Uptrend / Downtrend / Sideways (based on 50/200 DMA)
- **Momentum**: RSI level + MACD signal
- **Volatility**: Bollinger Band position, recent range
- **Key Levels**: Support and resistance prices

### Step 3: Fundamental Quality

- **Quality Score**: Out of 100 (CAGR 30% + Alpha 25% + Low-vol 20% + Beta 15% + Hurst 10%)
- **Growth**: CAGR %, Alpha vs benchmark
- **Risk**: Beta, annualized volatility
- **Persistence**: Hurst exponent (>0.5 = trending, <0.5 = mean-reverting)

### Step 4: Portfolio Fit

- Current weight if held (and drift from target)
- Sector exposure impact
- Correlation with top 3 holdings
- Would this improve or worsen diversification?

### Step 5: Verdict

**BUY / HOLD / TRIM / AVOID** with:
- Confidence: High / Medium / Low
- If BUY: suggested amount (respecting position limits)
- If HOLD: what would change the thesis
- If TRIM/AVOID: specific reason and alternative suggestion
- Tax note: STCG/LTCG status if already held

Keep the output focused — max 25 lines. The user wants a decision, not a textbook.