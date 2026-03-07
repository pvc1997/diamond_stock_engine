---
name: portfolio-visualizer
description: Creates visual portfolio representations. Auto-activates when the user says "show me a heatmap", "visualize my portfolio", "portfolio map", "color-coded view", "show returns by sector", or asks for a visual breakdown of holdings.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Portfolio Visualizer — Visual Portfolio Breakdown

## Trigger Conditions

Activate when:
- User says "heatmap", "visualize", "visual breakdown"
- User asks "show me my portfolio visually", "color-coded"
- User says "returns by sector", "sector map"
- User asks "what does my portfolio look like?"

## What To Do

1. Use `portfolio_heatmap` MCP tool
   - Default period: total return
   - Parse for "day", "week", "month" if mentioned

2. Present as a text-based heatmap grouped by sector

## Output Format

Group stocks by sector, sort by return. Use visual indicators:

**Portfolio Heatmap (total return):**

**IT Services** (18.2% weight)
  INFY.NS       +15.3%  Rs 48K  (6.2%)
  TCS.NS        +12.1%  Rs 42K  (5.4%)

**Banking** (14.5% weight)
  ICICIBANK.NS  +16.2%  Rs 45K  (5.8%)
  HDFCBANK.NS   +10.5%  Rs 38K  (4.9%)

**Pharma** (6.8% weight)
  SUNPHARMA.NS  +2.1%   Rs 28K  (3.6%)
  DRREDDY.NS    -4.2%   Rs 25K  (3.2%)

Positive = good, negative = flagged. Biggest weights first.
