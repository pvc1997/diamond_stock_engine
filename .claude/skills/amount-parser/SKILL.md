---
name: amount-parser
description: Parses natural language amounts into exact INR values. Auto-activates when the user mentions money amounts in Indian conventions like "2 lakhs", "50k", "1 crore", "half my cash", "5% of portfolio", or relative sizing like "double the position".
user-invocable: false
allowed-tools: mcp__diamond__*
---

# Amount Parser — Natural Language to INR

## Absolute Amounts

Parse these patterns to exact INR:
- "50k" / "50K" → 50,000
- "1 lakh" / "1L" / "1 lac" → 100,000
- "2.5 lakhs" → 250,000
- "1 crore" / "1cr" / "1C" → 10,000,000
- "50 thousand" → 50,000
- "25 hundred" → 2,500
- "10k each" → 10,000 per stock (multiply by count)

## Relative to Portfolio

When the user says relative amounts, resolve using `portfolio_status` MCP tool:
- "half my cash" → available_cash * 0.5
- "all my cash" → available_cash (WARN: this leaves zero buffer)
- "10% of portfolio" → NAV * 0.10
- "5% of cash" → available_cash * 0.05
- "equal weight" → NAV / stock_count (for rebalancing context)

## Relative to Position

When referring to an existing position (needs `portfolio_holdings`):
- "double this position" → current_position_value * 1.0 (add same amount again)
- "triple it" → current_position_value * 2.0
- "cut it in half" → sell 50% of shares
- "reduce by a third" → sell 33% of shares
- "add 20% more" → current_position_value * 0.20

## Safety Checks

After parsing, always verify:
- Amount > 0 (reject negative or zero)
- Amount ≤ available cash (for buys)
- Amount ≥ 1,000 INR (minimum trade threshold)
- Amount ≤ 10% of NAV for single position (flag if exceeding)

If amount seems unusually large (> 50% of NAV in one trade):
"That's INR X,XX,XXX — about Y% of your portfolio. Are you sure?"

## Output

Always confirm the parsed amount before proceeding:
"Understood: INR 2,50,000 (2.5 lakhs). That's X% of your portfolio."

Use Indian number formatting: 1,00,000 (not 100,000) for display.