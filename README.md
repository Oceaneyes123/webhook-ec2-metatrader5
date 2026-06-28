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

## Install and Configure the MQ5 EA

The tracked source is `mq5/Webhook.mq5`. Root `Webhook.mq5` is a symlink to the
live MetaTrader Experts file.

After every MQ5 edit:

```powershell
python sync_mq5.py
```

Then compile the live `Webhook.mq5` in MetaEditor.

In MetaTrader 5:

1. Open **Tools > Options > Expert Advisors**.
2. Enable **Allow WebRequest for listed URL**.
3. Add:

   ```text
   http://127.0.0.1:8000
   ```

4. Attach the EA to a chart and enable algorithmic trading.

The EA's default URL is:

```text
WebhookUrl = http://127.0.0.1:8000/webhook
```

Other useful EA inputs:

```text
WebRequestTimeoutMs = 5000
PrintDebugLogs = true
LevelLookbackBars = 100
SwingStrength = 2
AtrPeriod = 14
MinFvgAtrRatio = 0.25
```

M1 and M5 snapshots use EMA20/EMA50 only. M15, M30, H1, and H4 snapshots
include candle patterns and key levels.

## Telegram Commands

```text
/status - Check bot status
/pause - Suppress automatic pattern alerts
/resume - Resume automatic pattern alerts
/help - Show available commands
/recent Gold - Show the last five alerts for a symbol
/summary Gold - Show EMA and retained-pattern confluence
/levels Gold - Show M15-H4 support, resistance, Fibonacci, FVG, and PDH/PDL
```

Paused mode still stores incoming snapshots, so `/summary` and `/levels` remain
current.

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
