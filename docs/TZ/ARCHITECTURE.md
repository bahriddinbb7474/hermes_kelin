# Architecture

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

**Статус v3.8:** архитектура не менялась. Stage 5.1 repo/worktree — **OFFLINE PASS** (21 tools, plugin 1.0.4); текущий VPS runtime — **LIVE PENDING** (19 tools, plugin 1.0.3).

## Принцип Hermes-first

Hermes Agent — единственный "мозг" проекта: понимает речь, ведёт стиль Мариям, хранит мягкую память, выбирает когда вызвать tool, работает с Telegram, voice, cron и LLM.

Backend — только тонкий слой MCP tools/storage: принимает уже разобранные данные, валидирует, сохраняет и возвращает точные факты.

## Поток

```text
Telegram (Ойижон / Бахриддин ака)
  -> Hermes Telegram Gateway + allowlist
  -> Hermes Profile: mariyam_oyijon
       memory, skill, LLM, STT/TTS, cron
  -> Hermes profile plugin `mariyam_identity_guard`   (repo 1.0.4 / VPS 1.0.3, узкий слой)
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
- классификацию расходов, нормализацию сумм, **item_name_normalized / quantity / unit** (Stage 5.1 offline ready);
- формулировку всех ответов, отчётов и **осторожных финансовых советов** (не выдумывать цены/экономию);
- cron: утро, вечер, новости, 19:30, onboarding, heartbeat;
- веб-поиск для новостей и фактических вопросов.

Backend делает:

- сохраняет расходы, доходы, прогресс Корана, health notes, alerts, plan notes, usage costs;
- **Stage 5.1 repo implementation:** хранит quantity/unit; агрегирует by_category / by_item / compare / trend / plan-fact;
- возвращает отчётные числа и факты (**без прозы и советов**);
- валидирует категории, суммы, валюты, роли, даты, units;
- делает backup/status/heartbeat данные.

LLM memory **не** источник финансовой аналитики.

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
