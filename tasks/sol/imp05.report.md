# imp05 — отчёт

## Результат

Stage 6, шаг 1 завершён и развёрнут на VPS:

- migration 005 `recurring_obligations`;
- tools `upsert_recurring_obligation` и `get_recurring_obligations`;
- inventory/dispatch/discovery **26/26/26**;
- identity guard **1.3.0**;
- production health, read-only tool smoke и Telegram smoke на тест-аккаунт —
  PASS.

Evidence:
`docs/EVIDENCE_STAGE_6_OBLIGATIONS_2026-07-26.md`.

## Schema

`recurring_obligations` хранит user scope, тип
`internet|loan|tax|utility|other`, название, ожидаемую сумму UZS, due date,
approved repeat rule, reminder lead, active/paid state, last paid occurrence
и timestamps.

Repeat rules: `none`, `monthly`, `yearly`, `interval_days`. Calendar anchors
обеспечивают детерминированный переход 29–31 чисел, leap day и конец года.
Повторный `mark_paid` того же due occurrence не продвигает дату второй раз.

## Contracts

- `upsert_recurring_obligation(user_id, action, ...)`:
  `upsert|mark_paid|disable`; create/update по id или natural key; paid не
  создаёт expense/transaction.
- `get_recurring_obligations(user_id, active_only?, due_from?, due_to?)`:
  read-only active/due список.
- Oyijon self-only; admin cross-target только для id из
  `allowed_target_user_ids` через narrow tool allowlist.
- Deterministic no-mutation errors:
  `NOT_FOUND`, `OBLIGATION_INACTIVE`, `DUE_DATE_MISMATCH`,
  `INVALID_INPUT`, `BAD_AMOUNT`.

## Изменённые файлы

- `backend/sql/005_stage6_recurring_obligations.sql`
- `backend/db.py`
- `backend/server.py`
- `deploy/hermes_plugins/mariyam_identity_guard/__init__.py`
- `deploy/hermes_plugins/mariyam_identity_guard/plugin.yaml`
- `deploy/backup/mariyam-backup.sh`
- `deploy/backup/mariyam-restore-check.sh`
- `tests/test_stage6_recurring_obligations.py`
- count/version/regression assertions in existing tests
- `docs/TZ/TOOLS_CONTRACTS.md`
- `docs/TZ/DATABASE.md`
- `README.md`
- `docs/ROADMAP.md`
- `docs/EVIDENCE_STAGE_6_OBLIGATIONS_2026-07-26.md`

## Проверки

- local full offline: `263 passed, 86 skipped`;
- focused guard/Stage 6: `142 passed, 6 skipped`;
- disposable PostgreSQL Stage 6: `15 passed`;
- DB-backed Stage 5.1–6 regression: `137 passed`;
- POSIX Telegram/cron/Stage 5.3 guards: `133 passed`;
- permanent markers: 4/4 PASS;
- production: 26/26/26, no duplicates, DB/gateway healthy;
- live read-only Stage 6 tool: PASS;
- Telegram private-chat smoke на allowlisted test account: PASS.

## Deploy

- private rollback snapshot:
  `/opt/hermes-mariyam/var/deploy-backups/imp05-20260726T183000Z`;
- migration 005: `CREATE TABLE`, `CREATE INDEX`;
- backend and guard installed byte-for-byte from commit;
- restarted only Mariyam gateway;
- unrelated Time-Agent remained up;
- disposable DB and temporary files removed.

## Commits

- implementation/deployed:
  `81810334d0541a7af4b3e58755ab8210c3a16550`
  (`feat: Stage 6 recurring obligations (migration 005, tools 26, guard 1.3.0)`).

## Не сделано

Не реализовывались по запрету задачи: Hermes reminder cron для obligations,
утро/вечер, новости, погода, намаз, backend scheduler, utility migration 004,
utility connector и любые изменения transactions.
