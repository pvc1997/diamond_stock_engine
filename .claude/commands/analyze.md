Deep-dive analysis on a stock. User input: $ARGUMENTS

For the given stock (append .NS if not already present):

1. Run `uv run diamond analyze <TICKER>` — full technical + fundamental deep dive
2. Run `uv run diamond sentiment <TICKER>` — AI sentiment analysis

Then synthesize into a clear verdict:
- **Technical**: RSI, MACD, Bollinger Band position, support/resistance levels
- **Fundamental**: Quality score, CAGR, alpha, beta, volatility
- **Sentiment**: AI verdict + news context
- **Portfolio Fit**: Would this add diversification or increase concentration?
- **Verdict**: BUY / HOLD / AVOID with confidence level and price targets

If the stock is already in the portfolio, also show:
- Current weight and P&L
- Whether to add more or trim

If no ticker provided, ask the user which stock to analyze.