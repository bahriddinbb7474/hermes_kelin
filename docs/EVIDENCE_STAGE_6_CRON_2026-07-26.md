# Stage 6 cron — live evidence, 2026-07-26

Status: **CLOSED / LIVE PASS on the approved test Oyijon identity**.

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
- Cache after the 2026-07-27 retry: PASS, mode 0600, three daily entries.
- OpenWeather retry on 2026-07-27: PASS through the production MCP, fresh
  Tashkent data (`stale=false`). The same active key is present only in the two
  private 0600 production env files; its value was not logged or added to git.
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

On 2026-07-27 all three normal post-fix ticks completed successfully:

- morning 08:30: status `ok`, non-empty output, no guard/runtime marker,
  trust resolve PASS;
- obligation reminders 09:15: status `ok`, non-empty output, no guard/runtime
  marker, trust resolve PASS;
- evening 19:30: status `ok`, non-empty output, no guard/runtime marker,
  trust resolve PASS.

After explicit approval on 2026-07-27, the exact production morning job was run
manually for the test Oyijon identity. It delivered one Telegram digest at
22:35 Tashkent time: fresh Tashkent weather, all five prayer times, four UzA
news items and the honest empty-obligations result. The output contained 1,415
Cyrillic characters, was non-empty, and had no blocked/runtime/technical marker.

## Telegram one-shot smoke

- From the agreed test account, the phrase
  `Эртага соат 10 да дорини эслат.` received a Cyrillic confirmation and
  created exactly one `once` job for 10:00 the next day.
- The job was untrusted: mapping=false, repeat=1, no script, no user-scoped or
  terminal/tool instructions.
- The first safe due-now smoke at 19:42 was invoked on time and consumed, but
  the model provider returned HTTP 524 after its 120-second timeout. No reminder
  arrived in that historical attempt.
- The authorized retry used
  `Бугун, 27 июль 2026, Тошкент вақти билан соат 22:45 да
  «IMP06 retry синови» деб эслат.` The bot confirmed the date/time, created
  exactly one unmapped `once` job with repeat 1 and no script/tool instructions,
  and delivered at 22:45:
  `Ойижон, “IMP06 retry синови”ни унутманг.`
- The successful one-shot was consumed as designed. Its exact cron session,
  compression lock and output directory were removed. Production returned to
  **8 jobs / 8 mapping entries**. No test obligation was created.

## HTTP 524 and cron retry semantics

Read-only inspection of the installed Hermes runtime and active profile found:

- `agent.api_max_retries=1`, which means one call to the primary provider, not
  one retry after the first call;
- a configured OpenRouter `deepseek/deepseek-chat` fallback, and live journal
  evidence that Hermes switches to it after a retryable primary-provider 524;
- no cron-level retry. For a recurring job Hermes advances `next_run` before
  execution. If primary and fallback both fail, that occurrence is not retried
  and the job waits for its next normal schedule;
- an agent failure is converted to a sanitized failure message for delivery.
  If Telegram delivery also fails, Hermes records `last_delivery_error`, but
  the recipient can receive nothing;
- finite one-shots are claimed before execution and removed after their single
  attempt, including an unsuccessful attempt. A provider outage can therefore
  consume a reminder permanently.

Minimal pre-handover protection proposed, but not deployed in this acceptance:

1. Add deterministic watchdog ticks at 08:45, 09:30 and 19:45. Each checks the
   exact primary job's status for the current occurrence, exits silently through
   `{"wakeAgent": false}` after success, and triggers the exact primary job once
   after failure/missing completion.
2. Send an admin alert if that single recovery attempt also fails.
3. Move user one-shot reminders to a deterministic no-agent dispatcher/queue so
   delivery of stored reminder text does not require an LLM provider.

Increasing `api_max_retries` alone is not the preferred protection: each 524 can
consume the full 120-second provider timeout, while it still does not repair the
at-most-once cron/one-shot semantics.

Rollback is available from the backup directory above; restore the saved
backend/profile/cron/mapping files and DB dump as applicable, then restart only
the Mariyam gateway. Stage 6 acceptance is closed on the approved test identity;
the retry watchdog and provider-independent one-shot path remain a pre-handover
reliability item before connecting the real Oyijon.
