---
name: backtester
description: Runs walk-forward backtests on strategies. Auto-activates when the user says "backtest", "how would this have performed?", "historical performance", "test this strategy", "simulate from 2020", or asks about past strategy returns.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Backtester — Historical Strategy Simulation

## Trigger Conditions

Activate when:
- User mentions "backtest", "back-test", "historical performance"
- User asks "how would gods_plan have done since 2020?"
- User says "test this strategy", "simulate", "run it from 2015"
- User asks "what's the CAGR?", "what's the Sharpe ratio?"

## What To Do

1. Parse the request for:
   - Strategy name (default: gods_plan)
   - Start date (default: 2020-01-01)
   - End date (default: today)

2. Run `run_backtest` MCP tool with parsed parameters

3. Present results:
   - **CAGR**: Annualized return
   - **Sharpe Ratio**: Risk-adjusted performance
   - **Max Drawdown**: Worst peak-to-trough decline
   - **Win Rate**: % of positive rebalance windows
   - **vs Nifty 50**: Benchmark comparison

4. Add context:
   - "This period included [major events: COVID, rate hikes, etc.]"
   - "Past performance doesn't guarantee future results, but the strategy held up through [X]"

## Output Format

**Backtest: [strategy] from [start] to [end]**
| Metric | Strategy | Nifty 50 |
|--------|----------|----------|
| CAGR | X% | Y% |
| Sharpe | X | Y |
| Max DD | -X% | -Y% |

Note: Backtests use walk-forward methodology with no look-ahead bias.
