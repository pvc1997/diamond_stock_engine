#!/bin/bash
# Post-market log: runs once per afternoon (after 3:30 PM on weekdays)
# Suggests logging the day's P&L and reviewing movers
# Silent unless it's the first message after market close

PROJECT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MARKER="$PROJECT/data/.postmarket_marker"

cd "$PROJECT" || exit 0

# Only on weekdays
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    exit 0
fi

# Only after 3:30 PM
HOUR=$(date +%H)
MIN=$(date +%M)
TIME_MIN=$((HOUR * 60 + MIN))
if [ "$TIME_MIN" -lt 930 ]; then
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

# Touch marker
mkdir -p data
echo "$TODAY" > "$MARKER"

OUTPUT="POST_MARKET_LOG: Market has closed. Suggest running /movers to see today's portfolio impact, and /snapshot to save today's state.\n"
printf "$OUTPUT"
exit 0
