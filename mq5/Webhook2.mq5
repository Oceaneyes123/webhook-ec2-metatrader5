//+------------------------------------------------------------------+
//| Webhook2 - trade management                                      |
//+------------------------------------------------------------------+
#property strict
#property version "2.00"

#include <Trade/Trade.mqh>

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input bool PrintDebugLogs = true;
input long TradeMagicNumber = 260628;
input int EaIssueRepeatSeconds = 60;

#define TRADE_TF_COUNT 3

ENUM_TIMEFRAMES Timeframes[TRADE_TF_COUNT] =
{
   PERIOD_M1,
   PERIOD_M5,
   PERIOD_M15
};

int ema20Handles[TRADE_TF_COUNT];
int ema50Handles[TRADE_TF_COUNT];
CTrade trade;
string lastEaIssueKey = "";
datetime lastEaIssueTime = 0;

#include "includes/WebhookCommon.mqh"
#include "includes/TradeManager.mqh"

int OnInit()
{
   for(int index = 0; index < TRADE_TF_COUNT; index++)
   {
      ema20Handles[index] = iMA(
         _Symbol, Timeframes[index], 20, 0, MODE_EMA, PRICE_CLOSE
      );
      ema50Handles[index] = iMA(
         _Symbol, Timeframes[index], 50, 0, MODE_EMA, PRICE_CLOSE
      );
      if(ema20Handles[index] == INVALID_HANDLE
         || ema50Handles[index] == INVALID_HANDLE)
      {
         SendEaIssue(
            "Failed to create indicator handles",
            TimeframeToText(Timeframes[index]),
            Timeframes[index]
         );
         return INIT_FAILED;
      }
   }

   trade.SetExpertMagicNumber(TradeMagicNumber);
   Print("Webhook2 trade EA started for ", _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   for(int index = 0; index < TRADE_TF_COUNT; index++)
   {
      if(ema20Handles[index] != INVALID_HANDLE)
         IndicatorRelease(ema20Handles[index]);
      if(ema50Handles[index] != INVALID_HANDLE)
         IndicatorRelease(ema50Handles[index]);
   }
   Print("Webhook2 trade EA stopped. Reason: ", reason);
}

void OnTick()
{
   ManageTrading();
}
