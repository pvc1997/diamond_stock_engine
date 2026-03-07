Run stress tests and what-if scenarios. User input: $ARGUMENTS

Parse user input to determine scenario type:
- If contains a negative number (e.g., "-10", "-20%"): `uv run diamond scenario --crash <number>`
- If contains "add" + number (e.g., "add 50000"): `uv run diamond scenario --add <amount>`
- If contains "compare" or "vs" + two tickers: `uv run diamond scenario --compare TICKER1:TICKER2`
- If contains "add"/"remove" + ticker: `uv run diamond whatif gods_plan --add <TICKER>` or `--remove <TICKER>`
- If empty or unclear: run a default -10% crash test

Present results clearly:
- Per-stock impact (beta-adjusted)
- Portfolio-level drawdown
- Which stocks are most/least vulnerable
- Recovery outlook based on historical patterns
- Whether current risk levels are acceptable