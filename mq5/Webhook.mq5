//+------------------------------------------------------------------+
//|        Multi-Timeframe Candlestick Pattern Webhook EA             |
//|        Sends webhook alerts for supported candle patterns         |
//+------------------------------------------------------------------+
#property strict
#property version "1.06"

#include <Trade/Trade.mqh>

input string WebhookUrl = "http://127.0.0.1:8000/webhook";

input int  WebRequestTimeoutMs = 5000;
input bool PrintDebugLogs      = true;
input long TradeMagicNumber = 260628;
input int EaIssueRepeatSeconds = 60;
input double MaxBodyPercent = 35.0;
input double MinLongWickBodyRatio = 2.0;
input double MaxSmallWickBodyRatio = 1.0;
input double StrongCandleBodyPercent = 50.0;
input int LevelLookbackBars = 100;
input int SwingStrength = 2;
input int AtrPeriod = 14;
input double MinFvgAtrRatio = 0.25;

#define TF_COUNT 6

ENUM_TIMEFRAMES Timeframes[TF_COUNT] =
{
   PERIOD_M1,
   PERIOD_M5,
   PERIOD_M15,
   PERIOD_M30,
   PERIOD_H1,
   PERIOD_H4
};

datetime lastBarTimes[TF_COUNT];
bool hasSnapshot[TF_COUNT];
int ema20Handles[TF_COUNT];
int ema50Handles[TF_COUNT];
int rsiHandles[TF_COUNT];
CTrade trade;
string lastEaIssueKey = "";
datetime lastEaIssueTime = 0;

struct TradeConfig
{
   string mode;
   double lotSize;
   double trailPips;
};

struct Candle
{
   double open;
   double high;
   double low;
   double close;
};

struct LevelResult
{
   bool hasSupport;
   double support;
   bool hasResistance;
   double resistance;
   bool hasFib;
   string fibDirection;
   double fibStart;
   double fibEnd;
   double fib382;
   double fib500;
   double fib618;
   bool hasBullishFvg;
   double bullishFvgLow;
   double bullishFvgHigh;
   bool hasBearishFvg;
   double bearishFvgLow;
   double bearishFvgHigh;
   bool hasPreviousDay;
   double previousDayHigh;
   double previousDayLow;
};

//+------------------------------------------------------------------+
//| Timeframe to text                                                |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| Escape JSON string values                                        |
//+------------------------------------------------------------------+
string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   StringReplace(value, "\t", "\\t");

   return value;
}

//+------------------------------------------------------------------+
//| Convert datetime to string                                       |
//+------------------------------------------------------------------+
string DateTimeToText(datetime value)
{
   return TimeToString(value, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
}

string JsonNumberOrNull(bool available, double value, int digits)
{
   return available ? DoubleToString(value, digits) : "null";
}

string BuildLevelsJson(const LevelResult &levels, int digits)
{
   string fib = "null";
   if(levels.hasFib)
   {
      fib =
         "{"
            "\"direction\":\"" + levels.fibDirection + "\","
            "\"start\":" + DoubleToString(levels.fibStart, digits) + ","
            "\"end\":" + DoubleToString(levels.fibEnd, digits) + ","
            "\"38.2\":" + DoubleToString(levels.fib382, digits) + ","
            "\"50.0\":" + DoubleToString(levels.fib500, digits) + ","
            "\"61.8\":" + DoubleToString(levels.fib618, digits) +
         "}";
   }

   string bullishFvg = "null";
   if(levels.hasBullishFvg)
   {
      bullishFvg =
         "{"
            "\"low\":" + DoubleToString(levels.bullishFvgLow, digits) + ","
            "\"high\":" + DoubleToString(levels.bullishFvgHigh, digits) +
         "}";
   }

   string bearishFvg = "null";
   if(levels.hasBearishFvg)
   {
      bearishFvg =
         "{"
            "\"low\":" + DoubleToString(levels.bearishFvgLow, digits) + ","
            "\"high\":" + DoubleToString(levels.bearishFvgHigh, digits) +
         "}";
   }

   return
      "{"
         "\"support\":" +
            JsonNumberOrNull(levels.hasSupport, levels.support, digits) + ","
         "\"resistance\":" +
            JsonNumberOrNull(levels.hasResistance, levels.resistance, digits) + ","
         "\"fib\":" + fib + ","
         "\"bullish_fvg\":" + bullishFvg + ","
         "\"bearish_fvg\":" + bearishFvg + ","
         "\"previous_day_high\":" +
            JsonNumberOrNull(
               levels.hasPreviousDay, levels.previousDayHigh, digits
            ) + ","
         "\"previous_day_low\":" +
            JsonNumberOrNull(
               levels.hasPreviousDay, levels.previousDayLow, digits
            ) +
      "}";
}

string BuildSnapshotPayload(
   ENUM_TIMEFRAMES timeframe,
   datetime candleTime,
   const Candle &candle,
   bool notifyPatterns,
   string patternsJson,
   bool hasEma,
   double ema20,
   double ema50,
   bool hasRsi,
   double rsi14,
   const LevelResult &levels
)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   string payload =
      "{"
         "\"event_type\":\"TIMEFRAME_SNAPSHOT\","
         "\"symbol\":\"" + JsonEscape(_Symbol) + "\","
         "\"timeframe\":\"" + TimeframeToText(timeframe) + "\","
         "\"candle_time\":\"" + JsonEscape(DateTimeToText(candleTime)) + "\","
         "\"open\":" + DoubleToString(candle.open, digits) + ","
         "\"high\":" + DoubleToString(candle.high, digits) + ","
         "\"low\":" + DoubleToString(candle.low, digits) + ","
         "\"close\":" + DoubleToString(candle.close, digits) + ","
         "\"digits\":" + IntegerToString(digits) + ","
         "\"notify_patterns\":" + (notifyPatterns ? "true" : "false");

   if(hasRsi)
      payload += ",\"rsi14\":" + DoubleToString(rsi14, 2);

   if(hasEma)
   {
      payload +=
         ",\"ema20\":" + DoubleToString(ema20, digits) +
         ",\"ema50\":" + DoubleToString(ema50, digits);
   }
   else
   {
      payload +=
         ",\"patterns\":[" + patternsJson + "]"
         ",\"levels\":" + BuildLevelsJson(levels, digits);
   }

   return payload + "}";
}

//+------------------------------------------------------------------+
//| Print common MT5 WebRequest help                                 |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| Send webhook request                                             |
//+------------------------------------------------------------------+
bool SendWebhook(string payload)
{
   string url = WebhookUrl;

   if(url == "")
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
      "User-Agent: MT5-Engulfing-WebRequest\r\n";

   ResetLastError();

   int responseCode = WebRequest(
      "POST",
      url,
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
      Print("Webhook URL: ", url);
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
      PrintWebRequestHelp(url, mt5Error);
      return false;
   }

   if(responseCode < 200 || responseCode >= 300)
   {
      Print("Webhook request completed but server returned non-success HTTP code: ", responseCode);
      return false;
   }

   Print("Webhook sent successfully.");

   return true;
}

bool SendEaIssue(string message, string detail = "", ENUM_TIMEFRAMES timeframe = PERIOD_CURRENT)
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
      "{"
         "\"event_type\":\"EA_ERROR\","
         "\"symbol\":\"" + JsonEscape(_Symbol) + "\","
         "\"timeframe\":\"" + JsonEscape(tfText) + "\","
         "\"message\":\"" + JsonEscape(message) + "\","
         "\"detail\":\"" + JsonEscape(detail) + "\","
         "\"digits\":" + IntegerToString(digits) +
      "}";
   return SendWebhook(payload);
}

string TradeResultText()
{
   return "retcode=" + IntegerToString((int)trade.ResultRetcode())
      + " " + trade.ResultRetcodeDescription();
}

string TradeConfigUrl()
{
   string url = WebhookUrl;
   int marker = StringFind(url, "/webhook");
   if(marker >= 0)
      return StringSubstr(url, 0, marker) + "/trade-config";
   return url + "/trade-config";
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
      ushort ch = StringGetCharacter(json, end);
      if((ch >= 48 && ch <= 57) || ch == 46 || ch == 45)
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
   string body;
   if(!HttpGet(TradeConfigUrl(), body))
   {
      SendEaIssue("Trade config fetch failed", TradeConfigUrl());
      return false;
   }
   config.mode = JsonStringValue(body, "mode", "NOTRADE");
   config.lotSize = JsonDoubleValue(body, "lot_size", 0.2);
   config.trailPips = JsonDoubleValue(body, "trail_pips", 20.0);
   if(config.lotSize <= 0 || config.trailPips < 0)
   {
      SendEaIssue("Invalid trade config", body);
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Read one closed candle                                           |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| Check bullish engulfing                                          |
//+------------------------------------------------------------------+
bool IsBullishEngulfing(const Candle &candle1, const Candle &candle2)
{
   return HasValidBody(candle1)
      && HasValidBody(candle2)
      && IsBearishCandle(candle2)
      && IsBullishCandle(candle1)
      && candle1.open <= candle2.close
      && candle1.close >= candle2.open;
}

//+------------------------------------------------------------------+
//| Check bearish engulfing                                          |
//+------------------------------------------------------------------+
bool IsBearishEngulfing(const Candle &candle1, const Candle &candle2)
{
   return HasValidBody(candle1)
      && HasValidBody(candle2)
      && IsBullishCandle(candle2)
      && IsBearishCandle(candle1)
      && candle1.open >= candle2.close
      && candle1.close <= candle2.open;
}

//+------------------------------------------------------------------+
//| Check hammer-style lower wick candle                             |
//+------------------------------------------------------------------+
bool IsLowerWickPinBar(const Candle &candle)
{
   if(!HasValidBody(candle))
      return false;

   double body = CandleBody(candle);
   double range = CandleRange(candle);

   return body * 100.0 <= range * MaxBodyPercent
      && LowerWick(candle) >= body * MinLongWickBodyRatio
      && UpperWick(candle) <= body * MaxSmallWickBodyRatio;
}

//+------------------------------------------------------------------+
//| Check hammer                                                     |
//+------------------------------------------------------------------+
bool IsHammer(const Candle &candle)
{
   return IsBullishCandle(candle) && IsLowerWickPinBar(candle);
}

//+------------------------------------------------------------------+
//| Check hanging man                                                |
//+------------------------------------------------------------------+
bool IsHangingMan(const Candle &candle)
{
   return IsBearishCandle(candle) && IsLowerWickPinBar(candle);
}

//+------------------------------------------------------------------+
//| Check hammer-style upper wick candle                             |
//+------------------------------------------------------------------+
bool IsUpperWickPinBar(const Candle &candle)
{
   if(!HasValidBody(candle))
      return false;

   double body = CandleBody(candle);
   double range = CandleRange(candle);

   return body * 100.0 <= range * MaxBodyPercent
      && UpperWick(candle) >= body * MinLongWickBodyRatio
      && LowerWick(candle) <= body * MaxSmallWickBodyRatio;
}

bool IsShootingStar(
   const Candle &candle1,
   const Candle &candle2,
   const Candle &candle3,
   const Candle &candle4
)
{
   return IsUpperWickPinBar(candle1)
      && CandleRange(candle2) > 0
      && CandleRange(candle3) > 0
      && CandleRange(candle4) > 0
      && candle2.close > candle3.close
      && candle3.close > candle4.close;
}

bool IsInvertedHammer(
   const Candle &candle1,
   const Candle &candle2,
   const Candle &candle3,
   const Candle &candle4
)
{
   return IsUpperWickPinBar(candle1)
      && CandleRange(candle2) > 0
      && CandleRange(candle3) > 0
      && CandleRange(candle4) > 0
      && candle2.close < candle3.close
      && candle3.close < candle4.close;
}

bool IsStrongCandle(const Candle &candle)
{
   return HasValidBody(candle)
      && CandleBody(candle) * 100.0
         >= CandleRange(candle) * StrongCandleBodyPercent;
}

bool IsMorningStar(
   const Candle &candle1,
   const Candle &candle2,
   const Candle &candle3
)
{
   if(!HasValidBody(candle1)
      || !HasValidBody(candle2)
      || !IsStrongCandle(candle3))
      return false;

   double midpoint = (candle3.open + candle3.close) / 2.0;

   return IsBearishCandle(candle3)
      && CandleBody(candle2) * 100.0
         <= CandleBody(candle3) * MaxBodyPercent
      && IsBullishCandle(candle1)
      && candle1.close >= midpoint;
}

bool IsEveningStar(
   const Candle &candle1,
   const Candle &candle2,
   const Candle &candle3
)
{
   if(!HasValidBody(candle1)
      || !HasValidBody(candle2)
      || !IsStrongCandle(candle3))
      return false;

   double midpoint = (candle3.open + candle3.close) / 2.0;

   return IsBullishCandle(candle3)
      && CandleBody(candle2) * 100.0
         <= CandleBody(candle3) * MaxBodyPercent
      && IsBearishCandle(candle1)
      && candle1.close <= midpoint;
}

string InsideBarBreakoutSignal(
   const Candle &candle1,
   const Candle &candle2,
   const Candle &candle3
)
{
   if(CandleRange(candle1) <= 0
      || CandleRange(candle2) <= 0
      || CandleRange(candle3) <= 0)
      return "";

   bool inside = candle2.high <= candle3.high
      && candle2.low >= candle3.low;

   if(!inside)
      return "";
   if(candle1.close > candle3.high)
      return "BUY";
   if(candle1.close < candle3.low)
      return "SELL";
   return "";
}

void AddPattern(
   string &patternsJson,
   string eventType,
   string signal
)
{
   if(patternsJson != "")
      patternsJson += ",";
   patternsJson +=
      "{"
         "\"event_type\":\"" + eventType + "\","
         "\"signal\":\"" + signal + "\""
      "}";
}

bool ReadEmaValues(int index, double &ema20, double &ema50)
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

bool ReadRsiValue(int index, double &rsi14)
{
   double rsiBuffer[1];
   if(CopyBuffer(rsiHandles[index], 0, 1, 1, rsiBuffer) != 1)
      return false;
   rsi14 = rsiBuffer[0];
   return rsi14 != EMPTY_VALUE;
}

bool IsSwingHigh(ENUM_TIMEFRAMES timeframe, int shift)
{
   double center = iHigh(_Symbol, timeframe, shift);
   if(center <= 0)
      return false;
   for(int offset = 1; offset <= SwingStrength; offset++)
   {
      if(center <= iHigh(_Symbol, timeframe, shift - offset)
         || center <= iHigh(_Symbol, timeframe, shift + offset))
         return false;
   }
   return true;
}

bool IsSwingLow(ENUM_TIMEFRAMES timeframe, int shift)
{
   double center = iLow(_Symbol, timeframe, shift);
   if(center <= 0)
      return false;
   for(int offset = 1; offset <= SwingStrength; offset++)
   {
      if(center >= iLow(_Symbol, timeframe, shift - offset)
         || center >= iLow(_Symbol, timeframe, shift + offset))
         return false;
   }
   return true;
}

double AverageTrueRange(ENUM_TIMEFRAMES timeframe)
{
   if(AtrPeriod <= 0)
      return 0;
   double total = 0;
   for(int shift = 1; shift <= AtrPeriod; shift++)
   {
      if(iTime(_Symbol, timeframe, shift + 1) <= 0)
         return 0;
      double high = iHigh(_Symbol, timeframe, shift);
      double low = iLow(_Symbol, timeframe, shift);
      double previousClose = iClose(_Symbol, timeframe, shift + 1);
      total += MathMax(
         high - low,
         MathMax(MathAbs(high - previousClose), MathAbs(low - previousClose))
      );
   }
   return total / AtrPeriod;
}

void ResetLevels(LevelResult &levels)
{
   levels.hasSupport = false;
   levels.hasResistance = false;
   levels.hasFib = false;
   levels.hasBullishFvg = false;
   levels.hasBearishFvg = false;
   levels.hasPreviousDay = false;
}

void CalculateLevels(
   ENUM_TIMEFRAMES timeframe,
   double currentPrice,
   LevelResult &levels
)
{
   ResetLevels(levels);
   int bars = Bars(_Symbol, timeframe);
   int maximumShift = MathMin(
      LevelLookbackBars,
      bars - SwingStrength - 1
   );
   double supportDistance = DBL_MAX;
   double resistanceDistance = DBL_MAX;
   bool hasLatestPivot = false;
   bool latestPivotIsHigh = false;
   double latestPivotPrice = 0;

   for(int shift = SwingStrength + 1; shift <= maximumShift; shift++)
   {
      bool swingHigh = IsSwingHigh(timeframe, shift);
      bool swingLow = IsSwingLow(timeframe, shift);
      if(swingHigh)
      {
         double price = iHigh(_Symbol, timeframe, shift);
         if(price > currentPrice && price - currentPrice < resistanceDistance)
         {
            levels.hasResistance = true;
            levels.resistance = price;
            resistanceDistance = price - currentPrice;
         }
      }
      if(swingLow)
      {
         double price = iLow(_Symbol, timeframe, shift);
         if(price < currentPrice && currentPrice - price < supportDistance)
         {
            levels.hasSupport = true;
            levels.support = price;
            supportDistance = currentPrice - price;
         }
      }

      if(levels.hasFib || (!swingHigh && !swingLow) || (swingHigh && swingLow))
         continue;
      bool pivotIsHigh = swingHigh;
      double pivotPrice = pivotIsHigh
         ? iHigh(_Symbol, timeframe, shift)
         : iLow(_Symbol, timeframe, shift);
      if(!hasLatestPivot)
      {
         hasLatestPivot = true;
         latestPivotIsHigh = pivotIsHigh;
         latestPivotPrice = pivotPrice;
      }
      else if(pivotIsHigh != latestPivotIsHigh)
      {
         levels.hasFib = true;
         levels.fibStart = pivotPrice;
         levels.fibEnd = latestPivotPrice;
         levels.fibDirection =
            levels.fibEnd > levels.fibStart ? "UP" : "DOWN";
         levels.fib382 =
            levels.fibEnd + (levels.fibStart - levels.fibEnd) * 0.382;
         levels.fib500 =
            levels.fibEnd + (levels.fibStart - levels.fibEnd) * 0.500;
         levels.fib618 =
            levels.fibEnd + (levels.fibStart - levels.fibEnd) * 0.618;
      }
   }

   double atr = AverageTrueRange(timeframe);
   double minimumGap = atr * MinFvgAtrRatio;
   double bullishDistance = DBL_MAX;
   double bearishDistance = DBL_MAX;
   int maximumFvgShift = MathMin(LevelLookbackBars - 2, bars - 3);

   if(atr > 0 && minimumGap >= 0)
   {
      for(int shift = 1; shift <= maximumFvgShift; shift++)
      {
         Candle newest = ReadCandle(timeframe, shift);
         Candle oldest = ReadCandle(timeframe, shift + 2);

         double bullishLow = oldest.high;
         double bullishHigh = newest.low;
         if(bullishHigh - bullishLow >= minimumGap && bullishHigh < currentPrice)
         {
            bool filled = false;
            for(int later = 1; later < shift; later++)
            {
               if(iLow(_Symbol, timeframe, later) <= bullishLow)
               {
                  filled = true;
                  break;
               }
            }
            double distance = currentPrice - bullishHigh;
            if(!filled && distance < bullishDistance)
            {
               levels.hasBullishFvg = true;
               levels.bullishFvgLow = bullishLow;
               levels.bullishFvgHigh = bullishHigh;
               bullishDistance = distance;
            }
         }

         double bearishLow = newest.high;
         double bearishHigh = oldest.low;
         if(bearishHigh - bearishLow >= minimumGap && bearishLow > currentPrice)
         {
            bool filled = false;
            for(int later = 1; later < shift; later++)
            {
               if(iHigh(_Symbol, timeframe, later) >= bearishHigh)
               {
                  filled = true;
                  break;
               }
            }
            double distance = bearishLow - currentPrice;
            if(!filled && distance < bearishDistance)
            {
               levels.hasBearishFvg = true;
               levels.bearishFvgLow = bearishLow;
               levels.bearishFvgHigh = bearishHigh;
               bearishDistance = distance;
            }
         }
      }
   }

   if(iTime(_Symbol, PERIOD_D1, 1) > 0)
   {
      levels.hasPreviousDay = true;
      levels.previousDayHigh = iHigh(_Symbol, PERIOD_D1, 1);
      levels.previousDayLow = iLow(_Symbol, PERIOD_D1, 1);
   }
}

bool SendTimeframeSnapshot(int index, bool notifyPatterns)
{
   ENUM_TIMEFRAMES timeframe = Timeframes[index];
   string tfText = TimeframeToText(timeframe);
   datetime candleTime = iTime(_Symbol, timeframe, 1);
   if(candleTime <= 0)
   {
      if(PrintDebugLogs)
         Print("Closed candle data is not ready for ", tfText);
      return false;
   }

   Candle candle1 = ReadCandle(timeframe, 1);
   if(CandleRange(candle1) <= 0)
      return false;

   LevelResult levels;
   ResetLevels(levels);
   string patternsJson = "";
   bool hasEma = index < 2;
   double ema20 = 0;
   double ema50 = 0;
   double rsi14 = 0;
   bool hasRsi = ReadRsiValue(index, rsi14);

   if(hasEma)
   {
      if(!ReadEmaValues(index, ema20, ema50))
      {
         if(PrintDebugLogs)
            Print("EMA data is not ready for ", tfText);
         return false;
      }
   }
   else
   {
      Candle candle2 = ReadCandle(timeframe, 2);
      Candle candle3 = ReadCandle(timeframe, 3);
      Candle candle4 = ReadCandle(timeframe, 4);
      if(IsBullishEngulfing(candle1, candle2))
         AddPattern(patternsJson, "ENGULFING_CANDLE", "BUY");
      if(IsBearishEngulfing(candle1, candle2))
         AddPattern(patternsJson, "ENGULFING_CANDLE", "SELL");
      if(IsHammer(candle1))
         AddPattern(patternsJson, "HAMMER_CANDLE", "BUY");
      if(IsHangingMan(candle1))
         AddPattern(patternsJson, "HANGING_MAN_CANDLE", "SELL");
      if(IsShootingStar(candle1, candle2, candle3, candle4))
         AddPattern(patternsJson, "SHOOTING_STAR_CANDLE", "SELL");
      if(IsInvertedHammer(candle1, candle2, candle3, candle4))
         AddPattern(patternsJson, "INVERTED_HAMMER_CANDLE", "BUY");
      if(IsMorningStar(candle1, candle2, candle3))
         AddPattern(patternsJson, "MORNING_STAR", "BUY");
      if(IsEveningStar(candle1, candle2, candle3))
         AddPattern(patternsJson, "EVENING_STAR", "SELL");
      string insideBarSignal =
         InsideBarBreakoutSignal(candle1, candle2, candle3);
      if(insideBarSignal != "")
         AddPattern(
            patternsJson, "INSIDE_BAR_BREAKOUT", insideBarSignal
         );
      CalculateLevels(timeframe, candle1.close, levels);
   }

   string payload = BuildSnapshotPayload(
      timeframe,
      candleTime,
      candle1,
      notifyPatterns,
      patternsJson,
      hasEma,
      ema20,
      ema50,
      hasRsi,
      rsi14,
      levels
   );
   if(PrintDebugLogs)
      Print("Sending ", tfText, " timeframe snapshot.");
   return SendWebhook(payload);
}

void CheckTimeframe(int index)
{
   ENUM_TIMEFRAMES timeframe = Timeframes[index];
   datetime currentBarTime = iTime(_Symbol, timeframe, 0);
   if(currentBarTime <= 0 || currentBarTime == lastBarTimes[index])
      return;
   if(SendTimeframeSnapshot(index, hasSnapshot[index]))
   {
      lastBarTimes[index] = currentBarTime;
      hasSnapshot[index] = true;
   }
}

void CheckAllTimeframes()
{
   for(int i = 0; i < TF_COUNT; i++)
      CheckTimeframe(i);
}

double PipSize()
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return (digits == 3 || digits == 5) ? point * 10.0 : point;
}

bool ClosedCandleAboveEma20(int index)
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadEmaValues(index, ema20, ema50))
   {
      SendEaIssue("EMA data unavailable", "Above EMA20 confluence check", Timeframes[index]);
      return false;
   }
   Candle candle = ReadCandle(Timeframes[index], 1);
   return candle.open > ema20 && candle.close > ema20;
}

bool ClosedCandleBelowEma20(int index)
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadEmaValues(index, ema20, ema50))
   {
      SendEaIssue("EMA data unavailable", "Below EMA20 confluence check", Timeframes[index]);
      return false;
   }
   Candle candle = ReadCandle(Timeframes[index], 1);
   return candle.open < ema20 && candle.close < ema20;
}

bool BuyConfluence()
{
   double ema20 = 0;
   double ema50 = 0;
   if(!ReadEmaValues(0, ema20, ema50))
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
   if(!ReadEmaValues(0, ema20, ema50))
   {
      SendEaIssue("M1 EMA data unavailable", "Sell confluence check", PERIOD_M1);
      return false;
   }
   return ema50 > ema20
      && ClosedCandleBelowEma20(1)
      && ClosedCandleBelowEma20(2);
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
   // One open position per symbol: once a pending order is filled, stop
   // creating new orders for this symbol until the position is closed.
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

void DeletePendingOrders(ENUM_ORDER_TYPE type)
{
   for(int index = OrdersTotal() - 1; index >= 0; index--)
   {
      ulong ticket = OrderGetTicket(index);
      if(ticket == 0 || !OrderSelect(ticket))
         continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol
         && (long)OrderGetInteger(ORDER_MAGIC) == TradeMagicNumber
         && (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == type)
      {
         if(!trade.OrderDelete(ticket))
            SendEaIssue("OrderDelete failed", TradeResultText());
      }
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
      if(MathAbs(currentPrice - targetPrice) >= PipSize() * 0.1)
      {
         if(!trade.OrderModify(ticket, targetPrice, 0, 0, ORDER_TIME_GTC, 0))
            SendEaIssue("OrderModify failed", TradeResultText());
      }
      return;
   }

   if(type == ORDER_TYPE_BUY_LIMIT)
   {
      if(!trade.BuyLimit(lotSize, targetPrice, _Symbol, 0, 0, ORDER_TIME_GTC, 0, "Hermes trailing buy limit"))
         SendEaIssue("BuyLimit failed", TradeResultText(), PERIOD_M1);
   }
   else if(type == ORDER_TYPE_SELL_LIMIT)
   {
      if(!trade.SellLimit(lotSize, targetPrice, _Symbol, 0, 0, ORDER_TIME_GTC, 0, "Hermes trailing sell limit"))
         SendEaIssue("SellLimit failed", TradeResultText(), PERIOD_M1);
   }
}

void ManageTrading()
{
   TradeConfig config;
   if(!FetchTradeConfig(config))
      return;

   trade.SetExpertMagicNumber(TradeMagicNumber);
   if(HasOpenPositionForSymbol())
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
      if(!ReadEmaValues(0, ema20, ema50))
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
      if(!ReadEmaValues(0, ema20, ema50))
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

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   if(LevelLookbackBars < 10
      || SwingStrength < 1
      || AtrPeriod < 1
      || MinFvgAtrRatio < 0)
   {
      Print("Invalid level inputs.");
      SendEaIssue("Invalid EA inputs", "LevelLookbackBars/SwingStrength/AtrPeriod/MinFvgAtrRatio");
      return INIT_PARAMETERS_INCORRECT;
   }

   for(int i = 0; i < TF_COUNT; i++)
   {
      lastBarTimes[i] = 0;
      hasSnapshot[i] = false;
      ema20Handles[i] = iMA(
         _Symbol, Timeframes[i], 20, 0, MODE_EMA, PRICE_CLOSE
      );
      ema50Handles[i] = iMA(
         _Symbol, Timeframes[i], 50, 0, MODE_EMA, PRICE_CLOSE
      );
      rsiHandles[i] = iRSI(_Symbol, Timeframes[i], 14, PRICE_CLOSE);
      if(ema20Handles[i] == INVALID_HANDLE
         || ema50Handles[i] == INVALID_HANDLE
         || rsiHandles[i] == INVALID_HANDLE)
      {
         Print("Failed to create indicator handles for ", TimeframeToText(Timeframes[i]));
         SendEaIssue("Failed to create indicator handles", TimeframeToText(Timeframes[i]), Timeframes[i]);
         return INIT_FAILED;
      }
   }

   Print("===================================");
   Print("Multi-Timeframe Candlestick Pattern Webhook EA started.");
   Print("Version: 1.06");
   Print("Symbol: ", _Symbol);
   Print("Chart Period: ", EnumToString((ENUM_TIMEFRAMES)_Period));
   Print("Webhook URL: ", WebhookUrl);
   Print("Monitoring: M1, M5, M15, M30, H1, H4");
   Print("===================================");

   CheckAllTimeframes();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   for(int i = 0; i < TF_COUNT; i++)
   {
      if(ema20Handles[i] != INVALID_HANDLE)
         IndicatorRelease(ema20Handles[i]);
      if(ema50Handles[i] != INVALID_HANDLE)
         IndicatorRelease(ema50Handles[i]);
      if(rsiHandles[i] != INVALID_HANDLE)
         IndicatorRelease(rsiHandles[i]);
   }
   Print("Multi-Timeframe Candlestick Pattern Webhook EA stopped. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick                                                      |
//+------------------------------------------------------------------+
void OnTick()
{
   CheckAllTimeframes();
   ManageTrading();
}
//+------------------------------------------------------------------+
