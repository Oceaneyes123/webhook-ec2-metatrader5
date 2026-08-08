"""Trade mode persistence and symbol override management."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .app_logger import get_logger
from .json_data_parser import display_symbol

logger = get_logger()


def trade_state_path():
    return Path(
        os.environ.get(
            "TRADE_STATE_FILE",
            Path(__file__).parent.parent / "trade_state.json",
        )
    )


def normalize_trade_mode(value):
    mode = str(value or "").strip().upper()
    return mode if mode in {"AUTO", "BUY", "SELL", "NOTRADE"} else "NOTRADE"


def normalize_trade_symbol(value):
    return display_symbol(value).upper()


def default_trade_state():
    return {
        "default_mode": "NOTRADE",
        "symbols": {},
        "overtrade_enabled": True,
        "overtrade_profit_target": 1.0,
        "key_level_orders_enabled": True,
        "ema_enabled": True,
        "updated_at": "",
    }


def load_trade_state():
    try:
        raw_state = json.loads(trade_state_path().read_text(encoding="utf-8"))
        if not isinstance(raw_state, dict):
            raise ValueError("trade state must be a JSON object")
        symbols = raw_state.get("symbols", {})
        if not isinstance(symbols, dict):
            symbols = {}
        return {
            "default_mode": normalize_trade_mode(raw_state.get("default_mode")),
            "symbols": {
                normalize_trade_symbol(symbol): normalize_trade_mode(mode)
                for symbol, mode in symbols.items()
                if normalize_trade_symbol(symbol)
            },
            "overtrade_enabled": _bool(raw_state.get("overtrade_enabled", True)),
            "overtrade_profit_target": _positive_float(
                raw_state.get("overtrade_profit_target", 1.0), 1.0
            ),
            "key_level_orders_enabled": _bool(
                raw_state.get("key_level_orders_enabled", True)
            ),
            "ema_enabled": _bool(raw_state.get("ema_enabled", True)),
            "updated_at": str(raw_state.get("updated_at", "")),
        }
    except FileNotFoundError:
        return default_trade_state()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        logger.warning("Ignoring invalid trade state file %s: %s", trade_state_path(), error)
        return default_trade_state()


def save_trade_state(state):
    target = trade_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(state, temporary, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def get_trade_mode(symbol=None):
    symbol = normalize_trade_symbol(symbol)
    if symbol and symbol in TRADE_STATE["symbols"]:
        return TRADE_STATE["symbols"][symbol]
    return normalize_trade_mode(TRADE_MODE)


def symbol_trade_modes():
    """Return a snapshot of symbol-specific trade-mode overrides."""

    return dict(TRADE_STATE["symbols"])


def set_trade_mode(mode, symbol=None):
    global TRADE_MODE

    mode = normalize_trade_mode(mode)
    symbol = normalize_trade_symbol(symbol)
    if symbol:
        TRADE_STATE["symbols"][symbol] = mode
    else:
        TRADE_MODE = mode
        TRADE_STATE["default_mode"] = mode
    save_trade_state(TRADE_STATE)
    return mode


def _positive_float(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def overtrade_config():
    return {
        "enabled": bool(TRADE_STATE.get("overtrade_enabled", True)),
        "profit_target": _positive_float(
            TRADE_STATE.get("overtrade_profit_target", 1.0), 1.0
        ),
    }


def set_overtrade_enabled(enabled):
    TRADE_STATE["overtrade_enabled"] = bool(enabled)
    save_trade_state(TRADE_STATE)
    return overtrade_config()


def set_overtrade_profit_target(profit_target):
    target = _positive_float(profit_target, 0.0)
    if target <= 0:
        raise ValueError("profit target must be greater than zero")
    TRADE_STATE["overtrade_profit_target"] = target
    save_trade_state(TRADE_STATE)
    return overtrade_config()


def key_level_orders_enabled():
    return _bool(TRADE_STATE.get("key_level_orders_enabled", True))


def set_key_level_orders_enabled(enabled):
    TRADE_STATE["key_level_orders_enabled"] = bool(enabled)
    save_trade_state(TRADE_STATE)
    return key_level_orders_enabled()


def ema_enabled():
    return _bool(TRADE_STATE.get("ema_enabled", True))


def set_ema_enabled(enabled):
    TRADE_STATE["ema_enabled"] = bool(enabled)
    save_trade_state(TRADE_STATE)
    return ema_enabled()


def trade_config(symbol=None):
    return {
        "mode": get_trade_mode(symbol),
        "lot_size": float(os.environ.get("TRADE_LOT_SIZE", "0.1")),
        "trail_pips": float(os.environ.get("TRAIL_PIPS", "20")),
        "key_level_orders_enabled": key_level_orders_enabled(),
    }


# Initialize trade state at module load time
TRADE_STATE = load_trade_state()
TRADE_MODE = TRADE_STATE["default_mode"]
