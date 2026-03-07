Simulate portfolio changes. User input: $ARGUMENTS

Default strategy: gods_plan.

Parse $ARGUMENTS:
- "add TICKER": `uv run diamond whatif gods_plan --add TICKER.NS` — simulate adding a stock
- "remove TICKER": `uv run diamond whatif gods_plan --remove TICKER.NS` — simulate removing
- "swap TICKER1 TICKER2": run remove TICKER1 then add TICKER2 simulations
- If just a ticker: assume "add"

Show the impact:
- Portfolio beta change
- Sector concentration change
- Estimated return impact
- Correlation with existing holdings
- Verdict: "This improves/worsens diversification"