---
type: community
cohesion: 0.08
members: 77
---

# Server and Commands

**Cohesion:** 0.08 - loosely connected
**Members:** 77 nodes

## Members
- [[.do_GET()]] - code - webhook/server.py
- [[.do_POST()]] - code - webhook/server.py
- [[.emit()]] - code - webhook/app_logger.py
- [[.handle_telegram()]] - code - webhook/server.py
- [[.notify_error()]] - code - webhook/server.py
- [[.write_json()]] - code - webhook/server.py
- [[.write_text()]] - code - webhook/server.py
- [[BaseHTTPRequestHandler]] - code
- [[CleanFileHandler]] - code - webhook/app_logger.py
- [[Decorator register a function for one or more Telegram commands.]] - rationale - webhook/commands.py
- [[EA heartbeat tracking — records, ages, and reports heartbeat status.]] - rationale - webhook/heartbeat.py
- [[Environment config loading and utility helpers.]] - rationale - webhook/config.py
- [[HTTP server — WebhookHandler with GET and POST dispatch.]] - rationale - webhook/server.py
- [[Run the webhook-ec2 trading server.  Thin entry-point import the server module]] - rationale - run.py
- [[Telegram command registry — maps command strings to handler functions.]] - rationale - webhook/commands.py
- [[Telegram long-polling — fetches updates and dispatches commands.]] - rationale - webhook/polling.py
- [[Telegram message formatting — pure presentation helpers with no side effects.]] - rationale - webhook/messages.py
- [[Trade mode persistence and symbol override management.]] - rationale - webhook/trade_state.py
- [[WebhookHandler]] - code - webhook/server.py
- [[__init__.py_1]] - code - webhook/__init__.py
- [[_clean_old_log()]] - code - webhook/app_logger.py
- [[_cmd_buy()]] - code - webhook/commands.py
- [[_cmd_help()]] - code - webhook/commands.py
- [[_cmd_market_command()]] - code - webhook/commands.py
- [[_cmd_notrade()]] - code - webhook/commands.py
- [[_cmd_pause()]] - code - webhook/commands.py
- [[_cmd_recent()]] - code - webhook/commands.py
- [[_cmd_resume()]] - code - webhook/commands.py
- [[_cmd_sell()]] - code - webhook/commands.py
- [[_cmd_status()]] - code - webhook/commands.py
- [[_format_age()]] - code - webhook/heartbeat.py
- [[_post_telegram_request()]] - code - webhook/telegram_sender.py
- [[app_logger.py]] - code - webhook/app_logger.py
- [[command_reply()]] - code - webhook/commands.py
- [[commands.py]] - code - webhook/commands.py
- [[config.py]] - code - webhook/config.py
- [[default_trade_state()]] - code - webhook/trade_state.py
- [[error_message()]] - code - webhook/messages.py
- [[get_logger()]] - code - webhook/app_logger.py
- [[get_telegram_updates()]] - code - webhook/telegram_sender.py
- [[get_trade_mode()]] - code - webhook/trade_state.py
- [[health_text()]] - code - webhook/messages.py
- [[heartbeat.py]] - code - webhook/heartbeat.py
- [[heartbeat_age_seconds()]] - code - webhook/heartbeat.py
- [[heartbeat_stale_seconds()]] - code - webhook/config.py
- [[heartbeat_status_lines()]] - code - webhook/heartbeat.py
- [[help_text()]] - code - webhook/messages.py
- [[is_telegram_update()]] - code - webhook/commands.py
- [[load_dotenv()]] - code - webhook/config.py
- [[load_trade_state()]] - code - webhook/trade_state.py
- [[main()]] - code - webhook/server.py
- [[maybe_send_levels_chart()]] - code - webhook/polling.py
- [[messages.py]] - code - webhook/messages.py
- [[normalize_trade_mode()]] - code - webhook/trade_state.py
- [[normalize_trade_symbol()]] - code - webhook/trade_state.py
- [[poll_telegram_forever()]] - code - webhook/polling.py
- [[poll_telegram_once()]] - code - webhook/polling.py
- [[polling.py]] - code - webhook/polling.py
- [[polling_interval()]] - code - webhook/config.py
- [[record_ea_heartbeat()]] - code - webhook/heartbeat.py
- [[register_command()]] - code - webhook/commands.py
- [[reply_to_telegram_update()]] - code - webhook/polling.py
- [[run.py]] - code - run.py
- [[save_trade_state()]] - code - webhook/trade_state.py
- [[send_telegram_message()]] - code - webhook/telegram_sender.py
- [[send_telegram_photo()]] - code - webhook/telegram_sender.py
- [[server.py]] - code - webhook/server.py
- [[server_config()]] - code - webhook/config.py
- [[set_trade_mode()]] - code - webhook/trade_state.py
- [[start_telegram_polling()]] - code - webhook/polling.py
- [[telegram_configured()]] - code - webhook/config.py
- [[telegram_sender.py]] - code - webhook/telegram_sender.py
- [[trade_config()]] - code - webhook/trade_state.py
- [[trade_state.py]] - code - webhook/trade_state.py
- [[trade_state_path()]] - code - webhook/trade_state.py
- [[uptime_text()]] - code - webhook/config.py
- [[webhook-ec2 — MT5 Telegram Webhook Trading Server.]] - rationale - webhook/__init__.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Server_and_Commands
SORT file.name ASC
```

## Connections to other communities
- 50 edges to [[_COMMUNITY_Market Analysis Tests]]
- 5 edges to [[_COMMUNITY_Shared Test Fixtures]]
- 1 edge to [[_COMMUNITY_Telegram Test Utilities]]
- 1 edge to [[_COMMUNITY_Webhook Dispatch Tests]]
- 1 edge to [[_COMMUNITY_Market State and Levels]]
- 1 edge to [[_COMMUNITY_MQL5 Integration Tests]]

## Top bridge nodes
- [[__init__.py_1]] - degree 69, connects to 3 communities
- [[trade_state.py]] - degree 18, connects to 2 communities
- [[app_logger.py]] - degree 14, connects to 2 communities
- [[telegram_sender.py]] - degree 11, connects to 2 communities
- [[maybe_send_levels_chart()]] - degree 7, connects to 2 communities