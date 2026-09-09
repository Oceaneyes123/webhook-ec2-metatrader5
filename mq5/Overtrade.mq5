//+------------------------------------------------------------------+
//|                                      OvertradingController.mq5   |
//| Closes all chart-symbol positions when count and profit targets  |
//| are reached.                                                     |
//+------------------------------------------------------------------+
#property copyright ""
#property link      ""
#property version   "1.02"
#property strict

#include <Trade/Trade.mqh>

CTrade trade;

//--- Settings
input string   WebhookUrl              = "http://127.0.0.1:8000/webhook";
input int      WebRequestTimeoutMs     = 5000;
input bool     PrintDebugLogs          = true;
input int      HeartbeatSeconds        = 30;
input int      OvertradeConfigRefreshSeconds = 5;
input int      MinimumOpenPositions = 3;
input double   ProfitTargetUSD      = 1.00;
input int      CheckIntervalSeconds = 1;
input ulong    CloseDeviationPoints = 20;

datetime lastHeartbeatTime = 0;
datetime lastOvertradeConfigTime = 0;
bool overtradeSecurityEnabled = true;
double activeProfitTargetUSD = 0.0;

#include "includes/WebhookCommon.mqh"

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   if(MinimumOpenPositions < 1 || HeartbeatSeconds < 10 ||
      OvertradeConfigRefreshSeconds < 1)
   {
      Print("MinimumOpenPositions must be at least 1 and HeartbeatSeconds at least 10.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(ProfitTargetUSD <= 0.0)
   {
      Print("ProfitTargetUSD must be greater than zero.");
      return INIT_PARAMETERS_INCORRECT;
   }

   trade.SetDeviationInPoints(CloseDeviationPoints);
   trade.SetAsyncMode(false);
   activeProfitTargetUSD = ProfitTargetUSD;
   RefreshOvertradeConfig();

   int interval = CheckIntervalSeconds;

   if(interval < 1)
      interval = 1;

   EventSetTimer(interval);
   SendEaHeartbeat("overtrade");
   lastHeartbeatTime = TimeCurrent();

   Print("Overtrading Controller started for ", _Symbol);
   Print("It will close all ", _Symbol,
         " positions when there are at least ",
         MinimumOpenPositions,
         " positions with combined profit of $",
          DoubleToString(activeProfitTargetUSD, 2),
         " or more.");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//+------------------------------------------------------------------+
//| Tick event                                                       |
//+------------------------------------------------------------------+
void OnTick()
{
   CheckOvertradingLimit();
}

//+------------------------------------------------------------------+
//| Timer event                                                      |
//+------------------------------------------------------------------+
void OnTimer()
{
   RefreshOvertradeConfig();
   CheckOvertradingLimit();
   MaybeSendHeartbeat();
}

//+------------------------------------------------------------------+
//| Refresh remotely controlled enablement and profit target         |
//+------------------------------------------------------------------+
void RefreshOvertradeConfig()
{
   datetime now = TimeCurrent();
   if(lastOvertradeConfigTime != 0 &&
      now - lastOvertradeConfigTime < OvertradeConfigRefreshSeconds)
   {
      return;
   }
   lastOvertradeConfigTime = now;

   string configUrl = WebhookUrl;
   if(StringReplace(configUrl, "/webhook", "/overtrade-config") == 0)
   {
      Print("Overtrade config URL could not be derived from WebhookUrl.");
      return;
   }

   char request[];
   ArrayResize(request, 0);
   char response[];
   string responseHeaders;
   ResetLastError();
   int responseCode = WebRequest(
      "GET", configUrl, "Accept: application/json\r\n", WebRequestTimeoutMs,
      request, response, responseHeaders
   );

   if(responseCode < 200 || responseCode >= 300)
   {
      Print("Unable to refresh overtrade config. HTTP=", responseCode,
            " error=", GetLastError());
      return;
   }

   string body = CharArrayToString(response, 0, -1, CP_UTF8);
   int enabledStart = StringFind(body, "\"enabled\":");
   int targetStart = StringFind(body, "\"profit_target\":");
   if(enabledStart < 0 || targetStart < 0)
   {
      Print("Invalid overtrade config response: ", body);
      return;
   }

   enabledStart += StringLen("\"enabled\":");
   targetStart += StringLen("\"profit_target\":");
   int targetEnd = StringFind(body, ",", targetStart);
   if(targetEnd < 0)
      targetEnd = StringFind(body, "}", targetStart);
   if(targetEnd < 0)
      return;

   double target = StringToDouble(StringSubstr(body, targetStart, targetEnd - targetStart));
   if(target <= 0.0)
      return;

   overtradeSecurityEnabled = StringSubstr(body, enabledStart, 4) == "true";
   activeProfitTargetUSD = target;
}

//+------------------------------------------------------------------+
//| Send health updates without slowing position monitoring          |
//+------------------------------------------------------------------+
void MaybeSendHeartbeat()
{
   MaybeSendEaHeartbeat("overtrade", HeartbeatSeconds, lastHeartbeatTime);
}

//+------------------------------------------------------------------+
//| Count positions and calculate profit for current symbol          |
//+------------------------------------------------------------------+
void GetSymbolPositionData(int &positionCount, double &totalProfit)
{
   positionCount = 0;
   totalProfit   = 0.0;

   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);

      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);

      if(symbol != _Symbol)
         continue;

      positionCount++;

      // POSITION_PROFIT only; swap and commission are not added.
      totalProfit += PositionGetDouble(POSITION_PROFIT);
   }
}

//+------------------------------------------------------------------+
//| Check whether all current-symbol positions should be closed      |
//+------------------------------------------------------------------+
void CheckOvertradingLimit()
{
   static bool isClosing = false;

   if(isClosing)
      return;

   if(!overtradeSecurityEnabled)
      return;

   int positionCount;
   double totalProfit;

   GetSymbolPositionData(positionCount, totalProfit);

   if(positionCount < MinimumOpenPositions)
      return;

   if(totalProfit < activeProfitTargetUSD)
      return;

   isClosing = true;

   Print("Overtrading limit triggered for ", _Symbol,
         ". Positions: ", positionCount,
         ", combined profit: $",
         DoubleToString(totalProfit, 2));

   CloseAllSymbolPositions();

   isClosing = false;
}

//+------------------------------------------------------------------+
//| Close every open position for the current chart symbol           |
//+------------------------------------------------------------------+
void CloseAllSymbolPositions()
{
   bool allClosed = true;

   // Multiple passes help when the position list changes after closing.
   for(int pass = 0; pass < 3; pass++)
   {
      bool foundPosition = false;

      for(int index = PositionsTotal() - 1; index >= 0; index--)
      {
         ulong ticket = PositionGetTicket(index);

         if(ticket == 0)
            continue;

         if(!PositionSelectByTicket(ticket))
            continue;

         string symbol = PositionGetString(POSITION_SYMBOL);

         if(symbol != _Symbol)
            continue;

         foundPosition = true;

         ResetLastError();

         if(!trade.PositionClose(ticket))
         {
            allClosed = false;

            Print("Failed to close position #", ticket,
                  ". Retcode: ", trade.ResultRetcode(),
                  " - ", trade.ResultRetcodeDescription(),
                  ". Error: ", GetLastError());
         }
         else
         {
            Print("Closed position #", ticket,
                  " for ", _Symbol);
         }
      }

      if(!foundPosition)
         break;
   }

   int remainingPositions;
   double remainingProfit;

   GetSymbolPositionData(remainingPositions, remainingProfit);

   if(remainingPositions == 0)
   {
      Print("All ", _Symbol, " positions were closed successfully.");
   }
   else
   {
      Print("Warning: ", remainingPositions,
            " ", _Symbol,
            " position(s) remain open.");

      allClosed = false;
   }

   // Trading is immediately allowed again because the EA does not
   // create a cooldown or permanent trading lock.
}
