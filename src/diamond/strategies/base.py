"""Strategy protocol - the contract all strategies must implement.

Using Protocol (structural typing) instead of ABC so strategies
don't need to inherit from anything - just implement the methods.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class Strategy(Protocol):
    """Contract for portfolio strategies.

    Every strategy implements three methods:
    1. screen() - Filter the universe to candidates
    2. allocate() - Assign weights to candidates
    3. should_rebalance() - Decide if rebalancing is needed
    """

    name: str

    def screen(self, universe: pd.DataFrame, end_date: str | None = None) -> pd.DataFrame:
        """Filter universe DataFrame to strategy-specific candidates.

        Args:
            universe: Screened universe with columns like Alpha, Beta, CAGR, Volatility.
            end_date: If set, only use data up to this date (for backtesting).

        Returns:
            Filtered DataFrame of candidate stocks.
        """
        ...

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        """Allocate capital across candidates.

        Args:
            candidates: Filtered stocks from screen().
            capital: Total capital to allocate in INR.

        Returns:
            {ticker: amount_inr} allocation dict. Values should sum to <= capital.
        """
        ...

    def should_rebalance(
        self,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        days_since_last: int,
    ) -> bool:
        """Determine if portfolio needs rebalancing.

        Args:
            current_weights: {ticker: weight} of current portfolio.
            target_weights: {ticker: weight} of target allocation.
            days_since_last: Days since last rebalance.

        Returns:
            True if rebalancing should occur.
        """
        ...
