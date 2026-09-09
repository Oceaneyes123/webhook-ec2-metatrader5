# Development workflow

## Python source of truth and startup

`run.py` is the Python entry point. It imports `webhook.server.main`, which
loads `.env`, starts Telegram polling and heartbeat monitoring, and serves the
HTTP endpoints.

```powershell
python -m pip install -r requirements.txt
python run.py
```

Internal modules import functions and state from their owning modules. The
package-level names in `webhook/__init__.py` are lazy compatibility exports for
existing callers, not the application entry point.

## Formatting, linting, and tests

Install the development tools once:

```powershell
python -m pip install -r requirements-dev.txt
```

Then run:

```powershell
python -m ruff format --check
python -m ruff check webhook tests run.py sync_mq5.py
python -m unittest
```

To apply Python formatting intentionally:

```powershell
python -m ruff format
```

## MQL5 source of truth and synchronization

Edit canonical sources under `mq5/`. The main market/trade EAs are
`mq5/Webhook1.mq5` and `mq5/Webhook2.mq5`; their shared includes are
`mq5/includes/WebhookCommon.mqh`, `mq5/includes/MarketSnapshot.mqh`, and
`mq5/includes/TradeManager.mqh`. The auxiliary canonical EAs synchronized by
the same tool are `mq5/BigMove.mq5`, `mq5/TPSL.mq5`, and
`mq5/Overtrade.mq5`.

Never edit root `Webhook1.mq5` or `Webhook2.mq5`, or live MetaTrader include
copies. They point to, or are copied into, the live MetaTrader Experts tree.

After a canonical MQL5 change:

```powershell
python sync_mq5.py
python sync_mq5.py --check
```

Compile or reload both affected live EAs in MetaEditor. The sync check compares
all synchronized source files byte-for-byte and does not modify them.
