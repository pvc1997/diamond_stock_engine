"""Zerodha Kite Connect integration.

Optional dependency - gracefully degrades when kiteconnect is not installed.
Handles authentication, order placement, holdings sync, and CDSL authorization.
"""

import contextlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from diamond.config import get_config
from diamond.exceptions import AuthenticationError, BrokerError

logger = logging.getLogger(__name__)

try:
    from kiteconnect import KiteConnect  # type: ignore[import-not-found]

    KITE_AVAILABLE = True
except ImportError:
    KiteConnect = None  # type: ignore[assignment,misc]
    KITE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Ticker mapping: Kite tradingsymbol <-> yfinance ticker
# ---------------------------------------------------------------------------


def kite_to_yf(symbol: str) -> str:
    """Convert Kite trading symbol to yfinance ticker.

    Kite uses 'RELIANCE', yfinance uses 'RELIANCE.NS'.
    Handles special cases like M&M -> M&M.NS.
    """
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def yf_to_kite(ticker: str) -> str:
    """Convert yfinance ticker to Kite trading symbol.

    'RELIANCE.NS' -> 'RELIANCE'
    """
    for suffix in (".NS", ".BO"):
        if ticker.endswith(suffix):
            return ticker[: -len(suffix)]
    return ticker


class KiteClient:
    """Zerodha Kite Connect API wrapper.

    Features:
    - OAuth token generation and persistence
    - Order placement with dry-run support
    - Holdings and positions sync
    - CDSL holdings authorization
    - Automatic yfinance price fallback
    """

    def __init__(self) -> None:
        cfg = get_config()
        self._api_key = cfg.kite.api_key
        self._api_secret = cfg.kite.api_secret
        self._exchange = cfg.kite.exchange
        self._dry_run = cfg.kite.dry_run
        self._session_file = cfg.data_dir / "kite_session.json"
        self._kite: Any = None
        self._authenticated = False
        self._user_name: str = ""
        self._user_id: str = ""
        self._auth_time: Optional[datetime] = None

        if not KITE_AVAILABLE:
            logger.info("kiteconnect not installed - Kite features disabled")
            return

        if not self._api_key or not self._api_secret:
            logger.info("Kite API credentials not configured - Kite features disabled")
            return

        self._kite = KiteConnect(api_key=self._api_key)  # type: ignore[misc]
        self._load_session()

    @property
    def available(self) -> bool:
        """Check if Kite client is available and configured."""
        return self._kite is not None

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def user_name(self) -> str:
        return self._user_name

    @property
    def user_id(self) -> str:
        return self._user_id

    # --- Session management ---

    def _load_session(self) -> None:
        """Load saved access token from file."""
        if not self._session_file.exists():
            return
        try:
            data = json.loads(self._session_file.read_text())
            token_time = datetime.fromisoformat(data.get("timestamp", "2020-01-01"))
            # Kite tokens expire around 6 AM next day — check <23h old
            if datetime.now() - token_time < timedelta(hours=23):
                self._kite.set_access_token(data["access_token"])
                self._authenticated = True
                self._auth_time = token_time
                self._user_name = data.get("user_name", "")
                self._user_id = data.get("user_id", "")
                logger.info(f"Loaded existing Kite session ({self._user_name})")
            else:
                logger.info("Kite session expired — re-authentication needed")
        except Exception as e:
            logger.warning(f"Failed to load Kite session: {e}")

    def _save_session(self, access_token: str, user_data: dict) -> None:
        """Persist access token for reuse."""
        self._session_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": access_token,
            "timestamp": datetime.now().isoformat(),
            "user_id": user_data.get("user_id", ""),
            "user_name": user_data.get("user_name", ""),
        }
        self._session_file.write_text(json.dumps(data, indent=2))
        # Restrict permissions (owner-only read/write)
        with contextlib.suppress(OSError):
            self._session_file.chmod(0o600)

    def session_age_hours(self) -> float:
        """Return the age of the current session in hours.

        Uses in-memory auth time if available, otherwise reads from session file.

        Returns:
            Age in hours, or float('inf') if no session info available.
        """
        # Prefer in-memory auth time (set during authenticate() or _load_session())
        if self._auth_time is not None:
            delta = datetime.now() - self._auth_time
            return delta.total_seconds() / 3600.0

        # Fall back to session file
        try:
            if not self._session_file.exists():
                return float("inf")
            data = json.loads(self._session_file.read_text())
            ts = datetime.fromisoformat(data.get("timestamp", "2020-01-01"))
            delta = datetime.now() - ts
            return delta.total_seconds() / 3600.0
        except Exception:
            return float("inf")

    def is_session_valid(self) -> bool:
        """Check if the saved Kite session is still valid.

        Checks both file age (<23 hours) and, if possible, pings the Kite API.
        Handles: file missing, file corrupt, API unreachable.

        Returns:
            True if session appears valid, False otherwise.
        """
        # Check 1: file exists and is readable
        try:
            if not self._session_file.exists():
                logger.info("Kite session file not found")
                return False
        except Exception:
            return False

        # Check 2: file is valid JSON with required fields
        try:
            data = json.loads(self._session_file.read_text())
            if "access_token" not in data or "timestamp" not in data:
                logger.warning("Kite session file corrupt (missing fields)")
                return False
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Kite session file corrupt: {e}")
            return False

        # Check 3: session not expired by age
        age = self.session_age_hours()
        if age >= 23.0:
            logger.info(f"Kite session expired ({age:.1f}h old). Run `diamond kite --auth` to re-authenticate.")
            return False

        # Check 4: API ping (lightweight call) — only if Kite client is available
        if self._kite is not None and self._authenticated:
            try:
                self._kite.profile()
            except Exception as e:
                error_msg = str(e).lower()
                if "token" in error_msg or "session" in error_msg or "auth" in error_msg:
                    logger.warning("Kite session rejected by API. Run `diamond kite --auth` to re-authenticate.")
                    return False
                # Network error or other transient issue — don't invalidate
                logger.debug(f"Kite API ping failed (non-auth error, treating as valid): {e}")

        return True

    def session_status(self) -> dict:
        """Return session status info for display."""
        status = {
            "available": self.available,
            "authenticated": self.authenticated,
            "user_name": self._user_name,
            "user_id": self._user_id,
            "session_file": str(self._session_file),
            "expires": "",
        }
        if self._session_file.exists():
            try:
                data = json.loads(self._session_file.read_text())
                ts = datetime.fromisoformat(data.get("timestamp", ""))
                expires = ts + timedelta(hours=23)
                status["expires"] = expires.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        return status

    def authenticate(self, request_token: str) -> bool:
        """Complete OAuth flow with a request token.

        Args:
            request_token: Token from the Kite login redirect URL.

        Returns:
            True if authentication succeeded.
        """
        if not self.available:
            raise BrokerError("auth", "Kite client not available (missing library or credentials)")

        try:
            data = self._kite.generate_session(
                request_token=request_token,
                api_secret=self._api_secret,
            )
            self._kite.set_access_token(data["access_token"])
            self._save_session(data["access_token"], data)
            self._authenticated = True
            self._auth_time = datetime.now()
            self._user_name = data.get("user_name", "")
            self._user_id = data.get("user_id", "")
            logger.info(f"Kite authentication successful: {self._user_name}")
            return True
        except Exception as e:
            logger.error(f"Kite authentication failed: {e}")
            return False

    def login_url(self) -> str:
        """Get the Kite Connect login URL for OAuth."""
        if not self.available:
            raise BrokerError("login_url", "Kite client not available")
        return str(self._kite.login_url())

    def _require_auth(self) -> None:
        if not self._authenticated:
            raise AuthenticationError("Not authenticated. Run: diamond kite --auth")
        # Check if session has gone stale since we loaded it
        age = self.session_age_hours()
        if age >= 23.0:
            self._authenticated = False
            raise AuthenticationError("Kite session expired. Run `diamond kite --auth` to re-authenticate.")

    # --- Market data ---

    def get_quote(self, ticker: str) -> Optional[dict]:
        """Fetch live quote for a ticker. Falls back to yfinance."""
        if not self._authenticated:
            return self._yfinance_quote(ticker)

        try:
            instrument = f"{self._exchange}:{ticker}"
            quote = self._kite.quote(instrument)
            return quote.get(instrument)
        except Exception as e:
            logger.warning(f"Kite quote failed for {ticker}: {e}")
            return self._yfinance_quote(ticker)

    @staticmethod
    def _yfinance_quote(ticker: str) -> Optional[dict]:
        """Fallback price fetcher using yfinance."""
        try:
            import yfinance as yf

            sym = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
            info = yf.Ticker(sym).info
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            if not price:
                return None
            return {
                "last_price": price,
                "volume": info.get("volume", 0),
                "source": "yfinance",
            }
        except Exception:
            return None

    # --- Holdings ---

    def get_holdings(self) -> list[dict]:
        """Fetch current holdings from Kite account."""
        self._require_auth()
        return self._kite.holdings()

    def get_positions(self) -> dict:
        """Fetch day and net positions."""
        self._require_auth()
        return self._kite.positions()

    def get_holdings_mapped(self) -> dict[str, dict]:
        """Fetch Kite holdings and return mapped to yfinance tickers.

        Returns:
            {yf_ticker: {shares, avg_price, last_price, pnl, tradingsymbol}}
        """
        self._require_auth()
        raw = self._kite.holdings()
        result = {}
        for h in raw:
            if h.get("quantity", 0) <= 0:
                continue
            yf_ticker = kite_to_yf(h["tradingsymbol"])
            result[yf_ticker] = {
                "shares": h["quantity"],
                "avg_price": h.get("average_price", 0),
                "last_price": h.get("last_price", 0),
                "pnl": h.get("pnl", 0),
                "tradingsymbol": h["tradingsymbol"],
                "isin": h.get("isin", ""),
            }
        return result

    # --- Orders ---

    def place_order(
        self,
        ticker: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
    ) -> Optional[str]:
        """Place an order on Kite Connect.

        Args:
            ticker: Trading symbol (e.g., 'RELIANCE') — NOT yfinance format.
            action: 'BUY' or 'SELL'.
            quantity: Number of shares.
            order_type: 'MARKET' or 'LIMIT'.
            price: Limit price (required for LIMIT orders).

        Returns:
            Order ID string, or None on failure.
        """
        self._require_auth()
        cfg = get_config()

        if self._dry_run:
            logger.info(f"[DRY RUN] {action} {quantity} {ticker}")
            return f"DRY_RUN_{int(time.time())}"

        try:
            params: dict[str, Any] = {
                "variety": self._kite.VARIETY_REGULAR,
                "exchange": self._exchange,
                "tradingsymbol": ticker,
                "transaction_type": action,
                "quantity": quantity,
                "order_type": order_type,
                "product": cfg.kite.product_type,
                "validity": cfg.kite.order_validity,
            }
            if order_type == "LIMIT" and price is not None:
                params["price"] = price

            order_id = self._kite.place_order(**params)
            logger.info(f"Order placed: {order_id} ({action} {quantity} {ticker})")
            return str(order_id)

        except Exception as e:
            error_msg = str(e).lower()
            if "authoris" in error_msg or "cdsl" in error_msg or "tpin" in error_msg:
                raise BrokerError(
                    "place_order",
                    "Holdings not authorized for selling. Run: diamond kite authorize-sells",
                ) from e
            logger.error(f"Order failed: {e}")
            raise

    def get_order_status(self, order_id: str) -> Optional[dict]:
        """Fetch status of a specific order."""
        self._require_auth()
        try:
            for order in self._kite.orders():
                if order["order_id"] == order_id:
                    return order
        except Exception as e:
            logger.error(f"Order status check failed: {e}")
        return None

    def get_order_history(self, order_id: str) -> list[dict]:
        """Fetch full history of an order (status transitions)."""
        self._require_auth()
        try:
            return self._kite.order_history(order_id)
        except Exception as e:
            logger.error(f"Order history failed for {order_id}: {e}")
            return []

    def get_all_orders(self) -> list[dict]:
        """Fetch all orders for the day."""
        self._require_auth()
        try:
            return self._kite.orders()
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        self._require_auth()
        try:
            self._kite.cancel_order(variety="regular", order_id=order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False

    # --- CDSL Authorization (TPIN) ---

    def authorize_holdings(self) -> str:
        """Initiate CDSL holdings authorization for sell orders.

        This must be done once per trading day before selling.
        The user will be redirected to CDSL's portal to enter their TPIN.

        Returns:
            request_id for the authorization URL.
        """
        self._require_auth()
        response = self._kite._post("portfolio.holdings.authorise", params={})
        request_id = response.get("request_id", "")
        logger.info(f"CDSL authorization initiated: {request_id}")
        return request_id

    def authorization_url(self, request_id: str) -> str:
        """Generate the browser URL for CDSL authorization."""
        return f"https://kite.zerodha.com/connect/portfolio/authorise/holdings/{self._api_key}/{request_id}"

    def get_available_cash(self) -> float:
        """Fetch available cash (equity segment) from Kite account."""
        self._require_auth()
        try:
            margins = self._kite.margins("equity")
            return float(margins.get("available", {}).get("cash", 0))
        except Exception as e:
            logger.warning(f"Failed to fetch margins: {e}")
            return 0.0

    def check_sell_authorization(self) -> bool:
        """Check if holdings are authorized for selling today.

        Attempts a dummy check by inspecting holdings for authorisation field.
        Returns True if any holdings show as authorized.
        """
        self._require_auth()
        try:
            holdings = self._kite.holdings()
            # Kite marks holdings with 'authorised_quantity' or 'authorised_date'
            for h in holdings:
                if h.get("authorised_quantity", 0) > 0:
                    return True
                # Some API versions use different field
                if h.get("t1_quantity", 0) == 0 and h.get("quantity", 0) > 0:
                    # Has settled holdings — need to check if authorized
                    pass
            # If we got holdings without error, assume we can check at order time
            return False
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Holdings import: Kite -> Ledger
# ---------------------------------------------------------------------------


def import_holdings_from_kite(
    strategy: str,
    capital: float,
    kite_client: Optional[KiteClient] = None,
) -> dict:
    """Import current Kite holdings into a strategy's live ledger.

    Creates the ledger, records each holding as a synthetic BUY trade
    at the average price from Kite, and sets cash to the remainder.

    Args:
        strategy: Strategy name for the ledger.
        capital: Total capital (holdings value + remaining cash).
        kite_client: Optional pre-authenticated client.

    Returns:
        Summary dict with imported holdings and values.
    """
    from diamond.data.ledger import Ledger, Trade
    from diamond.execution.costs import calculate_costs

    if kite_client is None:
        kite_client = KiteClient()

    if not kite_client.authenticated:
        raise AuthenticationError()

    # Fetch holdings from Kite
    kite_holdings = kite_client.get_holdings_mapped()
    if not kite_holdings:
        raise BrokerError("import", "No holdings found in Kite account")

    # Reset ledger to fresh state with the given capital
    ledger = Ledger(strategy)
    ledger.reset(initial_capital=capital)

    today = datetime.now().strftime("%Y-%m-%d")
    imported = []
    total_invested = 0.0
    total_fees = 0.0

    for yf_ticker, info in sorted(kite_holdings.items()):
        shares = info["shares"]
        avg_price = info["avg_price"]
        value = shares * avg_price
        costs = calculate_costs("BUY", value)

        trade = Trade(
            timestamp=today,
            action="BUY",
            ticker=yf_ticker,
            shares=shares,
            price=avg_price,
            total_cost=costs.total,
            rationale="Imported from Kite",
        )
        ledger.record_trade(trade)
        total_invested += value + costs.total
        total_fees += costs.total

        imported.append(
            {
                "ticker": yf_ticker,
                "tradingsymbol": info["tradingsymbol"],
                "shares": shares,
                "avg_price": avg_price,
                "value": value,
            }
        )

    # Set last rebalance to today
    ledger.set_last_rebalance(today)

    return {
        "strategy": strategy,
        "holdings_count": len(imported),
        "holdings": imported,
        "total_invested": round(total_invested, 2),
        "total_fees": round(total_fees, 2),
        "remaining_cash": round(ledger.get_cash(), 2),
    }
