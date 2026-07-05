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
    return mode if mode in {"BUY", "SELL", "NOTRADE"} else "NOTRADE"


def normalize_trade_symbol(value):
    return display_symbol(value).upper()


def default_trade_state():
    return {"default_mode": "NOTRADE", "symbols": {}, "updated_at": ""}


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


def trade_config(symbol=None):
    return {
        "mode": get_trade_mode(symbol),
        "lot_size": float(os.environ.get("TRADE_LOT_SIZE", "0.2")),
        "trail_pips": float(os.environ.get("TRAIL_PIPS", "20")),
    }


# Initialize trade state at module load time
TRADE_STATE = load_trade_state()
TRADE_MODE = TRADE_STATE["default_mode"]
