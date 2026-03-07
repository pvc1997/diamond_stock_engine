# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. Email the maintainer directly or use GitHub's private vulnerability reporting
3. Include a description of the vulnerability and steps to reproduce

We will respond within 48 hours and work with you to resolve the issue.

## Sensitive Data

This project handles financial data and broker credentials. Contributors must ensure:

- **Never commit** `.env` files, API keys, or broker credentials
- **Never commit** ledger databases (`data/ledgers/*.db`), session files, or cache data
- **Never log** API keys, access tokens, or passwords
- The `.gitignore` excludes sensitive directories — do not override these exclusions

## Broker Integration

- Kite Connect integration defaults to **dry-run mode** (`KITE_DRY_RUN=true`)
- Real order placement requires explicit opt-in
- Session tokens are stored locally and expire after ~23 hours
- CDSL TPIN authorization is required for sells (additional security layer)

## Dependencies

- Dependencies are pinned via `uv.lock`
- We use `ruff` for static analysis which catches some security anti-patterns
- No secrets should appear in test fixtures — all tests use mocked data
