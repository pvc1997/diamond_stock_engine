---
name: earnings-calendar
description: Tracks upcoming quarterly results for portfolio stocks. Auto-activates when the user asks "any results coming?", "earnings this week", "quarterly results", "result season", or mentions earnings dates.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Earnings Calendar — Quarterly Results Tracker

## Trigger Conditions

Activate when the user:
- Asks about upcoming earnings/results for portfolio stocks
- Mentions "result season", "quarterly results", "earnings week"
- Asks "any results coming?", "when does X report?"
- Before buying a stock (check if earnings are imminent)

## What To Do

1. **Portfolio Earnings** — use `earnings_calendar` MCP tool
   - Show stocks with earnings in next 7 days (URGENT)
   - Show stocks with earnings in next 30 days (UPCOMING)
   - Flag any stock reporting tomorrow or today

2. **Pre-Trade Earnings Check** — if user is about to buy/sell:
   - WARN if earnings within 3 days (high volatility risk)
   - Suggest waiting until after results if within 1 week
   - Note: "Never buy on the day of earnings" is a default rule

3. **Earnings Season Overview**:
   - How many portfolio stocks report this month
   - Any sector clusters (e.g., all IT stocks report same week)

## Output Format

| Stock | Earnings Date | Days Until | Quarter | Action |
|-------|--------------|------------|---------|--------|
| TCS.NS | 2026-04-15 | 3 | Q4 FY26 | WAIT — results imminent |
| INFY.NS | 2026-04-20 | 8 | Q4 FY26 | Monitor |

- URGENT (< 3 days): Bold, suggest no trading
- UPCOMING (3-14 days): Note it, proceed with caution
- LATER (> 14 days): Informational only
