Month-end comprehensive portfolio review and reporting.

Run all of these:
1. Run `uv run diamond dashboard gods_plan` — full dashboard
2. Run `uv run diamond attribution gods_plan --period 1M` — monthly attribution
3. Run `uv run diamond risk gods_plan` — risk metrics
4. Run `uv run diamond compare gods_plan steady` — strategy comparison
5. Run `uv run diamond compare gods_plan baseline` — vs benchmark
6. Run `uv run diamond tax gods_plan` — tax status
7. Run `uv run diamond health gods_plan` — health check
8. Run `uv run diamond export gods_plan --format all` — generate all reports

Present a full monthly review:
- **Month Performance**: NAV change, total return vs Nifty, vs Steady
- **Attribution**: Top/bottom contributors, sector allocation effects
- **Risk Evolution**: How VaR, drawdown, beta changed over the month
- **Tax Status**: Realized gains YTD, estimated tax liability
- **Portfolio Quality**: Any holdings that dropped below quality thresholds?
- **Rebalance Status**: Last rebalance date, next due, current drift
- **Strategy Health**: gods_plan vs steady vs baseline — which outperformed?
- **Reports Generated**: List exported files for record-keeping

End with forward-looking notes:
- Upcoming corporate actions?
- Rebalance due soon?
- Tax planning considerations (especially Oct-Mar)?