# fix01 — Одна устаревшая строка статуса Stage 5.3 в ТЗ

## Контекст
После doc01 (commit `c03b603`) Stage 5.3 = CLOSED / LIVE PASS, но в
`docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md` (~строка 320–324, описание первого
неудачного E2E) осталось:
«Follow-up fix = **OFFLINE PASS / LIVE PENDING**; новый controlled deploy и E2E
обязательны до LIVE PASS.»
Это статус 5.3, противоречит закрытию этапа.

## Что сделать
1. Заменить эту фразу на:
   «Follow-up fix = **CLOSED / LIVE PASS**; повторный Telegram E2E пройден,
   см. `docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md`.»
   Историческое описание самого неудачного прогона выше по тексту НЕ менять.
2. Больше ничего не трогать. Упоминания «LIVE PENDING» про Stage 5.2 в
   DECISIONS.md и ТЗ — исторические, оставить как есть.
3. Commit только этого файла (`git add docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md`):
   `docs: fix stale Stage 5.3 status line in TZ` + push в `main`.
   CRLF-изменения других файлов не коммитить.

## Отчёт
- `tasks/luna/fix01.report.md`: diff строки, hash коммита, подтверждение push.
- В чат заказчику: 1–2 предложения простым русским.
