# imp09 — report

Status: **DONE — technical acceptance passed; the time-gated 08:30 and 19:30
scheduled-tick evidence remains an explicit follow-up**.

Completed:

- live language/persona matrix: 19/19 Uzbek Cyrillic, zero Latin letters and
  zero technical traces;
- safety, identity, reboot/autostart, encrypted backup, heartbeat and
  watchdog gates passed;
- OpenAI benchmark completed for `whisper-1`, `gpt-4o-transcribe` and
  `gpt-4o-mini-transcribe` on all 15 real recordings, 20 expense proxies and
  7 medical proxies: 126/126 API calls succeeded;
- selected `gpt-4o-transcribe`: best medical retention, comparable latency,
  production prompt retest 42/42 success and keyword gate 7/7;
- production STT now uses `gpt-4o-transcribe` through a private API key;
  config contains no key and transcript echo is disabled;
- API retry budget is capped at two 25-second attempts inside the Hermes
  120-second command timeout so local fallback can finish;
- a forced provider-failure smoke proved the local faster-whisper `base`
  fallback returns a non-empty transcript;
- strict voice→DB acceptance: 18/20 (90%); amount accuracy: 19/20 (95%);
- the prompt fix for “регулярно” produced one monthly
  `recurring_obligations` row and zero unexpected cron jobs; exact cleanup
  restored the baseline;
- measured projection logged through `log_usage_cost`: 20 files/day,
  96.3286 audio minutes/month, about USD 0.667/month;
- full offline regression: 298 passed, 87 skipped;
- post-deploy runtime: tools 29/29/29, health true, gateway active with zero
  restarts, PostgreSQL healthy with zero restarts;
- test mutations and temporary trusted jobs were removed; DB returned to
  transactions 9, cycles 1, obligations/health/Quran/alerts 0.

Time-gated follow-up (not claimed as passed in this report):

1. verify the first scheduled morning message after the final SOUL deploy at
   08:30 Asia/Tashkent;
2. verify the first scheduled evening message at 19:30 Asia/Tashkent.

The implementation, technical gates, evidence, cleanup and repository handoff
were completed now at the user's explicit request; the two future ticks were
not accelerated or represented as successful.

No real accounts were connected. Raw real-voice transcripts, Telegram IDs,
credentials and private mappings are absent from git and evidence.

Evidence: `docs/EVIDENCE_FINAL_ACCEPTANCE_2026-07-29.md`.
