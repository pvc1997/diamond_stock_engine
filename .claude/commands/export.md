Export portfolio reports. User input: $ARGUMENTS

Default strategy: gods_plan. Default format: all.
Parse $ARGUMENTS for strategy name and/or format (markdown, csv, json, all).

Run `uv run diamond export <strategy> --format <format>`

After export, show:
- List of generated files with paths
- Quick preview of the markdown summary (first 20 lines)
- Reminder: files are in `reports/<strategy>/`