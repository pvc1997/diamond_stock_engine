---
name: kite-reconciler
description: Reconciles Diamond ledger with actual Zerodha Kite holdings using live broker data. Activates when the user says "reconcile", "check my real holdings", "is my ledger accurate?", "sync with broker", "what does Kite show?", or when discrepancies are suspected.
allowed-tools: mcp__kite__*, mcp__diamond__*
---

# Kite Reconciler — Ledger vs Broker Truth

## Why This Matters

Diamond's ledger tracks trades locally. But the real source of truth is Zerodha.
Discrepancies happen from: corporate actions, trades placed on Kite web, failed orders, CDSL issues.

## Process

### Step 1: Get Both Views (parallel)

**From Diamond:**
- `mcp__diamond__portfolio_holdings` — local ledger holdings (ticker, shares, avg_cost)

**From Kite:**
- `mcp__kite__get_holdings` — actual demat holdings (tradingsymbol, quantity, average_price, last_price, pnl)

### Step 2: Compare

Convert tickers to common format and match:
- Diamond: `RELIANCE.NS` → `RELIANCE`
- Kite: `RELIANCE` (tradingsymbol)

Build comparison:
| Stock | Diamond Qty | Kite Qty | Diamond Avg | Kite Avg | Match? |
|-------|------------|----------|-------------|----------|--------|

### Step 3: Classify Discrepancies

**In Diamond, NOT in Kite:**
- Stock may be delisted → suggest `diamond cleanup`
- Stock sold on Kite web → need to record sell in Diamond ledger
- Corporate action renamed ticker → need mapping update

**In Kite, NOT in Diamond:**
- Bought on Kite web/app → need to import into Diamond
- Recent IPO allotment → need to add manually
- Suggest: `diamond kite --import <strategy> -c <capital>`

**Quantity Mismatch:**
- Unrecorded stock split → check `diamond actions`
- Partial fill not recorded → check Kite order history
- Bonus shares credited → check corporate actions

**Average Price Mismatch:**
- Minor differences (<2%) are normal (Diamond uses weighted avg, Kite uses FIFO)
- Large differences → likely unrecorded corporate action

### Step 4: Show Today's Kite Orders

Use `mcp__kite__get_orders` to check if any orders placed today outside Diamond:
- Show any orders NOT initiated by Diamond
- Flag: "These orders weren't tracked by Diamond. Reconcile?"

### Step 5: Recommendations

For each discrepancy, give a specific fix:
1. "MANGIND.NS is in Diamond but not Kite — likely delisted. Run cleanup."
2. "HDFCBANK found in Kite but not Diamond — bought outside? Import it."
3. "TCS shows 20 shares in Diamond but 40 in Kite — possible 2:1 split. Run `diamond actions`."

## Reconciliation Report

```
Reconciliation: Diamond vs Kite
================================
Matched:     14/17 positions
Mismatched:  2 positions (quantity)
Missing:     1 in Kite (delisted?)

Actions needed:
1. [CRITICAL] MANGIND.NS — in Diamond only, no Kite holding → cleanup
2. [WARNING] TCS.NS — Diamond: 20 shares, Kite: 40 shares → check split
3. [INFO] All other positions match within tolerance
```

## Frequency

Suggest running reconciliation:
- Weekly as part of `/weekly` review
- After any live trading session
- After corporate action sync
- When NAV doesn't match expectations