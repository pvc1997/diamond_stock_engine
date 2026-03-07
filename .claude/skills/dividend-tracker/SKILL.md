---
name: dividend-tracker
description: Tracks dividends and corporate actions for the portfolio. Activates when the user asks about dividends, "any dividends coming?", "corporate actions", "stock split", "bonus shares", "ex-date", or discusses income from holdings.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Dividend Tracker — Income & Corporate Actions

## Data Gathering

1. `corporate_actions` — recent and upcoming splits, dividends, bonus issues
2. `portfolio_holdings` — current holdings to match against actions
3. `portfolio_trades` — check if any synthetic trades recorded for past actions

## Corporate Action Summary

### Recent Actions (last 30 days)
| Stock | Type | Details | Date | Applied? |
|-------|------|---------|------|----------|

Types:
- **Dividend**: Amount per share, ex-date, record date
- **Split**: Ratio (e.g., 2:1), effective date
- **Bonus**: Ratio (e.g., 1:1), record date

### Upcoming Actions (next 30 days)
Flag any known upcoming events for held stocks.

### Ledger Verification
- Check that past splits are reflected in share counts
- Check that dividends are recorded as synthetic trades
- Flag any MISSING adjustments: "STOCK had a 2:1 split on DATE but ledger still shows old share count"

## Dividend Income Summary

If dividends have been received:
- Total dividend income YTD
- Dividend yield of portfolio (annualized)
- Top dividend payers in the portfolio

## Action Items

- **Unrecorded actions**: `uv run diamond actions gods_plan` to sync
- **Missing adjustments**: Flag for manual review
- **Upcoming ex-dates**: "STOCK goes ex-dividend on DATE. Hold through if you want the dividend."

Note: Dividends are recorded but not auto-reinvested. Suggest deploying dividend cash via `/accumulate deploy`.