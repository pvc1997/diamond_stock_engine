"""Tests for risk gate and corporate action integration in executor."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from diamond.execution.executor import _check_risk_gate, _sync_corporate_actions


class TestRiskGate:
    def test_returns_empty_when_safe(self):
        with patch("diamond.monitoring.risk.compute_risk_report") as mock_report:
            report = MagicMock()
            report.signals = ["WARNING: Something minor"]
            mock_report.return_value = report

            result = _check_risk_gate("test", {"A.NS": 100.0})
            assert result == []

    def test_returns_critical_signals(self):
        with patch("diamond.monitoring.risk.compute_risk_report") as mock_report:
            report = MagicMock()
            report.signals = [
                "CRITICAL: Drawdown 16.0% from high-water mark — consider liquidating",
                "WARNING: Something minor",
            ]
            mock_report.return_value = report

            result = _check_risk_gate("test", {"A.NS": 100.0})
            assert len(result) == 1
            assert "CRITICAL" in result[0]

    def test_graceful_on_failure(self):
        with patch("diamond.monitoring.risk.compute_risk_report") as mock_report:
            mock_report.side_effect = Exception("DB error")

            result = _check_risk_gate("test", {"A.NS": 100.0})
            assert result == []  # Fails open — don't block on error


class TestSyncCorporateActions:
    def test_returns_count_applied(self):
        with patch("diamond.data.corporate_actions.process_actions") as mock_proc:
            mock_proc.return_value = [MagicMock(), MagicMock()]

            result = _sync_corporate_actions("test")
            assert result == 2

    def test_returns_zero_on_none(self):
        with patch("diamond.data.corporate_actions.process_actions") as mock_proc:
            mock_proc.return_value = []

            result = _sync_corporate_actions("test")
            assert result == 0

    def test_graceful_on_failure(self):
        with patch("diamond.data.corporate_actions.process_actions") as mock_proc:
            mock_proc.side_effect = Exception("yfinance down")

            result = _sync_corporate_actions("test")
            assert result == 0  # Fails gracefully
