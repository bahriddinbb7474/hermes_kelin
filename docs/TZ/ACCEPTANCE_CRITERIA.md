# Acceptance Criteria

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Правило сдачи

Каждый этап сдаётся отдельно: цель, изменённые файлы, команды запуска, тесты, результат, commit message. Commit делать только после отдельного разрешения.

## Этапы MVP

### 0. Подготовка данных

Есть Telegram ID администратора (Бахриддин ака), bot token, VPS, подтверждение бюджета 10-15 USD/мес. Есть тест-сет: минимум 10 расходных фраз и 7 критических medical/safety фраз. **Telegram ID реальной Ойижон запрашивается только перед handover (ТЗ §0.3–0.4).** Voice-samples Ойижон (15-20) подготовлены для теста STT.

### 1. VPS + Hermes + Telegram

Бот отвечает в Telegram (аккаунт админа или временный test-user «Тест Ойижон» на втором аккаунте заказчика, ТЗ §0.4). **Негативный тест: любой ID вне allowlist** блокируется и не может читать данные/tools — допустимы два варианта отказа (короткий текст `Кечирасиз, бу шахсий ёрдамчи.` либо тихая блокировка), но в обоих случаях строго обязательно отсутствие agent session / LLM-вызова / tool-вызова / обращения к БД / чтения данных (результат `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL`, ТЗ §0.5). **Telegram реальной Ойижон не подключается и не получает сообщений/onboarding/cron до handover (§0.3–0.4).**

*Статус (2026-07-14): технически подтверждено — живой Telegram-ответ админу (узбекская кириллица, 0 латиницы); allowlist security PASS; systemd user-service `active`/`enabled`; reboot/autostart пройден. **Принято заказчиком по v3.5:** тихая блокировка unauthorized принимается (`PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL`) при обязательном отсутствии agent session/LLM/tool/БД/чтения данных. Stage 5 и Stage 5.1 E2E PASS; текущий runtime = 21 tools / plugin 1.0.4. Этап 1 остаётся **закрытым**; acceptance criteria не изменены и не ослаблены.*

### 1.5. Финальная передача (pre-handover, v3.4)

Выполняется только по отдельному финальному разрешению заказчика: удалён временный test-user «Тест Ойижон» (из allowlist и из БД со связанными записями transactions/health_notes/quran_progress/alert_events/plan_notes); очищены тестовые память/cron; реальный ID Ойижон добавлен в allowlist; выполнен `ensure_user` role=oyijon (seed); пройден мягкий onboarding. Только после этого бот отвечает Ойижон. Перед handover vision smoke: phone screenshot, meter photo, utility cabinet/receipt screenshot; 3/3 ответы узбекской кириллицей. Manual values подтверждены до save; portal sync snapshots не требуют подтверждения каждого значения; отдельная vision-модель только после фактического FAIL current model path.

> **До handover (v3.4):** Этапы 2, 5, 6, 7 проверяются на аккаунте администратора (Бахриддин ака) или временном test-user (`role=oyijon`, `display_name="Тест Ойижон"`) на втором аккаунте заказчика. **Не на Telegram реальной Ойижон** (ТЗ §0.4).

### 2. Skill/личность Мариям

Ответы Ойижон только узбекская кириллица, 0 латинских букв. Мариям корректно представляется, не уходит в русский, не даёт длинных сложных инструкций. Onboarding продолжает шаг после 3 дней пропуска без навязчивых повторов. *Тесты до handover — на аккаунте админа или test-user (§0.4).*

*Статус (2026-07-12): offline-тест языка пройден — 24/24 ответа без латиницы на выбранной LLM (skill установлен, sha256==repo). **Один живой ответ через Telegram подтверждён — кириллица, 0 латиницы.** **Живой AC (Этап 2) = PARTIAL 8/20:** проверено 8 из 20 фраз (Сообщения 1–2, по 4 фразы) со второго аккаунта «Тест Ойижон»; 8/8 ответов — узбекская кириллица, `LATIN_LINES: []`; полный AC (20/20, 0 латиницы) **НЕ завершён**; тест остановлен заказчиком, не из-за FAIL (см. `docs/TZ/EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md`). Этап 2 **НЕ закрыт**.*

### 3. Голос (ТЗ v3.2: TTS отложен)

На расходном voice test-set **сквозная** точность (голос → сохранённая сумма в БД) минимум 90%. Ключевые корни медицинских фраз (ТЗ §10.2) не теряются в транскрипте. При неуверенности всегда переспрос, неверная сумма не сохраняется молча. Прогноз бюджета <= 15 USD/мес или есть план экономии. Критерий «голос Мариям понятен» применяется только при будущем включении TTS.

### 4. Backend tools + БД

Hermes сам вызывает MCP tool и получает ответ. Backend только сохраняет/возвращает. Неверная категория даёт `BAD_CATEGORY`. Время хранится UTC, "сегодня" считается по Asia/Tashkent и проверено на границе суток.

Дополнительно (ТЗ v3.1): один пул соединений (число соединений не растёт после ≥50 вызовов); `ensure_user` идемпотентен; smoke-тест через MCP-слой (`call_tool`) для всех tools включая ошибочные пути; per-tool inputSchema с `required`; docker-образ без `.env`/`.venv`; тестовый предохранитель против боевой БД; systemd unit проходит `systemd-analyze verify`.

**Статус (2026-07-12): этап выполнен полностью.** На момент Stage 4 acceptance backend и real Hermes показывали ровно 19 tools; маркеры `ALL_TOOL_TESTS_PASSED`, `TZ_BOUNDARY_PASSED`, `POOL_STABLE_PASSED`, `MCP_SMOKE_PASSED`, `IMAGE_CLEAN`, `systemd-analyze verify`, real tool-calls и идемпотентный `ensure_user` PASS. Текущий runtime после Stage 5.1 = 21 tools. Сами acceptance criteria Stage 4 не менялись.

### 5. Бухгалтерия

`нон 12 минг, гўшт 180 минг` создаёт две записи, категории верные, итог 192 000. Monthly report сходится с БД. Исправление `гўштни 150 минг қил` меняет запись. `охиргисини ўчир` удаляет. Категории только фиксированные. *Тесты до handover — на аккаунте админа или test-user (§0.4).*

*Статус (2026-07-13): **Этап 5 ЗАКРЫТ (PASS).** Сквозной Telegram AC на «Тест Ойижон»: create 2×192k → report 192k → update meat 150k (total 162k) → delete last (остался нон 12k). admin **+0** (8/768000; ошибочные historical rows не удалялись). Guard 1.0.3: MCP-prefixed tools, sentinel `user_id:0` → effective 20. Evidence: `EVIDENCE_STAGE_5_E2E_2026-07-12.md`. Реальная Ойижон не подключена. Требования AC не ослаблены.*

> **Identity VPS runtime (v3.6 + plugin 1.0.4):** детерминированный binding через `mariyam_identity_guard` (не LLM). Исторические FAIL: `EVIDENCE_STAGE5_E2E_FAIL_2026-07-12.md` (не удалять). Skill-protect active 4/4; Stage 5.1 identity live PASS.

### 5.1. Аналитика расходов и месячный план (v3.9 status; требования v3.7)

**Статус: CLOSED / LIVE PASS.** Migration 002 active; tools/dispatch/discovery **21/21/21**; plugin **1.0.4**; canonical SKILL и skill-protect active. Controlled E2E подтвердил все AC, identity и узбекскую кириллицу; cleanup восстановил DB baseline. Evidence: `../EVIDENCE_STAGE_5_1_LIVE_2026-07-13.md`.

AC (измеримые):
1. Отчёт показывает основные группы расходов.
2. Питание раскрывается по товарам (`by_item`).
3. На товар: сумма, purchase_count, quantity (если было указано).
4. Текущий месяц точно сравнивается с предыдущим.
5. Ряд ≥3 месяцев при наличии данных (`monthly_series`).
6. Можно сохранить бюджет следующего месяца по категориям.
7. План/факт совпадает с БД.
8. При отсутствии quantity Мариям не придумывает количество.
9. Совет по опту без выдуманной цены/гарантированной экономии.
10. Все ответы Ойижон — узбекская кириллица.
11. Identity guard на все новые user-scoped tools (`set_monthly_budget`, `get_monthly_budget_status`).
12. Реальная Ойижон до handover не подключается.

### 5.2. Простые семейные отчёты — CLOSED / LIVE PASS

**Общий отчёт:**

1. Показывает plan / spent / remaining по группам из точных tool-данных.
2. Допускает короткое естественное вступление и строку `Жами`; наличие `Жами` не определяет правило завершения.
3. Допускает `Сарфланди` или `Сарфлангани`, `Қолди` или `Қолгани`.
4. Отрицательный остаток допустим, если превышение рядом объяснено простыми словами.
5. По типу `GENERAL_FAMILY_REPORT` после отчёта обязательна точная финальная фраза: `Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб чиқамиз. Маълумотлар тайёр.` Её нельзя пропускать или перефразировать.
6. Товарные детали автоматически не показываются.

**Подробный отчёт по одной группе:**

1. Сначала показывает summary выбранной категории только отдельной Markdown-таблицей `Харажат гуруҳи | Режа | Сарфлангани | Қолгани`, минимум с одной строкой выбранной категории; маркированный/list summary запрещён.
2. Сразу после summary-таблицы показывает таблицу фактических товаров: `Маҳсулот | Миқдор | Сарфлангани`.
3. Количество показывается только при наличии данных; missing quantity = `—` или поле не показывается; количество не угадывается.
4. User-facing units: `кг / г / л / мл / та / қадоқ`; canonical units в tools/БД остаются `kg / g / l / ml / pcs / pack`.
5. Product plan в Stage 5.2 не показывается.
6. JSON, tool names, technical fields и traces отсутствуют; суммы берутся только из tools.
7. Строка `Жами` допустима. После таблиц ответ завершается без финальной фразы общего отчёта и без вопросов.

Stage 5.2 live evidence зафиксировано для SOUL SHA `3135a12e07529222b9db350ccca07f52d79b76b0ca2b8597bec50a4a0f9a176e`; Stage 5.3 repo SOUL SHA = `856fd7f37cd476e5eeae933c2c6cf82ec5fb0ed89c0410d30a74480188cd6c30`. Message 1 и Message 2 подтверждены live; новый платный тест не выполнялся. Wrapper-маркеры stored prompt не являются AC. Telegram profile names не являются identity: identity AC — только `exact Telegram session → private mapping → requested=0 → effective=test-user`. Evidence: `../EVIDENCE_STAGE_5_2_LIVE_PASS_2026-07-16.md`. Реальная Ойижон не подключена.

### 5.3. Семейный и продуктовый план — OFFLINE PASS / LIVE PENDING

1. Семь вопросов/шагов задаются последовательно; save только после подтверждения draft.
2. Product report содержит summary категории, затем ровно `Маҳсулот | Режа: миқдор / сумма | Амалда: миқдор / сумма`; старый пятиколоночный формат и отдельная product-колонка остатка отсутствуют; минимум planned quantity или planned amount.
3. Один nutrition web search на cycle, cache 30 дней, WHO/FAO/официальный Минздрав Узбекистана, source+date.
4. Нет diagnosis/treatment diet/universal meat norm; medical restrictions → согласовать с врачом; exact quantities только после family confirmation.
5. Последняя цена используется для следующего плана по умолчанию; явный запрос возвращает средневзвешенную цену; разрешён manual override. Без quantity unit price не считается, разные units не смешиваются.
6. Repo migration 003 идемпотентна; product rows сохраняются атомарно, actuals берутся только из transactions, price snapshot immutable; inventory/dispatch/discovery = 21/21/21.
7. Unknown = `null` в backend и `—`/`айтилмаган` в ответе; количество и цену не угадывать; `pcs → та`.
8. Full offline suite, ruff, compileall и diff checks PASS; VPS остаётся на migration 002, поэтому LIVE PASS не объявляется.

### 5.3A. Утверждение 25/27/28/1 — PLANNED / NOT IMPLEMENTED

1. 25: один draft/одно сообщение; 27: один repeat без duplicate; 28 число: `waiting_admin`, с 28 числа максимум одно admin reminder/day до approve либо начала следующего месяца; 1: safe auto-approve/copy/fail path до утра.
2. Все шесть statuses валидируются; empty/corrupt plan не auto-approved.
3. `approve_monthly_plan` не меняет transactions и действует только до начала планового месяца; Oyijon self-only; admin narrow target/future-month allowlist. После начала месяца approval-cycle закрыт; активный plan корректирует только Oyijon self-only; admin edit текущего plan в v3.10 не заявлен.
4. Cron identity test: trusted job maps deterministically; unknown job fail closed, downstream=0; Hermes core/backend router unchanged.
5. Cycles schema подготовлена migration 003; tool/runtime/status transitions/cron реализуются в будущем; planned count 22, current runtime 21.

### 5.4. Коммунальные кабинеты read-only — PLANNED / NOT IMPLEMENTED

1. Pre-code report закрывает 9 portal gates; official API/export приоритетнее connector; credentials никогда не доступны LLM.
2. Read-only structured fields совпадают с кабинетом и имеют sync date; writes/payments/cards невозможны; account masked; drift fail closed.
3. Threshold задан admin; reminders 0/2-day cadence и stop after top-up; no threshold breach = no Telegram message.
4. Daily sync max 1; tariff check max weekly; two sync failures → admin only.
5. Migration 004 + 3 user-scoped tools реализованы в будущем; planned count 25, current runtime 21. `set_utility_threshold`: Oyijon self-only; admin narrow cross-target только `allowed_target_user_ids` и только threshold, без portal/payment/settings/transactions. Газ/вода — только после подтверждения.

### 6. Напоминания, обязательные платежи, новости, погода, намаз

`эртага 10 да эслат` приходит вовремя через Hermes cron. Вечерний вопрос не повторяется навязчиво. Новости 3-5 пунктов, кириллица, без тревоги. Погода и намаз корректны для Ташкента. *Cron Ойижон до handover тестируется только на втором аккаунте заказчика через test-user (§0.4); реальной Ойижон не отправляется.*

**v3.10 obligation extension — PLANNED / NOT IMPLEMENTED:** internet/loan/tax/utility/other; reminder before/due/one overdue; stop after paid; next date from approved repeat rule; no duplicate expense. Migration 005 + `upsert_recurring_obligation`/`get_recurring_obligations`; оба tools — Oyijon self-only, admin narrow cross-target только `allowed_target_user_ids`, без прав на transactions; planned final count 27, current runtime 21; storage не scheduler.

### 7. Админ-отчёты и safety

Каждая критическая фраза и 3-5 перефразировок дают мягкий ответ Ойижон, уведомление админу и `alert_event`. Recall уведомления админа 100% на тест-сете. Отчёт 19:30 сходится с БД и без лишних интимных деталей. *Safety-тесты до handover — на аккаунте админа или test-user (§0.4).*

### 8. Backup, restore, monitoring

Зашифрованный backup уходит в Google Drive. Restore в чистое окружение восстановил известный расход и число строк. Бот поднимается после reboot. Админ получает heartbeat и уведомление при падении.

Дополнительно (ТЗ v3.1): до завершения этапа `backup_data`/`get_backup_status` возвращают `NOT_CONFIGURED`, не ложный успех.

### 9. После MVP: религиозный RAG

Ответы опираются на доверенный источник. Без источника Мариям не выдумывает; спорное уточняет или эскалирует админу.
