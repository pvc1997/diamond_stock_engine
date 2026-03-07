Save or manage portfolio snapshots. User input: $ARGUMENTS

If no $ARGUMENTS or "save":
- Use `portfolio_snapshot` MCP tool to save current state
- Name: auto-generate as YYYY-MM-DD or use name from $ARGUMENTS
- Confirm: "Snapshot saved as '[name]' — NAV Rs [X], [N] stocks"

If $ARGUMENTS is "list":
- Use `list_snapshots` MCP tool
- Show all saved snapshots with date, NAV, stock count

If $ARGUMENTS starts with "delete":
- Delete the named snapshot

If $ARGUMENTS starts with "load" or is a snapshot name:
- Show the snapshot details: holdings, prices, NAV at that time