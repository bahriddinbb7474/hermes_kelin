# Cron watchdog + no-agent one-shot — evidence, 2026-07-28

Status: **CLOSED / LIVE PASS on approved test identities**. Real Oyijon and
other real recipient identities were not connected.

## Deployed state

- Feature commit:
  `d3ff5b5` (`feat: cron watchdog and no-agent one-shot reliability`), pushed
  to `origin/main`.
- VPS marker: `d3ff5b5`.
- Controlled rollback backup:
  `/opt/hermes-mariyam/var/deploy-backups/imp08-20260728T001757Z`.
- Gateway active; PostgreSQL healthy; Time-Agent running and not restarted.
- Backend inventory / dispatch / real MCP discovery: **29 / 29 / 29**,
  unique names **29**.
- MCP health: `gateway=up`, `db=up`.
- Canonical SOUL LF SHA-256:
  `999b657165f3557fe8d76d473c88d94fda543fdcefe37fbb05d15c6542831b60`.
- `mariyam_cron_reliability` **1.0.0** discovered, enabled and registered
  through the real Hermes plugin manager.
- User-systemd timer: active + enabled; service result `success`. Existing
  linger keeps the user manager alive after logout/reboot.
- Watchdog state parent: mode 0700. No claim DB was created by healthy/not-due
  production ticks.
- Production jobs/private mapping: **9 / 9**, mapping mode 0600. Exact eight
  critical jobs were found. Every watched trusted job remained enabled,
  mapped, `script=null`, `no_agent=false`.

## Mechanism

The timer runs every five minutes. For the current scheduled occurrence,
after a 15-minute grace and within a bounded six-hour window, it requires:

1. exact trusted name/schedule/job shape;
2. `last_run_at` for this occurrence and `last_status=ok`;
3. no `last_delivery_error`;
4. a new regular cron output file.

A private SQLite `(job_id, expected_at)` claim permits one retry only. If retry
or its direct Telegram notification is interrupted, the next tick resumes only
the admin alert and does not run the user delivery again. Ambiguous state
(output exists but delivery state was not committed) suppresses retry to avoid
a duplicate and alerts the admin. Retry failure sends the approved test-admin
only `job`, scheduled time and bounded reason through the Stage 8 heartbeat
Telegram credentials, without an LLM.

The profile middleware accepts only a future timezone-aware ISO one-shot from
a mapped Oyijon Telegram session. It materializes a private mode-0600 script,
sets `repeat=1`, `deliver=origin`, `no_agent=true`, removes model/tools/skills,
and leaves the job untrusted. Recurring/admin/non-Oyijon jobs pass unchanged.

## Offline gates

- Full repository suite: **290 passed, 87 skipped**.
- Focused prompt/identity/cron/health regression: **59 passed**.
- New imp08 contract suite: **10 passed**.
- Ruff for new Python implementation/tests: PASS.
- Python compile checks: PASS.

The permanent suite covers normal silence, failed tick → one successful retry,
failed retry → one admin alert, notifier recovery without rerunning the job,
stale/interrupted claim escalation, exact eight-job config, no-agent script
shape/self-delete and trusted/admin bypass.

## Live watchdog E2E

The initial failed occurrence was simulated in an isolated state-equivalent
job store (`last_status=error`, provider failure reason). The retry callback
ran the real Hermes cron execution/delivery path against a temporary untrusted
test job whose delivery target was copied from the existing test-Oyijon job.

Results:

```text
retry: result=retry_ok, calls=1, last_status=ok,
       last_delivery_error=false, unexpected_admin_notices=0
retry-fail: first=admin_alerted, second=already_handled,
            runs=1, direct_admin_notices=1
healthy: result=healthy, runs=0, admin_notices=0
```

Telegram Web visibly showed the retry message in the Mariyam/test-Oyijon chat
at 05:22. The approved test-admin received one direct failure alert containing
job, time and simulated reason. There was no second retry or second alert.

Cleanup removed the temporary retry job, its output and three exact temporary
cron session/message records. Production jobs returned **9 → 9**.

## Live no-agent one-shot E2E

A future ISO one-shot was created through the deployed real middleware chain
for the mapped test-Oyijon session. Before due:

```text
no_agent=true, script mode=0600, repeat=1, origin bound
skills=[], enabled_toolsets=[], model/provider unpinned
untrusted=true, jobs=10
```

At **05:29 Asia/Tashkent**, Telegram Web visibly showed the exact fixed phrase:

```text
Ойижон, имп08 но-агент синови тайёр.
```

Post-run evidence:

```text
job removed after once=true
script self-deleted=true
cron-agent/LLM sessions=0
delivery error logged=false
output contains exact phrase=true
```

Cleanup removed the output and any remaining script metadata; jobs returned to
**9**, private mapping stayed **9**, and no production session/job was changed.

## Rollback

Disable/remove only the three imp08 user units, restore profile SOUL/config and
the reliability plugin from the backup above, remove only imp08 watchdog state,
run `systemctl --user daemon-reload`, and restart only
`hermes-gateway-mariyam_oyijon.service`. Do not change backend, PostgreSQL,
migration 005, nine trusted jobs/mapping, Stage 8 heartbeat or Time-Agent.
