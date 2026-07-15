# Tools Contracts

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md` (полные примеры вход/выход — §15).
Реализация: `backend/server.py` + `backend/db.py`. **Repo/VPS runtime: 21 tools; dispatch/MCP discovery = 21/21; Stage 5.1 CLOSED / LIVE PASS.** Новые tools: `set_monthly_budget`, `get_monthly_budget_status`.

**v3.12 planned progression:** Stage 5.3 = 21, Stage 5.3A = 22, Stage 5.4 = 25, Stage 6 = 27. Всё сверх текущих 21 — **PLANNED / NOT IMPLEMENTED** и отсутствует в runtime discovery.

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

## Planned contract extensions v3.12

### Stage 5.3 — без новых tools, runtime count остаётся 21

- `set_monthly_budget`: optional `items[]`; каждый planned item может содержать `item_name_normalized`, `item_name_display`, `planned_quantity`, `unit`, `planned_amount_uzs`, `reference_unit_price_uzs`, `price_basis`, `price_as_of`, `note`. Минимум одно из `planned_quantity` или `planned_amount_uzs` обязательно.
- `get_monthly_budget_status(include_items=true)` возвращает по item: `planned_quantity`, `planned_unit`, `planned_amount_uzs`, `actual_quantity`, `actual_unit`, `actual_amount_uzs`, `remaining_amount_uzs`, `last_unit_price_uzs`, `average_unit_price_uzs`, `reference_unit_price_uzs`, `price_basis`, `price_as_of`. Unknown = `null`, не `0`; разные units не смешиваются.
- Backend считает точные числа, последнюю и средневзвешенную цену из transactions и сохраняет price snapshot плана; backend не пишет прозу. Цена рассчитывается только при наличии normalized item, amount, quantity и unit.
- Hermes объясняет данные, предлагает last price по умолчанию, спрашивает подтверждение и принимает `average` или `manual` override. Ценовая логика не хранится в LLM memory.

### Stage 5.3A — +1, planned 22

- `approve_monthly_plan`: approve plan + approval method/actor; не изменяет transactions и не удаляет expenses.
- Tool действует только до начала планового месяца. Oyijon self-only. Admin cross-target только allowed target, future month и узкий allowlist именно этого tool; transaction permissions не расширяются. После начала месяца approval-cycle закрыт; активный plan корректирует только Oyijon self-only, admin edit текущего plan в v3.10 не заявлен.

### Stage 5.4 — +3, planned 25

- `set_utility_threshold`, `sync_utility_account`, `get_utility_status`.
- Только structured read-only data. Payment/top-up/settings/tariff write запрещены. Stale data возвращается с last sync date.
- `set_utility_threshold`: Oyijon self-only; admin narrow cross-target только для target из `allowed_target_user_ids` и только threshold. Portal/payment/settings/transactions этим разрешением недоступны.

### Stage 6 — +2, planned 27

- `upsert_recurring_obligation`, `get_recurring_obligations`.
- Upsert также меняет amount/date, отмечает paid и disables; paid не создаёт expense автоматически.
- Оба tools: Oyijon self-only; admin narrow cross-target только для target из `allowed_target_user_ids` через отдельный per-tool allowlist; права на transactions не выдаются.

Все planned tools user-scoped. Unknown/untrusted Telegram или cron identity → fail closed до MCP.

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
- Identity (middleware, до backend): `IDENTITY_*`.
