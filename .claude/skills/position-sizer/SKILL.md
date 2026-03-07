---
name: position-sizer
description: Calculates optimal position sizes for trades. Auto-activates when the user asks "how much should I buy?", "what size?", "how many shares?", discusses allocation amounts, or needs help sizing a trade relative to portfolio.
argument-hint: [ticker] [amount]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Position Sizer — Optimal Trade Sizing

## Inputs Needed

- **Ticker**: Stock to size (from conversation)
- **Direction**: Buy or top-up (from context)
- **Available capital**: From portfolio cash or user-specified amount

## Data Gathering (parallel)

1. `portfolio_status` — current NAV and cash
2. `market_pulse` — verdict affects sizing multiplier
3. `volatility_sizing` — volatility-adjusted position size
4. `portfolio_holdings` — existing position weight
5. `sector_exposure` — sector room available

## Sizing Algorithm

### Step 1: Maximum Allowed
- **Position cap**: 10% of NAV = max for any single stock
- **Current weight**: If already held, max additional = (10% - current weight) * NAV
- **Sector cap**: 25% of NAV per sector, 4 stocks per sector

### Step 2: Market-Adjusted
Apply market pulse multiplier:
- DEPLOY: 100% of calculated size
- WAIT: 50% of calculated size (half position)
- DEFENSIVE: 25% of calculated size (quarter position, or skip)

### Step 3: Volatility-Adjusted
Use `volatility_sizing` to adjust for stock-specific risk:
- High volatility stock: Reduce size by vol ratio
- Low volatility stock: Can take full or slightly larger size
- Target equal risk contribution across positions

### Step 4: Practical Constraints
- Minimum trade: 1,000 INR (below this, skip)
- Round to whole shares
- Check cash available (can't size more than what's in the portfolio)
- Transaction costs: Factor in ~0.5% round-trip cost

## Output

| Parameter | Value |
|-----------|-------|
| Stock | TICKER.NS |
| Current Weight | X% |
| Target Weight | Y% |
| Shares to Buy | N |
| Amount | INR X,XXX |
| Post-Buy Weight | Z% |
| Market Adjustment | WAIT = 50% |

"Recommended: Buy N shares of TICKER at ~INR X,XXX (Y% of NAV after purchase)"
Command: `uv run diamond buy gods_plan TICKER.NS -a AMOUNT`