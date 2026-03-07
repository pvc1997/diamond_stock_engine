Sector analysis and exposure check. User input: $ARGUMENTS

1. Run `uv run diamond dashboard gods_plan` — get sector breakdown
2. Run `uv run diamond pulse` — market sector rotation data

Present sector analysis:
- **Current Exposure**: Table of sectors with weight %, stock count, and vs target
- **Concentration Check**: Any sector above 25% cap or >4 stocks?
- **Sector Rotation**: Which sectors are leading/lagging today?
- **Diversification Score**: How spread out vs concentrated?

If $ARGUMENTS contains a sector name (e.g., `/sector financials`):
- Show all holdings in that sector
- Sector performance vs Nifty
- Overweight or underweight assessment

If $ARGUMENTS contains a ticker (e.g., `/sector RELIANCE`):
- Run `uv run diamond analyze <TICKER>.NS` for sector context
- Show what sector it belongs to and current sector weight

Highlight:
- Sectors at or near the 25% cap — risk of over-concentration
- Sectors with 0% exposure — potential diversification opportunity
- Sectors rotating into strength — potential buy candidates

End with: any sector-driven trade suggestions (trim overweight sector, add to underweight).