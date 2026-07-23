# Roadmap

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## MVP этапы (нумерация = ТЗ §21)

| Этап | Что | Статус (2026-07-16) |
|---|---|---|
| 0 | Подготовка данных: доступы, Telegram ID админа (ID Ойижон — перед передачей), voice samples, категории, бюджет | 🟡 частично выполнен — есть ID админа, bot token, VPS, бюджет, voice-samples; ID Ойижон отложен до handover (v3.4) |
| 1 | VPS + Hermes + Telegram: установка, профиль, allowlist, автозапуск. Текущий allowlist: **admin + временный test-user «Тест Ойижон»** для e2e-тестов (§0.4); реальная Ойижон не подключается до handover | ✅ **закрыт по решению заказчика (2026-07-12, ТЗ v3.5)**: Gateway/live reply/allowlist/systemd/linger/reboot PASS; feature-ветка merged в `main`, accepted commits синхронизированы с origin. |
| 1.5 | Финальная передача (pre-handover, v3.4): очистка тест-данных/памяти/cron, добавление ID Ойижон, seed role=oyijon, мягкий onboarding — **только по отдельному разрешению** | ⬜ не начат |
| 2 | Profile prompt Мариям: стиль, язык, onboarding, кириллица | 🟡 runtime использует canonical SOUL v3.16; Stage 5.2 CLOSED, но **PARTIAL живой AC Этапа 2: 8/20 фраз проверены (8/8 кириллица, LATIN_LINES=[]), полный AC НЕ пройден — тест остановлен заказчиком, не из-за FAIL** (см. EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md) |
| 3 | Голос: сквозной STT-тест (голос→Whisper→LLM→БД, числа ≥90%), бюджет; TTS отложен (v3.2) | 🟡 **LLM выбрана: `gpt-5.6-luna` через api.n1n.ai (2026-07-12, язык 100%/числа 100%, резерв deepseek-v4-flash)**; 15 записей Ойижон есть; сквозная STT-точность ещё не измерена |
| 4 | Backend tools (MCP) + БД | ✅ выполнен полностью (2026-07-12): на момент Stage 4 acceptance backend/PostgreSQL и real Hermes имели ровно 19 tools; 4 test markers, systemd verify, real tool-calls и идемпотентный `ensure_user` PASS. Current runtime после Stage 5.1 = 21. |
| 5 | Бухгалтерия: расходы/доходы/отчёты/баланс/исправление/удаление | ✅ **закрыт (2026-07-13):** на момент acceptance identity guard **1.0.3**, runtime tools **19**; Telegram E2E 4/4 PASS; evidence `EVIDENCE_STAGE_5_E2E_2026-07-12.md`. Текущий runtime после Stage 5.1 указан следующей строкой. |
| 5.1 | Аналитика расходов + месячный план (quantity/unit, compare/trend, plan/fact, осторожные советы) | ✅ **CLOSED / LIVE PASS** (ТЗ v3.9 §0.9): migration 002 active; tools/dispatch/discovery **21/21/21**; plugin **1.0.4**; canonical SKILL + skill-protect active; controlled E2E и cleanup PASS. |
| 5.2 | Простые family reports для Ойижон: общий отчёт и фактические product details по просьбе | ✅ **CLOSED / LIVE PASS (v3.16)**; Message 1/2 подтверждены live; final phrase зависит от report type, не от `Жами`; новый платный тест не выполнялся |
| 5.3 | Семейный/product plan, product quantities/amounts, last/weighted average/manual reference price | ✅ **CLOSED / LIVE PASS (v3.19)** ([evidence](EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md)); explicit `items=[]` запрещён с zero mutation, structured product-draft guard и duplicate-success breaker реализованы отдельным profile plugin; controlled VPS deploy PASS, identity plugin 1.0.4/core/tools не изменены, inventory 21 |
| 5.3A | Approval cycle 25/27/28/1, `approve_monthly_plan`, deterministic cron identity | 🟡 **PARTIAL**: identity plugin **1.1.0** deployed (offline/live fail-closed probes + Telegram regression PASS); **backend tools `approve_monthly_plan` + `open_monthly_plan_cycle` реализованы в repo (вариант A 2026-07-24) — repo count 23, deployed 21** (backend deploy — imp02), детерминированные state machine + идемпотентность на schema migration 003; production mapping/jobs и cycle cron 25/27/28/1 не реализованы |
| 5.4 | Official utility cabinets read-only, thresholds/snapshots, daily sync | ⬜ **PLANNED / NOT IMPLEMENTED**; research gate + migration 004; planned count 25 |
| 6 | Hermes cron: reminders, recurring obligations, утро/вечер, новости, погода, намаз | ⬜ **PLANNED / NOT IMPLEMENTED**; migration 005 + 2 tools; planned final count 27; current runtime 21 |
| 7 | Admin reports + safety: отчёт 19:30, alerts, recall 100% | ⬜ не начат — backend-tools готовы, нужен Hermes |
| 8 | Backup/restore/monitoring | ⬜ не начат — `backup_data`/`get_backup_status` намеренно возвращают `NOT_CONFIGURED` |

## Технический долг

- **Очистка test data production-БД** — на момент Блока 6З оставался только `admin`, fixture tables были пусты, backup сохранён; позднее для pre-handover E2E добавлен временный test-user.
- **DB guard** — в `main` (`tests/db_guard.py`); destructive suite на production-БД не запускался.
- **Identity guard на момент Stage 5: 1.0.3** — Stage 5 E2E PASS (см. historical evidence); текущий runtime после Stage 5.1 = 1.0.4.
- **Этап 5.1** — **CLOSED / LIVE PASS** (решение v3.9, сохранено v3.12): runtime 21/1.0.4; migration 002 и skill-protect active; live E2E/cleanup PASS.
- **Этап 5.2** — **CLOSED / LIVE PASS** (v3.16): canonical SOUL LF SHA `3135a12e07529222b9db350ccca07f52d79b76b0ca2b8597bec50a4a0f9a176e`; active Mariyam `SKILL.md` отсутствует; evidence `EVIDENCE_STAGE_5_2_LIVE_PASS_2026-07-16.md`.
- **Stage 5.3 = CLOSED / LIVE PASS (v3.19):** первый повторный E2E остановлен на Message 3 — invalid product aliases привели к category-only save; cleanup PASS. Follow-up запрещает explicit `items=[]`, добавляет structured product-draft guard и duplicate-success breaker с `agent.max_turns=6`; identity plugin остаётся 1.0.4, отдельный guard plugin = 1.0.0. Inventory/dispatch/discovery = 21/21/21; migration 003 и controlled VPS deploy active/PASS; [live acceptance evidence](EVIDENCE_STAGE_5_3_LIVE_PASS_2026-07-23.md).
- **Stages 5.3A–6:** Stage 5.3A cron identity resolver 1.1.0 deployed и controlled probes PASS; approval runtime/production cron, migrations 004/005, utility connector и obligation tools не реализованы; tool count 27 не является runtime.
- **Skill-protect:** active 4/4; постоянные SHA/contract tests остаются обязательными.
- **Тихая блокировка unauthorized решена в ТЗ v3.5** — `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (решение заказчика 2026-07-12, ТЗ §0.5); отдельный gateway-fork не требуется; аудит и merge `d24d01c` в `main` **ВЫПОЛНЕНЫ** (через `dd9261e`).

## Перед handover

- Выполнить Telegram vision smoke: **скрин телефона с вопросом; фото счётчика; скрин коммунального кабинета или квитанции → объяснение узбекской кириллицей**.
- Сначала использовать native image input Hermes и текущую модель.
- Backend и Hermes core не менять.
- Отдельную vision-модель подключать только если текущий model path не принимает изображения.
- Числа подтверждать перед ручным сохранением; при deterministic portal sync подтверждение каждого snapshot не требуется.
- Это будущая проверка и не блокер Stage 5.1.

## Эксплуатационный бюджет v3.10

- Nutrition web search: максимум один на monthly plan cycle, cache 30 дней.
- Utility sync: максимум раз в сутки; tariff verification максимум раз в неделю.
- Paid utility API и continuously running extra agents — только по отдельному разрешению.
- Общий target остаётся **10–15 USD/мес**.

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
- **(v3.4) До финальной передачи бот не пишет реальную Ойижон:** тесты на аккаунте админа или временном test-user (второй аккаунт заказчика, `role=oyijon`, `display_name="Тест Ойижон"`); ID реальной Ойижон добавляется в allowlist только перед handover.
