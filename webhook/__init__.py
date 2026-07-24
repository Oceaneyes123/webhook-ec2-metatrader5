"""webhook-ec2 — MT5 Telegram Webhook Trading Server."""

# ── Standalone utilities (no project deps) ──────────────────────────
from .app_logger import get_logger
from .json_data_parser import (
    SUPPORTED_EVENTS,
    candle_alert_message,
    display_symbol,
    display_time,
    engulfing_candle_message,
    is_supported_payload,
    signal_and_bias,
)

# ── Config (depends on app_logger) ─────────────────────────────────
from .config import (
    START_TIME,
    heartbeat_stale_seconds,
    load_dotenv,
    polling_interval,
    server_config,
    telegram_configured,
    uptime_text,
)

# ── Market state / analysis (standalone) ────────────────────────────
from .market_state import (
    CHART_CANDLE_LOOKBACK,
    DEFAULT_PATH,
    EMA_TIMEFRAMES,
    LEVEL_TIMEFRAMES,
    PATTERN_TIMEFRAMES,
    RSI_LOOKBACKS,
    RSI_TIMEFRAMES,
    TIMEFRAMES,
    MarketState,
    _price,
    display_time as market_state_display_time,
    validate_snapshot,
)
from .market_analyzer import MarketAnalyzer
from .market_chart import MarketChart

# ── Cross-cutting globals (depends on market_* modules) ─────────────
from .state import ALERTS_PAUSED, RECENT_SIGNALS, MARKET_STATE, MARKET_ANALYZER, MARKET_CHART

# ── Trade state (depends on json_data_parser) ──────────────────────
from .trade_state import (
    TRADE_STATE,
    TRADE_MODE,
    default_trade_state,
    get_trade_mode,
    load_trade_state,
    normalize_trade_mode,
    normalize_trade_symbol,
    save_trade_state,
    set_trade_mode,
    trade_config,
    trade_state_path,
)

# ── Heartbeat (depends on json_data_parser, config) ─────────────────
from .heartbeat import (
    EA_HEARTBEATS,
    HEARTBEAT_ALERT_STATES,
    _format_age,
    check_heartbeat_alerts,
    heartbeat_age_seconds,
    heartbeat_status_lines,
    record_ea_heartbeat,
    start_heartbeat_monitor,
)

# ── Message formatters (depends on config, json_data_parser) ───────
from .messages import (
    ea_issue_message,
    error_message,
    health_text,
    help_text,
    key_level_message,
    strong_rsi_message,
    trade_close_message,
    trade_open_message,
)

# ── Command / event registries ─────────────────────────────────────
from .commands import (
    COMMAND_HANDLERS,
    command_reply,
    is_telegram_update,
    register_command,
)
from .events import (
    EVENT_HANDLERS,
    register_handler,
)

# ── Polling (depends on commands, telegram_sender) ─────────────────
from .polling import (
    maybe_send_levels_chart,
    poll_telegram_forever,
    poll_telegram_once,
    reply_to_telegram_update,
    start_telegram_polling,
)

# ── HTTP server ────────────────────────────────────────────────────
from .server import WebhookHandler

# ── Telegram I/O (standalone except app_logger) ─────────────────────
from .telegram_sender import (
    get_telegram_updates,
    send_telegram_message,
    send_telegram_photo,
)

# ── MQ5 sync utility ───────────────────────────────────────────────
from . import sync_mq5  # module, not function
