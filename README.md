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
│   ├── sql/001_init.sql, 002_stage51_quantity_budget.sql, 003_stage53_product_plans.sql
│   ├── requirements.txt, Dockerfile, .env.example
├── deploy/                # deploy docs + systemd template
│   ├── DEPLOY.md
│   ├── hermes_profile_mariyam_oyijon/SOUL.md # canonical profile prompt
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

## Текущее состояние (2026-07-18)

ТЗ: **v3.19**. Stage 5.1 и Stage 5.2 = **CLOSED / LIVE PASS**; Stage 5.3 = **CLOSED / LIVE PASS** ([evidence](docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md)). `items` omitted остаётся category-only совместимостью; explicit empty/null/non-array `items` детерминированно отклоняется до DB mutation. Новый отдельный profile plugin `mariyam_stage53_guard` связывает structured price lookup с product save и блокирует повтор идентичного mutating call после success или неизвестного outcome. Identity plugin **1.1.0 развёрнут на VPS**: cron resolver прошёл offline и controlled live gates; Hermes core не менялся. Новых tools нет, inventory/dispatch/discovery = **21/21/21**. Profile также отключает `skills`, `terminal`, `code_execution` и ограничивает turn шестью model iterations. Repo canonical SOUL LF SHA `0ec1eeed95ec90030f1e7e11dd88a1428076cdd44a9a8ffa93c57c4b5726012f`. Migration 003 active на VPS; controlled guard deploy PASS; [Telegram E2E live acceptance evidence](docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md). **Stage 5.3A (шаг 2): в repo реализован user-scoped tool `approve_monthly_plan` — repo tool count 22 (dispatch/discovery 22/22), deployed на VPS остаётся 21 (backend deploy отдельным шагом).** Он не читает и не меняет transactions, детерминированная state machine цикла `draft→…→approved/auto_approved` с идемпотентностью и границами месяца (Asia/Tashkent). Production cron 25/27/28/1 и реальная Ойижон остаются **PLANNED / NOT IMPLEMENTED**.

Этап 1 (VPS + Hermes + Telegram) — **закрыт по решению заказчика (2026-07-12, ТЗ v3.5)**:
- ✅ PostgreSQL healthy (порт 127.0.0.1:5432, init-миграции применены);
- ✅ Hermes Agent v0.18.2 установлен (профиль `mariyam_oyijon` создан; модель `gpt-5.6-luna` через api.n1n.ai — утверждена 2026-07-12, язык 100%/числа 100%; в allowlist сейчас admin + временный test-user «Тест Ойижон», допустимый для e2e-тестов — ТЗ §0.4);
- ✅ На момент Stage 4 acceptance MCP stdio `mariyam_backend` показывал ровно **19 tools**; реальные tool-calls работали, `ensure_user` был идемпотентен. Текущий runtime после Stage 5.1 = 21 tools;
- ✅ canonical SOUL v3.16 установлен; active Mariyam `SKILL.md` отсутствует;
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

**Stage 5.2 — CLOSED / LIVE PASS (v3.16):**
- единственный canonical prompt — `deploy/hermes_profile_mariyam_oyijon/SOUL.md`, LF SHA `3135a12e07529222b9db350ccca07f52d79b76b0ca2b8597bec50a4a0f9a176e`;
- Message 1 и Message 2 подтверждены live; новый платный Telegram/provider test не выполнялся;
- `GENERAL_FAMILY_REPORT` завершается обязательной дословной фразой; `CATEGORY_DETAIL` после двух таблиц завершается без этой фразы и без вопросов; наличие `Жами` правило не меняет;
- identity AC: exact Telegram session → private mapping → `requested=0` → effective test-user; wrapper-маркеры stored prompt и Telegram profile names не являются AC;
- evidence: `docs/EVIDENCE_STAGE_5_2_LIVE_PASS_2026-07-16.md`.

**Stage 5.3 — CLOSED / LIVE PASS (v3.19):**
- product plan, last/weighted average/manual reference prices и immutable snapshot реализованы и active repo/VPS в migration 003 и двух существующих tools;
- `get_monthly_budget_status(price_lookup_items=[...])` возвращает exact last/weighted-average facts до draft и не изменяет БД; неизвестная цена = `null`, разные units не смешиваются;
- category-only разрешён только при omitted `items`; explicit `items=[]` возвращает `INVALID_INPUT` с нулевой DB mutation;
- structured product-draft guard хранит private session-local lookup state максимум 30 минут и требует совпадения item/unit/reference price; duplicate-success breaker не выполняет одинаковую mutation второй раз;
- отдельный `mariyam_stage53_guard` работает после `mariyam_identity_guard 1.0.4`; tool count остаётся 21, Hermes core/backend-router не добавлены;
- Mariyam profile отключает `terminal` и `code_execution`; `execute_code` отсутствует, Hermes core не менялся;
- detailed product report: `Маҳсулот | Режа: миқдор / сумма | Амалда: миқдор / сумма`; отдельной product-колонки остатка нет;
- full offline gates и controlled VPS deploy PASS; migration 003, canonical SOUL и
  guard chain активны. [Stage 5.3 live acceptance evidence](docs/EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md).

**Planned after Stage 5.3 — NOT IMPLEMENTED:**
- Stage 5.3A: cron identity resolver **1.1.0** прошёл offline gates и controlled VPS deploy/probes; approval cycle 25/27/28/1, production mapping/jobs и `approve_monthly_plan` не реализованы; schema cycles подготовлена в migration 003, planned count 22;
- Stage 5.4: researched official utility cabinet, deterministic read-only connector, migration 004, planned count 25;
- Stage 6 extension: recurring obligations, migration 005, Hermes cron, planned final count 27;
- current VPS runtime остаётся **21**; Stage 5.3A–6 не реализованы.

Текущий allowlist: **admin + временный «Тест Ойижон»** (второй аккаунт заказчика, role=oyijon). Реальная Ойижон отсутствует (до handover).

Telegram Ойижон не подключается и не получает сообщений/onboarding/cron до финальной передачи.

## Развёртывание и документация

- `deploy/DEPLOY.md` — инструкция deploy (локальная проверка на Windows + VPS Ubuntu 24.04), команды будущего запуска/отката, секреты, FORBIDDEN-секция (изоляция от Time-Agent).
- `deploy/hermes-mariyam.service` — systemd unit template (`Type=oneshot` + `RemainAfterExit=yes`, без `Restart=`; перезапуск — ответственность docker), запуск через `docker compose up -d`, остановка `docker compose down`, секреты через `/opt/hermes-mariyam-secrets/backend.env`. Назначение: oneshot-шаблон запуска compose/PostgreSQL.
- `deploy/hermes-gateway-mariyam_oyijon.service` — долгоживущий systemd **user-service** Telegram Gateway (`Type=simple`, `Restart=always`), запуск `hermes -p mariyam_oyijon gateway run`. Назначение: постоянный автозапускаемый процесс бота, не смешивать с oneshot-шаблоном PostgreSQL.
- `backend/.env.example` — пример переменных окружения (только placeholder, без реального пароля).
- `tests/run_tests.py` — постоянные тесты (`ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`), запуск из репозитория.
