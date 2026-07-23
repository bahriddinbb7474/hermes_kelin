# Tools Contracts

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md` (полные примеры вход/выход — §15).
Реализация: `backend/server.py` + `backend/db.py`. **Repo inventory: 23 tools (dispatch/MCP discovery = 23/23); deployed на VPS: 21.** Stage 5.3A добавляет `approve_monthly_plan` и `open_monthly_plan_cycle` (репозиторий); backend/БД deploy — отдельным шагом (imp02). Migration 003 (со схемой `monthly_plan_cycles`) уже active на VPS; guard deploy active/PASS; [Telegram live acceptance evidence](../EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md).

**v3.19 progression:** Stage 5.3 = 21, Stage 5.3A repo = 23 (deployed 21), Stage 5.4 = planned +3, Stage 6 = planned +2. Всё сверх repo 23 — **PLANNED / NOT IMPLEMENTED** и отсутствует в runtime discovery.

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

## Базовые 19 tools (в составе текущего inventory 21)

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

**Назначение.** Единственная узкая мутация статуса цикла (создаёт draft-строку и делает escalate), которой не было у `approve_monthly_plan`. Пишет **только** строку `monthly_plan_cycles`; `monthly_budget_plans`/`monthly_budget_items`/`transactions` не трогает. Identity (Oyijon self-only, admin narrow cross-target, cron trusted job) — на стороне identity guard.

**Параметры:** `user_id` (int, req), `month` (`YYYY-MM-01`, req), `action` (enum `open`|`escalate`, req), `household_size` (int ≥1, optional).

**Результат (ok):** `{month, status, source, household_size, idempotent, created}`.

- `action=open`: если строки цикла нет — создаёт `waiting_oyijon` (`source=calculated`, `created:true`) для future month (Asia/Tashkent, строго до начала месяца), требует valid budget draft (та же валидация, что `EMPTY_DRAFT` в approve: ≥1 строка `monthly_budget_plans` за месяц, `SUM>0`). Строка любого статуса уже есть → идемпотентный ответ (`idempotent:true`, `created:false`), без мутации и без дублей.
- `action=escalate`: `waiting_oyijon`/`draft` → `waiting_admin` (future month). Уже `waiting_admin` → идемпотентный no-op. Terminal-статус → `INVALID_STATUS_TRANSITION`. Нет строки → `NO_DRAFT`. Всё — без мутации при отказе.
- Коды ошибок: `MONTH_ALREADY_STARTED`, `EMPTY_DRAFT`, `INVALID_STATUS_TRANSITION`, `NO_DRAFT` (+ `INVALID_INPUT` на bad `action`/`household_size`).

**Связка (вариант A end-to-end):** `open` → «ха»-approve Oyijon (`approved_by_oyijon`); `open` → `escalate` → admin approve (`approved_by_admin`); `open` → job 1 `auto` (`auto_approved`, approve существующего draft, без copy).

### Stage 5.4 — +3, planned 25

- `set_utility_threshold`, `sync_utility_account`, `get_utility_status`.
- Только structured read-only data. Payment/top-up/settings/tariff write запрещены. Stale data возвращается с last sync date.
- `set_utility_threshold`: Oyijon self-only; admin narrow cross-target только для target из `allowed_target_user_ids` и только threshold. Portal/payment/settings/transactions этим разрешением недоступны.

### Stage 6 — +2, planned 27

- `upsert_recurring_obligation`, `get_recurring_obligations`.
- Upsert также меняет amount/date, отмечает paid и disables; paid не создаёт expense автоматически.
- Оба tools: Oyijon self-only; admin narrow cross-target только для target из `allowed_target_user_ids` через отдельный per-tool allowlist; права на transactions не выдаются.

Все будущие tools Stage 5.3A–6 user-scoped. Unknown/untrusted Telegram или cron identity → fail closed до MCP.

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
| `open_monthly_plan_cycle` | user_id, month, action | repo 23; deploy отдельно; только строка monthly_plan_cycles |
| `save_quran_progress` | user_id | |
| `get_quran_progress` | user_id | |
| `save_health_note` | user_id, note | |
| `save_alert_event` | user_id, alert_type, severity, source_text | |
| `save_plan_note` | user_id, text | |
| `get_admin_report_data` | user_id | |
| `backup_data` | — | until Stage 8 → NOT_CONFIGURED |
| `get_backup_status` | — | until Stage 8 → NOT_CONFIGURED |
| `get_bot_status` | — | |
| `log_usage_cost` | provider, service_type, units, estimated_cost_usd | |

## Коды ошибок (единый список, ТЗ §15)

- `BAD_CATEGORY`, `BAD_AMOUNT`, `INVALID_INPUT` (в т.ч. bad quantity/unit), `NOT_FOUND`, `NOT_CONFIGURED`, `UNKNOWN_TOOL`, `INTERNAL`.
- `approve_monthly_plan` (детерминированные отказы, без мутации): `MONTH_ALREADY_STARTED`, `MONTH_NOT_STARTED`, `NO_DRAFT`, `EMPTY_DRAFT`, `NO_PLAN_SOURCE`, `INVALID_STATUS_TRANSITION`, `SELF_ONLY_VIOLATION`, `ADMIN_TARGET_REQUIRED`, `INVALID_APPROVER`.
- Identity (middleware, до backend): `IDENTITY_*`.
