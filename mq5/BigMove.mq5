//+------------------------------------------------------------------+
//| BigMove - M15 range alerts relative to the current D1 ATR       |
//+------------------------------------------------------------------+
#property strict
#property version "1.00"

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input int AtrPeriod = 14;
input double BigMoveAtrPercent = 25.0;

#include "includes/WebhookCommon.mqh"

int dailyAtrHandle = INVALID_HANDLE;
datetime lastClosedM15Bar = 0;

int OnInit()
{
   if(AtrPeriod < 1 || BigMoveAtrPercent <= 0)
      return INIT_PARAMETERS_INCORRECT;

   dailyAtrHandle = iATR(_Symbol, PERIOD_D1, AtrPeriod);
   if(dailyAtrHandle == INVALID_HANDLE)
      return INIT_FAILED;

   lastClosedM15Bar = iTime(_Symbol, PERIOD_M15, 1);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(dailyAtrHandle != INVALID_HANDLE)
      IndicatorRelease(dailyAtrHandle);
}

void OnTick()
{
   datetime candleTime = iTime(_Symbol, PERIOD_M15, 1);
   if(candleTime <= 0 || candleTime == lastClosedM15Bar)
      return;

   double atr[];
   if(CopyBuffer(dailyAtrHandle, 0, 0, 1, atr) != 1 || atr[0] <= 0)
      return;

   Candle candle = ReadCandle(PERIOD_M15, 1);
   double range = CandleRange(candle);
   double threshold = atr[0] * BigMoveAtrPercent / 100.0;
   lastClosedM15Bar = candleTime;
   if(range < threshold)
      return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   SendWebhook(
      "{\"event_type\":\"BIG_MOVE\",\"source\":\"bigmove\""
      + ",\"symbol\":\"" + JsonEscape(_Symbol) + "\""
      + ",\"timeframe\":\"M15\""
      + ",\"candle_time\":\"" + JsonEscape(DateTimeToText(candleTime)) + "\""
      + ",\"open\":" + DoubleToString(candle.open, digits)
      + ",\"high\":" + DoubleToString(candle.high, digits)
      + ",\"low\":" + DoubleToString(candle.low, digits)
      + ",\"close\":" + DoubleToString(candle.close, digits)
      + ",\"range\":" + DoubleToString(range, digits)
      + ",\"daily_atr\":" + DoubleToString(atr[0], digits)
      + ",\"threshold\":" + DoubleToString(threshold, digits)
      + ",\"atr_percent\":" + DoubleToString(BigMoveAtrPercent, 2) + "}"
   );
}
