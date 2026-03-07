---
name: risk-alert
description: Proactive risk monitoring that activates when discussing portfolio performance, losses, drawdowns, or when any conversation involves portfolio health. Also triggers on "I'm worried", "portfolio is down", "what's my exposure", "am I safe?", or concern about market risk.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Risk Alert — Proactive Risk Monitor

## Always Check These (parallel)

1. `risk_report` — VaR, CVaR, drawdown, beta, volatility, de-risking signals
2. `health_check` — all health alerts with severity
3. `portfolio_status` — NAV, day change, total return
4. `correlation_matrix` — concentration risk via correlation

## Risk Dashboard

Present concisely:

### Portfolio Risk Metrics
| Metric | Value | Status |
|--------|-------|--------|
| Drawdown from HWM | X% | OK/WARNING/CRITICAL |
| 1-Day VaR (95%) | INR X,XXX | OK/WARNING |
| Portfolio Beta | X.XX | LOW/NORMAL/HIGH |
| Annualized Vol | X% | OK/WARNING |
| Avg Correlation | 0.XX | OK/WARNING |

### Active Signals
List any de-risking signals with severity and recommended action.

### Stress Scenario
"If Nifty drops 10% from here, your portfolio would lose approximately INR X,XXX (Y%)"
Use portfolio beta for quick estimate: loss = beta * market_drop * NAV

## Response to Worry

When the user expresses concern:
1. Acknowledge the feeling (markets are volatile)
2. Show objective risk metrics (how bad IS it really?)
3. Compare to strategy design parameters (god's plan targets <30% max drawdown)
4. Put in historical context (2020 COVID was -38%, 2022 was -18%)
5. Recommend specific action OR reassure that current levels are within design parameters

## Escalation
- If drawdown > 15%: "This is beyond design parameters. Consider raising cash."
- If VaR > 5% of NAV: "Unusually high daily risk. Review position sizes."
- If all metrics green: "Portfolio risk is within normal bounds. Stay the course."