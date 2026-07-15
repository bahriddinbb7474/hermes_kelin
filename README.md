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

## Текущее состояние (2026-07-15)

ТЗ: **v3.13**. Stage 5.1 остаётся **CLOSED / LIVE PASS**. Stage 5.2 = **OFFLINE PASS / LIVE PENDING**: canonical SKILL и permanent contracts приведены к решениям заказчика, локальные проверки PASS. Repo canonical SKILL SHA = `f00214f7ebdd280bc71b04b133a40d7e018708bf35f7facea73843ec8cc02693`. После rollback VPS по-прежнему использует Stage 5.1 SKILL SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`; повторный Telegram E2E и deploy не выполнялись. Runtime = **21 tools / plugin 1.0.4 / migration 002**. Stage 5.3–6 остаются **PLANNED / NOT IMPLEMENTED**; migrations 003/004/005 отсутствуют. Реальная Ойижон не подключена.

Этап 1 (VPS + Hermes + Telegram) — **закрыт по решению заказчика (2026-07-12, ТЗ v3.5)**:
- ✅ PostgreSQL healthy (порт 127.0.0.1:5432, init-миграции применены);
- ✅ Hermes Agent v0.18.2 установлен (профиль `mariyam_oyijon` создан; модель `gpt-5.6-luna` через api.n1n.ai — утверждена 2026-07-12, язык 100%/числа 100%; в allowlist сейчас admin + временный test-user «Тест Ойижон», допустимый для e2e-тестов — ТЗ §0.4);
- ✅ На момент Stage 4 acceptance MCP stdio `mariyam_backend` показывал ровно **19 tools**; реальные tool-calls работали, `ensure_user` был идемпотентен. Текущий runtime после Stage 5.1 = 21 tools;
- ✅ skill mariyam установлен в профиль (enabled, sha256 совпадает с репо);
- ✅ Telegram Gateway установлен как **systemd user-service** (`hermes-gateway-mariyam_oyijon.service`; user-unit, `Restart=always`, без секретов); `loginctl enable-linger timeagent` выполнен; unit `active`/`enabled` (Блок 6И);
- ✅ **Живой ответ получен**: бот ответил Бахриддин ака в Telegram на узбекской кириллице (gateway реально принимает и обрабатывает сообщения);
- ✅ Негативный allowlist-тест выполнен: аккаунт вне allowlist блокируется адаптером **до** LLM/tools/БД — `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (решение заказчика 2026-07-12, ТЗ §0.5; точный текст отказа `Кечирасиз, бу шахсий ёрдамчи.` не обязателен для Hermes v0.18.2);
- ✅ Автозапуск + reboot-тест пройдены: после общего `sudo reboot` (VPS общий с Time-Agent) Gateway поднялся автоматически, ровно один процесс, PostgreSQL healthy, контейнер Time-Agent снова работает, `/opt/time-agent` не трогался (Блок 6И);
- ✅ На момент Блока 6З очистка production-БД оставила только `admin`, fixture-таблицы были пусты, backup сохранён; позднее для pre-handover E2E добавлен временный test-user;
- ✅ **Вся feature-ветка merged локально в `main` через `dd9261e`** (DB guard `tests/db_guard.py` и identity guard `deploy/hermes_plugins/mariyam_identity_guard/` включены; commit systemd `d24d01c` вошёл в merge).

**Формальный аудит и merge в `main` Этапа 1 — ВЫПОЛНЕНЫ.** VPS Phase B выполнена: Stage 5 Telegram E2E PASS. Текущий runtime после Stage 5.1 = **21 tools / plugin 1.0.4**; Stage 5.1 закрыт live acceptance.

**Этап 2 (язык, живой AC) — PARTIAL 8/20, НЕ закрыт:**
- ✅ 8 из 20 фраз проверены (Сообщения 1–2, по 4 фразы) со второго аккаунта «Тест Ойижон»;
- ✅ 8/8 ответов — узбекская кириллица, `LATIN_LINES: []` (STAGE2_LATIN_PASS на выборке); тон мягкий/уважительный;
- 🟡 полный AC (20/20, 0 латиницы) **НЕ пройден** — Сообщения 3–5 (фразы 9–20) не отправлялись; тест остановлен заказчиком, не из-за FAIL.
- Детали: `docs/TZ/EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md`.

**Этап 5 (бухгалтерия, живой AC) — ЗАКРЫТ (PASS 2026-07-13):**
- ✅ На момент Stage 5 acceptance: identity guard **1.0.3**, E2E 4/4, runtime tools **19**; текущий runtime после Stage 5.1 указан ниже.
- ✅ Evidence: `docs/TZ/EVIDENCE_STAGE_5_E2E_2026-07-12.md`.

**Этап 5.1 (аналитика + monthly plan) — CLOSED / LIVE PASS (решение v3.9, сохранено в v3.11):**
- ✅ Runtime: quantity/unit, by_item, compare/trend, plan/fact; tools/dispatch/discovery **21/21/21**; plugin **1.0.4**; migration 002 active; SKILL SHA `b1231182…`; skill-protect **4/4**.
- ✅ Controlled E2E на «Тест Ойижон»: identity PASS, 6/7 provider requests, retry=0; cleanup восстановил DB baseline. Evidence: `docs/EVIDENCE_STAGE_5_1_LIVE_2026-07-13.md`.

**Stage 5.2 — OFFLINE PASS / LIVE PENDING (v3.13):**
- canonical SKILL и permanent tests приведены к утверждённому формату общих и подробных отчётов;
- repo SHA = `f00214f7ebdd280bc71b04b133a40d7e018708bf35f7facea73843ec8cc02693`; VPS после rollback остаётся на SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`; повторный Telegram E2E и deploy не выполнялись;
- предыдущий live FAIL зафиксирован в `docs/EVIDENCE_STAGE_5_2_LIVE_FAIL_2026-07-15.md`.

**Planned v3.13 — NOT IMPLEMENTED:**
- Stage 5.3/5.3A: product plan, last/weighted average/manual reference prices, migration 003 price snapshot и approval cycle 25/27/28/1; planned count 21→22 после approval tool;
- Stage 5.4: researched official utility cabinet, deterministic read-only connector, migration 004, planned count 25;
- Stage 6 extension: recurring obligations, migration 005, Hermes cron, planned final count 27;
- current runtime остаётся **21**; VPS/profile не менялись в рамках offline fix.

Текущий allowlist: **admin + временный «Тест Ойижон»** (второй аккаунт заказчика, role=oyijon). Реальная Ойижон отсутствует (до handover).

Telegram Ойижон не подключается и не получает сообщений/onboarding/cron до финальной передачи.

## Развёртывание и документация

- `deploy/DEPLOY.md` — инструкция deploy (локальная проверка на Windows + VPS Ubuntu 24.04), команды будущего запуска/отката, секреты, FORBIDDEN-секция (изоляция от Time-Agent).
- `deploy/hermes-mariyam.service` — systemd unit template (`Type=oneshot` + `RemainAfterExit=yes`, без `Restart=`; перезапуск — ответственность docker), запуск через `docker compose up -d`, остановка `docker compose down`, секреты через `/opt/hermes-mariyam-secrets/backend.env`. Назначение: oneshot-шаблон запуска compose/PostgreSQL.
- `deploy/hermes-gateway-mariyam_oyijon.service` — долгоживущий systemd **user-service** Telegram Gateway (`Type=simple`, `Restart=always`), запуск `hermes -p mariyam_oyijon gateway run`. Назначение: постоянный автозапускаемый процесс бота, не смешивать с oneshot-шаблоном PostgreSQL.
- `backend/.env.example` — пример переменных окружения (только placeholder, без реального пароля).
- `tests/run_tests.py` — постоянные тесты (`ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`), запуск из репозитория.
