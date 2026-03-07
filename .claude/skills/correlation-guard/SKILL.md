---
name: correlation-guard
description: Warns before adding highly correlated stocks. Auto-activates when the user wants to buy a stock that may be correlated with existing holdings. Prevents hidden concentration risk.
allowed-tools: mcp__diamond__*, Bash(uv run diamond:*)
---

# Correlation Guard — Diversification Watchdog

## Trigger Conditions

Activate when:
- User wants to BUY a new stock
- Composing with trade-guard skill (runs in parallel)
- User asks "is X correlated with my portfolio?"
- Portfolio correlation warnings appear in risk report

## What To Do

1. **Check correlation** — use `correlation_check` MCP tool
   - Get pairwise correlations for existing holdings + proposed stock
   - Flag if new stock has correlation > 0.75 with ANY existing holding

2. **Sector overlap** — use `sector_exposure` and `stock_sector` MCP tools
   - Is this the same sector as an existing holding?
   - Would adding it breach sector caps?

3. **Similar stocks** — identify the most correlated existing holding
   - "HDFCBANK and ICICIBANK have 0.82 correlation — you're effectively doubling the same bet"

## Output Format

**Correlation Check for [TICKER]:**
- Most correlated with: [HOLDING] (r = 0.XX)
- Sector overlap: [Yes/No] — [sector] already has [N] stocks
- Portfolio avg correlation if added: [current] -> [projected]
- Verdict: SAFE / OVERLAP WARNING / HIGH CORRELATION RISK

If HIGH CORRELATION:
- Suggest alternatives in the same quality tier but different sector
- Or suggest replacing the correlated holding instead of adding
