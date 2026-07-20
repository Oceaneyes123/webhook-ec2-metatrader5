//+------------------------------------------------------------------+
//| BigMove - candle range alerts relative to the current D1 ATR    |
//+------------------------------------------------------------------+
#property strict
#property version "1.00"

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input int AtrPeriod = 14;

#include "includes/WebhookCommon.mqh"

#define TIMEFRAME_COUNT 5

int dailyAtrHandle = INVALID_HANDLE;
ENUM_TIMEFRAMES timeframes[TIMEFRAME_COUNT] =
   {PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H2, PERIOD_H4};
double atrPercents[TIMEFRAME_COUNT] = {16.0, 22.0, 32.5, 42.5, 60.0};
datetime lastClosedBars[TIMEFRAME_COUNT];

string TimeframeName(const ENUM_TIMEFRAMES timeframe)
{
   switch(timeframe)
   {
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H2:  return "H2";
      case PERIOD_H4:  return "H4";
   }
   return "";
}

void SendBigMove(const ENUM_TIMEFRAMES timeframe, const datetime candleTime,
                 const Candle &candle, const double range, const double atr,
                 const double atrPercent)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double threshold = atr * atrPercent / 100.0;
   SendWebhook(
      "{\"event_type\":\"BIG_MOVE\",\"source\":\"bigmove\""
      + ",\"symbol\":\"" + JsonEscape(_Symbol) + "\""
      + ",\"timeframe\":\"" + TimeframeName(timeframe) + "\""
      + ",\"candle_time\":\"" + JsonEscape(DateTimeToText(candleTime)) + "\""
      + ",\"open\":" + DoubleToString(candle.open, digits)
      + ",\"high\":" + DoubleToString(candle.high, digits)
      + ",\"low\":" + DoubleToString(candle.low, digits)
      + ",\"close\":" + DoubleToString(candle.close, digits)
      + ",\"range\":" + DoubleToString(range, digits)
      + ",\"daily_atr\":" + DoubleToString(atr, digits)
      + ",\"threshold\":" + DoubleToString(threshold, digits)
      + ",\"atr_percent\":" + DoubleToString(atrPercent, 2) + "}"
   );
}

int OnInit()
{
   if(AtrPeriod < 1)
      return INIT_PARAMETERS_INCORRECT;

   dailyAtrHandle = iATR(_Symbol, PERIOD_D1, AtrPeriod);
   if(dailyAtrHandle == INVALID_HANDLE)
      return INIT_FAILED;

   for(int i = 0; i < TIMEFRAME_COUNT; i++)
      lastClosedBars[i] = iTime(_Symbol, timeframes[i], 2);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(dailyAtrHandle != INVALID_HANDLE)
      IndicatorRelease(dailyAtrHandle);
}

void OnTick()
{
   double atr[];
   if(CopyBuffer(dailyAtrHandle, 0, 0, 1, atr) != 1 || atr[0] <= 0)
      return;

   for(int i = 0; i < TIMEFRAME_COUNT; i++)
   {
      datetime candleTime = iTime(_Symbol, timeframes[i], 1);
      if(candleTime <= 0 || candleTime == lastClosedBars[i])
         continue;

      Candle candle = ReadCandle(timeframes[i], 1);
      double range = CandleRange(candle);
      double threshold = atr[0] * atrPercents[i] / 100.0;
      lastClosedBars[i] = candleTime;
      if(range >= threshold)
         SendBigMove(timeframes[i], candleTime, candle, range, atr[0], atrPercents[i]);
   }
}
