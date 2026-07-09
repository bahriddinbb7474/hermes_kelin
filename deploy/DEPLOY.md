# Hermes/Mariyam — инструкция по развёртыванию (deploy docs)

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`, раздел 17.
Локальная среда (Windows) — только для разработки и проверки. Реальный VPS пока НЕ трогать.

## Что разворачивается

- `hermes_mariyam_backend` — MCP-сервер (storage tools, §15), слушает HTTP на `127.0.0.1:${BACKEND_HOST_PORT}` внутри изолированной сети compose.
- `hermes_mariyam_postgres` — PostgreSQL 16 (данные в volume `hermes_mariyam_pg_data`).
- Backend НЕ содержит scheduler и второго "мозга". Все расписания — через Hermes cron (§17).

## Локальная проверка (Windows, без sudo)

```bash
# 1. Создать backend/.env из примера и заполнить POSTGRES_PASSWORD
cp backend/.env.example backend/.env
#    отредактировать backend/.env: POSTGRES_PASSWORD=<сильный пароль>, BACKEND_HOST_PORT=8000

# 2. Поднять compose (изоляция: name=hermes-mariyam, контейнеры hermes_mariyam_*)
docker compose up -d

# 3. Проверить готовность БД
docker compose exec hermes_mariyam_postgres pg_isready -U hermes

# 4. Проверить, что backend отвечает по MCP HTTP
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'

# 5. Запустить тесты (требуют применённой миграции)
DATABASE_URL=postgresql://hermes:<пароль>@localhost:5432/hermes backend/.venv/Scripts/python.exe tests/run_tests.py
#    ожидаемый вывод: ALL_TOOL_TESTS_PASSED / TZ_BOUNDARY_PASSED

# 6. Остановить
docker compose down
```

## VPS deploy (Ubuntu 24.04, Hetzner) — КОМАНДЫ ДЛЯ БУДУЩЕГО ЗАПУСКА

> НЕ выполнять сейчас. Показано для готовности. Требует sudo и доступа к VPS.

```bash
# 0. Перед стартом — проверить, что порт 8000 свободен
ss -tulpen | grep ':8000' || true

# 1. Скопировать проект в /opt/hermes-mariyam
sudo install -d -m 755 /opt/hermes-mariyam
sudo rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.env' \
  ./ /opt/hermes-mariyam/

# 2. Секреты в изолированный env_file (НЕ в репозитории)
sudo install -d -m 700 /opt/hermes-mariyam-secrets
sudo install -m 600 /path/to/real-backend.env /opt/hermes-mariyam-secrets/backend.env
#    real-backend.env содержит: POSTGRES_PASSWORD=..., BACKEND_HOST_PORT=8000, DATABASE_URL=...

# 3. Установить systemd unit и включить автозапуск
sudo cp deploy/hermes-mariyam.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-mariyam.service

# 4. Проверить статус
sudo systemctl status hermes-mariyam.service
docker compose -f /opt/hermes-mariyam/docker-compose.yml ps
```

## VPS rollback

```bash
# Остановить и откатить к предыдущему коммиту/образу
sudo systemctl stop hermes-mariyam.service
cd /opt/hermes-mariyam && sudo docker compose down
#    вернуть предыдущую версию из git и повторить deploy (пункты 1-3)
sudo systemctl start hermes-mariyam.service
```

## Secrets (безопасность, §19)

- Реальные пароли/токены только в `/opt/hermes-mariyam-secrets/backend.env` (mode 600).
- `.env.example` — только placeholder, без реальных значений. Коммитится.
- `.env` и `.venv/` скрыты через `.gitignore`, в git не попадают.

## FORBIDDEN — что НЕ трогать (изоляция от Time-Agent)

- `/opt/time-agent` — каталог другого проекта.
- `time_agent_bot` — процесс/контейнер другого проекта.
- Time-Agent `.env` и любые его секреты.
- SQLite volume Time-Agent (если есть).
- logs и backups Time-Agent.

Hermes/Mariyam использует ТОЛЬКО свои изолированные ресурсы:
`name: hermes-mariyam`, контейнеры `hermes_mariyam_*`, сеть `hermes_mariyam_net`,
том `hermes_mariyam_pg_data`, порт `127.0.0.1:${BACKEND_HOST_PORT}`.

## Проверка изоляции

```bash
docker compose config          # name, container_name, networks, volumes — префикс hermes_mariyam
docker ps --format '{{.Names}}' | grep hermes_mariyam
```
