Evaluate buying opportunities. User input: $ARGUMENTS

1. Run `uv run diamond pulse` — check market verdict first
2. Run `uv run diamond accumulate --opportunities` — quality-ranked buy candidates
3. Run `uv run diamond screen` — fresh screener scores

Based on the results:
- If verdict is DEFENSIVE: recommend waiting, explain why
- If verdict is WAIT: show opportunities but flag that only 30% cash should deploy
- If verdict is DEPLOY: rank top 3-5 stocks to buy with reasoning

For each recommended stock, explain:
- Quality score and what drives it
- Current price context (near support? oversold RSI?)
- How it fits the portfolio (sector diversification, correlation)
- Suggested allocation amount

If the user named a specific stock in $ARGUMENTS (e.g., `/buy RELIANCE`), also run:
- `uv run diamond analyze <TICKER>.NS` — deep technical + fundamental analysis
- `uv run diamond sentiment <TICKER>.NS` — AI sentiment verdict

End with: "To execute, run: `uv run diamond accumulate --deploy`" or the appropriate paper/live command.