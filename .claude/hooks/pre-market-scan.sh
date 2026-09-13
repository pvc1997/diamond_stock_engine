#!/bin/bash
# Pre-market scan: runs once per morning (after 8:45 AM on weekdays)
# Fetches overnight global cues and market prep data
# Silent if already ran today or outside market prep window

PROJECT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MARKER="$PROJECT/data/.premarket_marker"

cd "$PROJECT" || exit 0

# Only on weekdays (1=Mon to 5=Fri)
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    exit 0
fi

# Only between 8:45 AM and 9:30 AM (pre-market window)
HOUR=$(date +%H)
MIN=$(date +%M)
TIME_MIN=$((HOUR * 60 + MIN))
if [ "$TIME_MIN" -lt 525 ] || [ "$TIME_MIN" -gt 570 ]; then
    exit 0
fi

# Only run once per day
TODAY=$(date +%Y-%m-%d)
if [ -f "$MARKER" ]; then
    MARKER_DATE=$(cat "$MARKER" 2>/dev/null || echo "")
    if [ "$MARKER_DATE" = "$TODAY" ]; then
        exit 0
    fi
fi

# Touch marker for today
mkdir -p data
echo "$TODAY" > "$MARKER"

OUTPUT=""

# Get market pulse for pre-market context
PULSE=$(uv run diamond pulse 2>/dev/null | head -10 || echo "")
if [ -n "$PULSE" ]; then
    OUTPUT="${OUTPUT}PRE_MARKET_SCAN: Market opens soon. Here's the pre-market context:\n${PULSE}\n"
fi

# Check for any critical alerts before market opens
ALERTS=$(uv run diamond alerts gods_plan 2>/dev/null || echo "")
CRIT_COUNT=$(echo "$ALERTS" | grep -c "\[CRITICAL\]")
if [ "$CRIT_COUNT" -gt 0 ]; then
    OUTPUT="${OUTPUT}MORNING_ALERTS: $CRIT_COUNT critical alert(s) need attention before market opens.\n"
fi

if [ -n "$OUTPUT" ]; then
    printf "$OUTPUT"
fi

exit 0
