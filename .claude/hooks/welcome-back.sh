#!/bin/bash
# Welcome-back hook: runs ONCE per session (checks timestamp file)
# Detects absence, overdue rebalance, and critical alerts
# Outputs hints for Claude to act on. Silent if nothing to report.

PROJECT="/Users/fi-fundsindia/Desktop/FundsIndia/Projects/diamond_stock_engine"
MARKER="$PROJECT/data/.session_marker"

cd "$PROJECT" || exit 0

# Only run once per session (marker less than 2 hours old = skip)
if [ -f "$MARKER" ]; then
    MARKER_AGE=$(( $(date +%s) - $(stat -f %m "$MARKER" 2>/dev/null || echo 0) ))
    if [ "$MARKER_AGE" -lt 7200 ]; then
        exit 0
    fi
fi

# Touch marker for this session
mkdir -p data
touch "$MARKER"

OUTPUT=""

# Check 1: Welcome back detection (gap in streak)
STREAK=$(uv run diamond streak 2>/dev/null | head -5 || echo "")
if echo "$STREAK" | grep -qi "0 day\|welcome back\|streak: 0"; then
    OUTPUT="${OUTPUT}WELCOME_BACK: User appears to have been away. Suggest a catch-up briefing with market changes and portfolio alerts.\n"
fi

# Check 2: Critical alerts
ALERTS=$(uv run diamond alerts gods_plan 2>/dev/null || echo "")
CRIT_COUNT=$(echo "$ALERTS" | grep -c "\[CRITICAL\]" || echo "0")
if [ "$CRIT_COUNT" -gt 0 ]; then
    OUTPUT="${OUTPUT}CRITICAL_ALERTS: $CRIT_COUNT critical alert(s) found. Surface these to the user.\n"
fi

# Check 3: Rebalance overdue (check last rebalance date)
STATUS=$(uv run diamond status 2>/dev/null || echo "")
if echo "$STATUS" | grep -qi "overdue\|never rebalanced\|rebalance.*[1-9][0-9][0-9].*days"; then
    OUTPUT="${OUTPUT}REBALANCE_NUDGE: Portfolio rebalance may be overdue. Suggest checking drift.\n"
fi

# Only output if there's something to report
if [ -n "$OUTPUT" ]; then
    printf "$OUTPUT"
fi

exit 0
