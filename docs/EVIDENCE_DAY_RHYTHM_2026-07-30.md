# fix02 — day rhythm evidence, 2026-07-30

Status: **CLOSED / LIVE PASS on the approved test identities**.

No real Oyijon account was connected. The customer approved the displayed
prayer templates, the exact RSS list and controlled deploy on 2026-07-30.
Telegram delivery used only the existing private test-Oyijon mapping; IDs,
tokens, full fingerprints and private mapping contents are not recorded here.

## Deployed state

- Controlled rollback backup:
  `/home/timeagent/fix02-backup-20260730_032536` (mode 0700).
- Backend inventory / dispatch / direct list / real MCP discovery / unique
  names: **29 / 29 / 29 / 29 / 29**.
- MCP health: `ok=true`, `gateway=up`, `db=up`, `last_error=null`.
- Gateway: active and enabled, `NRestarts=0`.
- PostgreSQL: running and healthy; Time-Agent: running.
- Plugin order: identity → health → cron reliability → Stage 5.3.
  Identity guard is **1.3.0**; cron reliability is **1.1.0**.
- Morning is exactly `0 8 * * *`; evening remains `30 19 * * *`.
  The watchdog configuration has the matching morning schedule.
- Prayer scheduler timer is active and enabled; its last service result is
  `success`, exit status 0.
- Trusted cron mapping remains **9** entries, mode 0600. At the final check
  there were 14 jobs: nine trusted recurring jobs and five future prayer jobs
  for the remainder of the current day. Fajr had already passed. A normal
  00:20 run creates the separate 07:45 prayer-time list and all five reminders
  when all six times are still in the future.

## Deploy incident and correction

The first scheduler start failed before creating a job because direct script
execution did not have the application root on Python's import path:
`ModuleNotFoundError: backend`. Gateway had already restarted successfully and
remained active. The user unit was corrected with the explicit production
`PYTHONPATH=/opt/hermes-mariyam`, passed `systemd-analyze verify --user`, and
the next run completed successfully. The same correction is committed in the
repository and in the deployed unit.

The manual no-agent smoke also established an operator detail: `cron run`
must be invoked with the profile `HERMES_HOME`, matching the Gateway service.
Without it, the standalone CLI looks for scripts in the global Hermes scripts
directory. Scheduled Gateway ticks already have the correct environment.

## Prayer and quiet-window mechanism

- Each of fajr/dhuhr/asr/maghrib/isha has ten Uzbek-Cyrillic templates.
  Rotation is deterministic by local date and cannot repeat yesterday's
  variant in the same slot.
- Every fajr template uses the full greeting and «Намоз уйқудан афзал».
- Fresh same-day Aladhan data is required. On the live date the cache was
  fresh and reported fajr 03:23, dhuhr 12:30, asr 17:34, maghrib 19:42 and
  isha 21:28, Hanafi.
- Finite reminders are scheduled ten minutes before prayer. The daily
  prayer-time list is a separate 07:45 finite job.
- All generated jobs have `no_agent=true`, repeat `1`, private mode-0600
  self-deleting scripts and a configured test-Oyijon delivery target.
- Sleep state lasts until 08:00; Quran state lasts 90 minutes. Prayer quiet
  windows last 20 minutes from each prayer start. Empty output is not queued
  and cannot be delivered later. Direct health alerts are outside this gate.

## News and split morning

UzA is absent. `backend/news_sources.json` contains the approved list:

1. Кун.уз — `https://kun.uz/news/rss?lang=ru`;
2. Новости ООН — `https://news.un.org/feed/subscribe/ru/news/all/rss.xml`;
3. Дойче Велле — `https://rss.dw.com/rdf/rss-ru-all`;
4. Евроньюс —
   `https://ru.euronews.com/rss?format=mrss&level=theme&name=news`.

The parser supports RSS, Atom and namespaced RDF. Topic/source selection is
allowlisted through the existing `get_daily_news` tool; no tool was added.
Available topics are daily, Uzbekistan, world and Middle East.

A production Middle East request selected all four configured sources and
returned 11 candidates. One UN News fetch was recorded as a partial source
error while the other three sources remained usable; an immediate independent
probe of the exact UN URL returned HTTP 200. The earlier compatibility probe
parsed Kun 15, UN News 30, DW 75 and Euronews 50 entries.

The controlled morning tick produced one conversational message with the exact
opening «Хайрли тонг, Ойижон, кунингиз баракали бўлсин!», caring weather,
two Kun facts and the approved offer to tell more. It contained no prayer
times, obligations or instruction-list tone.

## Live Telegram and cost gates

All observations were made in Telegram Web on the mapped test account.

1. **Morning:** controlled run at 03:31 delivered the new 08:00-format message.
   The normal LLM path changed sessions/API totals from `637/949` to
   `638/951`.
2. **Prayer-window silence:** two no-agent jobs run during the live fajr quiet
   window produced empty output and no Telegram delivery.
3. **Sleep silence:** test-Oyijon sent `сплю` at 03:32. No reply appeared,
   including after a later recheck. Private state was mode 0600, kind `sleep`,
   until 08:00. The two already skipped non-critical jobs were absent, so no
   delayed or duplicate delivery was possible.
4. **Two prayer slots:** after the fajr window ended and the test sleep state
   was removed, controlled no-agent runs delivered the exact current-day
   dhuhr and asr templates at 03:46. Both cron output documents contained the
   same text visibly received in Telegram.
5. **Zero added model cost:** after sleep, quiet-window and the two delivered
   prayer runs, totals remained exactly `638 sessions / 951 API calls`.
   The new prayer/list messages therefore added zero LLM/API calls.

## Verification and cleanup

- Focused day-rhythm/news/cron reliability/SOUL suite: **45 passed**.
- Full repository suite with the matching deployed Hermes v0.18.2 source:
  **306 passed, 87 skipped**.
- New day-rhythm implementation lint: PASS.
- Python compilation: PASS.
- Deploy shell syntax and both user-systemd units: PASS.
- Test quiet state was removed.
- Six exact diagnostic/live cron-output directories were removed.
- Dhuhr and asr future jobs were recreated; all five remaining finite jobs
  again have private scripts and repeat 0/1.
- Temporary local/VPS bundles and probes are removed after the final
  repository checks.

Rollback remains available from the private backup above through
`deploy/fix02_deploy.sh --rollback`.
