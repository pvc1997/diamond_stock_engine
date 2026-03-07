Full system health check. User input: $ARGUMENTS

Run all diagnostics:
1. Run `uv run diamond health gods_plan` — portfolio health alerts
2. Run `uv run diamond alerts gods_plan` — actionable alerts
3. Run `uv run diamond status` — cross-strategy status
4. Run `uv run diamond drift gods_plan` — drift from targets

Present a system health dashboard:
- **Portfolio Health**: Any CRITICAL or WARNING alerts? Count and severity.
- **Drift Status**: Max drift %, rebalance trigger status
- **Data Freshness**: When was the last rebalance? Last trade? Stale data risk?
- **Active Strategies**: Which strategies have holdings? NAV for each.
- **Pending Issues**: Delisted stocks, overweight positions, stop-loss breaches
- **Kite Session**: If live mode, is the session still valid?

Health verdict:
- HEALTHY: No alerts, drift <5%, recent rebalance
- NEEDS ATTENTION: Warnings present, drift 5-10%, or overdue rebalance
- ACTION REQUIRED: Critical alerts, drift >10%, or delisted stocks

If $ARGUMENTS contains a strategy name, focus on that strategy.

End with top 1-3 recommended actions to get back to HEALTHY status.