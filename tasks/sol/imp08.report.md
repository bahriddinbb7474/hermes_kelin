# imp08 report — cron reliability

Status: **CLOSED / LIVE PASS on test identities, 2026-07-28**.

## Result

- Feature commit: `d3ff5b5`
  (`feat: cron watchdog and no-agent one-shot reliability`), pushed.
- VPS marker: `d3ff5b5`; rollback backup:
  `/opt/hermes-mariyam/var/deploy-backups/imp08-20260728T001757Z`.
- User-systemd watchdog timer active/enabled; service result `success`.
- Eight critical recurring jobs covered with +15-minute grace, one retry,
  private dedupe claim and direct test-admin fallback without LLM.
- Trusted jobs unchanged: jobs/mapping **9/9**, all watched jobs
  `script=null`, `no_agent=false`.
- No-agent one-shot middleware **1.0.0** active; untrusted future ISO reminder
  uses private script 0600, repeat 1, origin delivery and no model/tools.
- Full tests: **290 passed, 87 skipped**; focused regression **59 passed**;
  imp08 contracts **10 passed**; Ruff/compile PASS.
- Live watchdog:
  - simulated failed state → one real retry → Telegram test-Oyijon delivery;
  - retry failure → one direct test-admin alert; next tick already handled;
  - healthy tick → zero retry, zero alert.
- Live one-shot: exact phrase delivered at 05:29 Asia/Tashkent; job removed,
  script self-deleted, cron-agent/LLM sessions **0**, delivery errors **0**.
- Cleanup: production jobs **9**, mapping **9**, temporary job/output/script
  and exact test cron session artifacts removed.
- Runtime: **29/29/29**, health `up/up`, Gateway active, PostgreSQL healthy,
  Time-Agent running. Real accounts were not connected.

Full evidence:
`docs/EVIDENCE_CRON_WATCHDOG_2026-07-28.md`.
