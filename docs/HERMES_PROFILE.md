# Hermes Profile

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Чек-лист настройки (Этапы 1–2, по порядку)

Предварительно нужны (Этап 0): Telegram Bot Token, **только Telegram ID администратора (Бахриддин ака)**. Telegram ID Ойижон запрашивается **перед финальной передачей** (решение v3.3, ТЗ §0.3, §21) — сейчас его подключать нельзя.

**Статус выполнения (2026-07-14):** шаги 1–9 выполнены — Hermes v0.18.2, профиль создан, allowlist = **admin + временный test-user «Тест Ойижон»** (второй аккаунт заказчика, role=oyijon, ТЗ §0.4), canonical skill установлен, stdio MCP `mariyam_backend` зарегистрирован (`hermes tools` = ровно 21), seed admin идемпотентен, Telegram Gateway `active`/`enabled`, reboot/autostart пройден. **Шаг 10 (AC 20 фраз через Telegram) — PARTIAL 8/20, НЕ закрыт** (8/8 кириллица на выборке; см. EVIDENCE_STAGE_2_PARTIAL_2026-07-12.md).

> **Stage 5.1 status (2026-07-15): CLOSED / LIVE PASS.** VPS/profile = tools **21**, plugin **1.0.4**, migration 002 active, SKILL SHA `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`, skill-protect **4/4**, `tool_progress` off. Controlled E2E и cleanup PASS.

> **ТЗ v3.12:** Stage 5.2 = **LIVE FAIL / FIX REQUIRED**. Controlled E2E выполнен; после rollback profile/runtime остаются на `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`, 21 tools, plugin 1.0.4, migration 002. Repo SKILL остаётся `b3afd9ecfb16a4d4618be898573a84c00ae24a1c3b41e8ae57823912b9ac9d18`; новый fix и повторный live test ещё не выполнялись. Stage 5.3–6 остаются **PLANNED / NOT IMPLEMENTED**; migrations 003/004/005 отсутствуют. Реальная Ойижон не подключалась.

**Модель профиля:** `gpt-5.6-luna` через api.n1n.ai (`provider: custom`, `base_url: https://api.n1n.ai/v1`, ключ `N1N_API_KEY` в профильном `.env`, 600). Резерв: `deepseek/deepseek-v4-flash` (DECISIONS.md, 2026-07-12).

1. Установить Hermes Agent на VPS по официальной документации (репозиторий NousResearch; ссылки — в конце ТЗ). Зафиксировать версию: `hermes --version` — от неё зависят точные имена конфиг-полей ниже.
2. Создать профиль `mariyam_oyijon`.
3. Подключить Telegram Gateway: bot token — только через env/конфиг вне git.
4. Настроить **allowlist**: начальное состояние — только Telegram ID администратора (Бахриддин ака). Для pre-handover E2E уже добавлен второй аккаунт заказчика как временный test-user «Тест Ойижон» (ТЗ §0.4); перед handover он удаляется. Реальный ID Ойижон — только при handover (ТЗ §19). Любой ID вне allowlist не может вызвать agent session / LLM / tools / БД; допустимы short denial или silent block (`PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL`).

5. Установить skill из `skills/mariyam/SKILL.md` в профиль.
5a. **Skill protect (активен в runtime; обязателен при любом переустановочном deploy):** слить в `config.yaml` профиля
    `deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml`:
    - `skills.creation_nudge_interval: 0` — выключить post-turn skill self-improvement;
    - `skills.write_approval: true` — skill_manage не пишет сразу (staging);
    - `display.memory_notifications: "off"` — нет служебных «Self-improvement review» в Telegram;
    - `agent.disabled_toolsets: [skills]` — нет `skill_manage` (skill **читается** через `skills.enabled`).
    Root cause: Hermes `agent/turn_finalizer.py` → `background_review` → `skill_manage` patch SKILL.md.
    После merge — restart gateway. Проверка: `tests/test_mariyam_skill_protection.py`.
6. Зарегистрировать backend как **stdio MCP-сервер** (точный синтаксис сверить с документацией установленной версии Hermes):
   ```yaml
   mcp:
     servers:
       mariyam_backend:
         command: python
         args: ["-m", "backend"]
         cwd: /opt/hermes-mariyam
         env:
           MCP_TRANSPORT: stdio
           DATABASE_URL: ${DATABASE_URL}   # из /opt/hermes-mariyam-secrets/backend.env
   ```
7. Проверить `hermes tools`: текущий VPS runtime должен показывать ровно **21** (список — `TOOLS_CONTRACTS.md`). Выдать tool-permissions.
8. Seed пользователей через `ensure_user` (или SQL из `deploy/DEPLOY.md`). **Обязателен `role=admin` (Бахриддин ака).** Опционально разрешён **временный test-user** для end-to-end тестов: `role=oyijon`, `display_name="Тест Ойижон"`, **только на втором Telegram-аккаунте, контролируемом заказчиком**. **Это НЕ реальная Ойижон** — настоящий ID Ойижон и настоящий seed выполняются только при финальной передаче (ТЗ §0.4, §21). Перед handover временный test-user и его данные удаляются. Записать полученные `user_id` в память профиля; tools принимают именно `user_id`, не telegram_id.
9. Настроить автозапуск Hermes (systemd user-service + `loginctl enable-linger`), проверить подъём после `reboot`.
10. Прогнать AC Этапа 2: 20 тест-фраз → ответы только узбекская кириллица (0 латинских букв).

### Stage 5.2 fix и planned profile gates — не выполнять сейчас

- Stage 5.2: canonical SKILL/tests ещё не приведены к решениям v3.12; изменение, установка в profile, restart и повторный Telegram E2E — только отдельной задачей и по отдельному разрешению.
- Stage 5.3A: до создания cron cycle проверить Hermes v0.18.2 cron identity; trusted job id → private mapping 0600 → internal user id; unknown job fail closed.
- Stage 5.4: utility credentials не помещать в profile/model-visible env; только VPS connector secrets. Hermes browser с открытыми credentials запрещён.
- Vision smoke перед handover сначала через native image input текущего model path; отдельная vision-модель только после фактического FAIL.

> **Запрет до handover (v3.4):** до отдельного финального разрешения заказчика бот **не пишет** реальной Ойижон — любые сообщения, onboarding и cron-доставка в её Telegram запрещены. Тесты (Telegram, allowlist, tools, cron, alerts) выполняются на аккаунте админа или на временном test-user «Тест Ойижон» (второй аккаунт заказчика, ТЗ §0.4).

## Наблюдаемое поведение allowlist (Hermes v0.18.2)

- user-service `hermes-gateway-mariyam_oyijon.service`: `active`, `enabled`, `Restart=always`; `loginctl show-user timeagent -p Linger` = `yes`; после общего `reboot` поднялся автоматически, ровно один процесс.
- allowlist содержит **admin + временный test-user «Тест Ойижон»** (второй аккаунт заказчика, role=oyijon, для e2e-тестов); реальная Ойижон не подключена (до handover).
- Пользователь вне allowlist блокируется адаптером **до** agent session / LLM / tools / БД — `PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL` (решение заказчика 2026-07-12, ТЗ §0.5).
- Точный текст отказа `Кечирасиз, бу шахсий ёрдамчи.` **не обязателен** для Hermes v0.18.2 (принято заказчиком); норма ТЗ (этот файл, шаг 4) остаётся как предпочтительный, но не обязательный вариант.

## Профиль

Основной профиль Hermes: `mariyam_oyijon`.

В профиле живут:

- skill/личность Мариям;
- мягкая память о людях, привычках, предпочтениях;
- onboarding state;
- cron-задачи и напоминания;
- подключение MCP tools;
- выбранные STT/TTS/LLM настройки.

## Стиль Мариям

- Образ: ИИ келинчак.
- Тон: мягкий, уважительный, спокойный, простой.
- Не спорить, не давить, не стыдить, не читать нравоучения.
- Вести к спокойствию, сабру, прощению, аккуратным действиям.
- Для Ойижон не использовать технические термины.

## Язык

Ойижон всегда получает ответы на узбекском кириллицей. Автотест: 0 латинских букв в ответах Ойижон, кроме допустимых чисел/единиц.

Если STT/LLM дал латиницу, Hermes должен привести текст к узбекской кириллице перед отправкой.

Для Бахриддин ака технические сообщения можно писать на русском.

## Память

Hermes memory хранит мягкие факты: родственники, привычки, вкусы, предпочтения, стиль общения, onboarding progress.

Точные данные не хранить только в memory: суммы, даты, отчёты, health notes, alert events, quran progress и usage costs должны идти через backend tools/PostgreSQL.

## Onboarding

Onboarding управляется флагами в Hermes memory:

- `onboarding_step` от 0 до 5;
- `onboarding_last_shown_date`.

Cron раз в день показывает следующий шаг, если он ещё не показан. Если Ойижон пропустила несколько дней, шаг не теряется и не повторяется навязчиво.

Шаги: знакомство/голос, расходы, напоминания, новости/погода/намаз, отчёты/вопросы.
