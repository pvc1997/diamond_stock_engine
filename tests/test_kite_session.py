"""Tests for Kite session resilience — validity, expiry, and graceful failure."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from diamond.execution.kite import KiteClient


def _make_client_with_session(tmp_path: Path, session_data: dict | None = None, **overrides):
    """Helper: create a KiteClient with a controlled session file."""
    session_file = tmp_path / "kite_session.json"

    if session_data is not None:
        session_file.write_text(json.dumps(session_data))

    mock_kite_instance = MagicMock()
    mock_kite_cls = MagicMock(return_value=mock_kite_instance)

    with patch("diamond.execution.kite.KITE_AVAILABLE", True), \
         patch("diamond.execution.kite.KiteConnect", mock_kite_cls, create=True), \
         patch("diamond.execution.kite.get_config") as mock_config:
        cfg = MagicMock()
        cfg.kite.api_key = overrides.get("api_key", "test_key")
        cfg.kite.api_secret = overrides.get("api_secret", "test_secret")
        cfg.kite.exchange = "NSE"
        cfg.kite.dry_run = True
        cfg.data_dir.__truediv__ = MagicMock(return_value=session_file)
        mock_config.return_value = cfg

        client = KiteClient()

    # Override internal session_file path so subsequent calls use it
    client._session_file = session_file
    return client, mock_kite_instance


class TestSessionAgeHours:
    def test_fresh_session(self, tmp_path: Path):
        now = datetime.now()
        data = {"access_token": "abc", "timestamp": now.isoformat()}
        client, _ = _make_client_with_session(tmp_path, data)

        age = client.session_age_hours()
        assert age < 0.1  # Less than a few minutes

    def test_old_session(self, tmp_path: Path):
        old = datetime.now() - timedelta(hours=20)
        data = {"access_token": "abc", "timestamp": old.isoformat()}
        client, _ = _make_client_with_session(tmp_path, data)

        age = client.session_age_hours()
        assert 19.5 < age < 20.5

    def test_expired_session(self, tmp_path: Path):
        expired = datetime.now() - timedelta(hours=24)
        data = {"access_token": "abc", "timestamp": expired.isoformat()}
        client, _ = _make_client_with_session(tmp_path, data)

        age = client.session_age_hours()
        assert age >= 23.0

    def test_missing_file(self, tmp_path: Path):
        client, _ = _make_client_with_session(tmp_path, session_data=None)

        age = client.session_age_hours()
        assert age == float("inf")

    def test_corrupt_file(self, tmp_path: Path):
        client, _ = _make_client_with_session(tmp_path, session_data=None)
        client._session_file.write_text("not json at all {{{{")

        age = client.session_age_hours()
        assert age == float("inf")


class TestIsSessionValid:
    def test_valid_fresh_session(self, tmp_path: Path):
        now = datetime.now()
        data = {"access_token": "abc", "timestamp": now.isoformat()}
        client, mock_kite = _make_client_with_session(tmp_path, data)
        # Mark as authenticated to trigger API ping
        client._authenticated = True
        mock_kite.profile.return_value = {"user_id": "AB1234"}

        assert client.is_session_valid() is True

    def test_expired_session(self, tmp_path: Path):
        expired = datetime.now() - timedelta(hours=24)
        data = {"access_token": "abc", "timestamp": expired.isoformat()}
        client, _ = _make_client_with_session(tmp_path, data)

        assert client.is_session_valid() is False

    def test_missing_session_file(self, tmp_path: Path):
        client, _ = _make_client_with_session(tmp_path, session_data=None)

        assert client.is_session_valid() is False

    def test_corrupt_session_file(self, tmp_path: Path):
        client, _ = _make_client_with_session(tmp_path, session_data=None)
        client._session_file.write_text("corrupted{{{")

        assert client.is_session_valid() is False

    def test_missing_fields_in_session(self, tmp_path: Path):
        # Has JSON but missing required fields
        data = {"some_other_key": "value"}
        client, _ = _make_client_with_session(tmp_path, data)

        assert client.is_session_valid() is False

    def test_api_ping_rejects_token(self, tmp_path: Path):
        now = datetime.now()
        data = {"access_token": "abc", "timestamp": now.isoformat()}
        client, mock_kite = _make_client_with_session(tmp_path, data)
        client._authenticated = True
        mock_kite.profile.side_effect = Exception("TokenException: session expired")

        assert client.is_session_valid() is False

    def test_api_ping_network_error(self, tmp_path: Path):
        """Non-auth API errors should NOT invalidate the session (fail-open)."""
        now = datetime.now()
        data = {"access_token": "abc", "timestamp": now.isoformat()}
        client, mock_kite = _make_client_with_session(tmp_path, data)
        client._authenticated = True
        mock_kite.profile.side_effect = ConnectionError("Network unreachable")

        # Network error is not an auth error — session still considered valid
        assert client.is_session_valid() is True

    def test_not_authenticated_skips_api_ping(self, tmp_path: Path):
        now = datetime.now()
        data = {"access_token": "abc", "timestamp": now.isoformat()}
        client, mock_kite = _make_client_with_session(tmp_path, data)
        client._authenticated = False

        # File is valid and fresh, API ping skipped since not authenticated
        assert client.is_session_valid() is True
        mock_kite.profile.assert_not_called()


class TestRequireAuthExpiry:
    def test_require_auth_detects_expired(self, tmp_path: Path):
        expired = datetime.now() - timedelta(hours=24)
        data = {"access_token": "abc", "timestamp": expired.isoformat()}
        client, _ = _make_client_with_session(tmp_path, data)
        client._authenticated = True

        from diamond.exceptions import AuthenticationError
        with pytest.raises(AuthenticationError, match="session expired"):
            client._require_auth()
        # Should also flip authenticated to False
        assert client._authenticated is False

    def test_require_auth_passes_fresh(self, tmp_path: Path):
        now = datetime.now()
        data = {"access_token": "abc", "timestamp": now.isoformat()}
        client, _ = _make_client_with_session(tmp_path, data)
        client._authenticated = True

        # Should not raise
        client._require_auth()


class TestForceAuditLog:
    def test_force_override_logged(self, tmp_path: Path):
        from diamond.execution.executor import _log_force_override

        with patch("diamond.execution.executor.get_config") as mock_config:
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config.return_value = cfg

            _log_force_override("gods_plan", ["CRITICAL: Drawdown 18%", "CRITICAL: VaR breach"])

        log_path = tmp_path / "force_audit.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "gods_plan" in content
        assert "CRITICAL: Drawdown 18%" in content
        assert "CRITICAL: VaR breach" in content
        # Two lines (one per signal)
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 2

    def test_force_audit_append_only(self, tmp_path: Path):
        from diamond.execution.executor import _log_force_override

        with patch("diamond.execution.executor.get_config") as mock_config:
            cfg = MagicMock()
            cfg.data_dir = tmp_path
            mock_config.return_value = cfg

            _log_force_override("steady", ["CRITICAL: Signal A"])
            _log_force_override("gods_plan", ["CRITICAL: Signal B"])

        log_path = tmp_path / "force_audit.log"
        content = log_path.read_text()
        assert "steady" in content
        assert "gods_plan" in content
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 2

    def test_force_audit_fail_open(self, tmp_path: Path):
        """Audit log failure should not crash."""
        from diamond.execution.executor import _log_force_override

        with patch("diamond.execution.executor.get_config") as mock_config:
            cfg = MagicMock()
            # Point to a non-writable path
            cfg.data_dir = Path("/nonexistent/path/that/wont/work")
            mock_config.return_value = cfg

            # Should not raise
            _log_force_override("test", ["CRITICAL: something"])


class TestLiveSessionValidation:
    def test_execute_live_aborts_on_expired_session(self):
        """execute_live should return error if session is expired."""
        from diamond.execution.live import execute_live

        mock_client = MagicMock(spec=KiteClient)
        mock_client.authenticated = True
        mock_client.is_session_valid.return_value = False

        result = execute_live(
            strategy="test",
            target_allocation={"RELIANCE.NS": 25000},
            capital=500000,
            kite_client=mock_client,
        )

        assert result["status"] == "error"
        assert "expired" in result["reason"].lower()

    def test_execute_orders_aborts_batch_on_auth_error(self):
        """_execute_orders should abort remaining trades on session error."""
        from diamond.execution.live import _execute_orders

        mock_client = MagicMock(spec=KiteClient)
        mock_client.place_order.side_effect = RuntimeError("Kite session expired. Run `diamond kite --auth` to re-authenticate.")

        mock_ledger = MagicMock()

        trades = [
            {"ticker": "A.NS", "kite_symbol": "A", "shares": 10, "price": 100, "value": 1000, "est_cost": 5},
            {"ticker": "B.NS", "kite_symbol": "B", "shares": 5, "price": 200, "value": 1000, "est_cost": 5},
            {"ticker": "C.NS", "kite_symbol": "C", "shares": 3, "price": 300, "value": 900, "est_cost": 5},
        ]

        results = _execute_orders(mock_client, trades, "BUY", mock_ledger, dry_run=False)

        # First trade blocked, remaining aborted
        assert results[0]["status"] == "blocked"
        assert results[1]["status"] == "aborted"
        assert results[2]["status"] == "aborted"
        # Only one API call was made
        assert mock_client.place_order.call_count == 1

    def test_execute_orders_aborts_on_token_exception(self):
        """_execute_orders should detect token errors from generic exceptions."""
        from diamond.execution.live import _execute_orders

        mock_client = MagicMock(spec=KiteClient)
        mock_client.place_order.side_effect = Exception("TokenException: Invalid token")

        mock_ledger = MagicMock()

        trades = [
            {"ticker": "A.NS", "kite_symbol": "A", "shares": 10, "price": 100, "value": 1000, "est_cost": 5},
            {"ticker": "B.NS", "kite_symbol": "B", "shares": 5, "price": 200, "value": 1000, "est_cost": 5},
        ]

        results = _execute_orders(mock_client, trades, "BUY", mock_ledger, dry_run=False)

        assert results[0]["status"] == "blocked"
        assert results[1]["status"] == "aborted"
