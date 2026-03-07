"""Personal investment rules — user-defined guardrails for trading decisions."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_RULES_FILE = Path("data/rules.json")

_DEFAULT_RULES = [
    {"text": "Never buy on the day of earnings results", "category": "buy"},
    {"text": "Always check sector exposure before adding a new stock", "category": "buy"},
    {"text": "Hold for at least 1 year unless stop-loss triggers", "category": "sell"},
    {"text": "Maximum 3 stocks per sector", "category": "risk"},
]


def _load_rules() -> list[dict]:
    """Load rules from file, creating defaults if not exists."""
    if not _RULES_FILE.exists():
        _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        rules = []
        for r in _DEFAULT_RULES:
            rules.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "text": r["text"],
                    "category": r["category"],
                    "created_at": datetime.now().isoformat(),
                    "active": True,
                }
            )
        _save_rules(rules)
        return rules
    try:
        return json.loads(_RULES_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_rules(rules: list[dict]) -> None:
    """Save rules to file."""
    _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RULES_FILE.write_text(json.dumps(rules, indent=2))


def get_rules(category: str | None = None) -> list[dict]:
    """List all active rules, optionally filtered by category."""
    rules = _load_rules()
    active = [r for r in rules if r.get("active", True)]
    if category:
        active = [r for r in active if r.get("category") == category]
    return active


def add_rule(text: str, category: str = "general") -> dict:
    """Add a new investment rule."""
    if category not in ("buy", "sell", "risk", "general"):
        category = "general"
    rules = _load_rules()
    rule = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "category": category,
        "created_at": datetime.now().isoformat(),
        "active": True,
    }
    rules.append(rule)
    _save_rules(rules)
    return rule


def remove_rule(rule_id: str) -> bool:
    """Soft-delete a rule by setting active=False."""
    rules = _load_rules()
    for r in rules:
        if r["id"] == rule_id:
            r["active"] = False
            _save_rules(rules)
            return True
    return False


def check_rules(action: str) -> list[dict]:
    """Return active rules matching an action type (buy/sell)."""
    action = action.lower()
    rules = _load_rules()
    matching = []
    for r in rules:
        if not r.get("active", True):
            continue
        cat = r.get("category", "general")
        if cat == action or cat == "general" or cat == "risk":
            matching.append(r)
    return matching
