# Roadmap

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## MVP этапы

1. Подготовка данных: доступы, Telegram IDs, voice samples, категории, бюджет.
2. VPS + Hermes + Telegram: установка, профиль, allowlist, автозапуск.
3. Skill Мариям: стиль, язык, onboarding, правило кириллицы.
4. Голос: тест STT, выбор TTS/LLM, budget estimate, `log_usage_cost`.
5. Backend tools + БД: PostgreSQL, MCP tools, категории, UTC/Asia-Tashkent правила.
6. Бухгалтерия: расходы, доходы, отчёты, баланс, исправление и удаление.
7. Hermes cron: напоминания, утро/вечер, новости, погода, намаз, heartbeat.
8. Admin reports + safety: отчёт 19:30, health alerts, `alert_events`.
9. Backup/restore/monitoring: encrypted backup, real restore test, reboot recovery.

## После MVP

- Религиозный RAG с проверенными и легальными источниками.
- Возможный medication-модуль, если появится назначенный список лекарств.
- Возможный второй emergency contact и настройка жёстких emergency-инструкций.
- Архив отправленных отчётов (`sent_reports`), если потребуется аудит.
- Более продвинутый cost monitoring и оптимизация моделей.

## Постоянные правила

- Не расширять backend в сторону второго мозга.
- Все новые расписания — через Hermes cron.
- Все точные данные — через tools/storage.
- Все ответы Ойижон — простая узбекская кириллица.
