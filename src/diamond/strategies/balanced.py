"""Balanced wealth strategy - 50% passive + 25% alpha + 25% defensive.

Combines index stability with selective alpha capture and downside protection.
Expected 9-11% CAGR, ~0.6%/year costs, quarterly rebalancing.
"""

from __future__ import annotations

import logging

import pandas as pd

from diamond.analysis.optimizer import equal_weights, market_cap_weights
from diamond.config import get_config
from diamond.data import market, universe
from diamond.strategies.constraints import apply_sector_cap

logger = logging.getLogger(__name__)


class BalancedStrategy:
    name = "balanced"

    def screen(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        """Return Nifty 50 tickers. Alpha/defensive selected during allocate()."""
        nifty50 = universe.get_nifty50()
        return pd.DataFrame({"Ticker": nifty50})

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        """Allocate capital across three components.

        50% -> Nifty 50 market-cap weighted (passive core)
        25% -> Top-alpha stocks from screened universe (equal-weighted)
        25% -> Low-beta quality stocks (equal-weighted)
        """
        cfg = get_config()
        bal = cfg.balanced

        # --- 1. Passive Component (50%) ---
        passive_capital = capital * bal.passive_alloc
        nifty_tickers = candidates["Ticker"].tolist()

        caps = {}
        for t in nifty_tickers:
            cap = market.get_market_cap(t)
            if cap and cap > 0:
                caps[t] = cap

        if caps:
            pw = market_cap_weights(caps)
            passive_alloc = {t: w * passive_capital for t, w in pw.items()}
        else:
            w = passive_capital / len(nifty_tickers)
            passive_alloc = {t: w for t in nifty_tickers}

        logger.info(f"Passive component: {len(passive_alloc)} stocks, {passive_capital:,.0f} INR")

        # --- 2. Alpha Component (25%) ---
        alpha_capital = capital * bal.alpha_alloc
        alpha_alloc = self._select_alpha(alpha_capital, bal.alpha_count)
        logger.info(f"Alpha component: {len(alpha_alloc)} stocks, {alpha_capital:,.0f} INR")

        # --- 3. Defensive Component (25%) ---
        def_capital = capital * bal.defensive_alloc
        def_alloc = self._select_defensive(def_capital, bal.defensive_count)
        logger.info(f"Defensive component: {len(def_alloc)} stocks, {def_capital:,.0f} INR")

        # --- Merge allocations (overlapping tickers sum up) ---
        merged: dict[str, float] = {}
        for alloc in [passive_alloc, alpha_alloc, def_alloc]:
            for t, amount in alloc.items():
                merged[t] = merged.get(t, 0) + amount

        logger.info(f"Balanced total: {len(merged)} unique stocks, {sum(merged.values()):,.0f} INR")
        return merged

    def _select_alpha(self, capital: float, count: int) -> dict[str, float]:
        """Select top-alpha stocks from cached screener results."""
        from diamond.analysis.screener import screen

        universe_df = screen()
        if universe_df.empty:
            return {}

        # Filter: Alpha > 0.2, CAGR > 15%
        alpha_candidates = universe_df[(universe_df["Alpha"] > 0.2) & (universe_df["CAGR"] > 0.15)]

        if len(alpha_candidates) < count:
            alpha_candidates = universe_df.nlargest(count * 2, "Alpha")

        # Sector cap and select top N
        tickers = apply_sector_cap(alpha_candidates["Ticker"].tolist())[:count]

        if not tickers:
            return {}

        weights = equal_weights(tickers)
        return {t: w * capital for t, w in weights.items()}

    def _select_defensive(self, capital: float, count: int) -> dict[str, float]:
        """Select low-beta, quality stocks from cached screener results."""
        from diamond.analysis.screener import screen

        universe_df = screen()
        if universe_df.empty:
            return {}

        # Filter: Beta < 0.80, CAGR > 12%
        def_candidates = universe_df[(universe_df["Beta"] < 0.80) & (universe_df["CAGR"] > 0.12)]

        if len(def_candidates) < count:
            def_candidates = universe_df.nsmallest(count * 2, "Beta")

        # Sector cap and select top N by lowest volatility
        def_candidates = def_candidates.sort_values("Volatility")  # type: ignore[call-overload]
        tickers = apply_sector_cap(def_candidates["Ticker"].tolist())[:count]

        if not tickers:
            return {}

        weights = equal_weights(tickers)
        return {t: w * capital for t, w in weights.items()}

    def should_rebalance(
        self,
        current_weights: dict[str, float],
        target_weights: dict[str, float],
        days_since_last: int,
    ) -> bool:
        """Rebalance quarterly (every 90 days)."""
        cfg = get_config()
        return days_since_last >= cfg.rebalance.rebalance_frequency_days
