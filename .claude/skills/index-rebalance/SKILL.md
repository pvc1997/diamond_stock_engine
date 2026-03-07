---
name: index-rebalance
description: Tracks index inclusion/exclusion for portfolio stocks. Auto-activates when the user asks "Nifty changes", "index inclusion", "added to Nifty", "removed from index", "index rebalance", or discusses index effects on stocks.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Index Rebalance — Index Membership Tracker

## Trigger Conditions

Activate when:
- User asks about index changes (Nifty 50, Nifty Next 50, etc.)
- User mentions "index inclusion", "index rebalance"
- A stock enters/exits a major index
- User asks "is X in Nifty?"

## What To Do

1. **Check membership** — use `index_membership` MCP tool
   - Which indices does the stock belong to?
   - Is it in Nifty 50, Nifty Next 50, or sector indices?

2. **Impact analysis:**
   - Index INCLUSION: typically bullish (passive fund buying)
   - Index EXCLUSION: typically bearish (passive fund selling)
   - Estimate passive flow impact (Nifty 50 trackers hold ~Rs 5L Cr)

3. **Portfolio check** — use `portfolio_holdings` MCP tool
   - Are any holdings at risk of index exclusion?
   - Any watchlist stocks being added to indices?

## Output Format

**Index Membership for [TICKER]:**
- Nifty 50: Yes/No
- Nifty Next 50: Yes/No
- Sector Index: [index name]
- Recent change: Added/Removed/No change (date if known)

**Portfolio Index Risk:**
- At risk of exclusion: [stocks near bottom of index by market cap]
- Recently added: [stocks that may see passive inflows]
- Impact: Index changes typically cause 3-5% price movement in the week around rebalance
