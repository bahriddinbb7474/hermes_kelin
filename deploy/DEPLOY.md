# Hermes/Mariyam — инструкция по развёртыванию

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`, раздел 17. VPS пока НЕ трогать без отдельного разрешения.

## Архитектура deploy

- По умолчанию на VPS: `docker compose` поднимает **только PostgreSQL**.
- Backend MCP регистрируется в Hermes как `stdio` command: `python -m backend`.
- HTTP backend в compose оставлен только для локальной проверки/запасного варианта.
- Backend = storage/tools. Scheduler/router/intent-classifier/LLM-orchestrator здесь запрещены.

## Секреты и env

Compose-файл не использует `env_file:`. Секреты попадают через **интерполяцию переменных окружения процесса** `docker compose`.
На VPS это делает systemd `EnvironmentFile=/opt/hermes-mariyam-secrets/backend.env`.

Для ручных compose-команд сначала загрузить env:

```bash
set -a; . backend/.env; set +a
# или на VPS:
set -a; . /opt/hermes-mariyam-secrets/backend.env; set +a
```

Иначе `docker compose down/up` может дать warning про unset `POSTGRES_PASSWORD`.
Не пишите реальные пароли прямо в shell-командах: они остаются в history.

## Локальная проверка с нуля

```bash
# 1. Создать backend/.env из примера и заполнить POSTGRES_PASSWORD, DATABASE_URL, BACKEND_HOST_PORT
cp backend/.env.example backend/.env
# для локальных тестов DATABASE_URL обязан указывать на ОТДЕЛЬНУЮ тестовую БД,
# имя которой оканчивается на _test (НЕ на боевую `hermes`):
# DATABASE_URL=postgresql://hermes_test:<TEST_PASSWORD>@127.0.0.1:${POSTGRES_HOST_PORT:-5432}/hermes_test
# и APP_ENV=test обязателен.

# 2. Загрузить env для compose и тестов
set -a; . backend/.env; set +a

# 3. Свежий volume и старт Postgres + HTTP-backend для локальной проверки
# ВНИМАНИЕ: удаляет локальную тестовую БД проекта.
docker compose down -v
docker compose up -d

# 4. Проверить готовность БД
docker compose exec hermes_mariyam_postgres pg_isready -U hermes

# 5. HTTP initialize: первый и повторный запрос должны вернуть JSON-RPC ответ
curl -s -X POST http://127.0.0.1:${BACKEND_HOST_PORT:-8000}/mcp/   -H "Content-Type: application/json"   -H "Accept: application/json, text/event-stream"   -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'

curl -s -X POST http://127.0.0.1:${BACKEND_HOST_PORT:-8000}/mcp/   -H "Content-Type: application/json"   -H "Accept: application/json, text/event-stream"   -d '{"jsonrpc":"2.0","id":2,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t2","version":"1"}}}'

# 6. Тесты. Перед запуском оператор ОБЯЗАН проверить имя БД в DATABASE_URL.
#    Требования (см. tests/db_guard.py, Блок 6Ж):
#      - APP_ENV=test (строго);
#      - имя БД оканчивается на _test;
#      - боевая БД `hermes` запрещена безусловно;
#      - localhost / 127.0.0.1 сами по себе НЕ являются признаком тестовой БД;
#      - удалённая тестовая БД требует ALLOW_DESTRUCTIVE_TESTS=1.
#    Destructive suite на VPS production НЕ запускать.
#
#    Безопасный пример (без реальных credential; <TEST_PASSWORD> — placeholder,
#    не копировать буквально):
APP_ENV=test \
DATABASE_URL='postgresql://test_user:<TEST_PASSWORD>@127.0.0.1:5432/hermes_test' \
backend/.venv/Scripts/python.exe tests/run_tests.py
# ожидаемые маркеры:
# ALL_TOOL_TESTS_PASSED
# TZ_BOUNDARY_PASSED
# POOL_STABLE_PASSED
# MCP_SMOKE_PASSED

# Создание отдельной тестовой БД (один согласованный тестовый пользователь
# `test_user`; <TEST_PASSWORD> — placeholder, НЕ копировать буквально и НЕ
# использовать реальный пароль боевой БД):
#   1. создать БД `hermes_test` (compose НЕ создаёт её автоматически);
#   2. применить к ней миграцию 001_init.sql;
#   3. запускать destructive suite ТОЛЬКО с APP_ENV=test и DATABASE_URL на
#      `hermes_test`.
#
# !!! ВНИМАНИЕ:
#   - боевая БД `hermes` ЗАПРЕЩЕНА для destructive suite;
#   - localhost / 127.0.0.1 сами по себе НЕ означают test БД;
#   - suite НЕЛЬЗЯ запускать против живой VPS-БД `hermes`;
#   - создание `hermes_test` не выполняется автоматически compose.
POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-5432}
docker compose exec -T hermes_mariyam_postgres psql -U hermes -v ON_ERROR_STOP=1 -c \
  "CREATE DATABASE hermes_test;"
# применить миграцию к тестовой БД (имя пользователя = имя БД, не путать):
docker compose exec -T hermes_mariyam_postgres psql -U hermes -d hermes_test -v ON_ERROR_STOP=1 \
  -f /docker-entrypoint-initdb.d/001_init.sql

# 7. Проверка образа: секреты и venv не внутри image
docker compose build hermes_mariyam_backend
docker run --rm --entrypoint sh hermes-mariyam-hermes_mariyam_backend:latest -c "ls -la /app/backend/; test ! -e /app/backend/.env && test ! -d /app/backend/.venv && echo IMAGE_CLEAN"

# 8. Остановить
docker compose down
```

## Миграции БД

`backend/sql/001_init.sql` применяется контейнером Postgres только при первом создании volume.
Для будущих миграций `002_*.sql` на существующей БД применять вручную:

```bash
set -a; . backend/.env; set +a
docker compose exec -T hermes_mariyam_postgres psql -U hermes -d hermes -f /docker-entrypoint-initdb.d/002_next.sql
```

## Seed пользователей — обязательно до подключения Hermes

Предпочтительно вызвать MCP-tool `ensure_user` из Hermes/MCP-клиента:

```json
{ "telegram_id": 111222333, "role": "oyijon", "display_name": "Ойижон" }
{ "telegram_id": 444555666, "role": "admin", "display_name": "Бахриддин ака" }
```

Запасной SQL:

```sql
INSERT INTO users (telegram_id, role, display_name) VALUES
  (<TG_ID_ОЙИЖОН>, 'oyijon', 'Ойижон'),
  (<TG_ID_АДМИНА>, 'admin',  'Бахриддин ака')
ON CONFLICT (telegram_id) DO NOTHING;
```

## Stdio backend в Hermes (VPS-вариант по умолчанию)

Пример MCP-конфига Hermes-профиля:

```yaml
mcp:
  servers:
    mariyam_backend:
      command: python
      args: ["-m", "backend"]
      cwd: /opt/hermes-mariyam
      env:
        MCP_TRANSPORT: stdio
        DATABASE_URL: ${DATABASE_URL}
```

Проверка запуска stdio вручную: `python -m backend` должен стартовать как MCP stdio server; полноценный initialize выполняется MCP-клиентом Hermes.

## VPS deploy (Ubuntu 24.04, Hetzner) — только позже

```bash
# 0. Pre-check: порт PostgreSQL на VPS
ss -tulpen | grep ':5432' || true
# Если 5432 уже занят — остановить deploy и согласовать другой POSTGRES_HOST_PORT.

# 1. Подготовить /opt/hermes-mariyam и секреты
sudo install -d -m 755 /opt/hermes-mariyam
sudo rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.env' ./ /opt/hermes-mariyam/

sudo install -d -m 700 /opt/hermes-mariyam-secrets
sudo install -m 600 /path/to/real-backend.env /opt/hermes-mariyam-secrets/backend.env

# 2. Проверить unit до enable
sudo cp deploy/hermes-mariyam.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/hermes-mariyam.service
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-mariyam.service

# 3. Проверить Postgres compose
sudo systemctl status hermes-mariyam.service
cd /opt/hermes-mariyam && sudo docker compose ps

# 4. Seed users, затем подключить backend в Hermes как stdio MCP server
```

## VPS rollback

```bash
sudo systemctl stop hermes-mariyam.service
cd /opt/hermes-mariyam && sudo docker compose down
# вернуть предыдущую версию из git и повторить deploy
sudo systemctl start hermes-mariyam.service
```

## Secrets

- Реальные пароли/токены только в `/opt/hermes-mariyam-secrets/backend.env` (mode 600) или локальном `backend/.env`.
- `.env.example` — placeholder, без реальных значений.
- `.env`, `.venv/`, `__pycache__/` и docs не должны попадать в Docker image; проверка — `IMAGE_CLEAN`.
- Если старый image уже собирался с `.env`, удалить старые images, выполнить `docker builder prune`, сменить `POSTGRES_PASSWORD`.

## FORBIDDEN — что НЕ трогать

- `/opt/time-agent`, `time_agent_bot`, Time-Agent `.env`, SQLite volume, logs, backups.
- Любой scheduler/router/intent-classifier/LLM-orchestrator в backend.

Hermes/Mariyam использует только свои ресурсы: `name: hermes-mariyam`, контейнеры `hermes_mariyam_*`, сеть `hermes_mariyam_net`, volume `hermes_mariyam_pg_data`, localhost-порт `${BACKEND_HOST_PORT}`.
