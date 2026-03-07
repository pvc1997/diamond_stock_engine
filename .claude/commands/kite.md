Zerodha Kite integration commands. User input: $ARGUMENTS

Parse $ARGUMENTS:
- "auth" or "login": `uv run diamond kite --auth` — start browser login flow
- "token TOKEN_VALUE": `uv run diamond kite --token <TOKEN>` — set session token
- "import" or "import STRATEGY": `uv run diamond kite --import <strategy> -c 500000` — import Kite holdings
- "reconcile" or "reconcile STRATEGY": `uv run diamond reconcile <strategy>` — compare ledger vs Kite
- "sells" or "authorize": `uv run diamond kite --authorize-sells` — daily TPIN/CDSL authorization
- "status" or empty: Check if session is active, show expiry

Workflow reminder:
1. `kite --auth` → browser login → copy token
2. `kite --token <TOKEN>` → session saved
3. `kite --authorize-sells` → TPIN for sell orders (daily)
4. `kite --import gods_plan -c 500000` → import holdings
5. `reconcile gods_plan` → verify ledger matches Kite