"""Earnings calendar — tracks upcoming quarterly results for portfolio stocks."""

from __future__ import annotations

import contextlib
import logging
from datetime import date, datetime

import yfinance as yf

from diamond.data.ledger import Ledger

logger = logging.getLogger(__name__)


def get_earnings_calendar(tickers: list[str]) -> list[dict]:
    """Get upcoming earnings dates for a list of tickers.

    Returns list of dicts sorted by days_until (soonest first):
        ticker, earnings_date, days_until, quarter
    """
    today = date.today()
    events = []

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None:
                continue

            # yfinance returns calendar as a dict or DataFrame
            earnings_date: date | None = None
            if isinstance(cal, dict):
                # Look for earnings date keys
                for key in ("Earnings Date", "earningsDate", "Earnings Average"):
                    if key in cal:
                        val = cal[key]
                        if isinstance(val, list) and val:
                            val = val[0]
                        if hasattr(val, "date") and callable(val.date):  # type: ignore[union-attr]
                            earnings_date = val.date()  # type: ignore[union-attr]
                        elif isinstance(val, date):
                            earnings_date = val
                        elif isinstance(val, str):
                            with contextlib.suppress(ValueError, TypeError):
                                earnings_date = datetime.strptime(val[:10], "%Y-%m-%d").date()
                        break
            elif hasattr(cal, "columns"):
                # DataFrame format
                if "Earnings Date" in cal.columns:
                    vals = cal["Earnings Date"].dropna()
                    if len(vals) > 0:
                        val = vals.iloc[0]
                        if hasattr(val, "date") and callable(val.date):
                            earnings_date = val.date()
                elif len(cal.columns) > 0:
                    # Try first column
                    vals = cal.iloc[:, 0].dropna()
                    if len(vals) > 0:
                        val = vals.iloc[0]
                        if hasattr(val, "date") and callable(val.date):
                            earnings_date = val.date()

            if earnings_date is None:
                continue

            days_until = (earnings_date - today).days

            # Determine fiscal quarter
            month = earnings_date.month
            if month <= 3:
                quarter = "Q4"
            elif month <= 6:
                quarter = "Q1"
            elif month <= 9:
                quarter = "Q2"
            else:
                quarter = "Q3"

            fy_year = earnings_date.year if month > 3 else earnings_date.year - 1
            quarter_label = f"{quarter} FY{fy_year % 100 + 1}"

            events.append(
                {
                    "ticker": ticker,
                    "earnings_date": earnings_date.isoformat(),
                    "days_until": days_until,
                    "quarter": quarter_label,
                }
            )
        except Exception as e:
            logger.debug(f"Earnings fetch failed for {ticker}: {e}")
            continue

    events.sort(key=lambda x: x["days_until"])
    return events


def get_portfolio_earnings(strategy: str = "gods_plan") -> list[dict]:
    """Get upcoming earnings for all portfolio holdings."""
    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if holdings:
                return get_earnings_calendar(list(holdings.keys()))
        except Exception:
            continue
    return []
