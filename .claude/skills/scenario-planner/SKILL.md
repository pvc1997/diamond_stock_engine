---
name: scenario-planner
description: Runs stress tests and what-if scenarios on the portfolio. Auto-activates when the user says "what if market crashes?", "stress test", "what happens if Nifty drops 10%?", "simulate a crash", "what if I add 50k?", "worst case scenario", or discusses hypothetical market events.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Scenario Planner — Stress Tests & What-If Analysis

## Trigger Conditions

Activate when:
- User asks "what if market crashes 10%?"
- User says "stress test", "worst case"
- User asks "what if I add 50k?", "simulate adding cash"
- User says "what if I remove TCS?", "what if I add Reliance?"
- User mentions war, recession, rate hike impact

## What To Do

**Market crash** ("what if market drops X%"):
- Use `scenario_stress` MCP tool with the percentage
- Show per-stock impact using beta
- Show portfolio-level loss estimate

**Add cash** ("what if I add X"):
- Use `scenario_cash` MCP tool
- Show how new capital would be deployed
- Show projected portfolio after deployment

**Stock change** ("what if I add/remove X"):
- Use `whatif_simulation` MCP tool
- Show before/after: NAV, sector exposure, risk metrics

**Historical scenario** ("what if 2008 happens again?"):
- Reference historical drawdowns
- Apply similar % decline using beta-adjusted impact

## Output Format

**Scenario: Market crashes -10%**

| Stock | Beta | Impact | New Value |
|-------|------|--------|-----------|
| RELIANCE.NS | 1.2 | -12.0% | Rs X |
| TCS.NS | 0.7 | -7.0% | Rs X |

**Portfolio Impact:** -Rs X (-Y%)
**Recovery estimate:** N months based on historical precedent
**Action:** [HOLD / harvest tax losses / deploy cash into quality]
