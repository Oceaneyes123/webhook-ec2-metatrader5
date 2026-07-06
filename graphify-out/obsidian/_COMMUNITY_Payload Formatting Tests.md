---
type: community
cohesion: 0.06
members: 32
---

# Payload Formatting Tests

**Cohesion:** 0.06 - loosely connected
**Members:** 32 nodes

## Members
- [[.test_candle_message_adds_five_hours_and_rolls_date()]] - code - tests/test_json_data_parser.py
- [[.test_candle_message_escapes_dynamic_html()]] - code - tests/test_json_data_parser.py
- [[.test_candle_message_includes_ohlc_when_high_and_low_are_available()]] - code - tests/test_json_data_parser.py
- [[.test_candle_message_removes_broker_prefix_and_suffix_from_symbol()]] - code - tests/test_json_data_parser.py
- [[.test_candle_message_uses_timezone_offset_from_environment()]] - code - tests/test_json_data_parser.py
- [[.test_display_time_accepts_seconds()]] - code - tests/test_json_data_parser.py
- [[.test_display_time_returns_empty_for_none_or_blank()]] - code - tests/test_json_data_parser.py
- [[.test_display_time_returns_invalid_value_unchanged()]] - code - tests/test_json_data_parser.py
- [[.test_display_time_uses_default_offset_when_environment_is_invalid()]] - code - tests/test_json_data_parser.py
- [[.test_empty_symbol_returns_empty()]] - code - tests/test_json_data_parser.py
- [[.test_engulfing_candle_message_rejects_missing_fields()]] - code - tests/test_json_data_parser.py
- [[.test_engulfing_candle_message_uses_buy_format()]] - code - tests/test_json_data_parser.py
- [[.test_engulfing_candle_message_uses_sell_format()]] - code - tests/test_json_data_parser.py
- [[.test_fixed_bias_patterns_infer_signal_and_bias()]] - code - tests/test_json_data_parser.py
- [[.test_gold_aliases_normalize_to_gold()]] - code - tests/test_json_data_parser.py
- [[.test_hammer_message_uses_hammer_title()]] - code - tests/test_json_data_parser.py
- [[.test_heartbeat_is_supported()]] - code - tests/test_json_data_parser.py
- [[.test_inside_bar_breakout_uses_payload_signal()]] - code - tests/test_json_data_parser.py
- [[.test_is_supported_payload_accepts_alert_events()]] - code - tests/test_json_data_parser.py
- [[.test_trade_close_is_supported()]] - code - tests/test_json_data_parser.py
- [[.test_unknown_symbol_falls_back_safely()]] - code - tests/test_json_data_parser.py
- [[.test_xauusd_normalizes_to_gold()]] - code - tests/test_json_data_parser.py
- [[CandleAlertMessageTest]] - code - tests/test_json_data_parser.py
- [[DisplayTimeTest]] - code - tests/test_json_data_parser.py
- [[Message formatting for candlepattern alerts.]] - rationale - tests/test_json_data_parser.py
- [[Payload event-type filtering.]] - rationale - tests/test_json_data_parser.py
- [[SupportedPayloadTest]] - code - tests/test_json_data_parser.py
- [[Symbol normalisation.]] - rationale - tests/test_json_data_parser.py
- [[SymbolAliasTest]] - code - tests/test_json_data_parser.py
- [[Tests for json_data_parser — candle messages, symbol aliases, display time.]] - rationale - tests/test_json_data_parser.py
- [[Timezone offset display formatting.]] - rationale - tests/test_json_data_parser.py
- [[test_json_data_parser.py]] - code - tests/test_json_data_parser.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Payload_Formatting_Tests
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Market Analysis Tests]]

## Top bridge nodes
- [[test_json_data_parser.py]] - degree 6, connects to 1 community