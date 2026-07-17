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
# DATABASE_URL=postgresql://hermes:<LOCAL_TEST_PASSWORD>@127.0.0.1:${POSTGRES_HOST_PORT:-5432}/hermes_test
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
#    Безопасный пример (без реальных credential; <LOCAL_TEST_PASSWORD> — placeholder,
#    не копировать буквально):
APP_ENV=test \
DATABASE_URL='postgresql://hermes:<LOCAL_TEST_PASSWORD>@127.0.0.1:5432/hermes_test' \
backend/.venv/Scripts/python.exe tests/run_tests.py
# ожидаемые маркеры:
# ALL_TOOL_TESTS_PASSED
# TZ_BOUNDARY_PASSED
# POOL_STABLE_PASSED
# MCP_SMOKE_PASSED

# Создание отдельной локальной тестовой БД (PostgreSQL role — `hermes`,
# та же, что владеет боевой БД; <LOCAL_TEST_PASSWORD> — placeholder, реальный
# пароль в документ не писать):
#   1. создать БД `hermes_test` (compose НЕ создаёт её автоматически);
#   2. применить к ней миграцию 001_init.sql;
#   3. запускать destructive suite ТОЛЬКО с APP_ENV=test и DATABASE_URL на
#      `hermes_test`.
#
# !!! ВНИМАНИЕ:
#   - боевая БД `hermes` ЗАПРЕЩЕНА для destructive suite (guard блокирует
#     безусловно);
#   - localhost / 127.0.0.1 сами по себе НЕ означают test БД;
#   - suite НЕЛЬЗЯ запускать против живой VPS-БД `hermes`;
#   - `hermes_test` compose автоматически не создаёт — создавать вручную;
#   - `createdb` выполняют ОДИН раз; если `hermes_test` уже есть, повторно не
#     создавать (иначе ошибка); удаление `hermes_test` НЕ затрагивает
#     production volume и БД `hermes`.
POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-5432}
docker compose exec -T hermes_mariyam_postgres \
  createdb -U hermes hermes_test
# применить миграцию к тестовой БД (role `hermes`, отдельная БД `hermes_test`):
docker compose exec -T hermes_mariyam_postgres \
  psql -U hermes -d hermes_test -v ON_ERROR_STOP=1 \
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

## Hermes Gateway — systemd USER-unit (автозапуск Telegram-бота)

Штатный путь (Hermes v0.18.2): `hermes gateway install` генерирует systemd unit,
`loginctl enable-linger` держит его после logout/reboot. Самодельные демоны НЕ писать.

```bash
# Под пользователем timeagent (НЕ root):
export PATH="$HOME/.local/bin:$HOME/.hermes/bin:$PATH"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# 1. Установить USER-unit (WantedBy=default.target, без секретов в файле)
hermes -p mariyam_oyijon gateway install --start-on-login

# 2. Linger — unit переживает logout и поднимается при boot
loginctl enable-linger timeagent
loginctl show-user timeagent -p Linger   # ожидаем: Linger=yes

# 3. Проверить unit ДО запуска (без секретов)
systemd-analyze --user verify ~/.config/systemd/user/hermes-gateway-mariyam_oyijon.service

# 4. Запуск (или enable --now в install сделает это сам)
hermes -p mariyam_oyijon gateway start
systemctl --user status hermes-gateway-mariyam_oyijon.service

# Остановка / откат:
hermes -p mariyam_oyijon gateway stop
# или: systemctl --user disable --now hermes-gateway-mariyam_oyijon.service
```

Эталонная копия unit лежит в `deploy/hermes-gateway-mariyam_oyijon.service`
(`Restart=always`, env только PATH/VIRTUAL_ENV/HERMES_HOME — секретов нет;
реальные токены/пароли из `~/.hermes/profiles/mariyam_oyijon/.env` в рантайме).

ВАЖНО: VPS общий с Time-Agent. Reboot влияет на оба сервиса — согласовывать окно.
НЕ трогать /opt/time-agent, time_agent_bot, Time-Agent .env, SQLite volume, logs, backups.

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

## Mariyam identity guard

Role-aware, fail-closed `tool_execution` middleware, который привязывает
MCP tools к правильному внутреннему `users.id` по текущей Telegram-сессии.
Plugin: `deploy/hermes_plugins/mariyam_identity_guard/`.

### Текущий VPS baseline

- Identity guard **1.0.4** установлен и включён в runtime profile.
- Приватный mapping находится вне git, имеет strict mode `0600`; Gateway Environment с `MARIYAM_IDENTITY_MAP_FILE` настроен.
- `display.tool_progress: "off"` настроен.
- MCP-prefix `mcp__mariyam_backend__<tool>` канонизируется до bare policy name; неизвестные/неразрешённые вызовы блокируются fail-closed.
- Stage 5 controlled Telegram E2E на «Тест Ойижон» — **PASS**.
- Текущий VPS runtime: tools/dispatch/MCP discovery **21/21/21**, plugin **1.0.4**, migration 002 active; Stage 5.1 и Stage 5.2 — **CLOSED / LIVE PASS**. Repo Stage 5.3 на VPS ещё не развёрнут.

Значения mapping, реальные Telegram ID и секреты в git/отчёты не добавлять. Реальную Ойижон до handover не подключать.

## Deterministic profile prompt и skill-protect

После Stage 5 E2E self-improvement fork переписал прежний
`skills/mariyam/SKILL.md` и отправил служебное сообщение в Telegram. Root cause
защиты от self-improvement (Hermes v0.18.x):

- `agent/turn_finalizer.py` → `_spawn_background_review(review_skills=True)`
  когда `skills.creation_nudge_interval > 0` и tool `skill_manage` доступен;
- `agent/background_review.py` вызывает `skill_manage` и шлёт
  `💾 Self-improvement review: …` через `background_review_callback`.

Stage 5.2 показал второй root cause: Hermes добавляет в system prompt только
индекс/description skills, а полный `SKILL.md` доступен лишь после `skill_view`.
При `agent.disabled_toolsets: [skills]` нет ни индекса, ни пути чтения. Ключ
`skills.enabled` в Hermes v0.18.2 не загружает body skill и фактически не
используется loader-ом.

**Поддерживаемый profile-level fix (без Hermes core):**

1. Слить в `~/.hermes/profiles/mariyam_oyijon/config.yaml` файл
   `deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml`
   (ключи: `creation_nudge_interval: 0`, `write_approval: true`,
   `memory_notifications: "off"`, `agent.disabled_toolsets: [skills]`).
2. Установить единственный canonical repo-source
   `deploy/hermes_profile_mariyam_oyijon/SOUL.md` как
   `~/.hermes/profiles/mariyam_oyijon/SOUL.md`. Не создавать вторую копию в
   `skills/mariyam/SKILL.md`.
3. Инвалидировать только session временного test-user через private mapping; другие
   sessions и данные не менять.
4. Перезапустить только `hermes-gateway-mariyam_oyijon.service`.
5. **Offline preflight deployed-профиля (API calls = 0):** собрать effective prompt
   через `build_system_prompt_parts()`, подтвердить полный SOUL, canonical SHA, оба
   report contracts и отсутствие truncation.
6. Новый платный Telegram/provider test не выполнять: Message 1 и Message 2 уже
   подтверждены live. Специальные wrapper-маркеры stored prompt не являются AC;
   Telegram first_name/last_name/username не являются identity. Identity проверяется
   только цепочкой `exact Telegram session → private mapping → requested=0 → effective=test-user`.
7. Offline gate:
   `pytest tests/test_mariyam_effective_prompt.py tests/test_mariyam_skill_protection.py`.

Опционально (filesystem belt, не вместо config): `chmod a-w` на profile
`SOUL.md` после deploy.

Stage 5.2 = **CLOSED / LIVE PASS**. Message 1 и Message 2 подтверждены live;
исправление завершения отчётов закреплено offline без нового платного теста.

Repo Stage 5.3 = **OFFLINE PASS / LIVE PENDING**: migration 003 и расширение двух
существующих budget tools реализованы, inventory остаётся **21/21/21**. Единственный
canonical repo-source — `deploy/hermes_profile_mariyam_oyijon/SOUL.md`, LF SHA
`5f7b08569cfd75cd26d78a234fbb8a39322dfc65e9221ae2d461e89444148266`.

VPS runtime пока остаётся на migration 002 и deployed Stage 5.2 SOUL SHA
`3135a12e07529222b9db350ccca07f52d79b76b0ca2b8597bec50a4a0f9a176e`;
это deployed baseline, а не текущий repo canonical SHA. Активный Mariyam `SKILL.md`
отсутствует, skill-protect и `tool_progress=off` сохранены. Stage 5.3A–6 остаются
**PLANNED / NOT IMPLEMENTED**; реальная Ойижон не подключена.

## Выполненный Stage 5.1 live deploy (история выполнения)

Последовательность выполнена controlled deploy:

1. Сделать backup production-БД и runtime profile Мариям.
2. Применить migration 002 (`backend/sql/002_stage51_quantity_budget.sql`) с `ON_ERROR_STOP=1`.
3. Установить backend из repo с inventory **21 tools**.
4. Обновить identity plugin **1.0.3 → 1.0.4**.
5. Применить profile-scoped skill-protect config.
6. Установить canonical `skills/mariyam/SKILL.md` из repo в runtime profile.
7. Проверить SHA-256 SKILL: `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`.
8. Перезапустить только Hermes Gateway профиля Мариям.
9. Проверить runtime inventory = **21**, plugin = **1.0.4**, Gateway active и отсутствие drift SKILL — PASS.
10. Провести controlled E2E только на временном test-user «Тест Ойижон», по одному сообщению и с DB-проверкой после каждого — PASS; cleanup восстановил baseline.

Не указывать в командах/отчётах Telegram ID, токены, mapping или другие секреты.

## FORBIDDEN — что НЕ трогать

- `/opt/time-agent`, `time_agent_bot`, Time-Agent `.env`, SQLite volume, logs, backups.
- Любой scheduler/router/intent-classifier/LLM-orchestrator в backend.

Hermes/Mariyam использует только свои ресурсы: `name: hermes-mariyam`, контейнеры `hermes_mariyam_*`, сеть `hermes_mariyam_net`, volume `hermes_mariyam_pg_data`, localhost-порт `${BACKEND_HOST_PORT}`.
