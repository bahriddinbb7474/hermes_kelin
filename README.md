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
│   ├── hermes-mariyam.service
│   └── hermes-gateway-mariyam_oyijon.service
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

Настроить Hermes profile `mariyam_oyijon`, Telegram allowlist, skill личности Мариям, память, сквозной STT-тест на реальном голосе (TTS отложен — ТЗ v3.2, ответы только текстом), маленький MCP backend с PostgreSQL для точных данных, бухгалтерию с исправлением/удалением, Hermes cron для напоминаний и отчётов, safety alerts, backup/restore и мониторинг.

## Текущее состояние (2026-07-12)

ТЗ: **v3.6**. Решение заказчика 2026-07-11/12: для полного тестирования до handover разрешён второй Telegram-аккаунт заказчика с временным test role=oyijon (`display_name="Тест Ойижон"`); настоящий ID Ойижон и seed — только при handover; реальной Ойижон отправка строго запрещена. Решение 2026-07-12: тихая блокировка unauthorized в Hermes v0.18.2 принята как допустимое поведение MVP (ТЗ §0.5, DECISIONS.md). Дополнительно 2026-07-12: детерминированная identity binding зафиксирована в ТЗ v3.6 (§0.6) и прошла независимый аудит `PASS_TO_VPS_PHASE_B`; вся feature-ветка **merged локально в `main` через `dd9261e`** (включая DB guard и identity guard). VPS Phase B ещё не выполнялась.

Этап 1 (VPS + Hermes + Telegram) — **закрыт по решению заказчика (2026-07-12, ТЗ v3.5)**:
- ✅ PostgreSQL healthy (порт 127.0.0.1:5432, init-миграции применены);
- ✅ Hermes Agent v0.18.2 установлен (профиль `mariyam_oyijon` создан; модель `gpt-5.6-luna` через api.n1n.ai — утверждена 2026-07-12, язык 100%/числа 100%; в allowlist сейчас admin + временный test-user «Тест Ойижон», допустимый для e2e-тестов — ТЗ §0.4);
- ✅ MCP stdio зарегистрирован (`mariyam_backend`): Hermes видит ровно **19 tools**, реальные tool-calls работают; `ensure_user` (admin) выполнен идемпотентно;
- ✅ skill mariyam установлен в профиль (enabled, sha256 совпадает с репо);
- ✅ Telegram Gateway установлен как **systemd user-service** (`hermes-gateway-mariyam_oyijon.service`; user-unit, `Restart=always`, без секретов); `loginctl enable-linger timeagent` выполнен; unit `active`/`enabled` (Блок 6И);
- ✅ **Живой ответ получен**: бот ответил Бахриддин ака в Telegram на узбекской кириллице (gateway реально принимает и обрабатывает сообщения);
- ✅ Негативный allowlist-тест выполнен: аккаунт вне allowlist блокируется адаптером **до** LLM/tools/БД — `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (решение заказчика 2026-07-12, ТЗ §0.5; точный текст отказа `Кечирасиз, бу шахсий ёрдамчи.` не обязателен для Hermes v0.18.2);
- ✅ Автозапуск + reboot-тест пройдены: после общего `sudo reboot` (VPS общий с Time-Agent) Gateway поднялся автоматически, ровно один процесс, PostgreSQL healthy, контейнер Time-Agent снова работает, `/opt/time-agent` не трогался (Блок 6И);
- ✅ Очистка тестовых данных production-БД выполнена (Блок 6З): остался только `admin` (id=1), все fixture-таблицы пусты; backup перед очисткой сохранён;
- ✅ **Вся feature-ветка merged локально в `main` через `dd9261e`** (DB guard `tests/db_guard.py` и identity guard `deploy/hermes_plugins/mariyam_identity_guard/` включены; commit systemd `d24d01c` вошёл в merge).

**Формальный аудит и merge в `main` Этапа 1 — ВЫПОЛНЕНЫ** (локальный commit `dd9261e`; push в `origin/main` ещё НЕ выполнен — по решению заказчика push отдельный). VPS Phase B (установка identity guard на VPS) ещё не выполнялась.

**Этап 2 (язык, живой AC) — PARTIAL 8/20, НЕ закрыт:**
- ✅ 8 из 20 фраз проверены (Сообщения 1–2, по 4 фразы) со второго аккаунта «Тест Ойижон»;
- ✅ 8/8 ответов — узбекская кириллица, `LATIN_LINES: []` (STAGE2_LATIN_PASS на выборке); тон мягкий/уважительный;
- 🟡 полный AC (20/20, 0 латиницы) **НЕ пройден** — Сообщения 3–5 (фразы 9–20) не отправлялись; тест остановлен заказчиком, не из-за FAIL.
- Детали: `docs/TZ/EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md`.

**Этап 5 (бухгалтерия, живой AC) — НЕ тестирован:**
- 🟡 backend готов; сквозная проверка через Hermes (6 бухгалтерских сообщений) не выполнялась. `transactions` test-user = 0.
- 🟡 **Identity-дефект обнаружен и устранён локально** (ТЗ §0.6, `docs/TZ/EVIDENCE_IDENTITY_GUARD_2026-07-12.md`): при livete-тесте Hermes передал tools `user_id` admin вместо test-user. Локальная реализация identity guard прошла **43 unit/integration tests**, реальный Hermes v0.18.2 PluginManager discovery подтверждён, независимый аудит — `PASS_TO_VPS_PHASE_B`; код merged в `main` `dd9261e`. **VPS runtime и Telegram E2E ещё НЕ выполнены** → Этап 5 **НЕ закрыт**.

Текущий allowlist: **admin + временный «Тест Ойижон»** (второй аккаунт заказчика, role=oyijon). Реальная Ойижон отсутствует (до handover).

Telegram Ойижон не подключается и не получает сообщений/onboarding/cron до финальной передачи.

## Развёртывание и документация

- `deploy/DEPLOY.md` — инструкция deploy (локальная проверка на Windows + VPS Ubuntu 24.04), команды будущего запуска/отката, секреты, FORBIDDEN-секция (изоляция от Time-Agent).
- `deploy/hermes-mariyam.service` — systemd unit template (`Type=oneshot` + `RemainAfterExit=yes`, без `Restart=`; перезапуск — ответственность docker), запуск через `docker compose up -d`, остановка `docker compose down`, секреты через `/opt/hermes-mariyam-secrets/backend.env`. Назначение: oneshot-шаблон запуска compose/PostgreSQL.
- `deploy/hermes-gateway-mariyam_oyijon.service` — долгоживущий systemd **user-service** Telegram Gateway (`Type=simple`, `Restart=always`), запуск `hermes -p mariyam_oyijon gateway run`. Назначение: постоянный автозапускаемый процесс бота, не смешивать с oneshot-шаблоном PostgreSQL.
- `backend/.env.example` — пример переменных окружения (только placeholder, без реального пароля).
- `tests/run_tests.py` — постоянные тесты (`ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`), запуск из репозитория.
