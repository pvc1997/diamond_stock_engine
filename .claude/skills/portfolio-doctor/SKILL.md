---
name: portfolio-doctor
description: Diagnoses and fixes portfolio problems. Use when the user says "fix my portfolio", "what's wrong", "help", "portfolio is red", "losing money", "what should I do", or expresses concern about their holdings.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Portfolio Doctor — Diagnose & Prescribe

## Diagnosis (run all in parallel)

1. `portfolio_status` — NAV, cash, holdings count, return
2. `risk_report` — VaR, drawdown, beta, volatility, signals
3. `health_check` — all health alerts
4. `actionable_alerts` — critical and warning alerts
5. `drift_analysis` — position drift from targets
6. `sector_exposure` — concentration issues

## Triage by Severity

### CRITICAL (act today)
- **Stop-loss breaches**: Stocks down >10% from cost. Recommend sell with command.
- **Delisted stocks**: No price data. Recommend cleanup: `uv run diamond cleanup gods_plan`
- **Risk gate triggers**: Drawdown >15%. Recommend going defensive.

### WARNING (act this week)
- **Overweight positions**: >10% weight. Recommend trim: `uv run diamond trim gods_plan`
- **High drift**: >5% from target. Recommend partial rebalance.
- **Sector concentration**: >25% in one sector. Identify which stocks to reduce.
- **Quality drops**: Stocks that no longer pass the strategy screen.

### MONITOR (keep watching)
- **Approaching limits**: Positions at 8-10% weight
- **Correlation creep**: Avg pairwise > 0.70
- **Volatility rising**: Approaching 30% annualized

## Prescription Format

For each issue found:
1. **Problem**: One-line description
2. **Impact**: What happens if you ignore it (INR terms where possible)
3. **Fix**: Exact command to resolve it
4. **Priority**: Today / This week / Monitor

End with: "Top 3 actions for today:" — numbered, specific, with commands.

If portfolio is healthy: "Your portfolio is in good shape. Next check: tomorrow's /morning"