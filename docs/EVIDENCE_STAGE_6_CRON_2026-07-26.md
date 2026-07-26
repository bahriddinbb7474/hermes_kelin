# Stage 6 cron — live evidence, 2026-07-26

Status: **PARTIAL / LIVE DEPLOYED**.

## Scope and deployed state

- Agreed inputs: UzA + Kun.uz; morning 08:30, obligations 09:15, evening
  19:30, timezone Asia/Tashkent.
- Feature commit: `1d3841345ddde3d611a215cea7577afeb9f1bd77`.
- Kun.uz endpoint fix: `09bb6c09d5b1cab889e3bc9f59c672b778ab9bd9`.
- VPS deployed source marker: `09bb6c09d5b…`.
- Backend inventory/dispatch/discovery: **29/29/29**. The Stage 6 obligations
  baseline at 26 tools remains present; the three external read-only tools
  make the current inventory 29.
- Identity guard: **1.3.0**. Hermes core and backend scheduler were not
  changed.
- Canonical SOUL SHA-256:
  `07f658f19990c69e7b948a94f906627137ee835e0d95db6e8fedc1396058489f`.
- Migration 005 remains active. Gateway restart affected only
  `hermes-gateway-mariyam_oyijon.service`.
- Private rollback backup:
  `/opt/hermes-mariyam/var/deploy-backups/imp06-20260726T141432Z`.
  It contains the pre-deploy backend/profile state, private cron state and DB
  dump. DB dump SHA-256 prefix: `6e6c7c65d08a…`.

## Automated and live checks

- Local full suite: **271 passed, 86 skipped**.
- Production MCP discovery: **29**, no duplicate names.
- MCP health: `gateway=up`, `db=up`.
- Services: gateway active; PostgreSQL container healthy; Time Agent
  container running.
- Aladhan/Hanafi: PASS, fresh cache, all five prayer times present.
- News: PASS, fresh cache, 12 candidates, UzA + Kun.uz, no source errors.
- Cache: PASS, mode 0600, two daily entries.
- OpenWeather: honest `EXTERNAL_DATA_UNAVAILABLE`; no key exists in either
  private production environment. No weather value was invented and no secret
  was added to git.
- Deployed backend/SOUL hashes: PASS.
- Private cron mapping: mode 0600, **8 entries / 8 jobs**.

## Production cron jobs

| Job | Schedule | Masked ID | Mapping / allowlist |
|---|---:|---:|---|
| Morning digest | `30 8 * * *` | `e5a1…` | trusted / `get_recurring_obligations` |
| Obligation reminders | `15 9 * * *` | `668f…` | trusted / `get_recurring_obligations` |
| Evening digest | `30 19 * * *` | `a87f…` | trusted / `get_admin_report_data` |

The first scheduled evening tick started at 19:30 and completed at 19:32. It
failed closed on the user-scoped call because the newly created job prompt had
a trailing newline while the persisted cron session was `rstrip()`-normalized.
The three new job prompts were normalized in place, their private fingerprints
were recomputed, and a second private rollback snapshot was retained. Final
read-only trust probe: fingerprint PASS, prompt hash PASS, prompt binding PASS,
`resolve_cron_actor` PASS.

A manual production Telegram replay was not performed: the safety gate rejected
sending an unreviewed admin/obligation payload to a recipient. Local-only model
replays were also rejected because they would disclose the mapped user's data
to the external model provider. No workaround was attempted.

## Telegram one-shot smoke

- From the agreed test account, the phrase
  `Эртага соат 10 да дорини эслат.` received a Cyrillic confirmation and
  created exactly one `once` job for 10:00 the next day.
- The job was untrusted: mapping=false, repeat=1, no script, no user-scoped or
  terminal/tool instructions.
- A safe due-now smoke,
  `Бугун соат 19:42 да «IMP06 синови» деб эслат.`, was confirmed and created
  as an equivalent untrusted one-shot.
- The scheduler invoked it on time and removed it after the single attempt, but
  the model provider returned HTTP 524 after its 120-second timeout. Therefore
  no Telegram reminder arrived; timely delivery is **FAIL**.
- Both test one-shot jobs, exact cron sessions and outputs were removed.
  Production returned to 8 jobs / 8 mapping entries. No test obligation was
  created.

## Residual work before CLOSED

1. Add `OPENWEATHER_API_KEY` to private VPS secrets and rerun the weather and
   morning-digest checks.
2. Obtain explicit approval for a payload-reviewed manual digest/reminder run,
   or use a synthetic user with no real obligation/report data.
3. Observe a post-fix normal scheduled digest tick with an allowed tool call.
4. Repeat the safe due-now one-shot when the model provider is healthy and
   confirm actual Telegram arrival.

Rollback is available from the backup directory above; restore the saved
backend/profile/cron/mapping files and DB dump as applicable, then restart only
the Mariyam gateway. Stage 6 must remain **PARTIAL** until all four residual
items pass.
