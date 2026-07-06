---
type: community
cohesion: 0.08
members: 41
---

# Shared Test Fixtures

**Cohesion:** 0.08 - loosely connected
**Members:** 41 nodes

## Members
- [[.test_far_levels_are_labels_without_compressing_candles()]] - code - tests/test_market_chart.py
- [[.test_higher_opposing_pattern_invalidates_older_lower_pattern()]] - code - tests/test_market_state.py
- [[.test_initial_snapshot_stores_patterns_and_returns_notifications()]] - code - tests/test_market_state.py
- [[.test_initial_snapshot_stores_patterns_without_notification()]] - code - tests/test_market_state.py
- [[.test_levels_chart_draws_recent_candlesticks()]] - code - tests/test_market_chart.py
- [[.test_levels_chart_writes_png_with_key_levels()]] - code - tests/test_market_chart.py
- [[.test_levels_report_formats_all_higher_timeframes_and_missing_data()]] - code - tests/test_market_analyzer.py
- [[.test_logger_cleans_log_after_five_hours()]] - code - tests/test_app_logger.py
- [[.test_market_state_accepts_optional_webhook1_source()]] - code - tests/test_market_state.py
- [[.test_market_state_accumulates_history_without_candles()]] - code - tests/test_market_state.py
- [[.test_market_state_module_is_available()]] - code - tests/test_market_state.py
- [[.test_market_state_persists_ema_snapshot_and_neutral_equality()]] - code - tests/test_market_state.py
- [[.test_market_state_rejects_snapshot_for_unknown_timeframe()]] - code - tests/test_market_state.py
- [[.test_market_state_returns_each_pattern_notification_once()]] - code - tests/test_market_state.py
- [[.test_market_state_stores_rsi_history_and_reports_extremes()]] - code - tests/test_market_state.py
- [[.test_market_state_uses_supplied_candle_history()]] - code - tests/test_market_state.py
- [[.test_summary_confluence_returns_buy_sell_or_wait()]] - code - tests/test_market_analyzer.py
- [[.test_summary_escapes_dynamic_symbol()]] - code - tests/test_market_analyzer.py
- [[Build a ``TIMEFRAME_SNAPSHOT`` payload with sensible defaults.]] - rationale - tests/test_helpers.py
- [[HTML escaping in reports.]] - rationale - tests/test_market_analyzer.py
- [[Levels chart image output.]] - rationale - tests/test_market_chart.py
- [[Levels report formatting.]] - rationale - tests/test_market_analyzer.py
- [[Log rotation  cleanup.]] - rationale - tests/test_app_logger.py
- [[LoggerCleanTest]] - code - tests/test_app_logger.py
- [[MarketAnalyzerHtmlEscapeTest]] - code - tests/test_market_analyzer.py
- [[MarketAnalyzerLevelsTest]] - code - tests/test_market_analyzer.py
- [[MarketAnalyzerSummaryTest]] - code - tests/test_market_analyzer.py
- [[MarketChartLevelsTest]] - code - tests/test_market_chart.py
- [[MarketState module availability.]] - rationale - tests/test_market_state.py
- [[MarketStateModuleTest]] - code - tests/test_market_state.py
- [[MarketStatePatternsTest]] - code - tests/test_market_state.py
- [[MarketStateSnapshotTest]] - code - tests/test_market_state.py
- [[Path]] - code
- [[Pattern tracking, invalidation, and notification dedup.]] - rationale - tests/test_market_state.py
- [[Snapshot ingestion and data persistence.]] - rationale - tests/test_market_state.py
- [[Summary confluence (buy  sell  wait).]] - rationale - tests/test_market_analyzer.py
- [[Tests for app_logger — log cleanup.]] - rationale - tests/test_app_logger.py
- [[Tests for market_state — snapshot ingestion, pattern notifications, candle histo]] - rationale - tests/test_market_state.py
- [[snapshot()]] - code - tests/test_helpers.py
- [[test_app_logger.py]] - code - tests/test_app_logger.py
- [[test_market_state.py]] - code - tests/test_market_state.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Shared_Test_Fixtures
SORT file.name ASC
```

## Connections to other communities
- 9 edges to [[_COMMUNITY_Market Analysis Tests]]
- 5 edges to [[_COMMUNITY_Server and Commands]]
- 4 edges to [[_COMMUNITY_Webhook Dispatch Tests]]
- 4 edges to [[_COMMUNITY_MQL5 Integration Tests]]
- 3 edges to [[_COMMUNITY_Telegram Test Utilities]]
- 2 edges to [[_COMMUNITY_Market State and Levels]]

## Top bridge nodes
- [[Path]] - degree 30, connects to 5 communities
- [[snapshot()]] - degree 24, connects to 3 communities
- [[test_market_state.py]] - degree 8, connects to 2 communities
- [[MarketChartLevelsTest]] - degree 5, connects to 1 community
- [[test_app_logger.py]] - degree 3, connects to 1 community