---
name: undo-trade
description: Reverses a recent trade safely. Activates when the user says "undo", "reverse that", "I shouldn't have bought X", "cancel that buy", "take it back", "that was a mistake", "sell what I just bought", or wants to reverse a recent trade decision.
argument-hint: [ticker]
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Undo Trade — Safe Trade Reversal

## IMPORTANT: This is NOT a database rollback

Undoing a trade means placing an OPPOSITE trade at CURRENT market prices.
The user will incur transaction costs both ways. Make this clear.

## Process

### Step 1: Identify the Trade to Undo

Use `portfolio_trades` MCP tool to find recent trades.

If user says:
- "Undo last trade" → most recent trade
- "Undo the RELIANCE buy" → most recent RELIANCE.NS trade
- "Undo today's trades" → all trades from today
- "That was a mistake" → infer from conversation context (session-context skill)

### Step 2: Show What Will Happen

"You bought 15 shares of TCS.NS at INR 2,557 on Mar 7 (total: INR 38,355).

To undo, I'll sell 15 shares at current price (~INR 2,560).
- Proceeds: ~INR 38,400
- Transaction costs (round-trip): ~INR 115
- Net impact: ~INR -70 (small loss from costs)
- Tax: STCG (held < 12 months)

This will remove TCS from your portfolio."

### Step 3: Confirm Before Executing

"Proceed with the reversal? This will:
1. Sell 15 shares of TCS.NS at market price
2. Record the sell in your ledger
3. Free up ~INR 38,400 in cash

Type 'yes' to confirm or 'no' to keep the position."

### Step 4: Execute (only after confirmation)

Use `sell_stock` MCP tool or `uv run diamond sell gods_plan TCS.NS`

### Step 5: Journal Entry

After undo, suggest recording a lesson:
"Want to note why this was reversed? (helps avoid the same mistake)"
If yes, trigger investment-journal skill.

## Safety Guards

- Cannot undo trades older than 7 days (prices may have moved significantly)
- Cannot undo partial fills (warn about the complexity)
- Show the cost of undoing (transaction fees + potential price difference)
- If the stock has moved >5% since the trade: "Warning: price has moved X% since your trade. Undoing now locks in a loss/gain of INR Y."
- If this would leave the portfolio with 0 holdings in a sector: flag it

## What This Does NOT Do
- Does NOT modify the ledger history (both trades are recorded)
- Does NOT refund transaction costs from the original trade
- Does NOT work for trades executed on Kite (broker orders are final — can only place a counter-order)