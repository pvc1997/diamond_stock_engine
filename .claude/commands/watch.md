Manage stock watchlist. User input: $ARGUMENTS

Parse the input:
- If empty: `uv run diamond watch` — show current watchlist with alerts
- If "add TICKER PRICE" (e.g., "add RELIANCE 2500"): `uv run diamond watch --add TICKER.NS --target PRICE`
- If "remove TICKER": `uv run diamond watch --remove TICKER.NS`
- If just a ticker name: `uv run diamond watch` then highlight that stock's status

After showing watchlist status, note:
- Which stocks are near alert levels
- Any RSI extremes (oversold <30 or overbought >70)
- Suggest: "Want to deep-dive any of these? Use `/analyze TICKER`"