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

## Текущее состояние (2026-07-10)

**Сделано и проверено** (ветка `feature-hermes-mariyam-mvp`, коммит `cd81fc2`, ТЗ v3.1):

- Backend MCP-сервер с 19 tools (включая `ensure_user`), PostgreSQL-схема, docker-compose с изоляцией, systemd-шаблон, deploy-доки, skill Мариям.
- Все блокеры аудита закрыты: единый пул соединений, fail-fast без `DATABASE_URL`, `.dockerignore` (образ чистый — `IMAGE_CLEAN`), валидный systemd unit, честные `NOT_CONFIGURED`-заглушки backup, per-tool схемы с `required`.
- Тесты зелёные на чистой БД: `ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`, `POOL_STABLE_PASSED`, `MCP_SMOKE_PASSED`; stdio и HTTP initialize проверены.

**Не сделано:** всё, что требует VPS и реальных данных — Этапы 0–3 и 6–8 ТЗ (доступы, Hermes+Telegram, тест голоса, cron, backup). VPS не трогать без отдельного разрешения.

## Карта кода (ветка feature-hermes-mariyam-mvp)

| Путь | Что это |
|---|---|
| `backend/server.py` | MCP-сервер: dispatch, схемы tools, транспорты stdio/HTTP |
| `backend/db.py` | Слой БД: SQL, валидация enum, границы дней Asia/Tashkent |
| `backend/config.py` | Пул соединений (один на процесс), `DATABASE_URL` fail-fast, TASHKENT tz |
| `backend/sql/001_init.sql` | Схема БД + seed категорий (идемпотентно) |
| `tests/run_tests.py` | Все тесты; 4 маркера; предохранитель от боевой БД |
| `docker-compose.yml` | Postgres (+ HTTP-backend для локальной проверки) |
| `deploy/DEPLOY.md` | Полная инструкция: локальная проверка, seed, миграции, VPS |
| `deploy/hermes-mariyam.service` | systemd unit (Postgres через compose) |
| `skills/mariyam/SKILL.md` | Личность/правила Мариям для Hermes-профиля |

## Как проверить локально

```bash
cd .worktrees/feature-hermes-mariyam-mvp   # или checkout ветки
set -a; . backend/.env; set +a            # backend/.env из backend/.env.example
docker compose up -d
DATABASE_URL=postgresql://hermes:${POSTGRES_PASSWORD}@localhost:5432/hermes \
  backend/.venv/Scripts/python.exe tests/run_tests.py
# ожидаются 4 маркера; подробности — deploy/DEPLOY.md
```

## Что делать дальше

Следующий этап — Этап 0/1 ТЗ (доступы, VPS, Hermes, Telegram). Пошаговые инструкции для исполнителя: `HERMES_PROFILE.md` (профиль/skill/MCP), `VOICE_STT_TTS.md` (тест голоса), `CRON_AND_REMINDERS.md` (расписания), `deploy/DEPLOY.md` (VPS).
