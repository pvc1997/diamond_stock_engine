"""Tests for structured metrics logging."""

from __future__ import annotations

import json
import logging

import pytest

from diamond.monitoring.metrics import (
    log_trade,
    log_rebalance,
    log_risk_signal,
    log_portfolio_snapshot,
    log_error,
    log_backtest_complete,
)


@pytest.fixture()
def capture_metrics(caplog):
    """Capture diamond.metrics log output."""
    with caplog.at_level(logging.INFO, logger="diamond.metrics"):
        yield caplog


def _parse_last(caplog) -> dict:
    """Parse the last metrics log record as JSON."""
    records = [r for r in caplog.records if r.name == "diamond.metrics"]
    assert len(records) > 0, "No metrics records found"
    return json.loads(records[-1].message)


class TestLogTrade:
    def test_emits_json(self, capture_metrics):
        log_trade("gods_plan", "BUY", "TCS.NS", 10, 3500.0, 42.5, "Rebalance")
        data = _parse_last(capture_metrics)
        assert data["event"] == "trade"
        assert data["strategy"] == "gods_plan"
        assert data["action"] == "BUY"
        assert data["ticker"] == "TCS.NS"
        assert data["shares"] == 10
        assert data["price"] == 3500.0
        assert data["value"] == 35000.0
        assert data["cost"] == 42.5
        assert data["reason"] == "Rebalance"
        assert "ts" in data

    def test_sell(self, capture_metrics):
        log_trade("steady", "SELL", "INFY.NS", 5, 1500.0, 18.0)
        data = _parse_last(capture_metrics)
        assert data["action"] == "SELL"
        assert data["value"] == 7500.0


class TestLogRebalance:
    def test_emits_json(self, capture_metrics):
        log_rebalance("gods_plan", 5, 200.0, 500000.0, 20000.0, 18, smart=True)
        data = _parse_last(capture_metrics)
        assert data["event"] == "rebalance"
        assert data["trades"] == 5
        assert data["smart"] is True

    def test_not_smart(self, capture_metrics):
        log_rebalance("baseline", 3, 100.0, 100000.0, 5000.0, 10)
        data = _parse_last(capture_metrics)
        assert data["smart"] is False


class TestLogRiskSignal:
    def test_with_value(self, capture_metrics):
        log_risk_signal("gods_plan", "WARNING", "drawdown > 10%", 12.5)
        data = _parse_last(capture_metrics)
        assert data["event"] == "risk_signal"
        assert data["level"] == "WARNING"
        assert data["value"] == 12.5

    def test_without_value(self, capture_metrics):
        log_risk_signal("steady", "CRITICAL", "VaR breach")
        data = _parse_last(capture_metrics)
        assert "value" not in data


class TestLogPortfolioSnapshot:
    def test_emits_json(self, capture_metrics):
        log_portfolio_snapshot("gods_plan", 500000.0, 20000.0, 18, 5.2)
        data = _parse_last(capture_metrics)
        assert data["event"] == "portfolio_snapshot"
        assert data["nav"] == 500000.0
        assert data["drawdown_pct"] == 5.2


class TestLogError:
    def test_with_context(self, capture_metrics):
        log_error("price_download", "timeout", strategy="gods_plan", ticker="TCS.NS")
        data = _parse_last(capture_metrics)
        assert data["event"] == "error"
        assert data["strategy"] == "gods_plan"
        assert data["ticker"] == "TCS.NS"

    def test_minimal(self, capture_metrics):
        log_error("config_load", "missing .env")
        data = _parse_last(capture_metrics)
        assert data["event"] == "error"
        assert "strategy" not in data


class TestLogBacktestComplete:
    def test_emits_json(self, capture_metrics):
        log_backtest_complete("gods_plan", "2020-01-01", "2025-01-01", 18.5, 1.2, 15.3, 120.5)
        data = _parse_last(capture_metrics)
        assert data["event"] == "backtest_complete"
        assert data["cagr"] == 18.5
        assert data["sharpe"] == 1.2
        assert data["max_drawdown"] == 15.3
        assert data["total_return"] == 120.5
