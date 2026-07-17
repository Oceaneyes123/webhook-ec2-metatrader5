//+------------------------------------------------------------------+
//| Webhook2 - trade management                                      |
//+------------------------------------------------------------------+
// Webhook2 does not send chart/history data.
#property strict
#property version "2.00"

#include <Trade/Trade.mqh>

input string WebhookUrl = "http://127.0.0.1:8000/webhook";
input int WebRequestTimeoutMs = 5000;
input bool PrintDebugLogs = true;
input long TradeMagicNumber = 260628;
input int EaIssueRepeatSeconds = 60;
input int TradeManageIntervalSeconds = 1;
input int HeartbeatSeconds = 30;
input int TradeConfigRefreshSeconds = 5;
input int TradeConfigMaxStaleSeconds = 30;
input int AccountReconcileSeconds = 60;
input string AccountActionSecret = "";
input double GoldPipSize = 0.1;

#define TRADE_TF_COUNT 3

ENUM_TIMEFRAMES Timeframes[TRADE_TF_COUNT] =
{
   PERIOD_M1,
   PERIOD_M5,
   PERIOD_M15
};

int ema20Handles[TRADE_TF_COUNT];
int ema50Handles[TRADE_TF_COUNT];
CTrade trade;
string lastEaIssueKey = "";
datetime lastEaIssueTime = 0;
datetime lastHeartbeatTime = 0;
datetime lastAccountReconcileTime = 0;

#include "includes/WebhookCommon.mqh"
#include "includes/TradeManager.mqh"

int OnInit()
{
   if(TradeManageIntervalSeconds < 1
      || HeartbeatSeconds < 10
      || HeartbeatSeconds < TradeManageIntervalSeconds
      || TradeConfigRefreshSeconds < 1
      || TradeConfigMaxStaleSeconds < TradeConfigRefreshSeconds)
   {
      Print("Invalid Webhook2 inputs.");
      SendEaIssue("Invalid Webhook2 inputs",
         "TradeManageIntervalSeconds/HeartbeatSeconds/TradeConfigRefreshSeconds/TradeConfigMaxStaleSeconds");
      return INIT_PARAMETERS_INCORRECT;
   }

   for(int index = 0; index < TRADE_TF_COUNT; index++)
   {
      ema20Handles[index] = iMA(
         _Symbol, Timeframes[index], 20, 0, MODE_EMA, PRICE_CLOSE
      );
      ema50Handles[index] = iMA(
         _Symbol, Timeframes[index], 50, 0, MODE_EMA, PRICE_CLOSE
      );
      if(ema20Handles[index] == INVALID_HANDLE
         || ema50Handles[index] == INVALID_HANDLE)
      {
         SendEaIssue(
            "Failed to create indicator handles",
            TimeframeToText(Timeframes[index]),
            Timeframes[index]
         );
         return INIT_FAILED;
      }
   }

   trade.SetExpertMagicNumber(TradeMagicNumber);
   EventSetTimer(TradeManageIntervalSeconds);

   Print("Webhook2 trade EA started for ", _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int index = 0; index < TRADE_TF_COUNT; index++)
   {
      if(ema20Handles[index] != INVALID_HANDLE)
         IndicatorRelease(ema20Handles[index]);
      if(ema50Handles[index] != INVALID_HANDLE)
         IndicatorRelease(ema50Handles[index]);
   }
   Print("Webhook2 trade EA stopped. Reason: ", reason);
}

void OnTick()
{
}

// Account-wide transaction feed: it is independent of this chart, symbol,
// magic number, and whether the account is netting or hedging.
void OnTradeTransaction(
   const MqlTradeTransaction &transaction,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
{
   if(transaction.type != TRADE_TRANSACTION_DEAL_ADD
      && transaction.type != TRADE_TRANSACTION_ORDER_ADD
      && transaction.type != TRADE_TRANSACTION_ORDER_UPDATE
      && transaction.type != TRADE_TRANSACTION_ORDER_DELETE
      && transaction.type != TRADE_TRANSACTION_POSITION
      && transaction.type != TRADE_TRANSACTION_REQUEST)
      return;
   string kind = EnumToString(transaction.type);
   ulong deal = transaction.deal;
   ulong order = transaction.order;
   ulong position = transaction.position;
   string symbol = transaction.symbol;
   long magic = 0;
   double profit = 0, commission = 0, swap = 0;
   string reason = "";
   string direction = "";
   datetime eventTime = TimeCurrent();
   string eventKind = kind;

   if(deal > 0 && HistoryDealSelect(deal))
   {
      position = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      symbol = HistoryDealGetString(deal, DEAL_SYMBOL);
      magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
      profit = HistoryDealGetDouble(deal, DEAL_PROFIT);
      commission = HistoryDealGetDouble(deal, DEAL_COMMISSION);
      swap = HistoryDealGetDouble(deal, DEAL_SWAP);
      reason = EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(deal, DEAL_REASON));
      direction = EnumToString((ENUM_DEAL_TYPE)HistoryDealGetInteger(deal, DEAL_TYPE));
      eventTime = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry == DEAL_ENTRY_IN)
      {
         ulong sourceOrder = (ulong)HistoryDealGetInteger(deal, DEAL_ORDER);
         eventKind = "POSITION_OPENED";
         if(sourceOrder > 0 && HistoryOrderSelect(sourceOrder))
         {
            ENUM_ORDER_TYPE orderType = (ENUM_ORDER_TYPE)HistoryOrderGetInteger(sourceOrder, ORDER_TYPE);
            if(orderType == ORDER_TYPE_BUY_LIMIT || orderType == ORDER_TYPE_SELL_LIMIT || orderType == ORDER_TYPE_BUY_STOP || orderType == ORDER_TYPE_SELL_STOP || orderType == ORDER_TYPE_BUY_STOP_LIMIT || orderType == ORDER_TYPE_SELL_STOP_LIMIT)
               eventKind = "PENDING_ORDER_FILLED";
         }
      }
      else if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
         eventKind = reason == "DEAL_REASON_SL" ? "STOP_LOSS_HIT" : reason == "DEAL_REASON_TP" ? "TAKE_PROFIT_HIT" : reason == "DEAL_REASON_CLIENT" ? "MANUAL_CLOSE" : PositionSelectByTicket(position) ? "PARTIAL_CLOSE" : "POSITION_CLOSED";
   }
   else if(order > 0 && HistoryOrderSelect(order))
   {
      position = (ulong)HistoryOrderGetInteger(order, ORDER_POSITION_ID);
      symbol = HistoryOrderGetString(order, ORDER_SYMBOL);
      magic = HistoryOrderGetInteger(order, ORDER_MAGIC);
      reason = EnumToString((ENUM_ORDER_STATE)HistoryOrderGetInteger(order, ORDER_STATE));
      direction = EnumToString((ENUM_ORDER_TYPE)HistoryOrderGetInteger(order, ORDER_TYPE));
      eventTime = (datetime)HistoryOrderGetInteger(order, ORDER_TIME_DONE);
      if(transaction.type == TRADE_TRANSACTION_ORDER_ADD) eventKind = "PENDING_ORDER_CREATED";
      else if(transaction.type == TRADE_TRANSACTION_ORDER_UPDATE) eventKind = "PENDING_ORDER_MODIFIED";
      else if(transaction.type == TRADE_TRANSACTION_ORDER_DELETE) eventKind = "PENDING_ORDER_CANCELLED";
   }
   if(transaction.type == TRADE_TRANSACTION_POSITION) eventKind = "POSITION_SL_TP_MODIFIED";
   if(transaction.type == TRADE_TRANSACTION_REQUEST && result.retcode != TRADE_RETCODE_DONE && result.retcode != TRADE_RETCODE_PLACED) eventKind = "TRADE_OPERATION_REJECTED";

   int digits = symbol == "" ? _Digits : (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   ulong identity = deal > 0 ? deal : order;
   string eventId = IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ":"
       + IntegerToString(identity) + ":" + IntegerToString((int)transaction.type);
   if(identity == 0) eventId += ":" + IntegerToString(GetTickCount64());
   else if(transaction.type == TRADE_TRANSACTION_ORDER_UPDATE)
      eventId += ":" + DoubleToString(transaction.price, digits) + ":" + DoubleToString(transaction.price_sl, digits) + ":" + DoubleToString(transaction.price_tp, digits) + ":" + DoubleToString(transaction.volume, 2);
   string payload =
      "{\"event_type\":\"TRADE_TRANSACTION\""
      ",\"event_id\":\"" + eventId + "\""
      ",\"source\":\"mt5_on_trade_transaction\""
      ",\"account_login\":" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))
      + ",\"broker_server\":\"" + JsonEscape(AccountInfoString(ACCOUNT_SERVER)) + "\""
       + ",\"transaction_type\":\"" + JsonEscape(eventKind) + "\""
      + ",\"symbol\":\"" + JsonEscape(symbol) + "\""
      + ",\"position_ticket\":\"" + IntegerToString(position) + "\""
      + ",\"order_ticket\":\"" + IntegerToString(order) + "\""
      + ",\"deal_ticket\":\"" + IntegerToString(deal) + "\""
      + ",\"magic_number\":" + IntegerToString(magic)
      + ",\"direction\":\"" + JsonEscape(direction) + "\""
      + ",\"volume\":" + DoubleToString(transaction.volume, 2)
       + ",\"entry_price\":" + DoubleToString(transaction.price, digits)
       + ",\"exit_price\":" + DoubleToString(transaction.price, digits)
      + ",\"sl\":" + DoubleToString(transaction.price_sl, digits)
      + ",\"tp\":" + DoubleToString(transaction.price_tp, digits)
      + ",\"profit\":" + DoubleToString(profit, 2)
      + ",\"commission\":" + DoubleToString(commission, 2)
      + ",\"swap\":" + DoubleToString(swap, 2)
      + ",\"reason\":\"" + JsonEscape(reason) + "\""
      + ",\"event_time\":\"" + DateTimeToText(eventTime) + "\""
       + ",\"retcode\":" + IntegerToString((int)result.retcode)
       + ",\"retcode_description\":\"" + JsonEscape(result.comment) + "\"}";
   SendWebhook(payload);
}

void OnTimer()
{
   ManageTrading();
   ProcessAccountAction();
   MaybeSendAccountReconciliation();
   MaybeSendHeartbeat();
}

void MaybeSendHeartbeat()
{
   datetime now = TimeCurrent();
   if(now - lastHeartbeatTime >= HeartbeatSeconds)
   {
      SendEaHeartbeat("webhook2");
      lastHeartbeatTime = now;
   }
}
