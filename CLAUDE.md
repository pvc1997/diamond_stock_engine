# Diamond Stock Engine

Systematic Indian equity portfolio management engine.

## Quick Reference

```bash
# Run a strategy
diamond run baseline --capital 500000
diamond run steady --capital 100000
diamond run gods_plan --capital 500000

# Paper trade first (simulated, no real orders)
diamond paper baseline --capital 500000
diamond paper baseline --status
diamond paper baseline --reset

# Promote paper to live when confident
diamond promote baseline
diamond promote baseline --execute

# Backtest
diamond backtest baseline --start 2010-01-01 --end 2025-01-01

# Targeted trades (single stock)
diamond sell gods_plan TATATECH.NS            # Sell all shares
diamond sell gods_plan TATATECH.NS -n 10      # Sell 10 shares
diamond sell gods_plan TATATECH.NS --dry-run  # Preview only
diamond buy gods_plan RELIANCE.NS -a 50000    # Buy ~50K worth
diamond buy gods_plan RELIANCE.NS -n 10       # Buy 10 shares

# Portfolio maintenance
diamond cleanup gods_plan              # Write off delisted stocks
diamond trim gods_plan                 # Trim positions > 10% weight
diamond alerts gods_plan               # Show actionable alerts
diamond alerts gods_plan --act         # Act on alerts (interactive)
diamond drift gods_plan --rebalance    # Partial rebalance for drift

# Risk & monitoring
diamond risk baseline
diamond health baseline
diamond status

# Corporate actions (auto-runs before rebalance too)
diamond actions baseline

# Screener & sentiment
diamond screen
diamond sentiment RELIANCE.NS

# Kite integration
diamond kite --auth
```

## Architecture

```
src/diamond/
  config.py              - Pydantic Settings, .env loading, singleton via get_config()
  cli.py                 - Typer CLI, single entry point

  data/
    market.py            - yfinance wrapper with retry + file cache
    universe.py          - NSE 500 ticker list, sector mapping
    ledger.py            - SQLite-backed trade ledger (ACID, queryable)
    corporate_actions.py - Split/bonus/dividend detection + ledger adjustment
    earnings.py          - Upcoming quarterly results calendar (yfinance)
    rules.py             - Personal investment rules (JSON-backed CRUD)
    snapshots.py         - Portfolio checkpoints: save, load, diff

  analysis/
    screener.py          - Alpha/Beta/CAGR/Volatility/Hurst calculation
    optimizer.py         - Monte Carlo + inverse-volatility weighting
    sentiment.py         - Gemini AI + heuristic fallback
    liquidity.py         - Volume/ADV check, stagger suggestions
    insider.py           - Insider/promoter activity tracking (yfinance)

  strategies/
    base.py              - Strategy Protocol (screen -> allocate -> should_rebalance)
    baseline.py          - Nifty 50 equal-weight benchmark
    steady.py            - Low-beta quality, inverse-vol weighted, capital protection
    gods_plan.py         - 55% quality growth + 25% defensive + 20% value
    constraints.py       - Sector caps + position weight limits

  execution/
    costs.py             - Indian market cost model (pure function, INR)
    executor.py          - Full rebalance + targeted sell/buy/cleanup/trim
    paper.py             - Paper trading mode (separate ledger, no real orders)
    promote.py           - Paper-to-live promotion with confidence scoring
    kite.py              - Zerodha Kite Connect + CDSL authorization

  backtest/
    engine.py            - Walk-forward orchestrator (temporal isolation, position continuity)
    reporter.py          - Metrics (CAGR, Sharpe, drawdown) + markdown reports

  monitoring/
    risk.py              - VaR/CVaR, correlation, drawdown HWM, de-risking signals
    alerts.py            - Drawdown/stop-loss/drift/concentration health checks
```

## Strategies

### Baseline (benchmark)
- Equal-weight Nifty 50
- No market cap dependency — reliable in backtests
- Quarterly rebalancing

### Steady (capital protection)
- 15-18 low-beta quality stocks from NSE 500
- Filters: Beta < 1.0, Alpha > 0, CAGR > 10%, Vol < 30%
- Inverse-volatility weighting + sector caps
- Target: 15-18% CAGR, <25% max drawdown

### God's Plan (aggressive growth)
- 55% Quality Growth: high-alpha trending stocks, inverse-vol weighted
- 25% Defensive Anchor: low-beta quality for downside protection
- 20% Opportunistic Value: low P/B + positive alpha
- 15-18 stocks total, no duplicates across components
- Target: 18-22% CAGR, <30% max drawdown

## Key Conventions

- **Strategy Protocol**: All strategies implement `screen()`, `allocate()`, `should_rebalance()` — structural typing via Protocol, not ABC
- **Pure cost model**: `execution/costs.py` has zero side effects, tested with exact INR amounts
- **SQLite ledger**: One `.db` file per strategy in `data/ledgers/`, paper ledgers suffixed `_paper`
- **Config singleton**: `get_config()` loads from `.env`, cached via `@lru_cache`
- **yfinance v2**: MultiIndex columns handled in `data/market.py` — don't flatten elsewhere
- **Fail-open safety**: Risk gate and corporate action sync in executor fail gracefully — never block on external service errors
- **Sell-before-buy**: Executor always sells first to free cash, then buys
- **Targeted operations**: `execute_sell()`, `execute_buy()`, `execute_cleanup()`, `execute_trim()` — single-stock ops that bypass the rebalance cycle
- **Delisted detection**: `check_delisted()` in alerts, `execute_cleanup()` writes off at price 0
- **Concentration enforcement**: Tiered alerts (WARNING at 1.25x, CRITICAL at 1.5x), `execute_trim()` auto-trims to limit
- **Audit trail**: Corporate actions (splits, dividends) recorded as synthetic trades in the ledger

## Backtest Engine

Walk-forward backtesting with:
- **Temporal isolation**: screener only sees data up to screen_end (no look-ahead)
- **Position continuity**: carries shares across windows, only trades the delta
- **Calendar-month windows**: uses relativedelta for proper alignment
- **Realistic costs**: Indian market transaction costs on every trade
- **No final liquidation**: last window's NAV includes held positions at exit prices

## Execution Flow

```
diamond run <strategy>
  1. Screen universe (strategy.screen())
  2. Allocate capital (strategy.allocate())
  3. Sync corporate actions (splits/dividends applied to ledger)
  4. Risk gate check (block on CRITICAL signals, skip on --force)
  5. Calculate trades (delta from current holdings to target)
  6. Execute: sells first, then buys, record to ledger
```

## Testing

```bash
pytest                          # All tests
pytest tests/test_costs.py      # Cost model only
pytest tests/test_strategies.py # Strategy tests
pytest -x                       # Stop on first failure
```

Tests use `tmp_path` fixtures for isolated SQLite ledgers. Market data is mocked — tests never hit real APIs.

## Configuration

All settings in `.env` (see `.env.example`). Key sections:
- **AI**: Gemini API key, model, rate limits (15 RPM)
- **Cache**: TTLs for prices (4h), screener (24h), sentiment (1h)
- **Portfolio**: Max position weight (10%), sector caps (4 stocks, 25%)
- **Risk**: Stop-loss (10%), cooldown (5 days), initial capital
- **Rebalancing**: Frequency (90 days), drift threshold (5%), min trade (1000 INR)
- **God's Plan**: Core filters (alpha, CAGR, Hurst, beta), value max P/B, drawdown threshold
- **Kite**: API key/secret, dry-run mode (default true), circuit breaker (5%)

## Risk Management

The risk engine (`monitoring/risk.py`) computes:
- **VaR/CVaR**: Historical 95% and 99% Value-at-Risk, Expected Shortfall
- **Drawdown**: Tracked against high-water mark (persisted in ledger state)
- **Correlation**: Pairwise correlation matrix, max and average
- **Beta**: Portfolio beta vs Nifty 50
- **Volatility**: Annualized from daily portfolio returns

De-risking signals auto-generated at these thresholds:
- Drawdown WARNING at 10%, CRITICAL at 15% from HWM
- VaR WARNING when 1-day VaR > 3% of NAV
- Correlation WARNING when avg pairwise > 0.80
- Volatility WARNING when annualized > 30%

CRITICAL signals block the executor (override with `--force`).

## Daily Investing Guide (Claude Code Interface)

When the user opens Claude Code in this project, treat it as an investing terminal. All commands accept arguments via `$ARGUMENTS`.

### Slash Commands — Quick Reference

**Daily Routine:**
| Command | What it does |
|---------|-------------|
| `/morning` | Quick pre-market scan — verdict + NAV + alerts + streak (compact) |
| `/daily` | Full morning briefing — market + portfolio + sectors + opportunities |
| `/weekly` | Weekly review — attribution + risk + drift + benchmark comparison |
| `/monthly` | Month-end full review + export all reports |

**Trading Decisions:**
| Command | What it does |
|---------|-------------|
| `/buy` | Evaluate buy opportunities with market-aware sizing |
| `/buy RELIANCE` | Deep-dive a specific stock before buying |
| `/sell` | Review what to trim/sell with tax-smart ordering |
| `/sell TCS` | Focused sell analysis on a specific stock |
| `/analyze INFY` | Full technical + fundamental + sentiment analysis |
| `/whatif add HDFC` | Simulate adding/removing a stock |
| `/peers INFY` | Quick peer comparison table (same sector) |
| `/movers` | Today's biggest portfolio gainers and losers |
| `/movers week` | Weekly movers |

**Portfolio Management:**
| Command | What it does |
|---------|-------------|
| `/portfolio` | Comprehensive portfolio review with attribution |
| `/status` | Quick cross-strategy overview |
| `/drift` | Check position drift from targets |
| `/rebalance` | Preview rebalance trades with cost/tax estimates |
| `/orders` | View/manage pending orders |
| `/compare gods_plan steady` | Side-by-side strategy comparison |
| `/sector` | Sector exposure, rotation signals, concentration check |
| `/accumulate` | Manage buy-only portfolio (status/deploy/add cash/review) |
| `/paper` | Paper trading: status, reset, promote to live |
| `/snapshot` | Save portfolio checkpoint for later comparison |
| `/snapshot list` | List all saved snapshots |
| `/diff checkpoint1` | Compare current portfolio vs a saved snapshot |
| `/heatmap` | Sector-grouped return heatmap |
| `/heatmap day` | Today's return heatmap |
| `/costs` | Total transaction costs breakdown |
| `/income` | Dividend + realized gains income report |

**Risk & Monitoring:**
| Command | What it does |
|---------|-------------|
| `/risk` | Quick risk snapshot — VaR, drawdown, beta, volatility |
| `/alerts` | Actionable alerts with fix-it suggestions |
| `/alerts fix` | Interactively resolve all alerts |
| `/health` | Full system health check — data, drift, sessions, alerts |
| `/cleanup` | Write off delisted stocks, trim overweight, fix stop-losses |
| `/watch` | Manage watchlist — view alerts, add/remove stocks |
| `/watch add RELIANCE 2500` | Add stock with target price |
| `/tax` | Capital gains tax report (STCG/LTCG) |
| `/scenario -10` | Stress test a market crash |
| `/scenario add 50000` | Simulate adding cash |
| `/calendar` | Upcoming earnings, dividends, corporate action dates |
| `/calendar TCS` | Calendar for a specific stock |
| `/rules` | Personal investment rules (list/add/remove) |
| `/rules add buy Never chase a stock up 5%` | Add a buy rule |

**Broker & Export:**
| Command | What it does |
|---------|-------------|
| `/kite auth` | Zerodha Kite login flow |
| `/reconcile` | Compare ledger vs Kite holdings, flag discrepancies |
| `/export` | Generate all reports (MD + CSV + JSON) |
| `/backtest steady 2015 2025` | Walk-forward backtest |
| `/replay 2020-03` | "What if you started in March 2020?" simulation |

**Learning:**
| Command | What it does |
|---------|-------------|
| `/learn` | Daily investing lesson using your portfolio |
| `/learn beta` | Teach a specific concept |

### Global Commands (work from any project)
| Command | What it does |
|---------|-------------|
| `/market` | Quick market pulse from anywhere |
| `/pf` | Portfolio snapshot from anywhere |

### Auto-Triggering Skills (no slash needed)

Skills in `.claude/skills/` auto-activate based on conversation context. They use MCP tools for structured data and provide intelligent, context-aware responses.

| Skill | Auto-triggers on | What it does |
|-------|-----------------|-------------|
| `trade-guard` | Any buy/sell execution intent | Pre-trade safety: market + risk + constraints check (GREEN/YELLOW/RED) |
| `stock-research` | "Should I buy X?", "What about X?", ticker mentions | Deep MCP-powered analysis: technicals + fundamentals + portfolio fit + verdict |
| `portfolio-doctor` | "Fix my portfolio", "what's wrong", concern about losses | Diagnoses issues, prescribes fixes with exact commands, triages by severity |
| `tax-optimizer` | Sell discussions, "tax", "harvest", "STCG/LTCG" | Tax impact analysis before any sell, optimal sell ordering, harvesting suggestions |
| `market-context` | "Is it a good time?", "how's the market?", timing questions | Market regime analysis with VIX interpretation and deployment guidance |
| `explain-trade` | "Why did we buy X?", "what's the rationale?" | Trade history, original rationale, performance since entry, thesis check |
| `position-sizer` | "How much should I buy?", "what size?", allocation questions | Optimal sizing: position caps + market adjustment + volatility scaling |
| `risk-alert` | "Am I safe?", "what's my exposure?", portfolio concern | Proactive risk dashboard with stress scenario and historical context |
| `rebalance-advisor` | "Should I rebalance?", "positions are off", drift discussion | Smart rebalance decision: skip vs partial vs full with cost/benefit analysis |
| `sector-rotation` | "Which sectors are hot?", "where is money flowing?" | Sector cycle analysis, rotation signals, portfolio tilt assessment |
| `dividend-tracker` | "Any dividends?", "corporate actions", "stock split" | Dividend income tracking, corporate action verification, upcoming events |
| `peer-compare` | "X vs Y", "which is better?", "swap X for Y" | Head-to-head comparison with portfolio context and swap cost analysis |
| `earnings-calendar` | "Any results coming?", "earnings this week" | Flags portfolio stocks with upcoming quarterly results, pre-trade warning |
| `drawdown-coach` | "I'm worried", "portfolio is red", panic selling | Behavioral coaching: historical context, rational analysis, action plan |
| `correlation-guard` | Before buying a new stock | Warns if new stock is correlated >0.75 with existing holding |
| `sip-planner` | "SIP", "monthly investment", "DCA" | Monthly deployment plan with market-adjusted sizing |
| `liquidity-check` | Trades > Rs 50K, "volume", "illiquid" | ADV check, slippage estimate, stagger plan if needed |
| `insider-tracker` | "Insider buying?", "promoter holding", "bulk deals" | Promoter/institutional activity signals for portfolio stocks |
| `index-rebalance` | "Nifty changes", "index inclusion" | Index membership check, passive flow impact analysis |
| `cash-manager` | "How much cash?", "deploy cash", "cash drag" | Cash position analysis, deployment schedule by market regime |
| `exit-strategy` | "When should I sell?", "target price", "exit plan" | Exit criteria: stop-loss, trailing stop, take-profit, tax-aware timing |
| `multi-account` | "Wife's portfolio", "family", "second account" | Multi-portfolio management with cross-account analysis |
| `daily-briefing` | "Good morning", "daily update", "weekly review", "catch me up" | Runs daily/weekly/monthly briefings via MCP tools |
| `backtester` | "Backtest this", "historical performance", "test steady" | Walk-forward backtesting with benchmark comparison |
| `paper-trader` | "Paper trade", "simulate", "promote to live", "go live" | Paper trading lifecycle: create, status, reset, promote |
| `report-exporter` | "Export", "generate report", "download CSV", "save reports" | Multi-format export: markdown, CSV, JSON |
| `portfolio-overview` | "All my portfolios", "overall status", "big picture" | Cross-strategy overview with combined metrics |
| `order-tracker` | "My orders", "pending orders", "cancel order" | Order lifecycle management and status tracking |
| `snapshot-manager` | "Save a snapshot", "checkpoint", "what changed since?" | Portfolio checkpoints with diff comparison |
| `cost-analyzer` | "How much in fees?", "trading costs", "brokerage charges" | Transaction cost breakdown and optimization |
| `portfolio-visualizer` | "Heatmap", "visualize", "color-coded view" | Sector-grouped return heatmap visualization |
| `historical-replay` | "What if I started in 2020?", "replay", "hindsight" | Hypothetical entry simulation with benchmark |
| `income-tracker` | "How much income?", "dividend income", "portfolio yield" | Dividend + realized gains + projected yield report |
| `rules-advisor` | "My rules", "add a rule", "trading discipline" | Personal investment rules CRUD + pre-trade check |
| `scenario-planner` | "What if market crashes?", "stress test", "worst case" | Stress tests and what-if scenarios with beta impact |

**Session Intelligence (invisible, always-on):**

| Skill | What it does |
|-------|-------------|
| `session-context` | Remembers last ticker/strategy discussed, resolves "it"/"that stock"/"the same one" |
| `ticker-resolver` | Fuzzy matches "HDFC" to HDFCBANK.NS, disambiguates with context |
| `amount-parser` | Converts "2 lakhs", "half my cash", "5% of portfolio" to exact INR |
| `onboarding` | Guides new users through first-time setup (strategy choice, capital, first trade) |

**Conversational Features:**

| Skill | Auto-triggers on | What it does |
|-------|-----------------|-------------|
| `winners-losers` | "My best/worst stocks", "top gainers", "biggest losers" | Portfolio performance rankings by day/week/month/total |
| `goal-tracker` | "Am I on track?", "when will I reach 10L?", "years to 1 crore" | Investment goal progress with projections and milestone tracking |
| `investment-journal` | "Note that...", "my thesis on X is...", "what was my reasoning?" | Save/retrieve investment thesis, trade reflections, personal rules |
| `natural-screen` | "Find me low-PE stocks", "quality IT stocks", "defensive picks" | Plain English stock screening with structured results |
| `undo-trade` | "Undo that", "reverse the buy", "that was a mistake" | Safe trade reversal at current prices with cost disclosure |
| `achievements` | "My achievements", "any milestones?", "badges" | Investment badges, streak milestones, portfolio landmarks |

### Hooks (automatic background tasks)

| Hook | Trigger | What it does |
|------|---------|-------------|
| Streak check-in | Every message | Silently logs daily check-in for streak tracking |
| Welcome-back | First message per session | Detects absence, critical alerts, overdue rebalance (runs once per 2h) |
| Pre-market scan | 8:45-9:30 AM weekdays | Overnight global cues, pre-open alerts (once per morning) |
| Post-market log | After 3:30 PM weekdays | Day's P&L snapshot nudge (once per afternoon) |
| Earnings alert | After 6 PM weekdays | Warns if any portfolio stock reports results tomorrow |
| Weekly digest | First Monday message | Weekly review nudge if not already done |
| Stop-loss check | Hourly during market hours | Alerts if any holding breached stop-loss level |

### Conversational Queries (no slash needed)
Just talk naturally. Skills auto-activate and compose together:
- "How's the market?" → market-context skill + market_pulse MCP
- "Should I buy Reliance?" → stock-research + trade-guard + position-sizer + correlation-guard + liquidity-check
- "TCS vs INFY" → peer-compare skill with both tickers
- "Buy it" (after discussing a stock) → session-context resolves ticker + trade-guard
- "Put 2 lakhs in" → amount-parser + position-sizer
- "What are my winners?" → winners-losers skill
- "I want to hit 20% CAGR" → goal-tracker skill
- "Note: bought TCS because of AI tailwinds" → investment-journal skill
- "Find me safe dividend stocks" → natural-screen skill
- "Undo that last buy" → undo-trade skill
- "Fix my portfolio" → portfolio-doctor skill
- "Any achievements?" → achievements skill
- "What's my risk?" → risk-alert skill
- "Is it time to rebalance?" → rebalance-advisor skill
- "Which sectors are hot?" → sector-rotation skill
- "Why do I own TCS?" → explain-trade + investment-journal
- "Check my taxes before selling" → tax-optimizer skill
- "Any dividends coming?" → dividend-tracker skill
- "I'm new here" → onboarding skill
- "Any earnings coming?" → earnings-calendar skill
- "I'm worried about my portfolio" → drawdown-coach skill
- "Is HDFC correlated with ICICI?" → correlation-guard skill
- "Set up a monthly SIP" → sip-planner skill
- "Can I sell this easily?" → liquidity-check skill
- "Any insider buying?" → insider-tracker skill
- "Is X in Nifty?" → index-rebalance skill
- "Deploy my cash" → cash-manager skill
- "What's my exit plan for TCS?" → exit-strategy skill
- "My wife's portfolio" → multi-account skill
- "Good morning" / "What's happening today?" → daily-briefing skill
- "Backtest gods_plan from 2020" → backtester skill
- "Paper trade steady with 5 lakhs" → paper-trader skill
- "Export my portfolio data" → report-exporter skill
- "Show all my strategies" → portfolio-overview skill
- "Any pending orders?" → order-tracker skill
- "Save a snapshot before rebalance" → snapshot-manager skill
- "How much have I paid in fees?" → cost-analyzer skill
- "Show me a heatmap" → portfolio-visualizer skill
- "What if I started in COVID crash?" → historical-replay skill
- "How much income from my portfolio?" → income-tracker skill
- "Add a rule: never buy on earnings day" → rules-advisor skill
- "What if market drops 15%?" → scenario-planner skill

### MCP Servers (structured data access)

Two MCP servers are configured in `.mcp.json`:

**1. Diamond MCP (`mcp__diamond__*`)** — Portfolio brain: strategy, risk, analysis
- 78 tools returning structured JSON
- Runs on Python 3.13 in `mcp_server/` with its own venv
- Use for: screening, allocation, risk, tax, backtesting, portfolio reasoning

MCP tool categories:
- **Market**: `market_pulse`, `market_screener`, `sector_list`, `stock_sector`
- **Analysis**: `analyze_stock`, `stock_sentiment`, `stock_prices`, `transaction_costs`
- **Portfolio**: `portfolio_status`, `portfolio_holdings`, `portfolio_trades`, `portfolio_summary`
- **Risk**: `risk_report`, `health_check`, `performance_attribution`, `risk_decomposition`
- **Watchlist**: `watchlist_view`, `watchlist_add`, `watchlist_remove`, `watchlist_signals`
- **Tax & Compare**: `tax_report`, `compare_strategies`, `whatif_simulation`, `tax_aware_trades`
- **Daily**: `today_briefing`, `daily_streak`, `learn_topic`
- **Accumulate**: `accumulate_opportunities`, `accumulate_review`, `accumulate_status`, `accumulate_add_cash`
- **Execution**: `preview_rebalance` (dry-run only), `estimate_costs_portfolio`, `order_book`, `corporate_actions`
- **Targeted Trades**: `sell_stock`, `buy_stock`, `cleanup_delisted`, `trim_positions`, `actionable_alerts`
- **Rebalancing**: `drift_analysis`, `rebalance_check`
- **Allocation**: `optimize_weights`, `inverse_vol_weights`, `equal_weight_allocation`, `market_cap_weight_allocation`
- **Analytics**: `correlation_matrix`, `volatility_sizing`, `sector_exposure`, `trade_rationale`, `custom_screen`
- **Backtesting**: `run_backtest`, `export_reports`
- **Scenarios**: `scenario_stress`, `scenario_cash`
- **Paper→Live**: `assess_promotion`, `stagger_entry`, `limit_order`
- **Earnings**: `earnings_calendar`, `earnings_check`
- **Rules**: `personal_rules`, `add_personal_rule`, `remove_personal_rule`, `check_rules_before_trade`
- **Snapshots**: `portfolio_snapshot`, `list_snapshots`, `portfolio_diff`
- **Liquidity**: `liquidity_check`, `portfolio_liquidity`
- **Insider**: `insider_activity`, `portfolio_insider_signals`
- **Cost Analysis**: `cost_breakdown`
- **Index**: `index_membership`
- **Cash**: `cash_position`
- **NAV History**: `historical_nav`
- **Correlation**: `correlation_check`
- **Dividends**: `dividend_yield_portfolio`
- **Visualization**: `portfolio_heatmap`

**2. Zerodha Kite MCP (`mcp__kite__*`)** — Broker hands: real-time data, orders, GTT
- Official Zerodha MCP server at `mcp.kite.trade`
- Requires Kite login (browser OAuth) on first use per session
- Use for: live quotes, order placement, GTT stop-losses, instrument search, reconciliation

Kite MCP tool categories:
- **Auth**: `login`
- **Market Data**: `get_quotes`, `get_ltp`, `get_ohlc`, `get_historical_data`, `search_instruments`
- **Portfolio**: `get_profile`, `get_margins`, `get_holdings`, `get_positions`, `get_mf_holdings`
- **Orders**: `place_order`, `modify_order`, `cancel_order`, `get_orders`, `get_trades`, `get_order_history`, `get_order_trades`
- **GTT**: `get_gtts`, `place_gtt_order`, `modify_gtt_order`, `delete_gtt_order`

**When to use which:**
| Need | Use |
|------|-----|
| Strategy decisions, screening, risk | Diamond MCP (`mcp__diamond__*`) |
| Live price during market hours | Kite MCP (`mcp__kite__get_ltp`) |
| Place/modify/cancel real orders | Kite MCP (`mcp__kite__place_order`) |
| GTT stop-loss/take-profit | Kite MCP (`mcp__kite__place_gtt_order`) |
| Paper trading, backtesting | Diamond MCP (no broker needed) |
| Reconcile ledger vs broker | Both (Diamond holdings + Kite holdings) |
| Historical daily data | Diamond MCP (yfinance, longer history) |
| Intraday candle data | Kite MCP (`mcp__kite__get_historical_data`) |

**Kite-powered skills:**
- `gtt-manager` — Automated stop-loss and take-profit GTT orders
- `live-quotes` — Real-time pricing from exchange (invisible, activates during live sessions)
- `kite-reconciler` — Ledger vs broker truth reconciliation
- `instrument-search` — Find any tradeable stock, including newly listed / outside NSE 500

### Tone
- Be a confident but cautious advisor (conservative bias — WAIT is the default)
- Lead with action items, not theory
- Always show the CLI command so the user can re-run independently
- Never recommend trades without showing risk context first
- Flag tax implications on sells
- Use `/morning` format for quick checks, `/daily` for deep analysis
