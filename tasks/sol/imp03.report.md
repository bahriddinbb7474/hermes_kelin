# imp03 — отчёт

## Результат

`mariyam_identity_guard` 1.1.0 развёрнут в production-профиле
`mariyam_oyijon`. Controlled cron probes и Telegram regression завершены PASS,
все временные jobs/outputs/sessions/mapping entries удалены.

Подробные masked логи:
`docs/EVIDENCE_STAGE_5_3A_CRON_GUARD_DEPLOY_2026-07-24.md`.

## Что изменено

- Сделан private backup plugin 1.0.4 и profile `.env`.
- Создан private cron mapping: parent `0700`, file `0600`.
- В private `.env` добавлен `MARIYAM_CRON_IDENTITY_MAP_FILE`.
- Установлен identity plugin 1.1.0, перезапущен только Mariyam Gateway.
- Исправлен найденный live edge case: пустой operator mapping
  `{"version":1,"jobs":{}}` теперь валиден.
- Добавлен regression test пустого mapping.
- README/ROADMAP обновлены до deployed plugin 1.1.0.

Hermes core, backend, DB schema/data, `mariyam_stage53_guard`, SOUL и
`/opt/time-agent` не менялись. Production jobs 25/27/28/1 не создавались.

## Проверки

- Targeted local suites: `89 passed`.
- Unknown job: `CRON_IDENTITY_UNRESOLVED`, downstream 0.
- Mapped test-user с forged model `user_id`: `oyijon_self`, backend read-only
  call выполнен с mapping identity.
- Mutated fingerprint: `CRON_JOB_UNTRUSTED`, downstream 0.
- Tool вне allowlist: `CRON_TOOL_FORBIDDEN`, downstream 0.
- Telegram read-only regression: PASS после одного retry из-за transient
  provider failure первого turn.
- Gateway active, PostgreSQL healthy, admin fingerprint unchanged.
- Новых/изменённых domain rows с начала deploy: 0.
- Inventory/dispatch/discovery: `21/21/21`.
- Cleanup: jobs/outputs/sessions/messages/mapping entries = `0/0/0/0/0`.

## Backup и rollback

Backup:

`/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/imp03-20260723T184146Z`

Одна rollback-процедура возврата на 1.0.4 приведена в evidence. Она не
выполнялась.
