#!/bin/bash
# Earnings alert: checks if any portfolio stock has earnings tomorrow
# Runs once per day (after 6 PM on weekdays)
# Warns user to avoid trading stocks with imminent earnings

PROJECT="/Users/fi-fundsindia/Desktop/FundsIndia/Projects/diamond_stock_engine"
MARKER="$PROJECT/data/.earnings_alert_marker"

cd "$PROJECT" || exit 0

# Only on weekdays
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    exit 0
fi

# Only after 6 PM
HOUR=$(date +%H)
if [ "$HOUR" -lt 18 ]; then
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

mkdir -p data
echo "$TODAY" > "$MARKER"

# Hint for Claude to check earnings via MCP tool
OUTPUT="EARNINGS_CHECK: End of day. Check if any portfolio stocks have earnings results tomorrow using the earnings_calendar MCP tool. Warn user if any do.\n"
printf "$OUTPUT"

exit 0
