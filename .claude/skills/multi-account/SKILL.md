---
name: multi-account
description: Manages multiple portfolios for family members. Auto-activates when the user mentions "my wife's portfolio", "second account", "family portfolio", "another account", "separate portfolio for", or discusses managing multiple investment accounts.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Multi-Account — Family Portfolio Manager

## Trigger Conditions

Activate when:
- User mentions another person's portfolio
- User asks to create a separate portfolio
- User wants to compare their portfolio with a family member's

## What To Do

1. **Strategy naming convention** — each account uses a unique strategy name:
   - Primary: `gods_plan` (default)
   - Spouse: `gods_plan_spouse` or custom name
   - Child: `gods_plan_child` or custom name
   - Use `diamond run <name> --capital <amount>` to initialize

2. **Portfolio operations** — all Diamond commands accept strategy name:
   - `uv run diamond status` shows all strategies
   - `uv run diamond buy gods_plan_spouse RELIANCE.NS -a 50000`
   - `uv run diamond risk gods_plan_spouse`
   - Each has its own ledger in `data/ledgers/`

3. **Family overview** — aggregate across accounts:
   - Total family NAV
   - Combined sector exposure
   - Cross-portfolio correlation (avoid same bets)

4. **Recommendations:**
   - Different risk profiles for different family members
   - Spouse: consider `steady` strategy (lower risk)
   - Child (long horizon): consider `gods_plan` (higher growth)
   - Tax optimization across accounts (harvest in one, hold in other)

## Output Format

**Family Portfolio Overview:**
| Account | Strategy | NAV | Return | Risk Level |
|---------|----------|-----|--------|------------|
| Primary | gods_plan | Rs X | +Y% | Aggressive |
| Spouse | steady | Rs X | +Y% | Conservative |
| Total | -- | Rs X | +Y% | -- |

**Cross-Portfolio Check:**
- Duplicate holdings: [stocks held in multiple accounts]
- Total sector exposure: [combined sector weights]
- Suggestion: [diversification advice across accounts]
