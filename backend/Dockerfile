# Hermes/Mariyam backend — Dockerfile
# Backend MCP-server. stdio по умолчанию; HTTP включается env MCP_TRANSPORT=http для compose-проверки.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ ./backend/
ENV PYTHONPATH=/app

ENV MCP_TRANSPORT=http     MCP_HTTP_HOST=0.0.0.0     MCP_HTTP_PORT=8000

EXPOSE 8000

CMD ["python", "-m", "backend"]
