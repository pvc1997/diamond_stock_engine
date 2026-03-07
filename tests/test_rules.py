"""Tests for personal investment rules."""

import json
from pathlib import Path

import pytest

import diamond.data.rules as rules_mod
from diamond.data.rules import add_rule, check_rules, get_rules, remove_rule


@pytest.fixture
def rules_dir(tmp_path, monkeypatch):
    """Redirect rules storage to tmp_path."""
    rules_file = tmp_path / "rules.json"
    monkeypatch.setattr(rules_mod, "_RULES_FILE", rules_file)
    return rules_file


class TestGetRules:
    def test_default_rules_on_first_access(self, rules_dir):
        """First access creates default rules."""
        result = get_rules()
        assert len(result) == 4
        categories = {r["category"] for r in result}
        assert categories == {"buy", "sell", "risk"}

    def test_filter_by_category(self, rules_dir):
        """Filter rules by category."""
        buy_rules = get_rules(category="buy")
        assert len(buy_rules) == 2
        assert all(r["category"] == "buy" for r in buy_rules)

    def test_filter_by_sell(self, rules_dir):
        sell_rules = get_rules(category="sell")
        assert len(sell_rules) == 1
        assert sell_rules[0]["category"] == "sell"

    def test_filter_by_risk(self, rules_dir):
        risk_rules = get_rules(category="risk")
        assert len(risk_rules) == 1
        assert risk_rules[0]["category"] == "risk"

    def test_returns_only_active(self, rules_dir):
        """Inactive rules are excluded."""
        rules = get_rules()
        rule_id = rules[0]["id"]
        remove_rule(rule_id)

        result = get_rules()
        assert len(result) == 3
        assert all(r["id"] != rule_id for r in result)


class TestAddRule:
    def test_add_rule_returns_rule(self, rules_dir):
        """add_rule returns the created rule."""
        rule = add_rule("Always diversify", "buy")
        assert rule["text"] == "Always diversify"
        assert rule["category"] == "buy"
        assert rule["active"] is True
        assert "id" in rule
        assert "created_at" in rule

    def test_add_rule_persists(self, rules_dir):
        """Added rule appears in subsequent get_rules."""
        add_rule("My new rule", "sell")
        result = get_rules(category="sell")
        texts = [r["text"] for r in result]
        assert "My new rule" in texts

    def test_invalid_category_defaults_to_general(self, rules_dir):
        """Invalid category falls back to 'general'."""
        rule = add_rule("Some rule", "invalid_cat")
        assert rule["category"] == "general"

    def test_add_general_category(self, rules_dir):
        """Explicit general category works."""
        rule = add_rule("General principle", "general")
        assert rule["category"] == "general"


class TestRemoveRule:
    def test_remove_sets_inactive(self, rules_dir):
        """remove_rule soft-deletes by setting active=False."""
        rules = get_rules()
        rule_id = rules[0]["id"]
        result = remove_rule(rule_id)
        assert result is True

        # Rule still exists in file but is inactive
        raw = json.loads(rules_dir.read_text())
        found = [r for r in raw if r["id"] == rule_id]
        assert len(found) == 1
        assert found[0]["active"] is False

    def test_remove_nonexistent_returns_false(self, rules_dir):
        """Removing non-existent rule returns False."""
        # Trigger default creation
        get_rules()
        result = remove_rule("nonexistent_id")
        assert result is False


class TestCheckRules:
    def test_check_buy_includes_buy_risk_general(self, rules_dir):
        """check_rules('buy') returns buy + risk + general rules."""
        add_rule("General wisdom", "general")
        result = check_rules("buy")
        categories = {r["category"] for r in result}
        # Should have buy, risk, and general
        assert "buy" in categories
        assert "risk" in categories
        assert "general" in categories
        # sell should NOT be included
        assert "sell" not in categories

    def test_check_sell_includes_sell_risk_general(self, rules_dir):
        """check_rules('sell') returns sell + risk + general rules."""
        add_rule("General wisdom", "general")
        result = check_rules("sell")
        categories = {r["category"] for r in result}
        assert "sell" in categories
        assert "risk" in categories
        assert "general" in categories
        assert "buy" not in categories

    def test_check_excludes_inactive(self, rules_dir):
        """check_rules excludes inactive rules."""
        rules = get_rules()
        buy_rule = [r for r in rules if r["category"] == "buy"][0]
        remove_rule(buy_rule["id"])

        result = check_rules("buy")
        ids = [r["id"] for r in result]
        assert buy_rule["id"] not in ids


class TestPersistence:
    def test_file_persistence_across_reloads(self, rules_dir):
        """Rules survive file reload (simulated by reading raw JSON)."""
        add_rule("Persist me", "sell")
        raw = json.loads(rules_dir.read_text())
        texts = [r["text"] for r in raw]
        assert "Persist me" in texts

    def test_corrupt_file_returns_empty(self, rules_dir):
        """Corrupt JSON file returns empty list."""
        rules_dir.write_text("NOT VALID JSON {{{")
        result = get_rules()
        assert result == []
