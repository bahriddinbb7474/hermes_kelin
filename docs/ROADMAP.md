# Roadmap

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## MVP этапы (нумерация = ТЗ §21)

| Этап | Что | Статус (2026-07-12) |
|---|---|---|
| 0 | Подготовка данных: доступы, Telegram ID админа (ID Ойижон — перед передачей), voice samples, категории, бюджет | 🟡 частично выполнен — есть ID админа, bot token, VPS, бюджет, voice-samples; ID Ойижон отложен до handover (v3.4) |
| 1 | VPS + Hermes + Telegram: установка, профиль, allowlist, автозапуск. Текущий allowlist: **admin + временный test-user «Тест Ойижон»** для e2e-тестов (§0.4); реальная Ойижон не подключается до handover | ✅ **закрыт по решению заказчика (2026-07-12, ТЗ v3.5)**: Gateway работает (user-systemd, active/enabled, 1 процесс); ✅ live Telegram-ответ админу (кириллица); ✅ allowlist security проверена (PASS_SECURITY / ACCEPTED_SILENT_DENIAL — тихая блокировка принята); ✅ systemd user-service; ✅ enable-linger; ✅ reboot/autostart пройден; ✅ **feature-ветка merged локально в `main` (`dd9261e`) — аудит и merge Этапа 1 ВЫПОЛНЕНЫ** (push в `origin/main` ещё НЕ выполнен) |
| 1.5 | Финальная передача (pre-handover, v3.4): очистка тест-данных/памяти/cron, добавление ID Ойижон, seed role=oyijon, мягкий onboarding — **только по отдельному разрешению** | ⬜ не начат |
| 2 | Skill Мариям: стиль, язык, onboarding, кириллица | 🟡 skill установлен в профиль (enabled, sha256==repo); offline-тест языка пройден (24/24 кириллица на выбранной LLM); **один живой ответ кириллицей через Telegram подтверждён**; **PARTIAL живой AC: 8/20 фраз проверены (8/8 кириллица, LATIN_LINES=[]), полный AC (20/20, 0 латиницы) НЕ пройден — тест остановлен заказчиком, не из-за FAIL** (см. EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md) |
| 3 | Голос: сквозной STT-тест (голос→Whisper→LLM→БД, числа ≥90%), бюджет; TTS отложен (v3.2) | 🟡 **LLM выбрана: `gpt-5.6-luna` через api.n1n.ai (2026-07-12, язык 100%/числа 100%, резерв deepseek-v4-flash)**; 15 записей Ойижон есть; сквозная STT-точность ещё не измерена |
| 4 | Backend tools (MCP) + БД | ✅ выполнен полностью (2026-07-12): backend tools + PostgreSQL (19 tools, 4 тест-маркера, ТЗ v3.1 AC); systemd verify пройден; stdio MCP зарегистрирован в реальном Hermes, `hermes tools` = ровно 19, реальные tool-calls работают, `ensure_user` идемпотентен |
| 5 | Бухгалтерия: расходы/доходы/отчёты/баланс/исправление/удаление | ✅ **закрыт (2026-07-13):** на момент acceptance identity guard **1.0.3**, runtime tools **19**; Telegram E2E 4/4 PASS; evidence `EVIDENCE_STAGE_5_E2E_2026-07-12.md`. Текущий runtime после Stage 5.1 указан следующей строкой. |
| 5.1 | Аналитика расходов + месячный план (quantity/unit, compare/trend, plan/fact, осторожные советы) | ✅ **CLOSED / LIVE PASS** (ТЗ v3.9 §0.9): migration 002 active; tools/dispatch/discovery **21/21/21**; plugin **1.0.4**; canonical SKILL + skill-protect active; controlled E2E и cleanup PASS. |
| 6 | Hermes cron: напоминания, утро/вечер, новости, погода, намаз | ⬜ не начат — см. `CRON_AND_REMINDERS.md` |
| 7 | Admin reports + safety: отчёт 19:30, alerts, recall 100% | ⬜ не начат — backend-tools готовы, нужен Hermes |
| 8 | Backup/restore/monitoring | ⬜ не начат — `backup_data`/`get_backup_status` намеренно возвращают `NOT_CONFIGURED` |

## Технический долг

- **Очистка тестовых данных production-БД** — ВЫПОЛНЕНА (Блок 6З: остался только `admin`, fixture-таблицы пусты, backup сохранён); требует закрепления финальным аудитом.
- **DB guard** — в `main` (`tests/db_guard.py`); destructive suite на production-БД не запускался.
- **Identity guard на момент Stage 5: 1.0.3** — Stage 5 E2E PASS (см. historical evidence); текущий runtime после Stage 5.1 = 1.0.4.
- **Этап 5.1** — **CLOSED / LIVE PASS** (ТЗ v3.9): runtime 21/1.0.4; migration 002, canonical SKILL и skill-protect active; live E2E/cleanup PASS.
- **Skill-protect:** active 4/4; постоянные SHA/contract tests остаются обязательными.
- **Тихая блокировка unauthorized решена в ТЗ v3.5** — `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (решение заказчика 2026-07-12, ТЗ §0.5); отдельный gateway-fork не требуется; аудит и merge `d24d01c` в `main` **ВЫПОЛНЕНЫ** (через `dd9261e`).

## Перед handover

- Выполнить отдельный Telegram vision smoke: **фото/скриншот → объяснение узбекской кириллицей**.
- Сначала использовать native image input Hermes и текущую модель.
- Backend и Hermes core не менять.
- Отдельную vision-модель подключать только если текущий model path не принимает изображения.
- Это будущая проверка и не блокер Stage 5.1.

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
