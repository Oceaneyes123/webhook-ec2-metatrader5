#ifndef EXTERNAL_CONFIG_MQH
#define EXTERNAL_CONFIG_MQH

string externalConfigJson = "";
datetime externalConfigCheckedAt = 0;
datetime externalConfigValidAt = 0;

string ExternalConfigToken(string key)
{
   if(externalConfigJson == "") return "";
   int start = StringFind(externalConfigJson, "\"" + key + "\":");
   if(start < 0) return "";
   start += StringLen(key) + 3;
   while(start < StringLen(externalConfigJson) && StringGetCharacter(externalConfigJson, start) == ' ') start++;
   bool quoted = StringGetCharacter(externalConfigJson, start) == '"';
   if(quoted) start++;
   int end = quoted ? StringFind(externalConfigJson, "\"", start) : StringFind(externalConfigJson, ",", start);
   if(end < 0) end = StringFind(externalConfigJson, "}", start);
   return end < 0 ? "" : StringSubstr(externalConfigJson, start, end - start);
}

bool ExternalConfigBool(string key, bool fallback) { string raw = ExternalConfigToken(key); return raw == "true" ? true : raw == "false" ? false : fallback; }
int ExternalConfigInt(string key, int fallback) { string raw = ExternalConfigToken(key); return raw == "" ? fallback : (int)StringToInteger(raw); }
long ExternalConfigLong(string key, long fallback) { string raw = ExternalConfigToken(key); return raw == "" ? fallback : (long)StringToInteger(raw); }
double ExternalConfigDouble(string key, double fallback) { string raw = ExternalConfigToken(key); return raw == "" ? fallback : StringToDouble(raw); }
string ExternalConfigString(string key, string fallback) { string raw = ExternalConfigToken(key); return raw == "" ? fallback : raw; }

void ExternalConfigRefresh(string ea, string webhookUrl, int timeoutMs, int refreshSeconds = 5, int staleSeconds = 30)
{
   datetime now = TimeCurrent();
   if(externalConfigCheckedAt && now - externalConfigCheckedAt < refreshSeconds) return;
   externalConfigCheckedAt = now;
   string url = webhookUrl;
   if(StringReplace(url, "/webhook", "/ea-config?ea=" + ea) == 0) return;
   char request[], response[]; ArrayResize(request, 0); string headers;
   ResetLastError();
   int status = WebRequest("GET", url, "Accept: application/json\r\n", timeoutMs, request, response, headers);
   string body = CharArrayToString(response, 0, -1, CP_UTF8);
   if(status >= 200 && status < 300 && StringFind(body, "\"values\":{") >= 0)
   {
      externalConfigJson = body;
      externalConfigValidAt = now;
      return;
   }
   if(externalConfigValidAt && now - externalConfigValidAt > staleSeconds) externalConfigJson = "";
}

#endif
