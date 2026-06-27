# MT5 Webhook to Telegram

Small Python webhook server for MetaTrader 5 alerts. MT5 posts candle signals to EC2, and the server forwards supported alerts to Telegram.

```text
MT5 EA -> POST /webhook -> EC2 Python server -> Telegram
Telegram -> POST /telegram -> pause/resume/status/recent commands
```

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/webhook` | Receive MT5 alert payloads |
| `POST` | `/telegram` | Receive Telegram bot command updates |
| `GET` | `/health` | Plain-text health check |

Health check example:

```text
✅ Webhook healthy
Telegram: configured
Alerts: running
Uptime: 2h 15m
```

## Environment

Create `.env` beside `webhook.py`:

```env
HOST=0.0.0.0
PORT=8000
PUBLIC_URL=http://YOUR_EC2_IP:8000/webhook
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
TIMEZONE_OFFSET_HOURS=5
```

The included `webhook-ec2.service` loads this file through `EnvironmentFile`.

For local shell runs, export the values first or use your shell's env loader, then run:

```bash
python3 webhook.py
```

## EC2 Setup

Clone and enter the project:

```bash
git clone https://github.com/Oceaneyes123/webhook-ec2-metatrader5.git
cd webhook-ec2-metatrader5
```

Open port `8000` only to the MT5 machine public IP when possible.

AWS Security Group inbound rule:

```text
Type: Custom TCP
Port: 8000
Source: YOUR_MT5_MACHINE_PUBLIC_IP/32
```

If `ufw` is active:

```bash
sudo ufw allow 8000/tcp
sudo ufw reload
```

Install and start the service:

```bash
sudo cp webhook-ec2.service /etc/systemd/system/webhook-ec2.service
sudo systemctl daemon-reload
sudo systemctl enable --now webhook-ec2
sudo systemctl status webhook-ec2
```

## Telegram Commands

Commands are read by polling every 10 seconds by default, so HTTPS is not required.

Optional `.env` setting:

```env
TELEGRAM_POLL_SECONDS=10
```

If you later use an HTTPS domain, you can set a Telegram webhook instead:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook?url=https://YOUR_DOMAIN/telegram"
```

Telegram requires an HTTPS webhook URL. Polling works with only the bot token and does not need a public `/telegram` URL.

Available commands:

```text
/status - Check bot status
/pause - Pause MT5 alerts
/resume - Resume MT5 alerts
/help - Show available commands
/recent Gold - Show last 5 saved signals for a pair
```

Paused alerts return `paused` to MT5 and are not sent to Telegram.

## MT5 Setup

In MT5:

```text
Tools > Options > Expert Advisors > Allow WebRequest for listed URL
```

Add:

```text
http://YOUR_EC2_IP:8000
```

Attach the EA to a live chart. MT5 WebRequest does not work in Strategy Tester.

Production EA inputs:

```text
WebhookEnvironment = ENV_PRODUCTION
ProductionWebhookUrl = http://YOUR_EC2_IP:8000/webhook
WebRequestTimeoutMs = 5000
PrintDebugLogs = true
```

## Test Requests

Health:

```bash
curl -i http://YOUR_EC2_IP:8000/health
```

Webhook:

```bash
curl -i -X POST http://YOUR_EC2_IP:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"event_type":"ENGULFING_CANDLE","signal":"BUY","symbol":"GOLDmicro","timeframe":"M1","candle_time":"2026.06.26 11:11:00","open":4029.07,"close":4030.23}'
```

Expected response:

```text
HTTP/1.0 200 OK
ok
```

## Troubleshooting

Check listener:

```bash
sudo ss -lntp | grep 8000
```

Check service logs:

```bash
journalctl -u webhook-ec2 -f
```

Common MT5 errors:

```text
4014 - URL is not in the MT5 WebRequest allow-list
5203 - Connection issue; check Security Group, firewall, URL, and service status
```

Run tests:

```bash
python -m unittest test_webhook.py
```
