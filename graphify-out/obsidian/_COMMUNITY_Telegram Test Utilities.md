---
type: community
cohesion: 0.10
members: 27
---

# Telegram Test Utilities

**Cohesion:** 0.10 - loosely connected
**Members:** 27 nodes

## Members
- [[.__enter__()]] - code - tests/test_helpers.py
- [[.__exit__()]] - code - tests/test_helpers.py
- [[.__init__()]] - code - tests/test_helpers.py
- [[.read()]] - code - tests/test_helpers.py
- [[.test_get_telegram_updates_uses_offset_and_timeout()]] - code - tests/test_telegram_sender.py
- [[.test_send_telegram_message_can_disable_html()]] - code - tests/test_telegram_sender.py
- [[.test_send_telegram_message_can_override_chat_id()]] - code - tests/test_telegram_sender.py
- [[.test_send_telegram_message_includes_telegram_error_body()]] - code - tests/test_telegram_sender.py
- [[.test_send_telegram_message_posts_to_send_message_api()]] - code - tests/test_telegram_sender.py
- [[.test_send_telegram_message_retries_connection_errors()]] - code - tests/test_telegram_sender.py
- [[Any]] - code
- [[File-like object that returns data when read.]] - rationale - tests/test_helpers.py
- [[GetTelegramUpdatesTest]] - code - tests/test_telegram_sender.py
- [[Polling for incoming updates.]] - rationale - tests/test_telegram_sender.py
- [[Return a ``urlopen`` callable that always returns ``{ok True}``.]] - rationale - tests/test_helpers.py
- [[Return a ``urlopen`` callable that records ``(request, timeout)`` calls.      Th]] - rationale - tests/test_helpers.py
- [[Return a ``urlopen`` that fails once, then succeeds on retry.]] - rationale - tests/test_helpers.py
- [[SendTelegramMessageTest]] - code - tests/test_telegram_sender.py
- [[Shared test utilities for webhook-ec2 tests.  Provides helpers used across multi]] - rationale - tests/test_helpers.py
- [[Telegram message sending behaviour.]] - rationale - tests/test_telegram_sender.py
- [[Tests for telegram_sender — send_message, get_updates, retries.]] - rationale - tests/test_telegram_sender.py
- [[_TelegramResponse]] - code - tests/test_helpers.py
- [[collect_requests()]] - code - tests/test_helpers.py
- [[fake_urlopen_ok()]] - code - tests/test_helpers.py
- [[test_helpers.py]] - code - tests/test_helpers.py
- [[test_telegram_sender.py]] - code - tests/test_telegram_sender.py
- [[urlopen_first_error_then_ok()]] - code - tests/test_helpers.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Telegram_Test_Utilities
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Webhook Dispatch Tests]]
- 3 edges to [[_COMMUNITY_Shared Test Fixtures]]
- 2 edges to [[_COMMUNITY_MQL5 Integration Tests]]
- 2 edges to [[_COMMUNITY_Market Analysis Tests]]
- 1 edge to [[_COMMUNITY_Heartbeat Tests]]
- 1 edge to [[_COMMUNITY_Server and Commands]]

## Top bridge nodes
- [[test_helpers.py]] - degree 15, connects to 5 communities
- [[Any]] - degree 3, connects to 2 communities
- [[test_telegram_sender.py]] - degree 8, connects to 1 community