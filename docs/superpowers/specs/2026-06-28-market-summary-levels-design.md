# Market Summary and Levels Design

## Goal

Restrict candle-pattern analysis to M15–H4, use EMA20/EMA50 as the only
directional signal on M1/M5, and add persistent HTML-formatted Telegram
`/summary <symbol>` and `/levels <symbol>` reports.

## Snapshot Architecture

The MT5 EA sends one `TIMEFRAME_SNAPSHOT` after each closed candle for M1, M5,
M15, M30, H1, and H4.

- M1/M5 snapshots contain `ema20`, `ema50`, and `ema_bias`. Candle-pattern
  detectors do not run on these timeframes. EMA updates change stored state
  without sending automatic Telegram messages.
- M15–H4 snapshots contain every pattern detected on the closed candle and a
  `levels` object calculated from MT5 candle history.
- Common fields identify the symbol, timeframe, and closed-candle time.
  Initialization snapshots disable pattern notifications; normal new-bar
  snapshots enable them.

Python validates each snapshot, stores the latest state by normalized symbol
and timeframe, and sends immediate alerts only for new M15–H4 patterns.
Retries are deduplicated by symbol, timeframe, candle time, and pattern
identity. Existing single-pattern payloads remain accepted during rollout,
but they do not populate EMA or level state.

The latest state is persisted as JSON beside the service. `STATE_FILE` may
override the path. A process lock and temporary-file replacement prevent
concurrent or partial writes.

## Analysis Rules

EMA bias is `BULLISH` when EMA20 is greater than EMA50, `BEARISH` when it is
less, and `NEUTRAL` when equal.

M15–H4 level calculations use these EA inputs:

- `LevelLookbackBars = 100`
- `SwingStrength = 2`
- `AtrPeriod = 14`
- `MinFvgAtrRatio = 0.25`

Support is the nearest confirmed swing low below current price; resistance is
the nearest confirmed swing high above it. A swing requires `SwingStrength`
candles on both sides.

Fibonacci levels use the latest two alternating confirmed pivots and report
38.2%, 50%, and 61.8% retracements for that completed swing leg.

Previous-day high and low come from the last completed D1 candle and are
reported once because they are shared by all report timeframes.

Fair value gaps use a three-candle imbalance. A bullish gap exists when the
newest candle's low is above the oldest candle's high; a bearish gap exists
when the newest candle's high is below the oldest candle's low. Gap width must
be at least `MinFvgAtrRatio * ATR(AtrPeriod)`. The report shows the nearest
active bullish gap below price and bearish gap above price. Partial fills
remain active; a gap is removed after price reaches its far boundary.

## Telegram Behavior

`/summary <symbol>` reports all six timeframes:

- M1/M5 show EMA20, EMA50, and bias.
- M15–H4 show the latest retained pattern set, timestamp, direction, and
  `(invalidated)` status where applicable.

Empty snapshots do not erase retained patterns. A new pattern set on the same
timeframe replaces the previous set. A newer opposing pattern on a higher
timeframe invalidates retained lower-timeframe patterns; invalidated patterns
remain visible until replaced.

The final suggestion is deterministic:

- `BUY` requires bullish M1 and M5 EMA bias, at least one non-invalidated
  bullish M15–H4 pattern, and no non-invalidated bearish pattern.
- `SELL` uses the inverse conditions.
- Every other state returns `WAIT` and identifies missing or conflicting
  confirmation.

`/levels <symbol>` reports M15, M30, H1, and H4 support, resistance, Fibonacci
levels, and nearest qualifying bullish/bearish FVG zones, followed by the
previous-day high/low.

Both commands require a symbol and return a usage message when it is absent.
Missing timeframe data renders as `Awaiting data`; unavailable levels render
as `None found`.

All bot-generated messages use Telegram HTML formatting. Dynamic symbol,
payload, and error text is HTML-escaped before sending. Reports stay within
Telegram's single-message limit; pagination is not included.

While `/pause` is active, snapshots continue updating persisted state but
automatic pattern alerts are suppressed. Commands remain available and
current.

## Validation

Python tests cover snapshot validation, JSON persistence, retry
deduplication, pause behavior, invalidation hierarchy, every confluence
outcome, command usage, missing data, HTML escaping and parse mode, and legacy
payload compatibility.

MT5 checks cover:

- No candle-pattern evaluation on M1/M5.
- EMA20/EMA50 values and neutral equality behavior.
- Pattern and level snapshots only on the intended timeframes.
- Swing, Fibonacci, previous-day, ATR-filtered FVG, partial-fill, and
  full-mitigation behavior.
- Initialization snapshots without stale alerts and normal new-bar snapshots
  with notifications enabled.

Verification runs the Python unit suite and byte-compilation, checks the Git
diff, and compiles the EA with MetaEditor.

## Assumptions

- MT5 remains the source of indicator and level calculations because it
  already has candle history.
- Python standard-library storage is sufficient; no database or dependency is
  added.
- Multiple patterns detected on the same candle are retained and reported as
  one timeframe pattern set.
- Automatic level and EMA messages are not sent; both are available on
  demand through commands.
