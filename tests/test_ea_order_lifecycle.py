from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EMA = (ROOT / "mq5" / "EMA.mq5").read_text(encoding="utf-8")
MANAGER = (ROOT / "mq5" / "includes" / "TradeManager.mqh").read_text(encoding="utf-8")


def block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_webhook2_keeps_same_direction_pending_order():
    buy = block(MANAGER, 'if(config.mode == "BUY")', 'if(config.mode == "SELL")')
    sell = block(MANAGER, 'if(config.mode == "SELL")', 'if(config.mode == "AUTO")')

    assert "DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);" not in buy
    assert "DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);" in buy
    assert "DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);" not in sell
    assert "DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);" in sell


def test_webhook2_pause_mode_preserves_pending_orders():
    no_trade = block(MANAGER, 'if(config.mode == "NOTRADE")', 'SendEaIssue("Unknown trade mode"')
    assert "DeletePendingOrders" not in no_trade


def test_webhook2_validates_limits_against_executable_market_side():
    assert "bid - minimumDistance" in MANAGER
    assert "ask + minimumDistance" in MANAGER
    assert "SYMBOL_TRADE_FREEZE_LEVEL" in MANAGER
    assert "MathCeil" in MANAGER
    assert "MathFloor(targetPrice / tick)" in MANAGER
    assert "MathCeil(targetPrice / tick)" in MANAGER


def test_webhook2_modification_preserves_existing_sl_and_tp():
    trail = block(MANAGER, "void TrailPendingOrder", "void ProcessKeyLevelPendingOrder")
    assert "double currentStopLoss = OrderGetDouble(ORDER_SL)" in trail
    assert "double currentTakeProfit = OrderGetDouble(ORDER_TP)" in trail
    assert "ticket, targetPrice, currentStopLoss, currentTakeProfit" in trail


def test_webhook2_backs_off_after_rejected_order():
    assert "PendingRetrySeconds" in MANAGER
    assert "pendingRetryUntil" in MANAGER
    assert re.search(r"pendingRetryUntil\s*=\s*TimeCurrent\(\)\s*\+\s*PendingRetrySeconds", MANAGER)
    assert "OrderModify failed; retry delayed" in MANAGER


def test_ema_keeps_pending_order_on_soft_signal_invalidation():
    assert "CancelPendingIfSignalInvalid" not in EMA
    stoch = block(EMA, "void ProcessM5StochRSILocks()", "//+------------------------------------------------------------------+\n//| Pending entry calculation")
    assert "DeleteManagedPendingOrder" not in stoch
    tick_invalidation = block(EMA, "bool hasPending =", "datetime currentM1BarTime")
    assert "DeleteManagedPendingOrder" not in tick_invalidation


def test_ema_validates_limits_against_executable_market_side():
    calculation = block(EMA, "double CalculatePendingEntry", "bool IsPendingCooldownActive")
    assert "bid - minDistance" in calculation
    assert "ask + minDistance" in calculation
    assert "SYMBOL_TRADE_FREEZE_LEVEL" in EMA
    assert "MathCeil" in EMA
    assert "MathFloor(entry / tick)" in calculation
    assert "MathCeil(entry / tick)" in calculation
    assert "normalizedEntry > bid - minDistance" in calculation
    assert "normalizedEntry < ask + minDistance" in calculation


def test_ema_backs_off_after_rejected_order():
    assert "OrderRetrySeconds" in EMA
    assert "pendingRetryUntil" in EMA
    assert re.search(r"pendingRetryUntil\s*=\s*TimeCurrent\(\)\s*\+\s*OrderRetrySeconds", EMA)
