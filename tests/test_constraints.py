"""Tests for sector constraint enforcement."""

from __future__ import annotations

from unittest.mock import patch

from diamond.strategies.constraints import apply_sector_cap, cap_sector_weights


class TestApplySectorCap:
    def test_caps_at_limit(self):
        # 5 tickers, all same sector, max 2 per sector
        tickers = ["A.NS", "B.NS", "C.NS", "D.NS", "E.NS"]
        with patch("diamond.strategies.constraints.get_sector", return_value="Tech"):
            result = apply_sector_cap(tickers, max_per_sector=2)
        assert len(result) == 2
        assert result == ["A.NS", "B.NS"]

    def test_preserves_order(self):
        tickers = ["BEST.NS", "GOOD.NS", "OK.NS"]
        with patch("diamond.strategies.constraints.get_sector", return_value="Finance"):
            result = apply_sector_cap(tickers, max_per_sector=10)
        assert result == tickers

    def test_mixed_sectors_pass_through(self):
        tickers = ["A.NS", "B.NS", "C.NS", "D.NS"]
        sectors = {"A.NS": "Tech", "B.NS": "Finance", "C.NS": "Tech", "D.NS": "Health"}
        with patch("diamond.strategies.constraints.get_sector", side_effect=lambda t: sectors[t]):
            result = apply_sector_cap(tickers, max_per_sector=1)
        assert len(result) == 3  # One from each sector

    def test_empty_list(self):
        assert apply_sector_cap([], max_per_sector=4) == []


class TestCapSectorWeights:
    def test_no_change_when_within_limits(self):
        weights = {"A.NS": 0.5, "B.NS": 0.5}
        sectors = {"A.NS": "Tech", "B.NS": "Finance"}
        with patch("diamond.strategies.constraints.get_sector", side_effect=lambda t: sectors[t]):
            result = cap_sector_weights(weights, max_sector_pct=0.60)
        assert abs(sum(result.values()) - 1.0) < 0.001
        assert abs(result["A.NS"] - 0.5) < 0.01

    def test_caps_overweight_sector(self):
        weights = {"A.NS": 0.4, "B.NS": 0.3, "C.NS": 0.3}
        # A and B are both Tech = 70%, C is Finance = 30%
        sectors = {"A.NS": "Tech", "B.NS": "Tech", "C.NS": "Finance"}
        with patch("diamond.strategies.constraints.get_sector", side_effect=lambda t: sectors[t]):
            result = cap_sector_weights(weights, max_sector_pct=0.50)

        # Tech sector should be scaled down
        tech_total = result["A.NS"] + result["B.NS"]
        assert tech_total <= 0.51  # Small tolerance
        assert abs(sum(result.values()) - 1.0) < 0.001

    def test_sums_to_one(self):
        weights = {"A.NS": 0.6, "B.NS": 0.2, "C.NS": 0.2}
        with patch("diamond.strategies.constraints.get_sector", return_value="Same"):
            result = cap_sector_weights(weights, max_sector_pct=0.25)
        assert abs(sum(result.values()) - 1.0) < 0.001
