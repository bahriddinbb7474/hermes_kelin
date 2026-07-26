# Evidence — Stage 6 recurring obligations, шаг 1 (2026-07-26)

VPS: `time-agent-prod`, service user `timeagent`. Telegram IDs, tokens,
database credentials and private mapping contents are not recorded here.

## Scope and source

- Deployed immutable source commit:
  `81810334d0541a7af4b3e58755ab8210c3a16550`.
- Migration: `backend/sql/005_stage6_recurring_obligations.sql`.
- Backend: `upsert_recurring_obligation`,
  `get_recurring_obligations`.
- Identity plugin: `mariyam_identity_guard` **1.3.0**.
- Hermes core, SOUL, cron jobs, scheduler and `transactions` code/schema were
  not changed.

## Pre-deploy rollback snapshot

Before migration or file replacement, a private on-VPS snapshot was created:

`/opt/hermes-mariyam/var/deploy-backups/imp05-20260726T183000Z`

It contains a PostgreSQL custom-format dump plus the exact previous
`backend/db.py`, `backend/server.py` and identity-plugin files. Directory mode
is `0700`; database dump SHA-256 prefix is `556b4369…`. Nothing was copied to
an unapproved external destination.

## Schema and contract

Migration 005 created `recurring_obligations` with:

- user scope and type `internet|loan|tax|utility|other`;
- name, expected UZS amount, due date and reminder lead;
- approved repeat rules `none|monthly|yearly|interval_days`;
- calendar anchor fields for deterministic 29–31/leap/year-end handling;
- active/paid state, last-paid occurrence and timestamps;
- unique natural key `(user_id, obligation_type, name)` and user/due index.

`mark_paid` requires the paid occurrence due date. A replay of the same
occurrence is idempotent. A recurring rule advances exactly once; a `none`
rule becomes paid/inactive. No FK, trigger or code path creates or updates a
transaction/expense.

## Tests before production

Local/offline:

- `compileall`: PASS;
- `git diff --check`: PASS;
- full offline suite: **263 passed, 86 skipped** (skips require PostgreSQL);
- focused Stage 6 + Telegram/cron/Stage 5.3 guard suite:
  **142 passed, 6 skipped**.

Disposable VPS database `hermes_imp05_test`:

- migrations 001/002/003/005: PASS;
- Stage 6 integration: **15 passed**;
- database-backed Stage 5.1–6 regression: **137 passed**;
- permanent markers:
  `ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`,
  `POOL_STABLE_PASSED`, `MCP_SMOKE_PASSED`.

Telegram/cron identity and Stage 5.3 guard regressions on the actual POSIX
runtime: **133 passed** under the required `umask 077`. An initial harness run
without the private-file umask correctly failed closed with
`IDENTITY_MAPPING_PERMISSIONS`; no code or tests were changed, and the
contract-correct rerun passed.

The disposable database, temporary clone and test dependencies were removed
after verification.

## Controlled production deploy

Sequence:

1. Apply migration 005 with `psql -v ON_ERROR_STOP=1`.
2. Install `backend/db.py`, `backend/server.py` and migration 005 from commit
   `8181033`.
3. Install backup/restore manifest updates for the new table.
4. Install identity guard 1.3.0 in the Mariyam profile.
5. Compile deployed Python.
6. Restart only `hermes-gateway-mariyam_oyijon.service`.

Result: `CREATE TABLE`, `CREATE INDEX`, gateway `active`.

Installed `db.py`, `server.py` and identity-plugin hashes match the pulled
commit byte-for-byte. `/opt/hermes-mariyam/.deployed-origin-main` is
`8181033`.

## Production verification

- Backend source inventory: **26**.
- Dispatch entries: **26**.
- Live MCP `list_tools`: **26**, duplicates `[]`.
- Required new names are present in discovery.
- Identity guard version: **1.3.0**; both new tools are in the tested
  user-scoped and narrow admin cross-target policy, while transaction writes
  remain excluded.
- `get_bot_status`: `ok=true`, gateway `up`, DB `up`, `last_error=null`.
- PostgreSQL `pg_isready`: accepting connections.
- `recurring_obligations` schema is present in production.
- Gateway user-service: `active`.
- `hermes_mariyam_postgres`: healthy.
- Unrelated `time_agent_bot`: remained up and was not restarted.

Read-only live Stage 6 MCP smoke for the mapped test user:

`STAGE6_READ_SMOKE True True 0`

Telegram smoke: the production Mariyam bot sent one short Uzbek-Cyrillic
message to the existing allowlisted test account. Bot API result:

`TELEGRAM_SMOKE_OK True private`

Customer-provided Telegram screenshot visually confirms receipt at 18:31 of
the exact smoke text:
`Текширув: Мариям янгиланди, маълумотлар хизмати ишлаяпти.` The screenshot is
not committed, avoiding an unnecessary binary artifact and image metadata.

No real Oyijon account was connected or messaged.

## Rollback

Preferred application rollback:

1. Stop only `hermes-gateway-mariyam_oyijon.service`.
2. Restore backend and identity-plugin files from the private imp05 snapshot.
3. Compile restored files and start the Mariyam gateway.
4. Verify discovery returns the prior 24 tools and guard 1.2.0.

Migration 005 is additive; the safest application rollback leaves the unused
table in place. If a schema rollback is explicitly required, use the
pre-deploy custom dump in a maintenance window and verify row counts before
switching the gateway back. Do not drop production data as part of an ordinary
application rollback.
