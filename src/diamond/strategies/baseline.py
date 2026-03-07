"""Nifty Baseline - equal-weight Nifty 50 benchmark strategy.

Simple, robust benchmark that doesn't depend on market cap data.
Equal-weight avoids large-cap concentration bias inherent in cap-weighted indices.
Quarterly rebalancing to maintain equal weights.
"""

from __future__ import annotations

import logging

import pandas as pd

from diamond.config import get_config
from diamond.data import universe

logger = logging.getLogger(__name__)


class BaselineStrategy:
    name = "baseline"

    def screen(self, universe_df: pd.DataFrame, end_date: str | None = None) -> pd.DataFrame:
        """Return Nifty 50 constituents (fixed universe, ignores end_date)."""
        nifty50 = universe.get_nifty50()
        return pd.DataFrame({"Ticker": nifty50})

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        """Equal-weight allocation across all Nifty 50 stocks."""
        tickers = candidates["Ticker"].tolist()
        if not tickers:
            return {}

        per_stock = capital / len(tickers)
        allocation = {t: per_stock for t in tickers}

        logger.info(f"Baseline allocation: {len(allocation)} stocks, {per_stock:,.0f} INR each")
        return allocation

    def should_rebalance(
        self,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        days_since_last: int,
    ) -> bool:
        """Rebalance quarterly (every 90 days)."""
        cfg = get_config()
        return days_since_last >= cfg.rebalance.rebalance_frequency_days
