"""Market Pulse - regime detection and daily investment verdict.

Conservative by default: recommends "WAIT" unless multiple signals align.
Fetches Nifty 50, India VIX, and breadth data to determine market regime.

Usage:
    from diamond.monitoring.market_pulse import get_market_pulse
    pulse = get_market_pulse()
    print(pulse.verdict)  # "DEPLOY" / "WAIT" / "DEFENSIVE"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MarketPulse:
    """Snapshot of market conditions."""

    timestamp: str
    # Nifty 50
    nifty_price: float = 0.0
    nifty_change_pct: float = 0.0
    nifty_50dma: float = 0.0
    nifty_200dma: float = 0.0
    nifty_distance_200dma_pct: float = 0.0  # % above/below 200 DMA

    # Volatility
    vix: float = 0.0
    vix_regime: str = "UNKNOWN"  # LOW / NORMAL / HIGH / EXTREME

    # Trend
    trend: str = "UNKNOWN"  # BULLISH / BEARISH / SIDEWAYS
    golden_cross: bool = False  # 50 DMA > 200 DMA
    death_cross: bool = False  # 50 DMA < 200 DMA

    # Breadth (% of Nifty 50 stocks above their 50 DMA)
    breadth_pct: float = 0.0
    breadth_regime: str = "UNKNOWN"  # STRONG / HEALTHY / WEAK / WASHOUT

    # Momentum
    nifty_rsi_14: float = 50.0
    momentum_regime: str = "UNKNOWN"  # OVERBOUGHT / NEUTRAL / OVERSOLD

    # Overall
    regime: str = "UNKNOWN"  # BULL / BEAR / SIDEWAYS / CORRECTION
    verdict: str = "WAIT"  # DEPLOY / WAIT / DEFENSIVE
    verdict_reasons: list[str] = field(default_factory=list)
    score: int = 0  # -100 to +100, positive = favorable


def _compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """Compute RSI for a price series."""
    if len(prices) < period + 1:
        return 50.0
    delta = prices.diff()
    gain = pd.Series(delta.where(delta > 0, 0.0).rolling(period).mean())
    loss = pd.Series((-delta.where(delta < 0, 0.0)).rolling(period).mean())
    last_gain = gain.iloc[-1]
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return round(100 - (100 / (1 + rs)), 2)


def _fetch_nifty_data() -> pd.DataFrame | None:
    """Fetch Nifty 50 price history (1 year)."""
    try:
        from diamond.data.market import download_prices

        df = download_prices(["^NSEI"], period_days=365, use_cache=True)
        if df.empty:
            return None
        return df
    except Exception as e:
        logger.warning(f"Failed to fetch Nifty data: {e}")
        return None


def _fetch_vix() -> float:
    """Fetch India VIX current value."""
    try:
        from diamond.data.market import download_prices

        df = download_prices(["^INDIAVIX"], period_days=5, use_cache=True)
        if df.empty or df.iloc[:, 0].dropna().empty:
            return 0.0
        return float(df.iloc[:, 0].dropna().iloc[-1])
    except Exception as e:
        logger.warning(f"Failed to fetch VIX: {e}")
        return 0.0


def _compute_breadth() -> float:
    """Compute breadth: % of Nifty 50 stocks above their 50 DMA."""
    try:
        from diamond.data.market import download_prices
        from diamond.data.universe import get_nifty50

        tickers = get_nifty50()
        prices = download_prices(tickers, period_days=90, use_cache=True)
        if prices.empty:
            return 50.0

        above_50dma = 0
        total = 0
        for col in prices.columns:
            series = prices[col].dropna()
            if len(series) < 50:
                continue
            sma50 = pd.Series(series.rolling(50).mean()).iloc[-1]
            current = series.iloc[-1]
            total += 1
            if current > sma50:
                above_50dma += 1

        return round(above_50dma / total * 100, 1) if total > 0 else 50.0
    except Exception as e:
        logger.warning(f"Failed to compute breadth: {e}")
        return 50.0


def get_market_pulse() -> MarketPulse:
    """Compute current market pulse with conservative verdict.

    Scoring system (-100 to +100):
      Positive signals add points, negative signals subtract.
      DEPLOY requires score >= 40 (multiple signals must align).
      WAIT is default for score -20 to +39.
      DEFENSIVE for score < -20.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pulse = MarketPulse(timestamp=timestamp)
    score = 0
    reasons: list[str] = []

    # --- 1. Nifty 50 data ---
    nifty_df = _fetch_nifty_data()
    if nifty_df is not None and not nifty_df.empty:
        nifty = nifty_df.iloc[:, 0].dropna()
        if len(nifty) >= 2:
            pulse.nifty_price = round(float(nifty.iloc[-1]), 2)
            pulse.nifty_change_pct = round((float(nifty.iloc[-1]) / float(nifty.iloc[-2]) - 1) * 100, 2)

        if len(nifty) >= 50:
            pulse.nifty_50dma = round(float(nifty.rolling(50).mean().iloc[-1]), 2)

        if len(nifty) >= 200:
            pulse.nifty_200dma = round(float(nifty.rolling(200).mean().iloc[-1]), 2)
            pulse.nifty_distance_200dma_pct = round((pulse.nifty_price / pulse.nifty_200dma - 1) * 100, 2)

            # Golden/Death cross
            pulse.golden_cross = pulse.nifty_50dma > pulse.nifty_200dma
            pulse.death_cross = pulse.nifty_50dma < pulse.nifty_200dma

            # Trend
            if pulse.golden_cross and pulse.nifty_price > pulse.nifty_50dma:
                pulse.trend = "BULLISH"
                score += 20
                reasons.append("Nifty above 50 & 200 DMA (bullish trend)")
            elif pulse.death_cross and pulse.nifty_price < pulse.nifty_50dma:
                pulse.trend = "BEARISH"
                score -= 30
                reasons.append("Nifty below 50 & 200 DMA (bearish trend)")
            else:
                pulse.trend = "SIDEWAYS"
                reasons.append("Nifty in sideways range")

            # Distance from 200 DMA
            if pulse.nifty_distance_200dma_pct > 15:
                score -= 15
                reasons.append(f"Nifty {pulse.nifty_distance_200dma_pct:+.1f}% above 200 DMA (stretched)")
            elif pulse.nifty_distance_200dma_pct < -10:
                score += 15
                reasons.append(f"Nifty {pulse.nifty_distance_200dma_pct:+.1f}% below 200 DMA (potential value)")
            elif pulse.nifty_distance_200dma_pct > 0:
                score += 5
                reasons.append(f"Nifty {pulse.nifty_distance_200dma_pct:+.1f}% above 200 DMA (healthy)")

        # RSI
        if len(nifty) >= 20:
            pulse.nifty_rsi_14 = _compute_rsi(nifty, 14)
            if pulse.nifty_rsi_14 > 70:
                pulse.momentum_regime = "OVERBOUGHT"
                score -= 15
                reasons.append(f"RSI {pulse.nifty_rsi_14:.0f} - overbought, wait for pullback")
            elif pulse.nifty_rsi_14 < 30:
                pulse.momentum_regime = "OVERSOLD"
                score += 20
                reasons.append(f"RSI {pulse.nifty_rsi_14:.0f} - oversold, potential buying opportunity")
            else:
                pulse.momentum_regime = "NEUTRAL"
                score += 5

    # --- 2. VIX ---
    pulse.vix = round(_fetch_vix(), 2)
    if pulse.vix > 0:
        if pulse.vix < 13:
            pulse.vix_regime = "LOW"
            score += 10
            reasons.append(f"VIX {pulse.vix:.1f} - low fear, calm market")
        elif pulse.vix < 20:
            pulse.vix_regime = "NORMAL"
            score += 5
            reasons.append(f"VIX {pulse.vix:.1f} - normal volatility")
        elif pulse.vix < 28:
            pulse.vix_regime = "HIGH"
            score -= 15
            reasons.append(f"VIX {pulse.vix:.1f} - elevated fear, proceed with caution")
        else:
            pulse.vix_regime = "EXTREME"
            score -= 30
            reasons.append(f"VIX {pulse.vix:.1f} - extreme fear, high risk environment")

    # --- 3. Breadth ---
    pulse.breadth_pct = _compute_breadth()
    if pulse.breadth_pct >= 70:
        pulse.breadth_regime = "STRONG"
        score += 15
        reasons.append(f"Breadth {pulse.breadth_pct:.0f}% - strong market participation")
    elif pulse.breadth_pct >= 50:
        pulse.breadth_regime = "HEALTHY"
        score += 5
        reasons.append(f"Breadth {pulse.breadth_pct:.0f}% - healthy participation")
    elif pulse.breadth_pct >= 30:
        pulse.breadth_regime = "WEAK"
        score -= 10
        reasons.append(f"Breadth {pulse.breadth_pct:.0f}% - narrow market, few stocks participating")
    else:
        pulse.breadth_regime = "WASHOUT"
        score -= 20
        reasons.append(f"Breadth {pulse.breadth_pct:.0f}% - broad weakness, washout conditions")

    # --- 4. Overall regime ---
    if score >= 30:
        pulse.regime = "BULL"
    elif score >= 0:
        pulse.regime = "SIDEWAYS"
    elif score >= -20:
        pulse.regime = "CORRECTION"
    else:
        pulse.regime = "BEAR"

    # --- 5. Conservative verdict ---
    # DEPLOY requires strong conviction (score >= 40)
    # WAIT is the default — we're conservative to minimize transaction costs
    # DEFENSIVE when things look bad
    if score >= 40:
        pulse.verdict = "DEPLOY"
        reasons.insert(0, "Multiple bullish signals align - good conditions to invest")
    elif score <= -20:
        pulse.verdict = "DEFENSIVE"
        reasons.insert(0, "Market stress detected - avoid new positions, review stops")
    else:
        pulse.verdict = "WAIT"
        reasons.insert(0, "No strong signal - hold current positions, wait for clarity")

    pulse.score = score
    pulse.verdict_reasons = reasons
    return pulse
