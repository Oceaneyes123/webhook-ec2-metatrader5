---
type: community
cohesion: 0.14
members: 14
---

# Heartbeat Tests

**Cohesion:** 0.14 - loosely connected
**Members:** 14 nodes

## Members
- [[.setUp()]] - code - tests/test_heartbeat.py
- [[.test_record_ea_heartbeat_normalizes_source_to_lowercase()]] - code - tests/test_heartbeat.py
- [[.test_record_ea_heartbeat_normalizes_symbol()]] - code - tests/test_heartbeat.py
- [[.test_record_ea_heartbeat_stores_source_symbol_and_status()]] - code - tests/test_heartbeat.py
- [[.test_status_shows_missing_when_no_heartbeats()]] - code - tests/test_heartbeat.py
- [[.test_status_shows_running_with_fresh_heartbeat()]] - code - tests/test_heartbeat.py
- [[.test_status_shows_stale_when_heartbeat_old()]] - code - tests/test_heartbeat.py
- [[.test_unknown_source_accepted_and_appears_after_known()]] - code - tests/test_heartbeat.py
- [[.test_webhook_ea_heartbeat_returns_ok_no_telegram()]] - code - tests/test_heartbeat.py
- [[.test_webhook_ea_heartbeat_stores_heartbeat()]] - code - tests/test_heartbeat.py
- [[EA heartbeat recording and status reporting.]] - rationale - tests/test_heartbeat.py
- [[HeartbeatTest]] - code - tests/test_heartbeat.py
- [[Tests for EA heartbeat management.]] - rationale - tests/test_heartbeat.py
- [[test_heartbeat.py]] - code - tests/test_heartbeat.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Heartbeat_Tests
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Telegram Test Utilities]]
- 1 edge to [[_COMMUNITY_Webhook Dispatch Tests]]

## Top bridge nodes
- [[test_heartbeat.py]] - degree 4, connects to 2 communities