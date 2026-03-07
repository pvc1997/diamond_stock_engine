---
name: winners-losers
description: Shows best and worst performing stocks in the portfolio. Activates when the user asks "my winners", "my losers", "best performers", "worst stocks", "top gainers", "biggest losers", "what's up today", "what's down", "best stock this week/month/year".
argument-hint: [period]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Winners & Losers — Portfolio Performance Rankings

## Data Gathering

1. `portfolio_holdings` — all current positions with cost basis
2. `portfolio_status` — NAV and day change
3. `stock_prices` — current prices for all holdings (for day change)

## Rankings to Show

### Today's Movers
| Rank | Stock | Day Change | INR Impact |
|------|-------|-----------|------------|
| 1 (best) | | +X.X% | +INR X,XXX |
| 2 | | | |
| 3 | | | |
| ... | | | |
| (worst) | | -X.X% | -INR X,XXX |

### Since Purchase (Total Return)
| Rank | Stock | Total Return | Held Since | INR P&L |
|------|-------|-------------|------------|---------|
| 1 (best) | | +XX% | DATE | +INR XX,XXX |
| ... | | | | |
| (worst) | | -XX% | DATE | -INR XX,XXX |

## Period Handling

If user specifies a period:
- "today" / "this session" → day change
- "this week" → 5-day return
- "this month" → 30-day return
- "this year" / "YTD" → year-to-date return
- "since I bought" / "overall" → total return since purchase (default)

## Insights

After showing rankings:
- **Winner insight**: "STOCK has been your best pick — up X% and contributing Y% of total portfolio return"
- **Loser insight**: "STOCK is dragging — down X%. Still passes quality screen? [Yes/No]. Holding period: [STCG/LTCG]."
- **Concentration check**: "Your top 3 winners are X% of portfolio — consider trimming if >30%"

## Quick Follow-ups

Suggest natural next actions:
- For big winners: "Trim STOCK? It's X% of portfolio now. `/sell STOCK`"
- For big losers: "Still a hold? `/analyze STOCK` for a fresh look"
- For losers near stop-loss: "STOCK is X% from stop-loss trigger. Watch closely."