"""Active management strategies - growth, defensive, momentum, value, quality.

WARNING: Active strategies underperformed passive in 9-year validation.
Use for research only. See CLAUDE.md for details.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from diamond.analysis import optimizer
from diamond.config import get_config
from diamond.data import market
from diamond.exceptions import UnknownStrategyError
from diamond.strategies.constraints import apply_sector_cap, cap_sector_weights

logger = logging.getLogger(__name__)


def _get_screened_universe(force: bool = False) -> pd.DataFrame:
    """Load or run the screener."""
    from diamond.analysis.screener import screen

    return screen(force=force)


def _fetch_returns(tickers: list[str], days: int = 365) -> pd.DataFrame:
    """Fetch price data and compute returns for optimizer input."""
    try:
        prices = market.download_prices(tickers, period_days=days)
        return prices.pct_change().dropna()
    except Exception as e:
        logger.warning(f"Failed to fetch returns: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Growth Strategy
# ---------------------------------------------------------------------------


class GrowthStrategy:
    """Top-alpha stocks, Monte Carlo optimized weights."""

    name = "growth"

    def screen(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        df = _get_screened_universe()
        if df.empty:
            return df
        cfg = get_config()
        # Filter positive alpha
        candidates = pd.DataFrame(df[df["Alpha"] > cfg.active.growth_min_alpha])
        if len(candidates) < cfg.active.target_size:
            candidates = df.nlargest(cfg.active.candidate_pool, "Alpha")
        return candidates

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        cfg = get_config()
        tickers = apply_sector_cap(candidates["Ticker"].tolist())[: cfg.active.target_size]
        if not tickers:
            return {}

        returns_df = _fetch_returns(tickers)
        if returns_df.empty:
            weights = optimizer.equal_weights(tickers)
        else:
            weights = optimizer.monte_carlo_optimize(
                returns_df,
                num_simulations=100_000,
                max_weight=cfg.portfolio.max_position_weight,
            )

        weights = cap_sector_weights(weights)
        return {t: w * capital for t, w in weights.items()}

    def should_rebalance(self, current_weights, target_weights, days_since_last):
        return days_since_last >= get_config().rebalance.rebalance_frequency_days


# ---------------------------------------------------------------------------
# Defensive Strategy
# ---------------------------------------------------------------------------


class DefensiveStrategy:
    """Low-beta quality stocks, inverse-volatility weighted."""

    name = "defensive"

    def screen(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        df = _get_screened_universe()
        if df.empty:
            return df
        cfg = get_config()
        candidates = pd.DataFrame(
            df[(df["Beta"] < cfg.active.defensive_max_beta) & (df["CAGR"] > cfg.active.defensive_min_cagr)]
        )
        if len(candidates) < cfg.active.target_size:
            candidates = df.nsmallest(cfg.active.candidate_pool, "Beta")
        return candidates

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        cfg = get_config()
        # Sort by efficiency: Alpha / Volatility
        candidates = candidates.copy()
        candidates["Efficiency"] = candidates["Alpha"] / candidates["Volatility"].clip(lower=0.01)
        candidates = candidates.sort_values("Efficiency", ascending=False)

        tickers = apply_sector_cap(candidates["Ticker"].tolist())[: cfg.active.target_size]
        if not tickers:
            return {}

        returns_df = _fetch_returns(tickers)
        if returns_df.empty:
            weights = optimizer.equal_weights(tickers)
        else:
            weights = optimizer.inverse_volatility_weights(
                returns_df,
                max_weight=cfg.portfolio.max_position_weight,
            )

        weights = cap_sector_weights(weights)
        return {t: w * capital for t, w in weights.items()}

    def should_rebalance(self, current_weights, target_weights, days_since_last):
        return days_since_last >= get_config().rebalance.rebalance_frequency_days


# ---------------------------------------------------------------------------
# Momentum Strategy
# ---------------------------------------------------------------------------


class MomentumStrategy:
    """Price momentum selection, equal-weighted."""

    name = "momentum"

    def screen(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        df = _get_screened_universe()
        if df.empty:
            return df
        return df.nlargest(get_config().active.candidate_pool, "CAGR")

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        cfg = get_config()
        tickers = apply_sector_cap(candidates["Ticker"].tolist())

        # Calculate momentum returns and rank
        momentum_scores: list[tuple[str, float]] = []
        lookback = cfg.active.momentum_lookback_months * 21  # Approx trading days
        skip = cfg.active.momentum_skip_months * 21

        for ticker in tickers:
            try:
                prices = market.download_single(ticker, period_days=lookback + skip + 30)
                if len(prices) > lookback:
                    start_price = prices.iloc[-(lookback + skip)]
                    end_price = prices.iloc[-skip] if skip > 0 else prices.iloc[-1]
                    mom = (end_price / start_price) - 1
                    momentum_scores.append((ticker, float(mom)))
            except Exception:
                pass

        if not momentum_scores:
            return {}

        # Top N by momentum, equal-weighted
        momentum_scores.sort(key=lambda x: x[1], reverse=True)
        top_tickers = [t for t, _ in momentum_scores[: cfg.active.target_size]]

        weights = optimizer.equal_weights(top_tickers)
        weights = cap_sector_weights(weights)
        return {t: w * capital for t, w in weights.items()}

    def should_rebalance(self, current_weights, target_weights, days_since_last):
        return days_since_last >= get_config().rebalance.rebalance_frequency_days


# ---------------------------------------------------------------------------
# Value Strategy
# ---------------------------------------------------------------------------


class ValueStrategy:
    """Low P/B stocks, equal-weighted."""

    name = "value"

    def screen(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        df = _get_screened_universe()
        if df.empty:
            return df
        return df.nlargest(get_config().active.candidate_pool, "Alpha")

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        cfg = get_config()
        tickers = apply_sector_cap(candidates["Ticker"].tolist())

        # Fetch P/B ratios and filter
        value_stocks: list[tuple[str, float]] = []
        for ticker in tickers:
            info = market.get_stock_info(ticker)
            pb = info.get("priceToBook")
            if pb and 0 < pb <= cfg.active.value_max_pb:
                value_stocks.append((ticker, pb))

        if not value_stocks:
            return {}

        # Sort by P/B ascending (cheapest first), take top N
        value_stocks.sort(key=lambda x: x[1])
        top_tickers = [t for t, _ in value_stocks[: cfg.active.target_size]]

        weights = optimizer.equal_weights(top_tickers)
        weights = cap_sector_weights(weights)
        return {t: w * capital for t, w in weights.items()}

    def should_rebalance(self, current_weights, target_weights, days_since_last):
        return days_since_last >= get_config().rebalance.rebalance_frequency_days


# ---------------------------------------------------------------------------
# Quality Strategy
# ---------------------------------------------------------------------------


class QualityStrategy:
    """Quality composite score (ROE + Safety + Growth), quality-proportional weights."""

    name = "quality"

    def screen(self, universe_df: pd.DataFrame) -> pd.DataFrame:
        df = _get_screened_universe()
        if df.empty:
            return df
        candidates = pd.DataFrame(df[df["CAGR"] > 0])
        if len(candidates) < get_config().active.target_size:
            candidates = df.nlargest(get_config().active.candidate_pool, "CAGR")
        return candidates

    def allocate(self, candidates: pd.DataFrame, capital: float) -> dict[str, float]:
        cfg = get_config()
        tickers = apply_sector_cap(candidates["Ticker"].tolist())

        # Fetch fundamental data and compute quality score
        scored: list[tuple[str, float]] = []
        roe_vals, safety_vals, growth_vals = [], [], []
        ticker_data: list[tuple[str, float, float, float]] = []

        for ticker in tickers:
            info = market.get_stock_info(ticker)
            roe = info.get("returnOnEquity", 0) or 0
            de = info.get("debtToEquity", 100) or 100
            # Match CAGR from screener
            row = pd.DataFrame(candidates[candidates["Ticker"] == ticker])
            cagr = float(row["CAGR"].iloc[0]) if len(row) > 0 else 0

            safety = 1.0 / max(de, 0.01)
            ticker_data.append((ticker, roe, safety, cagr))
            roe_vals.append(roe)
            safety_vals.append(safety)
            growth_vals.append(cagr)

        if not ticker_data:
            return {}

        # Z-score normalization
        def zscore(vals: list[float]) -> list[float]:
            arr = np.array(vals, dtype=float)
            std = arr.std()
            if std < 1e-10:
                return [0.0] * len(vals)
            return ((arr - arr.mean()) / std).tolist()

        z_roe = zscore(roe_vals)
        z_safety = zscore(safety_vals)
        z_growth = zscore(growth_vals)

        for i, (ticker, _, _, _) in enumerate(ticker_data):
            score = (
                cfg.active.quality_roe_weight * z_roe[i]
                + cfg.active.quality_safety_weight * z_safety[i]
                + cfg.active.quality_growth_weight * z_growth[i]
            )
            scored.append((ticker, score))

        # Top N by quality score
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[: cfg.active.target_size]

        if not top:
            return {}

        # Quality-proportional weights (shift to positive)
        min_score = min(s for _, s in top)
        shifted = {t: s - min_score + 1.0 for t, s in top}
        total = sum(shifted.values())
        weights = {t: v / total for t, v in shifted.items()}

        weights = cap_sector_weights(weights)
        return {t: w * capital for t, w in weights.items()}

    def should_rebalance(self, current_weights, target_weights, days_since_last):
        return days_since_last >= get_config().rebalance.rebalance_frequency_days


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

ACTIVE_STRATEGIES = {
    "growth": GrowthStrategy,
    "defensive": DefensiveStrategy,
    "momentum": MomentumStrategy,
    "value": ValueStrategy,
    "quality": QualityStrategy,
}


def get_active_strategy(name: str):
    """Get an active strategy class by name."""
    cls = ACTIVE_STRATEGIES.get(name)
    if cls is None:
        raise UnknownStrategyError(name, list(ACTIVE_STRATEGIES))
    return cls()
