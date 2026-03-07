# Contributing to Diamond Stock Engine

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/diamond-stock-engine.git
cd diamond-stock-engine

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (including dev)
uv sync --all-extras

# Copy environment config
cp .env.example .env

# Run tests to verify setup
uv run pytest tests/ -x --tb=short
```

## Development Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** — keep commits focused and atomic.

3. **Run checks locally** before pushing:
   ```bash
   uv run ruff check src/ tests/        # Lint
   uv run ruff format src/ tests/       # Format
   uv run pyright src/                   # Type check
   uv run pytest tests/ -x --tb=short   # Tests
   ```

4. **Push and open a PR** against `main`.

## Code Style

- **Formatter**: [ruff](https://docs.astral.sh/ruff/) (line length 120)
- **Type checker**: [pyright](https://github.com/microsoft/pyright) in standard mode
- **Target**: Python 3.9+
- **Imports**: sorted by ruff (isort-compatible)

## Architecture Guidelines

- **Strategies** implement the Protocol in `strategies/base.py` — structural typing, not ABC
- **Cost model** (`execution/costs.py`) must remain a pure function with zero side effects
- **Ledger** uses SQLite — one `.db` file per strategy in `data/ledgers/`
- **Config** loaded via Pydantic Settings from `.env` — use `get_config()` singleton
- **Tests** use `tmp_path` fixtures for isolated SQLite ledgers; market data is always mocked

## Testing

- All tests must pass without network access (mock external APIs)
- Use `tmp_path` for any file-based state (ledgers, caches)
- Minimum coverage: 60% (enforced in CI)
- Run a single test file: `uv run pytest tests/test_costs.py -v`

## What Makes a Good PR

- Focused on a single change
- Tests included for new functionality
- No unrelated formatting changes
- Passes all CI checks (lint, typecheck, tests)
- Updates `.env.example` if new config is added

## Reporting Issues

- Use GitHub Issues
- Include: Python version, OS, steps to reproduce, expected vs actual behavior
- For market data issues, note the date/time (caching may be involved)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
