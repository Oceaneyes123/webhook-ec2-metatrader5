# Local MT5 Webhook to Telegram

This project runs a Python webhook on the same Windows machine as MetaTrader 5.
The EA posts market snapshots to `127.0.0.1:8000`, and Python sends alerts and
command reports through Telegram.

```text
MT5 EA -> http://127.0.0.1:8000/webhook -> Python -> Telegram
Telegram polling -> Python -> /status, /summary, /levels, and other commands
```

## Requirements

- Python 3
- MetaTrader 5 on the same machine
- A Telegram bot token and chat ID

No Python package installation is required.

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
Set-Location D:\Project\Python\webhook-ec2

$env:TELEGRAM_BOT_TOKEN = "your_bot_token"
$env:TELEGRAM_CHAT_ID = "your_chat_id"
$env:TIMEZONE_OFFSET_HOURS = "5"

python webhook.py
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
$env:STATE_FILE = "D:\Project\Python\webhook-ec2\market_state.json"
$env:TRADE_STATE_FILE = "D:\Project\Python\webhook-ec2\trade_state.json"
$env:TELEGRAM_POLL_SECONDS = "10"
```

PowerShell variables apply only to the current terminal. Start `webhook.py`
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

`mq5/BigMove.mq5` alerts after a closed M15 candle has a high-to-low range of
at least 25% of the current D1 ATR(14). Attach it to each symbol chart to
monitor; it sends through the same webhook and Telegram bot.

All EAs use the same `WebhookUrl`, Python webhook server, Telegram bot, and
Telegram chat.

Shared tracked code is under `mq5/includes/`. Root `Webhook1.mq5` and
`Webhook2.mq5` are symlinks to the live MetaTrader Experts files.

After every MQ5 edit:

```powershell
python -m webhook.sync_mq5
```

This updates the live EAs and their shared includes. Then compile and reload
the changed EAs in MetaEditor.

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
6. Attach `BigMove` to each symbol chart that should receive M15 big-move
   alerts.

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

### EA Heartbeat

Both EAs send periodic heartbeats to the webhook server. The `/status` command
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
```

EAs report heartbeat by default every 30 seconds. The server considers a
heartbeat stale after 90 seconds (configurable via
`EA_HEARTBEAT_STALE_SECONDS` environment variable).

**New EA inputs:**

| EA | Input | Default | Description |
|---|---|---|---|
| Webhook1 | `HeartbeatSeconds` | 30 | Timer interval for sending heartbeats (min 10) |
| Webhook2 | `HeartbeatSeconds` | 30 | Minimum seconds between heartbeats (>= TradeManageIntervalSeconds, >= 10) |

The TPSL EA is external but can report heartbeats by sending:

```json
{
  "event_type": "EA_HEARTBEAT",
  "source": "tpsl",
  "symbol": "GOLDmicro",
  "status": "running"
}
```

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
/rsi Gold - Show RSI(14) status and 70/30 extreme lookback
/buy - Start trailing buy-limit mode
/sell - Start trailing sell-limit mode
/notrade - Stop trading activity
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
rsi - Show RSI(14) status and 70/30 extreme lookback
buy - Start trailing buy-limit mode
sell - Start trailing sell-limit mode
notrade - Stop trading activity
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

Run all tests:

```powershell
python -m unittest
```

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
