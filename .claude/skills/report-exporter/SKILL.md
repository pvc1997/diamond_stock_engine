---
name: report-exporter
description: Exports portfolio reports in various formats. Auto-activates when the user says "export", "generate report", "download my data", "save reports", "I need a CSV", "give me a summary file", or asks for portfolio documentation.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Report Exporter — Portfolio Documentation

## Trigger Conditions

Activate when:
- User says "export", "generate report", "save report"
- User asks "can I get a CSV?", "download my holdings"
- User says "I need documentation", "print my portfolio"
- User asks "where are my reports?"

## What To Do

1. Use `export_reports` MCP tool for the strategy
2. Run `uv run diamond export gods_plan --format all`
3. Show generated files:
   - Markdown summary
   - CSV holdings
   - CSV trades
   - JSON full export
4. Show file paths in `reports/{strategy}/`
5. Preview the markdown summary (first 20 lines)

## Output Format

**Reports Generated:**
- `reports/gods_plan/summary.md` — Portfolio overview
- `reports/gods_plan/holdings.csv` — Current holdings with prices
- `reports/gods_plan/trades.csv` — Full trade history
- `reports/gods_plan/full_export.json` — Complete data dump

Files are ready at `reports/gods_plan/`.
