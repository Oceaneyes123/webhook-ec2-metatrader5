#ifndef TRADE_MANAGER_MQH
#define TRADE_MANAGER_MQH

struct TradeConfig
{
   string mode;
   double lotSize;
   double trailPips;
   bool keyLevelOrdersEnabled;
};

TradeConfig cachedTradeConfig;
datetime cachedTradeConfigTime = 0;
bool hasCachedTradeConfig = false;
datetime pendingRetryUntil = 0;

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

bool JsonBoolValue(string json, string key, bool fallback)
{
   string marker = "\"" + key + "\":";
   int start = StringFind(json, marker);
   if(start < 0)
      return fallback;
   start += StringLen(marker);
   if(StringSubstr(json, start, 4) == "true") return true;
   if(StringSubstr(json, start, 5) == "false") return false;
   return fallback;
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
      config.lotSize = JsonDoubleValue(body, "lot_size", 0.1);
      config.trailPips = JsonDoubleValue(body, "trail_pips", 20.0);
      config.keyLevelOrdersEnabled = JsonBoolValue(body, "key_level_orders_enabled", true);
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

double NormalizeTradePrice(ENUM_ORDER_TYPE type, double targetPrice)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   double price = type == ORDER_TYPE_BUY_LIMIT
                  ? MathFloor(targetPrice / tick) * tick
                  : MathCeil(targetPrice / tick) * tick;
   return NormalizeDouble(
      price,
      (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)
   );
}

double TradeMinimumPendingDistance()
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = point;

   double stopsDistance =
      (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;
   double freezeDistance =
      (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * point;
   double brokerDistance = MathMax(stopsDistance, freezeDistance);

   double roundedBrokerDistance =
      MathCeil(brokerDistance / tick) * tick;
   return MathMax(tick, roundedBrokerDistance + tick);
}

bool PreparePendingPrice(
   ENUM_ORDER_TYPE type,
   double &targetPrice,
   string &reason
)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double minimumDistance = TradeMinimumPendingDistance();
   if(bid <= 0.0 || ask <= 0.0)
   {
      reason = "Bid/ask unavailable";
      return false;
   }

   if(type == ORDER_TYPE_BUY_LIMIT)
      targetPrice = MathMin(targetPrice, bid - minimumDistance);
   else if(type == ORDER_TYPE_SELL_LIMIT)
      targetPrice = MathMax(targetPrice, ask + minimumDistance);
   else
   {
      reason = "Unsupported pending order type";
      return false;
   }

   targetPrice = NormalizeTradePrice(type, targetPrice);
   if(type == ORDER_TYPE_BUY_LIMIT &&
      targetPrice > bid - minimumDistance)
   {
      reason = "Buy limit is not below Bid by the broker distance";
      return false;
   }
   if(type == ORDER_TYPE_SELL_LIMIT &&
      targetPrice < ask + minimumDistance)
   {
      reason = "Sell limit is not above Ask by the broker distance";
      return false;
   }

   reason = "";
   return true;
}

string EmaTrailOrderComment(ENUM_ORDER_TYPE type, int timeframeIndex)
{
   string direction = type == ORDER_TYPE_BUY_LIMIT ? "buy" : "sell";
   if(timeframeIndex == 0) return "Hermes trailing " + direction + " limit";
   if(timeframeIndex == 1) return "Hermes trailing " + direction + " limit M5";
   return "Hermes trailing " + direction + " limit M15";
}

ulong FindPendingOrder(ENUM_ORDER_TYPE type, string comment)
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol
         && (long)OrderGetInteger(ORDER_MAGIC) == TradeMagicNumber
         && (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type
         && OrderGetString(ORDER_COMMENT) == comment)
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

bool IsTradeSwingHigh(ENUM_TIMEFRAMES timeframe, int shift)
{
   double center = iHigh(_Symbol, timeframe, shift);
   if(center <= 0) return false;
   for(int offset = 1; offset <= KeyLevelSwingStrength; offset++)
      if(center <= iHigh(_Symbol, timeframe, shift - offset)
         || center <= iHigh(_Symbol, timeframe, shift + offset))
         return false;
   return true;
}

bool IsTradeSwingLow(ENUM_TIMEFRAMES timeframe, int shift)
{
   double center = iLow(_Symbol, timeframe, shift);
   if(center <= 0) return false;
   for(int offset = 1; offset <= KeyLevelSwingStrength; offset++)
      if(center >= iLow(_Symbol, timeframe, shift - offset)
         || center >= iLow(_Symbol, timeframe, shift + offset))
         return false;
   return true;
}

string ManualCloseCooldownKey()
{
   return "Webhook2ManualClose:" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))
      + ":" + _Symbol + ":" + IntegerToString(TradeMagicNumber);
}

void StartManualCloseCooldown()
{
   GlobalVariableSet(ManualCloseCooldownKey(), (double)(TimeCurrent() + ManualCloseCooldownMinutes * 60));
}

bool ManualCloseCooldownActive()
{
   double until = 0;
   return GlobalVariableGet(ManualCloseCooldownKey(), until) && until > TimeCurrent();
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

void DeleteEmaTrailOrders(ENUM_ORDER_TYPE type)
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol
         && (long)OrderGetInteger(ORDER_MAGIC) == TradeMagicNumber
         && (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type
         && StringFind(OrderGetString(ORDER_COMMENT), "Hermes trailing ") == 0
         && !trade.OrderDelete(ticket))
         SendEaIssue("EMA trail OrderDelete failed", TradeResultText());
   }
}

void TrailPendingOrder(
   ENUM_ORDER_TYPE type,
   double lotSize,
   double targetPrice,
   string comment,
   ENUM_TIMEFRAMES timeframe
)
{
   string priceReason = "";
   if(!PreparePendingPrice(type, targetPrice, priceReason))
   {
      SendEaIssue("Pending price invalid", priceReason, timeframe);
      return;
   }

   if(TimeCurrent() < pendingRetryUntil)
      return;

   ulong ticket = FindPendingOrder(type, comment);
   if(ticket > 0)
   {
      double currentPrice = OrderGetDouble(ORDER_PRICE_OPEN);
      double currentStopLoss = OrderGetDouble(ORDER_SL);
      double currentTakeProfit = OrderGetDouble(ORDER_TP);
      ENUM_ORDER_TYPE_TIME timeType =
         (ENUM_ORDER_TYPE_TIME)OrderGetInteger(ORDER_TYPE_TIME);
      datetime expiration =
         (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION);

      if(MathAbs(currentPrice - targetPrice) >= PipSize() * 0.1)
      {
         if(!trade.OrderModify(
               ticket, targetPrice, currentStopLoss, currentTakeProfit,
               timeType, expiration
            ))
         {
            pendingRetryUntil = TimeCurrent() + PendingRetrySeconds;
            SendEaIssue(
               "OrderModify failed; retry delayed",
               TradeResultText() + "; retry in " +
               IntegerToString(PendingRetrySeconds) + " seconds"
            );
         }
         else
         {
            pendingRetryUntil = 0;
         }
      }
      return;
   }

   bool placed = false;
   if(type == ORDER_TYPE_BUY_LIMIT)
   {
      placed = trade.BuyLimit(
         lotSize,
         targetPrice,
         _Symbol,
         0,
         0,
         ORDER_TIME_GTC,
         0,
         comment
      );
   }
   else if(type == ORDER_TYPE_SELL_LIMIT)
   {
      placed = trade.SellLimit(
         lotSize,
         targetPrice,
         _Symbol,
         0,
         0,
         ORDER_TIME_GTC,
         0,
         comment
      );
   }

   if(!placed)
   {
      pendingRetryUntil = TimeCurrent() + PendingRetrySeconds;
      SendEaIssue(
         type == ORDER_TYPE_BUY_LIMIT ? "BuyLimit failed" : "SellLimit failed",
         TradeResultText() + "; retry in " + IntegerToString(PendingRetrySeconds) + " seconds",
         timeframe
      );
   }
   else
   {
      pendingRetryUntil = 0;
   }
}

bool IsExactEmaTrailPrice(ENUM_ORDER_TYPE type, double targetPrice)
{
   double normalizedTarget = NormalizeTradePrice(type, targetPrice);
   double preparedTarget = targetPrice;
   string reason = "";
   if(!PreparePendingPrice(type, preparedTarget, reason))
      return false;

   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0.0)
      tick = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   return MathAbs(preparedTarget - normalizedTarget) < tick / 2.0;
}

bool MaintainEmaTrailOrders(ENUM_ORDER_TYPE type, double lotSize, double m1TrailPips)
{
   bool isBuy = type == ORDER_TYPE_BUY_LIMIT;
   double pip = PipSize();
   bool allPricesValid = true;

   for(int index = 0; index < TRADE_TF_COUNT; index++)
   {
      double ema20 = 0;
      double ema50 = 0;
      if(!ReadTradeEmaValues(index, ema20, ema50))
      {
         SendEaIssue("EMA data unavailable", "Trailing order", Timeframes[index]);
         allPricesValid = false;
         continue;
      }

      double offsetPips = index == 0
         ? (isBuy ? -m1TrailPips : m1TrailPips)
         : (index == 1 ? (isBuy ? 10.0 : -10.0) : (isBuy ? 5.0 : -5.0));
      double targetPrice = ema20 + offsetPips * pip;
      string comment = EmaTrailOrderComment(type, index);
      if(IsExactEmaTrailPrice(type, targetPrice))
         TrailPendingOrder(type, lotSize, targetPrice, comment, Timeframes[index]);
      else
      {
         allPricesValid = false;
         ulong ticket = FindPendingOrder(type, comment);
         if(ticket > 0 && !trade.OrderDelete(ticket))
            SendEaIssue("EMA trail OrderDelete failed", TradeResultText(), Timeframes[index]);
      }
   }
   return allPricesValid;
}

bool IsUntouchedKeyLevel(ENUM_TIMEFRAMES timeframe, int shift, double price, bool resistance)
{
   for(int newerShift = shift - 1; newerShift >= 0; newerShift--)
   {
      double reachedPrice = resistance
         ? iHigh(_Symbol, timeframe, newerShift)
         : iLow(_Symbol, timeframe, newerShift);
      if((resistance && reachedPrice >= price) || (!resistance && reachedPrice <= price))
         return false;
   }
   return true;
}

bool IsKeyLevelPendingOrder()
{
   return OrderGetString(ORDER_SYMBOL) == _Symbol
      && (long)OrderGetInteger(ORDER_MAGIC) == TradeMagicNumber
      && StringFind(OrderGetString(ORDER_COMMENT), "Hermes key level") == 0;
}

void DeleteKeyLevelPendingOrders()
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket) || !IsKeyLevelPendingOrder())
         continue;
      if(!trade.OrderDelete(ticket))
         SendEaIssue("Key-level OrderDelete failed", TradeResultText());
   }
}

bool HasKeyLevelPendingOrder(ENUM_ORDER_TYPE type, double price)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(IsKeyLevelPendingOrder()
         && (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type
         && MathAbs(OrderGetDouble(ORDER_PRICE_OPEN) - price) < point / 2.0)
         return true;
   }
   return false;
}

bool HasBetterNearbyKeyLevelOrder(ENUM_ORDER_TYPE type, double price)
{
   double maximumDistance = KeyLevelClusterPips * AccountPipSize(_Symbol);
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket) || !IsKeyLevelPendingOrder()
         || (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) != type)
         continue;
      double existing = OrderGetDouble(ORDER_PRICE_OPEN);
      if(MathAbs(existing - price) <= maximumDistance
         && ((type == ORDER_TYPE_BUY_LIMIT && existing < price)
            || (type == ORDER_TYPE_SELL_LIMIT && existing > price)))
         return true;
   }
   return false;
}

void CancelWorseNearbyKeyLevelOrders(ENUM_ORDER_TYPE type, double price)
{
   double maximumDistance = KeyLevelClusterPips * AccountPipSize(_Symbol);
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket) || !IsKeyLevelPendingOrder()
         || (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) != type)
         continue;
      double existing = OrderGetDouble(ORDER_PRICE_OPEN);
      if(MathAbs(existing - price) <= maximumDistance
         && ((type == ORDER_TYPE_BUY_LIMIT && existing > price)
            || (type == ORDER_TYPE_SELL_LIMIT && existing < price))
         && !trade.OrderDelete(ticket))
         SendEaIssue("Key-level cluster OrderDelete failed", TradeResultText());
   }
}

void PruneNearbyKeyLevelOrders()
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket) || !IsKeyLevelPendingOrder())
         continue;
      ENUM_ORDER_TYPE type = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if((type == ORDER_TYPE_BUY_LIMIT || type == ORDER_TYPE_SELL_LIMIT)
         && HasBetterNearbyKeyLevelOrder(type, OrderGetDouble(ORDER_PRICE_OPEN))
         && !trade.OrderDelete(ticket))
         SendEaIssue("Key-level cluster OrderDelete failed", TradeResultText());
   }
}

datetime UtcDateTime(int year, int month, int day, int hour)
{
   MqlDateTime value = {};
   value.year = year;
   value.mon = month;
   value.day = day;
   value.hour = hour;
   return StructToTime(value);
}

int LastSundayOfMonth(int year, int month)
{
   int nextMonth = month == 12 ? 1 : month + 1;
   int nextYear = month == 12 ? year + 1 : year;
   MqlDateTime value;
   TimeToStruct(UtcDateTime(nextYear, nextMonth, 1, 0) - 86400, value);
   return value.day - value.day_of_week;
}

bool LondonDst(datetime now)
{
   MqlDateTime value;
   TimeToStruct(now, value);
   datetime starts = UtcDateTime(value.year, 3, LastSundayOfMonth(value.year, 3), 1);
   datetime ends = UtcDateTime(value.year, 10, LastSundayOfMonth(value.year, 10), 1);
   return now >= starts && now < ends;
}

bool NewYorkDst(datetime now)
{
   MqlDateTime value;
   TimeToStruct(now, value);
   datetime marchFirst = UtcDateTime(value.year, 3, 1, 0);
   datetime novemberFirst = UtcDateTime(value.year, 11, 1, 0);
   MqlDateTime march, november;
   TimeToStruct(marchFirst, march);
   TimeToStruct(novemberFirst, november);
   int secondSundayMarch = 1 + ((7 - march.day_of_week) % 7) + 7;
   int firstSundayNovember = 1 + ((7 - november.day_of_week) % 7);
   datetime starts = UtcDateTime(value.year, 3, secondSundayMarch, 7);
   datetime ends = UtcDateTime(value.year, 11, firstSundayNovember, 6);
   return now >= starts && now < ends;
}

datetime SessionOpenUtc(datetime date, int session)
{
   MqlDateTime value;
   TimeToStruct(date, value);
   int hour = session == 0 ? 0 : session == 1 ? (LondonDst(date) ? 7 : 8) : (NewYorkDst(date) ? 12 : 13);
   return UtcDateTime(value.year, value.mon, value.day, hour);
}

bool KeyLevelSessionSafetyActive()
{
   datetime now = TimeGMT();
   int window = KeyLevelSessionSafetyMinutes * 60;
   for(int session = 0; session < 3; session++)
   {
      datetime opening = SessionOpenUtc(now, session);
      int secondsToOpen = (int)(opening - now);
      if(secondsToOpen >= -window && secondsToOpen <= window)
         return true;
   }
   return false;
}

bool IsNearCurrentPrice(double price)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   return bid > 0 && ask > 0
      && MathAbs(price - (bid + ask) / 2.0) <= KeyLevelSessionSafetyPips * AccountPipSize(_Symbol);
}

bool IsWithinKeyLevelPlacementDistance(double price)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   return bid > 0 && ask > 0
      && MathAbs(price - (bid + ask) / 2.0) <= KeyLevelMaxDistancePips * AccountPipSize(_Symbol);
}

void CancelNearbyKeyLevelOrdersForSession()
{
   if(!KeyLevelSessionSafetyActive())
      return;
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(IsKeyLevelPendingOrder()
         && IsNearCurrentPrice(OrderGetDouble(ORDER_PRICE_OPEN))
         && !trade.OrderDelete(ticket))
         SendEaIssue("Session-safety key-level OrderDelete failed", TradeResultText());
   }
}

void MaintainKeyLevelOrder(ENUM_ORDER_TYPE type, double price)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double minimumDistance = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;
   price = NormalizeDouble(price, digits);
   if(HasKeyLevelPendingOrder(type, price))
      return;
   if(!IsWithinKeyLevelPlacementDistance(price))
      return;
   if(KeyLevelSessionSafetyActive() && IsNearCurrentPrice(price))
      return;

   if((type == ORDER_TYPE_BUY_LIMIT && price >= SymbolInfoDouble(_Symbol, SYMBOL_ASK) - minimumDistance)
      || (type == ORDER_TYPE_SELL_LIMIT && price <= SymbolInfoDouble(_Symbol, SYMBOL_BID) + minimumDistance))
      return;
   if(HasBetterNearbyKeyLevelOrder(type, price))
      return;

   bool placed = type == ORDER_TYPE_BUY_LIMIT
      ? trade.BuyLimit(KeyLevelLotSize, price, _Symbol, 0, 0, ORDER_TIME_GTC, 0, "Hermes key level")
      : trade.SellLimit(KeyLevelLotSize, price, _Symbol, 0, 0, ORDER_TIME_GTC, 0, "Hermes key level");
   if(placed)
      CancelWorseNearbyKeyLevelOrders(type, price);
   else
      SendEaIssue(type == ORDER_TYPE_BUY_LIMIT ? "Key-level BuyLimit failed" : "Key-level SellLimit failed", TradeResultText());
}

void MaintainUntouchedKeyLevelOrders()
{
   ENUM_TIMEFRAMES timeframes[] = {PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(bid <= 0 || ask <= 0)
      return;
   double currentPrice = (bid + ask) / 2.0;
   for(int index = 0; index < ArraySize(timeframes); index++)
   {
      ENUM_TIMEFRAMES timeframe = timeframes[index];
      int maximumShift = MathMin(KeyLevelLookbackBars, Bars(_Symbol, timeframe) - KeyLevelSwingStrength - 1);
      for(int shift = KeyLevelSwingStrength + 1; shift <= maximumShift; shift++)
      {
         if(IsTradeSwingHigh(timeframe, shift))
         {
            double resistance = iHigh(_Symbol, timeframe, shift);
            if(resistance > currentPrice && IsUntouchedKeyLevel(timeframe, shift, resistance, true))
               MaintainKeyLevelOrder(ORDER_TYPE_SELL_LIMIT, resistance);
         }
         if(IsTradeSwingLow(timeframe, shift))
         {
            double support = iLow(_Symbol, timeframe, shift);
            if(support < currentPrice && IsUntouchedKeyLevel(timeframe, shift, support, false))
               MaintainKeyLevelOrder(ORDER_TYPE_BUY_LIMIT, support);
         }
      }
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
   if(ManualCloseCooldownActive())
   {
      SendEntryDecision(config.mode, "FAIL", "Manual close cooldown active");
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      return;
   }
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
         return;
      }
      bool allPricesValid = MaintainEmaTrailOrders(
         ORDER_TYPE_BUY_LIMIT, config.lotSize, config.trailPips
      );
      SendEntryDecision(
         "BUY",
         allPricesValid ? "PASS" : "FAIL",
         allPricesValid
            ? "Confluence passed; maintaining M1, M5, and M15 BUY_LIMITs"
            : "One or more BUY_LIMIT prices violate the broker distance"
      );
      return;
   }

   if(config.mode == "SELL")
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      string reason = "";
      if(!SellConfluence(reason))
      {
         SendEntryDecision("SELL", "FAIL", reason);
         return;
      }
      bool allPricesValid = MaintainEmaTrailOrders(
         ORDER_TYPE_SELL_LIMIT, config.lotSize, config.trailPips
      );
      SendEntryDecision(
         "SELL",
         allPricesValid ? "PASS" : "FAIL",
         allPricesValid
            ? "Confluence passed; maintaining M1, M5, and M15 SELL_LIMITs"
            : "One or more SELL_LIMIT prices violate the broker distance"
      );
      return;
   }

   if(config.mode == "AUTO")
   {
      if(!config.keyLevelOrdersEnabled)
      {
         DeleteKeyLevelPendingOrders();
      }
      else
      {
         CancelNearbyKeyLevelOrdersForSession();
         PruneNearbyKeyLevelOrders();
         MaintainUntouchedKeyLevelOrders();
      }

      string reason = "";
      if(BuyConfluence(reason))
      {
         DeleteEmaTrailOrders(ORDER_TYPE_SELL_LIMIT);
         bool allPricesValid = MaintainEmaTrailOrders(
            ORDER_TYPE_BUY_LIMIT, config.lotSize, config.trailPips
         );
         SendEntryDecision(
            "AUTO",
            allPricesValid ? "PASS" : "FAIL",
            allPricesValid
               ? "Buy confluence passed; maintaining M1, M5, and M15 BUY_LIMITs"
               : "One or more BUY_LIMIT prices violate the broker distance"
         );
         return;
      }
      if(SellConfluence(reason))
      {
         DeleteEmaTrailOrders(ORDER_TYPE_BUY_LIMIT);
         bool allPricesValid = MaintainEmaTrailOrders(
            ORDER_TYPE_SELL_LIMIT, config.lotSize, config.trailPips
         );
         SendEntryDecision(
            "AUTO",
            allPricesValid ? "PASS" : "FAIL",
            allPricesValid
               ? "Sell confluence passed; maintaining M1, M5, and M15 SELL_LIMITs"
               : "One or more SELL_LIMIT prices violate the broker distance"
         );
         return;
      }

      DeleteEmaTrailOrders(ORDER_TYPE_BUY_LIMIT);
      DeleteEmaTrailOrders(ORDER_TYPE_SELL_LIMIT);
      SendEntryDecision("AUTO", "FAIL", reason);
      return;
   }

   if(config.mode == "NOTRADE")
   {
      SendEntryDecision("?", "FAIL", "Trading mode is NOTRADE; accepted orders retained");
      return;
   }

   SendEaIssue("Unknown trade mode", config.mode);
}

#endif
