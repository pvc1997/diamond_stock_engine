---
name: rebalance-advisor
description: Advises on whether and how to rebalance the portfolio. Activates when the user asks "should I rebalance?", "is it time to rebalance?", "portfolio is drifting", "positions are off", or discusses portfolio alignment with targets.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Rebalance Advisor — Smart Rebalancing Guidance

## Assessment (parallel)

1. `drift_analysis` — current drift from targets per position
2. `rebalance_check` — is rebalance due? Days since last, threshold status
3. `portfolio_holdings` — current weights
4. `risk_report` — risk context for rebalance decision
5. `market_pulse` — should we rebalance in this market?
6. `estimate_costs_portfolio` — transaction cost of full rebalance

## Decision Framework

### Don't Rebalance If:
- Max drift < 5% (within tolerance)
- Last rebalance was < 30 days ago (too soon)
- Market verdict is DEFENSIVE (bad time for turnover)
- Transaction costs > expected drift recovery

### Partial Rebalance If:
- 1-3 positions drifted > 5% but most are fine
- Use `uv run diamond drift gods_plan --rebalance` for targeted fixes
- Lower cost, lower tax impact

### Full Rebalance If:
- Max drift > 10% OR multiple positions drifted > 5%
- Last rebalance was > 90 days ago
- Strategy screen has changed significantly (new stocks in, old stocks out)

## Output

### Drift Summary
| Position | Current | Target | Drift | Action |
|----------|---------|--------|-------|--------|
Top 5 most drifted positions

### Recommendation
- **SKIP**: "Drift is minimal. Next check in X days."
- **PARTIAL**: "Fix these 2-3 positions. Estimated cost: INR X. Command: `uv run diamond drift gods_plan --rebalance`"
- **FULL**: "Full rebalance recommended. Preview: `uv run diamond run gods_plan --dry-run`"

### Cost/Benefit
- Estimated transaction costs
- Estimated tax impact (sells trigger capital gains)
- Expected improvement in risk-adjusted returns