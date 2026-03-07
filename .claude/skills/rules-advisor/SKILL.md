---
name: rules-advisor
description: Manages personal investment rules and guardrails. Auto-activates when the user says "my rules", "investment rules", "add a rule", "what are my guardrails?", "trading discipline", "I keep making this mistake", or discusses personal investment constraints.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Rules Advisor — Personal Investment Guardrails

## Trigger Conditions

Activate when:
- User asks "my rules", "what are my rules?"
- User says "add a rule", "I want a rule that..."
- User mentions "trading discipline", "guardrails"
- User says "I keep making this mistake", "remind me to..."
- Before any trade (compose with trade-guard, check applicable rules)

## What To Do

**List** (default):
- Use `personal_rules` MCP tool
- Group by category: buy, sell, risk, general

**Add**:
- Use `add_personal_rule` MCP tool
- Parse the rule text and category from conversation
- Confirm: "Rule added: '[text]' in [category] category"

**Remove**:
- Use `remove_personal_rule` MCP tool
- Confirm before removing

**Pre-trade check**:
- Use `check_rules_before_trade` MCP tool
- Show applicable rules as reminders before executing

## Output Format

**Your Investment Rules:**

**Buy Rules:**
- Never buy on the day of earnings results
- Always check sector exposure before adding

**Sell Rules:**
- Hold for at least 1 year unless stop-loss triggers

**Risk Rules:**
- Maximum 3 stocks per sector

To add: "Add a rule: never buy more than 2 stocks per week"
To remove: tell me which rule to delete.
