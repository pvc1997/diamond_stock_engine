Compare portfolio states. User input: $ARGUMENTS

If $ARGUMENTS contains a snapshot name:
- Use `portfolio_diff` MCP tool to compare snapshot vs current portfolio
- Show: added stocks, removed stocks, weight changes, NAV change

If $ARGUMENTS contains two names (e.g., "march april"):
- Use `portfolio_diff` MCP tool with both names to compare snapshots

Present as a diff:
```
+ Added: RELIANCE.NS (5.2% weight)
- Removed: TATATECH.NS (was 3.1%)
~ Changed: TCS.NS (4.5% -> 6.2%, +1.7%)
NAV: Rs 4,50,000 -> Rs 5,20,000 (+15.6%)
```

Keep it clean and scannable. Show net impact on sector exposure if significant.