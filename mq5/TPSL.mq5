//+------------------------------------------------------------------+
//|                                           ATR_EMA_TPSL_Manager.mq5 |
//|       Adds M15 ATR TP, EMA-based SL, and breakeven management      |
//+------------------------------------------------------------------+
#property copyright ""
#property link      ""
#property version   "1.03"
#property strict

#include <Trade/Trade.mqh>

CTrade trade;

input string   WebhookUrl              = "http://127.0.0.1:8000/webhook";
input int      WebRequestTimeoutMs     = 5000;
input bool     PrintDebugLogs          = true;
input int      HeartbeatSeconds        = 30;
input int      M15AtrPeriod            = 14;
input int      M15EmaPeriod            = 200;
input int      EmaStopBufferPips       = 20;
input int      MaximumStopLossPips     = 80;
input int      PendingTakeProfitPips   = 100;
input int      PendingStopLossPips     = 100;
input bool     ManageCurrentSymbolOnly = true;
input bool     OnlySetIfMissing        = true;
input ulong    MagicNumberFilter       = 0;   // 0 = manage all magic numbers
input int      TimerSeconds            = 1;

// Breakeven settings
input bool     UseBreakeven            = true;
input int      BreakevenTriggerPips    = 50;  // Move SL when price is 50 pips in profit
input int      BreakevenOffsetPips     = 10;   // Near breakeven, small profit lock

datetime lastHeartbeatTime = 0;

#include "includes/WebhookCommon.mqh"

//+------------------------------------------------------------------+
//| Convert pips to price distance                                   |
//+------------------------------------------------------------------+
double PipSize(const string symbol)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);

   if(point <= 0.0)
      point = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);

   if(digits == 5 || digits == 3)
      return point * 10.0;

   if(digits == 2)
      return point * 10.0;

   return point;
}

//+------------------------------------------------------------------+
//| Normalize price to symbol digits                                 |
//+------------------------------------------------------------------+
double NormalizeSymbolPrice(const string symbol, double price)
{
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
}

//+------------------------------------------------------------------+
//| Read the current M15 ATR value                                  |
//+------------------------------------------------------------------+
bool GetM15Atr(const string symbol, double &atr)
{
   atr = 0.0;
   int handle = iATR(symbol, PERIOD_M15, M15AtrPeriod);

   if(handle == INVALID_HANDLE)
      return false;

   double values[];
   int copied = CopyBuffer(handle, 0, 0, 1, values);
   IndicatorRelease(handle);

   if(copied != 1 || values[0] <= 0.0)
      return false;

   atr = values[0];
   return true;
}

//+------------------------------------------------------------------+
//| Read the current M15 EMA value                                  |
//+------------------------------------------------------------------+
bool GetM15Ema(const string symbol, double &ema)
{
   ema = 0.0;
   int handle = iMA(symbol, PERIOD_M15, M15EmaPeriod, 0, MODE_EMA, PRICE_CLOSE);

   if(handle == INVALID_HANDLE)
      return false;

   double values[];
   int copied = CopyBuffer(handle, 0, 0, 1, values);
   IndicatorRelease(handle);

   if(copied != 1 || values[0] <= 0.0)
      return false;

   ema = values[0];
   return true;
}

//+------------------------------------------------------------------+
//| Build TP at 1x M15 ATR and the nearest valid requested SL       |
//+------------------------------------------------------------------+
bool GetDefaultProtection(
   const string symbol,
   const long type,
   const double openPrice,
   const double pip,
   double &sl,
   double &tp
)
{
   double atr = 0.0;
   double ema = 0.0;

   if(!GetM15Atr(symbol, atr) || !GetM15Ema(symbol, ema))
      return false;

   double maximumStopDistance = MaximumStopLossPips * pip;

   if(type == POSITION_TYPE_BUY)
   {
      double emaStop = ema - EmaStopBufferPips * pip;
      // An SL must remain below a buy entry; otherwise use the 80-pip cap.
      sl = emaStop < openPrice && openPrice - emaStop < maximumStopDistance
         ? emaStop
         : openPrice - maximumStopDistance;
      tp = openPrice + atr;
   }
   else if(type == POSITION_TYPE_SELL)
   {
      double emaStop = ema + EmaStopBufferPips * pip;
      // An SL must remain above a sell entry; otherwise use the 80-pip cap.
      sl = emaStop > openPrice && emaStop - openPrice < maximumStopDistance
         ? emaStop
         : openPrice + maximumStopDistance;
      tp = openPrice - atr;
   }
   else
   {
      return false;
   }

   sl = NormalizeSymbolPrice(symbol, sl);
   tp = NormalizeSymbolPrice(symbol, tp);
   return true;
}

//+------------------------------------------------------------------+
//| Check whether a filled pending order still has its 100-pip exits |
//+------------------------------------------------------------------+
bool HasFixedPendingProtection(
   const string symbol,
   const long type,
   const double openPrice,
   const double currentSL,
   const double currentTP,
   const double pip
)
{
   double expectedSL = 0.0;
   double expectedTP = 0.0;

   if(type == POSITION_TYPE_BUY)
   {
      expectedSL = openPrice - PendingStopLossPips * pip;
      expectedTP = openPrice + PendingTakeProfitPips * pip;
   }
   else if(type == POSITION_TYPE_SELL)
   {
      expectedSL = openPrice + PendingStopLossPips * pip;
      expectedTP = openPrice - PendingTakeProfitPips * pip;
   }
   else
   {
      return false;
   }

   return NormalizeSymbolPrice(symbol, currentSL) == NormalizeSymbolPrice(symbol, expectedSL)
      && NormalizeSymbolPrice(symbol, currentTP) == NormalizeSymbolPrice(symbol, expectedTP);
}

//+------------------------------------------------------------------+
//| Check if the EA should manage this symbol/magic                  |
//+------------------------------------------------------------------+
bool ShouldManage(const string symbol, const ulong magic)
{
   if(ManageCurrentSymbolOnly && symbol != _Symbol)
      return false;

   if(MagicNumberFilter != 0 && magic != MagicNumberFilter)
      return false;

   return true;
}

//+------------------------------------------------------------------+
//| Get breakeven SL if trigger is reached                           |
//+------------------------------------------------------------------+
bool GetBreakevenSL(
   const string symbol,
   const long type,
   const double openPrice,
   const double currentSL,
   const double pip,
   double &breakevenSL
)
{
   if(!UseBreakeven)
      return false;

   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

   if(bid <= 0.0 || ask <= 0.0)
      return false;

   double triggerDistance = BreakevenTriggerPips * pip;
   double offsetDistance  = BreakevenOffsetPips * pip;

   if(type == POSITION_TYPE_BUY)
   {
      double profitDistance = bid - openPrice;

      if(profitDistance < triggerDistance)
         return false;

      breakevenSL = NormalizeSymbolPrice(symbol, openPrice + offsetDistance);

      if(currentSL > 0.0 && currentSL >= breakevenSL)
         return false;

      return true;
   }

   if(type == POSITION_TYPE_SELL)
   {
      double profitDistance = openPrice - ask;

      if(profitDistance < triggerDistance)
         return false;

      breakevenSL = NormalizeSymbolPrice(symbol, openPrice - offsetDistance);

      if(currentSL > 0.0 && currentSL <= breakevenSL)
         return false;

      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Manage open market positions                                     |
//+------------------------------------------------------------------+
void ManagePositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0)
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      ulong magic   = (ulong)PositionGetInteger(POSITION_MAGIC);

      if(!ShouldManage(symbol, magic))
         continue;

      long type        = PositionGetInteger(POSITION_TYPE);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      double pip       = PipSize(symbol);

      double sl = currentSL;
      double tp = currentTP;

      double defaultSL = 0.0;
      double defaultTP = 0.0;

      if(!GetDefaultProtection(symbol, type, openPrice, pip, defaultSL, defaultTP))
      {
         Print("Unable to calculate M15 ATR/EMA protection for position #", ticket,
               " symbol=", symbol);
         continue;
      }

      if(OnlySetIfMissing)
      {
         if(HasFixedPendingProtection(symbol, type, openPrice, currentSL, currentTP, pip))
         {
            // A filled pending order inherits its 100-pip exits. Replace both
            // with the current ATR/EMA confluence exactly after it becomes a position.
            sl = defaultSL;
            tp = defaultTP;
         }
         else
         {
            if(currentSL <= 0.0)
               sl = defaultSL;

            if(currentTP <= 0.0)
               tp = defaultTP;
         }
      }
      else
      {
         sl = defaultSL;
         tp = defaultTP;
      }

      double breakevenSL = 0.0;

      if(GetBreakevenSL(symbol, type, openPrice, currentSL, pip, breakevenSL))
         sl = breakevenSL;

      sl = NormalizeSymbolPrice(symbol, sl);
      tp = NormalizeSymbolPrice(symbol, tp);

      bool slChanged = NormalizeSymbolPrice(symbol, currentSL) != sl;
      bool tpChanged = NormalizeSymbolPrice(symbol, currentTP) != tp;

      if(!slChanged && !tpChanged)
         continue;

      if(!trade.PositionModify(ticket, sl, tp))
      {
         Print("Failed to modify position #", ticket,
               " symbol=", symbol,
               " retcode=", trade.ResultRetcode(),
               " desc=", trade.ResultRetcodeDescription());
      }
      else
      {
         Print("Updated position #", ticket,
               " symbol=", symbol,
               " SL=", DoubleToString(sl, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
               " TP=", DoubleToString(tp, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
      }
   }
}

//+------------------------------------------------------------------+
//| Manage pending orders                                            |
//+------------------------------------------------------------------+
void ManageOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);

      if(ticket == 0)
         continue;

      string symbol = OrderGetString(ORDER_SYMBOL);
      ulong magic   = (ulong)OrderGetInteger(ORDER_MAGIC);

      if(!ShouldManage(symbol, magic))
         continue;

      ENUM_ORDER_TYPE type = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);

      if(type != ORDER_TYPE_BUY_LIMIT       &&
         type != ORDER_TYPE_SELL_LIMIT      &&
         type != ORDER_TYPE_BUY_STOP        &&
         type != ORDER_TYPE_SELL_STOP       &&
         type != ORDER_TYPE_BUY_STOP_LIMIT  &&
         type != ORDER_TYPE_SELL_STOP_LIMIT)
      {
         continue;
      }

      double openPrice = OrderGetDouble(ORDER_PRICE_OPEN);
      double currentSL = OrderGetDouble(ORDER_SL);
      double currentTP = OrderGetDouble(ORDER_TP);
      double pip       = PipSize(symbol);

      double sl = 0.0;
      double tp = 0.0;

      bool isBuyOrder =
         type == ORDER_TYPE_BUY_LIMIT ||
         type == ORDER_TYPE_BUY_STOP ||
         type == ORDER_TYPE_BUY_STOP_LIMIT;

      if(isBuyOrder)
      {
         sl = openPrice - PendingStopLossPips * pip;
         tp = openPrice + PendingTakeProfitPips * pip;
      }
      else
      {
         sl = openPrice + PendingStopLossPips * pip;
         tp = openPrice - PendingTakeProfitPips * pip;
      }

      sl = NormalizeSymbolPrice(symbol, sl);
      tp = NormalizeSymbolPrice(symbol, tp);

      if(OnlySetIfMissing)
      {
         if(currentSL > 0.0)
            sl = currentSL;

         if(currentTP > 0.0)
            tp = currentTP;

         if(currentSL > 0.0 && currentTP > 0.0)
            continue;
      }

      ENUM_ORDER_TYPE_TIME typeTime = (ENUM_ORDER_TYPE_TIME)OrderGetInteger(ORDER_TYPE_TIME);
      datetime expiration          = (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION);
      double stopLimit             = OrderGetDouble(ORDER_PRICE_STOPLIMIT);

      if(!trade.OrderModify(ticket, openPrice, sl, tp, typeTime, expiration, stopLimit))
      {
         Print("Failed to modify order #", ticket,
               " symbol=", symbol,
               " retcode=", trade.ResultRetcode(),
               " desc=", trade.ResultRetcodeDescription());
      }
      else
      {
         Print("Updated order #", ticket,
               " symbol=", symbol,
               " SL=", DoubleToString(sl, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
               " TP=", DoubleToString(tp, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)));
      }
   }
}

//+------------------------------------------------------------------+
//| Manage all positions and orders                                  |
//+------------------------------------------------------------------+
void ManageAll()
{
   ManagePositions();
   ManageOrders();
}

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   if(TimerSeconds < 1 || HeartbeatSeconds < 10 || M15AtrPeriod < 1 ||
      M15EmaPeriod < 1 || EmaStopBufferPips < 0 || MaximumStopLossPips <= 0 ||
      PendingTakeProfitPips <= 0 || PendingStopLossPips <= 0)
   {
      Print("Invalid TPSL EA inputs. Check timer, heartbeat, ATR, EMA, and stop-loss settings.");
      return INIT_PARAMETERS_INCORRECT;
   }

   trade.SetAsyncMode(false);

   EventSetTimer(TimerSeconds);
   SendEaHeartbeat("tpsl");
   lastHeartbeatTime = TimeCurrent();

   Print("TPSL EA started. TP=M15 ATR(", M15AtrPeriod,
         ") SL=M15 EMA(", M15EmaPeriod,
         ") +/- ", EmaStopBufferPips,
         " pips, capped at ", MaximumStopLossPips,
         " pips",
         " PendingTP=", PendingTakeProfitPips,
         " PendingSL=", PendingStopLossPips,
         " Breakeven=", UseBreakeven,
         " BreakevenTriggerPips=", BreakevenTriggerPips,
         " BreakevenOffsetPips=", BreakevenOffsetPips,
         " CurrentSymbolOnly=", ManageCurrentSymbolOnly,
         " OnlySetIfMissing=", OnlySetIfMissing);

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
//| Expert tick                                                      |
//+------------------------------------------------------------------+
void OnTick()
{
   ManageAll();
}

//+------------------------------------------------------------------+
//| Timer fallback                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   ManageAll();
   MaybeSendHeartbeat();
}

//+------------------------------------------------------------------+
//| Send TPSL health without slowing its management timer            |
//+------------------------------------------------------------------+
void MaybeSendHeartbeat()
{
   datetime now = TimeCurrent();
   if(now - lastHeartbeatTime >= HeartbeatSeconds)
   {
      SendEaHeartbeat("tpsl");
      lastHeartbeatTime = now;
   }
}
//+------------------------------------------------------------------+
