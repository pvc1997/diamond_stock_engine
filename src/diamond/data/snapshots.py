"""Portfolio snapshots — save and compare portfolio checkpoints."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from diamond.data.ledger import Ledger
from diamond.data.market import download_prices

logger = logging.getLogger(__name__)

_SNAPSHOTS_FILE = Path("data/snapshots.json")


def _load_snapshots() -> dict:
    """Load all snapshots from file."""
    if not _SNAPSHOTS_FILE.exists():
        return {}
    try:
        return json.loads(_SNAPSHOTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_snapshots(snapshots: dict) -> None:
    """Save snapshots to file."""
    _SNAPSHOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SNAPSHOTS_FILE.write_text(json.dumps(snapshots, indent=2, default=str))


def save_snapshot(name: str, strategy: str, notes: str = "") -> dict:
    """Capture current portfolio state as a named snapshot."""
    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            tickers = list(holdings.keys())
            prices = {}
            try:
                df = download_prices(tickers, period_days=5, use_cache=True)
                for col in df.columns:
                    series = df[col].dropna()
                    if len(series) > 0:
                        prices[col] = round(float(series.iloc[-1]), 2)
            except Exception:
                pass

            cash = ledger.get_cash()
            nav = cash + sum(holdings.get(t, 0) * prices.get(t, 0) for t in tickers)

            snapshot = {
                "name": name,
                "strategy": s,
                "timestamp": datetime.now().isoformat(),
                "holdings": holdings,
                "prices": prices,
                "cash": round(cash, 2),
                "nav": round(nav, 2),
                "notes": notes,
            }

            snapshots = _load_snapshots()
            snapshots[name] = snapshot
            _save_snapshots(snapshots)
            return snapshot
        except Exception:
            continue

    return {"error": f"No holdings found for strategy '{strategy}'"}


def load_snapshot(name: str) -> dict | None:
    """Load a snapshot by name."""
    snapshots = _load_snapshots()
    return snapshots.get(name)


def list_snapshots() -> list[dict]:
    """List all saved snapshots (summary only)."""
    snapshots = _load_snapshots()
    result = []
    for name, snap in snapshots.items():
        result.append(
            {
                "name": name,
                "strategy": snap.get("strategy", ""),
                "timestamp": snap.get("timestamp", ""),
                "nav": snap.get("nav", 0),
                "holdings_count": len(snap.get("holdings", {})),
                "notes": snap.get("notes", ""),
            }
        )
    result.sort(key=lambda x: x["timestamp"], reverse=True)
    return result


def delete_snapshot(name: str) -> bool:
    """Delete a snapshot by name."""
    snapshots = _load_snapshots()
    if name in snapshots:
        del snapshots[name]
        _save_snapshots(snapshots)
        return True
    return False


def diff_snapshots(name1: str, name2: str) -> dict:
    """Compare two snapshots."""
    snapshots = _load_snapshots()
    s1 = snapshots.get(name1)
    s2 = snapshots.get(name2)

    if not s1:
        return {"error": f"Snapshot '{name1}' not found"}
    if not s2:
        return {"error": f"Snapshot '{name2}' not found"}

    return _compute_diff(s1, s2, name1, name2)


def diff_with_current(name: str, strategy: str) -> dict:
    """Compare a snapshot to the current live portfolio."""
    snapshots = _load_snapshots()
    s1 = snapshots.get(name)
    if not s1:
        return {"error": f"Snapshot '{name}' not found"}

    # Build current state as a pseudo-snapshot
    current = save_snapshot("__temp_current__", strategy, "")
    if "error" in current:
        return current

    # Clean up temp
    all_snaps = _load_snapshots()
    all_snaps.pop("__temp_current__", None)
    _save_snapshots(all_snaps)

    return _compute_diff(s1, current, name, "current")


def _compute_diff(s1: dict, s2: dict, label1: str, label2: str) -> dict:
    """Compute diff between two portfolio states."""
    h1 = s1.get("holdings", {})
    h2 = s2.get("holdings", {})
    p1 = s1.get("prices", {})
    p2 = s2.get("prices", {})

    all_tickers = set(list(h1.keys()) + list(h2.keys()))

    added = []
    removed = []
    changed = []

    nav1 = s1.get("nav", 0)
    nav2 = s2.get("nav", 0)

    for ticker in sorted(all_tickers):
        shares1 = h1.get(ticker, 0)
        shares2 = h2.get(ticker, 0)
        price1 = p1.get(ticker, 0)
        price2 = p2.get(ticker, 0)

        val1 = shares1 * price1
        val2 = shares2 * price2
        w1 = round(val1 / nav1 * 100, 2) if nav1 > 0 else 0
        w2 = round(val2 / nav2 * 100, 2) if nav2 > 0 else 0

        if shares1 == 0 and shares2 > 0:
            added.append({"ticker": ticker, "shares": shares2, "weight_pct": w2})
        elif shares1 > 0 and shares2 == 0:
            removed.append({"ticker": ticker, "shares": shares1, "weight_pct": w1})
        elif shares1 != shares2 or abs(w1 - w2) > 0.5:
            changed.append(
                {
                    "ticker": ticker,
                    "shares_before": shares1,
                    "shares_after": shares2,
                    "weight_before": w1,
                    "weight_after": w2,
                    "weight_change": round(w2 - w1, 2),
                }
            )

    return {
        "from": label1,
        "to": label2,
        "nav_before": round(nav1, 2),
        "nav_after": round(nav2, 2),
        "nav_change_pct": round((nav2 - nav1) / nav1 * 100, 2) if nav1 > 0 else 0,
        "added": added,
        "removed": removed,
        "changed": changed,
        "net_stocks_change": len(added) - len(removed),
    }
