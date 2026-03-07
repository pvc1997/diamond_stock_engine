"""Stock watchlist with price alerts and entry signals.

Persistent JSON-backed watchlist for tracking stocks outside your portfolio.
Checks for price threshold crossings, RSI signals, and strategy filter matches.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from diamond.config import get_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class WatchlistEntry:
    ticker: str
    added: str
    notes: str = ""
    price_above: float | None = None
    price_below: float | None = None


@dataclass
class WatchlistSignal:
    ticker: str
    signal_type: str  # price_above, price_below, quality_filter, rsi_oversold, rsi_overbought
    message: str
    value: float | None = None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _watchlist_path() -> Path:
    return get_config().data_dir / "watchlist.json"


def load_watchlist() -> dict[str, WatchlistEntry]:
    """Load watchlist from JSON. Returns empty dict on failure."""
    path = _watchlist_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return {
            ticker: WatchlistEntry(
                ticker=ticker,
                added=entry.get("added", ""),
                notes=entry.get("notes", ""),
                price_above=entry.get("price_above"),
                price_below=entry.get("price_below"),
            )
            for ticker, entry in data.items()
        }
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning(f"Failed to load watchlist: {e}")
        return {}


def save_watchlist(entries: dict[str, WatchlistEntry]) -> None:
    """Save watchlist to JSON."""
    path = _watchlist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        ticker: {
            "added": entry.added,
            "notes": entry.notes,
            "price_above": entry.price_above,
            "price_below": entry.price_below,
        }
        for ticker, entry in entries.items()
    }
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def add_ticker(
    ticker: str,
    notes: str = "",
    price_above: float | None = None,
    price_below: float | None = None,
) -> WatchlistEntry:
    """Add a stock to the watchlist."""
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    entries = load_watchlist()
    entry = WatchlistEntry(
        ticker=ticker,
        added=datetime.now().strftime("%Y-%m-%d"),
        notes=notes,
        price_above=price_above,
        price_below=price_below,
    )
    entries[ticker] = entry
    save_watchlist(entries)
    return entry


def remove_ticker(ticker: str) -> bool:
    """Remove a stock from the watchlist. Returns True if it existed."""
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    entries = load_watchlist()
    if ticker not in entries:
        return False
    del entries[ticker]
    save_watchlist(entries)
    return True


# ---------------------------------------------------------------------------
# Price and signal checking
# ---------------------------------------------------------------------------


def fetch_watchlist_prices(entries: dict[str, WatchlistEntry]) -> dict[str, dict]:
    """Fetch current prices and daily change for watchlist stocks.

    Returns {ticker: {"price": float, "change_pct": float, "sector": str}}.
    """
    from diamond.data import market
    from diamond.data.universe import get_sector

    result = {}
    tickers = list(entries.keys())
    if not tickers:
        return result

    try:
        df = market.download_prices(tickers, period_days=5, use_cache=True)
        for ticker in tickers:
            if ticker in df.columns:
                series = df[ticker].dropna()
                if len(series) >= 2:
                    price = float(series.iloc[-1])
                    prev = float(series.iloc[-2])
                    change = (price / prev - 1) * 100 if prev > 0 else 0
                    result[ticker] = {
                        "price": price,
                        "change_pct": round(change, 2),
                        "sector": get_sector(ticker),
                    }
                elif len(series) == 1:
                    result[ticker] = {
                        "price": float(series.iloc[-1]),
                        "change_pct": 0.0,
                        "sector": get_sector(ticker),
                    }
    except Exception as e:
        logger.warning(f"Failed to fetch watchlist prices: {e}")

    return result


def _compute_rsi(prices: list[float], period: int = 14) -> float:
    """Compute RSI from a list of prices."""
    if len(prices) < period + 1:
        return 50.0

    import numpy as np

    arr = np.array(prices)
    delta = np.diff(arr)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def check_signals(
    entries: dict[str, WatchlistEntry],
    prices: dict[str, dict] | None = None,
) -> list[WatchlistSignal]:
    """Check all watchlist stocks for entry/exit signals.

    Signals checked:
    - Price above/below user-set thresholds
    - RSI oversold (< 30) / overbought (> 70)
    - God's Plan quality filter match
    """
    signals = []

    if prices is None:
        prices = fetch_watchlist_prices(entries)

    for ticker, entry in entries.items():
        price_data = prices.get(ticker)
        if not price_data:
            continue

        current_price = price_data["price"]

        # Price threshold alerts
        if entry.price_above is not None and current_price >= entry.price_above:
            signals.append(
                WatchlistSignal(
                    ticker=ticker,
                    signal_type="price_above",
                    message=f"Price {current_price:,.0f} crossed above {entry.price_above:,.0f}",
                    value=current_price,
                )
            )

        if entry.price_below is not None and current_price <= entry.price_below:
            signals.append(
                WatchlistSignal(
                    ticker=ticker,
                    signal_type="price_below",
                    message=f"Price {current_price:,.0f} dropped below {entry.price_below:,.0f}",
                    value=current_price,
                )
            )

    # RSI check — batch fetch price history
    from diamond.data import market

    tickers = list(entries.keys())
    try:
        df = market.download_prices(tickers, period_days=30, use_cache=True)
        for ticker in tickers:
            if ticker not in df.columns:
                continue
            series = df[ticker].dropna().tolist()
            if len(series) < 16:
                continue

            rsi = _compute_rsi(series)
            if rsi < 30:
                signals.append(
                    WatchlistSignal(
                        ticker=ticker,
                        signal_type="rsi_oversold",
                        message=f"RSI {rsi:.0f} — oversold, potential entry",
                        value=rsi,
                    )
                )
            elif rsi > 70:
                signals.append(
                    WatchlistSignal(
                        ticker=ticker,
                        signal_type="rsi_overbought",
                        message=f"RSI {rsi:.0f} — overbought, consider exit",
                        value=rsi,
                    )
                )
    except Exception as e:
        logger.warning(f"RSI check failed: {e}")

    # Quality filter check (God's Plan criteria)
    try:
        cfg = get_config()
        cache_file = cfg.data_dir / "universe_cache.csv"
        if cache_file.exists():
            import pandas as pd

            screener_df = pd.read_csv(cache_file)
            gp = cfg.gods_plan

            for ticker in tickers:
                matches = screener_df[screener_df["Ticker"] == ticker]
                if matches.empty:
                    continue
                row = matches.iloc[0]
                alpha = row.get("Alpha", 0)
                cagr = row.get("CAGR", 0)
                hurst = row.get("Hurst", 0)
                beta = row.get("Beta", 1)

                if (
                    alpha >= gp.core_min_alpha
                    and cagr >= gp.core_min_cagr
                    and hurst >= gp.core_min_hurst
                    and gp.core_min_beta <= beta <= gp.core_max_beta
                ):
                    signals.append(
                        WatchlistSignal(
                            ticker=ticker,
                            signal_type="quality_filter",
                            message=(
                                f"Passes God's Plan quality filter: "
                                f"Alpha={alpha:.2f}, CAGR={cagr:.1%}, "
                                f"Hurst={hurst:.2f}, Beta={beta:.2f}"
                            ),
                            value=alpha,
                        )
                    )
    except Exception as e:
        logger.warning(f"Quality filter check failed: {e}")

    return signals
