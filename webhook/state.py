"""Shared global state used across webhook modules.

Cross-cutting state that doesn't naturally belong to any single module.
MARKET_STATE/ANALYZER/CHART are initialised here after their class definitions
are imported.
"""

from .market_analyzer import MarketAnalyzer
from .market_chart import MarketChart
from .market_state import MarketState

# Alert toggle — read/written by commands, read by event handlers
ALERTS_PAUSED = False

# Rolling signal history — appended by event handlers, read by /recent command
RECENT_SIGNALS: list = []

# Market data singletons
MARKET_STATE = MarketState()
MARKET_ANALYZER = MarketAnalyzer(MARKET_STATE)
MARKET_CHART = MarketChart(MARKET_STATE)


def alerts_paused():
    """Return whether automatic alerts are paused."""

    return ALERTS_PAUSED


def set_alerts_paused(paused):
    """Set the automatic-alert pause flag."""

    global ALERTS_PAUSED
    ALERTS_PAUSED = bool(paused)


def recent_signal_count():
    return len(RECENT_SIGNALS)


def recent_signals_for(symbol, limit=5):
    messages = [
        item["message"] for item in RECENT_SIGNALS if item["symbol"].upper() == symbol.upper()
    ]
    return messages[-limit:]


def add_recent_signal(symbol, message, limit=50):
    RECENT_SIGNALS.append({"symbol": symbol, "message": message})
    del RECENT_SIGNALS[:-limit]


def market_state():
    return MARKET_STATE


def market_analyzer():
    return MARKET_ANALYZER


def market_chart():
    return MARKET_CHART
