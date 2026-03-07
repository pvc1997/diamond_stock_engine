---
name: snapshot-manager
description: Saves and compares portfolio checkpoints. Auto-activates when the user says "save a snapshot", "take a checkpoint", "compare to last month", "what changed?", "portfolio diff", "how has my portfolio changed?", or discusses tracking portfolio evolution over time.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Snapshot Manager — Portfolio Version Control

## Trigger Conditions

Activate when:
- User says "save a snapshot", "checkpoint", "bookmark this"
- User asks "what changed since last month?", "how has my portfolio evolved?"
- User says "compare to [date/name]", "diff", "what's different?"
- User asks "show my snapshots", "list checkpoints"

## What To Do

**Save** (default if no comparison asked):
- Use `portfolio_snapshot` MCP tool
- Auto-name as YYYY-MM-DD unless user gives a name

**List**:
- Use `list_snapshots` MCP tool
- Show all saved checkpoints with date, NAV, stock count

**Compare**:
- Use `portfolio_diff` MCP tool
- Show added/removed stocks, weight changes, NAV change
- Present as a clean diff

## Output Format

**Snapshot saved: "march-rebalance"**
- NAV: Rs 5,20,000 | 18 stocks | Cash: Rs 15,000

**Diff: march-rebalance vs current:**
```
+ Added: RELIANCE.NS (5.2%)
- Removed: TATATECH.NS (was 3.1%)
~ Changed: TCS.NS (4.5% -> 6.2%)
NAV: Rs 4,50,000 -> Rs 5,20,000 (+15.6%)
```
