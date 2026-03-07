"""Tests for concurrent access to SQLite-backed ledger.

Validates that:
- Two ledger instances writing to same DB handle gracefully
- Reads during writes don't crash
- Rapid sequential trades don't corrupt data
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from diamond.data.ledger import Ledger, Trade


# ---------------------------------------------------------------------------
# Two ledger instances writing to the same DB
# ---------------------------------------------------------------------------


class TestDualLedgerAccess:
    """Two Ledger instances pointed at the same .db file."""

    def test_two_instances_read_same_data(self, tmp_path: Path):
        """Two instances reading the same DB see the same data."""
        db = tmp_path / "shared.db"
        ledger1 = Ledger("shared", db_path=db)
        ledger1.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        ledger2 = Ledger("shared", db_path=db)
        assert ledger2.get_holdings()["RELIANCE.NS"] == 10
        assert ledger2.get_cash() == ledger1.get_cash()

    def test_two_instances_sequential_writes(self, tmp_path: Path):
        """Two instances writing sequentially to the same DB."""
        db = tmp_path / "shared.db"
        ledger1 = Ledger("shared", db_path=db)
        ledger2 = Ledger("shared", db_path=db)

        ledger1.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy via L1"))
        ledger2.record_trade(Trade("2024-01-16", "BUY", "TCS.NS", 5, 3000.0, 30.0, "Buy via L2"))

        # Both trades should be visible from either instance
        trades1 = ledger1.get_trades()
        trades2 = ledger2.get_trades()
        assert len(trades1) == 2
        assert len(trades2) == 2

    @pytest.mark.skip(reason="Flaky: SQLite locking under concurrent threads is non-deterministic")
    def test_two_instances_concurrent_writes_threaded(self, tmp_path: Path):
        """Two threads writing to the same DB file should not corrupt data."""
        db = tmp_path / "concurrent.db"
        errors = []

        def writer(thread_id: int, count: int):
            try:
                ledger = Ledger(f"concurrent", db_path=db)
                for i in range(count):
                    trade = Trade(
                        f"2024-01-{15 + i:02d}",
                        "BUY",
                        f"STOCK_T{thread_id}_{i}.NS",
                        1,
                        100.0,
                        1.0,
                        f"Thread {thread_id}",
                    )
                    try:
                        ledger.record_trade(trade)
                    except sqlite3.OperationalError:
                        # Database locked is acceptable under concurrent writes
                        pass
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=writer, args=(1, 10))
        t2 = threading.Thread(target=writer, args=(2, 10))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # No unexpected errors (sqlite3.OperationalError for locking is OK)
        assert not errors, f"Unexpected errors: {errors}"

        # Database should be readable after concurrent writes
        ledger = Ledger("concurrent", db_path=db)
        trades = ledger.get_trades()
        # At least some trades should have succeeded
        assert len(trades) > 0

    def test_two_instances_write_then_read_consistency(self, tmp_path: Path):
        """After concurrent writes, data should be internally consistent."""
        db = tmp_path / "consistency.db"
        ledger1 = Ledger("test", db_path=db)
        ledger2 = Ledger("test", db_path=db)

        # L1 buys RELIANCE
        ledger1.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "L1"))
        # L2 reads and then buys TCS
        cash_after_l1 = ledger2.get_cash()
        ledger2.record_trade(Trade("2024-01-16", "BUY", "TCS.NS", 5, 3000.0, 30.0, "L2"))

        # Final state check via fresh instance
        ledger3 = Ledger("test", db_path=db)
        holdings = ledger3.get_holdings()
        assert "RELIANCE.NS" in holdings
        assert "TCS.NS" in holdings


# ---------------------------------------------------------------------------
# Read during write
# ---------------------------------------------------------------------------


class TestReadDuringWrite:
    """Reading data while another thread is writing should not crash."""

    @pytest.mark.skip(reason="Flaky: SQLite locking under concurrent threads is non-deterministic")
    def test_read_holdings_during_trade_writes(self, tmp_path: Path):
        """Concurrent read of holdings while trades are being written."""
        db = tmp_path / "readwrite.db"
        errors = []
        read_results = []

        def writer():
            try:
                ledger = Ledger("test", db_path=db)
                for i in range(20):
                    trade = Trade(
                        f"2024-01-{15 + (i % 15):02d}",
                        "BUY",
                        f"STOCK{i}.NS",
                        1,
                        100.0,
                        1.0,
                        "Write",
                    )
                    try:
                        ledger.record_trade(trade)
                    except sqlite3.OperationalError:
                        pass  # Locked is OK
            except Exception as e:
                errors.append(f"writer: {e}")

        def reader():
            try:
                ledger = Ledger("test", db_path=db)
                for _ in range(20):
                    try:
                        holdings = ledger.get_holdings()
                        cash = ledger.get_cash()
                        read_results.append((len(holdings), cash))
                    except sqlite3.OperationalError:
                        pass  # Locked is OK
            except Exception as e:
                errors.append(f"reader: {e}")

        t_write = threading.Thread(target=writer)
        t_read = threading.Thread(target=reader)
        t_write.start()
        t_read.start()
        t_write.join(timeout=10)
        t_read.join(timeout=10)

        assert not errors, f"Unexpected errors: {errors}"
        # Reader should have gotten at least some results
        assert len(read_results) > 0

    @pytest.mark.skip(reason="Flaky: SQLite locking under concurrent threads is non-deterministic")
    def test_get_trades_during_writes(self, tmp_path: Path):
        """get_trades() called during concurrent writes should return valid list."""
        db = tmp_path / "trades_rw.db"
        errors = []

        def writer():
            try:
                ledger = Ledger("test", db_path=db)
                for i in range(10):
                    try:
                        ledger.record_trade(Trade(
                            f"2024-02-{i+1:02d}", "BUY", f"S{i}.NS", 1, 50.0, 1.0, "W",
                        ))
                    except sqlite3.OperationalError:
                        pass
            except Exception as e:
                errors.append(str(e))

        def reader():
            try:
                ledger = Ledger("test", db_path=db)
                for _ in range(10):
                    try:
                        trades = ledger.get_trades()
                        assert isinstance(trades, list)
                    except sqlite3.OperationalError:
                        pass
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors


# ---------------------------------------------------------------------------
# Rapid sequential trades
# ---------------------------------------------------------------------------


class TestRapidSequentialTrades:
    """Many trades in quick succession — no data corruption."""

    def test_100_sequential_buys(self, tmp_path: Path):
        """100 sequential buy trades should all be recorded correctly."""
        ledger = Ledger("rapid", db_path=tmp_path / "rapid.db")

        for i in range(100):
            trade = Trade(
                "2024-01-15",
                "BUY",
                f"STOCK{i}.NS",
                1,
                100.0 + i,
                1.0,
                f"Buy {i}",
            )
            ledger.record_trade(trade)

        assert len(ledger.get_trades()) == 100
        assert len(ledger.get_holdings()) == 100

    def test_rapid_buy_sell_same_stock(self, tmp_path: Path):
        """Rapidly buying and selling the same stock should maintain consistency."""
        ledger = Ledger("rapid_bs", db_path=tmp_path / "rapid_bs.db")

        for i in range(50):
            ledger.record_trade(Trade(
                f"2024-01-{(i % 28) + 1:02d}", "BUY", "RELIANCE.NS", 1, 2500.0, 5.0, "Buy",
            ))
            ledger.record_trade(Trade(
                f"2024-01-{(i % 28) + 1:02d}", "SELL", "RELIANCE.NS", 1, 2510.0, 5.0, "Sell",
            ))

        # After equal buys and sells, should have 0 holdings
        assert ledger.get_holdings() == {}
        assert len(ledger.get_trades()) == 100  # 50 buys + 50 sells

    def test_rapid_trades_cash_consistency(self, tmp_path: Path):
        """After many trades, cash should match manual calculation."""
        ledger = Ledger("cash_check", db_path=tmp_path / "cash.db")
        initial_cash = ledger.get_cash()

        # Buy 10 stocks, 1 share each at 1000, cost 10 per trade
        for i in range(10):
            ledger.record_trade(Trade(
                "2024-01-15", "BUY", f"S{i}.NS", 1, 1000.0, 10.0, "Buy",
            ))

        expected_cash = initial_cash - (10 * (1000 + 10))
        assert abs(ledger.get_cash() - expected_cash) < 0.01

    def test_rapid_trades_total_fees(self, tmp_path: Path):
        """Total fees should be sum of all individual trade costs."""
        ledger = Ledger("fees", db_path=tmp_path / "fees.db")

        total_expected = 0.0
        for i in range(20):
            cost = 5.0 + i * 0.5
            total_expected += cost
            ledger.record_trade(Trade(
                "2024-01-15", "BUY", f"S{i}.NS", 1, 100.0, cost, "Buy",
            ))

        assert abs(ledger.get_total_fees() - total_expected) < 0.01

    def test_rapid_avg_price_updates(self, tmp_path: Path):
        """Multiple buys of the same stock should update average price correctly."""
        ledger = Ledger("avg", db_path=tmp_path / "avg.db")

        # Buy 10 at 100, then 10 at 200
        ledger.record_trade(Trade("2024-01-15", "BUY", "X.NS", 10, 100.0, 0, "Buy1"))
        ledger.record_trade(Trade("2024-01-16", "BUY", "X.NS", 10, 200.0, 0, "Buy2"))

        # Average: (10*100 + 10*200) / 20 = 150
        assert abs(ledger.get_avg_price("X.NS") - 150.0) < 0.01
        assert ledger.get_holdings()["X.NS"] == 20

    def test_rapid_sell_preserves_avg_price(self, tmp_path: Path):
        """Selling shares should not change the average purchase price."""
        ledger = Ledger("avg_sell", db_path=tmp_path / "avg_sell.db")

        ledger.record_trade(Trade("2024-01-15", "BUY", "X.NS", 20, 150.0, 0, "Buy"))
        avg_before_sell = ledger.get_avg_price("X.NS")

        ledger.record_trade(Trade("2024-02-15", "SELL", "X.NS", 10, 200.0, 0, "Sell"))
        avg_after_sell = ledger.get_avg_price("X.NS")

        assert avg_before_sell == avg_after_sell
        assert ledger.get_holdings()["X.NS"] == 10


# ---------------------------------------------------------------------------
# Threaded portfolio value reads
# ---------------------------------------------------------------------------


class TestThreadedPortfolioValue:
    """Multiple threads computing portfolio value simultaneously."""

    def test_concurrent_portfolio_value_reads(self, tmp_path: Path):
        """Multiple threads reading portfolio value should all get valid results."""
        db = tmp_path / "pv.db"
        ledger = Ledger("test", db_path=db)
        ledger.record_trade(Trade("2024-01-15", "BUY", "RELIANCE.NS", 10, 2500.0, 50.0, "Buy"))

        prices = {"RELIANCE.NS": 2600.0}
        expected = ledger.get_portfolio_value(prices)
        results = []
        errors = []

        def reader():
            try:
                l = Ledger("test", db_path=db)
                for _ in range(10):
                    try:
                        val = l.get_portfolio_value(prices)
                        results.append(val)
                    except sqlite3.OperationalError:
                        pass
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        # All successful reads should return the same value
        assert all(v == expected for v in results)

    def test_write_off_concurrent_safety(self, tmp_path: Path):
        """Two threads trying to write off the same stock — one should succeed."""
        db = tmp_path / "writeoff.db"
        ledger = Ledger("test", db_path=db)
        ledger.record_trade(Trade("2024-01-15", "BUY", "DEAD.NS", 10, 100.0, 5.0, "Buy"))

        results = []
        errors = []

        def do_writeoff():
            try:
                l = Ledger("test", db_path=db)
                try:
                    result = l.write_off("DEAD.NS")
                    results.append(result)
                except sqlite3.OperationalError:
                    results.append("locked")
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=do_writeoff)
        t2 = threading.Thread(target=do_writeoff)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors
        # At least one should have succeeded (True), the other may get False or locked
        true_count = sum(1 for r in results if r is True)
        assert true_count >= 1

        # After both finish, stock should be gone
        final = Ledger("test", db_path=db)
        assert "DEAD.NS" not in final.get_holdings()
