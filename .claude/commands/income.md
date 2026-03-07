Investment income report. User input: $ARGUMENTS

Show all income from the portfolio — dividends + realized gains.

1. Use `tax_report` MCP tool for gods_plan — realized gains (STCG + LTCG)
2. Use `corporate_actions` MCP tool for gods_plan — dividend history
3. Use `portfolio_status` MCP tool — unrealized gains
4. Use `dividend_yield_portfolio` MCP tool — projected dividend income

Present:
- **Realized Income**: total gains booked, STCG vs LTCG split
- **Dividend Income**: total dividends received, annualized yield
- **Unrealized Gains**: paper profit still in portfolio
- **Total Return**: realized + unrealized + dividends
- **Projected Annual Income**: from current dividend yield

If $ARGUMENTS contains "monthly" or "quarterly" or "annual", break down by that period.

Show the tax liability estimate for realized gains.