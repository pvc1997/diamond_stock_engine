Show upcoming portfolio events calendar. User input: $ARGUMENTS

1. Use `earnings_calendar` MCP tool for gods_plan — upcoming quarterly results
2. Use `corporate_actions` MCP tool for gods_plan — splits, dividends, bonuses
3. Use `watchlist_signals` MCP tool — any watchlist price alerts near trigger

Present a unified timeline:
- **This Week**: events in next 7 days (earnings, dividends, ex-dates)
- **This Month**: events in next 30 days
- **Key Dates**: RBI policy, options expiry, index rebalance dates

Format as a clean timeline. Flag any conflicts (e.g., earnings on same day as rebalance).

If $ARGUMENTS contains a ticker, use `earnings_check` MCP tool for that specific stock and show its calendar only.