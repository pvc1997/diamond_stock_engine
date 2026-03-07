Quick peer comparison table. User input: $ARGUMENTS

Parse $ARGUMENTS for a ticker (e.g., `/peers INFY`).

1. Use `analyze_stock` MCP tool for the ticker — get fundamentals + sector
2. Use `stock_sector` MCP tool to identify sector
3. Use `market_screener` MCP tool — get all screened stocks, filter for same sector

Present a quick comparison table of sector peers:
| Metric | INFY | TCS | WIPRO | HCLTECH |
|--------|------|-----|-------|---------|
| Price | Rs X | Rs X | Rs X | Rs X |
| CAGR | X% | X% | X% | X% |
| Alpha | X | X | X | X |
| Beta | X | X | X | X |
| Volatility | X% | X% | X% | X% |

Highlight the "best" value in each row. Add a one-line verdict.

This is the quick version — for deep comparison, suggest `/compare INFY TCS`.