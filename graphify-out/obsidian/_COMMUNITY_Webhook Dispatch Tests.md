---
type: community
cohesion: 0.06
members: 44
---

# Webhook Dispatch Tests

**Cohesion:** 0.06 - loosely connected
**Members:** 44 nodes

## Members
- [[.setUp()_1]] - code - tests/test_webhook_handler.py
- [[.test_buy_saves_default_trade_mode()]] - code - tests/test_webhook_handler.py
- [[.test_corrupt_trade_state_uses_defaults()]] - code - tests/test_webhook_handler.py
- [[.test_ea_error_accepts_both_sources()]] - code - tests/test_webhook_handler.py
- [[.test_ea_error_payload_is_sent_to_telegram()]] - code - tests/test_webhook_handler.py
- [[.test_ea_issue_message_includes_source_when_present()]] - code - tests/test_webhook_handler.py
- [[.test_ea_issue_message_omits_source_when_missing()]] - code - tests/test_webhook_handler.py
- [[.test_help_lists_summary_levels_rsi_and_trade_commands()]] - code - tests/test_webhook_handler.py
- [[.test_load_dotenv_skips_comments_and_empty()]] - code - tests/test_webhook_handler.py
- [[.test_load_trade_state_restores_default_mode()]] - code - tests/test_webhook_handler.py
- [[.test_missing_trade_state_uses_defaults()]] - code - tests/test_webhook_handler.py
- [[.test_poll_telegram_once_replies_and_returns_next_offset()]] - code - tests/test_webhook_handler.py
- [[.test_save_trade_state_creates_parent_directories()]] - code - tests/test_webhook_handler.py
- [[.test_status_reports_default_mode_and_symbol_overrides()]] - code - tests/test_webhook_handler.py
- [[.test_status_reports_symbol_mode()]] - code - tests/test_webhook_handler.py
- [[.test_summary_levels_and_rsi_commands_require_a_symbol()]] - code - tests/test_webhook_handler.py
- [[.test_symbol_overrides_are_saved_and_reloaded()]] - code - tests/test_webhook_handler.py
- [[.test_symbol_trade_commands_do_not_change_default_mode()]] - code - tests/test_webhook_handler.py
- [[.test_telegram_command_can_arrive_on_webhook_path()]] - code - tests/test_webhook_handler.py
- [[.test_telegram_configured_returns_false_when_chat_id_missing()]] - code - tests/test_webhook_handler.py
- [[.test_telegram_configured_returns_false_when_token_missing()]] - code - tests/test_webhook_handler.py
- [[.test_telegram_configured_returns_true_when_env_set()]] - code - tests/test_webhook_handler.py
- [[.test_telegram_pause_and_resume_commands_control_alerts()]] - code - tests/test_webhook_handler.py
- [[.test_telegram_status_help_and_recent_commands()]] - code - tests/test_webhook_handler.py
- [[.test_trade_config_endpoint_returns_json()]] - code - tests/test_webhook_handler.py
- [[.test_trade_config_endpoint_uses_normalized_symbol_override()]] - code - tests/test_webhook_handler.py
- [[.test_trade_mode_commands_update_trade_config()]] - code - tests/test_webhook_handler.py
- [[.test_webhook1_snapshot_updates_market_state()]] - code - tests/test_webhook_handler.py
- [[.test_webhook_accepts_non_json_body()]] - code - tests/test_webhook_handler.py
- [[.test_webhook_accepts_valid_payload()]] - code - tests/test_webhook_handler.py
- [[.test_webhook_engulfing_candle_sends_telegram_notification()]] - code - tests/test_webhook_handler.py
- [[.test_webhook_rejects_invalid_path()]] - code - tests/test_webhook_handler.py
- [[EA error payload handling.]] - rationale - tests/test_webhook_handler.py
- [[EaErrorTest]] - code - tests/test_webhook_handler.py
- [[Return a bare ``WebhookHandler`` wired with dummy IO.      The handler's ``resp]] - rationale - tests/test_helpers.py
- [[Telegram initialisation and env detection.]] - rationale - tests/test_webhook_handler.py
- [[TelegramEnvTest]] - code - tests/test_webhook_handler.py
- [[Tests for webhook handler dispatch, Telegram commands, EA lifecycle, and trade s]] - rationale - tests/test_webhook_handler.py
- [[Trade mode persistence and symbol overrides.]] - rationale - tests/test_webhook_handler.py
- [[TradeStateTest]] - code - tests/test_webhook_handler.py
- [[Webhook POST dispatch via WebhookHandler.]] - rationale - tests/test_webhook_handler.py
- [[WebhookHandlerTest]] - code - tests/test_webhook_handler.py
- [[make_handler()]] - code - tests/test_helpers.py
- [[test_webhook_handler.py]] - code - tests/test_webhook_handler.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Webhook_Dispatch_Tests
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Shared Test Fixtures]]
- 3 edges to [[_COMMUNITY_Telegram Test Utilities]]
- 1 edge to [[_COMMUNITY_Heartbeat Tests]]
- 1 edge to [[_COMMUNITY_Market Analysis Tests]]
- 1 edge to [[_COMMUNITY_Server and Commands]]

## Top bridge nodes
- [[test_webhook_handler.py]] - degree 10, connects to 4 communities
- [[make_handler()]] - degree 17, connects to 2 communities
- [[.test_webhook1_snapshot_updates_market_state()]] - degree 3, connects to 1 community
- [[.setUp()_1]] - degree 2, connects to 1 community
- [[.test_save_trade_state_creates_parent_directories()]] - degree 2, connects to 1 community