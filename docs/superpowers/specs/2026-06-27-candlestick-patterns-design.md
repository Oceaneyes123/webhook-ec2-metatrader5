# Candlestick Pattern Support Design

## Goal

Add Shooting Star, Inverted Hammer, Morning Star, Evening Star, and Inside Bar
Breakout alerts to the MT5 EA and Python Telegram report while preserving
existing payload compatibility.

## MT5 Detection

The EA continues scanning M1, M5, M15, M30, H1, and H4 when a new bar opens.
It reads the four most recent closed candles once per timeframe and evaluates
each detector independently so every distinct matching pattern is sent.
`lastBarTimes` remains the per-timeframe duplicate guard.

Code comments use these indices:

- Candle 1: most recent closed confirmation candle.
- Candle 2: previous closed candle.
- Candle 3: third closed candle, or mother candle for Inside Bar.
- Candle 4: additional prior candle used only for trend confirmation.

The EA exposes these inputs:

- `MaxBodyPercent = 35`
- `MinLongWickBodyRatio = 2.0`
- `MaxSmallWickBodyRatio = 1.0`
- `StrongCandleBodyPercent = 50`

All detectors reject candles whose range is not greater than zero. Checks using
body-relative thresholds also reject zero-body candles. Comparisons use
multiplication rather than division to avoid division-by-zero.

Inclusive comparisons are intentional unless stated otherwise.

The new-bar guard should prevent repeated tick alerts, but it must not prevent
multiple distinct patterns from sending on the same closed candle/timeframe.

Shooting Star and Inverted Hammer may share the same wick/body shape. Their
classification is determined by prior-close trend context.

### Shooting Star and Inverted Hammer

Both require candle 1's body to be no more than `MaxBodyPercent` of its range,
its upper wick to be at least `MinLongWickBodyRatio` times its body, and its
lower wick to be no more than `MaxSmallWickBodyRatio` times its body.

- Shooting Star requires `close2 > close3 > close4` and sends SELL.
- Inverted Hammer requires `close2 < close3 < close4` and sends BUY.

### Morning Star and Evening Star

These use candles 3, 2, and 1. Candle 3 must have a body of at least
`StrongCandleBodyPercent` of its range. Candle 2's body must be no more than
`MaxBodyPercent` of candle 3's body.

- Morning Star: candle 3 is bearish, candle 1 is bullish, and candle 1 closes at
  or above candle 3's body midpoint. It sends BUY.
- Evening Star: candle 3 is bullish, candle 1 is bearish, and candle 1 closes at
  or below candle 3's body midpoint. It sends SELL.

### Inside Bar Breakout

Candle 2 must have a high no greater than candle 3's high and a low no less
than candle 3's low. Candle 1 confirms the breakout:

- A close above candle 3's high sends BUY.
- A close below candle 3's low sends SELL.

## Payload and Python Reporting

EA payloads include event type, signal, symbol, timeframe, candle time,
open/high/low/close, and bias. Morning Star and Evening Star use candle 1 as
the payload candle.

Python adds all new event display names and a bias mapping:

- Hammer, Inverted Hammer, and Morning Star infer `Bullish / BUY`.
- Hanging Man, Shooting Star, and Evening Star infer `Bearish / SELL`.
- Engulfing and Inside Bar derive bias from the payload's BUY/SELL signal.

The Telegram message always includes a `Bias:` line. When both high and low are
present, prices use labeled O/H/L/C output. If either is absent, the existing
open-close price output remains unchanged.

## Validation

Python unit tests cover the new supported event types, fixed-bias inference,
dynamic Inside Bar bias, labeled OHLC output, and the legacy open-close
fallback. The existing suite verifies webhook delivery and prior event
behavior. The EA is compile-checked when an MQL5 compiler is available; no new
test framework or dependency is added.

## Scope

No database, webhook endpoint, timeframe configuration, retry behavior, or
unrelated Telegram command behavior changes are included.
