"""Capital gains tax computation for Indian equity markets.

Indian equity tax rules (FY 2025-26):
- STCG (Short-Term): Holding < 12 months = 20% tax
- LTCG (Long-Term): Holding >= 12 months = 12.5% tax (above 1.25L exemption)
- STT already paid as part of transaction costs

Uses FIFO (First-In-First-Out) matching for buy-sell lot pairing.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from diamond.data.ledger import Ledger, Trade

logger = logging.getLogger(__name__)

# Indian equity tax rates (FY 2025-26)
STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_EXEMPTION = 125000.0
STCG_THRESHOLD_DAYS = 365


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaxLot:
    """A matched buy-sell pair for capital gains computation."""

    ticker: str
    buy_date: str
    sell_date: str
    shares: int
    buy_price: float
    sell_price: float
    buy_cost: float
    sell_cost: float
    gain: float
    holding_days: int
    tax_category: str  # STCG or LTCG
    tax_rate: float


@dataclass(frozen=True)
class UnrealizedLot:
    """Current holding with projected tax category."""

    ticker: str
    buy_date: str
    shares: int
    buy_price: float
    current_price: float
    unrealized_gain: float
    holding_days: int
    projected_category: str  # STCG or LTCG


@dataclass
class TaxReport:
    fiscal_year: str
    realized_lots: list[TaxLot]
    unrealized_lots: list[UnrealizedLot]
    total_stcg: float
    total_ltcg: float
    ltcg_exemption: float
    taxable_ltcg: float
    estimated_stcg_tax: float
    estimated_ltcg_tax: float
    total_estimated_tax: float
    total_dividends: float
    total_transaction_costs: float


# ---------------------------------------------------------------------------
# Fiscal year helpers
# ---------------------------------------------------------------------------


def _current_fiscal_year() -> str:
    """Get current Indian fiscal year string (e.g., '2025-26')."""
    today = datetime.now()
    if today.month >= 4:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    return f"{today.year - 1}-{str(today.year)[-2:]}"


def _fy_date_range(fy: str) -> tuple[str, str]:
    """Convert fiscal year string to (start_date, end_date).

    '2025-26' -> ('2025-04-01', '2026-03-31')
    """
    start_year = int(fy.split("-")[0])
    start = f"{start_year}-04-01"
    end = f"{start_year + 1}-03-31"
    return start, end


def _parse_date(date_str: str) -> datetime:
    """Parse a date string (handles both YYYY-MM-DD and YYYY-MM-DD HH:MM:SS)."""
    return datetime.strptime(date_str[:10], "%Y-%m-%d")


# ---------------------------------------------------------------------------
# FIFO lot matching
# ---------------------------------------------------------------------------


def _match_lots(
    trades: list[Trade],
    fy_start: str | None = None,
    fy_end: str | None = None,
) -> tuple[list[TaxLot], dict[str, deque]]:
    """FIFO match buy-sell pairs and return realized lots + remaining buy lots.

    Args:
        trades: All trades sorted by timestamp.
        fy_start: If set, only include sells on or after this date.
        fy_end: If set, only include sells on or before this date.

    Returns:
        (realized_lots, remaining_buy_lots) where remaining_buy_lots is
        {ticker: deque of (date, shares, price, cost_per_share)}.
    """
    # Build buy queues per ticker
    buy_queues: dict[str, deque] = {}
    realized: list[TaxLot] = []

    for trade in trades:
        ticker = trade.ticker

        # Skip synthetic trades (splits, bonuses, dividends with price=0)
        if trade.price <= 0:
            continue

        if trade.action == "BUY":
            if ticker not in buy_queues:
                buy_queues[ticker] = deque()
            cost_per_share = trade.total_cost / trade.shares if trade.shares > 0 else 0
            buy_queues[ticker].append(
                (
                    trade.timestamp,
                    trade.shares,
                    trade.price,
                    cost_per_share,
                )
            )

        elif trade.action == "SELL":
            if ticker not in buy_queues or not buy_queues[ticker]:
                logger.warning(f"Sell without matching buy for {ticker} on {trade.timestamp}")
                continue

            # Check FY filter
            sell_date = trade.timestamp[:10]
            if fy_start and sell_date < fy_start:
                # Sell is before FY — still consume buy lots but don't record
                remaining_sell = trade.shares
                while remaining_sell > 0 and buy_queues[ticker]:
                    buy_date, buy_shares, buy_price, buy_cost_ps = buy_queues[ticker][0]
                    matched = min(remaining_sell, buy_shares)
                    if matched >= buy_shares:
                        buy_queues[ticker].popleft()
                    else:
                        buy_queues[ticker][0] = (
                            buy_date,
                            buy_shares - matched,
                            buy_price,
                            buy_cost_ps,
                        )
                    remaining_sell -= matched
                continue

            if fy_end and sell_date > fy_end:
                continue

            # FIFO match
            sell_cost_per_share = trade.total_cost / trade.shares if trade.shares > 0 else 0
            remaining_sell = trade.shares

            while remaining_sell > 0 and buy_queues[ticker]:
                buy_date, buy_shares, buy_price, buy_cost_ps = buy_queues[ticker][0]
                matched = min(remaining_sell, buy_shares)

                # Holding period
                holding_days = (_parse_date(sell_date) - _parse_date(buy_date)).days
                category = "LTCG" if holding_days >= STCG_THRESHOLD_DAYS else "STCG"
                rate = LTCG_RATE if category == "LTCG" else STCG_RATE

                # Gain calculation
                buy_cost_total = matched * buy_cost_ps
                sell_cost_total = matched * sell_cost_per_share
                gain = (trade.price - buy_price) * matched - buy_cost_total - sell_cost_total

                realized.append(
                    TaxLot(
                        ticker=ticker,
                        buy_date=buy_date[:10],
                        sell_date=sell_date,
                        shares=matched,
                        buy_price=buy_price,
                        sell_price=trade.price,
                        buy_cost=round(buy_cost_total, 2),
                        sell_cost=round(sell_cost_total, 2),
                        gain=round(gain, 2),
                        holding_days=holding_days,
                        tax_category=category,
                        tax_rate=rate,
                    )
                )

                if matched >= buy_shares:
                    buy_queues[ticker].popleft()
                else:
                    buy_queues[ticker][0] = (buy_date, buy_shares - matched, buy_price, buy_cost_ps)

                remaining_sell -= matched

    return realized, buy_queues


def _compute_unrealized(
    buy_queues: dict[str, deque],
    current_prices: dict[str, float],
) -> list[UnrealizedLot]:
    """Compute unrealized gains from remaining buy lots."""
    today = datetime.now()
    lots = []

    for ticker, queue in buy_queues.items():
        price = current_prices.get(ticker, 0)
        for buy_date, shares, buy_price, _cost_ps in queue:
            if shares <= 0:
                continue
            holding_days = (today - _parse_date(buy_date)).days
            category = "LTCG" if holding_days >= STCG_THRESHOLD_DAYS else "STCG"
            unrealized = (price - buy_price) * shares if price > 0 else 0

            lots.append(
                UnrealizedLot(
                    ticker=ticker,
                    buy_date=buy_date[:10],
                    shares=shares,
                    buy_price=buy_price,
                    current_price=price,
                    unrealized_gain=round(unrealized, 2),
                    holding_days=holding_days,
                    projected_category=category,
                )
            )

    return lots


def _extract_dividends(trades: list[Trade]) -> float:
    """Sum dividend income from synthetic dividend trades."""
    total = 0.0
    for trade in trades:
        rationale_lower = trade.rationale.lower()
        if "dividend" in rationale_lower and trade.action == "BUY" and trade.price == 0:
            # Dividend trades are recorded as synthetic with cash added
            # The cash impact is shares * 0 + total_cost (which may be 0)
            # Actually, dividends add cash — check the corporate_actions module pattern
            pass
        if "dividend" in rationale_lower:
            # Dividend amounts are recorded in various ways;
            # the most reliable is to look for trades where rationale mentions dividend
            # and the action implies cash inflow
            if trade.action == "SELL" and trade.price == 0:
                # Some patterns record dividends as zero-price sells
                pass
            # Cash inflow from dividends is typically the total_cost field
            # used as the dividend amount in corporate_actions.py
            if trade.price == 0 and trade.total_cost > 0:
                total += trade.total_cost
    return round(total, 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_tax_report(
    strategy: str,
    fiscal_year: str | None = None,
    current_prices: dict[str, float] | None = None,
) -> TaxReport:
    """Compute capital gains tax report for a strategy.

    Args:
        strategy: Strategy name (for ledger lookup).
        fiscal_year: e.g., '2025-26'. Defaults to current FY.
        current_prices: Current prices for unrealized gains.
            If None, fetches from market.

    Returns:
        TaxReport with realized/unrealized lots and tax estimates.
    """
    fy = fiscal_year or _current_fiscal_year()
    fy_start, fy_end = _fy_date_range(fy)

    ledger = Ledger(strategy)
    all_trades = ledger.get_trades()

    if not all_trades:
        return TaxReport(
            fiscal_year=fy,
            realized_lots=[],
            unrealized_lots=[],
            total_stcg=0,
            total_ltcg=0,
            ltcg_exemption=LTCG_EXEMPTION,
            taxable_ltcg=0,
            estimated_stcg_tax=0,
            estimated_ltcg_tax=0,
            total_estimated_tax=0,
            total_dividends=0,
            total_transaction_costs=0,
        )

    # FIFO match
    realized, remaining = _match_lots(all_trades, fy_start, fy_end)

    # Unrealized gains
    if current_prices is None:
        try:
            from diamond.data import market

            holdings = ledger.get_holdings()
            current_prices = {}
            for ticker in holdings:
                try:
                    series = market.download_single(ticker, period_days=5)
                    if len(series) > 0:
                        current_prices[ticker] = float(series.iloc[-1])
                except Exception:
                    pass
        except Exception:
            current_prices = {}

    unrealized = _compute_unrealized(remaining, current_prices)

    # Aggregate
    total_stcg = sum(lot.gain for lot in realized if lot.tax_category == "STCG")
    total_ltcg = sum(lot.gain for lot in realized if lot.tax_category == "LTCG")
    taxable_ltcg = max(0, total_ltcg - LTCG_EXEMPTION)

    estimated_stcg_tax = max(0, total_stcg * STCG_RATE) if total_stcg > 0 else 0
    estimated_ltcg_tax = taxable_ltcg * LTCG_RATE

    dividends = _extract_dividends(all_trades)
    total_costs = sum(t.total_cost for t in all_trades if t.price > 0)

    return TaxReport(
        fiscal_year=fy,
        realized_lots=realized,
        unrealized_lots=unrealized,
        total_stcg=round(total_stcg, 2),
        total_ltcg=round(total_ltcg, 2),
        ltcg_exemption=LTCG_EXEMPTION,
        taxable_ltcg=round(taxable_ltcg, 2),
        estimated_stcg_tax=round(estimated_stcg_tax, 2),
        estimated_ltcg_tax=round(estimated_ltcg_tax, 2),
        total_estimated_tax=round(estimated_stcg_tax + estimated_ltcg_tax, 2),
        total_dividends=dividends,
        total_transaction_costs=round(total_costs, 2),
    )
