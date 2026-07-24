#ifndef MARKET_SNAPSHOT_MQH
#define MARKET_SNAPSHOT_MQH

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

bool SendMarketEaIssue(
   string message,
   string detail = "",
   ENUM_TIMEFRAMES timeframe = PERIOD_CURRENT
)
{
   string tfText = timeframe == PERIOD_CURRENT ? "" : TimeframeToText(timeframe);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return SendWebhook(
      "{\"event_type\":\"EA_ERROR\""
      ",\"source\":\"webhook1\""
      ",\"symbol\":\"" + JsonEscape(_Symbol) + "\""
      ",\"timeframe\":\"" + JsonEscape(tfText) + "\""
      ",\"message\":\"" + JsonEscape(message) + "\""
      ",\"detail\":\"" + JsonEscape(detail) + "\""
      ",\"digits\":" + IntegerToString(digits) + "}"
   );
}

bool IsBullishEngulfing(const Candle &current, const Candle &previous)
{
   return HasValidBody(current)
      && HasValidBody(previous)
      && IsBearishCandle(previous)
      && IsBullishCandle(current)
      && current.open <= previous.close
      && current.close >= previous.open;
}

bool IsBearishEngulfing(const Candle &current, const Candle &previous)
{
   return HasValidBody(current)
      && HasValidBody(previous)
      && IsBullishCandle(previous)
      && IsBearishCandle(current)
      && current.open >= previous.close
      && current.close <= previous.open;
}

bool IsLowerWickPinBar(const Candle &candle)
{
   if(!HasValidBody(candle))
      return false;
   double body = CandleBody(candle);
   return body * 100.0 <= CandleRange(candle) * MaxBodyPercent
      && LowerWick(candle) >= body * MinLongWickBodyRatio
      && UpperWick(candle) <= body * MaxSmallWickBodyRatio;
}

bool IsHammer(const Candle &candle)
{
   return IsBullishCandle(candle) && IsLowerWickPinBar(candle);
}

bool IsHangingMan(const Candle &candle)
{
   return IsBearishCandle(candle) && IsLowerWickPinBar(candle);
}

bool IsUpperWickPinBar(const Candle &candle)
{
   if(!HasValidBody(candle))
      return false;
   double body = CandleBody(candle);
   return body * 100.0 <= CandleRange(candle) * MaxBodyPercent
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
   return IsBearishCandle(candle3)
      && CandleBody(candle2) * 100.0
         <= CandleBody(candle3) * MaxBodyPercent
      && IsBullishCandle(candle1)
      && candle1.close >= (candle3.open + candle3.close) / 2.0;
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
   return IsBullishCandle(candle3)
      && CandleBody(candle2) * 100.0
         <= CandleBody(candle3) * MaxBodyPercent
      && IsBearishCandle(candle1)
      && candle1.close <= (candle3.open + candle3.close) / 2.0;
}

string InsideBarBreakoutSignal(
   const Candle &candle1,
   const Candle &candle2,
   const Candle &candle3
)
{
   if(CandleRange(candle1) <= 0
      || CandleRange(candle2) <= 0
      || CandleRange(candle3) <= 0
      || candle2.high > candle3.high
      || candle2.low < candle3.low)
      return "";
   if(candle1.close > candle3.high)
      return "BUY";
   if(candle1.close < candle3.low)
      return "SELL";
   return "";
}

void AddPattern(string &patternsJson, string eventType, string signal)
{
   if(patternsJson != "")
      patternsJson += ",";
   patternsJson +=
      "{\"event_type\":\"" + eventType + "\",\"signal\":\"" + signal + "\"}";
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
   double buffer[1];
   if(CopyBuffer(rsiHandles[index], 0, 1, 1, buffer) != 1)
      return false;
   rsi14 = buffer[0];
   return rsi14 != EMPTY_VALUE;
}

bool IsSwingHigh(ENUM_TIMEFRAMES timeframe, int shift)
{
   double center = iHigh(_Symbol, timeframe, shift);
   if(center <= 0)
      return false;
   for(int offset = 1; offset <= SwingStrength; offset++)
      if(center <= iHigh(_Symbol, timeframe, shift - offset)
         || center <= iHigh(_Symbol, timeframe, shift + offset))
         return false;
   return true;
}

bool IsSwingLow(ENUM_TIMEFRAMES timeframe, int shift)
{
   double center = iLow(_Symbol, timeframe, shift);
   if(center <= 0)
      return false;
   for(int offset = 1; offset <= SwingStrength; offset++)
      if(center >= iLow(_Symbol, timeframe, shift - offset)
         || center >= iLow(_Symbol, timeframe, shift + offset))
         return false;
   return true;
}

double AverageTrueRange(ENUM_TIMEFRAMES timeframe)
{
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
   int maximumShift = MathMin(LevelLookbackBars, bars - SwingStrength - 1);
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

   if(atr > 0)
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
               if(iLow(_Symbol, timeframe, later) <= bullishLow)
               {
                  filled = true;
                  break;
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
               if(iHigh(_Symbol, timeframe, later) >= bearishHigh)
               {
                  filled = true;
                  break;
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

string BuildLevelsJson(const LevelResult &levels, int digits)
{
   string fib = "null";
   if(levels.hasFib)
      fib =
         "{\"direction\":\"" + levels.fibDirection + "\""
         ",\"start\":" + DoubleToString(levels.fibStart, digits)
         + ",\"end\":" + DoubleToString(levels.fibEnd, digits)
         + ",\"38.2\":" + DoubleToString(levels.fib382, digits)
         + ",\"50.0\":" + DoubleToString(levels.fib500, digits)
         + ",\"61.8\":" + DoubleToString(levels.fib618, digits) + "}";

   string bullishFvg = "null";
   if(levels.hasBullishFvg)
      bullishFvg =
         "{\"low\":" + DoubleToString(levels.bullishFvgLow, digits)
         + ",\"high\":" + DoubleToString(levels.bullishFvgHigh, digits) + "}";

   string bearishFvg = "null";
   if(levels.hasBearishFvg)
      bearishFvg =
         "{\"low\":" + DoubleToString(levels.bearishFvgLow, digits)
         + ",\"high\":" + DoubleToString(levels.bearishFvgHigh, digits) + "}";

   return
      "{\"support\":"
      + JsonNumberOrNull(levels.hasSupport, levels.support, digits)
      + ",\"resistance\":"
      + JsonNumberOrNull(levels.hasResistance, levels.resistance, digits)
      + ",\"fib\":" + fib
      + ",\"bullish_fvg\":" + bullishFvg
      + ",\"bearish_fvg\":" + bearishFvg
      + ",\"previous_day_high\":"
      + JsonNumberOrNull(
         levels.hasPreviousDay, levels.previousDayHigh, digits
      )
      + ",\"previous_day_low\":"
      + JsonNumberOrNull(
         levels.hasPreviousDay, levels.previousDayLow, digits
      ) + "}";
}

string BuildCandlesJson(ENUM_TIMEFRAMES timeframe, int digits)
{
   string candles = "";
   for(int shift = ChartHistoryBars; shift >= 1; shift--)
   {
      datetime candleTime = iTime(_Symbol, timeframe, shift);
      double open = iOpen(_Symbol, timeframe, shift);
      double high = iHigh(_Symbol, timeframe, shift);
      double low = iLow(_Symbol, timeframe, shift);
      double close = iClose(_Symbol, timeframe, shift);
      if(candleTime <= 0
         || open <= 0
         || high <= 0
         || low <= 0
         || close <= 0
         || high < MathMax(open, close)
         || low > MathMin(open, close))
         continue;
      if(candles != "")
         candles += ",";
      candles +=
         "{\"time\":\"" + JsonEscape(DateTimeToText(candleTime)) + "\""
         + ",\"open\":" + DoubleToString(open, digits)
         + ",\"high\":" + DoubleToString(high, digits)
         + ",\"low\":" + DoubleToString(low, digits)
         + ",\"close\":" + DoubleToString(close, digits) + "}";
   }
   return "[" + candles + "]";
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
   bool hasLevels,
   const LevelResult &levels
)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   string payload =
      "{\"event_type\":\"TIMEFRAME_SNAPSHOT\""
      ",\"source\":\"webhook1\""
      ",\"symbol\":\"" + JsonEscape(_Symbol) + "\""
      ",\"timeframe\":\"" + TimeframeToText(timeframe) + "\""
      ",\"candle_time\":\"" + JsonEscape(DateTimeToText(candleTime)) + "\""
      ",\"open\":" + DoubleToString(candle.open, digits)
      + ",\"high\":" + DoubleToString(candle.high, digits)
      + ",\"low\":" + DoubleToString(candle.low, digits)
      + ",\"close\":" + DoubleToString(candle.close, digits)
      + ",\"bid\":" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), digits)
      + ",\"ask\":" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), digits)
      + ",\"daily_open\":" + DoubleToString(iOpen(_Symbol, PERIOD_D1, 0), digits)
      + ",\"daily_high\":" + DoubleToString(iHigh(_Symbol, PERIOD_D1, 0), digits)
      + ",\"daily_low\":" + DoubleToString(iLow(_Symbol, PERIOD_D1, 0), digits)
      + ",\"digits\":" + IntegerToString(digits)
      + ",\"notify_patterns\":" + (notifyPatterns ? "true" : "false")
      + ",\"candles\":" + BuildCandlesJson(timeframe, digits);

   if(hasRsi)
      payload += ",\"rsi14\":" + DoubleToString(rsi14, 2);
   if(hasEma)
      payload +=
         ",\"ema20\":" + DoubleToString(ema20, digits)
         + ",\"ema50\":" + DoubleToString(ema50, digits);
   else
      payload +=
         ",\"patterns\":[" + patternsJson + "]";
   if(hasLevels)
      payload += ",\"levels\":" + BuildLevelsJson(levels, digits);
   return payload + "}";
}

bool SendTimeframeSnapshot(int index, bool notifyPatterns)
{
   ENUM_TIMEFRAMES timeframe = Timeframes[index];
   datetime candleTime = iTime(_Symbol, timeframe, 1);
   if(candleTime <= 0)
      return false;

   Candle candle1 = ReadCandle(timeframe, 1);
   if(CandleRange(candle1) <= 0)
      return false;

   LevelResult levels;
   ResetLevels(levels);
   string patternsJson = "";
   bool hasEma = index < 2;
   bool hasLevels = index >= 1;
   double ema20 = 0;
   double ema50 = 0;
   double rsi14 = 0;
   bool hasRsi = ReadRsiValue(index, rsi14);

   if(hasEma)
   {
      if(!ReadEmaValues(index, ema20, ema50))
         return false;
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
         AddPattern(patternsJson, "INSIDE_BAR_BREAKOUT", insideBarSignal);
   }
   if(hasLevels)
      CalculateLevels(
         timeframe,
         timeframe == PERIOD_D1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : candle1.close,
         levels
      );

   return SendWebhook(
      BuildSnapshotPayload(
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
         hasLevels,
         levels
      )
   );
}

void CheckTimeframe(int index)
{
   datetime currentBarTime = iTime(_Symbol, Timeframes[index], 0);
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
   for(int index = 0; index < TF_COUNT; index++)
      CheckTimeframe(index);
}

#endif
