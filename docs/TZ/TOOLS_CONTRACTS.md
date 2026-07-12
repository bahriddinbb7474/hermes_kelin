# Tools Contracts

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md` (полные примеры вход/выход — §15).
Реализация: `backend/server.py` (схемы, dispatch) + `backend/db.py` (SQL) в `main` (merged через `dd9261e`). Все 19 tools реализованы и покрыты smoke-тестом через MCP-слой (маркер `MCP_SMOKE_PASSED`).

## Общие правила

Все tools — один MCP-сервер. Hermes вызывает tools сам; backend не решает смысл сообщения.

Конвенции:

- успех: `{ "ok": true, ... }`;
- ошибка: `{ "ok": false, "error_code": "...", "message_ru": "...", "message_uz": "..." }`;
- время: UTC ISO 8601, границы дней считаются по Asia/Tashkent;
- суммы: в сумах, тийины не используются;
- категории расходов только из фиксированного списка;
- каждый tool публикует **собственную** inputSchema с блоком `required` (общая схема на все tools запрещена, ТЗ §15);
- backend держит **один** пул соединений на процесс (создание пула на каждый вызов запрещено, ТЗ §16);
- нереализованная функция возвращает `NOT_CONFIGURED`, а не ложный успех (ТЗ §15).

## Детерминированная identity binding (v3.6)

- `user_id` — internal owner/target (из `users`), см. ТЗ §15.
- Для user-scoped tools effective `user_id` **проверяется и при необходимости переписывается identity guard** (`mariyam_identity_guard`, `tool_execution` middleware) на основе current Telegram session — до вызова backend. Аргументы модели/display name не являются источником identity.
- `role=oyijon` **не может** вызвать tool для другого пользователя (всегда self-only).
- `role=admin` cross-target ограничен строгими allowlists: tools ∈ {`get_expense_report`, `get_balance_summary`, `get_admin_report_data`, `save_plan_note`} И target ∈ `allowed_target_user_ids`; cross-target write/delete запрещены.
- Malformed/unknown identity блокируется **до backend** (fail-closed, коды `IDENTITY_*`).
- API backend tools **не меняется** (ТЗ §0.6, §19, §20).

## MVP tools

- `ensure_user` — идемпотентно создать/найти пользователя по telegram_id (seed при настройке; ТЗ §15.15).
- `save_expense` — сохранить один или несколько расходов, уже разобранных Hermes.
- `save_income` — сохранить доход, например пенсию.
- `update_expense` — исправить расход по id.
- `update_last_expense` — исправить последнюю расходную запись пользователя.
- `delete_expense` — удалить расход по id.
- `delete_last_expense` — удалить последний расход пользователя.
- `get_expense_report` — вернуть точные суммы за день/неделю/месяц/custom и разбивку по категориям.
- `get_balance_summary` — вернуть доход, расход и остаток за период.
- `save_quran_progress` — сохранить прогресс чтения Корана.
- `get_quran_progress` — вернуть последний прогресс Корана.
- `save_health_note` — сохранить заметку о самочувствии без диагноза.
- `save_alert_event` — записать событие urgent/safety alert.
- `save_plan_note` — сохранить текстовую заметку/план/счётчик, если нужно как факт.
- `get_admin_report_data` — вернуть факты для отчёта 19:30; прозу пишет Hermes.
- `backup_data` — запустить/зафиксировать backup.
- `get_backup_status` — вернуть состояние последнего backup.
- `get_bot_status` — heartbeat/status gateway/db/errors/time.
- `log_usage_cost` — записать оценку расходов STT/TTS/LLM.

## Обязательные поля (required) по tools

| Tool | required | Примечание |
|---|---|---|
| `ensure_user` | telegram_id, role, display_name | role: `oyijon`/`admin`; повторный вызов → тот же user_id, `created:false`. **При runtime setup через identity guard (v3.6): `telegram_id`, `role` и `display_name` привязываются к sender mapping из middleware — LLM не может произвольно создать другого пользователя через подмену аргументов.** |
| `save_expense` | user_id, items | items: `[{item_name, amount_uzs, category_code}]`; required внутри item: amount_uzs |
| `save_income` | user_id, amount | currency по умолчанию UZS |
| `update_expense` | user_id, expense_id, fields | fields: amount_uzs / category_code / item_name; пустые → INVALID_INPUT |
| `update_last_expense` | user_id, fields | правит последнюю расходную запись |
| `delete_expense` | user_id, expense_id | |
| `delete_last_expense` | user_id | |
| `get_expense_report` | user_id | period: today/week/month/custom (по умолчанию month); custom требует from и/или to |
| `get_balance_summary` | user_id | |
| `save_quran_progress` | user_id | surah/juz/page/note опциональны |
| `get_quran_progress` | user_id | нет записей → NOT_FOUND |
| `save_health_note` | user_id, note | severity: info/low/medium/high/critical |
| `save_alert_event` | user_id, alert_type, severity, source_text | severity: low/medium/high/critical; detected_by: llm/keyword/both |
| `save_plan_note` | user_id, text | |
| `get_admin_report_data` | user_id | date опционален → сегодня по Ташкенту |
| `backup_data` | — | до Этапа 8 → NOT_CONFIGURED |
| `get_backup_status` | — | до Этапа 8 → NOT_CONFIGURED |
| `get_bot_status` | — | heartbeat |
| `log_usage_cost` | provider, service_type, units, estimated_cost_usd | service_type: stt/tts/llm |

## Коды ошибок (единый список, ТЗ §15)

- `BAD_CATEGORY` — категория не из утверждённого списка.
- `BAD_AMOUNT` — сумма отрицательная / не число.
- `INVALID_INPUT` — нет обязательных полей, неверный формат даты/валюты/severity, пустые `fields` в update. Enum-поля (`currency`, `severity`, `source_type`, `detected_by`, `service_type`) валидируются в коде до INSERT, не CHECK-ошибкой БД.
- `NOT_FOUND` — запись для update/delete/get не найдена.
- `NOT_CONFIGURED` — функция ещё не настроена (backup до Этапа 8).
- `UNKNOWN_TOOL` — неизвестное имя tool.
- `INTERNAL` — прочая внутренняя ошибка.

В сомнительных голосовых случаях Hermes обязан переспросить до сохранения; backend не должен молча сохранять неверные суммы.
