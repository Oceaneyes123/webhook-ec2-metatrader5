---
type: community
cohesion: 0.11
members: 29
---

# Alerts and Heartbeats

**Cohesion:** 0.11 - loosely connected
**Members:** 29 nodes

## Members
- [[Alert Pause and Resume Control]] - code - webhook/commands.py
- [[Broker Symbol Normalization]] - code - webhook/json_data_parser.py
- [[Canonical-to-Live MQ5 Sync Tests]] - code - tests/test_sync_mq5.py
- [[EA Event Handler Registry]] - code - webhook/events.py
- [[EA Heartbeat Registry]] - code - webhook/heartbeat.py
- [[Environment-Based Configuration]] - code - webhook/config.py
- [[HTML-Safe Candle Alert Formatting]] - code - webhook/json_data_parser.py
- [[Heartbeat Freshness Reporting]] - code - webhook/heartbeat.py
- [[Heartbeat Lifecycle Tests]] - code - tests/test_heartbeat.py
- [[Key Levels Report]] - code - webhook/market_analyzer.py
- [[Market Analyzer Report Tests]] - code - tests/test_market_analyzer.py
- [[Market Chart Rendering Tests]] - code - tests/test_market_chart.py
- [[Market Report Commands]] - code - webhook/commands.py
- [[Market Snapshot Test Fixture]] - code - tests/test_helpers.py
- [[Market State Snapshot and Pattern Tests]] - code - tests/test_market_state.py
- [[Multi-Timeframe Trade Confluence]] - code - webhook/market_analyzer.py
- [[Payload Parsing and Formatting Tests]] - code - tests/test_json_data_parser.py
- [[Persisted Trade Modes]] - code - trade_state.json
- [[RSI Extreme Report]] - code - webhook/market_analyzer.py
- [[Read-Only Market State Analysis]] - code - webhook/market_analyzer.py
- [[Telegram Command Registry]] - code - webhook/commands.py
- [[Telegram HTTP Transport Tests]] - code - tests/test_telegram_sender.py
- [[Timeframe Snapshot Notification Pipeline]] - code - webhook/events.py
- [[Trade Mode Commands]] - code - webhook/commands.py
- [[Trade and EA Issue Notifications]] - code - webhook/events.py
- [[Two-EA Responsibility Separation]] - code - tests/test_sync_mq5.py
- [[Webhook HTTP Dispatch Tests]] - code - tests/test_webhook_handler.py
- [[Webhook Payload Contract]] - code - webhook/json_data_parser.py
- [[Webhook Trade State Integration Tests]] - code - tests/test_webhook_handler.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Alerts_and_Heartbeats
SORT file.name ASC
```
