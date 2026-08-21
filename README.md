# Local MT5 Webhook to Telegram

This project runs a Python webhook on the same Windows machine as MetaTrader 5.
The EA posts market snapshots to `127.0.0.1:8000`, and Python sends alerts and
command reports through Telegram.

```text
MT5 EA -> http://127.0.0.1:8000/webhook -> Python -> Telegram
Telegram polling -> Python -> /status, /summary, /levels, and other commands
```

## Requirements

- Python 3.11 or newer
- MetaTrader 5 on the same machine
- A Telegram bot token and chat ID

Install the runtime dependency before starting the service:

```powershell
python -m pip install -r requirements.txt
```

## Telegram Credentials

1. Create a bot with Telegram's `@BotFather` and copy its token.
2. Send any message to the new bot.
3. Before starting this server, open:

   ```text
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```

4. Find `message.chat.id` in the response and use it as the chat ID.

## Start the Local Server

Open PowerShell in the repository:

```powershell
Set-Location C:\Project\Personal\webhook-ec2

$env:TELEGRAM_BOT_TOKEN = "your_bot_token"
$env:TELEGRAM_CHAT_ID = "your_chat_id"
$env:TIMEZONE_OFFSET_HOURS = "5"

python run.py
```

The default configuration is:

```text
Host: 127.0.0.1
Port: 8000
Webhook: http://127.0.0.1:8000/webhook
Health: http://127.0.0.1:8000/health
```

Optional environment overrides:

```powershell
$env:HOST = "127.0.0.1"
$env:PORT = "8000"
$env:PUBLIC_URL = "http://127.0.0.1:8000/webhook"
$env:TRADE_STATE_FILE = "C:\Project\Personal\webhook-ec2\trade_state.json"
$env:TELEGRAM_POLL_SECONDS = "10"
$env:ACCOUNT_DB_FILE = "C:\Project\Personal\webhook-ec2\account_state.db"
$env:ACCOUNT_ACTIONS_ENABLED = "false" # set true only after demo testing
$env:ACCOUNT_ACTION_SECRET = "long-random-local-secret"
$env:AUTHORIZED_TELEGRAM_CHAT = "your_chat_id"
$env:AUTHORIZED_TELEGRAM_USER = "" # optional Telegram user ID
$env:PRICE_DATA_STALE_SECONDS = "120"
$env:PROFIT_ALERT_PIPS = "50"
$env:BREAKEVEN_ELIGIBILITY_PIPS = "30"
$env:BREAKEVEN_PROTECTED_PIPS = "10"
$env:CONFIRMATION_EXPIRY_SECONDS = "120"
$env:ACCOUNT_ACTION_LEASE_SECONDS = "60"
$env:GOLD_PIP_SIZE = "0.1"
$env:REPORT_RECOVERY_DAYS = "7"
$env:EVENT_DELAY_SECONDS = "60"
# Optional DST-aware session overrides: Name|IANA zone|start|end, comma-separated
$env:REPORT_SESSIONS = "Asian|Asia/Tokyo|09:00|18:00,London|Europe/London|08:00|17:00,New York|America/New_York|08:00|17:00"
$env:SESSION_LONDON_ENABLED = "true"
# Optional selective closed-candle thresholds
$env:MARKET_STRICTNESS = "balanced" # conservative, balanced, aggressive
$env:STRUCTURE_SWING_BARS_M30 = "2"
$env:STRUCTURE_SWING_BARS_H1 = "2"
$env:STRUCTURE_SWING_BARS_H4 = "2"
$env:STRUCTURE_SWING_BARS_D1 = "2"
$env:STRUCTURE_MIN_PROMINENCE_ATR = "0.35"
$env:STRUCTURE_BREAK_ATR_BUFFER = "0.12"
$env:STRUCTURE_MIN_BODY_RATIO = "0.5"
$env:STRUCTURE_MIN_CLOSE_LOCATION = "0.65"
$env:LEVEL_REJECTION_WICK_RATIO = "1.2"
$env:LEVEL_REJECTION_MIN_BODY_RATIO = "0.25"
$env:LEVEL_SWEEP_PENETRATION_ATR = "0.15"
$env:LEVEL_SWEEP_MIN_BODY_RATIO = "0.35"
$env:LEVEL_REARM_DISTANCE_ATR = "0.5"
$env:LEVEL_COOLDOWN_MULTIPLIER = "5" # source timeframe minutes × multiplier
$env:LEVEL_STALE_UPDATES = "20"
$env:LEVEL_COINCIDENCE_ATR = "0.25"
$env:LEVEL_MIN_STRENGTH = "0.75"
$env:LEVEL_RETENTION = "200"
$env:LEVEL_ENABLED_TYPES = "" # empty enables all supported types
$env:LEVEL_ENABLED_EVENTS = "" # empty enables all supported events
$env:MARKET_DEBUG_LOGGING = "false"
```

PowerShell variables apply only to the current terminal. Start `run.py`
from that same terminal.

Verify the server:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Expected output includes:

```text
✅ Webhook healthy
Telegram: configured
Alerts: running
```

## MT5 EA Setup

`mq5/Webhook1.mq5` is the market-data EA. Attach it to the symbol chart to
send snapshots, candle history, RSI/EMA values, patterns, and key levels. It
powers `/summary`, `/levels`, and `/rsi`.

`mq5/Webhook2.mq5` is the trade-management EA. Attach it to the same symbol
chart only when trade management is desired. It fetches
`/trade-config?symbol=<symbol>` and can create, modify, and delete pending
orders.

`mq5/BigMove.mq5` alerts after a closed M15, M30, H1, H2, or H4 candle reaches
its strong-candle average (16%, 22%, 32.5%, 42.5%, or 60%) of the current D1
ATR(14). Attach it to each symbol chart to monitor; it sends through the same
webhook and Telegram bot.

All EAs use the same `WebhookUrl`, Python webhook server, Telegram bot, and
Telegram chat.
`TPSL.mq5` is the TP/SL and breakeven manager; attach it to the same chart as
Webhook2 when its positions need exit protection.

### Structure and key-level alerts

Only confirmed external swings on closed M30, H1, H4, and D1 candles can
produce BOS or CHoCH. A BOS continues an established trend; a CHoCH breaks its
protected swing and moves the structure to ranging until a new sequence forms.
Support, resistance, Fibonacci, FVG, and previous-day levels remain separate
key-level objects and can produce breaks, rejections, sweeps, reclaims, and
retests, but they cannot change market structure. Key-level alerts use the
source timeframe and level type in their persisted identity, group coincident
levels, and require ATR-relative candle confirmation. M5 and M15 remain
available to `/levels` but do not send break/rejection alerts. Repeatable
touch/rejection/sweep alerts require both meaningful separation and the
persisted source-timeframe ×5 cooldown; distinct break, retest, and reclaim
transitions remain eligible immediately so the lifecycle can progress.
Present levels do not age toward expiry. Objects absent from source snapshots
are retired after `LEVEL_STALE_UPDATES`, and bounded retention prunes their
alert state too.

Canonical tracked sources are under `mq5/`; shared code is under
`mq5/includes/`. Root `Webhook1.mq5` and `Webhook2.mq5` are live MetaTrader
links or checkout pointer files and must never be edited directly. Live include
files are synchronized copies and must not be edited directly either.

After every MQ5 edit:

```powershell
python sync_mq5.py
```

This updates `Webhook1.mq5`, `Webhook2.mq5`, `BigMove.mq5`, `EMA.mq5`,
`TPSL.mq5`, `Overtrade.mq5`, and their shared includes in the live Experts
folder. Then compile and reload the changed EAs in MetaEditor.

Verify synchronization without copying:

```powershell
python sync_mq5.py --check
```

In MetaTrader 5:

1. Open **Tools > Options > Expert Advisors**.
2. Enable **Allow WebRequest for listed URL**.
3. Add:

   ```text
   http://127.0.0.1:8000
   ```

4. Attach `Webhook1` to the required symbol chart.
5. Attach `Webhook2` to the same chart only if trade management is required,
   then enable algorithmic trading.
6. Attach `BigMove` to each symbol chart that should receive M15–H4 big-move
   alerts.
7. Attach `TPSL` to the Webhook2 chart when TP/SL and breakeven management is
   required.

The EA's default URL is:

```text
WebhookUrl = http://127.0.0.1:8000/webhook
```

Other useful EA inputs:

```text
WebRequestTimeoutMs = 5000
PrintDebugLogs = true
TradeManageIntervalSeconds = 1
TradeMagicNumber = 260628
EaIssueRepeatSeconds = 60
LevelLookbackBars = 100
SwingStrength = 2
AtrPeriod = 14
MinFvgAtrRatio = 0.25
```

`TradeManageIntervalSeconds` controls how often `Webhook2` runs trade
management through `OnTimer`.

### Account-wide trade monitoring and safety

Webhook2 uses `OnTradeTransaction()` for account-wide trade activity, including
manual trades, other EAs, hedging positions, netting positions, pending orders,
partial closes, SL/TP changes, and broker rejections. Each event carries account,
position, order, deal, magic, price, P&L, reason, and an idempotency key. The
timer remains only for trade management, heartbeat, confirmed actions, and a
60-second account-position reconciliation backup.

The Python service stores transaction ids, open-position snapshots, entry
decisions, confirmation tokens, queued actions, and sent reports in SQLite
(`ACCOUNT_DB_FILE`, default `account_state.db`), so duplicate webhooks and
restarts do not repeat acknowledged alerts. Delivery is leased until Telegram
accepts it, so an HTTP/Telegram failure can be retried without losing the event.
Telegram offers no idempotency key: a crash after Telegram accepts a request but
before SQLite records it can produce one duplicate alert on retry. Queued actions
are leased, while Webhook2 records each accepted request ID in a terminal global
variable before execution and only considers the confirmed ticket list. This is
at-most-once execution (a lost result may require manual reconciliation), not a
claim of exactly-once result delivery. Keep the SQLite database and MT5 terminal
data when restarting the service.

Account-wide Telegram actions are disabled by default. To enable them, set
`ACCOUNT_ACTIONS_ENABLED=true` and configure `AUTHORIZED_TELEGRAM_CHAT`
(and optionally `AUTHORIZED_TELEGRAM_USER`) plus a unique `ACCOUNT_ACTION_SECRET`
matching Webhook2's `AccountActionSecret` input. Buttons require a short-lived
confirmation, revalidate positions in MT5, and report actual MT5 result codes.
`Move SL to BE` targets the confirmed positions above 30 pips and protects about 10 pips;
`Close Profitable Positions` targets all positions with positive floating P&L.
Both can affect manual and other-EA positions on the whole account. Test only
on a demo account before enabling them.

Daily reports are sent at `DAILY_REPORT_HOUR` (default `6`) in
`PHILIPPINE_TIMEZONE` (default `Asia/Manila`) and cover the preceding 24 hours.
Session reports follow Tokyo, London, and New York local session clocks, so London
and New York delivery shifts automatically with daylight saving time. Set
`DAILY_REPORT_ENABLED=false`, `SESSION_REPORTS_ENABLED=false`, or an individual
`SESSION_<NAME>_ENABLED=false` to disable them. `REPORT_RECOVERY_DAYS` controls
how many missed windows are recovered after downtime.
Recovery sends older daily/session windows only when the local SQLite history has
an event or account snapshot in that window; recovered data is labelled delayed.
Session windows use each configured session's local start and end (including DST),
not a 24-hour fallback. Trade timestamps carry MT5's server-to-UTC offset; old
offset-less broker timestamps are retained at receive time rather than guessed as
Philippine time.

### EA Heartbeat

All four EAs send periodic heartbeats to the webhook server. The `/status` command
shows whether EAs are running, stale, or missing:

```text
✅ Bot online
Alerts: running
Telegram: configured
Recent signals: 3
Default trade mode: NOTRADE

EA status:
Webhook1: running, GOLD, 12s ago
Webhook2: running, GOLD, 5s ago
TPSL: missing
Overtrade: running, GOLD, 8s ago
```

EAs report heartbeat by default every 30 seconds. The server considers a
heartbeat stale after 90 seconds (configurable via
`EA_HEARTBEAT_STALE_SECONDS` environment variable).

**New EA inputs:**

| EA | Input | Default | Description |
|---|---|---|---|
| Webhook1 | `HeartbeatSeconds` | 30 | Timer interval for sending heartbeats (min 10) |
| Webhook2 | `HeartbeatSeconds` | 30 | Minimum seconds between heartbeats (>= TradeManageIntervalSeconds, >= 10) |
| TPSL | `HeartbeatSeconds` | 30 | Minimum seconds between heartbeats (min 10) |
| Overtrade | `HeartbeatSeconds` | 30 | Minimum seconds between heartbeats (min 10) |

TPSL uses its existing `TimerSeconds` input (default 1 second) for TP/SL and
breakeven management; heartbeats are rate-limited separately and do not slow
that timer.

Overtrade uses its existing `CheckIntervalSeconds` input for position monitoring;
heartbeats are rate-limited separately and do not slow that timer.

### Webhook2 Trade Config Cache

`Webhook2` fetches `/trade-config?symbol=<symbol>` from the Python server to
determine trade mode, lot size, and trail pips. To avoid HTTP requests on every
timer tick, the config is cached locally.

**New EA inputs:**

| Input | Default | Description |
|---|---|---|
| `TradeConfigRefreshSeconds` | 5 | Max age of cached config before refreshing (min 1) |
| `TradeConfigMaxStaleSeconds` | 30 | Max age of stale config usable as fallback when HTTP fails (>= RefreshSeconds) |

Behavior:

- If cached config is fresher than `TradeConfigRefreshSeconds`, return cached
  config without an HTTP request.
- On HTTP success, update the cache and return the new config.
- On HTTP failure, use the cached config as fallback if its age is within
  `TradeConfigMaxStaleSeconds`.
- If no valid cache exists and HTTP fails, return false and skip trading.

### Trade Close Notifications

When a trade closes, Webhook2 detects the position departure and sends a
notification to Telegram. The message includes the close reason (TP Hit, SL
Hit, or Manual Close), the P&L, and the current account balance:

```
🔴 Trade Closed
Symbol: GOLD
Reason: 🛑 SL Hit
P&L: -30.50
💰 Balance: 9950.50
```

```
🟢 Trade Closed
Symbol: GOLD
Reason: 🎯 TP Hit
P&L: +45.20
💰 Balance: 10050.20
```

**Detection:** Webhook2 tracks position state on every timer tick. When a position
disappears, it looks up the most recent closed deal in account history to
determine the reason and P&L.

**Reason mapping:**

| MQL5 Constant | Telegram Reason |
|---|---|
| `DEAL_REASON_TP` (14) | 🎯 TP Hit |
| `DEAL_REASON_SL` (15) | 🛑 SL Hit |
| Manual close / other | 👋 Manual Close |

**External EAs** (such as TPSL) can also send trade close notifications by
POSTing to the webhook:

```json
{
  "event_type": "TRADE_CLOSE",
  "source": "tpsl",
  "symbol": "GOLDmicro",
  "reason": "TP_HIT",
  "profit": 45.20,
  "balance": 10050.20
}
```

### Symbol Aliases

Symbol normalization is controlled by a centralized alias map in
`json_data_parser.py`:

```python
SYMBOL_ALIASES = {
    "GOLD": ["GOLD", "Gold", "Goldmicro", "Goldm#", "XAUUSD"],
}
```

To add another broker variant for Gold, update only the `GOLD` list:

```python
"GOLD": ["Goldmicro", "Goldm#", "XAUUSD", "XAUUSD.fx"],
```

The map can also be overridden at startup via the `SYMBOL_ALIASES_JSON`
environment variable:

```powershell
$env:SYMBOL_ALIASES_JSON = '{"GOLD":["Goldmicro","Goldm#","XAUUSD"]}'
```

Alias matching is case-insensitive and whitespace-trimmed. Unknown symbols fall
back to the legacy prefix/suffix cleanup (`micro`, `m#`).

### TP/SL Ownership

Webhook2 is entry-management only. It places and trails pending entries. TP/SL,
breakeven, and exit protection are handled by the separate TPSL EA. Make sure
the TPSL EA is attached, running, and configured to manage Webhook2 trades.

M1 and M5 snapshots use EMA20/EMA50 only. M15, M30, H1, and H4 snapshots
include candle patterns and key levels.

### Context-aware candle patterns

MT5 reports raw patterns from closed candles. Python then checks the available
closed-candle history before sending a normal alert: body/wick geometry, ATR
size, nearby M30-D1 levels, EMA alignment, countertrend risk, and extreme-candle
exhaustion. A raw match alone is not a strong signal. Qualified alerts include
their score, classification, context, nearest level, ATR-relative size, and
pass/warning reasons; the stable pattern ID is symbol, timeframe, event,
direction, and candle close time, so restart does not duplicate the same candle
event. Persisted lifecycle states are `raw_detected`, `awaiting_confirmation`,
`confirmed`, `alerted`, `failed`, `invalidated`, and `expired`.

Defaults can be overridden with `PATTERN_MIN_ALERT_SCORE` (80),
`PATTERN_MIN_BODY_RATIO` (0.10), `PATTERN_MIN_ATR_RATIO` (0.35),
`PATTERN_LEVEL_ATR_TOLERANCE` (0.50), `PATTERN_MIN_WICK_BODY_RATIO` (2.0),
`PATTERN_MIN_WICK_RANGE_RATIO` (0.35), `PATTERN_EXTREME_ATR_RATIO` (2.5),
`PATTERN_INSIDE_BREAKOUT_RATIO` (0.15), `PATTERN_MAX_AGE_CANDLES` (8), and
`PATTERN_RETENTION_CANDLES` (32). Use
`PATTERN_<EVENT_TYPE>_CONFIRMATION_MODE=immediate|follow_through|retest|structure_confirmed` for a
per-pattern override, or `PATTERN_CONFIRMATION_MODE` for the fallback;
engulfing defaults to immediate while rejection/star/inside-bar patterns wait
for follow-through. Countertrend immediate confirmation is disabled by default
and can be explicitly enabled with `PATTERN_COUNTERTREND_IMMEDIATE=true`.
`PATTERN_ENABLED_TYPES` and `PATTERN_ENABLED_TIMEFRAMES` (default
`M30,H1,H4`) control the active pattern set; `PATTERN_ALERT_GROUPING_ENABLED`
groups related same-candle alerts.
`PATTERN_VOLUME_EXPANSION_RATIO`, `PATTERN_LOW_VOLUME_RATIO`,
`PATTERN_SESSION_WINDOWS` (JSON), `PATTERN_SESSION_TIMEZONE`, and
`PATTERN_SESSION_WEIGHT_TOKYO/LONDON/NEW_YORK` control volume/session weighting.
`PATTERN_CANDLE_TIMEZONE` (default `Asia/Manila`) is the source timezone
assumption for naive MT5 candle timestamps; timestamps are converted to
`PATTERN_SESSION_TIMEZONE` before session classification. `PATTERN_SWEEP_MIN_ATR_RATIO`
(default `0.15`) sets material level penetration for sweep/reclaim scoring.
`PATTERN_DAILY_ATR_WARNING_RATIO`, `PATTERN_VWAP_SCORE`,
`PATTERN_SWEEP_SCORE`, `PATTERN_OPPOSING_LEVEL_SCORE`, and their corresponding
`*_SCORE`/tolerance settings control the remaining context factors.
`PATTERN_DEBUG_LOGGING` enables suppressed-pattern diagnostics and
`PATTERN_INVALIDATION_ALERTS` defaults to false. `PATTERN_INVALIDATION_ATR_RATIO`
(default `0.10`) controls the close-through buffer. `PATTERN_REQUIRE_HTF_ALIGNMENT`
(default `true`),
`PATTERN_MISSING_HTF_SCORE`, and `PATTERN_COUNTERTREND_STRICTNESS` explicitly
control higher-timeframe alignment and countertrend scoring. Snapshots with missing history
are informational-only and cannot alert; missing optional context remains safe
and is shown as unknown rather than invented.

> **Risk:** `Webhook2` can place, modify, and delete pending orders. Test on a
> demo account first, confirm the chart symbol, and check Telegram trade mode
> with `/status Gold` before expecting trades.

## Telegram Commands

```text
/status - Check bot status
/pause - Suppress automatic pattern alerts
/resume - Resume automatic pattern alerts
/help - Show available commands
/recent Gold - Show the last five alerts for a symbol
/summary Gold - Show EMA and retained-pattern confluence
/levels Gold - Show M15-H4 support, resistance, Fibonacci, FVG, PDH/PDL, and a key-levels plot image
/rsi Gold - Show RSI(14) status and 75/25 extreme lookback
/price Gold - Latest MetaTrader bid, ask, spread, daily range, and data age
/market Gold - M5 EMA trend and current Asian/London/New York session
/why Gold - Latest concise Webhook2 entry decision
/buy - Start trailing buy-limit mode
/sell - Start trailing sell-limit mode
/notrade - Stop trading activity
/leveltrade on|off - Enable or remove key-level limit orders
/overtrade on - Enable overtrade security
/overtrade off - Disable overtrade security
/overtrade 5 - Close eligible positions at $5 combined profit
/status Gold - Check status and trade mode for Gold
/buy Gold - Start trailing buy-limit mode for Gold
/sell Gold - Start trailing sell-limit mode for Gold
/notrade Gold - Stop trading activity for Gold
```

For BotFather
```text
status - Check bot status
pause - Suppress automatic pattern alerts
resume - Resume automatic pattern alerts
help - Show available commands
recent - Show the last five alerts for a symbol
summary - Show EMA and retained-pattern confluence
levels - Show M15-H4 key levels
rsi - Show RSI(14) status and 75/25 extreme lookback
buy - Start trailing buy-limit mode
sell - Start trailing sell-limit mode
notrade - Stop trading activity
leveltrade - Enable or remove key-level limit orders
overtrade - Enable, disable, or set the overtrade profit target
price - Latest MT5 price
market - M5 EMA trend and session
why - Latest entry decision
status - Check status and trade mode for Gold
buy - Start trailing buy-limit mode for Gold
sell - Start trailing sell-limit mode for Gold
notrade - Stop trading activity for Gold
```

Paused mode still stores incoming snapshots, so `/summary` and `/levels` remain
current.

The default trade mode and symbol overrides persist in `trade_state.json`.
Set `TRADE_STATE_FILE` to store that file elsewhere. The commands `/buy`,
`/sell`, `/notrade`, and `/status` operate on the default mode; their symbol
forms operate on one normalized symbol.

Overtrade security is enabled by default and closes eligible chart-symbol
positions at a combined profit target of `$1.00`. Use `/overtrade on`,
`/overtrade off`, or `/overtrade <amount>` to change its persisted setting.

## Test the Webhook Manually

```powershell
$body = @{
    event_type = "TIMEFRAME_SNAPSHOT"
    symbol = "GOLDmicro"
    timeframe = "M1"
    candle_time = "2026.06.28 12:01:00"
    open = 2300.0
    high = 2310.0
    low = 2290.0
    close = 2305.0
    digits = 2
    notify_patterns = $true
    ema20 = 2306.0
    ema50 = 2305.0
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://127.0.0.1:8000/webhook `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

The response should be `ok`.

## Tests and Logs

## Market structure and key-level alerts

`KEY_LEVEL_BREAK_*`, rejection, sweep, reclaim, and retest are interactions with
support/resistance, Fibonacci, FVG, or previous-day levels. They never change
market structure. BOS/CHoCH are emitted only by the closed-candle external
swing engine: a BOS continues an already-confirmed HH/HL or LH/LL trend; a
CHoCH breaks its protected low/high and then waits for a new structure before
another BOS. The default filters require ATR-relative displacement, a 50% body,
and a close near the breaking end. Weak wick touches remain silent.

Level state is persistent and keyed by symbol, source timeframe, type, and
price/zone. Broken levels move to a broken lifecycle; a reclaim/retest is a
later closed-candle sequence, not a same-candle rejection. Alerts rearm only
after price separates by 0.5 ATR. The engine retains 80 swings per
symbol/timeframe; this is deliberately external-only until internal alerts are
needed.

Run all tests:

```powershell
python -m unittest
```

Formatting and linting commands are documented in
[`docs/development.md`](docs/development.md).

Follow the local log:

```powershell
Get-Content .\webhook.log -Wait
```

Common MT5 errors:

```text
4014 - Add http://127.0.0.1:8000 to the WebRequest allow-list.
5201 - Confirm the Python server is running.
5202 - The local request timed out.
5203 - Check the URL, port, and webhook log.
```

## Optional Future Linux Service

`webhook-ec2.service` is retained as a future systemd deployment artifact and
is not used by the local Windows setup. Its paths and environment file must be
adapted to the target Linux machine before use.
