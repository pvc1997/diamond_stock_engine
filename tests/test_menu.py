"""Tests for the interactive menu tree."""

from __future__ import annotations

import pytest

from diamond.menu import MenuItem, build_menu_tree, _format_entry


class TestMenuItem:
    def test_leaf_node(self):
        item = MenuItem(label="Test", command="diamond status")
        assert item.is_leaf is True

    def test_branch_node(self):
        item = MenuItem(
            label="Parent",
            children=[MenuItem(label="Child", command="diamond status")],
        )
        assert item.is_leaf is False

    def test_leaf_with_children_is_not_leaf(self):
        item = MenuItem(
            label="Mixed",
            command="diamond status",
            children=[MenuItem(label="Child", command="x")],
        )
        assert item.is_leaf is False


class TestBuildMenuTree:
    def test_root_has_children(self):
        tree = build_menu_tree()
        assert len(tree.children) > 0

    def test_all_branches_populated(self):
        tree = build_menu_tree()
        for child in tree.children:
            assert child.label
            # Each top-level should have children (it's a category)
            assert len(child.children) > 0, f"{child.label} has no children"

    def test_leaf_nodes_have_commands(self):
        """Every leaf node must have a command."""
        tree = build_menu_tree()
        _check_leaves(tree)

    def test_no_empty_labels(self):
        """No menu item should have an empty label."""
        tree = build_menu_tree()
        _check_labels(tree)

    def test_categories_present(self):
        tree = build_menu_tree()
        labels = [c.label for c in tree.children]
        expected = ["Daily", "Portfolio", "Accumulate", "Run Strategy",
                     "Paper Trading", "Analysis", "Scenarios", "Backtest",
                     "Reports", "Watchlist", "Broker (Kite)"]
        for cat in expected:
            assert cat in labels, f"Missing category: {cat}"

    def test_total_leaf_count(self):
        """Should have a good number of actionable commands."""
        tree = build_menu_tree()
        count = _count_leaves(tree)
        assert count >= 50, f"Expected >= 50 leaf commands, got {count}"


class TestFormatEntry:
    def test_leaf_format(self):
        item = MenuItem(label="Status", description="Show status", command="diamond status")
        result = _format_entry(item)
        assert "Status" in result
        assert "Show status" in result

    def test_branch_format_has_arrow(self):
        item = MenuItem(label="Portfolio", children=[MenuItem(label="X", command="y")])
        result = _format_entry(item)
        assert ">" in result

    def test_no_description(self):
        item = MenuItem(label="Simple", command="diamond x")
        result = _format_entry(item)
        assert result == "Simple"


# --- Helpers ---

def _check_leaves(node: MenuItem) -> None:
    if node.is_leaf:
        assert node.command, f"Leaf '{node.label}' has no command"
        assert "diamond" in node.command, f"Leaf '{node.label}' command doesn't start with diamond: {node.command}"
    for child in node.children:
        _check_leaves(child)


def _check_labels(node: MenuItem) -> None:
    assert node.label, "Found MenuItem with empty label"
    for child in node.children:
        _check_labels(child)


def _count_leaves(node: MenuItem) -> int:
    if node.is_leaf:
        return 1
    return sum(_count_leaves(c) for c in node.children)
