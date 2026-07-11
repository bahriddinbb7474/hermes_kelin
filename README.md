# Hermes/Mariyam

Источник истины: `docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Что это

Hermes/Mariyam — персональный Telegram ИИ-агент для Ойижон. Образ агента: Мариям, уважительная ИИ келинчак. Главная платформа: Hermes Agent с Telegram Gateway, памятью, skills, voice, cron и LLM.

Ключевой принцип: **Hermes-first**. Hermes является единственным "мозгом"; backend нужен только как MCP tools/storage для точных данных.

## Структура репозитория

```
hermes-mariyam/
├── README.md              # этот файл
├── docs/                  # вся документация
│   ├── TZ/                # ТЗ и спецификации (источник истины)
│   │   ├── TZ_Hermes_Mariyam_FINAL_v3_0.md
│   │   ├── ARCHITECTURE.md, DATABASE.md, TOOLS_CONTRACTS.md
│   │   ├── CRON_AND_REMINDERS.md, VOICE_STT_TTS.md
│   │   ├── SECURITY_PRIVACY.md, DECISIONS.md, ACCEPTANCE_CRITERIA.md
│   ├── HERMES_PROFILE.md  # профиль Hermes
│   ├── PROJECT_CONTEXT.md # контекст проекта
│   └── ROADMAP.md         # дорожная карта
├── backend/               # тонкий MCP backend (FastMCP + PostgreSQL)
│   ├── server.py, db.py, config.py, __init__.py, __main__.py
│   ├── sql/001_init.sql
│   ├── requirements.txt, Dockerfile, .env.example
├── skills/mariyam/        # skill личности Мариям (SOUL-профиль)
│   └── SKILL.md
├── deploy/                # deploy docs + systemd template
│   ├── DEPLOY.md
│   └── hermes-mariyam.service
├── tests/run_tests.py     # постоянные тесты (ALL_TOOL_TESTS_PASSED)
├── data/voice-samples/    # голоса (gitignored, не коммитятся)
├── docker-compose.yml     # изолированный compose (hermes_mariyam_*)
└── .gitignore
```

## Как читать документы

1. Начинать с `docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md` — финальный single source of truth.
2. Затем рабочие конспекты в `docs/TZ/`: архитектура, контракты tools, БД, cron, безопасность, критерии приёмки.
3. **Задания по аудиту v3.1** — `docs/TZ/ZADANIYA_KODERU_FIKSY_AUDITA_v3_1.md` (порядок работы A→B→C, Definition of Done).
4. Старые v1/v2/review-файлы не использовать для исполнения.

## Что нельзя

- Нельзя писать отдельный backend-router, intent-classifier, LLM orchestrator или второй "мозг".
- Нельзя делать backend scheduler: все расписания идут через Hermes cron.
- Нельзя переносить стиль, тексты отчётов или смысловую классификацию в backend.

## MVP в одном абзаце

Настроить Hermes profile `mariyam_oyijon`, Telegram allowlist, skill личности Мариям, память, сквозной STT-тест на реальном голосе (TTS отложен — ТЗ v3.4, ответы только текстом), маленький MCP backend с PostgreSQL для точных данных, бухгалтерию с исправлением/удалением, Hermes cron для напоминаний и отчётов, safety alerts, backup/restore и мониторинг.

## Текущее состояние (2026-07-11)

ТЗ: **v3.4**. Решение заказчика 2026-07-11: для полного тестирования до handover разрешён второй Telegram-аккаунт заказчика с временным test role=oyijon (`display_name="Тест Ойижон"`); настоящий ID Ойижон и seed — только при handover; реальной Ойижон отправка строго запрещена.

Этап 1 (VPS + Hermes + Telegram) — **в работе**:
- ✅ PostgreSQL healthy (порт 127.0.0.1:5432, init-миграции применены);
- ✅ Hermes Agent v0.18.2 установлен (профиль `mariyam_oyijon` создан; модель `gpt-5.6-luna` через api.n1n.ai — утверждена 2026-07-12, язык 100%/числа 100%; в allowlist сейчас только админ, временный test-user «Тест Ойижон» допустим для e2e-тестов — ТЗ §0.4);
- ✅ MCP stdio зарегистрирован (`mariyam_backend`): Hermes видит ровно **19 tools**, реальные tool-calls работают; `ensure_user` (admin) выполнен идемпотентно;
- ✅ skill mariyam установлен в профиль (enabled, sha256 совпадает с репо);
- ⬜ Telegram Gateway + негативный тест: любой ID вне allowlist;
- ⬜ автозапуск (systemd user-service + `loginctl enable-linger`) + reboot-тест.

Telegram Ойижон не подключается и не получает сообщений/onboarding/cron до финальной передачи.

## Развёртывание и документация

- `deploy/DEPLOY.md` — инструкция deploy (локальная проверка на Windows + VPS Ubuntu 24.04), команды будущего запуска/отката, секреты, FORBIDDEN-секция (изоляция от Time-Agent).
- `deploy/hermes-mariyam.service` — systemd unit template (`Type=oneshot` + `RemainAfterExit=yes`, без `Restart=`; перезапуск — ответственность docker), запуск через `docker compose up -d`, остановка `docker compose down`, секреты через `/opt/hermes-mariyam-secrets/backend.env`.
- `backend/.env.example` — пример переменных окружения (только placeholder, без реального пароля).
- `tests/run_tests.py` — постоянные тесты (`ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`), запуск из репозитория.
