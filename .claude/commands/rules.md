Personal investment rules. User input: $ARGUMENTS

Manage personal investment rules that guide trading decisions.

If no $ARGUMENTS or "list":
- Use `personal_rules` MCP tool to list all active rules
- Show grouped by category (buy/sell/risk/general)

If $ARGUMENTS starts with "add":
- Parse the rule text and category from the rest of $ARGUMENTS
- Use `add_personal_rule` MCP tool
- Example: `/rules add buy Never chase a stock up more than 5% in a day`
- Default category is "general" if not specified

If $ARGUMENTS starts with "remove" or "delete":
- Parse the rule ID or text
- Use `remove_personal_rule` MCP tool

If $ARGUMENTS starts with "check":
- Parse the action type (buy/sell)
- Use `check_rules_before_trade` MCP tool
- Show which rules apply to this action

Show rules as a clean checklist:
**Buy Rules:**
- Never buy on the day of earnings results
- Always check sector exposure before adding

**Sell Rules:**
- Hold for at least 1 year unless stop-loss triggers

**Risk Rules:**
- Maximum 3 stocks per sector