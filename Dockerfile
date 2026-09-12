FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    ACCOUNT_DB_FILE=/data/account_state.db \
    TRADE_STATE_FILE=/data/trade_state.json \
    WEBHOOK_LOG_FILE=/data/webhook.log

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY run.py strategy_config.json ./
COPY config ./config
COPY frontend ./frontend
COPY webhook ./webhook

RUN useradd --create-home --uid 10001 webhook \
    && mkdir /data \
    && chown webhook:webhook /data

USER webhook
WORKDIR /data

EXPOSE 8000

CMD ["python", "/app/run.py"]
