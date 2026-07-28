# REGISTRY — задачи кодерам

| id | кодер | суть | статус | вердикт проверки |
|----|-------|------|--------|------------------|
| doc01 | Luna | Закрытие Stage 5.3: evidence + флип статусов + commit/push | done | PASS, 1 пропуск → fix01 |
| fix01 | Luna | Устаревшая строка статуса 5.3 в ТЗ (~стр. 322) | done | PASS |
| imp01 | Sol | Gate 5.3A: исследование cron identity Hermes v0.18.2 + design-док | done | PASS |
| imp02 | Sol | Cron identity resolver в identity guard 1.1.0 + offline-тесты | done | PASS, push подтверждён |
| imp03 | Sol | Controlled VPS deploy guard 1.1.0 + cron probes + evidence | done | PASS (замечание: версию после hotfix 7d9f7cf не подняли) |
| imp01-opus | Opus | Tool approve_monthly_plan + state machine цикла, count 22 | done | PASS |
| imp02-opus | Opus | Deploy + production cron jobs 25/27/28/1 + E2E | done (v2, через блокеры) | PASS частично: deploy/guard 1.2.0/jobs/25-27-28 ок; FAIL — cron-обёртка в чате Ойижон → fix01 |
| imp03b-opus | Opus | get_monthly_plan_cycle (24) + guard 1.2.0 + jobs 1a/1b | done | PASS (в составе imp02) |
| fix01-opus | Opus | Убрать cron-обёртку из доставки Ойижон + добить «ха»/1a/1b E2E | done | PASS; 5.3A = PARTIAL до live «ха» или auto-approve 1 авг |
| imp01-terra | Terra | Stage 8: backup+restore-проверка, автозапуск, heartbeat | done | LIVE PASS |
| imp03-opus | Opus | Tool open_monthly_plan_cycle (вариант A), count 23 | done | PASS |
| imp04-sol | Sol | Gate 5.4: исследование кабинета электрики (без кода) | done | PASS; вердикт NO-GO до разрешения HET + проверки с реальным аккаунтом |
| imp05-sol | Sol | Stage 6 шаг 1: migration 005 + obligations tools 26 + guard 1.3.0 + deploy | done | PASS, live deploy подтверждён |
| imp06-sol | Sol | Stage 6 шаг 2: cron-быт (утро/вечер, новости, погода, намаз, напоминания) | done | PASS, Stage 6 CLOSED live на test-user |
| imp07-sol | Sol | Stage 7: отчёт админу 19:30 + health-alerts recall 100% | done | PASS, CLOSED live; on-demand с admin-аккаунта — проверить заказчику |
| imp08-sol | Sol | Cron watchdog +15 мин и no-agent one-shot (pre-handover reliability) | done | PASS, CLOSED live |
| imp04-opus | Opus | Аудит токенов + личность «живая келин», SOUL v2 (2 фазы, STOP на утверждении) | фаза 1 done, STOP | — (ждёт утверждения заказчика) |
| — | Sol | Языковой + голосовой тест (после восстановления лимитов) | запланирована | — |
