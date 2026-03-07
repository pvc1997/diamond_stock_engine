"""Corporate actions handler for portfolio positions.

Adjusts ledger holdings for stock splits, bonuses, and dividends.
Uses yfinance for action detection and records adjustments as
synthetic trades in the ledger for audit trail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from diamond.data.ledger import Ledger, Trade

logger = logging.getLogger(__name__)


@dataclass
class CorporateAction:
    """A detected corporate action."""

    ticker: str
    action_type: str  # "split", "bonus", "dividend"
    date: str  # YYYY-MM-DD
    ratio: float  # Split/bonus ratio (e.g., 2.0 for 2:1 split)
    value: float  # Dividend amount per share (INR), or 0 for splits
    applied: bool = False


# ---------------------------------------------------------------------------
# Detection — uses yfinance actions data
# ---------------------------------------------------------------------------


def detect_splits(ticker: str, since: str | None = None) -> list[CorporateAction]:
    """Detect stock splits from yfinance.

    Args:
        ticker: Yahoo Finance ticker (e.g., "RELIANCE.NS").
        since: Only return splits after this date (YYYY-MM-DD).

    Returns:
        List of CorporateAction for splits.
    """
    try:
        stock = yf.Ticker(ticker)
        splits = stock.splits
        if splits.empty:
            return []

        actions = []
        for date, ratio in splits.items():
            ts = pd.Timestamp(str(date))
            date_str = ts.strftime("%Y-%m-%d") if not pd.isna(ts) else str(date)  # type: ignore[union-attr]
            if since and date_str <= since:
                continue
            if ratio != 1.0 and ratio > 0:
                actions.append(
                    CorporateAction(
                        ticker=ticker,
                        action_type="split",
                        date=date_str,
                        ratio=float(ratio),
                        value=0.0,
                    )
                )
        return actions
    except Exception as e:
        logger.warning(f"Failed to fetch splits for {ticker}: {e}")
        return []


def detect_dividends(ticker: str, since: str | None = None) -> list[CorporateAction]:
    """Detect dividends from yfinance.

    Args:
        ticker: Yahoo Finance ticker.
        since: Only return dividends after this date.

    Returns:
        List of CorporateAction for dividends.
    """
    try:
        stock = yf.Ticker(ticker)
        dividends = stock.dividends
        if dividends.empty:
            return []

        actions = []
        for date, amount in dividends.items():
            ts = pd.Timestamp(str(date))
            date_str = ts.strftime("%Y-%m-%d") if not pd.isna(ts) else str(date)  # type: ignore[union-attr]
            if since and date_str <= since:
                continue
            if amount > 0:
                actions.append(
                    CorporateAction(
                        ticker=ticker,
                        action_type="dividend",
                        date=date_str,
                        ratio=1.0,
                        value=float(amount),
                    )
                )
        return actions
    except Exception as e:
        logger.warning(f"Failed to fetch dividends for {ticker}: {e}")
        return []


def detect_all(ticker: str, since: str | None = None) -> list[CorporateAction]:
    """Detect all corporate actions for a ticker."""
    actions = detect_splits(ticker, since) + detect_dividends(ticker, since)
    actions.sort(key=lambda a: a.date)
    return actions


# ---------------------------------------------------------------------------
# Application — adjusts ledger positions
# ---------------------------------------------------------------------------


def apply_split(ledger: Ledger, action: CorporateAction) -> Trade | None:
    """Apply a stock split to ledger holdings.

    For a 2:1 split (ratio=2.0): shares double, avg price halves.

    Args:
        ledger: Strategy ledger.
        action: CorporateAction with action_type="split".

    Returns:
        Synthetic Trade recording the adjustment, or None if no position.
    """
    holdings = ledger.get_holdings()
    ticker = action.ticker

    if ticker not in holdings:
        return None

    old_shares = holdings[ticker]
    old_avg = ledger.get_avg_price(ticker)
    ratio = action.ratio

    # New shares after split
    new_shares = int(old_shares * ratio)
    additional = new_shares - old_shares

    if additional <= 0:
        return None

    # Adjust in database directly (avg price changes, total value unchanged)
    new_avg = old_avg / ratio

    with ledger._conn() as conn:
        conn.execute(
            "UPDATE holdings SET shares = ?, avg_price = ? WHERE ticker = ?",
            (new_shares, new_avg, ticker),
        )

    # Record synthetic trade for audit trail
    trade = Trade(
        timestamp=action.date,
        action="BUY",
        ticker=ticker,
        shares=additional,
        price=0.0,  # No cash impact
        total_cost=0.0,
        rationale=f"Split {action.ratio}:1 — {old_shares} → {new_shares} shares",
    )

    with ledger._conn() as conn:
        conn.execute(
            """INSERT INTO trades (timestamp, action, ticker, shares, price, total_cost, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.timestamp,
                trade.action,
                trade.ticker,
                trade.shares,
                trade.price,
                trade.total_cost,
                trade.rationale,
            ),
        )

    logger.info(f"Applied split for {ticker}: {old_shares} → {new_shares} shares (ratio {ratio}:1)")
    action.applied = True
    return trade


def apply_bonus(ledger: Ledger, ticker: str, ratio: float, date: str) -> Trade | None:
    """Apply a bonus issue to ledger holdings.

    Bonus issues are economically identical to splits for portfolio tracking.

    Args:
        ledger: Strategy ledger.
        ticker: Stock ticker.
        ratio: Bonus ratio (e.g., 1.0 for 1:1 bonus = shares double).
        date: Date of bonus issue (YYYY-MM-DD).

    Returns:
        Synthetic Trade recording the adjustment.
    """
    action = CorporateAction(
        ticker=ticker,
        action_type="bonus",
        date=date,
        ratio=1.0 + ratio,  # 1:1 bonus means 2x shares
        value=0.0,
    )
    return apply_split(ledger, action)


def apply_dividend(ledger: Ledger, action: CorporateAction) -> Trade | None:
    """Record a dividend receipt in the ledger.

    Adds dividend amount to cash. Does not change share count.

    Args:
        ledger: Strategy ledger.
        action: CorporateAction with action_type="dividend".

    Returns:
        Synthetic Trade recording the dividend, or None if no position.
    """
    holdings = ledger.get_holdings()
    ticker = action.ticker

    if ticker not in holdings:
        return None

    shares = holdings[ticker]
    dividend_total = round(shares * action.value, 2)

    if dividend_total <= 0:
        return None

    # Add dividend to cash
    cash = ledger.get_cash()
    ledger.set_cash(cash + dividend_total)

    # Record synthetic trade
    trade = Trade(
        timestamp=action.date,
        action="BUY",
        ticker=ticker,
        shares=0,
        price=0.0,
        total_cost=0.0,
        rationale=f"Dividend {action.value:.2f}/share × {shares} = {dividend_total:.2f} INR",
    )

    with ledger._conn() as conn:
        conn.execute(
            """INSERT INTO trades (timestamp, action, ticker, shares, price, total_cost, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.timestamp,
                trade.action,
                trade.ticker,
                trade.shares,
                trade.price,
                trade.total_cost,
                trade.rationale,
            ),
        )

    logger.info(f"Applied dividend for {ticker}: {dividend_total:.2f} INR ({action.value:.2f}/share × {shares})")
    action.applied = True
    return trade


# ---------------------------------------------------------------------------
# Batch processing — scan all holdings for pending actions
# ---------------------------------------------------------------------------


def process_actions(
    strategy: str,
    since: str | None = None,
) -> list[CorporateAction]:
    """Scan all holdings for corporate actions and apply them.

    Args:
        strategy: Strategy name (for ledger lookup).
        since: Only process actions after this date. Defaults to last rebalance date.

    Returns:
        List of CorporateAction objects that were applied.
    """
    ledger = Ledger(strategy)
    holdings = ledger.get_holdings()

    if not holdings:
        logger.info(f"No holdings for {strategy} — nothing to process")
        return []

    if since is None:
        since = ledger.get_last_rebalance() or None

    applied: list[CorporateAction] = []

    for ticker in holdings:
        actions = detect_all(ticker, since)
        for action in actions:
            if action.action_type == "split":
                result = apply_split(ledger, action)
                if result:
                    applied.append(action)
            elif action.action_type == "dividend":
                result = apply_dividend(ledger, action)
                if result:
                    applied.append(action)

    if applied:
        logger.info(f"Processed {len(applied)} corporate actions for {strategy}")
    else:
        logger.info(f"No pending corporate actions for {strategy}")

    return applied
