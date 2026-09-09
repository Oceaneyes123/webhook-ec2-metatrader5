//+------------------------------------------------------------------+
//|              EMA Confluence Drawdown Recovery EA                 |
//+------------------------------------------------------------------+
#property copyright ""
#property link      ""
#property version   "2.60"
#property strict

#include <Trade/Trade.mqh>
#include "includes/WebhookCommon.mqh"

CTrade trade;

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input int HeartbeatSeconds = 30;
input int EmaConfigRefreshSeconds = 5;

//--- Primary entry
input double Lots                         = 0.10;
input int    MinimumEMAGapPips            = 20;
input int    TP_Pips                      = 100;
input int    SL_Pips                      = 100;
input bool   CancelPendingIfSignalInvalid = true;

//--- Pending lifecycle
input int PendingExpiryMinutes   = 15;
input int PendingReentryWaitMins = 5;

//--- M1 RSI exit
input bool   EnableRSIExit             = true;
input int    RSIPeriod                 = 7;
input double BuyRSIExitLevel           = 75.0;
input double SellRSIExitLevel          = 25.0;
input double RSIExitMinimumProfitMoney = 0.01;

//--- Stochastic RSI
input bool   EnableM15StochRSIFilter    = true;
input bool   EnableM5StochRSIFilter     = true;
input bool   EnableM5StochRSIExit       = true;
input int    StochRSIRSILength          = 14;
input int    StochRSILength             = 14;
input int    StochRSIKSmoothing         = 3;
input int    StochRSIDSmoothing         = 3;
input double StochRSIMiddleLevel        = 50.0;
input double StochRSIBuyExitLevel       = 80.0;
input double StochRSISellExitLevel      = 20.0;
input double StochRSIExitMinProfitMoney = 0.01;

//--- Recovery
input bool   EnableRecoveryManagement   = true;
input int    BreakevenDrawdownPips      = 30;
input int    BreakevenTriggerPips       = 50;
input int    BreakevenProfitPips        = 10;
input int    RecoveryCloseDrawdownPips  = 50;
input double RecoveryMinimumProfitMoney = 0.01;
input int    SecondEntryDrawdownPips    = 70;
input int    BasketTargetPips           = 50;
input int    RecoveryCooldownMinutes    = 15;

//--- General
input ulong MagicNumber     = 20260711;
input int   DeviationPoints = 20;

//--- EMA configuration
enum EMA_INDEX
{
   EMA_20,
   EMA_50,
   EMA_100,
   EMA_200,
   EMA_COUNT
};

const int EMA_PERIODS[EMA_COUNT] = {20, 50, 100, 200};

int m1EmaHandles[EMA_COUNT];
int m15Ema20Handle = INVALID_HANDLE;
int m1RsiHandle    = INVALID_HANDLE;
int m5RsiHandle    = INVALID_HANDLE;
int m15RsiHandle   = INVALID_HANDLE;

//--- Time state
datetime lastM1BarTime         = 0;
datetime lastM5BarTime         = 0;
datetime recoveryCooldownUntil = 0;
datetime pendingCooldownUntil  = 0;
datetime lastHeartbeatTime     = 0;
datetime lastEmaConfigTime     = 0;
bool emaTradingEnabled         = true;

//--- Recovery state
ulong  trackedPrimaryTicket       = 0;
double maximumPrimaryDrawdownPips = 0.0;
bool   reached30PipDrawdown       = false;
bool   reached50PipDrawdown       = false;
bool   reached70PipDrawdown       = false;
bool   secondEntryAttempted       = false;

//--- M5 Stochastic RSI lock state
bool buyStochLocked  = false;
bool sellStochLocked = false;

void RefreshEmaConfig()
{
   datetime now = TimeCurrent();
   if(lastEmaConfigTime != 0 && now - lastEmaConfigTime < EmaConfigRefreshSeconds)
      return;
   lastEmaConfigTime = now;

   string configUrl = WebhookUrl;
   if(StringReplace(configUrl, "/webhook", "/ema-config") == 0)
      return;

   char request[];
   char response[];
   string responseHeaders;
   ResetLastError();
   int responseCode = WebRequest(
      "GET", configUrl, "Accept: application/json\r\n",
      WebRequestTimeoutMs, request, response, responseHeaders
   );
   if(responseCode < 200 || responseCode >= 300)
      return;

   string body = CharArrayToString(response, 0, -1, CP_UTF8);
   int enabledAt = StringFind(body, "\"enabled\"");
   if(enabledAt < 0)
      return;
   int trueAt = StringFind(body, "true", enabledAt);
   int falseAt = StringFind(body, "false", enabledAt);
   if(trueAt >= 0 && (falseAt < 0 || trueAt < falseAt))
      emaTradingEnabled = true;
   else if(falseAt >= 0)
      emaTradingEnabled = false;
}

//+------------------------------------------------------------------+
//| Symbol utilities                                                 |
//+------------------------------------------------------------------+
double PipSize()
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0) tick = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   return tick * 10.0;
}

double NormalizePrice(double price)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0) tick = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   return NormalizeDouble(MathRound(price / tick) * tick,
                          (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

double NormalizeVolume(double volume)
{
   double minVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step      = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(step <= 0.0) step = minVolume;

   volume = MathMax(minVolume, MathMin(maxVolume, volume));
   volume = MathFloor(volume / step + 0.0000001) * step;

   return NormalizeDouble(volume, 2);
}

double MinimumPendingDistance()
{
   return (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) *
          SymbolInfoDouble(_Symbol, SYMBOL_POINT);
}

bool IsManagedOrder()
{
   return OrderGetString(ORDER_SYMBOL) == _Symbol &&
          (ulong)OrderGetInteger(ORDER_MAGIC) == MagicNumber;
}

bool IsManagedPosition()
{
   return PositionGetString(POSITION_SYMBOL) == _Symbol &&
          (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber;
}

//+------------------------------------------------------------------+
//| Indicator utilities                                              |
//+------------------------------------------------------------------+
int CreateEMA(ENUM_TIMEFRAMES timeframe, int period)
{
   return iMA(_Symbol, timeframe, period, 0, MODE_EMA, PRICE_CLOSE);
}

bool GetBufferValue(int handle, int shift, double &value)
{
   double buffer[1];

   if(CopyBuffer(handle, 0, shift, 1, buffer) != 1)
      return false;

   value = buffer[0];
   return true;
}

bool GetBufferValues(int handle, int shift, int count, double &values[])
{
   ArrayResize(values, count);
   return CopyBuffer(handle, 0, shift, count, values) == count;
}

bool IsEMAOrderValid(double ema20, double ema50, double ema100, bool buy)
{
   return buy ? ema20 > ema50 && ema50 > ema100
              : ema20 < ema50 && ema50 < ema100;
}

//+------------------------------------------------------------------+
//| Stochastic RSI calculation                                       |
//+------------------------------------------------------------------+
bool CalculateRawStochRSI(int rsiHandle, int shift, double &value)
{
   double currentRSI;
   double minimumRSI = DBL_MAX;
   double maximumRSI = -DBL_MAX;

   if(!GetBufferValue(rsiHandle, shift, currentRSI))
      return false;

   for(int i = 0; i < StochRSILength; i++)
   {
      double rsi;

      if(!GetBufferValue(rsiHandle, shift + i, rsi))
         return false;

      minimumRSI = MathMin(minimumRSI, rsi);
      maximumRSI = MathMax(maximumRSI, rsi);
   }

   double range = maximumRSI - minimumRSI;

   value = range <= 0.0000001
           ? 50.0
           : 100.0 * (currentRSI - minimumRSI) / range;

   return true;
}

bool CalculateStochRSIK(int rsiHandle, int shift, double &k)
{
   double total = 0.0;

   for(int i = 0; i < StochRSIKSmoothing; i++)
   {
      double raw;

      if(!CalculateRawStochRSI(rsiHandle, shift + i, raw))
         return false;

      total += raw;
   }

   k = total / StochRSIKSmoothing;
   return true;
}

bool CalculateStochRSI(int rsiHandle, int shift, double &k, double &d)
{
   if(!CalculateStochRSIK(rsiHandle, shift, k))
      return false;

   double totalD = 0.0;

   for(int i = 0; i < StochRSIDSmoothing; i++)
   {
      double historicalK;

      if(!CalculateStochRSIK(rsiHandle, shift + i, historicalK))
         return false;

      totalD += historicalK;
   }

   d = totalD / StochRSIDSmoothing;
   return true;
}

//+------------------------------------------------------------------+
//| Entry filters                                                    |
//+------------------------------------------------------------------+
bool M15BodyFilter(bool buy)
{
   double ema20;

   if(!GetBufferValue(m15Ema20Handle, 1, ema20))
      return false;

   double openPrice  = iOpen(_Symbol, PERIOD_M15, 1);
   double closePrice = iClose(_Symbol, PERIOD_M15, 1);

   if(openPrice == 0.0 || closePrice == 0.0)
      return false;

   return buy ? openPrice > ema20 && closePrice > ema20
              : openPrice < ema20 && closePrice < ema20;
}

bool M15StochRSIFilter(bool buy)
{
   if(!EnableM15StochRSIFilter)
      return true;

   double k, d;

   if(!CalculateStochRSI(m15RsiHandle, 1, k, d))
      return false;

   return buy ? k > d : k < d;
}

bool M1EMAFilter(bool buy)
{
   double ema20[], ema50[], ema100[];

   if(!GetBufferValues(m1EmaHandles[EMA_20], 1, 10, ema20) ||
      !GetBufferValues(m1EmaHandles[EMA_50], 1, 10, ema50) ||
      !GetBufferValues(m1EmaHandles[EMA_100], 1, 10, ema100))
   {
      return false;
   }

   for(int i = 0; i < 10; i++)
      if(!IsEMAOrderValid(ema20[i], ema50[i], ema100[i], buy))
         return false;

   double latest20, latest50, latest100, latest200;

   if(!GetBufferValue(m1EmaHandles[EMA_20], 1, latest20) ||
      !GetBufferValue(m1EmaHandles[EMA_50], 1, latest50) ||
      !GetBufferValue(m1EmaHandles[EMA_100], 1, latest100) ||
      !GetBufferValue(m1EmaHandles[EMA_200], 1, latest200))
   {
      return false;
   }

   return buy
          ? latest20 > latest50 && latest50 > latest100 && latest100 > latest200
          : latest20 < latest50 && latest50 < latest100 && latest100 < latest200;
}

bool PrimaryEMAGapFilter(bool buy)
{
   double ema20, ema200;

   if(!GetBufferValue(m1EmaHandles[EMA_20], 1, ema20) ||
      !GetBufferValue(m1EmaHandles[EMA_200], 1, ema200))
   {
      return false;
   }

   double gapPips = buy ? (ema20 - ema200) / PipSize()
                        : (ema200 - ema20) / PipSize();

   return gapPips >= MinimumEMAGapPips;
}

bool SecondaryEntryEMAFilter(ENUM_POSITION_TYPE type)
{
   double ema200;

   if(!GetBufferValue(m1EmaHandles[EMA_200], 1, ema200))
      return false;

   double candleClose = iClose(_Symbol, PERIOD_M1, 1);

   if(candleClose == 0.0)
      return false;

   return type == POSITION_TYPE_BUY
          ? candleClose > ema200
          : candleClose < ema200;
}

bool BaseSignalValid(bool buy)
{
   return M15BodyFilter(buy) &&
          M15StochRSIFilter(buy) &&
          M1EMAFilter(buy);
}

//+------------------------------------------------------------------+
//| Pending-order utilities                                          |
//+------------------------------------------------------------------+
bool GetManagedPendingOrder(ulong &ticket, ENUM_ORDER_TYPE &type,
                            double &price, datetime &setupTime)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong currentTicket = OrderGetTicket(i);

      if(currentTicket == 0 || !OrderSelect(currentTicket))
         continue;

      if(!IsManagedOrder())
      {
         continue;
      }

      ENUM_ORDER_TYPE currentType =
         (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);

      if(currentType != ORDER_TYPE_BUY_LIMIT &&
         currentType != ORDER_TYPE_SELL_LIMIT)
      {
         continue;
      }

      ticket    = currentTicket;
      type      = currentType;
      price     = OrderGetDouble(ORDER_PRICE_OPEN);
      setupTime = (datetime)OrderGetInteger(ORDER_TIME_SETUP);

      return true;
   }

   ticket    = 0;
   price     = 0.0;
   setupTime = 0;

   return false;
}

bool DeleteManagedPendingOrder(string reason = "")
{
   ulong ticket;
   ENUM_ORDER_TYPE type;
   double price;
   datetime setupTime;

   if(!GetManagedPendingOrder(ticket, type, price, setupTime))
      return true;

   if(trade.OrderDelete(ticket))
   {
      Print("PENDING ORDER DELETED | ticket=", ticket,
            " | reason=", reason);

      return true;
   }

   Print("PENDING DELETE FAILED | ticket=", ticket,
         " | reason=", reason,
         " | retcode=", trade.ResultRetcode(),
         " | description=", trade.ResultRetcodeDescription());

   return false;
}

//+------------------------------------------------------------------+
//| M5 Stochastic RSI entry locking                                  |
//+------------------------------------------------------------------+
bool IsStochRSIAgainstDirection(bool buy, double k, double d)
{
   return buy ? k < d : k > d;
}

bool IsM5StochRSIEntryAllowed(bool buy)
{
   if(!EnableM5StochRSIFilter)
      return true;

   if((buy && buyStochLocked) || (!buy && sellStochLocked))
      return false;

   double k, d;

   if(!CalculateStochRSI(m5RsiHandle, 1, k, d))
      return false;

   if(!IsStochRSIAgainstDirection(buy, k, d))
      return true;

   if(buy)
      buyStochLocked = true;
   else
      sellStochLocked = true;

   Print("M5 STOCH RSI ENTRY LOCKED",
         " | direction=", buy ? "BUY" : "SELL",
         " | K=", DoubleToString(k, 2),
         " | D=", DoubleToString(d, 2),
         " | reason=", buy ? "K is below D" : "K is above D");

   return false;
}

void ProcessM5StochRSILocks()
{
   if(!EnableM5StochRSIFilter)
      return;

   double k, d;

   if(!CalculateStochRSI(m5RsiHandle, 1, k, d))
      return;

   if(buyStochLocked && k < StochRSIMiddleLevel)
   {
      buyStochLocked = false;

      Print("M5 STOCH RSI BUY LOCK RELEASED",
            " | K=", DoubleToString(k, 2),
            " | reset_level=", DoubleToString(StochRSIMiddleLevel, 2));
   }

   if(sellStochLocked && k > StochRSIMiddleLevel)
   {
      sellStochLocked = false;

      Print("M5 STOCH RSI SELL LOCK RELEASED",
            " | K=", DoubleToString(k, 2),
            " | reset_level=", DoubleToString(StochRSIMiddleLevel, 2));
   }

   ulong ticket;
   ENUM_ORDER_TYPE type;
   double price;
   datetime setupTime;

   if(!GetManagedPendingOrder(ticket, type, price, setupTime))
      return;

   bool buy = type == ORDER_TYPE_BUY_LIMIT;

   if(!IsStochRSIAgainstDirection(buy, k, d))
      return;

   string reason = buy
                   ? "M5 Stoch RSI K moved below D"
                   : "M5 Stoch RSI K moved above D";

   if(DeleteManagedPendingOrder(reason))
   {
      if(buy)
         buyStochLocked = true;
      else
         sellStochLocked = true;

      Print("M5 STOCH RSI PENDING BLOCKED",
            " | direction=", buy ? "BUY" : "SELL",
            " | K=", DoubleToString(k, 2),
            " | D=", DoubleToString(d, 2));
   }
}

//+------------------------------------------------------------------+
//| Pending entry calculation                                        |
//+------------------------------------------------------------------+
double CalculatePendingEntry(bool buy, double ema20, double ema50)
{
   double entry       = (ema20 + ema50) / 2.0;
   double ask         = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid         = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minDistance = MinimumPendingDistance();

   if(buy && entry >= ask - minDistance)
      entry = ask - minDistance;

   if(!buy && entry <= bid + minDistance)
      entry = bid + minDistance;

   return NormalizePrice(entry);
}

bool IsPendingCooldownActive()
{
   if(pendingCooldownUntil <= 0)
      return false;

   if(TimeCurrent() < pendingCooldownUntil)
      return true;

   pendingCooldownUntil = 0;

   Print("PENDING REENTRY WAIT FINISHED | time=",
         TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES));

   return false;
}

void StartPendingCooldown()
{
   pendingCooldownUntil =
      TimeCurrent() + PendingReentryWaitMins * 60;

   Print("PENDING REENTRY WAIT STARTED",
         " | minutes=", PendingReentryWaitMins,
         " | until=",
         TimeToString(pendingCooldownUntil, TIME_DATE | TIME_MINUTES));
}

bool CheckPendingExpiry()
{
   ulong ticket;
   ENUM_ORDER_TYPE type;
   double price;
   datetime setupTime;

   if(!GetManagedPendingOrder(ticket, type, price, setupTime) ||
      setupTime <= 0)
   {
      return false;
   }

   if(TimeCurrent() - setupTime < PendingExpiryMinutes * 60)
      return false;

   string reason =
      "Expired after " +
      IntegerToString(PendingExpiryMinutes) +
      " minutes without execution";

   if(!DeleteManagedPendingOrder(reason))
      return false;

   StartPendingCooldown();
   return true;
}

bool PlacePendingOrder(bool buy)
{
   if(IsRecoveryCooldownActive() ||
      IsPendingCooldownActive() ||
      !IsM5StochRSIEntryAllowed(buy))
   {
      return false;
   }

   double ema20, ema50;

   if(!GetBufferValue(m1EmaHandles[EMA_20], 0, ema20) ||
      !GetBufferValue(m1EmaHandles[EMA_50], 0, ema50))
   {
      return false;
   }

   double pip    = PipSize();
   double entry  = CalculatePendingEntry(buy, ema20, ema50);
   double sl     = NormalizePrice(buy ? entry - SL_Pips * pip
                                      : entry + SL_Pips * pip);
   double tp     = NormalizePrice(buy ? entry + TP_Pips * pip
                                      : entry - TP_Pips * pip);
   double volume = NormalizeVolume(Lots);

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DeviationPoints);

   bool placed = buy
      ? trade.BuyLimit(volume, entry, _Symbol, sl, tp,
                       ORDER_TIME_GTC, 0,
                       "Primary BUY: EMA midpoint")
      : trade.SellLimit(volume, entry, _Symbol, sl, tp,
                        ORDER_TIME_GTC, 0,
                        "Primary SELL: EMA midpoint");

   if(!placed)
   {
      Print("PRIMARY ORDER FAILED",
            " | direction=", buy ? "BUY" : "SELL",
            " | retcode=", trade.ResultRetcode(),
            " | description=", trade.ResultRetcodeDescription());
   }

   return placed;
}

void TrailPendingOrderOnNewM1Bar()
{
   ulong ticket;
   ENUM_ORDER_TYPE type;
   double currentEntry;
   datetime setupTime;

   if(!GetManagedPendingOrder(ticket, type, currentEntry, setupTime))
      return;

   bool buy = type == ORDER_TYPE_BUY_LIMIT;

   double ema20, ema50;

   if(!GetBufferValue(m1EmaHandles[EMA_20], 0, ema20) ||
      !GetBufferValue(m1EmaHandles[EMA_50], 0, ema50))
   {
      return;
   }

   double newEntry = CalculatePendingEntry(buy, ema20, ema50);
   double tick     = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);

   if(tick <= 0.0)
      tick = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   bool shouldMove = buy
                     ? newEntry > currentEntry + tick / 2.0
                     : newEntry < currentEntry - tick / 2.0;

   if(!shouldMove)
      return;

   double pip = PipSize();
   double sl  = NormalizePrice(buy ? newEntry - SL_Pips * pip
                                   : newEntry + SL_Pips * pip);
   double tp  = NormalizePrice(buy ? newEntry + TP_Pips * pip
                                   : newEntry - TP_Pips * pip);

   if(!trade.OrderModify(ticket, newEntry, sl, tp,
                         ORDER_TIME_GTC, 0, 0.0))
   {
      Print("PENDING TRAIL FAILED",
            " | ticket=", ticket,
            " | retcode=", trade.ResultRetcode(),
            " | description=", trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| Position utilities                                               |
//+------------------------------------------------------------------+
int ManagedPositionCount()
{
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(IsManagedPosition())
      {
         count++;
      }
   }

   return count;
}

bool GetPrimaryPosition(ulong &ticket, ENUM_POSITION_TYPE &type,
                        double &entry, double &volume,
                        double &profitMoney)
{
   ticket = 0;
   long oldestTime = LONG_MAX;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong currentTicket = PositionGetTicket(i);

      if(currentTicket == 0 ||
         !PositionSelectByTicket(currentTicket))
      {
         continue;
      }

      if(!IsManagedPosition())
      {
         continue;
      }

      long currentTime = PositionGetInteger(POSITION_TIME_MSC);

      if(currentTime >= oldestTime)
         continue;

      oldestTime  = currentTime;
      ticket      = currentTicket;
      type        = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      entry       = PositionGetDouble(POSITION_PRICE_OPEN);
      volume      = PositionGetDouble(POSITION_VOLUME);
      profitMoney = PositionGetDouble(POSITION_PROFIT) +
                    PositionGetDouble(POSITION_SWAP);
   }

   return ticket != 0;
}

double PositionProfitPips(ulong ticket)
{
   if(!PositionSelectByTicket(ticket))
      return 0.0;

   ENUM_POSITION_TYPE type =
      (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   double entry = PositionGetDouble(POSITION_PRICE_OPEN);

   double currentPrice =
      type == POSITION_TYPE_BUY
      ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
      : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   return type == POSITION_TYPE_BUY
          ? (currentPrice - entry) / PipSize()
          : (entry - currentPrice) / PipSize();
}

double PositionProfitMoney(ulong ticket)
{
   if(!PositionSelectByTicket(ticket))
      return 0.0;

   return PositionGetDouble(POSITION_PROFIT) +
          PositionGetDouble(POSITION_SWAP);
}

double BasketProfitPips()
{
   double total = 0.0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(IsManagedPosition())
      {
         total += PositionProfitPips(ticket);
      }
   }

   return total;
}

double BasketProfitMoney()
{
   double total = 0.0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(IsManagedPosition())
      {
         total += PositionGetDouble(POSITION_PROFIT) +
                  PositionGetDouble(POSITION_SWAP);
      }
   }

   return total;
}

bool CloseManagedPosition(ulong ticket, string reason)
{
   if(!PositionSelectByTicket(ticket))
      return false;

   Print(reason,
         " | ticket=", ticket,
         " | pips=", DoubleToString(PositionProfitPips(ticket), 1),
         " | profit=", DoubleToString(PositionProfitMoney(ticket), 2));

   if(trade.PositionClose(ticket))
      return true;

   Print("EA CLOSE FAILED",
         " | ticket=", ticket,
         " | reason=", reason,
         " | retcode=", trade.ResultRetcode(),
         " | description=", trade.ResultRetcodeDescription());

   return false;
}

bool CloseAllManagedPositions(string reason)
{
   ulong tickets[];
   int count = 0;

   ArrayResize(tickets, PositionsTotal());

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);

      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(IsManagedPosition())
      {
         tickets[count++] = ticket;
      }
   }

   bool allClosed = true;

   for(int i = 0; i < count; i++)
      if(!CloseManagedPosition(tickets[i], reason))
         allClosed = false;

   return allClosed;
}

//+------------------------------------------------------------------+
//| Recovery state                                                   |
//+------------------------------------------------------------------+
void ResetRecoveryState()
{
   trackedPrimaryTicket       = 0;
   maximumPrimaryDrawdownPips = 0.0;
   reached30PipDrawdown       = false;
   reached50PipDrawdown       = false;
   reached70PipDrawdown       = false;
   secondEntryAttempted       = false;
}

void TrackPrimaryTicket(ulong ticket)
{
   if(ticket == trackedPrimaryTicket)
      return;

   ResetRecoveryState();
   trackedPrimaryTicket = ticket;
}

void StartRecoveryCooldown(string reason)
{
   recoveryCooldownUntil =
      TimeCurrent() + RecoveryCooldownMinutes * 60;

   DeleteManagedPendingOrder("Recovery cooldown started");

   Print("EA RECOVERY COOLDOWN STARTED",
         " | reason=", reason,
         " | until=",
         TimeToString(recoveryCooldownUntil,
                      TIME_DATE | TIME_MINUTES));
}

bool IsRecoveryCooldownActive()
{
   if(recoveryCooldownUntil <= 0)
      return false;

   if(TimeCurrent() < recoveryCooldownUntil)
      return true;

   recoveryCooldownUntil = 0;
   return false;
}

//+------------------------------------------------------------------+
//| M5 Stochastic RSI exit                                           |
//+------------------------------------------------------------------+
bool ManageM5StochRSIExit()
{
   if(!EnableM5StochRSIExit ||
      ManagedPositionCount() <= 0)
   {
      return false;
   }

   double k, d;

   if(!CalculateStochRSI(m5RsiHandle, 1, k, d))
      return false;

   ulong primaryTicket;
   ENUM_POSITION_TYPE primaryType;
   double entry, volume, primaryProfitMoney;

   if(!GetPrimaryPosition(primaryTicket, primaryType,
                          entry, volume, primaryProfitMoney))
   {
      return false;
   }

   bool exitTriggered =
      primaryType == POSITION_TYPE_BUY
      ? k >= StochRSIBuyExitLevel
      : k <= StochRSISellExitLevel;

   if(!exitTriggered)
      return false;

   int positionCount = ManagedPositionCount();

   if(positionCount == 1)
   {
      double profitPips  = PositionProfitPips(primaryTicket);
      double profitMoney = PositionProfitMoney(primaryTicket);

      if(profitPips <= 0.0 ||
         profitMoney < StochRSIExitMinProfitMoney)
      {
         return false;
      }

      string reason =
         "EA CLOSE [M5 STOCH RSI EXIT]: " +
         string(primaryType == POSITION_TYPE_BUY ? "BUY" : "SELL") +
         " profitable | K=" + DoubleToString(k, 2) +
         " | D=" + DoubleToString(d, 2);

      if(CloseManagedPosition(primaryTicket, reason))
      {
         ResetRecoveryState();
         return true;
      }

      return false;
   }

   if(BasketProfitPips() <= 0.0 ||
      BasketProfitMoney() < StochRSIExitMinProfitMoney)
   {
      return false;
   }

   string reason =
      "EA CLOSE [M5 STOCH RSI BASKET EXIT]: " +
      string(primaryType == POSITION_TYPE_BUY ? "BUY" : "SELL") +
      " basket profitable | K=" + DoubleToString(k, 2) +
      " | D=" + DoubleToString(d, 2);

   if(CloseAllManagedPositions(reason))
   {
      ResetRecoveryState();
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| M1 RSI exit                                                      |
//+------------------------------------------------------------------+
bool ManageRSIExit()
{
   if(!EnableRSIExit ||
      ManagedPositionCount() <= 0)
   {
      return false;
   }

   double rsi;

   if(!GetBufferValue(m1RsiHandle, 1, rsi))
      return false;

   ulong primaryTicket;
   ENUM_POSITION_TYPE primaryType;
   double entry, volume, profitMoney;

   if(!GetPrimaryPosition(primaryTicket, primaryType,
                          entry, volume, profitMoney))
   {
      return false;
   }

   bool triggered =
      primaryType == POSITION_TYPE_BUY
      ? rsi >= BuyRSIExitLevel
      : rsi <= SellRSIExitLevel;

   if(!triggered)
      return false;

   if(ManagedPositionCount() == 1)
   {
      if(PositionProfitPips(primaryTicket) <= 0.0 ||
         PositionProfitMoney(primaryTicket) < RSIExitMinimumProfitMoney)
      {
         return false;
      }

      string reason =
         "EA CLOSE [M1 RSI EXIT]: RSI=" +
         DoubleToString(rsi, 2);

      if(CloseManagedPosition(primaryTicket, reason))
      {
         ResetRecoveryState();
         return true;
      }

      return false;
   }

   if(BasketProfitPips() <= 0.0 ||
      BasketProfitMoney() < RSIExitMinimumProfitMoney)
   {
      return false;
   }

   string reason =
      "EA CLOSE [M1 RSI BASKET EXIT]: RSI=" +
      DoubleToString(rsi, 2);

   if(CloseAllManagedPositions(reason))
   {
      ResetRecoveryState();
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Recovery actions                                                 |
//+------------------------------------------------------------------+
bool MovePrimaryStopToProfit(ulong ticket)
{
   if(!PositionSelectByTicket(ticket))
      return false;

   ENUM_POSITION_TYPE type =
      (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   double entry     = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSL = PositionGetDouble(POSITION_SL);
   double currentTP = PositionGetDouble(POSITION_TP);

   double targetSL =
      NormalizePrice(
         type == POSITION_TYPE_BUY
         ? entry + BreakevenProfitPips * PipSize()
         : entry - BreakevenProfitPips * PipSize()
      );

   bool alreadyProtected =
      type == POSITION_TYPE_BUY
      ? currentSL >= targetSL
      : currentSL > 0.0 && currentSL <= targetSL;

   if(alreadyProtected)
      return true;

   if(trade.PositionModify(ticket, targetSL, currentTP))
   {
      Print("EA STOP MODIFIED",
            " | ticket=", ticket,
            " | protected_profit=",
            BreakevenProfitPips, " pips");

      return true;
   }

   Print("EA STOP MODIFY FAILED",
         " | ticket=", ticket,
         " | retcode=", trade.ResultRetcode(),
         " | description=",
         trade.ResultRetcodeDescription());

   return false;
}

bool OpenSecondEntry(ENUM_POSITION_TYPE type,
                     double primaryVolume)
{
   if(!SecondaryEntryEMAFilter(type))
   {
      Print("SECONDARY ENTRY SKIPPED",
            " | reason=M1 close is not on required side of EMA200");

      return false;
   }

   double volume = NormalizeVolume(primaryVolume);
   double pip    = PipSize();

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DeviationPoints);

   bool opened;

   if(type == POSITION_TYPE_BUY)
   {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      opened = trade.Buy(
         volume,
         _Symbol,
         0.0,
         NormalizePrice(ask - SL_Pips * pip),
         NormalizePrice(ask + TP_Pips * pip),
         "Secondary BUY: recovery"
      );
   }
   else
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      opened = trade.Sell(
         volume,
         _Symbol,
         0.0,
         NormalizePrice(bid + SL_Pips * pip),
         NormalizePrice(bid - TP_Pips * pip),
         "Secondary SELL: recovery"
      );
   }

   if(opened)
   {
      Print("SECONDARY ENTRY OPENED",
            " | direction=",
            type == POSITION_TYPE_BUY ? "BUY" : "SELL",
            " | volume=", DoubleToString(volume, 2));

      return true;
   }

   Print("SECONDARY ENTRY FAILED",
         " | retcode=", trade.ResultRetcode(),
         " | description=",
         trade.ResultRetcodeDescription());

   return false;
}

//+------------------------------------------------------------------+
//| Recovery management                                              |
//+------------------------------------------------------------------+
void ManageRecovery()
{
   if(!EnableRecoveryManagement)
      return;

   int positionCount = ManagedPositionCount();

   if(positionCount == 0)
   {
      ResetRecoveryState();
      return;
   }

   ulong primaryTicket;
   ENUM_POSITION_TYPE primaryType;
   double entry, volume, profitMoney;

   if(!GetPrimaryPosition(primaryTicket, primaryType,
                          entry, volume, profitMoney))
   {
      return;
   }

   TrackPrimaryTicket(primaryTicket);

   double profitPips   = PositionProfitPips(primaryTicket);
   double drawdownPips = MathMax(0.0, -profitPips);

   maximumPrimaryDrawdownPips =
      MathMax(maximumPrimaryDrawdownPips,
              drawdownPips);

   if(maximumPrimaryDrawdownPips >=
      BreakevenDrawdownPips)
   {
      reached30PipDrawdown = true;
   }

   if(maximumPrimaryDrawdownPips >=
      RecoveryCloseDrawdownPips)
   {
      reached50PipDrawdown = true;
   }

   if(maximumPrimaryDrawdownPips >=
      SecondEntryDrawdownPips)
   {
      reached70PipDrawdown = true;
   }

   if(positionCount >= 2)
   {
      if(BasketProfitPips() >= BasketTargetPips)
      {
         string reason =
            "EA CLOSE [BASKET RECOVERY]: Combined +" +
            IntegerToString(BasketTargetPips) +
            " pips";

         if(CloseAllManagedPositions(reason))
         {
            StartRecoveryCooldown(
               "Basket recovery completed"
            );

            ResetRecoveryState();
         }
      }

      return;
   }

   if(reached70PipDrawdown &&
      !secondEntryAttempted)
   {
      secondEntryAttempted = true;
      OpenSecondEntry(primaryType, volume);
      return;
   }

   if(reached50PipDrawdown &&
      profitMoney >= RecoveryMinimumProfitMoney)
   {
      string reason =
         "EA CLOSE [SINGLE RECOVERY]: Recovered after -" +
         IntegerToString(RecoveryCloseDrawdownPips) +
         " pip drawdown";

      if(CloseManagedPosition(primaryTicket, reason))
      {
         StartRecoveryCooldown(
            "Single recovery completed"
         );

         ResetRecoveryState();
      }

      return;
   }

   if(reached30PipDrawdown &&
      !reached50PipDrawdown &&
      profitPips >= BreakevenTriggerPips)
   {
      MovePrimaryStopToProfit(primaryTicket);
   }
}

//+------------------------------------------------------------------+
//| Initialization                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(HeartbeatSeconds < 10 || EmaConfigRefreshSeconds < 1)
   {
      Print("Initialization failed: invalid heartbeat or EMA config interval.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if((ENUM_ACCOUNT_MARGIN_MODE)
      AccountInfoInteger(ACCOUNT_MARGIN_MODE) !=
      ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
   {
      Print("Initialization failed: hedging account required.");
      return INIT_FAILED;
   }

   if(StochRSIRSILength < 1 ||
      StochRSILength < 1 ||
      StochRSIKSmoothing < 1 ||
      StochRSIDSmoothing < 1)
   {
      Print("Initialization failed: invalid Stochastic RSI settings.");
      return INIT_FAILED;
   }

   for(int i = 0; i < EMA_COUNT; i++)
   {
      m1EmaHandles[i] =
         CreateEMA(PERIOD_M1, EMA_PERIODS[i]);

      if(m1EmaHandles[i] == INVALID_HANDLE)
      {
         Print("Failed to create M1 EMA",
               EMA_PERIODS[i]);

         return INIT_FAILED;
      }
   }

   m15Ema20Handle = CreateEMA(PERIOD_M15, 20);
   m1RsiHandle    = iRSI(_Symbol, PERIOD_M1,
                         RSIPeriod, PRICE_CLOSE);
   m5RsiHandle    = iRSI(_Symbol, PERIOD_M5,
                         StochRSIRSILength,
                         PRICE_CLOSE);
   m15RsiHandle   = iRSI(_Symbol, PERIOD_M15,
                         StochRSIRSILength,
                         PRICE_CLOSE);

   if(m15Ema20Handle == INVALID_HANDLE ||
      m1RsiHandle == INVALID_HANDLE ||
      m5RsiHandle == INVALID_HANDLE ||
      m15RsiHandle == INVALID_HANDLE)
   {
      Print("Failed to create indicator handles.");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(DeviationPoints);

   lastM1BarTime = iTime(_Symbol, PERIOD_M1, 0);
   lastM5BarTime = iTime(_Symbol, PERIOD_M5, 0);

   ResetRecoveryState();

   EventSetTimer(1);
   RefreshEmaConfig();
   SendEaHeartbeat("ema");
   lastHeartbeatTime = TimeCurrent();

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Cleanup                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int i = 0; i < EMA_COUNT; i++)
      if(m1EmaHandles[i] != INVALID_HANDLE)
         IndicatorRelease(m1EmaHandles[i]);

   if(m15Ema20Handle != INVALID_HANDLE)
      IndicatorRelease(m15Ema20Handle);

   if(m1RsiHandle != INVALID_HANDLE)
      IndicatorRelease(m1RsiHandle);

   if(m5RsiHandle != INVALID_HANDLE)
      IndicatorRelease(m5RsiHandle);

   if(m15RsiHandle != INVALID_HANDLE)
      IndicatorRelease(m15RsiHandle);
}

void OnTimer()
{
   RefreshEmaConfig();
   MaybeSendEaHeartbeat("ema", HeartbeatSeconds, lastHeartbeatTime);
}

//+------------------------------------------------------------------+
//| Main                                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime currentM5BarTime =
      iTime(_Symbol, PERIOD_M5, 0);

   if(currentM5BarTime != 0 &&
      currentM5BarTime != lastM5BarTime)
   {
      lastM5BarTime = currentM5BarTime;
      ProcessM5StochRSILocks();
   }

   if(ManageM5StochRSIExit())
      return;

   if(ManageRSIExit())
      return;

   ManageRecovery();

   if(!emaTradingEnabled)
   {
      DeleteManagedPendingOrder("EMA trading disabled");
      return;
   }

   if(ManagedPositionCount() > 0)
      return;

   if(IsRecoveryCooldownActive())
   {
      DeleteManagedPendingOrder(
         "Recovery cooldown active"
      );

      return;
   }

   if(CheckPendingExpiry())
      return;

   bool pendingWaitActive =
      IsPendingCooldownActive();

   bool buyBaseSignal  = BaseSignalValid(true);
   bool sellBaseSignal = BaseSignalValid(false);

   ulong pendingTicket;
   ENUM_ORDER_TYPE pendingType;
   double pendingPrice;
   datetime pendingSetupTime;

   bool hasPending =
      GetManagedPendingOrder(
         pendingTicket,
         pendingType,
         pendingPrice,
         pendingSetupTime
      );

   if(hasPending &&
      CancelPendingIfSignalInvalid)
   {
      bool valid =
         pendingType == ORDER_TYPE_BUY_LIMIT
         ? buyBaseSignal
         : sellBaseSignal;

      if(!valid &&
         DeleteManagedPendingOrder(
            "Original EMA or M15 Stoch RSI confluence became invalid"
         ))
      {
         hasPending = false;
      }
   }

   datetime currentM1BarTime =
      iTime(_Symbol, PERIOD_M1, 0);

   bool newM1Bar =
      currentM1BarTime != 0 &&
      currentM1BarTime != lastM1BarTime;

   if(newM1Bar)
   {
      lastM1BarTime = currentM1BarTime;

      if(hasPending)
         TrailPendingOrderOnNewM1Bar();
   }

   if(hasPending || pendingWaitActive)
      return;

   bool buyEntrySignal =
      buyBaseSignal &&
      PrimaryEMAGapFilter(true);

   bool sellEntrySignal =
      sellBaseSignal &&
      PrimaryEMAGapFilter(false);

   if(buyEntrySignal &&
      !sellEntrySignal)
   {
      PlacePendingOrder(true);
   }
   else if(sellEntrySignal &&
           !buyEntrySignal)
   {
      PlacePendingOrder(false);
   }
}
//+------------------------------------------------------------------+
