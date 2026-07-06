---
type: community
cohesion: 0.08
members: 28
---

# MQL5 Integration Tests

**Cohesion:** 0.08 - loosely connected
**Members:** 28 nodes

## Members
- [[.test_all_canonical_mql5_sources_exist()]] - code - tests/test_sync_mq5.py
- [[.test_both_eas_use_the_local_webhook_default()]] - code - tests/test_sync_mq5.py
- [[.test_legacy_canonical_ea_is_removed()]] - code - tests/test_sync_mq5.py
- [[.test_market_ea_owns_snapshots_only()]] - code - tests/test_sync_mq5.py
- [[.test_readme_documents_two_ea_setup()]] - code - tests/test_sync_mq5.py
- [[.test_sync_copies_both_eas_and_shared_includes()]] - code - tests/test_sync_mq5.py
- [[.test_sync_rejects_canonical_files_as_live_targets()]] - code - tests/test_sync_mq5.py
- [[.test_trade_config_url_includes_encoded_chart_symbol()]] - code - tests/test_sync_mq5.py
- [[.test_trade_ea_manages_trading_on_timer()]] - code - tests/test_sync_mq5.py
- [[.test_trade_ea_owns_trade_management_only()]] - code - tests/test_sync_mq5.py
- [[.test_trade_manager_has_config_cache()]] - code - tests/test_sync_mq5.py
- [[.test_trade_manager_has_position_close_detection()]] - code - tests/test_sync_mq5.py
- [[.test_webhook1_has_heartbeat_timer()]] - code - tests/test_sync_mq5.py
- [[.test_webhook2_has_heartbeat_and_config_cache()]] - code - tests/test_sync_mq5.py
- [[.test_webhook_common_has_send_ea_heartbeat()]] - code - tests/test_sync_mq5.py
- [[.test_webhook_common_has_send_trade_close()]] - code - tests/test_sync_mq5.py
- [[All canonical MQL5 source files exist.]] - rationale - tests/test_sync_mq5.py
- [[EaContentTest]] - code - tests/test_sync_mq5.py
- [[MQ5 source sync behaviour.]] - rationale - tests/test_sync_mq5.py
- [[Mq5SourceExistenceTest]] - code - tests/test_sync_mq5.py
- [[Structural assertions on MQ5 source contents.]] - rationale - tests/test_sync_mq5.py
- [[SyncMq5Test]] - code - tests/test_sync_mq5.py
- [[Tests for sync_mq5 — file copying and source validation.]] - rationale - tests/test_sync_mq5.py
- [[Write placeholder MQ5 source files under source_dir.]] - rationale - tests/test_helpers.py
- [[make_mq5_sources()]] - code - tests/test_helpers.py
- [[sync_mq5()]] - code - webhook/sync_mq5.py
- [[sync_mq5.py]] - code - webhook/sync_mq5.py
- [[test_sync_mq5.py]] - code - tests/test_sync_mq5.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/MQL5_Integration_Tests
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Shared Test Fixtures]]
- 2 edges to [[_COMMUNITY_Telegram Test Utilities]]
- 1 edge to [[_COMMUNITY_Server and Commands]]

## Top bridge nodes
- [[make_mq5_sources()]] - degree 6, connects to 2 communities
- [[test_sync_mq5.py]] - degree 7, connects to 1 community
- [[.test_sync_copies_both_eas_and_shared_includes()]] - degree 3, connects to 1 community
- [[.test_sync_rejects_canonical_files_as_live_targets()]] - degree 3, connects to 1 community
- [[sync_mq5.py]] - degree 3, connects to 1 community