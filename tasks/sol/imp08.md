# imp08 (Sol) — Надёжность cron: watchdog +15 мин и no-agent путь (pre-handover)

## Контекст
Repo `main` (после `4a4f0b0`). Runtime: backend 29, guard 1.3.0,
health guard plugin, 9 trusted jobs. Из imp06 зафиксировано: у Hermes есть
provider-fallback (deepseek), но НЕТ cron-retry — упавший recurring-тик
пропадает до следующего расписания, упавший one-shot сгорает. Для реальной
Ойижон это риск: молча пропавшее утро/намаз/лекарство. Твоя же рекомендация:
deterministic +15-minute watchdog + no-agent one-shot dispatcher.

## Что сделать
1. Watchdog (+15 мин) для критичных recurring jobs (утро, obligation reminders,
   19:30 admin report, jobs цикла 25/27/28/1a/1b):
   - детерминированно определять «тик прошёл, доставки не было» (по
     cron output/session state, без LLM);
   - один повторный запуск; если и он упал — уведомление админу напрямую
     (механизм heartbeat из Stage 8, мимо LLM);
   - без дублей: если доставка была — watchdog молчит; повтор не создаёт
     второе сообщение Ойижон.
   Реализация — ops-контур (systemd timer/скрипт, как Stage 8) или узкое
   расширение профиля; Hermes core не менять. Решение зафиксировать в DECISIONS.
2. No-agent путь для one-shot напоминаний («эртага 10 да эслат»):
   - исследовать `no_agent`/script-доставку Hermes для one-shot: текст
     напоминания фиксируется при создании и доставляется БЕЗ вызова LLM
     (провайдер-независимо);
   - SOUL-инструкцию создания one-shot переключить на этот путь, если он
     жизнеспособен; иначе — обосновать в отчёте и оставить LLM-путь
     + включить one-shots в watchdog.
   Помни: trusted mapping для identity jobs запрещает script/no_agent — это
   касается только untrusted one-shot напоминаний без user-scoped tools.
3. Тесты/E2E: симулированный сбой (подмена provider endpoint на тест-job или
   иной безопасный способ) → watchdog повторил → доставка; сбой повтора →
   admin-уведомление; штатный успешный тик → watchdog молчит (нет дублей);
   one-shot no-agent → доставлен вовремя без LLM-вызова. Cleanup.
4. Deploy controlled + rollback; evidence `docs/EVIDENCE_CRON_WATCHDOG_<дата>.md`;
   README/ROADMAP: пункт pre-handover reliability закрыт.

## Запрещено
Hermes core; дубли сообщений Ойижон; script/no_agent в trusted identity jobs;
секреты в git/логи.

## Отчёт
`tasks/sol/imp08.report.md`: механизм, логи симуляций, hash коммитов.
Commit поимённо + push: `feat: cron watchdog and no-agent one-shot reliability`.
В чат заказчику: 2–3 предложения простым русским.
