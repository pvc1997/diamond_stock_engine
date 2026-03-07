"""Tests for the structured exception hierarchy."""

from __future__ import annotations

import pytest

from diamond.exceptions import (
    DiamondError,
    DataError,
    PriceDownloadError,
    EmptyDataError,
    InsufficientDataError,
    ExecutionError,
    InsufficientCashError,
    RiskGateError,
    BrokerError,
    AuthenticationError,
    StrategyError,
    UnknownStrategyError,
    ConfigError,
)


class TestHierarchy:
    """All domain exceptions should be catchable via DiamondError."""

    @pytest.mark.parametrize("exc_cls,parent", [
        (DataError, DiamondError),
        (PriceDownloadError, DataError),
        (EmptyDataError, DataError),
        (InsufficientDataError, DataError),
        (ExecutionError, DiamondError),
        (InsufficientCashError, ExecutionError),
        (RiskGateError, ExecutionError),
        (BrokerError, ExecutionError),
        (AuthenticationError, BrokerError),
        (StrategyError, DiamondError),
        (UnknownStrategyError, StrategyError),
        (ConfigError, DiamondError),
    ])
    def test_inherits(self, exc_cls, parent):
        assert issubclass(exc_cls, parent)

    def test_all_catchable_as_diamond_error(self):
        with pytest.raises(DiamondError):
            raise PriceDownloadError(["TCS.NS"], "timeout")

        with pytest.raises(DiamondError):
            raise AuthenticationError()

        with pytest.raises(DiamondError):
            raise UnknownStrategyError("foo")


class TestPriceDownloadError:
    def test_message_with_reason(self):
        e = PriceDownloadError(["A.NS", "B.NS"], "network error")
        assert "A.NS" in str(e)
        assert "network error" in str(e)

    def test_message_without_reason(self):
        e = PriceDownloadError(["A.NS"])
        assert "A.NS" in str(e)

    def test_tickers_attribute(self):
        e = PriceDownloadError(["X.NS"])
        assert e.tickers == ["X.NS"]


class TestEmptyDataError:
    def test_with_period(self):
        e = EmptyDataError(["A.NS"], "2023-01-01 to 2023-06-01")
        assert "2023-01-01" in str(e)

    def test_without_period(self):
        e = EmptyDataError(["A.NS"])
        assert "A.NS" in str(e)


class TestInsufficientDataError:
    def test_with_need(self):
        e = InsufficientDataError("TCS.NS", 10, 30)
        assert "10" in str(e)
        assert "30" in str(e)

    def test_without_need(self):
        e = InsufficientDataError("TCS.NS", 5)
        assert "5" in str(e)


class TestInsufficientCashError:
    def test_amounts(self):
        e = InsufficientCashError(50000, 20000)
        assert e.required == 50000
        assert e.available == 20000
        assert "50,000" in str(e)


class TestRiskGateError:
    def test_signals(self):
        e = RiskGateError(["CRITICAL: drawdown > 15%"])
        assert e.signals == ["CRITICAL: drawdown > 15%"]
        assert "drawdown" in str(e)


class TestBrokerError:
    def test_operation(self):
        e = BrokerError("place_order", "timeout")
        assert e.operation == "place_order"
        assert "place_order" in str(e)


class TestAuthenticationError:
    def test_default_message(self):
        e = AuthenticationError()
        assert "diamond kite auth" in str(e)

    def test_is_broker_error(self):
        assert issubclass(AuthenticationError, BrokerError)


class TestUnknownStrategyError:
    def test_with_available(self):
        e = UnknownStrategyError("foo", ["baseline", "steady"])
        assert "foo" in str(e)
        assert "baseline" in str(e)

    def test_without_available(self):
        e = UnknownStrategyError("bar")
        assert "bar" in str(e)
        assert e.name == "bar"
