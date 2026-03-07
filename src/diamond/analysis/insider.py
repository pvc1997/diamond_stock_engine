"""Insider tracker — monitors promoter and institutional activity."""

import logging

import yfinance as yf

from diamond.data.ledger import Ledger

logger = logging.getLogger(__name__)


def get_insider_activity(ticker: str) -> dict:
    """Get insider/promoter trading activity for a stock.

    Returns:
        promoter_holding_pct, recent_transactions, net_insider_sentiment,
        institutional_holding_pct
    """
    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    result = {
        "ticker": ticker,
        "promoter_holding_pct": None,
        "institutional_holding_pct": None,
        "recent_transactions": [],
        "net_insider_sentiment": "neutral",
    }

    try:
        t = yf.Ticker(ticker)

        # Major holders
        try:
            holders = t.major_holders
            if holders is not None and not holders.empty:
                for _, row in holders.iterrows():
                    label = str(row.iloc[1]).lower() if len(row) > 1 else ""
                    value = row.iloc[0]
                    if isinstance(value, str) and "%" in value:
                        value = float(value.replace("%", ""))
                    elif isinstance(value, (int, float)):
                        value = float(value)
                    else:
                        continue

                    if "insider" in label or "promoter" in label:
                        result["promoter_holding_pct"] = round(value, 2)
                    elif "institution" in label:
                        result["institutional_holding_pct"] = round(value, 2)
        except Exception as e:
            logger.debug(f"Major holders fetch failed for {ticker}: {e}")

        # Insider transactions
        try:
            insider_txns = t.insider_transactions
            if insider_txns is not None and not insider_txns.empty:
                net_value = 0
                txns = []
                for _, row in insider_txns.head(10).iterrows():
                    txn = {}
                    # Map available columns
                    for col in insider_txns.columns:
                        col_lower = col.lower()
                        if "date" in col_lower or "start" in col_lower:
                            val = row[col]
                            txn["date"] = val.isoformat() if hasattr(val, "isoformat") else str(val)  # type: ignore[union-attr]
                        elif "insider" in col_lower or "name" in col_lower or "owner" in col_lower:
                            txn["insider"] = str(row[col])
                        elif "share" in col_lower or "unit" in col_lower:
                            try:
                                txn["shares"] = int(row[col])
                            except (ValueError, TypeError):
                                txn["shares"] = 0
                        elif "value" in col_lower or "amount" in col_lower:
                            try:
                                txn["value"] = float(row[col])
                            except (ValueError, TypeError):
                                txn["value"] = 0
                        elif "transaction" in col_lower or "type" in col_lower or "text" in col_lower:
                            txn["type"] = str(row[col])

                    # Determine buy/sell
                    txn_type = txn.get("type", "").lower()
                    if "buy" in txn_type or "purchase" in txn_type or "acquisition" in txn_type:
                        txn["action"] = "BUY"
                        net_value += abs(txn.get("value", 0))
                    elif "sell" in txn_type or "sale" in txn_type or "disposal" in txn_type:
                        txn["action"] = "SELL"
                        net_value -= abs(txn.get("value", 0))
                    else:
                        txn["action"] = "UNKNOWN"

                    txns.append(txn)

                result["recent_transactions"] = txns

                if net_value > 0:
                    result["net_insider_sentiment"] = "buying"
                elif net_value < 0:
                    result["net_insider_sentiment"] = "selling"
                else:
                    result["net_insider_sentiment"] = "neutral"
        except Exception as e:
            logger.debug(f"Insider transactions fetch failed for {ticker}: {e}")

    except Exception as e:
        logger.warning(f"Insider activity failed for {ticker}: {e}")
        result["error"] = str(e)

    return result


def get_portfolio_insider_signals(strategy: str = "gods_plan") -> list[dict]:
    """Scan all portfolio holdings for insider activity signals."""
    for s in [strategy, f"{strategy}_paper"]:
        try:
            ledger = Ledger(s)
            holdings = ledger.get_holdings()
            if not holdings:
                continue

            signals = []
            for ticker in holdings:
                activity = get_insider_activity(ticker)
                signals.append(activity)

            # Sort: selling first (bearish signals), then buying (bullish)
            order = {"selling": 0, "buying": 1, "neutral": 2}
            signals.sort(key=lambda x: order.get(x.get("net_insider_sentiment", "neutral"), 3))
            return signals
        except Exception:
            continue
    return []


def get_bulk_deals(ticker: str) -> list[dict]:
    """Fetch institutional holders data."""
    if not ticker.endswith(".NS"):
        ticker = f"{ticker}.NS"

    try:
        t = yf.Ticker(ticker)
        inst = t.institutional_holders
        if inst is None or inst.empty:
            return []

        deals = []
        for _, row in inst.iterrows():
            deal = {}
            for col in inst.columns:
                val = row[col]
                deal[col] = val.isoformat() if hasattr(val, "isoformat") else str(val)  # type: ignore[union-attr]
            deals.append(deal)
        return deals
    except Exception as e:
        logger.debug(f"Bulk deals fetch failed for {ticker}: {e}")
        return []
