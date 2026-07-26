# imp06 report — Stage 6 cron daily life

Result: **PARTIAL / deployed** on 2026-07-26.

Implemented and pushed:

- three read-only external tools: OpenWeather, Aladhan/Hanafi and UzA + Kun.uz;
- daily 0600 cache with honest stale/unavailable behavior;
- canonical morning 08:30, obligation 09:15 and evening 19:30 jobs;
- safe SOUL contract for untrusted plain-text one-shot reminders;
- tests and documentation.

Commits:

- `1d3841345ddde3d611a215cea7577afeb9f1bd77`
  `feat: Stage 6 cron daily life (morning/evening/news/weather/prayer)`
- `09bb6c09d5b1cab889e3bc9f59c672b778ab9bd9`
  `fix: use active Kun.uz RSS endpoint`

Live job inventory:

- morning `e5a1…`, `30 8 * * *`;
- obligations `668f…`, `15 9 * * *`;
- evening `a87f…`, `30 19 * * *`.

All three are trusted, mapped to the test Oyijon identity through the private
0600 file, and allow only their listed read-only user tool. Total production
state after cleanup: 8 jobs / 8 mapping entries.

Verification:

- local suite: 271 passed, 86 skipped;
- production backend/MCP: 29/29/29, health gateway+DB PASS;
- prayer/news/cache/hashes/services PASS;
- weather honestly unavailable because the private OpenWeather key is absent;
- Telegram creation/confirmation and untrusted one-shot security PASS;
- due-now one-shot delivery FAIL because the model provider returned HTTP 524;
- first scheduled evening tick ran, exposed a trailing-newline prompt-binding
  mismatch, and failed closed; job prompts/fingerprints were normalized and
  final `resolve_cron_actor` probe PASS;
- manual sensitive digest replay was not authorized by the safety gate;
- exact test one-shot jobs/sessions/outputs cleaned.

Full masked evidence and rollback details:
`docs/EVIDENCE_STAGE_6_CRON_2026-07-26.md`.
