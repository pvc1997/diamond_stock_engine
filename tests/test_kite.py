"""Tests for Kite Connect client."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from diamond.execution.kite import (
    KiteClient,
    kite_to_yf,
    yf_to_kite,
    import_holdings_from_kite,
)


class TestTickerMapping:
    def test_kite_to_yf(self):
        assert kite_to_yf("RELIANCE") == "RELIANCE.NS"
        assert kite_to_yf("M&M") == "M&M.NS"

    def test_kite_to_yf_already_suffixed(self):
        assert kite_to_yf("RELIANCE.NS") == "RELIANCE.NS"
        assert kite_to_yf("RELIANCE.BO") == "RELIANCE.BO"

    def test_yf_to_kite(self):
        assert yf_to_kite("RELIANCE.NS") == "RELIANCE"
        assert yf_to_kite("M&M.NS") == "M&M"
        assert yf_to_kite("RELIANCE.BO") == "RELIANCE"

    def test_yf_to_kite_no_suffix(self):
        assert yf_to_kite("RELIANCE") == "RELIANCE"

    def test_roundtrip(self):
        assert yf_to_kite(kite_to_yf("RELIANCE")) == "RELIANCE"
        assert yf_to_kite(kite_to_yf("M&M")) == "M&M"


class TestKiteClient:
    @patch("diamond.execution.kite.KITE_AVAILABLE", False)
    def test_unavailable_without_library(self):
        client = KiteClient()
        assert client.available is False
        assert client.authenticated is False

    def test_not_authenticated_raises(self):
        with patch("diamond.execution.kite.KITE_AVAILABLE", False):
            client = KiteClient()
            from diamond.exceptions import AuthenticationError
            with pytest.raises(AuthenticationError, match="Not authenticated"):
                client.get_holdings()

    @patch("yfinance.Ticker")
    def test_yfinance_fallback_quote(self, mock_yf_ticker):
        mock_info = {"currentPrice": 2500.0, "volume": 1000000}
        mock_yf_ticker.return_value = MagicMock(info=mock_info)

        result = KiteClient._yfinance_quote("RELIANCE")
        assert result is not None
        assert result["last_price"] == 2500.0
        assert result["source"] == "yfinance"

    @patch("yfinance.Ticker")
    def test_yfinance_fallback_no_price(self, mock_yf_ticker):
        mock_yf_ticker.return_value = MagicMock(info={})
        result = KiteClient._yfinance_quote("UNKNOWN")
        assert result is None

    def test_available_with_credentials(self):
        mock_kite = MagicMock()

        with patch("diamond.execution.kite.KITE_AVAILABLE", True), \
             patch("diamond.execution.kite.KiteConnect", mock_kite, create=True), \
             patch("diamond.execution.kite.get_config") as mock_config:
            cfg = MagicMock()
            cfg.kite.api_key = "test_key"
            cfg.kite.api_secret = "test_secret"
            cfg.kite.exchange = "NSE"
            cfg.kite.dry_run = True
            session_path = MagicMock()
            session_path.exists.return_value = False
            cfg.data_dir.__truediv__ = MagicMock(return_value=session_path)
            mock_config.return_value = cfg

            client = KiteClient()
            assert client.available is True
            assert client.authenticated is False

    def test_authenticate_success(self):
        mock_kite_instance = MagicMock()
        mock_kite_instance.generate_session.return_value = {
            "access_token": "abc123",
            "user_id": "AB1234",
            "user_name": "Test User",
        }
        mock_kite_cls = MagicMock(return_value=mock_kite_instance)

        with patch("diamond.execution.kite.KITE_AVAILABLE", True), \
             patch("diamond.execution.kite.KiteConnect", mock_kite_cls, create=True), \
             patch("diamond.execution.kite.get_config") as mock_config:
            cfg = MagicMock()
            cfg.kite.api_key = "test_key"
            cfg.kite.api_secret = "test_secret"
            cfg.kite.exchange = "NSE"
            cfg.kite.dry_run = True
            session_path = MagicMock()
            session_path.exists.return_value = False
            session_path.parent.mkdir = MagicMock()
            session_path.write_text = MagicMock()
            session_path.chmod = MagicMock()
            cfg.data_dir.__truediv__ = MagicMock(return_value=session_path)
            mock_config.return_value = cfg

            client = KiteClient()
            assert client.authenticate("test_token") is True
            assert client.authenticated is True
            assert client.user_name == "Test User"
            assert client.user_id == "AB1234"

    def test_dry_run_order(self):
        mock_kite_instance = MagicMock()
        mock_kite_instance.generate_session.return_value = {
            "access_token": "abc123",
            "user_id": "AB1234",
            "user_name": "Test",
        }
        mock_kite_cls = MagicMock(return_value=mock_kite_instance)

        with patch("diamond.execution.kite.KITE_AVAILABLE", True), \
             patch("diamond.execution.kite.KiteConnect", mock_kite_cls, create=True), \
             patch("diamond.execution.kite.get_config") as mock_config:
            cfg = MagicMock()
            cfg.kite.api_key = "test_key"
            cfg.kite.api_secret = "test_secret"
            cfg.kite.exchange = "NSE"
            cfg.kite.dry_run = True
            cfg.kite.product_type = "CNC"
            cfg.kite.order_validity = "DAY"
            session_path = MagicMock()
            session_path.exists.return_value = False
            session_path.parent.mkdir = MagicMock()
            session_path.write_text = MagicMock()
            session_path.chmod = MagicMock()
            cfg.data_dir.__truediv__ = MagicMock(return_value=session_path)
            mock_config.return_value = cfg

            client = KiteClient()
            client.authenticate("test_token")

            order_id = client.place_order("RELIANCE", "BUY", 10)
            assert order_id is not None
            assert order_id.startswith("DRY_RUN_")
            mock_kite_instance.place_order.assert_not_called()

    def test_session_status(self):
        with patch("diamond.execution.kite.KITE_AVAILABLE", False):
            client = KiteClient()
            status = client.session_status()
            assert status["available"] is False
            assert status["authenticated"] is False

    def test_get_holdings_mapped(self):
        mock_kite_instance = MagicMock()
        mock_kite_instance.generate_session.return_value = {
            "access_token": "abc123",
            "user_id": "AB1234",
            "user_name": "Test",
        }
        mock_kite_instance.holdings.return_value = [
            {
                "tradingsymbol": "RELIANCE",
                "quantity": 10,
                "average_price": 2500.0,
                "last_price": 2600.0,
                "pnl": 1000.0,
                "isin": "INE002A01018",
            },
            {
                "tradingsymbol": "TCS",
                "quantity": 5,
                "average_price": 3400.0,
                "last_price": 3500.0,
                "pnl": 500.0,
                "isin": "INE467B01029",
            },
            {
                "tradingsymbol": "SOLD_STOCK",
                "quantity": 0,
                "average_price": 100.0,
                "last_price": 0,
                "pnl": 0,
            },
        ]
        mock_kite_cls = MagicMock(return_value=mock_kite_instance)

        with patch("diamond.execution.kite.KITE_AVAILABLE", True), \
             patch("diamond.execution.kite.KiteConnect", mock_kite_cls, create=True), \
             patch("diamond.execution.kite.get_config") as mock_config:
            cfg = MagicMock()
            cfg.kite.api_key = "test_key"
            cfg.kite.api_secret = "test_secret"
            cfg.kite.exchange = "NSE"
            cfg.kite.dry_run = True
            session_path = MagicMock()
            session_path.exists.return_value = False
            session_path.parent.mkdir = MagicMock()
            session_path.write_text = MagicMock()
            session_path.chmod = MagicMock()
            cfg.data_dir.__truediv__ = MagicMock(return_value=session_path)
            mock_config.return_value = cfg

            client = KiteClient()
            client.authenticate("test_token")

            mapped = client.get_holdings_mapped()
            assert "RELIANCE.NS" in mapped
            assert "TCS.NS" in mapped
            assert "SOLD_STOCK.NS" not in mapped  # Zero qty filtered out
            assert mapped["RELIANCE.NS"]["shares"] == 10
            assert mapped["RELIANCE.NS"]["avg_price"] == 2500.0
            assert mapped["TCS.NS"]["tradingsymbol"] == "TCS"


class TestImportHoldings:
    def _make_mock_client(self, holdings=None):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.get_holdings_mapped.return_value = holdings or {}
        return mock_client

    def test_import_creates_ledger(self, tmp_path):
        mock_client = self._make_mock_client({
            "RELIANCE.NS": {
                "shares": 10,
                "avg_price": 2500.0,
                "last_price": 2600.0,
                "pnl": 1000.0,
                "tradingsymbol": "RELIANCE",
                "isin": "INE002A01018",
            },
            "TCS.NS": {
                "shares": 5,
                "avg_price": 3400.0,
                "last_price": 3500.0,
                "pnl": 500.0,
                "tradingsymbol": "TCS",
                "isin": "INE467B01029",
            },
        })

        # Patch get_config to use tmp_path for ledger storage
        with patch("diamond.data.ledger.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.ledger_dir = tmp_path
            cfg.risk.initial_capital = 500000

            def ledger_path(strategy):
                return tmp_path / f"{strategy}.db"

            cfg.ledger_path = ledger_path
            mock_cfg.return_value = cfg

            result = import_holdings_from_kite("test", 500000, mock_client)

        assert result["holdings_count"] == 2
        assert result["strategy"] == "test"
        assert result["remaining_cash"] > 0
        # Total invested should be ~42,000 (25000 + 17000)
        assert result["total_invested"] > 40000

    def test_import_requires_auth(self):
        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = False

        from diamond.exceptions import AuthenticationError
        with pytest.raises(AuthenticationError):
            import_holdings_from_kite("test", 500000, mock_client)

    def test_import_requires_holdings(self):
        from diamond.exceptions import BrokerError
        mock_client = self._make_mock_client({})

        with pytest.raises(BrokerError, match="No holdings"):
            import_holdings_from_kite("test", 500000, mock_client)
