Full portfolio review. Run all of these and give me a comprehensive status:

1. Run `uv run diamond dashboard gods_plan` — full dashboard
2. Run `uv run diamond risk gods_plan` — risk metrics
3. Run `uv run diamond attribution gods_plan --period 3M` — performance attribution
4. Run `uv run diamond health gods_plan` — health check

Present as:
- **Overview**: NAV, total return, cash position
- **Risk Profile**: VaR, max drawdown, portfolio beta, volatility
- **Winners & Losers**: Top/bottom 3 contributors with attribution
- **Sector Breakdown**: Over/under-weight sectors
- **Health Alerts**: Any active warnings
- **Recommendations**: Rebalance needed? Sector adjustments? Cash deployment?

Compare performance vs Nifty 50 baseline if data available.
