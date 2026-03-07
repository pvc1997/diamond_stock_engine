#!/bin/bash
# Stop-loss check: runs during market hours (9:15 AM - 3:30 PM weekdays)
# Checks if any portfolio stock has breached stop-loss levels
# Only runs once per hour to avoid spam

PROJECT="/Users/fi-fundsindia/Desktop/FundsIndia/Projects/diamond_stock_engine"
MARKER="$PROJECT/data/.stoploss_check_marker"

cd "$PROJECT" || exit 0

# Only on weekdays
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    exit 0
fi

# Only during market hours (9:15 AM - 3:30 PM)
HOUR=$(date +%H)
MIN=$(date +%M)
TIME_MIN=$((HOUR * 60 + MIN))
if [ "$TIME_MIN" -lt 555 ] || [ "$TIME_MIN" -gt 930 ]; then
    exit 0
fi

# Only run once per hour
CURRENT_HOUR=$(date +%Y-%m-%d-%H)
if [ -f "$MARKER" ]; then
    MARKER_HOUR=$(cat "$MARKER" 2>/dev/null || echo "")
    if [ "$MARKER_HOUR" = "$CURRENT_HOUR" ]; then
        exit 0
    fi
fi

mkdir -p data
echo "$CURRENT_HOUR" > "$MARKER"

# Check for stop-loss alerts
ALERTS=$(uv run diamond alerts gods_plan 2>/dev/null || echo "")
STOPLOSS_COUNT=$(echo "$ALERTS" | grep -ci "stop.loss\|drawdown.*CRITICAL" || echo "0")

if [ "$STOPLOSS_COUNT" -gt 0 ]; then
    OUTPUT="STOP_LOSS_ALERT: $STOPLOSS_COUNT stop-loss or critical drawdown alert(s) detected during market hours. Surface these immediately to the user with recommended actions.\n"
    printf "$OUTPUT"
fi

exit 0
