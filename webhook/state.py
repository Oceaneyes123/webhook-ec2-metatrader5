"""Shared global state used across webhook modules.

Cross-cutting state that doesn't naturally belong to any single module.
MARKET_STATE/ANALYZER/CHART are initialised here after their class definitions
are imported.
"""

from .market_state import MarketState
from .market_analyzer import MarketAnalyzer
from .market_chart import MarketChart

# Alert toggle — read/written by commands, read by event handlers
ALERTS_PAUSED = False

# Rolling signal history — appended by event handlers, read by /recent command
RECENT_SIGNALS: list = []

# Market data singletons
MARKET_STATE = MarketState()
MARKET_ANALYZER = MarketAnalyzer(MARKET_STATE)
MARKET_CHART = MarketChart(MARKET_STATE)
