"""AI sentiment analysis using Gemini with heuristic fallback.

Provides qualitative stock signals from news headlines and fundamentals.
Falls back to keyword-based heuristics when Gemini API key is unavailable
or quota is exhausted.
"""

from __future__ import annotations

import json
import logging
import re
import time

from diamond.config import get_config

logger = logging.getLogger(__name__)


# --- Heuristic dictionaries ---

SENTIMENT_WORDS: dict[str, float] = {
    # Negative
    "fraud": -5.0,
    "investigation": -4.0,
    "arrest": -5.0,
    "sebi": -3.0,
    "penalty": -3.0,
    "fine": -2.0,
    "loss": -3.0,
    "default": -5.0,
    "bankruptcy": -5.0,
    "scam": -5.0,
    "resignation": -2.0,
    "downgrade": -3.0,
    "slowdown": -3.0,
    "decline": -2.0,
    "weak": -2.0,
    # Positive
    "growth": 3.0,
    "expansion": 3.0,
    "acquisition": 4.0,
    "deal": 3.0,
    "order": 3.0,
    "breakthrough": 4.0,
    "profit": 3.0,
    "surge": 2.0,
    "buyback": 4.0,
    "patent": 3.0,
    "record": 2.0,
    "strong": 2.0,
}

NEGATION_WORDS = {"no", "not", "never", "none", "without", "neither"}

TOXIC_KEYWORDS = {"fraud", "investigation", "default", "scam", "arrest", "whistleblower"}
GROWTH_KEYWORDS = {"expansion", "acquisition", "record", "buyback", "profit", "breakthrough"}


# --- Result structure ---


def _make_result(
    score: float,
    sentiment: str,
    multiplier: float,
    rationale: str,
    source: str,
) -> dict:
    """Build a standardized sentiment result dict."""
    return {
        "score": round(max(-10.0, min(10.0, score)), 2),
        "sentiment": sentiment,
        "multiplier": round(multiplier, 2),
        "rationale": rationale,
        "source": source,
    }


# --- Heuristic analysis ---


def _heuristic_news(headlines: list[str]) -> dict:
    """Score news headlines using keyword matching with negation detection."""
    text = " ".join(headlines).lower()
    words = re.findall(r"\b\w+\b", text)

    score = 0.0
    for i, word in enumerate(words):
        if word in SENTIMENT_WORDS:
            weight = SENTIMENT_WORDS[word]
            # Check for negation in preceding 3 words
            for j in range(max(0, i - 3), i):
                if words[j] in NEGATION_WORDS:
                    weight = -weight * 0.7
                    break
            score += weight

    # Multiplier based on keyword clusters
    multiplier = 1.0
    found_toxic = [w for w in words if w in TOXIC_KEYWORDS]
    found_growth = [w for w in words if w in GROWTH_KEYWORDS]

    if found_toxic:
        multiplier = 0.6
    elif found_growth:
        multiplier = 1.2

    # Map score to sentiment
    if score >= 3.0:
        sentiment = "Bullish"
    elif score >= 1.0:
        sentiment = "Positive"
    elif score <= -3.0:
        sentiment = "Toxic"
    elif score <= -1.0:
        sentiment = "Bearish"
    else:
        sentiment = "Neutral"

    return _make_result(score, sentiment, multiplier, "Heuristic news analysis", "heuristic")


def _heuristic_fundamental(info: dict) -> dict:
    """Score stock using fundamental data when no news is available."""
    score = 0.0
    parts = []

    rec = (info.get("recommendationKey") or "none").lower()
    if rec in ("buy", "strongbuy"):
        score += 3.0
        parts.append(f"Analyst: {rec}")
    elif rec in ("sell", "strongsell"):
        score -= 3.0
        parts.append(f"Analyst: {rec}")
    elif rec == "hold":
        score += 0.5
        parts.append("Analyst: hold")

    roe = info.get("returnOnEquity") or 0
    if abs(roe) > 0.001:
        if roe > 0.15:
            score += 2.0
            parts.append(f"Strong ROE: {roe:.1%}")
        elif roe > 0.10:
            score += 1.0
            parts.append(f"Good ROE: {roe:.1%}")
        elif roe < 0:
            score -= 2.0
            parts.append(f"Negative ROE: {roe:.1%}")

    if score >= 3.0:
        sentiment = "Bullish"
    elif score >= 1.0:
        sentiment = "Positive"
    elif score <= -3.0:
        sentiment = "Toxic"
    elif score <= -1.0:
        sentiment = "Bearish"
    else:
        sentiment = "Neutral"

    rationale = f"Heuristic fundamental: {', '.join(parts)}" if parts else "Heuristic fundamental: no signals"
    return _make_result(score, sentiment, 0.9, rationale, "heuristic")


# --- Gemini AI analysis ---


def _gemini_analyze(ticker: str, text: str, prompt_type: str) -> dict | None:
    """Call Gemini API for sentiment analysis.

    Returns parsed result dict or None on failure.
    """
    cfg = get_config()
    if not cfg.ai.gemini_api_key:
        return None

    try:
        from google import genai  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("google-generativeai not installed, using heuristic fallback")
        return None

    if prompt_type == "news":
        prompt = f"""Analyze these news headlines for Indian stock {ticker}:
{text}

Determine sentiment and assign a score from -10 (toxic) to +10 (bullish).
Be opinionated. Assign a conviction multiplier (0.5 to 1.5).

Respond in strict JSON:
{{"sentiment": "Bullish/Positive/Neutral/Bearish/Toxic", "score": 8.5, "conviction_multiplier": 1.3, "rationale": "explanation"}}"""  # noqa: E501
    else:
        prompt = f"""Analyze the fundamental outlook for Indian stock {ticker}:
{text}

Since no recent news is available, base this on business model and sector.
Score from -10 to +10. Conviction multiplier 0.8 to 1.2.

Respond in strict JSON:
{{"sentiment": "Bullish/Positive/Neutral/Bearish/Toxic", "score": 7.0, "conviction_multiplier": 1.1, "rationale": "explanation"}}"""  # noqa: E501

    try:
        client = genai.Client(api_key=cfg.ai.gemini_api_key)

        for attempt in range(cfg.ai.ai_retry_limit):
            try:
                time.sleep(60 / cfg.ai.ai_rate_limit_rpm)  # Rate limiting
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
                return _make_result(
                    score=float(data.get("score", 0)),
                    sentiment=data.get("sentiment", "Neutral"),
                    multiplier=float(data.get("conviction_multiplier", 1.0)),
                    rationale=data.get("rationale", "AI analysis"),
                    source="gemini",
                )

            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    if attempt < cfg.ai.ai_retry_limit - 1:
                        time.sleep(2 ** (attempt + 2))
                        continue
                    logger.warning(f"Gemini quota exhausted for {ticker}")
                    return None
                raise

    except Exception as e:
        logger.error(f"Gemini analysis failed for {ticker}: {e}")
        return None

    return None


# --- Cache ---


def _load_cache() -> dict:
    """Load sentiment cache from JSON file."""
    cfg = get_config()
    cache_file = cfg.cache_dir / "sentiments.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    """Save sentiment cache to JSON file."""
    cfg = get_config()
    cache_file = cfg.cache_dir / "sentiments.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=2))


# --- Public API ---


def analyze_stock(ticker: str, force: bool = False) -> dict:
    """Analyze a stock's qualitative sentiment signal.

    Tries Gemini AI first, falls back to heuristic keyword analysis.
    Results are cached with configurable TTL.

    Args:
        ticker: Stock ticker (e.g., 'RELIANCE.NS').
        force: Bypass cache.

    Returns:
        Dict with keys: score (-10 to 10), sentiment, multiplier, rationale, source.
    """
    cfg = get_config()

    # Check cache
    if not force:
        cache = _load_cache()
        entry = cache.get(ticker)
        if entry:
            cached_at = entry.get("cached_at", 0)
            if time.time() - cached_at < cfg.cache.sentiment_ttl:
                logger.debug(f"Cache hit for {ticker}")
                return entry.get("data", {})

    # Fetch news headlines
    try:
        from diamond.data import market

        info = market.get_stock_info(ticker)
    except Exception:
        info = {}

    headlines = []
    try:
        import yfinance as yf

        sym = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        news = yf.Ticker(sym).news or []
        headlines = [
            n.get("title", "")
            for n in news[:5]
            if n.get("title", "").strip().lower() not in ("", "no title", "n/a", "none")
        ]
    except Exception:
        pass

    # Try Gemini AI first
    result = None
    if headlines:
        text = "\n".join(f"- {h}" for h in headlines)
        result = _gemini_analyze(ticker, text, "news")
        if result is None:
            result = _heuristic_news(headlines)
    else:
        # No news — use fundamental analysis
        summary = info.get("longBusinessSummary", "")
        sector = info.get("sector", "Unknown")
        rec = info.get("recommendationKey", "none")
        text = f"Sector: {sector}\nAnalyst: {rec}\nSummary: {summary[:500]}"
        result = _gemini_analyze(ticker, text, "fundamental")
        if result is None:
            result = _heuristic_fundamental(info)

    # Cache result
    cache = _load_cache()
    cache[ticker] = {
        "cached_at": time.time(),
        "data": result,
    }
    _save_cache(cache)

    return result
