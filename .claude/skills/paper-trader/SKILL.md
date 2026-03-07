---
name: paper-trader
description: Manages paper trading portfolios. Auto-activates when the user says "paper trade", "simulate trades", "practice portfolio", "test without real money", "paper portfolio status", "promote to live", "go live", or discusses virtual trading.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Paper Trader — Virtual Portfolio Management

## Trigger Conditions

Activate when:
- User mentions "paper trade", "paper portfolio", "virtual portfolio"
- User asks "can I test this without real money?"
- User says "start a practice portfolio", "simulate"
- User asks "how is my paper portfolio doing?"
- User says "promote to live", "go live", "ready for real trading?"

## What To Do

**Status check** (default):
- Use `portfolio_status` for the paper strategy
- Show NAV, return, holdings count, days active

**Start new**:
- Run `uv run diamond paper gods_plan --capital <amount>`
- Default capital: 500000

**Promote assessment**:
- Use `portfolio_status` for paper and live
- Check: 30+ days active? Positive returns? Outperforming baseline?
- Run `assess_promotion` MCP tool

**Promotion** (requires explicit confirmation):
- Run `uv run diamond promote gods_plan --execute`
- ALWAYS ask for confirmation first

## Output Format

**Paper Portfolio Dashboard:**
- NAV: Rs X (+Y% since start)
- Days Active: N
- Holdings: N stocks
- Promotion Ready: Yes/No (criteria: 30 days, positive return, beats baseline)

For new users, always suggest paper trading first before live.
