#ifndef WEBHOOK_COMMON_MQH
#define WEBHOOK_COMMON_MQH

struct Candle
{
   double open;
   double high;
   double low;
   double close;
};

string TimeframeToText(ENUM_TIMEFRAMES timeframe)
{
   switch(timeframe)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      default:         return EnumToString(timeframe);
   }
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   StringReplace(value, "\t", "\\t");
   return value;
}

string DateTimeToText(datetime value)
{
   return TimeToString(value, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
}

string JsonNumberOrNull(bool available, double value, int digits)
{
   return available ? DoubleToString(value, digits) : "null";
}

void PrintWebRequestHelp(string url, int errorCode)
{
   Print("Webhook failed.");
   Print("MT5 Error Code: ", errorCode);
   Print("URL: ", url);

   if(errorCode == 4014)
   {
      Print("Meaning: WebRequest is not allowed for this URL.");
      Print("Fix:");
      Print("1. Go to Tools > Options > Expert Advisors");
      Print("2. Enable 'Allow WebRequest for listed URL'");
      Print("3. Add:");
      Print("   http://127.0.0.1");
      Print("   http://127.0.0.1:8000");
      Print("   http://127.0.0.1:8000/webhook");
   }
   else if(errorCode == 5200)
      Print("Meaning: Invalid URL.");
   else if(errorCode == 5201)
      Print("Meaning: Failed to connect to the server.");
   else if(errorCode == 5202)
      Print("Meaning: Timeout.");
   else if(errorCode == 5203)
      Print("Meaning: HTTP request failed.");
}

bool SendWebhook(string payload)
{
   if(WebhookUrl == "")
   {
      Print("Webhook URL is empty.");
      return false;
   }

   char data[];
   int dataSize = StringToCharArray(payload, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(dataSize > 0)
      ArrayResize(data, dataSize - 1);

   char result[];
   string resultHeaders;
   string headers =
      "Content-Type: application/json\r\n"
      "Accept: application/json\r\n"
      "User-Agent: MT5-Webhook\r\n";

   ResetLastError();
   int responseCode = WebRequest(
      "POST",
      WebhookUrl,
      headers,
      WebRequestTimeoutMs,
      data,
      result,
      resultHeaders
   );
   int mt5Error = GetLastError();
   string responseBody = CharArrayToString(result, 0, -1, CP_UTF8);

   if(PrintDebugLogs)
   {
      Print("========== WEBHOOK DEBUG START ==========");
      Print("Webhook URL: ", WebhookUrl);
      Print("HTTP Code: ", responseCode);
      Print("MT5 Error Code: ", mt5Error);
      Print("Payload Size: ", ArraySize(data));
      Print("Payload: ", payload);
      Print("Response Headers: ", resultHeaders);
      Print("Response Body: ", responseBody);
      Print("========== WEBHOOK DEBUG END ==========");
   }

   if(responseCode == -1)
   {
      PrintWebRequestHelp(WebhookUrl, mt5Error);
      return false;
   }
   if(responseCode < 200 || responseCode >= 300)
   {
      Print("Webhook returned HTTP ", responseCode);
      return false;
   }
   return true;
}

Candle ReadCandle(ENUM_TIMEFRAMES timeframe, int shift)
{
   Candle candle;
   candle.open = iOpen(_Symbol, timeframe, shift);
   candle.high = iHigh(_Symbol, timeframe, shift);
   candle.low = iLow(_Symbol, timeframe, shift);
   candle.close = iClose(_Symbol, timeframe, shift);
   return candle;
}

double CandleBody(const Candle &candle)
{
   return MathAbs(candle.close - candle.open);
}

double CandleRange(const Candle &candle)
{
   return candle.high - candle.low;
}

double UpperWick(const Candle &candle)
{
   return candle.high - MathMax(candle.open, candle.close);
}

double LowerWick(const Candle &candle)
{
   return MathMin(candle.open, candle.close) - candle.low;
}

bool IsBullishCandle(const Candle &candle)
{
   return candle.close > candle.open;
}

bool IsBearishCandle(const Candle &candle)
{
   return candle.close < candle.open;
}

bool HasValidBody(const Candle &candle)
{
   return CandleRange(candle) > 0 && CandleBody(candle) > 0;
}

bool SendEaHeartbeat(string source)
{
   string payload =
      "{\"event_type\":\"EA_HEARTBEAT\""
      ",\"source\":\"" + JsonEscape(source) + "\""
      ",\"symbol\":\"" + JsonEscape(_Symbol) + "\""
      ",\"status\":\"running\"}";
   return SendWebhook(payload);
}

bool SendTradeCloseNotification(string reason, double profit, double balance)
{
   string payload = StringFormat(
      "{\"event_type\":\"TRADE_CLOSE\",\"source\":\"webhook2\""
      ",\"symbol\":\"%s\",\"reason\":\"%s\",\"profit\":%.2f,\"balance\":%.2f}",
      _Symbol, reason, profit, balance
   );
   return SendWebhook(payload);
}

bool SendTradeOpenNotification(string source, ENUM_POSITION_TYPE type, double price, double volume, double sl, double tp)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   string typeText = (type == POSITION_TYPE_BUY) ? "BUY" : "SELL";
   string payload = StringFormat(
      "{\"event_type\":\"TRADE_OPEN\",\"source\":\"%s\""
      ",\"symbol\":\"%s\",\"type\":\"%s\",\"price\":%s,\"volume\":%.2f"
      ",\"sl\":%s,\"tp\":%s}",
      source, _Symbol, typeText,
      DoubleToString(price, digits), volume,
      sl > 0 ? DoubleToString(sl, digits) : "null",
      tp > 0 ? DoubleToString(tp, digits) : "null"
   );
   return SendWebhook(payload);
}

#endif
