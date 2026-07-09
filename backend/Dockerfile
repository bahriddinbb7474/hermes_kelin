# Hermes/Mariyam backend — Dockerfile
# Backend MCP-server + PostgreSQL. HTTP-транспорт по localhost для подключения из Hermes.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ ./backend/
# пакет backend импортируется как `backend` — добавляем /app в PATH
ENV PYTHONPATH=/app

# HTTP MCP-режим по умолчанию (localhost внутри compose-сети)
ENV MCP_TRANSPORT=http \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8000 \
    DATABASE_URL=postgresql://hermes:hermes@db:5432/hermes

EXPOSE 8000

CMD ["python", "-m", "backend"]
