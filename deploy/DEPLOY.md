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

Применённые миграции (в порядке применения):

1. `001_init` — схема и справочники.
2. `002_stage51_quantity_budget` — количество и месячные бюджеты.
3. `003_stage53_product_plans` — планы продуктов.
4. `005_stage6_recurring_obligations` — повторяющиеся обязательства.
5. `006_user_news_sources` — пользовательские источники новостей.
6. `007_food_subcategories` — подгруппы еды: молочное, напитки, соусы,
   полуфабрикаты.

Миграция `004` в репозитории отсутствует.

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
- Baseline перед v3.19 controlled deploy: tools/dispatch/MCP discovery **21/21/21**, identity plugin **1.0.4**, migration 003 active; Stage 5.1 и Stage 5.2 — **CLOSED / LIVE PASS**, Stage 5.3 — **CLOSED / LIVE PASS** ([evidence](../docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md)).

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
   `memory_notifications: "off"`, `busy_ack_enabled: false`,
   `long_running_notifications: false`,
   `agent.disabled_toolsets: [skills, terminal, code_execution]`). Hermes v0.18.2
   относит `terminal`/`process` к `terminal`, а `execute_code` — к отдельному
   `code_execution`; оба отключаются только для Mariyam profile.
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

Repo Stage 5.3 = **CLOSED / LIVE PASS** ([evidence](../docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md)): migration 003 и расширение двух
существующих budget tools реализованы, inventory остаётся **21/21/21**. v3.19
разделяет omitted `items` и explicit empty, добавляет отдельный
`mariyam_stage53_guard` и profile-only `max_turns: 6`; identity plugin 1.0.4 и
Hermes core не меняются. Единственный canonical repo-source —
`deploy/hermes_profile_mariyam_oyijon/SOUL.md`, LF SHA
`ba51bee5411c0dafc5758060a7bfe0145b758df97077c6e2644d5705bcf6bf07`.

Controlled deploy guard:

1. Скопировать `deploy/hermes_plugins/mariyam_stage53_guard/` в profile `plugins/`.
2. Создать private state path вне `HERMES_HOME`: parent принадлежит service user,
   не является symlink и имеет mode 0700; задать `MARIYAM_STAGE53_STATE_FILE` через
   private profile environment. State/lock — regular non-linked files mode 0600.
3. Merge snippet так, чтобы middleware order был identity → Stage 5.3 guard и
   `agent.max_turns` был равен 6; profile secrets не заменять.
4. Reset только exact test-user session; restart только Mariyam Gateway.

VPS runtime уже использует migration 003, но до controlled fix deploy сохраняет
SOUL SHA `5f7b08569cfd75cd26d78a234fbb8a39322dfc65e9221ae2d461e89444148266`
и прежний profile config. Активный Mariyam `SKILL.md` отсутствует, skill-protect и
`tool_progress=off` сохранены. Stage 5.3A–6 остаются **PLANNED / NOT IMPLEMENTED**;
реальная Ойижон не подключена.

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

## Изоляция кодерских прогонов (imp12)

- `mariyam_oyijon` — семейный production-контур. На нём запрещены тестовые
  расходы, память, обязательства и cron-job'ы; допустима только согласованная
  приёмка на реальных данных без тестовых записей.
- Все кодерские сценарии выполнять только в профиле `mariyam_test` под
  внутренней учётной записью `Кодер тест`. У него отдельная БД `hermes_test`,
  пустые при создании память, cron и sessions; production-БД и память в этот
  профиль не копировать.
- У `mariyam_test` намеренно нет Telegram-токена, gateway-сервиса и доставки.
  До выдачи отдельного тестового bot token использовать только ручной CLI и
  backend-прогоны; токен семейного бота подключать к тестовому профилю нельзя.
- Перед любым destructive suite ещё раз проверить, что имя БД — ровно
  `hermes_test`. Если это не так, прогон немедленно остановить.

## Cron identity — обязательный шаг любого deploy (fix04)

Trusted cron-задачи привязаны к отпечатку своего определения. Отпечаток
считается по полям `id, name, prompt, schedule, repeat, deliver, origin,
skills, script, no_agent, context_from, enabled_toolsets, workdir, model,
provider, base_url`. Как только любое из них меняется, guard перестаёт
доверять задаче и **молча** отказывает её инструментам: задача отрабатывает и
даже доставляет сообщение, но без данных. Так уже дважды ломалась утренняя
сводка Ойижон — это её главное сообщение за день.

**Правило.** Отпечатки пересчитываются в том же прогоне, что и изменение —
не «потом руками». Пересчёт нужен не только после правки промпта: смена
расписания, `deliver` (например, перепривязка бота на другой Telegram-аккаунт
при handover), модели или провайдера ломает доверие точно так же.

```bash
python3 /opt/hermes-mariyam/deploy/imp04_refresh_cron_fingerprints.py           # dry-run
python3 /opt/hermes-mariyam/deploy/imp04_refresh_cron_fingerprints.py --apply
python3 /opt/hermes-mariyam/deploy/imp04_refresh_cron_fingerprints.py --check   # гейт: exit 1, если хоть одна задача не пройдёт guard
```

Требования к любому скрипту деплоя, который трогает профиль (SOUL, cron-задачи,
delivery, модель):

1. вызвать `--apply`, затем `--check` **до** рестарта gateway;
2. при ненулевом коде `--check` — откатиться и не деплоить;
3. сам файл `imp04_refresh_cron_fingerprints.py` должен лежать на VPS в
   `/opt/hermes-mariyam/deploy/`; его отсутствие — повод остановить деплой,
   а не пропустить шаг.

Это закреплено тестом `tests/test_fix04_cron_fingerprint_gate.py`: он падает,
если в `deploy/` появится скрипт, который пишет `SOUL.md` или `cron/jobs.json`
и не вызывает пересчёт отпечатков.

**Гейта в скриптах мало (fix05).** Определение задачи меняют и мимо деплоя:
`hermes cron edit`, перепривязка доставки при handover, ручная правка. Поэтому
расхождение ищет ещё и watchdog — на каждом тике таймера, раз в 15 минут:

- при расхождении шлёт админу отдельный алерт с именами задач (одно сообщение
  на набор расхождений в сутки, не спам каждые 15 минут);
- проверка идёт **после** обычной retry-логики, поэтому не может её подменить;
- отпечаток считается функциями самого guard, а не копией;
- ручной прогон без побочных эффектов:
  `python3 /opt/hermes-mariyam/deploy/watchdog/mariyam-cron-watchdog.py --check`
  (ничего не пишет, ничего не шлёт, exit 1 при расхождении).

Почему это важнее гейта: задача с устаревшим отпечатком отрабатывает
«успешно» — `last_status=ok`, доставка есть, output есть, — и прежний watchdog
считал её здоровой. Пустой оказывалась только сводка у мамы.

После deploy проверить, что доверены **все девять** задач: `--check` печатает
`fingerprints already current; 9 trusted job(s) verified`.

## Скрипты в `deploy/` (что осталось и зачем, imp07)

Одноразовые deploy-обёртки закрытых задач удалены (`imp04_deploy.sh`,
`imp04_patch_config.py`, `imp09_stt_deploy.sh`, `imp11_deploy.sh`) — их шаги
описаны ниже в исторических разделах и в evidence-документах. Оставлены только
те, что нужны при правках промптов, восстановлении и пересоздании профиля:

| скрипт | когда нужен |
|---|---|
| `imp04_refresh_cron_fingerprints.py` | **обязательно** после любой правки cron-задачи: пересчитывает `job_fingerprint_sha256` и `prompt_sha256` в приватной cron-identity-карте. Без этого identity guard заблокирует tools внутри job. Сначала без флага (dry-run), затем `--apply`, затем `--check` как гейт (см. раздел «Cron identity — обязательный шаг любого deploy») |
| `imp05_patch_config.py` | пересоздание профиля: идемпотентно добавляет `mariyam_outbound_filter` в `plugins.enabled` и блок `session_reset` (daily 02:00, notify off) |
| `imp09_patch_stt_config.py` | пересоздание профиля: STT-конфигурация голосовых сообщений |
| `imp04_job_id.py` | найти id cron-job по имени (нужен как вход для двух скриптов выше) |
| `fix02_deploy.sh` | исторический day-rhythm деплой; на него завязана регрессия `tests/test_day_rhythm.py`, поэтому файл сохранён |

## FORBIDDEN — что НЕ трогать

- `/opt/time-agent`, `time_agent_bot`, Time-Agent `.env`, SQLite volume, logs, backups.
- Любой scheduler/router/intent-classifier/LLM-orchestrator в backend.

Hermes/Mariyam использует только свои ресурсы: `name: hermes-mariyam`, контейнеры `hermes_mariyam_*`, сеть `hermes_mariyam_net`, volume `hermes_mariyam_pg_data`, localhost-порт `${BACKEND_HOST_PORT}`.

## Stage 6 daily-life controlled deploy

1. До замены файлов сохранить private backup backend, profile SOUL,
   `cron/jobs.json` и cron identity mapping; записать rollback path.
2. Добавить `OPENWEATHER_API_KEY` только в
   `/opt/hermes-mariyam-secrets/backend.env` (mode 0600). Значение не печатать.
   Aladhan key не требует.
   Для stdio MCP одной записи в private env недостаточно: gateway загружает
   profile `.env` через systemd drop-in
   `hermes-gateway-mariyam_oyijon.service.d/10-profile-env.conf`, а
   `mcp_servers.mariyam_backend.env.OPENWEATHER_API_KEY` хранит только
   placeholder `${OPENWEATHER_API_KEY}`. Основной unit генерирует Hermes и
   может перезаписать, поэтому `EnvironmentFile` нельзя добавлять только туда.
3. Установить `backend/external_data.py`, `backend/server.py`, canonical SOUL и
   три `cron/06_*.md`; cache path =
   `/opt/hermes-mariyam/var/external-data-cache.json`.
4. Создать три jobs штатным Hermes cron:
   `30 8 * * *` morning, `15 9 * * *` obligation reminders,
   `30 19 * * *` evening, timezone profile = Asia/Tashkent.
5. В private cron mapping добавить exact fingerprints:
   morning → только `get_recurring_obligations`; reminder → только
   `get_recurring_obligations`; evening → только `get_admin_report_data`.
   Mapping atomic, owner service user, mode 0600. External tools не
   user-scoped и в mapping не входят.
6. Compile, restart только `hermes-gateway-mariyam_oyijon.service`; проверить
   **29/29/29**, health, guard 1.3.0, `cron.wrap_response=false`.
7. Controlled manual runs + минимум один штатный tick только на временный
   test-user. One-shot probe не добавлять в mapping; prompt — готовый текст,
   tools = 0. После evidence удалить probe job/session/output и test obligation.

Rollback: pause/remove только три Stage 6 jobs, атомарно вернуть предыдущий
private mapping и `cron/jobs.json`, восстановить backend/SOUL из backup,
удалить cache-файл (он содержит только публичные facts), restart только
Mariyam Gateway. Migration 005 и существующие пять Stage 5.3A jobs не менять.

## Stage 7 admin report + health alerts controlled deploy

1. Сохранить private backup: backend `db.py`, profile SOUL/config/plugins,
   `cron/jobs.json`, cron identity mapping и production DB dump. Не печатать
   mapping/Telegram IDs/health text.
2. Установить `mariyam_health_guard` в profile plugins и
   `stage7_record_keyword_alert.py` в profile `scripts/`; script и plugin
   принадлежат service user, не symlink. Добавить в private service env только
   non-secret absolute paths:
   `MARIYAM_BACKEND_ROOT=/opt/hermes-mariyam`,
   `MARIYAM_HEALTH_ALERT_PYTHON=/opt/hermes-mariyam/.venv/bin/python`,
   `MARIYAM_HEALTH_ALERT_SCRIPT=<profile>/scripts/stage7_record_keyword_alert.py`.
3. Merge profile config: enabled plugins =
   identity guard → health guard → Stage 5.3 guard. Hermes core не менять.
4. Установить backend `db.py`, SOUL и `cron/07_admin_report.md`. Создать один
   trusted job `30 19 * * *`, delivery = test-admin, mapped actor =
   test-Oyijon, allowed tools = только `get_admin_report_data`.
5. Атомарно обновить mapping (0600) exact prompt/fingerprint, compile и
   перезапустить только `hermes-gateway-mariyam_oyijon.service`.
6. Проверить 29/29/29, health, plugin registrations, dataset recall=100%,
   SQL/report equality. Live: manual admin report + 2–3 alert-фразы только с
   test-Oyijon; подтвердить мягкий ответ, отдельный admin message и
   `alert_events`, затем удалить только test rows/sessions.

Rollback: pause/remove только Stage 7 admin job; вернуть сохранённые mapping,
jobs/backend/SOUL/config/plugins/env; удалить private health-guard state и
writer только если они созданы этим deploy; restart только Mariyam Gateway.

## Cron reliability watchdog + no-agent one-shot controlled deploy

1. До изменения сохранить private backup profile SOUL/config/plugins,
   `cron/jobs.json`, cron identity mapping и текущих systemd units. Записать
   active commit marker; секреты и Telegram IDs не выводить.
2. Установить `deploy/hermes_plugins/mariyam_cron_reliability/` в profile
   `plugins/`, canonical SOUL и merge config order:
   identity → health → cron reliability → Stage 5.3. Не заменять `.env`.
3. Установить `deploy/watchdog/` в `/opt/hermes-mariyam/deploy/watchdog/`.
   Создать `/opt/hermes-mariyam/var/watchdog` owner `timeagent`, mode 0700.
   Установить user units `mariyam-cron-watchdog.service/.timer` и
   `mariyam-heartbeat-failure@.service` в
   `~/.config/systemd/user/`, выполнить `systemctl --user daemon-reload`,
   enable/start timer. Existing linger обеспечивает работу после logout/reboot;
   watchdog state создаётся mode 0600.
4. Перезапустить только user-unit
   `hermes-gateway-mariyam_oyijon.service`. Backend/PostgreSQL/migrations и
   Hermes core не менять.
5. Проверить plugin registration, timer active, watchdog service PASS,
   29/29/29, health, cron/mapping 9/9 и exact восемь watched jobs.
   Для всех trusted jobs подтвердить `script=null`, `no_agent=false`.
6. E2E только на test identities: safe simulated failed state →
   один retry/delivery; forced retry failure → один direct test-admin alert;
   healthy state → silence. Создать будущий one-shot из Telegram test-Oyijon,
   подтвердить `no_agent=true`, timely exact delivery без нового LLM-run и
   удалить test job/session/output/scripts/state.

Rollback: `systemctl --user disable --now` и удалить только watchdog
timer/service/failure unit, вернуть profile
SOUL/config/plugin из private backup, удалить только imp08 watchdog state и
оставшиеся imp08 test artifacts, restart только Mariyam Gateway. Production
trusted jobs/mapping, backend, migration 005, PostgreSQL и Stage 8 heartbeat не
изменять.

## fix02: day rhythm controlled deploy

До deploy обязателен approval заказчика на два примера каждого prayer-slot и
точный список RSS. После approval bundle загружается в `/tmp/fix02`; скрипт
работает от `timeagent`:

```bash
bash /tmp/fix02/deploy/fix02_deploy.sh
bash /tmp/fix02/deploy/fix02_deploy.sh --apply
```

Apply создаёт private backup, останавливает только Mariyam Gateway, ставит
backend news-config, cron reliability 1.1.0, day-rhythm helper/systemd units,
меняет morning schedule/prompt и evening prompt, затем пересобирает private
trusted fingerprints до запуска Gateway. Prayer scheduler создаёт только
finite `no_agent=true` jobs для единственного Oyijon из private mapping.

Rollback указывается строкой из apply:

```bash
bash /tmp/fix02/deploy/fix02_deploy.sh --rollback \
  /home/timeagent/fix02-backup-YYYYMMDD_HHMMSS
```

После apply проверить: plugin order identity → health → cron reliability →
Stage 5.3; backend `29/29/29`; morning exact `0 8 * * *`; watchdog exact;
prayer timer active; шесть daily finite jobs без LLM; quiet-state 0600;
health-alert не подавляется; rollback backup остаётся private.
