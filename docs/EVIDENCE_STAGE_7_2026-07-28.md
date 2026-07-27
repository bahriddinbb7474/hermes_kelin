# Stage 7 admin report + health alerts — evidence, 2026-07-28

Status: **CLOSED / LIVE PASS on the approved test identities**. Real Oyijon
and other real recipient identities were not connected.

## Scope and deployed state

- Feature commit:
  `bbb66e4e8d3b4a45d009b1e132524e324cd53b5a`
  (`feat: Stage 7 admin report and health alerts`), pushed to `origin/main`.
- VPS marker: `bbb66e4`.
- Controlled rollback backup:
  `/opt/hermes-mariyam/var/deploy-backups/imp07-20260727T182600Z`.
  The directory is mode 0700, files are mode 0600; the production DB dump
  SHA-256 prefix is `ae31c9292266…`.
- Backend inventory / dispatch / real MCP discovery: **29 / 29 / 29**,
  no duplicate names.
- MCP health: `gateway=up`, `db=up`.
- Gateway: active, one MainPID, `NRestarts=0` after the controlled restart.
- PostgreSQL: healthy. Time-Agent container: running and not restarted.
- Plugins loaded through the real Hermes plugin manager:
  identity guard **1.3.0**, health guard **1.0.0**, Stage 5.3 guard **1.0.0**.
  Health registrations: `pre_gateway_dispatch` hook and `tool_execution`
  middleware.
- Canonical SOUL SHA-256:
  `765572a3f7a0174e1a203b8787b8a65a09a2049438adec18b31831b05a012c01`.
- Trusted cron inventory / private mapping: **9 / 9**, mapping mode 0600.
  New job schedule is `30 19 * * *`; masked job id `5c46…`; its immutable
  fingerprint, prompt SHA and allowlist
  (`get_admin_report_data` only) all validated.

## Offline gates

- Full repository suite: **277 passed, 87 skipped**.
- Focused Stage 7 suite after the final contracts: **9 passed, 1 skipped**.
- Prompt assembler suite: **6 passed**.
- Compile checks: PASS for repo and installed backend/plugin/writer files.
- Dataset: **35 positive** phrases (all seven §10.2 trigger families with
  four variants each) and **20 curated negative** phrases.
- Deterministic detector:
  - positives detected: **35/35**;
  - misses: **0**;
  - curated false positives: **0/20**;
  - recall: **100%**;
  - precision on this curated set: **100%**.
- Disposable PostgreSQL:
  `day=192000`, `month=200000`, `plan_remaining=300000`, `due=1`,
  `private_fields=0`; database dropped after the test.

## Admin report live verification

The deployed `get_admin_report_data` was compared with independent production
SQL immediately before the manual run:

```text
REPORT_SQL=PASS day_expense=0 day_income=0
month_expense=12000 month_income=0 planned=0 due=0 alerts=0
private_fields=0
```

The exact persistent trusted job was then run once manually. It completed after
the configured provider/fallback path with:

```text
last_status=ok
last_error=null
last_delivery_error=null
repeat.completed=1
delivery=telegram:test-admin
```

The report exposes day/month expense and income totals, category aggregates,
plan status/totals, due obligations and allowlisted alert metadata. It does not
expose `source_text`, bot responses, raw health notes, diagnoses, Telegram IDs
or other intimate fields.

SOUL contains the same `get_admin_report_data`-only contract for incoming admin
requests “отчёт за сегодня/месяц”. A second inbound UI request from test-admin
was not sent because the available Telegram Web session was the test-Oyijon
identity. The actual test-admin delivery endpoint and exact report tool path
were exercised by the manual trusted job above.

## Telegram health-alert live verification

After the user's explicit authorization, three representative dataset phrases
were sent from the mapped test-Oyijon Telegram account (heart pain, breathing
difficulty and high blood pressure trigger families).

Results:

- deterministic pre-dispatch detection: **3/3**;
- soft Uzbek Cyrillic replies to Oyijon: **3/3**;
- separate Telegram adapter delivery to the mapped test-admin: **3/3**;
- `alert_events` rows: **3**, unique **3/3**;
- every row: `alert_type=medical`, `severity=critical`,
  `detected_by=keyword`, `sent_to_admin=true`;
- guard state: `notified=1`, `recorded=1` for all **3/3**;
- duplicate rows or duplicate replies: **0**.

The user-facing reply was calm: it suggested telling close relatives and
seeking medical help, and stated that the son would be informed. It did not
diagnose, prescribe treatment or promise that the symptoms were harmless.

Cleanup removed exactly the three test `alert_events` rows and the three
corresponding private guard dedupe rows. The post-cleanup report/SQL comparison
again returned `alerts=0`; gateway remained active, PostgreSQL healthy and
Time-Agent running.

## Deploy notes and rollback

The first install attempt stopped before activation because canonical SOUL was
read-only; the helper was changed to atomic replacement. Hermes stores cron
schedule as `{kind: cron, expr: ...}` rather than a string; the deploy helper
was made idempotent and resumed the already-created single job without a
duplicate. No gateway restart happened until files, job and mapping were
consistent.

Rollback: restore backend/profile/config/env/plugins/jobs/mapping and the DB
dump from the backup directory above, remove only the Stage 7 private guard
state/writer if created by this deploy, and restart only
`hermes-gateway-mariyam_oyijon.service`.
