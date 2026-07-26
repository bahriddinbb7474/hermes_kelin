# Tools Contracts

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md` (полные примеры вход/выход — §15).
Реализация: `backend/server.py` + `backend/db.py` + `backend/external_data.py`.
**Repo inventory: 29 tools (dispatch/MCP discovery = 29/29).** Stage 6 шаг 2
добавляет три read-only external-data tool с суточным файловым кэшем.

**Progression:** Stage 5.3 = 21, Stage 5.3A = 24, Stage 6 шаг 1 = 26,
Stage 6 шаг 2 = 29. Stage 5.4 utility tools остаются NO-GO/не реализованы,
поэтому numbering migration 005 намеренно пропускает 004.

## Общие правила

Все tools — один MCP-сервер. Hermes вызывает tools сам; backend не решает смысл сообщения и **не пишет советы/прозу**.

Конвенции:

- успех: `{ "ok": true, ... }`;
- ошибка: `{ "ok": false, "error_code": "...", "message_ru": "...", "message_uz": "..." }`;
- время: UTC ISO 8601, границы дней — Asia/Tashkent;
- суммы: в сумах;
- категории расходов только из фиксированного списка;
- per-tool inputSchema с `required`;
- один пул соединений на процесс;
- `NOT_CONFIGURED` вместо ложного успеха.

## Детерминированная identity binding (repo/VPS 1.0.4)

- Для user-scoped tools effective `user_id` переписывается identity guard до backend.
- Новые user-scoped tools Этапа 5.1 (`set_monthly_budget`, `get_monthly_budget_status`) — **тоже** под guard (self-only для oyijon).
- Malformed/unknown → fail-closed `IDENTITY_*`.

## Базовые 19 tools (в составе текущего inventory 29)

- `ensure_user`, `save_expense`, `save_income`, `update_expense`, `update_last_expense`, `delete_expense`, `delete_last_expense`, `get_expense_report`, `get_balance_summary`, `save_quran_progress`, `get_quran_progress`, `save_health_note`, `save_alert_event`, `save_plan_note`, `get_admin_report_data`, `backup_data`, `get_backup_status`, `get_bot_status`, `log_usage_cost`.

## Live tools Этапа 5.1 (+2 → runtime 21)

- `set_monthly_budget` — upsert план категории на месяц.
- `get_monthly_budget_status` — planned/actual/remaining + by_category usage_percent.

## Расширения (v3.7 requirements; live verified)

**save_expense items (optional):** `item_name_normalized`, `quantity`, `unit` (canonical units; unit only with quantity).

**get_expense_report (optional in):** `compare_previous`, `trend_months` (default 3, max 12).

**get_expense_report (out extras):** `by_item` (total_uzs, purchase_count, quantity_by_unit, average_unit_price_uzs if homogeneous), `previous_period` (change_percent=null if prev total=0), `monthly_series`.

## Stage 5.3 implemented contract extensions

### Stage 5.3 — без новых tools, runtime count остаётся 21

- `set_monthly_budget`: optional `items[]`; каждый planned item может содержать `item_name_normalized`, `item_name_display`, `planned_quantity`, `unit`, `planned_amount_uzs`, `reference_unit_price_uzs`, `price_basis`, `price_as_of`, `note`. Минимум одно из `planned_quantity` или `planned_amount_uzs` обязательно.
- Если `items` отсутствует, допустим category-only plan и product rows не меняются. Если key передан, значение обязано быть непустым массивом: `items=[]`, `items=null` и любой non-array возвращают `INVALID_INPUT` до открытия pool/transaction; ни category plan, ни product rows не изменяются. Непустой `items` атомарно заменяет category + products. Подтверждённый product draft использует exact fields; factual snapshot last/average сверяется с transactions.
- `get_monthly_budget_status(include_items=true)` возвращает по item: `planned_quantity`, `planned_unit`, `planned_amount_uzs`, `actual_quantity`, `actual_unit`, `actual_amount_uzs`, `remaining_amount_uzs`, `last_unit_price_uzs`, `average_unit_price_uzs`, `reference_unit_price_uzs`, `price_basis`, `price_as_of`. Unknown = `null`, не `0`; разные units не смешиваются.
- `get_monthly_budget_status(price_lookup_items=[...])` — optional read-only lookup до draft. Каждый элемент требует `item_name_normalized`, exact `unit` и `price_basis=last|average`; максимум 50. Output дополнительно возвращает выбранные `reference_unit_price_uzs`, `price_basis`, `price_as_of`. Multi-item lookup использует один read-only `REPEATABLE READ` snapshot.
- Lookup использует только expense текущего effective user с case-insensitive normalized item, exact unit, `quantity > 0` и известной UZS amount. Unknown price/timestamp = `null`, count = `0`; lookup не изменяет transaction, category plan, product item или cycle.
- Profile plugin `mariyam_stage53_guard` хранит structured lookup state ≤30 минут и для той же session требует непустой product payload с совпадающими item/unit/reference-price facts. Перед mutating downstream он атомарно сохраняет private canonical claim; identical call в том же turn downstream второй раз не вызывается (`DUPLICATE_SUCCESS_BLOCKED`), включая concurrent process и unknown outcome после exception. Identity plugin остаётся 1.0.4; `agent.max_turns=6` — второй profile-scoped предел.
- Default `include_items=false`, поэтому Stage 5.2 contract не меняется.
- Backend casefold-нормализует item name, считает точные числа, последнюю и средневзвешенную цену из transactions и сохраняет price snapshot плана; backend не пишет прозу. Цена рассчитывается только при наличии normalized item, amount, quantity и unit. При category plan `food` фактические расходы дочерних `food.*` сворачиваются в родительскую строку, если для конкретной дочерней категории нет более точного плана.
- Hermes объясняет данные, предлагает last price по умолчанию, спрашивает подтверждение и принимает `average` или `manual` override. Ценовая логика не хранится в LLM memory.

### Stage 5.3A — `approve_monthly_plan` (repo 22, deployed 21)

**Назначение.** Утвердить месячный план цикла 25/27/28/1. Tool не читает на запись и не изменяет `transactions`; изменение расходов запрещено. Backend хранит/валидирует; identity (Oyijon self-only, admin narrow cross-target allowlist, cron trusted job → users.id) обеспечивает identity guard до backend.

**Параметры (inputSchema):**

| Поле | Тип | Обяз. | Смысл |
|---|---|---|---|
| `user_id` | integer | да | субъект плана (guard rebinds) |
| `month` | string `YYYY-MM-01` | да | плановый месяц |
| `source` | enum `oyijon`\|`admin`\|`auto` | да | способ утверждения |
| `approved_by_user_id` | integer | нет | актор для `admin` (target != actor); для `oyijon` — только сам, для `auto` — запрещён |
| `household_size` | integer ≥1 | нет | размер семьи, пишется в cycle |

**Результат (ok):** `{month, status, source, household_size, approved_by_user_id, approved_at, idempotent, plan_copied}`. `source` в ответе — origin строки cycle (`calculated`\|`copied_previous`\|`manually_created`), не входной approval `source`.

**Детерминированная state machine (`monthly_plan_cycles.status`, unique `user/month`):**

- non-terminal: `draft`, `waiting_oyijon`, `waiting_admin`; terminal: `approved_by_oyijon`, `approved_by_admin`, `auto_approved`.
- Целевой статус по approval `source`: `oyijon → approved_by_oyijon`, `admin → approved_by_admin`, `auto → auto_approved`.
- Разрешён переход `non-terminal → target`. `current == target` → идемпотентный replay (`idempotent:true`, без второй записи, `approved_at` не переписывается), допускается даже после начала месяца (безопасность retry/cron). `current ∈ terminal и != target` → `INVALID_STATUS_TRANSITION`, без мутации.

**Границы месяца (Asia/Tashkent), проверка до записи:**

- `oyijon`/`admin` (ручное) — только строго ДО начала планового месяца; иначе `MONTH_ALREADY_STARTED`.
- `auto` (cron «1 число») — только в первый календарный день месяца; раньше → `MONTH_NOT_STARTED`, позже → `MONTH_ALREADY_STARTED`.

**Валидность draft.** valid draft = ≥1 строка `monthly_budget_plans` за месяц с суммарным `planned_amount_uzs > 0`. Пустой/нулевой → `EMPTY_DRAFT`, без мутации.

**auto (cron «1 число»):** valid draft → `auto_approved` (origin сохраняется); нет cycle-строки → copy последнего approved месяца (его `monthly_budget_plans`+`monthly_budget_items` копируются в плановый месяц, `plan_copied:true`, origin `copied_previous`); нет draft и нет прошлого approved → `NO_PLAN_SOURCE`. Уведомление админа при `NO_PLAN_SOURCE` — задача cron prompt, не backend.

**Ручное без draft:** `oyijon`/`admin` при отсутствии cycle-строки → `NO_DRAFT`.

**Изменение сумм.** Этот tool суммы плана не редактирует (это остаётся `set_monthly_budget`, Oyijon self-only, future month) и не расширяет update/delete transactions; единственная запись плановых сумм — copy последнего approved при `auto`. `household_size` пишется только для future month (ручные пути уже future по границе).

**Identity rails (backend-уровень, дублируют guard):** `oyijon` с `approved_by_user_id != user_id` → `SELF_ONLY_VIOLATION`; `admin` без target или target == user_id → `ADMIN_TARGET_REQUIRED`; `auto` с `approved_by_user_id` → `INVALID_APPROVER`. Проверка `allowed_target_user_ids` — на стороне identity guard.

### Stage 5.3A — `open_monthly_plan_cycle` (repo 23, deployed 21; вариант A 2026-07-24)

**Назначение.** Единственная узкая мутация статуса цикла (создаёт draft-строку и делает escalate), которой не было у `approve_monthly_plan`. `monthly_budget_items`/`transactions` не трогает; при генерации draft (см. `open`) пишет `monthly_budget_plans`. Identity (Oyijon self-only, admin narrow cross-target, cron trusted job) — на стороне identity guard.

**Параметры:** `user_id` (int, req), `month` (`YYYY-MM-01`, req), `action` (enum `open`|`escalate`, req), `household_size` (int ≥1, optional).

**Результат (ok):** `{month, status, source, household_size, idempotent, created, draft_generated}`.

- `action=open`: строки цикла нет — создаёт `waiting_oyijon` (`source=calculated`, `created:true`) для future month (Asia/Tashkent, строго до начала месяца). Уже есть valid budget-draft (≥1 строка `monthly_budget_plans`, `SUM>0`) → просто открывает цикл (`draft_generated:false`). Content нет → **backend детерминированно вычисляет и персистит draft** (решение 2026-07-25): последний approved plan ∪ категории расходов за 3 последних месяца по округлённому среднему; сумм не выдумывает; обязательные платежи (Stage 6) пока не включаются; пишет `monthly_budget_plans`, `draft_generated:true`. Строка цикла любого статуса уже есть → идемпотентно (`idempotent:true`, `created:false`), без мутации и дублей.
- `action=escalate`: `waiting_oyijon`/`draft` → `waiting_admin` (future month). Уже `waiting_admin` → идемпотентный no-op. Terminal-статус → `INVALID_STATUS_TRANSITION`. Нет строки → `NO_DRAFT`. Всё — без мутации при отказе.
- Коды ошибок: `MONTH_ALREADY_STARTED`, `NO_PLAN_SOURCE` (open: нет источника для draft), `EMPTY_DRAFT` (open: уже есть zero-sum plan, не перезаписывается), `INVALID_STATUS_TRANSITION`, `NO_DRAFT` (+ `INVALID_INPUT` на bad `action`/`household_size`).

### Stage 5.3A — `get_monthly_plan_cycle` (repo 24; read-only)

**Назначение.** Read-only статус цикла для cron-гейтинга (jobs 27/28/1b): узнать, одобрила ли Ойижон план. Мутаций нет.

**Параметры:** `user_id` (int, req), `month` (`YYYY-MM-01`, req).

**Результат (ok):** `{month, exists, status, source, household_size, proposed_at, approved_at, approved_by_user_id}`. Нет строки → `exists:false`, остальные поля `null` (не ошибка). `status` ∈ шести статусов цикла.

**Связка (вариант A end-to-end):** `open` → «ха»-approve Oyijon (`approved_by_oyijon`); `open` → `escalate` → admin approve (`approved_by_admin`); `open` → job 1 `auto` (`auto_approved`, approve существующего draft, без copy).

### Stage 5.4 — +3, planned 25

- `set_utility_threshold`, `sync_utility_account`, `get_utility_status`.
- Только structured read-only data. Payment/top-up/settings/tariff write запрещены. Stale data возвращается с last sync date.
- `set_utility_threshold`: Oyijon self-only; admin narrow cross-target только для target из `allowed_target_user_ids` и только threshold. Portal/payment/settings/transactions этим разрешением недоступны.

### Stage 6 — recurring obligations (+2 → repo/runtime 26)

`upsert_recurring_obligation` — единственная мутация. Required: `user_id`,
`action`. Действия:

- `upsert`: также обязательны `obligation_type`, `name`,
  `expected_amount_uzs`, `due_date`, `repeat_rule`; optional
  `obligation_id`, `repeat_interval_days`, `reminder_lead_days` (default 3).
  Без `obligation_id` natural key `(user_id, obligation_type, name)` делает
  retry идемпотентным; с id изменяются сумма/дата/rule существующей строки.
- `mark_paid`: обязательны `obligation_id` и `due_date` именно оплаченного
  occurrence. Повтор того же вызова идемпотентен. `none` закрывает строку
  (`paid=true`, `active=false`); recurring rule записывает
  `last_paid_due_date/at` и открывает следующий due occurrence. Expense или
  transaction никогда не создаётся.
- `disable`: обязателен `obligation_id`; повторный disable идемпотентен.

Approved repeat rules: `none`, `monthly`, `yearly`, `interval_days`.
`interval_days` требует positive `repeat_interval_days`. Monthly/yearly
сохраняют исходный calendar anchor: 31-е clamp-ится к концу короткого месяца,
но следующий подходящий месяц снова использует 31-е; 29 февраля аналогично
восстанавливается в leap year. Backend вычисляет только один следующий due.

`get_recurring_obligations` — read-only список, required `user_id`; optional
`active_only=true`, inclusive `due_from`/`due_to`. Оба tools user-scoped:
Oyijon self-only; admin cross-target только для target из
`allowed_target_user_ids` через отдельный narrow tool allowlist. Права на
transactions не выдаются.

### Stage 6 — daily-life external facts (+3 → repo 29)

- `get_tashkent_weather()` — OpenWeather current facts для Ташкента. API key
  читается только из `OPENWEATHER_API_KEY`; в output/URL ключ не возвращается.
- `get_tashkent_prayer_times()` — Aladhan timings для Ташкента с
  `school=1` (Hanafi), calculation method 3.
- `get_daily_news()` — заголовки только согласованных источников **UzA +
  Kun.uz**, с URL/датой/источником. Backend не пишет дайджест и не выбирает
  смысл; Hermes выбирает 3–5 спокойных пунктов и пересказывает кириллицей.

У всех трёх input schema пустая: они не принимают `user_id`, не читают
пользовательские таблицы и ничего не мутируют. Кэш — один JSON-файл
`MARIYAM_EXTERNAL_CACHE_FILE`, freshness = текущий календарный день
Asia/Tashkent. При отказе upstream возвращается предыдущая запись с
`cache.stale=true` и честной пометкой; если кэша нет —
`EXTERNAL_DATA_UNAVAILABLE`, без выдуманных значений.

Все user-scoped tools Stage 5.3A–6 проходят identity guard. Unknown/untrusted
Telegram или cron identity → fail closed до MCP. Три external-data tools не
имеют user scope и не дают доступа к данным пользователя.

## Обязательные поля (required) по tools

| Tool | required | Примечание |
|---|---|---|
| `ensure_user` | telegram_id, role, display_name | identity guard rebinds sender |
| `save_expense` | user_id, items | item: amount_uzs required; quantity/unit optional |
| `save_income` | user_id, amount | |
| `update_expense` | user_id, expense_id, fields | |
| `update_last_expense` | user_id, fields | |
| `delete_expense` | user_id, expense_id | |
| `delete_last_expense` | user_id | |
| `get_expense_report` | user_id | period default month; compare/trend optional |
| `get_balance_summary` | user_id | |
| `set_monthly_budget` | user_id, month, category_code, planned_amount_uzs | runtime active; live E2E PASS |
| `get_monthly_budget_status` | user_id, month | runtime active; live E2E PASS |
| `approve_monthly_plan` | user_id, month, source | repo 23; deploy отдельно; не трогает transactions |
| `open_monthly_plan_cycle` | user_id, month, action | repo 24; deploy отдельно; monthly_plan_cycles (+ сген. draft) |
| `get_monthly_plan_cycle` | user_id, month | repo 24; read-only статус цикла |
| `upsert_recurring_obligation` | user_id, action | action-specific fields валидируются до mutation; transactions не трогает |
| `get_recurring_obligations` | user_id | active/due read-only список |
| `get_tashkent_weather` | — | read-only OpenWeather, daily cache |
| `get_tashkent_prayer_times` | — | read-only Aladhan Hanafi, daily cache |
| `get_daily_news` | — | read-only UzA + Kun.uz candidates, daily cache |
| `save_quran_progress` | user_id | |
| `get_quran_progress` | user_id | |
| `save_health_note` | user_id, note | |
| `save_alert_event` | user_id, alert_type, severity, source_text | |
| `save_plan_note` | user_id, text | |
| `get_admin_report_data` | user_id | |
| `backup_data` | — | Stage 8: read-only статус последнего backup; запуск из LLM запрещён |
| `get_backup_status` | — | Stage 8: `last_ok`, `last_backup_at`, `archive`, `uploaded`, `sha256` |
| `get_bot_status` | — | |
| `log_usage_cost` | provider, service_type, units, estimated_cost_usd | |

## Коды ошибок (единый список, ТЗ §15)

- `BAD_CATEGORY`, `BAD_AMOUNT`, `INVALID_INPUT` (в т.ч. bad quantity/unit), `NOT_FOUND`, `NOT_CONFIGURED`, `UNKNOWN_TOOL`, `INTERNAL`.
- `approve_monthly_plan` (детерминированные отказы, без мутации): `MONTH_ALREADY_STARTED`, `MONTH_NOT_STARTED`, `NO_DRAFT`, `EMPTY_DRAFT`, `NO_PLAN_SOURCE`, `INVALID_STATUS_TRANSITION`, `SELF_ONLY_VIOLATION`, `ADMIN_TARGET_REQUIRED`, `INVALID_APPROVER`.
- `upsert_recurring_obligation`: `NOT_FOUND`, `OBLIGATION_INACTIVE`,
  `DUE_DATE_MISMATCH`; все отказы без мутации.
- Identity (middleware, до backend): `IDENTITY_*`.
