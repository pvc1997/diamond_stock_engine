"""Deep stock analysis — technicals, fundamentals, screener metrics, AI verdict.

Provides a comprehensive single-stock analysis with:
- Technical indicators: RSI, MACD, Bollinger Bands, support/resistance, DMAs
- Fundamental data: P/E, P/B, ROE, D/E, dividend yield, growth
- Screener metrics: Alpha, Beta, CAGR, Volatility, Hurst
- Peer comparison within sector
- AI-generated narrative and verdict via Gemini (with rule-based fallback)

Usage: diamond analyze RELIANCE.NS
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from diamond.config import get_config
from diamond.data import market, universe
from diamond.exceptions import InsufficientDataError, PriceDownloadError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TechnicalIndicators:
    current_price: float
    rsi_14: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_position: str  # ABOVE / WITHIN / BELOW
    dma_50: float
    dma_200: float
    dma_trend: str  # GOLDEN_CROSS / DEATH_CROSS / NEUTRAL
    support: float
    resistance: float
    price_change_1d: float  # 1-day % change
    price_change_1w: float  # 5-day % change
    price_change_1m: float  # 21-day % change


@dataclass(frozen=True)
class FundamentalData:
    pe_ratio: float
    pb_ratio: float
    roe: float
    debt_to_equity: float
    dividend_yield: float
    revenue_growth: float
    profit_growth: float
    market_cap: float
    sector: str
    industry: str
    recommendation: str  # buy/sell/hold from analyst consensus
    free_cash_flow: float
    book_value: float
    eps: float


@dataclass(frozen=True)
class ScreenerMetrics:
    alpha: float
    beta: float
    cagr: float
    volatility: float
    hurst: float


@dataclass(frozen=True)
class PeerComparison:
    ticker: str
    name: str
    alpha: float
    beta: float
    cagr: float
    pe_ratio: float
    market_cap: float


@dataclass
class DeepAnalysis:
    ticker: str
    name: str
    timestamp: str
    technicals: TechnicalIndicators
    fundamentals: FundamentalData
    screener: ScreenerMetrics
    peers: list[PeerComparison]
    sentiment: dict
    ai_narrative: str
    verdict: str  # BUY / SELL / HOLD
    confidence: float  # 0.0 to 1.0
    verdict_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Technical indicator computation
# ---------------------------------------------------------------------------


def _compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """Compute RSI for the latest data point."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = pd.Series(gain.rolling(period).mean())
    avg_loss = pd.Series(loss.rolling(period).mean())

    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]

    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return float(100 - (100 / (1 + rs)))


def _compute_technicals(prices: pd.Series) -> TechnicalIndicators:
    """Compute all technical indicators from a price series."""
    current = float(prices.iloc[-1])

    # RSI(14)
    rsi = _compute_rsi(prices) if len(prices) >= 20 else 50.0

    # MACD(12, 26, 9)
    if len(prices) >= 35:
        ema_12 = prices.ewm(span=12, adjust=False).mean()
        ema_26 = prices.ewm(span=26, adjust=False).mean()
        macd_line = float((ema_12 - ema_26).iloc[-1])
        signal_line = (ema_12 - ema_26).ewm(span=9, adjust=False).mean()
        macd_signal = float(signal_line.iloc[-1])
        macd_hist = macd_line - macd_signal
    else:
        macd_line = macd_signal = macd_hist = 0.0

    # Bollinger Bands(20, 2)
    if len(prices) >= 20:
        sma_20 = pd.Series(prices.rolling(20).mean())
        std_20 = pd.Series(prices.rolling(20).std())
        bb_upper = float((sma_20 + 2 * std_20).iloc[-1])
        bb_middle = float(sma_20.iloc[-1])
        bb_lower = float((sma_20 - 2 * std_20).iloc[-1])

        if current > bb_upper:
            bb_pos = "ABOVE"
        elif current < bb_lower:
            bb_pos = "BELOW"
        else:
            bb_pos = "WITHIN"
    else:
        bb_upper = bb_middle = bb_lower = current
        bb_pos = "WITHIN"

    # 50/200 DMA
    dma_50 = float(pd.Series(prices.rolling(50).mean()).iloc[-1]) if len(prices) >= 50 else current
    dma_200 = float(pd.Series(prices.rolling(200).mean()).iloc[-1]) if len(prices) >= 200 else current

    if dma_50 > dma_200 * 1.01:
        dma_trend = "GOLDEN_CROSS"
    elif dma_50 < dma_200 * 0.99:
        dma_trend = "DEATH_CROSS"
    else:
        dma_trend = "NEUTRAL"

    # Support / Resistance (20-day rolling min/max)
    if len(prices) >= 20:
        recent = prices.iloc[-60:] if len(prices) >= 60 else prices
        support = float(pd.Series(recent.rolling(20).min()).iloc[-1])
        resistance = float(pd.Series(recent.rolling(20).max()).iloc[-1])
    else:
        support = float(prices.min())
        resistance = float(prices.max())

    # Price changes
    def _pct_change(n: int) -> float:
        if len(prices) > n:
            return float((current / prices.iloc[-n - 1] - 1) * 100)
        return 0.0

    return TechnicalIndicators(
        current_price=current,
        rsi_14=round(rsi, 1),
        macd_line=round(macd_line, 2),
        macd_signal=round(macd_signal, 2),
        macd_histogram=round(macd_hist, 2),
        bb_upper=round(bb_upper, 2),
        bb_middle=round(bb_middle, 2),
        bb_lower=round(bb_lower, 2),
        bb_position=bb_pos,
        dma_50=round(dma_50, 2),
        dma_200=round(dma_200, 2),
        dma_trend=dma_trend,
        support=round(support, 2),
        resistance=round(resistance, 2),
        price_change_1d=round(_pct_change(1), 2),
        price_change_1w=round(_pct_change(5), 2),
        price_change_1m=round(_pct_change(21), 2),
    )


# ---------------------------------------------------------------------------
# Fundamental data extraction
# ---------------------------------------------------------------------------


def _fetch_fundamentals(ticker: str) -> FundamentalData:
    """Extract fundamentals from yfinance .info dict."""
    info = market.get_stock_info(ticker)

    def _get(key: str, default: float = 0.0) -> float:
        val = info.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    return FundamentalData(
        pe_ratio=_get("trailingPE"),
        pb_ratio=_get("priceToBook"),
        roe=_get("returnOnEquity"),
        debt_to_equity=_get("debtToEquity"),
        dividend_yield=_get("dividendYield"),
        revenue_growth=_get("revenueGrowth"),
        profit_growth=_get("earningsGrowth"),
        market_cap=_get("marketCap"),
        sector=info.get("sector", "Unknown") or "Unknown",
        industry=info.get("industry", "Unknown") or "Unknown",
        recommendation=(info.get("recommendationKey") or "none").lower(),
        free_cash_flow=_get("freeCashflow"),
        book_value=_get("bookValue"),
        eps=_get("trailingEps"),
    )


# ---------------------------------------------------------------------------
# Screener metrics (reuses screener.py logic for a single stock)
# ---------------------------------------------------------------------------


def _compute_screener_metrics(ticker: str) -> ScreenerMetrics:
    """Compute Alpha, Beta, CAGR, Volatility, Hurst for a single stock."""
    from diamond.analysis.screener import _compute_metrics

    cfg = get_config()
    rf = cfg.screener.risk_free_rate
    benchmark = cfg.passive.index_ticker

    try:
        stock_prices = market.download_single(ticker)
        bench_prices = market.download_single(benchmark)
    except Exception as e:
        logger.warning(f"Failed to download prices for screener metrics: {e}")
        return ScreenerMetrics(alpha=0, beta=1, cagr=0, volatility=0, hurst=0.5)

    bench_returns = bench_prices.pct_change().dropna()
    market_ann_return = float((1 + bench_returns.mean()) ** 252 - 1)

    metrics = _compute_metrics(stock_prices, bench_returns, market_ann_return, rf)
    if not metrics:
        return ScreenerMetrics(alpha=0, beta=1, cagr=0, volatility=0, hurst=0.5)

    return ScreenerMetrics(
        alpha=metrics["Alpha"],
        beta=metrics["Beta"],
        cagr=metrics["CAGR"],
        volatility=metrics["Volatility"],
        hurst=metrics["Hurst"],
    )


# ---------------------------------------------------------------------------
# Peer comparison
# ---------------------------------------------------------------------------


def _find_peers(
    ticker: str,
    sector: str,
    max_peers: int = 5,
) -> list[PeerComparison]:
    """Find sector peers and compute comparative metrics."""
    from diamond.analysis.screener import _compute_metrics

    # Find tickers in the same sector
    sector_tickers = [t for t in universe.get_screening_universe() if universe.get_sector(t) == sector and t != ticker]

    if not sector_tickers:
        return []

    # Limit to avoid excessive API calls
    sector_tickers = sector_tickers[: max_peers * 2]

    cfg = get_config()
    rf = cfg.screener.risk_free_rate

    try:
        bench_prices = market.download_single(cfg.passive.index_ticker)
        bench_returns = bench_prices.pct_change().dropna()
        market_ann = float((1 + bench_returns.mean()) ** 252 - 1)
    except Exception:
        return []

    peers = []
    for peer_ticker in sector_tickers:
        if len(peers) >= max_peers:
            break
        try:
            prices = market.download_single(peer_ticker, period_days=504)
            if len(prices) < 60:
                continue
            metrics = _compute_metrics(prices, bench_returns, market_ann, rf)
            if not metrics:
                continue

            info = market.get_stock_info(peer_ticker)
            peers.append(
                PeerComparison(
                    ticker=peer_ticker,
                    name=info.get("shortName", peer_ticker.replace(".NS", "")) or peer_ticker.replace(".NS", ""),
                    alpha=metrics["Alpha"],
                    beta=metrics["Beta"],
                    cagr=metrics["CAGR"],
                    pe_ratio=float(info.get("trailingPE", 0) or 0),
                    market_cap=float(info.get("marketCap", 0) or 0),
                )
            )
        except Exception:
            continue

    return peers


# ---------------------------------------------------------------------------
# Rule-based verdict (fallback when AI unavailable)
# ---------------------------------------------------------------------------


def _rule_based_verdict(
    technicals: TechnicalIndicators,
    fundamentals: FundamentalData,
    screener: ScreenerMetrics,
    sentiment: dict,
) -> tuple[str, float, list[str]]:
    """Score-based verdict when Gemini is unavailable.

    Returns (verdict, confidence, reasons).
    """
    score = 0.0
    reasons = []

    # --- Technical signals ---
    if technicals.rsi_14 < 30:
        score += 2.0
        reasons.append(f"RSI {technicals.rsi_14:.0f} — oversold, potential bounce")
    elif technicals.rsi_14 > 70:
        score -= 2.0
        reasons.append(f"RSI {technicals.rsi_14:.0f} — overbought, pullback risk")
    elif technicals.rsi_14 < 40:
        score += 0.5
        reasons.append(f"RSI {technicals.rsi_14:.0f} — approaching oversold")

    if technicals.macd_histogram > 0:
        score += 1.0
        reasons.append("MACD histogram positive — bullish momentum")
    else:
        score -= 0.5
        reasons.append("MACD histogram negative — bearish momentum")

    if technicals.dma_trend == "GOLDEN_CROSS":
        score += 1.5
        reasons.append("Golden cross (50 DMA > 200 DMA) — bullish trend")
    elif technicals.dma_trend == "DEATH_CROSS":
        score -= 1.5
        reasons.append("Death cross (50 DMA < 200 DMA) — bearish trend")

    if technicals.bb_position == "BELOW":
        score += 1.0
        reasons.append("Price below lower Bollinger Band — oversold")
    elif technicals.bb_position == "ABOVE":
        score -= 0.5
        reasons.append("Price above upper Bollinger Band — extended")

    if technicals.current_price > technicals.dma_200:
        score += 0.5
        reasons.append("Trading above 200 DMA — in uptrend")
    else:
        score -= 0.5
        reasons.append("Trading below 200 DMA — in downtrend")

    # --- Screener signals ---
    if screener.alpha > 0.15:
        score += 2.0
        reasons.append(f"High alpha {screener.alpha:.1%} — outperforming market")
    elif screener.alpha > 0.05:
        score += 1.0
        reasons.append(f"Positive alpha {screener.alpha:.1%}")
    elif screener.alpha < -0.05:
        score -= 1.5
        reasons.append(f"Negative alpha {screener.alpha:.1%} — underperforming")

    if screener.cagr > 0.20:
        score += 1.5
        reasons.append(f"Strong CAGR {screener.cagr:.1%}")
    elif screener.cagr > 0.12:
        score += 0.5
        reasons.append(f"Decent CAGR {screener.cagr:.1%}")
    elif screener.cagr < 0:
        score -= 1.0
        reasons.append(f"Negative CAGR {screener.cagr:.1%}")

    if screener.hurst > 0.55:
        score += 1.0
        reasons.append(f"Hurst {screener.hurst:.2f} — persistent trend")
    elif screener.hurst < 0.45:
        score -= 0.5
        reasons.append(f"Hurst {screener.hurst:.2f} — mean-reverting")

    if screener.beta < 0.8:
        score += 0.5
        reasons.append(f"Low beta {screener.beta:.2f} — defensive")
    elif screener.beta > 1.3:
        score -= 0.5
        reasons.append(f"High beta {screener.beta:.2f} — volatile")

    # --- Fundamental signals ---
    if fundamentals.roe > 0.20:
        score += 1.0
        reasons.append(f"Excellent ROE {fundamentals.roe:.1%}")
    elif fundamentals.roe > 0.15:
        score += 0.5
        reasons.append(f"Good ROE {fundamentals.roe:.1%}")
    elif fundamentals.roe < 0:
        score -= 1.0
        reasons.append(f"Negative ROE {fundamentals.roe:.1%}")

    if 0 < fundamentals.pe_ratio < 15:
        score += 0.5
        reasons.append(f"Low P/E {fundamentals.pe_ratio:.1f} — potential value")
    elif fundamentals.pe_ratio > 50:
        score -= 0.5
        reasons.append(f"High P/E {fundamentals.pe_ratio:.1f} — expensive")

    if fundamentals.debt_to_equity > 0 and fundamentals.debt_to_equity < 50:
        score += 0.5
        reasons.append(f"Low leverage (D/E: {fundamentals.debt_to_equity:.0f}%)")
    elif fundamentals.debt_to_equity > 150:
        score -= 0.5
        reasons.append(f"High leverage (D/E: {fundamentals.debt_to_equity:.0f}%)")

    if fundamentals.revenue_growth > 0.15:
        score += 1.0
        reasons.append(f"Strong revenue growth {fundamentals.revenue_growth:.1%}")
    elif fundamentals.revenue_growth < -0.05:
        score -= 0.5
        reasons.append(f"Revenue declining {fundamentals.revenue_growth:.1%}")

    if fundamentals.recommendation in ("buy", "strongbuy", "strong_buy"):
        score += 1.0
        reasons.append(f"Analyst consensus: {fundamentals.recommendation}")
    elif fundamentals.recommendation in ("sell", "strongsell", "strong_sell"):
        score -= 1.0
        reasons.append(f"Analyst consensus: {fundamentals.recommendation}")

    # --- Sentiment signals ---
    sent_score = sentiment.get("score", 0)
    if sent_score >= 3:
        score += 1.0
        reasons.append(f"Positive sentiment ({sent_score:+.1f})")
    elif sent_score <= -3:
        score -= 1.0
        reasons.append(f"Negative sentiment ({sent_score:+.1f})")

    # --- Verdict ---
    if score >= 4:
        verdict = "BUY"
    elif score <= -3:
        verdict = "SELL"
    else:
        verdict = "HOLD"

    confidence = min(abs(score) / 12.0, 1.0)

    # Sort reasons by absolute impact (most impactful first)
    return verdict, round(confidence, 2), reasons


# ---------------------------------------------------------------------------
# AI narrative via Gemini
# ---------------------------------------------------------------------------


def _generate_ai_narrative(
    ticker: str,
    technicals: TechnicalIndicators,
    fundamentals: FundamentalData,
    screener: ScreenerMetrics,
    sentiment: dict,
    peers: list[PeerComparison],
) -> tuple[str, str, float, list[str]]:
    """Call Gemini for AI-generated verdict and narrative.

    Returns (narrative, verdict, confidence, reasons).
    Falls back to rule-based if Gemini unavailable.
    """
    cfg = get_config()
    if not cfg.ai.gemini_api_key:
        v, c, r = _rule_based_verdict(technicals, fundamentals, screener, sentiment)
        narrative = f"Rule-based analysis: {v} with {c:.0%} confidence."
        return narrative, v, c, r

    peer_summary = ""
    if peers:
        peer_lines = [
            f"  {p.ticker.replace('.NS', '')}: Alpha={p.alpha:.2f}, CAGR={p.cagr:.1%}, P/E={p.pe_ratio:.1f}"
            for p in peers[:3]
        ]
        peer_summary = "SECTOR PEERS:\n" + "\n".join(peer_lines)

    prompt = f"""You are an expert Indian equity analyst. Analyze {ticker.replace(".NS", "")} based on this data:

PRICE: {technicals.current_price:,.2f} INR
TECHNICALS:
  RSI(14): {technicals.rsi_14:.1f}
  MACD: Line={technicals.macd_line:.2f}, Signal={technicals.macd_signal:.2f}, Hist={technicals.macd_histogram:.2f}
  Bollinger: {technicals.bb_position} (U={technicals.bb_upper:.0f}, M={technicals.bb_middle:.0f}, L={technicals.bb_lower:.0f})
  50 DMA: {technicals.dma_50:.0f}, 200 DMA: {technicals.dma_200:.0f}, Trend: {technicals.dma_trend}
  Support: {technicals.support:.0f}, Resistance: {technicals.resistance:.0f}
  1D: {technicals.price_change_1d:+.1f}%, 1W: {technicals.price_change_1w:+.1f}%, 1M: {technicals.price_change_1m:+.1f}%

SCREENER METRICS:
  Alpha: {screener.alpha:.4f}, Beta: {screener.beta:.2f}
  CAGR: {screener.cagr:.1%}, Volatility: {screener.volatility:.1%}
  Hurst: {screener.hurst:.2f} ({"trending" if screener.hurst > 0.5 else "mean-reverting"})

FUNDAMENTALS:
  P/E: {fundamentals.pe_ratio:.1f}, P/B: {fundamentals.pb_ratio:.2f}
  ROE: {fundamentals.roe:.1%}, D/E: {fundamentals.debt_to_equity:.0f}
  Div Yield: {fundamentals.dividend_yield:.2%}, Revenue Growth: {fundamentals.revenue_growth:.1%}
  Profit Growth: {fundamentals.profit_growth:.1%}
  Sector: {fundamentals.sector}, Industry: {fundamentals.industry}
  Analyst: {fundamentals.recommendation}

SENTIMENT: Score={sentiment.get("score", 0):.1f} ({sentiment.get("sentiment", "Neutral")})
  {sentiment.get("rationale", "")}

{peer_summary}

Give a BUY/SELL/HOLD verdict with confidence (0.0 to 1.0).
Write a 3-5 sentence narrative explaining your reasoning — be specific about what makes this stock attractive or risky.
List 3-5 key reasons as bullet points.

Respond in strict JSON:
{{"verdict": "BUY", "confidence": 0.75, "narrative": "...", "reasons": ["...", "..."]}}"""

    try:
        from google import genai  # type: ignore[attr-defined]

        client = genai.Client(api_key=cfg.ai.gemini_api_key)
        time.sleep(60 / cfg.ai.ai_rate_limit_rpm)

        response = client.models.generate_content(
            model=cfg.ai.gemini_model,
            contents=prompt,
        )
        text_out = response.text.strip()

        # Strip markdown code blocks
        if "```json" in text_out:
            text_out = text_out.split("```json")[1].split("```")[0].strip()
        elif "```" in text_out:
            text_out = text_out.split("```")[1].split("```")[0].strip()

        data = json.loads(text_out)
        verdict = data.get("verdict", "HOLD").upper()
        if verdict not in ("BUY", "SELL", "HOLD"):
            verdict = "HOLD"

        return (
            data.get("narrative", "AI analysis complete."),
            verdict,
            float(data.get("confidence", 0.5)),
            data.get("reasons", []),
        )

    except Exception as e:
        logger.warning(f"Gemini analysis failed for {ticker}: {e}")
        v, c, r = _rule_based_verdict(technicals, fundamentals, screener, sentiment)
        narrative = f"Rule-based analysis (AI unavailable): {v} with {c:.0%} confidence."
        return narrative, v, c, r


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_deep(ticker: str, use_ai: bool = True) -> DeepAnalysis:
    """Run full deep analysis for a single stock.

    Args:
        ticker: Stock ticker (e.g., 'RELIANCE.NS').
        use_ai: Whether to use Gemini AI for narrative.

    Returns:
        DeepAnalysis with all computed data.
    """
    # Normalize ticker
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = f"{ticker}.NS"

    logger.info(f"Deep analysis: {ticker}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. Download price history
    try:
        prices = market.download_single(ticker, period_days=504)
    except Exception as e:
        raise PriceDownloadError([ticker], str(e)) from e

    if len(prices) < 30:
        raise InsufficientDataError(ticker, len(prices), 30)

    # 2. Technical indicators
    technicals = _compute_technicals(prices)

    # 3. Fundamentals
    fundamentals = _fetch_fundamentals(ticker)

    # 4. Screener metrics
    screener = _compute_screener_metrics(ticker)

    # 5. Sentiment (reuse existing module)
    try:
        from diamond.analysis.sentiment import analyze_stock

        sentiment = analyze_stock(ticker)
    except Exception as e:
        logger.warning(f"Sentiment analysis failed: {e}")
        sentiment = {
            "score": 0,
            "sentiment": "Neutral",
            "multiplier": 1.0,
            "rationale": "N/A",
            "source": "none",
        }

    # 6. Peer comparison
    peers = _find_peers(ticker, fundamentals.sector)

    # 7. AI narrative + verdict
    if use_ai:
        narrative, verdict, confidence, reasons = _generate_ai_narrative(
            ticker,
            technicals,
            fundamentals,
            screener,
            sentiment,
            peers,
        )
    else:
        verdict, confidence, reasons = _rule_based_verdict(
            technicals,
            fundamentals,
            screener,
            sentiment,
        )
        narrative = f"Rule-based analysis: {verdict} with {confidence:.0%} confidence."

    # Stock name
    info = market.get_stock_info(ticker)
    name = info.get("shortName", ticker.replace(".NS", "")) or ticker.replace(".NS", "")

    return DeepAnalysis(
        ticker=ticker,
        name=name,
        timestamp=now,
        technicals=technicals,
        fundamentals=fundamentals,
        screener=screener,
        peers=peers,
        sentiment=sentiment,
        ai_narrative=narrative,
        verdict=verdict,
        confidence=confidence,
        verdict_reasons=reasons,
    )
