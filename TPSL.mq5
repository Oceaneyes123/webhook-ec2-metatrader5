//+------------------------------------------------------------------+
//|                                             Set_100_Pip_TP_SL.mq5 |
//|              Adds pip-based TP/SL and breakeven stop management   |
//+------------------------------------------------------------------+
#property copyright ""
#property link      ""
#property version   "1.02"
#property strict

#include <Trade/Trade.mqh>

CTrade trade;

input int      TP_Pips                 = 100;
input int      SL_Pips                 = 100;
input bool     ManageCurrentSymbolOnly = true;
input bool     OnlySetIfMissing        = true;
input ulong    MagicNumberFilter       = 0;   // 0 = manage all magic numbers
input int      TimerSeconds            = 1;

// Breakeven settings
input bool     UseBreakeven            = true;
input int      BreakevenTriggerPips    = 50;  // Move SL when price is 50 pips in profit
input int      BreakevenOffsetPips     = 10;   // Near breakeven, small profit lock

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

      if(type == POSITION_TYPE_BUY)
      {
         defaultSL = openPrice - SL_Pips * pip;
         defaultTP = openPrice + TP_Pips * pip;
      }
      else if(type == POSITION_TYPE_SELL)
      {
         defaultSL = openPrice + SL_Pips * pip;
         defaultTP = openPrice - TP_Pips * pip;
      }
      else
      {
         continue;
      }

      defaultSL = NormalizeSymbolPrice(symbol, defaultSL);
      defaultTP = NormalizeSymbolPrice(symbol, defaultTP);

      if(OnlySetIfMissing)
      {
         if(currentSL <= 0.0)
            sl = defaultSL;

         if(currentTP <= 0.0)
            tp = defaultTP;
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

      bool isSellOrder =
         type == ORDER_TYPE_SELL_LIMIT ||
         type == ORDER_TYPE_SELL_STOP ||
         type == ORDER_TYPE_SELL_STOP_LIMIT;

      if(isBuyOrder)
      {
         sl = openPrice - SL_Pips * pip;
         tp = openPrice + TP_Pips * pip;
      }
      else if(isSellOrder)
      {
         sl = openPrice + SL_Pips * pip;
         tp = openPrice - TP_Pips * pip;
      }
      else
      {
         continue;
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
   trade.SetAsyncMode(false);

   if(TimerSeconds > 0)
      EventSetTimer(TimerSeconds);

   Print("Set TP/SL EA started. TP_Pips=", TP_Pips,
         " SL_Pips=", SL_Pips,
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
}
//+------------------------------------------------------------------+
