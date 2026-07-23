# imp01 — отчёт

## Результат

Исследован фактический Hermes v0.18.2 на VPS и создан design:
`docs/TZ/CRON_IDENTITY_GATE_5_3A.md`.

Текущий runtime безопасен: cron создаёт отдельную session с `source=cron`, без
Telegram origin, загружает 21 MCP tool и проходит через profile middleware.
`mariyam_identity_guard` 1.0.4 принимает только persisted Telegram origin,
поэтому любой user-scoped cron call сейчас блокируется
`IDENTITY_UNRESOLVED` до backend.

## Live evidence

- Hermes `v0.18.2`, local commit `3b2ef789`.
- Cron storage profile-scoped:
  `~/.hermes/profiles/mariyam_oyijon/cron/jobs.json`.
- Каждый запуск получает новый
  `cron_<job_id>_<timestamp>` session и новый `AIAgent(platform="cron")`.
- MCP discovery выполняется внутри cron; profile `max_turns=6` наследуется.
- Controlled job `3831b7e88a89` один раз попытался вызвать read-only
  `get_balance_summary` с поддельным `user_id`.
- Лог: 21 MCP tools; guard `IDENTITY_UNRESOLVED`; tool middleware завершился за
  0.00s; turn `api_calls=2/6`; saved response `IDENTITY_UNRESOLVED`.
- По коду guard вернул safe error до `next_call`, поэтому downstream MCP calls =
  0.

## Cleanup

Тестовый job, его output, созданный пустой `jobs.json`, exact cron session и 4
messages удалены. Финально scheduled jobs отсутствуют, matching
sessions/messages = 0. Production PostgreSQL, config, SOUL, plugins и
`/opt/time-agent` не менялись.

## Предложенный gate

Узко расширить существующий `mariyam_identity_guard`:

`server-created cron session → persisted source=cron → exact job id → immutable
job/prompt fingerprint → private mapping 0600 → internal users.id + tool
allowlist`.

Mapping создаёт только deploy operator в
`/opt/hermes-mariyam-secrets/cron-identity-map.json`; LLM-supplied `user_id`
игнорируется. Unknown job, modified prompt, tool вне allowlist, битый mapping
или неверные права блокируются до backend.

Текущий duplicate breaker защищает только один `session_id + turn_id`; между
разными cron firings session меняется. Поэтому planned `approve_monthly_plan`
должен отдельно иметь business idempotency через `monthly_plan_cycles`.

Код Stage 5.3A, Hermes core и backend не изменялись.
