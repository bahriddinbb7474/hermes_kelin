# Задания кодеру — фиксы по аудиту (ТЗ v3.1)

**Источник истины:** `TZ_Hermes_Mariyam_FINAL_v3_0.md` (внутри — версия 3.1, раздел 0.1 — список изменений).
**Ветка работы:** `feature-hermes-mariyam-mvp` (в `.worktrees/`).
**Статус:** deploy на VPS ЗАБЛОКИРОВАН, пока не закрыты все задачи Блока A и не пройден Definition of Done.

Правила:

1. Сначала выполнить Шаг 0 (синхронизация с main), потом задачи строго по порядку: A → B → C.
2. Каждая задача имеет раздел «Проверка» — она обязательна, «сделал, но не проверил» = не сделал.
3. Hermes-first не трогать: никакой логики смысла, router'ов, scheduler'ов на backend. Все фиксы — storage/инфраструктура.
4. Commit — только после того, как весь блок сделан и проверен; commit message указывать в отчёте. Push/deploy — только с разрешения Бахриддина.
5. В отчёте о сдаче: список задач, вывод команд проверки (маркеры тестов, вывод docker/systemd команд), изменённые файлы.

---

## Шаг 0. Синхронизация документации

В worktree ветки выполнить merge main (там обновлены ТЗ v3.1, TOOLS_CONTRACTS.md, DATABASE.md, SECURITY_PRIVACY.md, ARCHITECTURE.md, ACCEPTANCE_CRITERIA.md):

```bash
cd .worktrees/feature-hermes-mariyam-mvp
git merge main
```

Конфликтов быть не должно (правки только в docs). Прочитать раздел 0.1 ТЗ перед началом работы.

---

# БЛОК A — КРИТИЧЕСКИЕ (deploy заблокирован без них)

## A1. Утечка пула соединений (`backend/config.py`, `backend/server.py`)

**Проблема.** `get_pool()` в `config.py` создаёт **новый** `asyncpg.create_pool()` при каждом вызове, а `call_tool()` в `server.py:39` зовёт его на каждый tool-вызов и никогда не закрывает. Каждый пул навсегда держит ≥1 соединение. При Postgres `max_connections=100` backend перестанет работать примерно после 90 вызовов — тихо, посреди месяца.

**Что сделать.** Кэшировать пул на уровне модуля — создаётся один раз, дальше переиспользуется:

```python
# config.py
import asyncio

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool
```

Lock обязателен: первые вызовы могут прийти конкурентно. В `server.py` ничего менять не нужно (он продолжает звать `get_pool()`), но убрать бессмысленную обёртку `_pool()` (строки 25–26) и звать `get_pool()` напрямую.

**Проверка.**
1. В тесты (задача C2) добавить цикл ≥50 вызовов `call_tool("get_bot_status", {})` подряд, затем:
   ```sql
   SELECT count(*) FROM pg_stat_activity WHERE datname='hermes';
   ```
   Число соединений ≤ 6 (max_size 5 + сам запрос). Assert в тесте, маркер `POOL_STABLE_PASSED`.
2. `tests/run_tests.py` по-прежнему печатает `ALL_TOOL_TESTS_PASSED` и `TZ_BOUNDARY_PASSED`.

## A2. Убрать fallback-креды из кода и Dockerfile (ТЗ §17, §20 п.14)

**Проблема.** Блокер B3 закрыт только в compose. Слабые креды `hermes:hermes` остались:
- `backend/config.py:12-15` — `DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes")`;
- `backend/Dockerfile:21` — `ENV ... DATABASE_URL=postgresql://hermes:hermes@db:5432/hermes`.

**Что сделать.**
1. `config.py`: fail fast. `DATABASE_URL` читать лениво (функцией), при отсутствии — падать с понятной ошибкой:
   ```python
   def get_database_url() -> str:
       url = os.environ.get("DATABASE_URL")
       if not url:
           raise RuntimeError(
               "DATABASE_URL is not set. Configure backend/.env or environment. "
               "Weak fallback credentials are forbidden (TZ §17)."
           )
       return url
   ```
   `get_pool()` использует `get_database_url()`. Важно: читать env в момент вызова, не при импорте модуля — иначе тесты не смогут подставить свой URL.
2. `Dockerfile`: удалить строку `DATABASE_URL=...` из `ENV` полностью. Остальные ENV (`MCP_TRANSPORT` и т.д.) оставить.
3. `tests/run_tests.py`: убрать двойное `os.environ.setdefault` с зашитым URL (строки 15-18) — см. задачу C1 (тестовый URL задаётся явно с предохранителем).

**Проверка.**
- `python -c "import os; os.environ.pop('DATABASE_URL', None); from backend.config import get_database_url; get_database_url()"` → падает с RuntimeError и понятным текстом.
- `grep -rn "hermes:hermes" backend/ docker-compose.yml` → ноль результатов (кроме, возможно, комментариев в docs).
- Тесты проходят с явно заданным `DATABASE_URL`.

## A3. `.dockerignore` — секреты не должны попадать в образ (ТЗ §17)

**Проблема.** `.dockerignore` нет. Build context = корень репозитория, а `Dockerfile` делает `COPY backend/ ./backend/` — в слой образа копируются **реальный `backend/.env` с паролем** и 47 МБ `backend/.venv`.

**Что сделать.** Создать `.dockerignore` в корне репозитория:

```
.git
.gitignore
.worktrees
.env
.env.*
!.env.example
**/.env
**/.venv
**/__pycache__
*.py[cod]
logs
*.log
tmp
temp
tests
deploy
*.md
Hermes-Oyijon-TZ
skills
```

Минимально обязательные строки: `.git`, `**/.env`, `**/.venv`, `**/__pycache__`. Остальное — чтобы образ был маленьким (в него нужны только `backend/*.py`, `backend/requirements.txt`, `backend/sql/`).

**Проверка.**
```bash
docker compose build hermes_mariyam_backend
docker run --rm --entrypoint sh <image> -c "ls -la /app/backend/; test ! -e /app/backend/.env && test ! -d /app/backend/.venv && echo IMAGE_CLEAN"
```
Ожидаемый вывод содержит `IMAGE_CLEAN`. Вывод приложить к отчёту.

**Дополнительно:** уже собранные ранее образы содержат `.env` в слоях — удалить их локально (`docker image rm` + `docker builder prune`) и **сменить `POSTGRES_PASSWORD`** в `backend/.env` (пароль считать скомпрометированным локально; на VPS он ещё не уезжал).

## A4. systemd-юнит не загрузится (`deploy/hermes-mariyam.service`)

**Проблема.** `Type=oneshot` + `Restart=always` — недопустимая комбинация; systemd откажется загружать юнит («Restart= setting other than no isn't allowed for Type=oneshot»). На VPS автозапуск просто не включится.

**Что сделать.**
1. Удалить строку `Restart=always` из `[Service]`.
2. Оставить `Type=oneshot` + `RemainAfterExit=yes`. Перезапуски контейнеров уже обеспечивает `restart: unless-stopped` в compose + `Restart=always` у docker.service.
3. Обновить комментарий в шапке юнита: перезапуск — ответственность docker, не systemd.
4. В `deploy/DEPLOY.md` поправить неточность: секреты попадают в compose не через `env_file:` (такой директивы в compose нет), а через **интерполяцию переменных окружения процесса** `docker compose` (systemd `EnvironmentFile=` кладёт их в env юнита). Там же добавить предупреждение: при ручном запуске `docker compose down` без загруженного env будет warning об unset `POSTGRES_PASSWORD` — использовать `set -a; . /opt/hermes-mariyam-secrets/backend.env; set +a` перед ручными compose-командами.

**Проверка.** На Linux/VPS позже: `systemd-analyze verify deploy/hermes-mariyam.service`. Сейчас на Windows — визуальная проверка + приложить diff юнита к отчёту. В DEPLOY.md добавить шаг «`systemd-analyze verify` перед `systemctl enable`».

## A5. Tool `ensure_user` + seed пользователей (ТЗ §13.2, §15.15)

**Проблема.** Все tools требуют `user_id`, но создать пользователя нечем: `db.ensure_user` есть, но не экспонирован как tool и не задокументирован seed. Первый реальный `save_expense` на чистой БД упадёт с FK-violation → невнятный `INTERNAL`.

**Что сделать.**
1. Доработать `db.ensure_user`: возвращать `(user_id, created)`; при существующем `telegram_id` — вернуть существующий id, `created=False`, **не** перезаписывая role/display_name. Валидировать `role in ('oyijon','admin')` в коде → `INVALID_INPUT` (не CHECK из БД). Использовать `INSERT ... ON CONFLICT (telegram_id) DO NOTHING` + последующий SELECT, чтобы не ловить гонку.
2. В `server.py`: добавить `t_ensure_user` в `DISPATCH` и `TOOLS`. Контракт — ТЗ §15.15:
   ```jsonc
   in:  { "telegram_id": 111222333, "role": "oyijon", "display_name": "Ойижон" }
   out: { "ok": true, "user_id": 1, "created": true|false }
   ```
3. В `deploy/DEPLOY.md` добавить раздел «Seed пользователей (обязательно до подключения Hermes)»: вызов `ensure_user` через MCP-клиент **или** запасной SQL:
   ```sql
   INSERT INTO users (telegram_id, role, display_name) VALUES
     (<TG_ID_ОЙИЖОН>, 'oyijon', 'Ойижон'),
     (<TG_ID_АДМИНА>, 'admin',  'Бахриддин ака')
   ON CONFLICT (telegram_id) DO NOTHING;
   ```

**Проверка.** В тестах: `ensure_user` дважды с одним `telegram_id` → одинаковый `user_id`, второй раз `created:false`; с `role="bogus"` → `INVALID_INPUT`. Входит в smoke-тест C2.

---

# БЛОК B — НАДЁЖНОСТЬ И КОНТРАКТЫ

## B1. Транспорт MCP: stdio по умолчанию, HTTP — только через SDK session-manager (ТЗ §16 п.5–6)

**Проблема.** HTTP-обвязка в `server.py:262-299` самодельная и хрупкая: один глобальный `StreamableHTTPServerTransport` на весь lifespan (переподключение Hermes может убить сессию), обращение к приватному `request._send`, задублированная строка `init_options` (строки 273 и 279). При этом `.env.example` рекомендует stdio, а compose/Dockerfile жёстко ставят http — противоречие.

**Что сделать.**
1. Принять решение ТЗ v3.1: **на VPS — stdio**. Hermes запускает `python -m backend` как subprocess; docker compose используется только для Postgres.
2. Переписать HTTP-ветку `main()` на `StreamableHTTPSessionManager` из официального `mcp` SDK (модуль `mcp.server.streamable_http_manager`) — он сам управляет сессиями и ASGI. Убрать: ручной `StreamableHTTPServerTransport`, `request._send`, дублирование `init_options`.
3. Compose оставить рабочим (для локальной проверки и как запасной вариант), но в `deploy/DEPLOY.md` явно разделить: «VPS-вариант по умолчанию: compose поднимает ТОЛЬКО Postgres; backend региструется в Hermes как stdio-команда» и дать пример конфигурации MCP в Hermes (command: `python -m backend`, env: `DATABASE_URL=...`, `MCP_TRANSPORT=stdio`).

**Проверка.**
- stdio: smoke-тест C2 работает in-process (он транспорта не касается) + ручная проверка `python -m backend` стартует и отвечает на initialize (можно через `mcp` client из venv или простым JSON-RPC в stdin).
- http: `docker compose up -d`, затем curl-initialize из DEPLOY.md шаг 4 возвращает валидный JSON-RPC ответ, и **повторный** initialize (вторая сессия) тоже работает. Вывод приложить.

## B2. Баг `custom`-периода в `_period_bounds` (`backend/db.py:151-160`)

**Проблема.** При `custom` с только `from` (без `to`): `_day_bounds(from)` присваивает и `s`, и `e`, но следующая ветка перезаписывает `e = parse_dt(None) = None` → SQL с NULL-границей → `INTERNAL`. Также `custom` вообще без `from`/`to` даёт `s=None, e=None`.

**Что сделать.** Переписать `custom`-ветку явно:
- есть `from`, нет `to` → интервал = [день `from` по Ташкенту, конец дня `from`] если `from` — дата; если `from` — datetime, то `to` обязателен;
- есть оба → как сейчас (дата = ташкентские границы дня, datetime = как есть); `e` не должен затираться;
- нет `from` и нет `to` → `raise ValueError("INVALID_INPUT: custom period requires from/to")`;
- `from > to` → `INVALID_INPUT`.
Маппинг `INVALID_INPUT` в `call_tool` уже есть.

**Проверка.** Тесты: `expense_report(pool, oy, "custom", "2026-07-09", None)` возвращает данные дня 9-го (не ошибку); `("custom", None, None)` → ValueError INVALID_INPUT; `("custom", "2026-07-10", "2026-07-09")` → INVALID_INPUT. Существующий TZ-boundary тест не ломается.

## B3. Честные заглушки backup (ТЗ §15, §20 п.16)

**Проблема.** `t_backup_data` возвращает `ok:true`, `t_get_backup_status` — `last_ok:true`, хотя backup не настроен. Админ будет уверен, что бэкапы есть.

**Что сделать.** До реализации Этапа 8 оба tool'а возвращают:
```json
{ "ok": false, "error_code": "NOT_CONFIGURED",
  "message_ru": "Backup ещё не настроен (Этап 8)", "message_uz": "Заҳира нусхаси ҳали созланмаган" }
```
Описания в `TOOLS` дополнить пометкой «до Этапа 8 возвращает NOT_CONFIGURED».

**Проверка.** Smoke-тест C2: оба tool'а возвращают `ok:false`, `error_code:"NOT_CONFIGURED"`.

## B4. Per-tool inputSchema с `required` (ТЗ §15)

**Проблема.** Одна `SCHEMA_OBJ` на все 18 tools, без `required` (`server.py:203-238`). Hermes-LLM видит у каждого tool одинаковую схему со всеми полями сразу — это ухудшает точность tool-calling; валидация обязательных полей сейчас работает через KeyError.

**Что сделать.** Для каждого tool — своя схема только с его полями и блоком `required`. Пример:

```python
def schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}

SAVE_EXPENSE_SCHEMA = schema({
    "user_id": {"type": "integer"},
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "item_name": {"type": "string"},
        "amount_uzs": {"type": "number"},
        "category_code": {"type": "string"},
    }, "required": ["amount_uzs"]}},
    "occurred_at": {"type": "string", "description": "UTC ISO 8601 или дата (день по Ташкенту)"},
    "source_type": {"type": "string", "enum": ["text", "voice", "admin"]},
    "source_text": {"type": "string"},
}, required=["user_id", "items"])
```

`required` по ТЗ §15: `save_expense`: user_id, items; `save_income`: user_id, amount; `update_expense`: user_id, expense_id, fields; `update_last_expense`: user_id, fields; `delete_expense`: user_id, expense_id; `delete_last_expense`: user_id; `get_expense_report`: user_id; `get_balance_summary`: user_id; `save_quran_progress`: user_id; `get_quran_progress`: user_id; `save_health_note`: user_id, note; `save_alert_event`: user_id, alert_type, severity, source_text; `save_plan_note`: user_id, text; `get_admin_report_data`: user_id; `backup_data`/`get_backup_status`/`get_bot_status`: без required; `log_usage_cost`: provider, service_type, units, estimated_cost_usd; `ensure_user`: telegram_id, role, display_name. Enum-поля (`currency`, `severity`, `source_type`, `detected_by`, `service_type`, `period`, `role`) описать через `"enum": [...]`.

Дополнительно в `call_tool`: перед dispatch проверять наличие required-полей самим кодом (не полагаться на клиента) → `INVALID_INPUT` с перечнем недостающих полей.

**Проверка.** Smoke-тест: `list_tools()` возвращает 19 tools, у каждого схема не идентична соседним (assert на разные `required`); вызов `save_expense` без `items` → `INVALID_INPUT`, не KeyError/INTERNAL.

## B5. Валидация enum-полей в коде, а не CHECK-ом БД

**Проблема.** Невалидные `currency`, `severity`, `source_type`, `detected_by`, `service_type` сейчас доходят до INSERT и падают CHECK-констрейнтом → пользователь получает `INTERNAL` вместо понятной ошибки.

**Что сделать.** В `db.py` завести константы:
```python
CURRENCIES = ("UZS", "USD")
HEALTH_SEVERITIES = ("info", "low", "medium", "high", "critical")
ALERT_SEVERITIES = ("low", "medium", "high", "critical")
SOURCE_TYPES = ("text", "voice", "admin")
DETECTED_BY = ("llm", "keyword", "both")
SERVICE_TYPES = ("stt", "tts", "llm")
ROLES = ("oyijon", "admin")
```
и проверять входы в соответствующих функциях: невалидно → `raise ValueError("INVALID_INPUT: <поле> must be one of ...")`. CHECK-констрейнты в SQL остаются (вторая линия защиты).

**Проверка.** Тесты: `save_income(..., currency="EUR")` → INVALID_INPUT; `save_health_note(..., severity="huge")` → INVALID_INPUT; `save_alert_event(..., detected_by="magic")` → INVALID_INPUT.

## B6. `update_expense` с пустыми `fields` → `INVALID_INPUT`, не `NOT_FOUND`

**Проблема.** `db.update_expense` при пустых/неизвестных `fields` возвращает `None`, что сервер маппит в `NOT_FOUND` — вводит Hermes в заблуждение (запись-то существует).

**Что сделать.** Если после разбора `fields` список `sets` пуст → `raise ValueError("INVALID_INPUT: fields is empty, nothing to update")`.

**Проверка.** Тест: `update_expense(pool, oy, id, {})` → INVALID_INPUT; `update_expense` на несуществующий id → по-прежнему NOT_FOUND.

## B7. `get_admin_report_data` без `date` возвращает `date: null`

**Проблема.** `admin_report_data` кладёт в ответ исходный `date_str`; при `date=None` Hermes получает `"date": null`, хотя отчёт посчитан за сегодняшний ташкентский день.

**Что сделать.** Если `date_str` не передан — вычислить и вернуть фактическую дату дня по Ташкенту (`datetime.now(TASHKENT).date().isoformat()`).

**Проверка.** Тест: вызов без `date` → в ответе валидная строка `YYYY-MM-DD`.

---

# БЛОК C — ТЕСТЫ, ГИГИЕНА, ДОКУМЕНТАЦИЯ

## C1. Предохранитель тестов от боевой БД (ТЗ §20 п.15)

**Проблема.** `tests/run_tests.py` делает `TRUNCATE ... CASCADE`. Направленный на боевую БД, он сотрёт все данные Ойижон.

**Что сделать.** В начале тестов:
```python
db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    sys.exit("DATABASE_URL is not set for tests")
allowed = ("localhost" in db_url or "127.0.0.1" in db_url or "_test" in db_url)
if not allowed and os.environ.get("ALLOW_DESTRUCTIVE_TESTS") != "1":
    sys.exit("REFUSED: tests TRUNCATE the database; DATABASE_URL does not look like a test DB. "
             "Set ALLOW_DESTRUCTIVE_TESTS=1 only if you are absolutely sure.")
```
Также убрать зашитый дефолтный URL (см. A2): без явного `DATABASE_URL` тесты не стартуют.

**Проверка.** Запуск без `DATABASE_URL` → отказ с понятным сообщением. Запуск с `DATABASE_URL=postgresql://...@some-prod-host/...` → `REFUSED`. Запуск с localhost → тесты идут.

## C2. Smoke-тест через MCP-слой (`call_tool`)

**Проблема.** Тесты гоняют `db.*` напрямую — `call_tool`, dispatch, маппинг ошибок и схемы не покрыты вообще. Утечку пула (A1) текущие тесты тоже не видят.

**Что сделать.** Добавить в `tests/run_tests.py` функцию `test_mcp_smoke()` (in-process, без транспорта — импортировать `call_tool`, `list_tools` из `backend.server` и звать напрямую):
1. `list_tools()` → ровно 19 tools, имена совпадают со списком ТЗ §15; у каждого — свой inputSchema с `required` (B4).
2. Успешный путь каждого tool'а через `call_tool(name, args)` → распарсить JSON из `TextContent`, assert `ok:true` (кроме backup-заглушек → `NOT_CONFIGURED`, B3).
3. Ошибочные пути: `BAD_CATEGORY`, `BAD_AMOUNT`, `NOT_FOUND` (update несуществующего id), `INVALID_INPUT` (пустые fields, невалидная currency, custom без границ), `UNKNOWN_TOOL` (вызов несуществующего имени).
4. Цикл 50× `call_tool("get_bot_status", {})` + проверка `pg_stat_activity` (A1) → маркер `POOL_STABLE_PASSED`.
5. Итоговый маркер: `MCP_SMOKE_PASSED`.

**Проверка.** `tests/run_tests.py` печатает все четыре маркера: `ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`, `MCP_SMOKE_PASSED`, `POOL_STABLE_PASSED`.

## C3. Чистка кода

- `server.py`: убрать неиспользуемый импорт `DATABASE_URL` (после A2 его вообще не будет); перенести `import os` наверх к остальным; удалить дублированную строку `init_options` (уйдёт вместе с B1); убрать обёртку `_pool()`.
- `db.py`: убрать неиспользуемый `import asyncpg`; локальные `from datetime import ...` внутри функций поднять в шапку модуля.
- `config.py`: заменить `TASHKENT = timezone(__import__("datetime").timedelta(hours=5))` на нормальный код: либо `from zoneinfo import ZoneInfo; TASHKENT = ZoneInfo("Asia/Tashkent")` (тогда `tzdata` в requirements оправдан), либо `from datetime import timedelta, timezone; TASHKENT = timezone(timedelta(hours=5))` и убрать `tzdata` из requirements. Рекомендуется первый вариант. `__import__` в продакшен-коде недопустим.
- `requirements.txt`: убрать `python-dotenv`, если он нигде не импортируется (сейчас не импортируется); после B1 проверить актуальность `starlette`/`anyio` (uvicorn может тянуть их сам — оставить явно, если используются напрямую).

**Проверка.** `python -m pyflakes backend/` (или `ruff check backend/`) — ноль warnings о неиспользуемых именах. Все тесты проходят.

## C4. Сузить keyword-список в `skills/mariyam/SKILL.md` (ТЗ §10.2 v3.1)

**Проблема.** Skill расширил список ТЗ бытовыми словами `ёмон`, `ёрдам`, `дард`, `бемор`, `температура` — «об-ҳаво ёмон» будет эскалироваться админу. Спам убьёт доверие к алертам.

**Что сделать.** В разделе 9 SKILL.md заменить список на узкие корни фраз из ТЗ §10.2:
`юрагим оғри`, `кўкрагим оғри`, `нафас ол(иш қийин)`, `бошим айлан`, `ҳушим кет`, `қон босим(им баланд)`, `ёмон бўляпман` (именно фраза целиком, не слово `ёмон`).
Добавить правило из ТЗ: одиночные бытовые слова в список не включать; расширение — только по фактам пропусков. Также добавить в раздел 9 строку: «Если Hermes поддерживает pre-processing hooks — keyword-проверка настраивается там (см. ТЗ §10.2); инструкция ниже — обязательный минимум».

**Проверка.** Ручной чек-лист: фразы «об-ҳаво ёмон экан», «менга ёрдам беринг, харажат ёзинг», «оёғим бироз дард қиляпти» НЕ должны подпадать под keyword-корни списка (прогнать глазами/скриптом по подстрокам). Все 7 фраз из ТЗ §10.2 — подпадают.

## C5. Обновить `deploy/DEPLOY.md`

Свести туда все изменения блоков A/B:
1. Раздел «Seed пользователей» (A5) — обязательный шаг до подключения Hermes.
2. Раздел «Транспорт»: VPS-вариант по умолчанию stdio (compose только для Postgres), HTTP — запасной (B1).
3. Правка про env_file/интерполяцию + `set -a` для ручных compose-команд (A4).
4. Шаг «Миграции» (ТЗ §13.2): initdb-скрипты применяются только при первом создании volume; команда ручного применения `psql -f` для будущих `002_*.sql`.
5. Шаг «Проверка образа»: команда из A3 (`IMAGE_CLEAN`).
6. Шаг «systemd-analyze verify» перед enable (A4).
7. В раздел тестов: `DATABASE_URL` обязателен, предохранитель C1, четыре ожидаемых маркера (C2).
8. Убрать/поправить примеры с паролем в командной строке: `DATABASE_URL=postgresql://hermes:<пароль>@...` в шелл-команде остаётся в history — рекомендовать `export $(grep -v '^#' backend/.env | xargs)` или `set -a; . backend/.env; set +a`.

**Проверка.** Прогнать «Локальную проверку» из обновлённого DEPLOY.md с нуля (свежий volume): все команды работают как написано, маркеры тестов на месте.

---

# Порядок выполнения и Definition of Done

Порядок: Шаг 0 → A1 → A2 → A3 → A4 → A5 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → C1 → C2 → C3 → C4 → C5.

Deploy разблокируется, когда ВСЁ нижеследующее истинно:

- [ ] `tests/run_tests.py` печатает `ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`, `MCP_SMOKE_PASSED`, `POOL_STABLE_PASSED` на чистой compose-БД.
- [ ] `grep -rn "hermes:hermes" backend/ docker-compose.yml` — пусто; запуск без `DATABASE_URL` падает сразу с понятной ошибкой.
- [ ] Проверка образа даёт `IMAGE_CLEAN`; старые образы удалены; локальный `POSTGRES_PASSWORD` сменён.
- [ ] В юните нет `Restart=` при `Type=oneshot`; в DEPLOY.md есть шаг `systemd-analyze verify`.
- [ ] `list_tools()` = 19 tools (с `ensure_user`), у каждого своя схема с `required`.
- [ ] `backup_data`/`get_backup_status` → `NOT_CONFIGURED`.
- [ ] Тесты отказываются работать с не-тестовой БД.
- [ ] SKILL.md: keyword-список сужен до корней фраз ТЗ §10.2.
- [ ] DEPLOY.md актуален (seed, stdio, миграции, image-check, verify, маркеры).
- [ ] `ruff check backend/` (или pyflakes) — чисто.
- [ ] Ничего из ТЗ §20 (запреты 1–16) не нарушено; на backend не появилось ни строчки «логики смысла».

Формат отчёта о сдаче: список задач со статусом, вывод всех команд «Проверка», изменённые файлы, предлагаемый commit message. Commit после ревью, push/deploy — только по команде Бахриддина.
