//+------------------------------------------------------------------+
//| Webhook2 - trade management                                      |
//+------------------------------------------------------------------+
// Webhook2 does not send chart/history data.
#property strict
#property version "2.00"

#include <Trade/Trade.mqh>

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input bool PrintDebugLogs = true;
input long TradeMagicNumber = 260628;
input int EaIssueRepeatSeconds = 60;
input int TradeManageIntervalSeconds = 1;
input int HeartbeatSeconds = 30;
input int TradeConfigRefreshSeconds = 5;
input int TradeConfigMaxStaleSeconds = 30;

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
datetime lastHeartbeatTime = 0;

#include "includes/WebhookCommon.mqh"
#include "includes/TradeManager.mqh"

int OnInit()
{
   if(TradeManageIntervalSeconds < 1
      || HeartbeatSeconds < 10
      || HeartbeatSeconds < TradeManageIntervalSeconds
      || TradeConfigRefreshSeconds < 1
      || TradeConfigMaxStaleSeconds < TradeConfigRefreshSeconds)
   {
      Print("Invalid Webhook2 inputs.");
      SendEaIssue("Invalid Webhook2 inputs",
         "TradeManageIntervalSeconds/HeartbeatSeconds/TradeConfigRefreshSeconds/TradeConfigMaxStaleSeconds");
      return INIT_PARAMETERS_INCORRECT;
   }

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
   EventSetTimer(TradeManageIntervalSeconds);

   // Initialize position state to avoid phantom notifications on startup
   lastHadPosition = HasOpenPositionForSymbol();
   // Initialize manual position ticket tracker to avoid phantom notifications on startup
   lastManualPositionTickets = "";
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol)
      {
         long magic = (long)PositionGetInteger(POSITION_MAGIC);
         if(magic != TradeMagicNumber)
         {
            if(lastManualPositionTickets != "")
               lastManualPositionTickets += ",";
            lastManualPositionTickets += IntegerToString(ticket);
         }
      }
   }
   Print("Webhook2 trade EA started for ", _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
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
}

void OnTimer()
{
   ManageTrading();
   MaybeSendHeartbeat();
}

void MaybeSendHeartbeat()
{
   datetime now = TimeCurrent();
   if(now - lastHeartbeatTime >= HeartbeatSeconds)
   {
      SendEaHeartbeat("webhook2");
      lastHeartbeatTime = now;
   }
}
