#ifndef TRADE_MANAGER_MQH
#define TRADE_MANAGER_MQH

struct TradeConfig
{
   string mode;
   double lotSize;
   double trailPips;
};

TradeConfig cachedTradeConfig;
datetime cachedTradeConfigTime = 0;
bool hasCachedTradeConfig = false;
bool lastHadPosition = false;
string lastManualPositionTickets = "";

bool SendEaIssue(
   string message,
   string detail = "",
   ENUM_TIMEFRAMES timeframe = PERIOD_CURRENT
)
{
   string tfText = timeframe == PERIOD_CURRENT ? "" : TimeframeToText(timeframe);
   string key = message + "|" + detail + "|" + tfText;
   datetime now = TimeCurrent();
   if(key == lastEaIssueKey && EaIssueRepeatSeconds > 0
      && now - lastEaIssueTime < EaIssueRepeatSeconds)
      return false;
   lastEaIssueKey = key;
   lastEaIssueTime = now;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   string payload =
      "{\"event_type\":\"EA_ERROR\""
      ",\"source\":\"webhook2\""
      ",\"symbol\":\"" + JsonEscape(_Symbol) + "\""
      ",\"timeframe\":\"" + JsonEscape(tfText) + "\""
      ",\"message\":\"" + JsonEscape(message) + "\""
      ",\"detail\":\"" + JsonEscape(detail) + "\""
      ",\"digits\":" + IntegerToString(digits) + "}";
   return SendWebhook(payload);
}

string TradeResultText()
{
   return "retcode=" + IntegerToString((int)trade.ResultRetcode())
      + " " + trade.ResultRetcodeDescription();
}

string UrlEncode(string value)
{
   uchar bytes[];
   StringToCharArray(value, bytes, 0, WHOLE_ARRAY, CP_UTF8);
   string encoded = "";
   for(int index = 0; index < ArraySize(bytes) - 1; index++)
   {
      int character = bytes[index];
      if((character >= 'A' && character <= 'Z')
         || (character >= 'a' && character <= 'z')
         || (character >= '0' && character <= '9')
         || character == '-' || character == '_'
         || character == '.' || character == '~')
         encoded += CharToString((uchar)character);
      else
         encoded += "%" + StringFormat("%02X", character);
   }
   return encoded;
}

string TradeConfigUrl()
{
   int marker = StringFind(WebhookUrl, "/webhook");
   if(marker >= 0)
      return StringSubstr(WebhookUrl, 0, marker)
         + "/trade-config?symbol=" + UrlEncode(_Symbol);
   return WebhookUrl + "/trade-config?symbol=" + UrlEncode(_Symbol);
}

bool HttpGet(string url, string &responseBody)
{
   char data[];
   char result[];
   string resultHeaders;
   string headers =
      "Accept: application/json\r\n"
      "User-Agent: MT5-Trade-Config\r\n";

   ResetLastError();
   int responseCode = WebRequest(
      "GET",
      url,
      headers,
      WebRequestTimeoutMs,
      data,
      result,
      resultHeaders
   );
   int mt5Error = GetLastError();
   responseBody = CharArrayToString(result, 0, -1, CP_UTF8);
   if(responseCode == -1)
   {
      if(PrintDebugLogs)
         PrintWebRequestHelp(url, mt5Error);
      return false;
   }
   if(responseCode < 200 || responseCode >= 300)
   {
      if(PrintDebugLogs)
         Print("GET ", url, " returned HTTP ", responseCode, ": ", responseBody);
      return false;
   }
   return true;
}

string JsonStringValue(string json, string key, string fallback)
{
   string marker = "\"" + key + "\":\"";
   int start = StringFind(json, marker);
   if(start < 0)
      return fallback;
   start += StringLen(marker);
   int end = StringFind(json, "\"", start);
   if(end < 0)
      return fallback;
   return StringSubstr(json, start, end - start);
}

double JsonDoubleValue(string json, string key, double fallback)
{
   string marker = "\"" + key + "\":";
   int start = StringFind(json, marker);
   if(start < 0)
      return fallback;
   start += StringLen(marker);
   int end = start;
   while(end < StringLen(json))
   {
      ushort character = StringGetCharacter(json, end);
      if((character >= 48 && character <= 57)
         || character == 46
         || character == 45)
         end++;
      else
         break;
   }
   if(end == start)
      return fallback;
   return StringToDouble(StringSubstr(json, start, end - start));
}

bool FetchTradeConfig(TradeConfig &config)
{
   datetime now = TimeCurrent();

   // Use cached config if fresh enough
   if(hasCachedTradeConfig && now - cachedTradeConfigTime < TradeConfigRefreshSeconds)
   {
      config = cachedTradeConfig;
      return true;
   }

   // Try HTTP fetch
   string body;
   bool fetched = HttpGet(TradeConfigUrl(), body);
   if(fetched)
   {
      config.mode = JsonStringValue(body, "mode", "NOTRADE");
      config.lotSize = JsonDoubleValue(body, "lot_size", 0.2);
      config.trailPips = JsonDoubleValue(body, "trail_pips", 20.0);
      if(config.lotSize <= 0 || config.trailPips < 0)
      {
         SendEaIssue("Invalid trade config", body);
         // Fall back to stale cache if available
         if(hasCachedTradeConfig && now - cachedTradeConfigTime <= TradeConfigMaxStaleSeconds)
         {
            if(PrintDebugLogs)
               Print("Using stale-but-allowed fallback config, age=", now - cachedTradeConfigTime, "s");
            config = cachedTradeConfig;
            return true;
         }
         return false;
      }
      // Update cache on success
      cachedTradeConfig = config;
      cachedTradeConfigTime = now;
      hasCachedTradeConfig = true;
      return true;
   }

   // HTTP fetch failed
   SendEaIssue("Trade config fetch failed", TradeConfigUrl());
   if(hasCachedTradeConfig && now - cachedTradeConfigTime <= TradeConfigMaxStaleSeconds)
   {
      if(PrintDebugLogs)
         Print("Using stale-but-allowed fallback config, age=", now - cachedTradeConfigTime, "s");
      config = cachedTradeConfig;
      return true;
   }

   if(PrintDebugLogs)
      Print("Trade config unavailable. No valid cache.");
   return false;
}

bool ReadTradeEmaValues(int index, double &ema20, double &ema50)
{
   double ema20Buffer[1];
   double ema50Buffer[1];
   if(CopyBuffer(ema20Handles[index], 0, 1, 1, ema20Buffer) != 1
      || CopyBuffer(ema50Handles[index], 0, 1, 1, ema50Buffer) != 1)
      return false;
   ema20 = ema20Buffer[0];
   ema50 = ema50Buffer[0];
   return ema20 != EMPTY_VALUE && ema50 != EMPTY_VALUE;
}

bool ClosedCandleAboveEma20(int index)
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadTradeEmaValues(index, ema20, ema50))
   {
      SendEaIssue(
         "EMA data unavailable",
         "Above EMA20 confluence check",
         Timeframes[index]
      );
      return false;
   }
   Candle candle = ReadCandle(Timeframes[index], 1);
   return candle.open > ema20 && candle.close > ema20;
}

bool ClosedCandleBelowEma20(int index)
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadTradeEmaValues(index, ema20, ema50))
   {
      SendEaIssue(
         "EMA data unavailable",
         "Below EMA20 confluence check",
         Timeframes[index]
      );
      return false;
   }
   Candle candle = ReadCandle(Timeframes[index], 1);
   return candle.open < ema20 && candle.close < ema20;
}

bool BuyConfluence()
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadTradeEmaValues(0, ema20, ema50))
   {
      SendEaIssue("M1 EMA data unavailable", "Buy confluence check", PERIOD_M1);
      return false;
   }
   return ema20 > ema50
      && ClosedCandleAboveEma20(1)
      && ClosedCandleAboveEma20(2);
}

bool SellConfluence()
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadTradeEmaValues(0, ema20, ema50))
   {
      SendEaIssue("M1 EMA data unavailable", "Sell confluence check", PERIOD_M1);
      return false;
   }
   return ema50 > ema20
      && ClosedCandleBelowEma20(1)
      && ClosedCandleBelowEma20(2);
}

double PipSize()
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return (digits == 3 || digits == 5) ? point * 10.0 : point;
}

ulong FindPendingOrder(ENUM_ORDER_TYPE type)
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol
         && (long)OrderGetInteger(ORDER_MAGIC) == TradeMagicNumber
         && (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type)
         return ticket;
   }
   return 0;
}

bool HasOpenPositionForSymbol()
{
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol
         && (long)PositionGetInteger(POSITION_MAGIC) == TradeMagicNumber)
         return true;
   }
   return false;
}

bool HasAnyPositionForSymbol()
{
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol)
         return true;
   }
   return false;
}

void DeletePendingOrders(ENUM_ORDER_TYPE type)
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol
         && (long)OrderGetInteger(ORDER_MAGIC) == TradeMagicNumber
         && (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type
         && !trade.OrderDelete(ticket))
         SendEaIssue("OrderDelete failed", TradeResultText());
   }
}

void TrailPendingOrder(ENUM_ORDER_TYPE type, double lotSize, double targetPrice)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   targetPrice = NormalizeDouble(targetPrice, digits);
   ulong ticket = FindPendingOrder(type);
   if(ticket > 0)
   {
      double currentPrice = OrderGetDouble(ORDER_PRICE_OPEN);
      if(MathAbs(currentPrice - targetPrice) >= PipSize() * 0.1
         && !trade.OrderModify(ticket, targetPrice, 0, 0, ORDER_TIME_GTC, 0))
         SendEaIssue("OrderModify failed", TradeResultText());
      return;
   }

   if(type == ORDER_TYPE_BUY_LIMIT)
   {
      if(!trade.BuyLimit(
         lotSize,
         targetPrice,
         _Symbol,
         0,
         0,
         ORDER_TIME_GTC,
         0,
         "Hermes trailing buy limit"
      ))
         SendEaIssue("BuyLimit failed", TradeResultText(), PERIOD_M1);
   }
   else if(type == ORDER_TYPE_SELL_LIMIT)
   {
      if(!trade.SellLimit(
         lotSize,
         targetPrice,
         _Symbol,
         0,
         0,
         ORDER_TIME_GTC,
         0,
         "Hermes trailing sell limit"
      ))
         SendEaIssue("SellLimit failed", TradeResultText(), PERIOD_M1);
   }
}

void NotifyFilledEaPositions()
{
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol
         || (long)PositionGetInteger(POSITION_MAGIC) != TradeMagicNumber)
         continue;

      SendTradeOpenNotification(
         "webhook2",
         (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE),
         PositionGetDouble(POSITION_PRICE_OPEN),
         PositionGetDouble(POSITION_VOLUME),
         PositionGetDouble(POSITION_SL),
         PositionGetDouble(POSITION_TP)
      );
   }
}

void ManageTrading()
{
   // Detect position close (runs every tick, even if config fetch fails below)
   bool hasPosition = HasOpenPositionForSymbol();
   if(!lastHadPosition && hasPosition)
      NotifyFilledEaPositions();
   if(lastHadPosition && !hasPosition)
   {
      double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      string reason = "MANUAL_CLOSE";
      double profit = 0;

      // Look up the last closed deal for this symbol/magic
      HistorySelect(TimeCurrent() - 7 * 86400, TimeCurrent());
      int totalDeals = HistoryDealsTotal();
      for(int i = totalDeals - 1; i >= 0; i--)
      {
         ulong dealTicket = HistoryDealGetTicket(i);
         if(dealTicket <= 0) continue;
         if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) continue;
         if((long)HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != TradeMagicNumber) continue;
         if((long)HistoryDealGetInteger(dealTicket, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;

         profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
         long dealReason = HistoryDealGetInteger(dealTicket, DEAL_REASON);

         if(dealReason == DEAL_REASON_TP) reason = "TP_HIT";
         else if(dealReason == DEAL_REASON_SL) reason = "SL_HIT";
         else reason = "MANUAL_CLOSE";
         break;
      }

      SendTradeCloseNotification(reason, profit, balance);
   }
   lastHadPosition = hasPosition;

   // Detect new manual position open — tracks individual position tickets
   // Handles: second manual position, manual while EA position exists, and multiple
   // positions opened between timer ticks (P2 fix).
   string currentManualTickets = "";
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
            string ticketStr = IntegerToString(ticket);
            if(currentManualTickets != "")
               currentManualTickets += ",";
            currentManualTickets += ticketStr;

            // New ticket not in the last known set → detect it
            string needle = "," + ticketStr + ",";
            string haystack = "," + lastManualPositionTickets + ",";
            if(StringFind(haystack, needle) < 0)
            {
               double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
               ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
               double volume = PositionGetDouble(POSITION_VOLUME);
               double sl = PositionGetDouble(POSITION_SL);
               double tp = PositionGetDouble(POSITION_TP);
               SendTradeOpenNotification("manual", posType, openPrice, volume, sl, tp);
            }
         }
      }
   }
   lastManualPositionTickets = currentManualTickets;

   TradeConfig config;
   if(!FetchTradeConfig(config))
      return;

   trade.SetExpertMagicNumber(TradeMagicNumber);
   if(hasPosition)
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      return;
   }

   if(config.mode == "BUY")
   {
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      if(!BuyConfluence())
      {
         DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
         return;
      }
      double ema20 = 0;
      double ema50 = 0;
      if(!ReadTradeEmaValues(0, ema20, ema50))
         return;
      double price = ema20 - config.trailPips * PipSize();
      if(price < SymbolInfoDouble(_Symbol, SYMBOL_ASK))
         TrailPendingOrder(ORDER_TYPE_BUY_LIMIT, config.lotSize, price);
      return;
   }

   if(config.mode == "SELL")
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      if(!SellConfluence())
      {
         DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
         return;
      }
      double ema20 = 0;
      double ema50 = 0;
      if(!ReadTradeEmaValues(0, ema20, ema50))
         return;
      double price = ema20 + config.trailPips * PipSize();
      if(price > SymbolInfoDouble(_Symbol, SYMBOL_BID))
         TrailPendingOrder(ORDER_TYPE_SELL_LIMIT, config.lotSize, price);
      return;
   }

   if(config.mode == "NOTRADE")
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      return;
   }

   SendEaIssue("Unknown trade mode", config.mode);
   DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
   DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
}

#endif
