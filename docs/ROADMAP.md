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
| 5 | Бухгалтерия: расходы/доходы/отчёты/баланс/исправление/удаление | ✅ **закрыт (2026-07-13):** identity guard **1.0.3** (MCP-prefix + fail-closed barrier + int `telegram_id` + SKILL sentinel `user_id:0`); VPS live; Telegram E2E 4/4 PASS на «Тест Ойижон» (create/report/update/delete; effective always 20; admin +0). Evidence: `EVIDENCE_STAGE_5_E2E_2026-07-12.md`, `EVIDENCE_IDENTITY_GUARD_2026-07-12.md`. Исторические FAIL сохранены (`EVIDENCE_STAGE5_E2E_FAIL_…`). Final DB: test **1/12000**, admin **8/768000** (ошибочные rows не удалялись). Реальная Ойижон не подключена. |
| 6 | Hermes cron: напоминания, утро/вечер, новости, погода, намаз | ⬜ не начат — см. `CRON_AND_REMINDERS.md` |
| 7 | Admin reports + safety: отчёт 19:30, alerts, recall 100% | ⬜ не начат — backend-tools готовы, нужен Hermes |
| 8 | Backup/restore/monitoring | ⬜ не начат — `backup_data`/`get_backup_status` намеренно возвращают `NOT_CONFIGURED` |

## Технический долг

- **Очистка тестовых данных production-БД** — ВЫПОЛНЕНА (Блок 6З: остался только `admin`, fixture-таблицы пусты, backup сохранён); требует закрепления финальным аудитом.
- **DB guard** — в `main` (`tests/db_guard.py`); destructive suite на production-БД не запускался.
- **Identity guard 1.0.3** — VPS runtime + Stage 5 E2E PASS (см. evidence). Локальный commit после Stage 5 — отдельно; push `origin/main` — отдельное разрешение.
- **КРИТИЧЕСКИЙ ОТКРЫТЫЙ БЛОКЕР:** self-improvement/curator **изменил runtime SKILL.md** после E2E msg4 (sha drift; служебное сообщение в Telegram). SKILL восстановлен (`dfc7e327…`). **Следующие live-этапы и handover запрещены** до минимального фикса самопереписывания security-critical skill.
- **Тихая блокировка unauthorized решена в ТЗ v3.5** — `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (решение заказчика 2026-07-12, ТЗ §0.5); отдельный gateway-fork не требуется; аудит и merge `d24d01c` в `main` **ВЫПОЛНЕНЫ** (через `dd9261e`); push в `origin/main` остаётся отдельным действием.

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
