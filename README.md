# Hermes/Mariyam

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Что это

Hermes/Mariyam — персональный Telegram ИИ-агент для Ойижон. Образ агента: Мариям, уважительная ИИ келинчак. Главная платформа: Hermes Agent с Telegram Gateway, памятью, skills, voice, cron и LLM.

Ключевой принцип: **Hermes-first**. Hermes является единственным "мозгом"; backend нужен только как MCP tools/storage для точных данных.

## Как читать документы

1. Начинать с `Hermes-Oyijon-TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md` — это финальный single source of truth.
2. Затем читать рабочие конспекты в корне: архитектура, профиль Hermes, контракты tools, БД, cron, безопасность, критерии приёмки.
3. Старые v1/v2/review-файлы не использовать для исполнения. Они только история.

## Что нельзя начинать из этих документов

- Нельзя писать отдельный backend-router, intent-classifier, LLM orchestrator или второй "мозг".
- Нельзя делать backend scheduler: все расписания идут через Hermes cron.
- Нельзя переносить стиль, тексты отчётов или смысловую классификацию в backend.

## MVP в одном абзаце

Настроить Hermes profile `mariyam_oyijon`, Telegram allowlist, skill личности Мариям, память, STT/TTS тест на реальном голосе, маленький MCP backend с PostgreSQL для точных данных, бухгалтерию с исправлением/удалением, Hermes cron для напоминаний и отчётов, safety alerts, backup/restore и мониторинг.
