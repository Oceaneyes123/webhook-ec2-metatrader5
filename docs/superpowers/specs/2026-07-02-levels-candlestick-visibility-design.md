# `/levels` Candle-First Chart Design

## Goal

Make the `/levels Gold` Telegram image a readable MT5 candlestick chart with
key levels overlaid without allowing distant levels to compress the candles.

## Market Data Ownership

`Webhook1.mq5` remains the only EA responsible for chart and market-analysis
data. Its `ChartHistoryBars` input defaults to 200 for every configured
timeframe. `MarketSnapshot.mqh` owns the candle-history JSON builder.

`BuildCandlesJson()` reads only closed MT5 candles using `iTime`, `iOpen`,
`iHigh`, `iLow`, and `iClose`. It iterates from shift 200 down to shift 1,
skips invalid candles, and emits chronological objects using `time`, `open`,
`high`, `low`, and `close`. Every `TIMEFRAME_SNAPSHOT` retains its top-level
OHLC fields and includes `"source":"webhook1"` plus the `candles` array.

`Webhook2.mq5` remains trade-management-only. It receives only a short comment
documenting that it does not send chart/history data.

## Python Snapshot Handling

`validate_snapshot()` keeps `source` optional for backward compatibility.
When `candles` is provided, it must be a list whose entries contain `time` or
`candle_time` and finite numeric OHLC values. Each entry is normalized to:

```python
{
    "candle_time": "...",
    "open": float,
    "high": float,
    "low": float,
    "close": float,
}
```

Valid supplied history is stored in its existing chronological order as
`snapshot["candle_history"]`. When `candles` is absent, the existing behavior
continues accumulating one top-level closed candle per snapshot. History is
retained up to 200 candles.

## Chart Selection

`MarketState._chart_candles()` selects available history in this order:

1. M15
2. M30
3. H1
4. H4
5. M1
6. M5

It returns the selected chronological history and timeframe, capped at the
latest 200 entries.

## Candle-First Rendering

`MarketState.levels_chart()` derives its y-axis only from the selected candle
highs and lows:

```python
visible_low = min(candle["low"] for candle in candles)
visible_high = max(candle["high"] for candle in candles)
padding = max(
    (visible_high - visible_low) * 0.15,
    candles[-1]["close"] * 0.001,
    1,
)
```

The plot range is the visible candle range plus this padding. Key levels never
expand it.

FVG zones that intersect the plot range are clipped to the plot bounds and
drawn first with light muted fills. In-range support, resistance, fib, PDH,
and PDL lines are drawn next. Candle wicks, bodies, and contrasting outlines
are drawn last. This guarantees that candle colors remain visible.

Fully out-of-range levels are omitted from the plot and retained in the
right-side label rail with `above chart` or `below chart`. Partially
intersecting FVG zones are clipped rather than expanding the scale.

The chart subtitle shows the selected timeframe, latest history close, and
latest history timestamp. The first, middle, and latest candle timestamps are
shown along the x-axis. Candle width is calculated from the available plot
width so up to 200 bars remain distinguishable.

## Telegram Behavior

Python remains the only Telegram sender. `/levels Gold` continues sending a
PNG. Existing short-caption and follow-up-report behavior remains unchanged,
as do bot token and chat ID handling.

## Verification

`test_webhook.py` covers:

- snapshots with `"source":"webhook1"` and snapshots without `source`;
- supplied history using either `time` or `candle_time`;
- fallback accumulation when `candles` is absent;
- M15 preference over M30, H1, and H4;
- retention and rendering of up to 200 candles;
- candle-derived y-axis behavior with distant FVG and point levels;
- distant `above chart` and `below chart` labels;
- bullish and bearish candle-colored pixels after rendering; and
- unchanged Telegram photo delivery.

After Python tests pass, compile both canonical EAs, run `python sync_mq5.py`,
compile or reload both live EAs, and compare all canonical/live MQL5 files.
No commit or push is part of this work.

## Out of Scope

No new charting dependency, separate chart panel, Webhook2 market-data logic,
Telegram configuration change, or unrelated MQL5 refactor is included.
