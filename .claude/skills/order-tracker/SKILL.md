---
name: order-tracker
description: Tracks and manages pending orders. Auto-activates when the user says "my orders", "pending orders", "order status", "cancel order", "any orders open?", "what's queued?", or asks about trade execution status.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*), mcp__kite__*
---

# Order Tracker — Pending Order Management

## Trigger Conditions

Activate when:
- User asks "my orders", "pending orders", "order status"
- User says "cancel that order", "what's queued?"
- User asks "did my order fill?", "any open orders?"
- User mentions "limit order", "order book"

## What To Do

1. **Diamond orders** — use `order_book` MCP tool
   - Show pending, filled, and cancelled orders
   - Flag any stale orders (pending > 24h)

2. **Kite orders** (if live session) — use `mcp__kite__get_orders`
   - Show real broker orders with status
   - Show GTT orders via `mcp__kite__get_gtts`

3. **Cancel** if requested:
   - Diamond: `uv run diamond orders gods_plan --cancel <order_id>`
   - Kite: use `mcp__kite__cancel_order`
   - Always confirm before cancelling

## Output Format

**Open Orders:**
| # | Stock | Type | Qty | Price | Status | Age |
|---|-------|------|-----|-------|--------|-----|
| 1 | TCS.NS | BUY LIMIT | 5 | Rs 3,800 | PENDING | 2h |

**GTT Orders:** [list if any]
**Recently Filled:** [last 3 fills]
