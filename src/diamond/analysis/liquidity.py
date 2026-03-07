"""Liquidity checker — checks stock volume before large trades."""

import logging

import yfinance as yf

from diamond.data.ledger import Ledger

logger = logging.getLogger(__name__)


def check_liquidity(ticker: str, trade_value: float) -> dict:
    """Check if a trade can be executed without significant market impact.

    Returns:
        avg_daily_volume, avg_daily_value, trade_as_pct_of_adv,
        safe (bool), warning, suggestion
    """
    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    try:
        hist = yf.Ticker(ticker).history(period="3mo")
        if hist.empty or "Volume" not in hist.columns:
            return {
                "ticker": ticker,
                "error": "No volume data available",
                "safe": False,
                "warning": "Cannot assess liquidity — no data",
            }

        avg_volume = int(hist["Volume"].mean())
        avg_price = float(hist["Close"].mean())
        avg_daily_value = avg_volume * avg_price
        trade_pct = (trade_value / avg_daily_value * 100) if avg_daily_value > 0 else 100

        if trade_pct < 5:
            safe = True
            warning = None
            suggestion = None
        elif trade_pct < 10:
            safe = True
            warning = f"Trade is {trade_pct:.1f}% of ADV — may cause 0.5-1% slippage"
            suggestion = "Consider using limit orders instead of market orders"
        elif trade_pct < 25:
            safe = False
            days = max(2, int(trade_pct / 5))
            warning = f"Trade is {trade_pct:.1f}% of ADV — high market impact likely"
            suggestion = f"Stagger over {days} days, Rs {trade_value / days:,.0f} per day"
        else:
            safe = False
            warning = f"Trade is {trade_pct:.1f}% of ADV — stock is illiquid for this size"
            suggestion = "Avoid this trade size. Reduce position or find alternative"

        return {
            "ticker": ticker,
            "avg_daily_volume": avg_volume,
            "avg_daily_value": round(avg_daily_value, 2),
            "trade_value": round(trade_value, 2),
            "trade_as_pct_of_adv": round(trade_pct, 2),
            "safe": safe,
            "warning": warning,
            "suggestion": suggestion,
        }
    except Exception as e:
        return {
            "ticker": ticker,
            "error": f"Liquidity check failed: {e}",
            "safe": False,
            "warning": "Cannot assess liquidity",
        }


def check_portfolio_liquidity(strategy: str = "gods_plan") -> list[dict]:
    """Check liquidity for all portfolio holdings."""
    from diamond.data.market import download_prices

    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            # Get current prices for position values
            tickers = list(holdings.keys())
            prices = {}
            try:
                df = download_prices(tickers, period_days=5, use_cache=True)
                for col in df.columns:
                    series = df[col].dropna()
                    if len(series) > 0:
                        prices[col] = float(series.iloc[-1])
            except Exception:
                pass

            results = []
            for ticker, shares in holdings.items():
                price = prices.get(ticker, 0)
                position_value = shares * price
                result = check_liquidity(ticker, position_value)
                result["shares_held"] = shares
                result["position_value"] = round(position_value, 2)
                results.append(result)

            results.sort(key=lambda x: x.get("trade_as_pct_of_adv", 0), reverse=True)
            return results
        except Exception:
            continue
    return []


def suggest_stagger(ticker: str, trade_value: float) -> dict:
    """Suggest a stagger plan for a large trade."""
    check = check_liquidity(ticker, trade_value)
    pct = check.get("trade_as_pct_of_adv", 0)

    if pct < 5:
        return {
            "ticker": ticker,
            "stagger_needed": False,
            "message": "Trade can be executed in a single order",
        }

    # Target each day's trade at ~5% of ADV
    adv = check.get("avg_daily_value", 0)
    daily_safe = adv * 0.05 if adv > 0 else trade_value
    days = max(2, int(trade_value / daily_safe) + 1)
    daily_amount = trade_value / days

    tranches = []
    for i in range(days):
        tranches.append(
            {
                "day": i + 1,
                "amount": round(daily_amount, 2),
                "order_type": "LIMIT",
            }
        )

    return {
        "ticker": ticker,
        "stagger_needed": True,
        "total_value": round(trade_value, 2),
        "days": days,
        "daily_amount": round(daily_amount, 2),
        "tranches": tranches,
        "estimated_slippage_saved": f"{max(0, pct * 0.1 - 0.5):.1f}%",
    }
