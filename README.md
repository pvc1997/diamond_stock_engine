# Diamond Stock Engine

[![CI](https://github.com/YOUR_USERNAME/diamond-stock-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/diamond-stock-engine/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

Systematic Indian equity portfolio management engine with walk-forward backtested strategies, risk management, paper trading, and Zerodha Kite integration.

## Features

- **3 backtested strategies** — Baseline (Nifty 50), Steady (low-beta quality), God's Plan (aggressive growth)
- **Walk-forward backtesting** — temporal isolation, realistic Indian market costs, no look-ahead bias
- **Risk engine** — VaR/CVaR, drawdown tracking, correlation matrix, de-risking signals
- **Paper trading** — full simulation with separate ledger, promotion to live with confidence scoring
- **Zerodha Kite integration** — live order placement, GTT stop-losses, CDSL authorization
- **Accumulate mode** — buy-only long-term portfolio with quality scoring
- **850+ tests** — all mocked, no network calls

## Quick Start

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/YOUR_USERNAME/diamond-stock-engine.git
cd diamond-stock-engine
uv sync

# Configure
cp .env.example .env
# Edit .env with your Gemini API key (optional — for AI sentiment)

# Run a strategy
diamond run baseline --capital 500000
diamond run gods_plan --capital 500000

# Paper trade first (recommended)
diamond paper gods_plan --capital 500000
diamond paper gods_plan --status
```

## Strategies

| Strategy | Stocks | Style | Target CAGR | Max Drawdown |
|----------|--------|-------|-------------|--------------|
| **Baseline** | 50 | Equal-weight Nifty 50 benchmark | Market | ~30% |
| **Steady** | 15-18 | Low-beta quality, inverse-vol weighted | 15-18% | <25% |
| **God's Plan** | 15-18 | 55% growth + 25% defensive + 20% value | 18-22% | <30% |

## Usage

```bash
# Core commands
diamond run <strategy> --capital 500000    # Execute strategy
diamond paper <strategy> --capital 500000  # Paper trade
diamond backtest <strategy> --start 2010-01-01 --end 2025-01-01

# Portfolio management
diamond sell gods_plan TATATECH.NS         # Sell all shares
diamond buy gods_plan RELIANCE.NS -a 50000 # Buy ~50K worth
diamond cleanup gods_plan                  # Write off delisted stocks
diamond trim gods_plan                     # Trim overweight positions
diamond drift gods_plan --rebalance        # Partial rebalance

# Risk & monitoring
diamond risk <strategy>                    # VaR, drawdown, beta
diamond alerts <strategy>                  # Stop-loss, concentration alerts
diamond health <strategy>                  # Full system health check
diamond status                             # Cross-strategy overview

# Analysis
diamond screen                             # Universe screener
diamond sentiment RELIANCE.NS              # AI sentiment analysis
diamond today                              # Daily briefing
diamond watch                              # Watchlist management

# Broker integration
diamond kite --auth                        # Zerodha Kite login
diamond promote <strategy> --execute       # Paper to live
```

## Architecture

```
src/diamond/
  config.py                  Pydantic Settings, .env loading
  cli.py                     Typer CLI entry point
  exceptions.py              Structured exception hierarchy

  data/
    market.py                yfinance wrapper, retry + file cache
    universe.py              NSE 500 tickers, sector mapping
    ledger.py                SQLite trade ledger (ACID, auto-backup)
    corporate_actions.py     Split/bonus/dividend detection + adjustment
    earnings.py              Upcoming quarterly results calendar
    rules.py                 Personal investment rules (JSON-backed)
    snapshots.py             Portfolio checkpoints: save, load, diff
    watchlist.py             Stock watchlist with price alerts

  analysis/
    screener.py              Alpha/Beta/CAGR/Volatility/Hurst scoring
    optimizer.py             Monte Carlo + inverse-volatility weighting
    sentiment.py             Gemini AI + heuristic fallback
    deep.py                  Full technical analysis (RSI, MACD, Bollinger)
    attribution.py           Brinson sector decomposition
    compare.py               Side-by-side strategy comparison
    tax.py                   Capital gains (STCG/LTCG), FIFO lot matching
    liquidity.py             Volume/ADV check, stagger suggestions
    insider.py               Insider/promoter activity tracking
    export.py                Markdown, CSV, JSON report generation
    rationale.py             Trade rationale engine

  strategies/
    base.py                  Strategy Protocol (structural typing)
    baseline.py              Nifty 50 equal-weight benchmark
    steady.py                Low-beta quality, inverse-vol weighted
    gods_plan.py             3-tier aggressive growth basket
    accumulate.py            Buy-only long-term portfolio
    constraints.py           Sector caps + position weight limits

  execution/
    costs.py                 Indian market cost model (STT, GST, stamp duty)
    executor.py              Rebalance + targeted sell/buy/cleanup/trim
    paper.py                 Paper trading (separate ledger)
    promote.py               Paper-to-live promotion scoring
    smart_rebalance.py       Drift detection, volatility-adjusted sizing
    orders.py                Order lifecycle management
    kite.py                  Zerodha Kite Connect + CDSL authorization
    live.py                  Live execution with interactive confirmation

  backtest/
    engine.py                Walk-forward orchestrator (temporal isolation)
    reporter.py              CAGR, Sharpe, drawdown + markdown reports

  monitoring/
    risk.py                  VaR/CVaR, correlation, drawdown, beta
    alerts.py                Stop-loss, drift, concentration health checks
    metrics.py               Structured JSON event logging
    market_pulse.py          Market regime detection (DEPLOY/WAIT/DEFENSIVE)

  daily/
    today.py                 Daily briefing: market + portfolio + opportunities
    learn.py                 Contextual investing education
    streak.py                Check-in streak tracking
    whatif.py                Stress testing and scenario simulation
```

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests (850+ tests, all mocked)
uv run pytest tests/ -x --tb=short

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run pyright src/

# Pre-commit hooks (runs all of the above)
uv run pre-commit install
uv run pre-commit run --all-files
```

## Configuration

All settings in `.env` (see [`.env.example`](.env.example)):

| Section | Key Settings |
|---------|-------------|
| AI | Gemini API key, model, rate limits (15 RPM) |
| Cache | Prices TTL (4h), screener (24h), sentiment (1h) |
| Portfolio | Max position weight (10%), sector caps (4 stocks, 25%) |
| Risk | Stop-loss (10%), cooldown (5 days), VaR/drawdown thresholds |
| Rebalancing | Frequency (90 days), drift threshold (5%), min trade (1000 INR) |
| God's Plan | Core filters (alpha, CAGR, Hurst, beta), value max P/B |
| Kite | API key/secret, dry-run mode (default true), circuit breaker (5%) |

## Risk Management

The risk engine computes VaR/CVaR, drawdown (tracked against high-water mark), correlation matrix, portfolio beta, and annualized volatility. De-risking signals are auto-generated:

- Drawdown WARNING at 10%, CRITICAL at 15% from HWM
- VaR WARNING when 1-day VaR > 3% of NAV
- Correlation WARNING when avg pairwise > 0.80
- Volatility WARNING when annualized > 30%

CRITICAL signals block the executor (override with `--force`).

## Paper Trading Workflow

```bash
diamond paper gods_plan --capital 500000     # Start paper trading
diamond paper gods_plan --status             # Check paper portfolio
diamond risk gods_plan_paper                 # Risk metrics on paper
diamond promote gods_plan                    # Assess promotion readiness
diamond promote gods_plan --execute          # Go live
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities and handling sensitive data.

## License

[MIT](LICENSE)
