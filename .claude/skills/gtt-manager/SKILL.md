---
name: gtt-manager
description: Manages GTT (Good-Till-Triggered) stop-loss and take-profit orders via Zerodha. Activates when the user says "set a stop loss", "protect my position", "auto-sell if X drops below Y", "take profit at Z", "GTT order", "trailing stop", "set an alert to sell", or discusses automated exit conditions for holdings.
argument-hint: [ticker] [trigger-price]
allowed-tools: mcp__kite__*, mcp__diamond__*
---

# GTT Manager — Automated Stop-Loss & Take-Profit

## What GTT Orders Do

GTT (Good-Till-Triggered) orders sit on Zerodha's servers and auto-execute when a price condition is met. They persist across sessions — no need to be logged in.

This is the KEY upgrade over manual stop-loss monitoring.

## Supported Scenarios

### Stop-Loss Protection
User says: "Protect TATATECH if it drops below 550"
- Trigger: LTP <= 550
- Action: SELL all shares at market
- Type: Single-leg GTT

### Take-Profit
User says: "Sell RELIANCE when it hits 3200"
- Trigger: LTP >= 3200
- Action: SELL all shares at market
- Type: Single-leg GTT

### OCO (One-Cancels-Other) — Stop-Loss + Take-Profit
User says: "Protect SAIL — sell if drops below 100 or if it hits 150"
- Lower trigger: LTP <= 100 (stop-loss)
- Upper trigger: LTP >= 150 (take-profit)
- Whichever hits first cancels the other
- Type: Two-leg GTT (OCO)

## Process

### Step 1: Gather Context

Use Diamond MCP tools:
- `portfolio_holdings` — get current shares, avg cost, current weight
- `portfolio_status` — check NAV for position sizing context

Use Kite MCP tools:
- `mcp__kite__get_ltp` — get current live price
- `mcp__kite__get_holdings` — verify shares are in demat

### Step 2: Calculate Trigger Price

If user specifies an exact price: use it.
If user says "10% stop loss": calculate from avg cost or current price.
If user says "protect it": suggest stop-loss at -10% from current price (default Diamond threshold).

Always show:
- Current price: INR X
- Trigger price: INR Y
- Distance: Z% from current
- Shares affected: N
- Estimated proceeds if triggered: INR X,XXX

### Step 3: Place the GTT

Use `mcp__kite__place_gtt_order` with:
- `trigger_type`: "single" or "two-leg"
- `instrument_token`: from search_instruments
- `exchange`: "NSE"
- `trigger_values`: [price] or [lower, upper]
- `orders`: [{transaction_type: "SELL", quantity: N, price: 0 (market), order_type: "MARKET"}]

### Step 4: Confirm

"GTT order placed:
- Stock: TATATECH.NS
- Trigger: Sell N shares if price drops to INR 550
- GTT ID: XXXXX
- Status: Active (persists until triggered or cancelled)
- No action needed — Zerodha monitors this 24/7."

## Management

### View Active GTTs
User says "my stop losses" or "active GTTs":
- Use `mcp__kite__get_gtts` to list all active GTT orders
- Cross-reference with Diamond holdings to show which positions are protected

### Modify GTT
User says "move my stop loss on TCS to 2400":
- Use `mcp__kite__modify_gtt_order` with new trigger price

### Cancel GTT
User says "remove the stop loss on RELIANCE":
- Use `mcp__kite__delete_gtt_order`

## Integration with Diamond Risk System

When `risk-alert` skill detects a stop-loss breach:
- Check if a GTT already exists for that stock
- If yes: "GTT is active — it will auto-sell at INR X. No action needed."
- If no: "No GTT protection. Want me to set one?"

When `trade-guard` runs before a buy:
- After confirming the buy, suggest: "Want to set a 10% stop-loss GTT for protection?"

## Safety Rules

- NEVER place a GTT without showing the user the exact trigger and quantity first
- NEVER place a GTT that would sell MORE shares than held
- ALWAYS verify shares are in demat (not T+1 pending)
- For OCO orders: verify the upper trigger > current price > lower trigger
- Remind user: GTT orders expire after 1 year on Zerodha