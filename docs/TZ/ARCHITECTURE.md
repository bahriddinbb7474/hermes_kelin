# Architecture

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

**Статус v3.17:** архитектура Hermes-first не меняется. Stage 5.1 и Stage 5.2 — **CLOSED / LIVE PASS**. Stage 5.3 — **OFFLINE PASS / LIVE PENDING**: repo canonical LF SOUL SHA `856fd7f37cd476e5eeae933c2c6cf82ec5fb0ed89c0410d30a74480188cd6c30`, migration 003 и расширенные два tools готовы; inventory = 21. VPS остаётся на 21 tools / plugin 1.0.4 / migration 002 и предыдущем deployed SOUL. Stage 5.3A–6 — **PLANNED / NOT IMPLEMENTED**; migrations 004/005 отсутствуют; реальная Ойижон не подключалась.

## Принцип Hermes-first

Hermes Agent — единственный "мозг" проекта: понимает речь, ведёт стиль Мариям, хранит мягкую память, выбирает когда вызвать tool, работает с Telegram, voice, cron и LLM.

Backend — только тонкий слой MCP tools/storage: принимает уже разобранные данные, валидирует, сохраняет и возвращает точные факты.

## Поток

```text
Telegram (Ойижон / Бахриддин ака)
  -> Hermes Telegram Gateway + allowlist
  -> Hermes Profile: mariyam_oyijon
       memory, canonical SOUL, LLM, STT/TTS, cron
  -> Hermes profile plugin `mariyam_identity_guard`   (repo/VPS 1.0.4, узкий слой)
       tool_execution middleware: current session
       -> persisted Telegram source -> private mapping -> internal users.id
       (не router, не второй мозг; только детерминированная привязка sender)
  -> MCP backend tools
  -> PostgreSQL
  -> encrypted backup через rclone/Google Drive
```

> Узкий слой `mariyam_identity_guard` (v3.6) стоит **между** профилем Hermes и MCP backend. Он **не является router-ом и не является вторым мозгом**: плагин только детерминированно связывает Telegram sender с internal `users.id` и переписывает `user_id` в аргументах user-scoped tools до вызова backend. Смысл сообщения, категория расхода, сумма и решение вызвать tool остаются в Hermes. Backend остаётся тонким tools/storage (ТЗ §0.6, §19, §20).

## Граница Hermes/backend

Hermes делает:

- общение с Ойижон и админом;
- понимание бытовых фраз и голоса;
- классификацию расходов, нормализацию сумм, **item_name_normalized / quantity / unit** (Stage 5.1 live verified);
- формулировку всех ответов, отчётов и **осторожных финансовых советов** (не выдумывать цены/экономию);
- cron: утро, вечер, новости, 19:30, onboarding, heartbeat;
- веб-поиск для новостей и фактических вопросов.
- **Stage 5.3:** один nutrition web search на plan cycle (WHO/FAO/официальный Минздрав Узбекистана), cache 30 дней; источник и дата в ответе; save только после подтверждения draft.
- **Planned Stage 5.3A/5.4/6:** orchestration и расписание делает только Hermes cron; user-scoped cron identity детерминирована до MCP.

Backend делает:

- сохраняет расходы, доходы, прогресс Корана, health notes, alerts, plan notes, usage costs;
- **Stage 5.1 live implementation:** хранит quantity/unit; агрегирует by_category / by_item / compare / trend / plan-fact;
- возвращает отчётные числа и факты (**без прозы и советов**);
- валидирует категории, суммы, валюты, роли, даты, units;
- делает backup/status/heartbeat данные.
- **Stage 5.3 data/storage:** product plan items, actuals из transactions и immutable price snapshot; cycles пока только подготовленная schema. Planned data/storage: utility connector snapshots и recurring obligations; connector не понимает сообщения, не пишет прозу и не выполняет payments.

LLM memory **не** источник финансовой аналитики.

## Planned v3.10 extensions — не current runtime

```text
Hermes cron job
  -> trusted cron job id
  -> private mapping mode 0600
  -> internal users.id
  -> identity guard
  -> user-scoped MCP tool
```

Unknown cron job блокируется fail closed до downstream tool. Utility access: official API → official export/endpoint → узкий deterministic read-only connector. Credentials остаются в VPS secrets и не видны LLM. Hermes browser с открытыми credentials запрещён. Hermes core, backend router/orchestrator и backend scheduler не добавляются.

Planned tool progression: Stage 5.3 = 21 (расширение существующих contracts), Stage 5.3A = 22, Stage 5.4 = 25, Stage 6 extension = 27. **Текущий runtime = 21.**

Stage 5.3 сохраняет reference price snapshot в `monthly_budget_items`: backend считает last/weighted average из transactions и сохраняет выбранный `last / average / manual`; Hermes объясняет и спрашивает подтверждение. Отдельная price table и ценовая логика в LLM memory не создаются.

## Запрещённые backend-heavy решения

- Message Router, Intent Classifier, LLM Orchestrator на backend.
- Парсинг смысла фраз, намерений или категорий на backend.
- Backend-формирование прозы отчётов.
- Отдельный scheduler-сервис.
- Хранение точных данных только в LLM memory.
- Второй "мозг" рядом с Hermes.

## Развёртывание

На VPS: Hermes Agent, профиль `mariyam_oyijon`, Telegram Gateway, MCP backend tools, PostgreSQL, rclone backup, systemd автозапуск, логи с ротацией.

Транспорт MCP (ТЗ §16): по умолчанию **stdio** — Hermes запускает backend как subprocess, docker compose используется только для PostgreSQL. HTTP — запасной вариант: только localhost и только через поддерживаемый session-manager MCP SDK. Backend держит один пул соединений на процесс.
