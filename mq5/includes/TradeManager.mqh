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

int DecisionDataAgeSeconds()
{
   datetime oldest = iTime(_Symbol, PERIOD_M1, 1);
   for(int index = 1; index < TRADE_TF_COUNT; index++)
   {
      datetime candle = iTime(_Symbol, Timeframes[index], 1);
      if(candle > 0 && (oldest == 0 || candle < oldest)) oldest = candle;
   }
   return oldest > 0 ? (int)(TimeCurrent() - oldest) : -1;
}

void SendEntryDecision(string direction, string result, string reason)
{
   SendWebhook("{\"event_type\":\"ENTRY_DECISION\",\"source\":\"webhook2\",\"symbol\":\"" + JsonEscape(_Symbol)
      + "\",\"direction\":\"" + direction + "\",\"result\":\"" + result + "\",\"reason\":\"" + JsonEscape(reason)
      + "\",\"time\":\"" + DateTimeToText(TimeCurrent()) + "\",\"data_age_seconds\":" + IntegerToString(DecisionDataAgeSeconds()) + "}");
}

string TradeResultText()
{
   return "retcode=" + IntegerToString((int)trade.ResultRetcode())
      + " " + trade.ResultRetcodeDescription();
}

bool TradeResultSucceeded()
{
   uint code = trade.ResultRetcode();
   return code == TRADE_RETCODE_DONE || code == TRADE_RETCODE_DONE_PARTIAL || code == TRADE_RETCODE_PLACED;
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

string AccountActionUrl()
{
   int marker = StringFind(WebhookUrl, "/webhook");
   if(marker >= 0)
      return StringSubstr(WebhookUrl, 0, marker) + "/account-action";
   return WebhookUrl + "/account-action";
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

bool HttpGetAccountAction(string &responseBody)
{
   if(AccountActionSecret == "") return false;
   char data[]; char result[]; string resultHeaders;
   string headers = "Accept: application/json\r\nX-Account-Action-Key: " + AccountActionSecret + "\r\n";
   ResetLastError();
   int code = WebRequest("GET", AccountActionUrl(), headers, WebRequestTimeoutMs, data, result, resultHeaders);
   responseBody = CharArrayToString(result, 0, -1, CP_UTF8);
   return code >= 200 && code < 300;
}

double AccountPipSize(string symbol)
{
   string name = symbol; StringToUpper(name);
   if(StringFind(name, "XAU") >= 0 || StringFind(name, "GOLD") >= 0) return GoldPipSize;
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return (digits == 3 || digits == 5) ? point * 10.0 : point;
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

bool JsonTicketRequested(string json, ulong ticket)
{
   int start = StringFind(json, "\"tickets\":[");
   if(start < 0) return false;
   int end = StringFind(json, "]", start);
   return end > start && StringFind(StringSubstr(json, start, end - start), "\"" + IntegerToString(ticket) + "\"") >= 0;
}

bool MarkActionProcessed(string requestId)
{
   string key = "Webhook2Action:" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ":" + requestId;
   if(GlobalVariableCheck(key)) return false;
   GlobalVariableSet(key, (double)TimeCurrent());
   return true;
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

// Python only queues an action after an authorized, short-lived confirmation.
// Re-reading positions here is the final safety check before any account-wide change.
void ProcessAccountAction()
{
   string body;
   if(!HttpGetAccountAction(body) || body == "" || body == "{}")
      return;
   string action = JsonStringValue(body, "action", "");
   string requestId = JsonStringValue(body, "id", "");
   if(requestId == "" || (action != "be" && action != "close") || !MarkActionProcessed(requestId))
      return;

   int modified = 0, skipped = 0, failed = 0;
   string results = "";
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(!JsonTicketRequested(body, ticket))
         continue;
      string symbol = PositionGetString(POSITION_SYMBOL);
      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double profit = PositionGetDouble(POSITION_PROFIT);
      if(action == "close")
      {
         if(profit <= 0) { skipped++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"skipped\",\"reason\":\"not profitable\"},"; continue; }
         bool requested = trade.PositionClose(ticket);
         if(requested && TradeResultSucceeded()) { modified++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"closed\",\"reason\":\"" + JsonEscape(trade.ResultRetcodeDescription()) + "\"},"; }
         else { failed++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"failed\",\"reason\":\"" + JsonEscape(trade.ResultRetcodeDescription()) + "\"},"; }
         continue;
      }

      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      double pip = AccountPipSize(symbol);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double current = type == POSITION_TYPE_BUY ? SymbolInfoDouble(symbol, SYMBOL_BID) : SymbolInfoDouble(symbol, SYMBOL_ASK);
      double pips = (type == POSITION_TYPE_BUY ? current - entry : entry - current) / pip;
      double eligibility = JsonDoubleValue(body, "eligibility_pips", 30.0);
      double protectedPips = JsonDoubleValue(body, "protected_pips", 10.0);
      if(pips <= eligibility) { skipped++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"skipped\",\"reason\":\"below threshold\"},"; continue; }
      double target = entry + (type == POSITION_TYPE_BUY ? protectedPips * pip : -protectedPips * pip);
      double tick = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      target = NormalizeDouble(tick > 0 ? MathRound(target / tick) * tick : target, digits);
      double minDistance = MathMax((double)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL), (double)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL)) * SymbolInfoDouble(symbol, SYMBOL_POINT);
      if((type == POSITION_TYPE_BUY && current - target < minDistance) || (type == POSITION_TYPE_SELL && target - current < minDistance)) { skipped++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"skipped\",\"reason\":\"broker stop/freeze level\"},"; continue; }
      double oldSl = PositionGetDouble(POSITION_SL);
      bool better = type == POSITION_TYPE_BUY ? oldSl >= target && oldSl > 0 : oldSl <= target && oldSl > 0;
      if(better) { skipped++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"skipped\",\"reason\":\"already better protected\"},"; continue; }
      bool requested = trade.PositionModify(ticket, target, PositionGetDouble(POSITION_TP));
      if(requested && TradeResultSucceeded()) { modified++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"modified\",\"reason\":\"" + JsonEscape(trade.ResultRetcodeDescription()) + "\"},"; }
      else { failed++; results += "{\"ticket\":\"" + IntegerToString(ticket) + "\",\"status\":\"failed\",\"reason\":\"" + JsonEscape(trade.ResultRetcodeDescription()) + "\"},"; }
   }
   if(StringLen(results) > 0) results = StringSubstr(results, 0, StringLen(results) - 1);
   SendWebhook("{\"event_type\":\"ACCOUNT_ACTION_RESULT\",\"request_id\":\"" + JsonEscape(requestId)
      + "\",\"action\":\"" + action + "\",\"modified\":" + IntegerToString(modified)
      + ",\"skipped\":" + IntegerToString(skipped) + ",\"failed\":" + IntegerToString(failed)
      + ",\"retcode\":\"" + IntegerToString((int)trade.ResultRetcode()) + "\""
      + ",\"retcode_description\":\"" + JsonEscape(trade.ResultRetcodeDescription()) + "\""
      + ",\"results\":[" + results + "]}");
}

void MaybeSendAccountReconciliation()
{
   datetime now = TimeCurrent();
   if(now - lastAccountReconcileTime < AccountReconcileSeconds)
      return;
   string positions = "";
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      string symbol = PositionGetString(POSITION_SYMBOL);
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      double pip = AccountPipSize(symbol);
      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double current = type == POSITION_TYPE_BUY ? SymbolInfoDouble(symbol, SYMBOL_BID) : SymbolInfoDouble(symbol, SYMBOL_ASK);
      double pips = (type == POSITION_TYPE_BUY ? current - entry : entry - current) / pip;
      if(positions != "") positions += ",";
      positions += "{\"position_ticket\":\"" + IntegerToString(ticket)
         + "\",\"symbol\":\"" + JsonEscape(symbol) + "\",\"direction\":\"" + (type == POSITION_TYPE_BUY ? "BUY" : "SELL")
         + "\",\"magic_number\":" + IntegerToString(PositionGetInteger(POSITION_MAGIC))
         + "\",\"entry_price\":" + DoubleToString(entry, digits)
         + ",\"current_price\":" + DoubleToString(current, digits)
         + ",\"profit_pips\":" + DoubleToString(pips, 1)
         + ",\"floating_profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2)
         + ",\"duration\":\"" + IntegerToString((long)(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME))) + "s\""
         + ",\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), digits)
         + ",\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), digits) + "}";
   }
   string orders = "";
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0) continue;
      string symbol = OrderGetString(ORDER_SYMBOL);
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      if(orders != "") orders += ",";
      orders += "{\"order_ticket\":\"" + IntegerToString(ticket)
         + "\",\"symbol\":\"" + JsonEscape(symbol) + "\",\"type\":\"" + JsonEscape(EnumToString((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE)))
         + "\",\"volume\":" + DoubleToString(OrderGetDouble(ORDER_VOLUME_CURRENT), 2)
         + ",\"price\":" + DoubleToString(OrderGetDouble(ORDER_PRICE_OPEN), digits)
         + ",\"sl\":" + DoubleToString(OrderGetDouble(ORDER_SL), digits)
         + ",\"tp\":" + DoubleToString(OrderGetDouble(ORDER_TP), digits) + "}";
   }
   string payload = "{\"event_type\":\"ACCOUNT_RECONCILIATION\",\"source\":\"webhook2\""
      + ",\"account_login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))
      + ",\"broker_server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\""
      + ",\"margin_mode\":\"" + JsonEscape(EnumToString((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE))) + "\""
      + ",\"balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2)
      + ",\"equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2)
      + ",\"positions\":[" + positions + "],\"pending_orders\":[" + orders + "]}";
   if(SendWebhook(payload))
      lastAccountReconcileTime = now;
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

bool BuyConfluence(string &reason)
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadTradeEmaValues(0, ema20, ema50))
   {
      SendEaIssue("M1 EMA data unavailable", "Buy confluence check", PERIOD_M1);
      reason = "M1 EMA data unavailable";
      return false;
   }
   if(ema20 <= ema50) { reason = "M1 EMA20 is not above EMA50"; return false; }
   if(!ClosedCandleAboveEma20(1)) { reason = "M5 closed candle is not above EMA20"; return false; }
   if(!ClosedCandleAboveEma20(2)) { reason = "M15 closed candle is not above EMA20"; return false; }
   reason = "";
   return true;
}

bool SellConfluence(string &reason)
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadTradeEmaValues(0, ema20, ema50))
   {
      SendEaIssue("M1 EMA data unavailable", "Sell confluence check", PERIOD_M1);
      reason = "M1 EMA data unavailable";
      return false;
   }
   if(ema50 <= ema20) { reason = "M1 EMA50 is not above EMA20"; return false; }
   if(!ClosedCandleBelowEma20(1)) { reason = "M5 closed candle is not below EMA20"; return false; }
   if(!ClosedCandleBelowEma20(2)) { reason = "M15 closed candle is not below EMA20"; return false; }
   reason = "";
   return true;
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
   TradeConfig config;
   if(!FetchTradeConfig(config))
   {
      SendEntryDecision("?", "FAIL", "Trade configuration unavailable");
      return;
   }

   trade.SetExpertMagicNumber(TradeMagicNumber);
   if(HasOpenPositionForSymbol())
   {
      SendEntryDecision(config.mode, "FAIL", "Existing position already open");
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      return;
   }

   if(config.mode == "BUY")
   {
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      string reason = "";
      if(!BuyConfluence(reason))
      {
         SendEntryDecision("BUY", "FAIL", reason);
         DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
         return;
      }
      double ema20 = 0;
      double ema50 = 0;
      if(!ReadTradeEmaValues(0, ema20, ema50))
      {
         SendEntryDecision("BUY", "FAIL", "M1 EMA data unavailable");
         return;
      }
      double price = ema20 - config.trailPips * PipSize();
      if(price < SymbolInfoDouble(_Symbol, SYMBOL_ASK))
      {
         SendEntryDecision("BUY", "PASS", "Confluence passed; maintaining BUY_LIMIT");
         TrailPendingOrder(ORDER_TYPE_BUY_LIMIT, config.lotSize, price);
      }
      else
         SendEntryDecision("BUY", "FAIL", "Buy limit price is not below ask");
      return;
   }

   if(config.mode == "SELL")
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      string reason = "";
      if(!SellConfluence(reason))
      {
         SendEntryDecision("SELL", "FAIL", reason);
         DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
         return;
      }
      double ema20 = 0;
      double ema50 = 0;
      if(!ReadTradeEmaValues(0, ema20, ema50))
      {
         SendEntryDecision("SELL", "FAIL", "M1 EMA data unavailable");
         return;
      }
      double price = ema20 + config.trailPips * PipSize();
      if(price > SymbolInfoDouble(_Symbol, SYMBOL_BID))
      {
         SendEntryDecision("SELL", "PASS", "Confluence passed; maintaining SELL_LIMIT");
         TrailPendingOrder(ORDER_TYPE_SELL_LIMIT, config.lotSize, price);
      }
      else
         SendEntryDecision("SELL", "FAIL", "Sell limit price is not above bid");
      return;
   }

   if(config.mode == "NOTRADE")
   {
      SendEntryDecision("?", "FAIL", "Trading mode is NOTRADE");
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      return;
   }

   SendEaIssue("Unknown trade mode", config.mode);
   DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
   DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
}

#endif
