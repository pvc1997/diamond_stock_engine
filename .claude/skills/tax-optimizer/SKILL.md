---
name: tax-optimizer
description: Tax-aware trade optimization. Auto-activates when the user discusses selling stocks, harvesting losses, tax implications, STCG, LTCG, capital gains, or asks about the tax impact of any trade.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Tax Optimizer — Minimize Tax Drag

## When This Activates

- User wants to sell a stock (check tax impact first)
- User asks about taxes or capital gains
- User mentions "harvest", "STCG", "LTCG", "tax loss"
- Before any rebalance that involves sells

## Tax Context (gather via MCP)

1. `tax_report` — current STCG/LTCG breakdown for all holdings
2. `portfolio_holdings` — holding period for each stock
3. `tax_aware_trades` — optimally ordered trade list

## Indian Tax Rules Applied

- **STCG** (held < 12 months): Taxed at 20%
- **LTCG** (held > 12 months): Taxed at 12.5%, exempt up to 1.25L/year
- **Tax-loss harvesting**: Sell losers to offset gains (must respect wash-sale logic)

## Analysis Framework

For any proposed sell:
1. **Holding period**: How long held? STCG or LTCG?
2. **Gain/Loss**: Unrealized P&L in INR
3. **Tax cost**: Estimated tax on this sale
4. **Net proceeds**: After tax and transaction costs
5. **Harvesting opportunity**: Can we sell a loser to offset this gain?

## Optimization Suggestions

- **Defer STCG sells**: If stock will cross 12-month mark within 30 days, suggest waiting
- **Harvest losses first**: Sell losers before winners to reduce net tax
- **Use LTCG exemption**: Track how much of the 1.25L annual exemption is used
- **Batch sells**: If multiple sells needed, order them tax-optimally

## Output Format

| Stock | Held | Type | Gain/Loss | Tax | Net Impact |
|-------|------|------|-----------|-----|------------|

Then: "Tax-optimal order: Sell X first (harvest loss), then Y (LTCG exemption covers), then Z (unavoidable STCG)."

Always show the tax cost BEFORE the user confirms any sell.