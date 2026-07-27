# imp07 report — Stage 7

Status: **CLOSED / LIVE PASS on test identities, 2026-07-28**.

## Result

- Feature commit:
  `bbb66e4e8d3b4a45d009b1e132524e324cd53b5a`.
- Production backend: **29/29/29**, health `up/up`.
- Plugins: identity **1.3.0**, health **1.0.0**, Stage 5.3 **1.0.0**.
- Cron/mapping: **9/9**, Stage 7 job `30 19 * * *`, report tool allowlist only.
- Dataset: **35 positives / 20 negatives**.
- Detector recall: **100%**; curated precision: **100%**.
- Tests: full suite **277 passed, 87 skipped**; focused Stage 7
  **9 passed, 1 skipped**.
- Disposable PostgreSQL report equality: PASS, private fields: 0.
- Production report/SQL equality: PASS; manual test-admin delivery:
  `status=ok`, delivery error: none.
- Telegram alerts: **3/3** detected, **3/3** soft replies,
  **3/3** separate test-admin notifications, **3/3** DB rows.
- Cleanup: exact test DB rows **3**, guard-state rows **3** removed;
  post-cleanup `alerts=0`.
- Gateway active, PostgreSQL healthy, Time-Agent running.
- Real accounts were not connected.

Full evidence:
`docs/EVIDENCE_STAGE_7_2026-07-28.md`.

One explicit coverage note: the available Telegram Web session was
test-Oyijon, so a second inbound “отчёт за сегодня” message from test-admin was
not sent. The identical report tool path and actual test-admin delivery were
verified through the exact trusted Stage 7 job.
