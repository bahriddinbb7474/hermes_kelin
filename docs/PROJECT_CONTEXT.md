# Project Context

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Цель

Сделать для Ойижон простого и доверительного Telegram-помощника Мариям: голос, расходы, напоминания, Коран, намаз, погода, новости, мягкая поддержка и уведомления Бахриддин ака в важных случаях.

Главное качество проекта — не количество функций, а чтобы Ойижон спокойно пользовалась голосом, без кнопок, страха и сложных инструкций.

## Роли

### Ойижон

- Основной пользователь.
- Женщина 1962 г.р., родом из Хорезмской области, живёт в Ташкенте.
- Язык общения: только узбекский, кириллица.
- Умеет пользоваться Telegram; читать умеет, но глаза болят, поэтому голос приоритетен.
- Обращение: `Ойижон`; приветствие: `Ассалому алайкум, Ойижон`.

### Бахриддин ака

- Администратор и сын Ойижон.
- Получает ежедневный отчёт в 19:30 и важные уведомления.
- Может добавлять напоминания для Ойижон, спрашивать бухгалтерские итоги, менять настройки.
- Для него технические сообщения допустимы на русском.

### Мариям

- ИИ келинчак в Hermes profile `mariyam_oyijon`.
- Общается мягко, уважительно, просто, без давления и нравоучений.
- Не врач, не судья, не строгий бухгалтер.
- Помнит мягкие факты о семье, привычках и предпочтениях, но точные суммы/даты хранит только через tools/storage.

## Канал

Основной и обязательный канал MVP — Telegram. Семейная группа, веб-дашборд, кнопочный UI и CRM в MVP не нужны.

## Где мы сейчас (2026-07-16)

ТЗ: **v3.15**. Этап 5.1 остаётся **CLOSED / LIVE PASS**. Stage 5.2 = **OFFLINE PASS / LIVE PENDING**: controlled live дал Message 1 PASS и Message 2 format-only FAIL; cleanup/rollback PASS. Narrow category-table fix и full effective Telegram prompt contract PASS без truncation. Repo LF SOUL SHA = `a9b584e14d704f08b4778b7928ca71a0cf095394583f769c5e9571097884b4e4`; VPS/profile после rollback остаются на Stage 5.1 SKILL SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`, plugin **1.0.4**, migration 002, inventory 21. Stage 5.3–6 — **PLANNED / NOT IMPLEMENTED**; migrations 003/004/005 отсутствуют. Narrow fix не развёрнут; реальная Ойижон не подключена.

На VPS выполнено (Этап 1, технически):
- PostgreSQL поднят и **healthy** (контейнер `hermes_mariyam_postgres`, порт 127.0.0.1:5432, init-миграции применены).
- Hermes Agent **v0.18.2** (upstream `3b2ef789`) установлен под `timeagent`.
- Профиль `mariyam_oyijon` создан; модель **`gpt-5.6-luna` через api.n1n.ai** (утверждена 2026-07-12, резерв `deepseek-v4-flash`; DECISIONS.md); allowlist содержит **только ID администратора** (до тестов) — в ходе частичного живого теста временно добавлен test-user «Тест Ойижон» (второй аккаунт заказчика, role=oyijon), остаётся для следующих этапов.
- Backend зарегистрирован как **stdio MCP** (`mariyam_backend`): inventory/dispatch/discovery = **21/21/21**, реальные tool-calls работают, `ensure_user` (admin) выполнен идемпотентно.
- В профиль после rollback установлен Stage 5.1 skill SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`; Stage 5.2 repo LF SOUL SHA `a9b584e14d704f08b4778b7928ca71a0cf095394583f769c5e9571097884b4e4` не является live runtime.
- Telegram Gateway установлен как **systemd user-service** (`hermes-gateway-mariyam_oyijon.service`), `active`/`enabled`; `loginctl enable-linger timeagent` выполнен (Блок 6И).
- **Первый живой ответ получен**: бот ответил Бахриддин ака в Telegram на узбекской кириллице (gateway реально принимает/обрабатывает сообщения).
- systemd/автозапуск/reboot проверены: после общего `sudo reboot` Gateway поднялся автоматически (ровно 1 процесс), PostgreSQL healthy, контейнер Time-Agent снова работает, `/opt/time-agent` не трогался (Блок 6И).
- allowlist блокирует чужой аккаунт **до** LLM/tools/БД (`PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL`); точный текст отказа `Кечирасиз, бу шахсий ёрдамчи.` не обязателен для Hermes v0.18.2 (решение заказчика 2026-07-12, ТЗ §0.5).
- На момент Блока 6З после очистки production-БД оставался только `admin`, fixture-таблицы были пусты; позднее для pre-handover E2E добавлен временный test-user.

Статусы и открытые работы:
- **Этап 1 закрыт по решению заказчика (2026-07-12, ТЗ v3.5):** `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (тихая блокировка принята). **Аудит и merge коммита `d24d01c` (systemd unit) в `main` ВЫПОЛНЕНЫ** — вся feature-ветка merged в `main` через `dd9261e`.
- **DB guard (`tests/db_guard.py`) находится в `main`** (merged через `dd9261e`; 16 unit-тестов PASS). Destructive suite на production-БД не запускался.
- **Identity guard 1.0.4** — VPS runtime + Stage 5/5.1 E2E PASS (`TZ/EVIDENCE_IDENTITY_GUARD_2026-07-12.md`, `TZ/EVIDENCE_STAGE_5_E2E_2026-07-12.md`, `EVIDENCE_STAGE_5_1_LIVE_2026-07-13.md`). MCP-prefix, fail-closed barrier, int `telegram_id`, SKILL sentinel `user_id:0`.
- **Этап 5 (бухгалтерия): ЗАКРЫТ (PASS 2026-07-13)** — E2E 4/4; final test **1/12000**, admin **8/768000**; на момент acceptance runtime tools **19**, затем расширены Stage 5.1 до 21.
- **Этап 5.1: CLOSED / LIVE PASS** (решение v3.9, сохранено в **v3.12**) — quantity/unit, by_item, compare/trend, plan/fact и identity подтверждены live; runtime 21 tools / plugin 1.0.4.
- **Stage 5.2: OFFLINE PASS / LIVE PENDING** (v3.15) — previous live: Message 1 PASS, Message 2 category-summary format-only FAIL, cleanup/rollback PASS; narrow table fix offline PASS. Evidence: `EVIDENCE_STAGE_5_2_CATEGORY_TABLE_FIX_2026-07-16.md`.
- **Planned v3.15:** Stage 5.3 product plans + reference price snapshot; Stage 5.3A approval cycle + cron identity gate; Stage 5.4 utility read-only; Stage 6 recurring obligations. Planned tools 21→22→25→27; current runtime не менялся.
- **Prompt/skill protect:** repo LF SOUL assertion = `a9b584e14d704f08b4778b7928ca71a0cf095394583f769c5e9571097884b4e4`; VPS protection после rollback фиксирует legacy runtime SKILL SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`; `tool_progress` off.
- Мариям = бытовой финансовый аналитик; backend считает факты, Hermes объясняет; memory ≠ источник аналитики.
- очистка тестовых данных БД — выполнена, закрепить аудитом;
- **Этап 2 (язык): PARTIAL 8/20, НЕ закрыт** — 8 из 20 фраз проверены (8/8 кириллица, `LATIN_LINES: []`), полный AC (20/20, 0 латиницы) не пройден; тест остановлен заказчиком, не из-за FAIL (см. `docs/TZ/EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md`);
- STT end-to-end — не выполнен;
- cron / safety / backup — не начаты.

Бот НЕ готов для реальной Ойижон: она не подключена до handover. Текущий allowlist: **admin + временный «Тест Ойижон»** (второй аккаунт заказчика, role=oyijon). Реальная Ойижон отсутствует. Telegram Ойижон не получает сообщений/onboarding/cron до финальной передачи (ТЗ §0.3). Статусы по этапам — `ROADMAP.md`; входная точка для исполнителя — `README.md`.
