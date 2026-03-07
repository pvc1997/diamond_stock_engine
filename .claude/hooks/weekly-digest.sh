#!/bin/bash
# Weekly digest: runs on first message on Monday
# Suggests a weekly review if not already done

PROJECT="/Users/fi-fundsindia/Desktop/FundsIndia/Projects/diamond_stock_engine"
MARKER="$PROJECT/data/.weekly_digest_marker"

cd "$PROJECT" || exit 0

# Only on Monday (1)
DOW=$(date +%u)
if [ "$DOW" -ne 1 ]; then
    exit 0
fi

# Only run once per week
WEEK=$(date +%Y-W%V)
if [ -f "$MARKER" ]; then
    MARKER_WEEK=$(cat "$MARKER" 2>/dev/null || echo "")
    if [ "$MARKER_WEEK" = "$WEEK" ]; then
        exit 0
    fi
fi

mkdir -p data
echo "$WEEK" > "$MARKER"

OUTPUT="WEEKLY_DIGEST: It's Monday! Last week's portfolio review hasn't been shown yet. Suggest running /weekly for a comprehensive check-in, or give a quick 3-line summary: NAV change, biggest mover, and any pending actions.\n"
printf "$OUTPUT"

exit 0
