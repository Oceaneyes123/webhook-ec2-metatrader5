# Graph Report - .  (2026-07-06)

## Corpus Check
- Corpus is ~19,328 words - fits in a single context window. You may not need a graph.

## Summary
- 468 nodes · 841 edges · 23 communities (16 shown, 7 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 52 edges (avg confidence: 0.81)
- Token cost: 29,308 input · 18,777 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Server and Commands|Server and Commands]]
- [[_COMMUNITY_Market Analysis Tests|Market Analysis Tests]]
- [[_COMMUNITY_Webhook Dispatch Tests|Webhook Dispatch Tests]]
- [[_COMMUNITY_Shared Test Fixtures|Shared Test Fixtures]]
- [[_COMMUNITY_Candlestick Chart Design|Candlestick Chart Design]]
- [[_COMMUNITY_Market State and Levels|Market State and Levels]]
- [[_COMMUNITY_Payload Formatting Tests|Payload Formatting Tests]]
- [[_COMMUNITY_Alerts and Heartbeats|Alerts and Heartbeats]]
- [[_COMMUNITY_MQL5 Integration Tests|MQL5 Integration Tests]]
- [[_COMMUNITY_Telegram Test Utilities|Telegram Test Utilities]]
- [[_COMMUNITY_Local Server Runtime|Local Server Runtime]]
- [[_COMMUNITY_Heartbeat Tests|Heartbeat Tests]]
- [[_COMMUNITY_MQL5 Source Workflow|MQL5 Source Workflow]]
- [[_COMMUNITY_Candlestick Patterns|Candlestick Patterns]]
- [[_COMMUNITY_Environment Loading|Environment Loading]]
- [[_COMMUNITY_Telegram Messages|Telegram Messages]]
- [[_COMMUNITY_Logging Lifecycle|Logging Lifecycle]]
- [[_COMMUNITY_Package Entrypoints|Package Entrypoints]]
- [[_COMMUNITY_Pytest Configuration|Pytest Configuration]]
- [[_COMMUNITY_Test Package Setup|Test Package Setup]]
- [[_COMMUNITY_CodeGraph Policy|CodeGraph Policy]]
- [[_COMMUNITY_Git Safety Policy|Git Safety Policy]]
- [[_COMMUNITY_Symbol Aliases|Symbol Aliases]]

## God Nodes (most connected - your core abstractions)
1. `display_symbol()` - 28 edges
2. `snapshot()` - 24 edges
3. `MarketState` - 20 edges
4. `make_handler()` - 17 edges
5. `TradeStateTest` - 15 edges
6. `EaContentTest` - 14 edges
7. `CandleAlertMessageTest` - 13 edges
8. `HeartbeatTest` - 12 edges
9. `WebhookHandlerTest` - 12 edges
10. `get_logger()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Support, Resistance, Fibonacci, PDH/PDL, and FVG Levels` --semantically_similar_to--> `Chart Level and Candle Selection`  [INFERRED] [semantically similar]
  docs/superpowers/specs/2026-06-28-market-summary-levels-design.md → webhook/market_chart.py
- `Webhook2 Trade Config Cache` --semantically_similar_to--> `Telegram Request Retry Policy`  [INFERRED] [semantically similar]
  README.md → webhook/telegram_sender.py
- `Chronological Candle History Normalization` --conceptually_related_to--> `MarketState`  [EXTRACTED]
  docs/superpowers/plans/2026-07-02-levels-candlestick-visibility.md → webhook/market_state.py
- `Unified Timeframe Snapshot Pipeline` --conceptually_related_to--> `MarketState`  [EXTRACTED]
  docs/superpowers/plans/2026-06-28-market-summary-levels.md → webhook/market_state.py
- `EMA and Pattern Timeframe Roles` --conceptually_related_to--> `Pattern and EMA Notification Pipeline`  [INFERRED]
  docs/superpowers/specs/2026-06-28-market-summary-levels-design.md → webhook/market_state.py

## Import Cycles
- 1-file cycle: `webhook/__init__.py -> webhook/__init__.py`
- 3-file cycle: `webhook/__init__.py -> webhook/server.py -> webhook/polling.py -> webhook/__init__.py`

## Hyperedges (group relationships)
- **Telegram Command Control Plane** — commands_command_registry, commands_alert_control, commands_trade_mode_commands, heartbeat_status_reporting [EXTRACTED 1.00]
- **Market Intelligence Reports** — market_analyzer_confluence, market_analyzer_rsi_report, market_analyzer_key_levels [EXTRACTED 1.00]
- **Snapshot Alert Delivery** — events_snapshot_pipeline, json_data_parser_alert_formatting, json_data_parser_symbol_normalization [EXTRACTED 1.00]
- **Market Snapshot State and Reporting Flow** — market_summary_levels_plan_snapshot_pipeline, market_state_market_state, state_market_singletons, polling_levels_chart_delivery, market_chart_levels_chart [INFERRED 0.88]
- **Canonical MQL5 Delivery Workflow** — agents_mq5_source_workflow, sync_mq5_mql5_source_manifest, sync_mq5_canonical_sync, two_ea_refactor_plan_multi_file_sync, readme_two_ea_setup [EXTRACTED 1.00]
- **Telegram Levels Response Flow** — polling_telegram_polling, polling_levels_chart_delivery, state_market_singletons, market_chart_levels_chart, telegram_sender_photo_upload [EXTRACTED 1.00]
- **Candle History Pipeline** — levels_candlestick_visibility_build_candles_json, levels_candlestick_visibility_validate_snapshot, levels_candlestick_visibility_candle_history, levels_candlestick_visibility_chart_selection, levels_candlestick_visibility_levels_chart [EXTRACTED 1.00]
- **Two-EA Architecture** — two_ea_refactor_webhook1, two_ea_refactor_webhook2, two_ea_refactor_shared_common, two_ea_refactor_market_snapshot, two_ea_refactor_trade_manager, two_ea_refactor_python_server [EXTRACTED 1.00]
- **Candle-First Rendering Strategy** — levels_candlestick_visibility_candle_derived_axis, levels_candlestick_visibility_fvg_clipping, levels_candlestick_visibility_label_rail, levels_candlestick_visibility_render_order [EXTRACTED 1.00]

## Communities (23 total, 7 thin omitted)

### Community 0 - "Server and Commands"
Cohesion: 0.08
Nodes (55): BaseHTTPRequestHandler, Run the webhook-ec2 trading server.  Thin entry-point: import the server module, _clean_old_log(), CleanFileHandler, get_logger(), _cmd_buy(), _cmd_help(), _cmd_notrade() (+47 more)

### Community 1 - "Market Analysis Tests"
Cohesion: 0.08
Nodes (33): Tests for market_analyzer — summary, levels, RSI reports., Tests for market_chart — levels chart PNG generation., _handle_candle_pattern(), _handle_ea_error(), _handle_tf_snapshot(), _handle_trade_close(), _handle_trade_open(), notify_error() (+25 more)

### Community 2 - "Webhook Dispatch Tests"
Cohesion: 0.06
Nodes (11): make_handler(), Return a bare ``WebhookHandler`` wired with dummy I/O.      The handler's ``resp, EaErrorTest, Tests for webhook handler dispatch, Telegram commands, EA lifecycle, and trade s, Telegram initialisation and env detection., EA error payload handling., Trade mode persistence and symbol overrides., Webhook POST dispatch via WebhookHandler. (+3 more)

### Community 3 - "Shared Test Fixtures"
Cohesion: 0.08
Nodes (21): Path, LoggerCleanTest, Tests for app_logger — log cleanup., Log rotation / cleanup., Build a ``TIMEFRAME_SNAPSHOT`` payload with sensible defaults., snapshot(), MarketAnalyzerHtmlEscapeTest, MarketAnalyzerLevelsTest (+13 more)

### Community 4 - "Candlestick Chart Design"
Cohesion: 0.07
Nodes (35): BuildCandlesJson, Candle-Derived Y-Axis, Normalized candle_history, MarketState._chart_candles, Closed Candle History, FVG Zone Clipping, Out-of-Range Level Label Rail, MarketState.levels_chart (+27 more)

### Community 5 - "Market State and Levels"
Cohesion: 0.09
Nodes (24): Levels Candle-First Chart Plan, Candle-Defined Chart Axis, Chronological Candle History Normalization, Chart Level and Candle Selection, Candle-First Key Levels Chart, Pattern and EMA Notification Pipeline, Retained Pattern Invalidation, Timeframe Snapshot Validation (+16 more)

### Community 6 - "Payload Formatting Tests"
Cohesion: 0.06
Nodes (9): CandleAlertMessageTest, DisplayTimeTest, Tests for json_data_parser — candle messages, symbol aliases, display time., Message formatting for candle/pattern alerts., Timezone offset display formatting., Payload event-type filtering., Symbol normalisation., SupportedPayloadTest (+1 more)

### Community 7 - "Alerts and Heartbeats"
Cohesion: 0.11
Nodes (29): Alert Pause and Resume Control, Telegram Command Registry, Market Report Commands, Trade Mode Commands, Environment-Based Configuration, EA Event Handler Registry, Timeframe Snapshot Notification Pipeline, Trade and EA Issue Notifications (+21 more)

### Community 8 - "MQL5 Integration Tests"
Cohesion: 0.08
Nodes (10): make_mq5_sources(), Write placeholder MQ5 source files under *source_dir*., EaContentTest, Mq5SourceExistenceTest, Tests for sync_mq5 — file copying and source validation., MQ5 source sync behaviour., All canonical MQL5 source files exist., Structural assertions on MQ5 source contents. (+2 more)

### Community 9 - "Telegram Test Utilities"
Cohesion: 0.10
Nodes (15): Any, collect_requests(), fake_urlopen_ok(), Shared test utilities for webhook-ec2 tests.  Provides helpers used across multi, File-like object that returns *data* when read., Return a ``urlopen`` callable that always returns ``{"ok": True}``., Return a ``urlopen`` callable that records ``(request, timeout)`` calls.      Th, Return a ``urlopen`` that fails once, then succeeds on retry. (+7 more)

### Community 10 - "Local Server Runtime"
Cohesion: 0.11
Nodes (21): Local-Default Setup Design, Optional Future Linux Deployment, Local-Default Setup Plan, 127.0.0.1:8000 Default, Atomic Market-State Persistence, Telegram Long Polling, EA Heartbeat Monitoring, Local MT5 Webhook-to-Telegram Architecture (+13 more)

### Community 11 - "Heartbeat Tests"
Cohesion: 0.14
Nodes (3): HeartbeatTest, Tests for EA heartbeat management., EA heartbeat recording and status reporting.

### Community 12 - "MQL5 Source Workflow"
Cohesion: 0.36
Nodes (9): Canonical-First MQL5 Source Workflow, MQL5 Source Sync Plan, One-Way Canonical Source Copy, Two-EA MT5 Setup, Canonical-to-Live MQL5 Sync, Tracked MQL5 Source Manifest, Two-EA Refactor Plan, Two-Target Multi-File Sync (+1 more)

### Community 13 - "Candlestick Patterns"
Cohesion: 0.47
Nodes (6): Candlestick Pattern Support Design, Legacy Pattern Payload Compatibility, Shooting Star, Inverted Hammer, Star, and Inside Bar Rules, Candlestick Pattern Support Plan, Directional Bias and OHLC Reporting, Independent Multi-Pattern Detection

### Community 14 - "Environment Loading"
Cohesion: 0.50
Nodes (4): Automatic Dotenv Loading Design, Standard-Library Dotenv Loader, Automatic Dotenv Loading Plan, Process Environment Precedence

### Community 15 - "Telegram Messages"
Cohesion: 0.50
Nodes (4): Escaped EA Issue Message, Telegram Message Formatting, Trade Open and Close Notifications, Trade Close Notifications

## Ambiguous Edges - Review These
- `Candlestick Visibility Verification` → `Optional Development Tools`  [AMBIGUOUS]
  requirements.txt · relation: conceptually_related_to

## Knowledge Gaps
- **36 isolated node(s):** `Webhook Server Entrypoint`, `Webhook Public API Facade`, `Environment-Based Configuration`, `RSI Extreme Report`, `Log Cleanup Contract Tests` (+31 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Candlestick Visibility Verification` and `Optional Development Tools`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `MarketState` connect `Market State and Levels` to `Server and Commands`, `Market Analysis Tests`, `Local Server Runtime`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Why does `MarketChart` connect `Market Analysis Tests` to `Server and Commands`, `Market State and Levels`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `Levels Chart Delivery Flow` connect `Market State and Levels` to `Local Server Runtime`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `Path` (e.g. with `.test_logger_cleans_log_after_five_hours()` and `.test_summary_escapes_dynamic_symbol()`) actually correct?**
  _`Path` has 29 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Run the webhook-ec2 trading server.  Thin entry-point: import the server module`, `webhook-ec2 test suite.  Automatically adds the project root to ``sys.path`` so`, `pytest configuration — ensures the project root is on sys.path.` to the rest of the system?**
  _103 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Server and Commands` be split into smaller, more focused modules?**
  _Cohesion score 0.07552973342447027 - nodes in this community are weakly interconnected._