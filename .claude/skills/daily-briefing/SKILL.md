---
name: daily-briefing
description: Runs daily/weekly/monthly portfolio briefings. Auto-activates when the user says "good morning", "what's happening today?", "daily update", "weekly review", "month-end review", "catch me up", "what did I miss?", or greets at the start of a session.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Daily Briefing — Routine Portfolio Updates

## Trigger Conditions

Activate when:
- User greets: "good morning", "hi", "hey" (during market hours)
- User asks: "what's happening today?", "catch me up", "what did I miss?"
- User asks for "daily update", "weekly review", "month-end review"
- User says "brief me", "any news?", "how are we doing?"
- Monday morning (compose with weekly-digest hook)

## What To Do

**Morning / Daily** (default):
1. `market_pulse` — one-line verdict (DEPLOY/WAIT/DEFENSIVE) + Nifty + VIX
2. `portfolio_status` — NAV + day change
3. `health_check` — any alerts
4. `daily_streak` — streak status

**Weekly** (if user says "weekly", "week in review", or it's Monday):
1. All of the above, plus:
2. `performance_attribution` — top/bottom contributors
3. `risk_report` — risk snapshot
4. `drift_analysis` — any drift from targets
5. `portfolio_status` for baseline — benchmark comparison

**Monthly** (if user says "monthly", "month-end", "end of month"):
1. All of weekly, plus:
2. `export_reports` — generate all report files
3. `tax_report` — YTD capital gains
4. `cost_breakdown` — transaction costs review
5. `sector_exposure` — sector balance check

## Output Format

Keep morning briefings under 15 lines. Weekly under 30. Monthly can be comprehensive.

Always end with: "The one thing to do today: [specific action or 'All clear']"
