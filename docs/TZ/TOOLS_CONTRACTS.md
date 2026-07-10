# Tools Contracts

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Общие правила

Все tools — один MCP-сервер. Hermes вызывает tools сам; backend не решает смысл сообщения.

Конвенции:

- успех: `{ "ok": true, ... }`;
- ошибка: `{ "ok": false, "error_code": "...", "message_ru": "...", "message_uz": "..." }`;
- время: UTC ISO 8601, границы дней считаются по Asia/Tashkent;
- суммы: в сумах, тийины не используются;
- категории расходов только из фиксированного списка.

## MVP tools

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

## Важные ошибки

- `BAD_CATEGORY` — категория не из утверждённого списка.
- `NOT_FOUND` — запись для update/delete не найдена.
- В сомнительных голосовых случаях Hermes обязан переспросить до сохранения; backend не должен молча сохранять неверные суммы.
