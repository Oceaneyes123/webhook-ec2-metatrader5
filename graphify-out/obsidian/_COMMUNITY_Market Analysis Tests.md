---
type: community
cohesion: 0.08
members: 53
---

# Market Analysis Tests

**Cohesion:** 0.08 - loosely connected
**Members:** 53 nodes

## Members
- [[.__init__()_1]] - code - webhook/market_analyzer.py
- [[.__init__()_2]] - code - webhook/market_chart.py
- [[._chart_candles()]] - code - webhook/market_chart.py
- [[._chart_items()]] - code - webhook/market_chart.py
- [[._draw_candles()]] - code - webhook/market_chart.py
- [[._format_zone()]] - code - webhook/market_analyzer.py
- [[._level()]] - code - webhook/market_analyzer.py
- [[._suggestion()]] - code - webhook/market_analyzer.py
- [[.levels()]] - code - webhook/market_analyzer.py
- [[.levels_chart()]] - code - webhook/market_chart.py
- [[.rsi_summary()]] - code - webhook/market_analyzer.py
- [[.summary()]] - code - webhook/market_analyzer.py
- [[Chart rendering for key-level visualisations.  Extracted from MarketState to dec]] - rationale - webhook/market_chart.py
- [[Convert MT5 datetime value to human-readable string.]] - rationale - webhook/market_state.py
- [[Decorator register a function for one or more event types.]] - rationale - webhook/events.py
- [[EA webhook event dispatcher — strongly-typed handlers by event_type.]] - rationale - webhook/events.py
- [[Format a price to the snapshot's decimal digits.]] - rationale - webhook/market_state.py
- [[Market analysis logic — summary, levels, RSI reports.  Extracted from MarketStat]] - rationale - webhook/market_analyzer.py
- [[MarketAnalyzer]] - code - webhook/market_analyzer.py
- [[MarketChart]] - code - webhook/market_chart.py
- [[Persistent latest-state storage for market snapshots.  Keeps candle-history, EMA]] - rationale - webhook/market_state.py
- [[Raise ValueError if payload is not a valid TIMEFRAME_SNAPSHOT.]] - rationale - webhook/market_state.py
- [[Read-only analysis over a MarketState's persisted data.]] - rationale - webhook/market_analyzer.py
- [[Renders key-level PNG charts from MarketState data.]] - rationale - webhook/market_chart.py
- [[Shared global state used across webhook modules.  Cross-cutting state that doesn]] - rationale - webhook/state.py
- [[Tests for market_analyzer — summary, levels, RSI reports.]] - rationale - tests/test_market_analyzer.py
- [[Tests for market_chart — levels chart PNG generation.]] - rationale - tests/test_market_chart.py
- [[_handle_candle_pattern()]] - code - webhook/events.py
- [[_handle_ea_error()]] - code - webhook/events.py
- [[_handle_tf_snapshot()]] - code - webhook/events.py
- [[_handle_trade_close()]] - code - webhook/events.py
- [[_handle_trade_open()]] - code - webhook/events.py
- [[_price()]] - code - webhook/market_state.py
- [[candle_alert_message()]] - code - webhook/json_data_parser.py
- [[display_symbol()]] - code - webhook/json_data_parser.py
- [[display_time()]] - code - webhook/json_data_parser.py
- [[display_time()_1]] - code - webhook/market_state.py
- [[ea_issue_message()]] - code - webhook/messages.py
- [[events.py]] - code - webhook/events.py
- [[is_supported_payload()]] - code - webhook/json_data_parser.py
- [[json_data_parser.py]] - code - webhook/json_data_parser.py
- [[market_analyzer.py]] - code - webhook/market_analyzer.py
- [[market_chart.py]] - code - webhook/market_chart.py
- [[market_state.py]] - code - webhook/market_state.py
- [[notify_error()]] - code - webhook/events.py
- [[register_handler()]] - code - webhook/events.py
- [[signal_and_bias()]] - code - webhook/json_data_parser.py
- [[state.py]] - code - webhook/state.py
- [[test_market_analyzer.py]] - code - tests/test_market_analyzer.py
- [[test_market_chart.py]] - code - tests/test_market_chart.py
- [[trade_close_message()]] - code - webhook/messages.py
- [[trade_open_message()]] - code - webhook/messages.py
- [[validate_snapshot()]] - code - webhook/market_state.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Market_Analysis_Tests
SORT file.name ASC
```

## Connections to other communities
- 50 edges to [[_COMMUNITY_Server and Commands]]
- 9 edges to [[_COMMUNITY_Shared Test Fixtures]]
- 8 edges to [[_COMMUNITY_Market State and Levels]]
- 2 edges to [[_COMMUNITY_Telegram Test Utilities]]
- 1 edge to [[_COMMUNITY_Payload Formatting Tests]]
- 1 edge to [[_COMMUNITY_Webhook Dispatch Tests]]

## Top bridge nodes
- [[market_state.py]] - degree 17, connects to 3 communities
- [[state.py]] - degree 12, connects to 3 communities
- [[display_symbol()]] - degree 28, connects to 2 communities
- [[json_data_parser.py]] - degree 16, connects to 2 communities
- [[market_analyzer.py]] - degree 12, connects to 2 communities