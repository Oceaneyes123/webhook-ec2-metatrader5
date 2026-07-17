//+------------------------------------------------------------------+
//| Webhook1 - market snapshots and alerts                           |
//+------------------------------------------------------------------+
// Webhook1 sends chart/history data for Python rendering.
#property strict
#property version "2.00"

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input bool PrintDebugLogs = true;
input int ChartHistoryBars = 200;
input double MaxBodyPercent = 35.0;
input double MinLongWickBodyRatio = 2.0;
input double MaxSmallWickBodyRatio = 1.0;
input double StrongCandleBodyPercent = 50.0;
input int LevelLookbackBars = 100;
input int SwingStrength = 2;
input int AtrPeriod = 14;
input double MinFvgAtrRatio = 0.25;
input int HeartbeatSeconds = 30;

#define TF_COUNT 6

ENUM_TIMEFRAMES Timeframes[TF_COUNT] =
{
   PERIOD_M1,
   PERIOD_M5,
   PERIOD_M15,
   PERIOD_M30,
   PERIOD_H1,
   PERIOD_H4
};

datetime lastBarTimes[TF_COUNT];
bool hasSnapshot[TF_COUNT];
int ema20Handles[TF_COUNT];
int ema50Handles[TF_COUNT];
int rsiHandles[TF_COUNT];

#include "includes/WebhookCommon.mqh"
#include "includes/MarketSnapshot.mqh"

int OnInit()
{
   if(ChartHistoryBars < 1
      || LevelLookbackBars < 10
      || SwingStrength < 1
      || AtrPeriod < 1
      || MinFvgAtrRatio < 0
      || HeartbeatSeconds < 10)
   {
      Print("Invalid market EA inputs.");
      SendMarketEaIssue(
         "Invalid EA inputs",
         "ChartHistoryBars/LevelLookbackBars/SwingStrength/AtrPeriod/MinFvgAtrRatio/HeartbeatSeconds"
      );
      return INIT_PARAMETERS_INCORRECT;
   }

   for(int index = 0; index < TF_COUNT; index++)
   {
      lastBarTimes[index] = 0;
      hasSnapshot[index] = false;
      ema20Handles[index] = iMA(
         _Symbol, Timeframes[index], 20, 0, MODE_EMA, PRICE_CLOSE
      );
      ema50Handles[index] = iMA(
         _Symbol, Timeframes[index], 50, 0, MODE_EMA, PRICE_CLOSE
      );
      rsiHandles[index] =
         iRSI(_Symbol, Timeframes[index], 14, PRICE_CLOSE);
      if(ema20Handles[index] == INVALID_HANDLE
         || ema50Handles[index] == INVALID_HANDLE
         || rsiHandles[index] == INVALID_HANDLE)
      {
         SendMarketEaIssue(
            "Failed to create indicator handles",
            TimeframeToText(Timeframes[index]),
            Timeframes[index]
         );
         return INIT_FAILED;
      }
   }

   Print("Webhook1 market EA started for ", _Symbol);
   EventSetTimer(HeartbeatSeconds);
   SendEaHeartbeat("webhook1");
   CheckAllTimeframes();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int index = 0; index < TF_COUNT; index++)
   {
      if(ema20Handles[index] != INVALID_HANDLE)
         IndicatorRelease(ema20Handles[index]);
      if(ema50Handles[index] != INVALID_HANDLE)
         IndicatorRelease(ema50Handles[index]);
      if(rsiHandles[index] != INVALID_HANDLE)
         IndicatorRelease(rsiHandles[index]);
   }
   Print("Webhook1 market EA stopped. Reason: ", reason);
}

void OnTick()
{
   CheckAllTimeframes();
}

void OnTimer()
{
   SendEaHeartbeat("webhook1");
}
