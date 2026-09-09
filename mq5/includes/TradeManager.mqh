#ifndef TRADE_MANAGER_MQH
#define TRADE_MANAGER_MQH

struct TradeConfig
{
   string mode;
   double lotSize;
   double trailPips;
   string strategyDirection;
   string strategyReason;
   string setupId;
   double entry, sl, tp, expires, minRR, tolerance;
   double breakevenR, protectR, protectLockR, partialR, partialFraction, trailR;
   string trailingMethod;
   bool keyLevelOrdersEnabled;
};

TradeConfig cachedTradeConfig;
datetime cachedTradeConfigTime = 0;
bool hasCachedTradeConfig = false;
// Per-timeframe retry lock: a failure on one EMA timeframe (M1/M5/M15) must
// not starve the others, so each index gets its own retry deadline.
datetime pendingRetryUntil[TRADE_TF_COUNT] = {0, 0, 0};

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
   string quote = "&bid=" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), _Digits)
      + "&ask=" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), _Digits)
      + "&tick_size=" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), _Digits)
      + "&stops_distance=" + DoubleToString(SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point, _Digits)
      + "&quote_time=" + IntegerToString((long)(SymbolInfoInteger(_Symbol, SYMBOL_TIME) - (TimeTradeServer() - TimeGMT())))
      + "&account=" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))
      + "&broker_server=" + UrlEncode(AccountInfoString(ACCOUNT_SERVER));
   return WebRequestAllowListUrl(WebhookUrl)
      + "/trade-config?symbol=" + UrlEncode(_Symbol) + quote;
}

string AccountActionUrl()
{
   return WebRequestAllowListUrl(WebhookUrl) + "/account-action";
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
         || character == 45 || character == 43 || character == 101 || character == 69)
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
      config.strategyDirection = JsonStringValue(body, "strategy_direction", "WAIT");
      config.strategyReason = JsonStringValue(body, "strategy_reason", "Python strategy unavailable");
      config.setupId = JsonStringValue(body, "setup_id", "");
      config.entry = JsonDoubleValue(body, "entry", 0);
      config.sl = JsonDoubleValue(body, "sl", 0);
      config.tp = JsonDoubleValue(body, "tp", 0);
      config.expires = JsonDoubleValue(body, "expires_at", 0);
      config.minRR = JsonDoubleValue(body, "min_rr", 0);
      config.tolerance = JsonDoubleValue(body, "execution_tolerance", 0);
      config.breakevenR = JsonDoubleValue(body, "breakeven_r", 0);
      config.protectR = JsonDoubleValue(body, "protect_r", 0);
      config.protectLockR = JsonDoubleValue(body, "protect_lock_r", 0);
      config.partialR = JsonDoubleValue(body, "partial_close_r", 0);
      config.partialFraction = JsonDoubleValue(body, "partial_fraction", 0);
      config.trailR = JsonDoubleValue(body, "trail_start_r", 0);
      config.trailingMethod = JsonStringValue(body, "trailing_method", "off");
      config.keyLevelOrdersEnabled = JsonBoolValue(body, "key_level_orders_enabled", true);
      if(config.lotSize <= 0 || config.trailPips < 0)
      {
         SendEaIssue("Invalid trade config", body);
         // Fall back to stale cache if available
         if(hasCachedTradeConfig && cachedTradeConfig.mode != "AUTO" && now - cachedTradeConfigTime <= TradeConfigMaxStaleSeconds)
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
   if(hasCachedTradeConfig && cachedTradeConfig.mode != "AUTO" && now - cachedTradeConfigTime <= TradeConfigMaxStaleSeconds)
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
         + ",\"entry_price\":" + DoubleToString(entry, digits)
         + ",\"current_price\":" + DoubleToString(current, digits)
         + ",\"profit_pips\":" + DoubleToString(pips, 1)
         + ",\"floating_profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2)
         + ",\"duration\":\"" + IntegerToString((long)(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME))) + "s\""
         + ",\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), digits)
         + ",\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), digits)
         + ",\"position_id\":\"" + IntegerToString(PositionGetInteger(POSITION_IDENTIFIER)) + "\""
         + StrategyTelemetry(PositionGetString(POSITION_COMMENT)) + "}";
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
   int timeframeIndex,
   ENUM_TIMEFRAMES timeframe
)
{
   string priceReason = "";
   if(!PreparePendingPrice(type, targetPrice, priceReason))
   {
      SendEaIssue("Pending price invalid", priceReason, timeframe);
      return;
   }

   if(TimeCurrent() < pendingRetryUntil[timeframeIndex])
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
            pendingRetryUntil[timeframeIndex] = TimeCurrent() + PendingRetrySeconds;
            SendEaIssue(
               "OrderModify failed; retry delayed",
               TradeResultText() + "; retry in " +
               IntegerToString(PendingRetrySeconds) + " seconds"
            );
         }
         else
         {
            pendingRetryUntil[timeframeIndex] = 0;
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
      pendingRetryUntil[timeframeIndex] = TimeCurrent() + PendingRetrySeconds;
      SendEaIssue(
         type == ORDER_TYPE_BUY_LIMIT ? "BuyLimit failed" : "SellLimit failed",
         TradeResultText() + "; retry in " + IntegerToString(PendingRetrySeconds) + " seconds",
         timeframe
      );
   }
   else
   {
      pendingRetryUntil[timeframeIndex] = 0;
   }
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
      // Clamp-and-place: when the raw EMA-based target sits inside the
      // broker minimum distance, PreparePendingPrice() adjusts it to the
      // nearest valid price (ask+minDist for sells, bid-minDist for buys)
      // instead of rejecting the order. This keeps all TRADE_TF_COUNT
      // EMA trail orders alive even when price hugs the EMA.
      string priceReason = "";
      if(!PreparePendingPrice(type, targetPrice, priceReason))
      {
         SendEaIssue("Pending price invalid", priceReason, Timeframes[index]);
         allPricesValid = false;
         continue;
      }
      TrailPendingOrder(type, lotSize, targetPrice, comment, index, Timeframes[index]);
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

string StrategyKey(string id, string field)
{
   return "Strategy:" + id + ":" + field;
}

double StrategyLockR(double currentR, double beR, double protectR, double lockedR)
{
   double result = -1;
   if(beR > 0 && currentR >= beR) result = 0;
   if(protectR > 0 && currentR >= protectR) result = MathMax(result, lockedR);
   return result;
}

double StrategyPartialVolume(double original, double current, double step, double minimum, double fraction)
{
   if(step <= 0 || fraction <= 0 || fraction >= 1 || current < original - step / 2) return 0;
   double amount = MathFloor(original * fraction / step + 1e-8) * step;
   return amount >= minimum && current - amount >= minimum ? amount : 0;
}

bool StrategyManagementChecks()
{
   // Runnable on EA initialization; these are the same functions used below.
   return StrategyLockR(0.99, 1, 1.5, 0.5) == -1
      && StrategyLockR(1, 1, 1.5, 0.5) == 0
      && StrategyLockR(1.5, 1, 1.5, 0.5) == 0.5
      && StrategyLockR(3, 0, 0, 0.5) == -1
      && MathAbs(StrategyPartialVolume(1, 1, 0.1, 0.1, 0.5) - 0.5) < 1e-8
      && StrategyPartialVolume(1, 0.5, 0.1, 0.1, 0.5) == 0
      && StrategyPartialVolume(0.01, 0.01, 0.01, 0.01, 0.5) == 0;
}

void SendStrategyTransaction(string payload, string id, ulong deal)
{
   FolderCreate("strategy_events");
   string path = "strategy_events\\" + id + "_" + IntegerToString(deal) + ".json";
   int file = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_UNICODE);
   if(file == INVALID_HANDLE) { Print("Cannot persist strategy deal ", deal); SendWebhook(payload); return; }
   FileWriteString(file, payload);
   FileFlush(file);
   FileClose(file);
   if(SendWebhook(payload)) FileDelete(path);
}

void ReplayStrategyTransactions()
{
   static datetime lastReplay = 0;
   if(TimeGMT() - lastReplay < 10) return;
   lastReplay = TimeGMT();
   string name;
   long search = FileFindFirst("strategy_events\\*.json", name);
   if(search == INVALID_HANDLE) return;
   int count = 0;
   do
   {
      string path = "strategy_events\\" + name;
      int file = FileOpen(path, FILE_READ | FILE_TXT | FILE_UNICODE);
      if(file == INVALID_HANDLE) continue;
      string payload = FileReadString(file);
      FileClose(file);
      if(!SendWebhook(payload)) break;
      FileDelete(path);
      count++;
   } while(count < 5 && FileFindNext(search, name));
   FileFindClose(search);
}

double StrategyValue(string id, string field)
{
   double value = 0;
   GlobalVariableGet(StrategyKey(id, field), value);
   return value;
}

void StrategySet(string id, string field, double value)
{
   GlobalVariableSet(StrategyKey(id, field), value);
}

string StrategyId(string comment)
{
   return StringFind(comment, "S:") == 0 && StringLen(comment) >= 18 ? StringSubstr(comment, 2, 16) : "";
}

string StrategyTelemetry(string comment)
{
   string id = StrategyId(comment);
   if(id == "") return "";
   return ",\"setup_id\":\"" + id + "\""
      + ",\"initial_risk\":" + DoubleToString(StrategyValue(id, "risk"), 8)
      + ",\"risk_cash\":" + DoubleToString(StrategyValue(id, "cash"), 8)
      + ",\"risk_confirmed\":" + (StrategyValue(id, "initialized") > 0 ? "true" : "false")
      + ",\"initial_volume\":" + DoubleToString(StrategyValue(id, "volume"), 8)
      + ",\"current_r\":" + DoubleToString(StrategyValue(id, "current"), 6)
      + ",\"mfe_r\":" + DoubleToString(StrategyValue(id, "mfe"), 6)
      + ",\"mae_r\":" + DoubleToString(StrategyValue(id, "mae"), 6);
}

void StrategyExecutionDecision(string id, string result, string reason)
{
   SendWebhook("{\"event_type\":\"ENTRY_DECISION\",\"strategy\":true,\"setup_id\":\"" + id
      + "\",\"symbol\":\"" + JsonEscape(_Symbol) + "\",\"result\":\"" + result
      + "\",\"reason\":\"" + JsonEscape(reason) + "\"}");
}

void UpdateStrategyMetrics()
{
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol
         || PositionGetInteger(POSITION_MAGIC) != TradeMagicNumber) continue;
      string id = StrategyId(PositionGetString(POSITION_COMMENT));
      if(id == "" || StrategyValue(id, "sl") <= 0) continue;
      double sign = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double volume = PositionGetDouble(POSITION_VOLUME);
      if(StrategyValue(id, "initialized") == 0 || volume > StrategyValue(id, "volume") + SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP) / 2)
      {
         double risk = sign * (entry - StrategyValue(id, "sl"));
         double cash = 0;
         if(risk <= 0 || !OrderCalcProfit(sign > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol,
            volume, entry, StrategyValue(id, "sl"), cash) || cash >= 0) continue;
         StrategySet(id, "risk", risk);
         StrategySet(id, "cash", -cash);
         StrategySet(id, "volume", volume);
         StrategySet(id, "entry", entry);
         StrategySet(id, "initialized", 1);
      }
      double risk = StrategyValue(id, "risk");
      if(risk <= 0) continue;
      double price = SymbolInfoDouble(_Symbol, sign > 0 ? SYMBOL_BID : SYMBOL_ASK);
      double r = sign * (price - entry) / risk;
      StrategySet(id, "current", r);
      StrategySet(id, "mfe", MathMax(StrategyValue(id, "mfe"), r));
      StrategySet(id, "mae", MathMax(StrategyValue(id, "mae"), -r));
   }
}

void ManageStrategyPositions()
{
   UpdateStrategyMetrics();
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol
         || PositionGetInteger(POSITION_MAGIC) != TradeMagicNumber) continue;
      string id = StrategyId(PositionGetString(POSITION_COMMENT));
      double risk = StrategyValue(id, "risk");
      if(id == "" || risk <= 0 || StrategyValue(id, "initialized") == 0) continue;
      double sign = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double r = StrategyValue(id, "current");
      double currentSL = PositionGetDouble(POSITION_SL);
      double sl = currentSL;
      double tp = PositionGetDouble(POSITION_TP);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double price = SymbolInfoDouble(_Symbol, sign > 0 ? SYMBOL_BID : SYMBOL_ASK);
      double be = StrategyValue(id, "be");
      double protect = StrategyValue(id, "protect");
      double lockR = StrategyLockR(r, be, protect, StrategyValue(id, "lock"));
      double protectedSL = entry + sign * risk * lockR;
      if(lockR >= 0 && (sl == 0 || sign * (protectedSL - sl) > 0)) sl = protectedSL;
      double trail = StrategyValue(id, "trail");
      if(trail > 0 && r >= trail && StrategyValue(id, "method") > 0)
      {
         double candidate = sign > 0 ? iLow(_Symbol, PERIOD_M5, 1) : iHigh(_Symbol, PERIOD_M5, 1);
         if(StrategyValue(id, "method") == 2)
         {
            double ema20, ema50;
            candidate = ReadTradeEmaValues(1, ema20, ema50) ? ema20 : 0;
         }
         if(candidate > 0 && sign * (candidate - entry) > 0 && (sl == 0 || sign * (candidate - sl) > 0)) sl = candidate;
      }
      double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tick <= 0) continue;
      sl = NormalizeDouble((sign > 0 ? MathFloor(sl / tick) : MathCeil(sl / tick)) * tick, _Digits);
      double distance = MathMax(SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL),
                                SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL)) * _Point;
      if(sl > 0 && sl != currentSL && sign * (price - sl) > distance
         && (currentSL == 0 || sign * (sl - currentSL) > 0))
      {
         if(!trade.PositionModify(ticket, sl, tp) || !TradeResultSucceeded())
            SendEaIssue("Strategy stop modification failed", TradeResultText());
      }
      double partial = StrategyValue(id, "partial");
      double fraction = StrategyValue(id, "fraction");
      double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
      if(partial <= 0 || fraction <= 0 || r < partial || step <= 0 || StrategyValue(id, "partial_done") != 0) continue;
      double original = StrategyValue(id, "volume");
      // A manual or previously successful partial counts too, including after restart.
      if(volume < original - step / 2) { StrategySet(id, "partial_done", 1); continue; }
      double minimum = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
      double amount = StrategyPartialVolume(original, volume, step, minimum, fraction);
      if(amount <= 0) continue;
      StrategySet(id, "partial_done", 1); // uncertain broker responses must never double-close
      GlobalVariablesFlush();
      bool requested = false;
      if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
         requested = trade.PositionClosePartial(ticket, amount);
      else
      {
         // Netting reduction is explicitly tied to the selected position, not a new thesis.
         MqlTradeRequest request = {};
         MqlTradeResult result = {};
         request.action = TRADE_ACTION_DEAL;
         request.position = ticket;
         request.symbol = _Symbol;
         request.magic = TradeMagicNumber;
         request.volume = amount;
         request.type = sign > 0 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
         request.price = price;
         request.comment = "S:" + id;
         int filling = (int)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
         request.type_filling = (filling & SYMBOL_FILLING_FOK) != 0 ? ORDER_FILLING_FOK : ORDER_FILLING_IOC;
         requested = OrderSend(request, result) && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_DONE_PARTIAL);
         if(!requested) SendEaIssue("Strategy partial reduction failed", result.comment);
         continue;
      }
      if(!requested || !TradeResultSucceeded()) SendEaIssue("Strategy partial close failed", TradeResultText());
   }
}

void ExecuteStrategy(const TradeConfig &config)
{
   if(config.strategyDirection != "BUY" && config.strategyDirection != "SELL") return;
   string id = config.setupId;
   if(id == "" || StrategyValue(id, "used") != 0) return;
   if(ManualCloseCooldownActive() || HasAnyPositionForSymbol()) return;
   // Pending orders from any EA/manual action can fill into the same thesis.
   for(int i = OrdersTotal() - 1; i >= 0; i--)
      if(OrderGetTicket(i) > 0 && OrderGetString(ORDER_SYMBOL) == _Symbol) return;
   double sign = config.strategyDirection == "BUY" ? 1 : -1;
   double price = SymbolInfoDouble(_Symbol, sign > 0 ? SYMBOL_ASK : SYMBOL_BID);
   double risk = sign * (price - config.sl);
   double reward = sign * (config.tp - price);
   double minimum = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(TimeGMT() >= (datetime)config.expires || risk <= minimum + spread || reward <= minimum + spread
      || config.sl <= 0 || config.tp <= 0 || config.minRR <= 0 || reward / risk < config.minRR
      || MathAbs(price - config.entry) > config.tolerance)
   {
      StrategySet(id, "used", 1);
      StrategyExecutionDecision(id, "FAIL", "Expired offer, price drift or insufficient executable R:R");
      return;
   }
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double volume = step > 0 ? MathFloor(config.lotSize / step + 1e-8) * step : 0;
   if(volume < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN) || volume > SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX)) return;
   double cash = 0;
   if(!OrderCalcProfit(sign > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, _Symbol, volume, price, config.sl, cash) || cash >= 0) return;
   string lock = "StrategyLock:" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ":" + _Symbol;
   GlobalVariableTemp(lock);
   double until = GlobalVariableGet(lock);
   if(until > TimeGMT() || !GlobalVariableSetOnCondition(lock, (double)(TimeGMT() + 30), until)) return;
   if(HasAnyPositionForSymbol()) { GlobalVariableSet(lock, 0); return; }
   StrategySet(id, "used", 1);
   StrategySet(id, "sl", config.sl);
   StrategySet(id, "risk", risk);
   StrategySet(id, "cash", -cash);
   StrategySet(id, "volume", volume);
   StrategySet(id, "entry", price);
   StrategySet(id, "sign", sign);
   StrategySet(id, "be", config.breakevenR);
   StrategySet(id, "protect", config.protectR);
   StrategySet(id, "lock", config.protectLockR);
   StrategySet(id, "partial", config.partialR);
   StrategySet(id, "fraction", config.partialFraction);
   StrategySet(id, "trail", config.trailR);
   StrategySet(id, "method", config.trailingMethod == "ema" ? 2 : config.trailingMethod == "structure" ? 1 : 0);
   GlobalVariablesFlush();
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetDeviationInPoints((ulong)MathFloor(config.tolerance / _Point));
   bool requested = sign > 0
      ? trade.Buy(volume, _Symbol, price, config.sl, config.tp, "S:" + id)
      : trade.Sell(volume, _Symbol, price, config.sl, config.tp, "S:" + id);
   bool succeeded = requested && TradeResultSucceeded();
   UpdateStrategyMetrics();
   GlobalVariablesFlush();
   StrategyExecutionDecision(id, succeeded ? "PASS" : "FAIL", TradeResultText());
   GlobalVariableSet(lock, 0);
}

void ManageTrading()
{
   ManageStrategyPositions();
   TradeConfig config;
   if(!FetchTradeConfig(config))
   {
      SendEntryDecision("?", "FAIL", "Trade configuration unavailable");
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      return;
   }

   trade.SetExpertMagicNumber(TradeMagicNumber);
   static string previousMode = "";
   if(config.mode != previousMode)
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      previousMode = config.mode;
   }
   if(config.mode == "AUTO")
   {
      DeletePendingOrders(ORDER_TYPE_BUY_LIMIT);
      DeletePendingOrders(ORDER_TYPE_SELL_LIMIT);
      ExecuteStrategy(config);
      return;
   }
   if(config.mode == "EMA")
   {
      string reason = "";
      config.mode = BuyConfluence(reason) ? "BUY" : SellConfluence(reason) ? "SELL" : "NOTRADE";
   }
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

   if(config.mode == "LEVEL")
   {
      if(!config.keyLevelOrdersEnabled)
      {
         DeleteKeyLevelPendingOrders();
      }
      else
      {
         CancelNearbyKeyLevelOrdersForSession();
         PruneNearbyKeyLevelOrders();
         SendEntryDecision("LEVEL", "PASS", "Explicit legacy untouched M30-D1 key-level limits");
         MaintainUntouchedKeyLevelOrders();
      }
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
