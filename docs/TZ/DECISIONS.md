# Decisions

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Утверждённые решения

- **Hermes-first:** Hermes — единственный мозг проекта.
- **Backend только tools/storage:** backend не классифицирует intent, не пишет отчёты, не планирует расписания.
- **Telegram основной канал:** MVP строится вокруг Telegram Gateway и allowlist.
- **Ойижон получает узбекскую кириллицу:** ответы Ойижон не на русском и не латиницей.
- **Cron только Hermes:** отдельный scheduler/backend-cron сервис не создаётся.
- **Отчёты текстом пишет Hermes:** backend отдаёт только факты и числа через `get_admin_report_data`.
- **Расходы можно исправлять и удалять:** обязательны update/delete для последней и выбранной записи.
- **Религиозный RAG после MVP:** в MVP только осторожные простые ответы, прогресс Корана и намаз; не давать фатвы из головы.
- **Медицина без диагноза:** Мариям не врач, не назначает и не отменяет лекарства; при тревожных фразах уведомляет Бахриддин ака.
- **budget 10–15 USD/мес:** STT/TTS/LLM выбирать и настраивать с учётом этого бюджета.

## Зафиксированные ограничения MVP

- Второй экстренный контакт не добавляется.
- Автоматический жёсткий совет звонить 103 не включается; Мариям мягко советует обратиться за медпомощью.
- Сложный medication-модуль не делается без назначенного списка лекарств.
- Семейная группа, веб-дашборд, кнопочный UI и CRM не входят в MVP.

## Решения v3.1 (аудит 2026-07-09, реализованы)

- **Транспорт MCP — stdio по умолчанию на VPS:** Hermes запускает `python -m backend` как subprocess; docker compose поднимает только PostgreSQL. HTTP — запасной вариант, только 127.0.0.1, только через `StreamableHTTPSessionManager`.
- **Один пул соединений на процесс** — кэш в `backend/config.py`; создание пула на вызов запрещено.
- **Fail fast без секретов:** нет `DATABASE_URL` → процесс падает сразу; fallback-креды запрещены везде.
- **`ensure_user`** — 19-й tool: идемпотентный seed пользователей по telegram_id; роль после создания не перезаписывается.
- **Честные заглушки:** нереализованное возвращает `NOT_CONFIGURED` (backup до Этапа 8).
- **Per-tool inputSchema с `required`** — общая схема на все tools запрещена.
- **Postgres публикуется на 127.0.0.1:5432** (нужно stdio-backend'у на хосте); на VPS порт проверять на конфликт, переопределение через `POSTGRES_HOST_PORT`.
- **Keyword-список алертов — узкий:** только корни срочных фраз ТЗ §10.2; бытовые слова запрещены.
- **Тесты имеют предохранитель** от запуска против боевой БД (`TRUNCATE`).

## Решения заказчика (2026-07-10)

- **STT/LLM пайплайн (Этап 3):** Whisper выступает как «уши» — передаёт сырой текст (любой язык/латиница) в LLM в фоне; LLM интерпретирует смысл и отвечает узбекской кириллицей. Критерий приёмки Этапа 3: сквозная точность ≥90% меряется **голос → сохранённая сумма в БД** (не по качеству транскрипта). Если на 15 записях Ойижон сквозная точность <90% — возвращаемся к сравнению кандидатов STT (Gemini-аудио через OpenRouter, ElevenLabs free, Groq). Железное правило: при сомнении в сумме/числе — переспросить, не сохранять молча.
- **Голосовые ответы отключены (TTS off):** решение заказчика, зафиксировано в ТЗ v3.2 (§0.2, §6.1, §6.3). Мариям отвечает Ойижон **только текстом** (узбекская кириллица). Голосовой *ввод* (voice message) остаётся — принимается и транскрибируется Whisper как обычно. TTS включим позже, только когда выберем приличный узбекский женский/мягкий голос.

## Решения заказчика (2026-07-11) — не беспокоить Ойижон незавершённым продуктом

**Обоснование:** проект пока не внутренне готов (финальная LLM не выбрана, skill/cron/alerts не прогнаны на живом боте, модель `tencent/hy3:free` — временная тестовая). Подключать пожилую Ойижон к незавершённому продукту нельзя: риск путаницы, некорректных ответов и потери доверия.

- **Telegram Ойижон не подключается до финальной готовности.** Запрещены любые сообщения, onboarding и cron-доставка в её Telegram до отдельного финального разрешения заказчика.
- **Все тесты — только на аккаунтах заказчика.** Тесты Telegram, allowlist, tools, cron и alerts выполняются через Telegram Бахриддин ака. Второй пользователь для теста (если нужен) — второй Telegram-аккаунт, контролируемый заказчиком.
- **Этап 0:** сейчас обязателен только Telegram ID администратора. Telegram ID Ойижон запрашивается перед финальной передачей.
- **На дату этого решения (2026-07-11) allowlist содержал только ID администратора**; позже решением v3.4 добавлен временный test-user для pre-handover E2E.
- **`tencent/hy3:free` — временная тестовая модель**, не финальный выбор. Финальная LLM выбирается после узбекского мини-теста.
- **Финальная передача:** перед подключением Ойижон — очистить тестовые данные/память/cron, добавить реальный ID Ойижон в allowlist, выполнить `ensure_user` role=oyijon (seed) и мягкий onboarding. Только после этого бот начинает отвечать Ойижон (ТЗ §0.3, §21).

## Решения заказчика (2026-07-11, v3.4) — второй аккаунт для тестов до handover

**Обоснование:** для полноценного end-to-end тестирования (cron, skill, safety, бухгалтерия) нужен второй пользователь-«Ойижон», но подключать реальную Ойижон к незавершённому продукту нельзя (решение v3.3).

- **Разрешён второй Telegram-аккаунт, контролируемый заказчиком** (не реальная Ойижон) для полного тестирования до handover.
- **Seed:** обязателен `role=admin` (Бахриддин ака). Опционально разрешён **временный test-user**: `role=oyijon`, `display_name="Тест Ойижон"`, **только на втором аккаунте заказчика**. Это НЕ реальная Ойижон.
- **Настоящий ID Ойижон и настоящий seed — только при handover** (ТЗ §0.4, §21). Перед handover временный test-user, его данные, тестовая память и cron удаляются.
- **Реальной Ойижон отправка строго запрещена** до отдельного финального разрешения. На основном аккаунте админа остаются admin-report (19:30) и heartbeat (23:00).

## Решения заказчика (2026-07-12) — LLM выбрана; бюджетное правило

- **Рабочая модель профиля: `gpt-5.6-luna` через api.n1n.ai** (Hermes `provider: custom`, `base_url: https://api.n1n.ai/v1`, ключ `N1N_API_KEY` в профильном `.env`, 600). У заказчика скидка на n1n.
- **Основание:** валидация 24 прогона (12 фраз × 2, тест-сет Блока 6В): язык — 100% (0 латинских букв во всех ответах), числа — 100% по смыслу. Модель пишет суммы словами («12 минг сўм») — для Ойижон допустимо и даже удобнее; нормализация чисел для tools проверяется отдельно сквозным тестом Этапа 3. Стабильность формулировок низкая — не критично (смысл и язык стабильны).
- **Резерв:** `deepseek/deepseek-v4-flash` — спот-тест 4/4 (язык 100%, числа 100%), дешёвая без скидки. Использовать, если n1n/скидка недоступны.
- **`tencent/hy3:free` непригодна** для продакшена (язык 50–58%); few-shot примеры слабую модель не спасают — few-shot в SKILL §2 остаётся как страховка для средних моделей.
- **Пост-обработки выхода в Hermes v0.18.2 нет** (только redact секретов) — гарантия кириллицы держится на модели + skill; автотест «0 латиницы» обязателен в AC каждого этапа с живым ботом.
- **Бюджетное правило (после инцидента ~$2 на повторных прогонах):** любые платные API-вызовы — только по утверждённому заказчиком списку моделей и жёсткому лимиту вызовов; в раннерах обязательны счётчик с `sys.exit` и `retry=0`; факт расхода сверяется с дашбордом провайдера в каждом отчёте.

## Решения заказчика (2026-07-12) — тихая блокировка unauthorized (ТЗ → v3.5)

**Обоснование (зачем):** безопасность уже доказана (внешний sender блокируется адаптером до LLM/tools/БД); исправление потребовало бы вмешательства в upstream Gateway Hermes v0.18.2.

- **Зачем:** безопасность уже доказана; исправление потребовало бы вмешательства в upstream Gateway.
- **Риск:** посторонний пользователь не получает объяснения (тихий отказ).
- **Цена:** нулевая стоимость реализации; без отдельного gateway-fork и его поддержки.
- **Эффект:** Этап 1 принимается по функциональной безопасности (`PASS_SECURITY` / `ACCEPTED_SILENT_DENIAL`); разработка следующих этапов не блокируется; аудит и merge в `main` остаются отдельными действиями.

Короткий текст `Кечирасиз, бу шахсий ёрдамчи.` остаётся предпочтительным, но для Hermes v0.18.2 не обязателен. Решение не разрешает доступ unauthorized-пользователю и не ослабляет allowlist (ТЗ §0.5, §19).

## Решения заказчика (2026-07-12) — процесс документации

- **Не создавать дублирующие папки документации** (экспортные копии, CHAT_SOURCES, backup-copy).
- **Единственный рабочий набор документов находится в репозитории**; репозиторий — единственный источник файлов проекта.
- **Для обновления источников чата файлы выбираются напрямую из актуального repo/worktree** (свежие незакоммиченные или последний коммит — по указанию заказчика).
- **Экспортные копии и CHAT_SOURCES запрещены** (закреплено в `docs/ARCHITECT_PROMPT.md`, правило 2).

## Решения заказчика (2026-07-12) — детерминированная identity binding MCP tools

**Обоснование (зачем):** при livete-тестировании бухгалтерских tools Telegram-сессия test-user была корректной, но Hermes передал tools `user_id` администратора — две тестовые записи попали владельцу admin. Root cause: стабильный Telegram sender ID отсутствовал в model context, identity ошибочно зависела от LLM.

- **Identity берётся из текущей Telegram session через Hermes middleware** (`tool_execution`), а не из аргументов модели/display name.
- **LLM/display_name не являются источником identity** — `user_id` для user-scoped tools переписывается guard на sender-bound.
- **Oyijon self-only:** всегда свой internal `user_id`.
- **Admin cross-target только по строгим allowlists:** tool ∈ {`get_expense_report`, `get_balance_summary`, `get_admin_report_data`, `save_plan_note`} И target ∈ `allowed_target_user_ids`; cross-target write/delete запрещены.
- **Unknown/corrupt identity fail-closed:** блок до MCP tool (коды `IDENTITY_UNRESOLVED` / `IDENTITY_TARGET_FORBIDDEN` / `IDENTITY_MAPPING_INVALID` / `IDENTITY_MAPPING_PERMISSIONS` / `IDENTITY_GUARD_ERROR`).
- **Mapping вне model-visible profile/git**, mode `0600`.
- **Backend и Hermes core не изменяются** — плагин только детерминированно связывает sender с internal user, не становится вторым мозгом и не делает identity routing.
- **Независимый аудит: PASS** (итог `PASS_TO_VPS_PHASE_B`).
- **Merged в `main` `dd9261e`** (merge feature-ветки identity guard).
- **VPS runtime + Stage 5 E2E PASS (2026-07-13)** — plugin 1.0.3; evidence `EVIDENCE_STAGE_5_E2E_2026-07-12.md`.
- Реальные Telegram ID и содержимое mapping не логируются.

## Решения заказчика (2026-07-13) — аналитика расходов и месячный план (Этап 5.1 / ТЗ v3.7)

**Зачем:** Мариям должна быть бытовым финансовым аналитиком (группы, товары, quantity, compare/trend, plan/fact, осторожные советы), а не только калькулятором сумм.

**Риск:** галлюцинации quantity/цен/экономии; смешение units; точные прогнозы без данных; drift security-critical SKILL (уже открытый блокер).

**Цена:** миграция schema + 2 MCP tools (19→21) + расширение report; skill/проза; без identity rewrite.

**Эффект:**
- nullable `item_name_normalized` / `quantity` / `unit` на `transactions`;
- `monthly_budget_plans` + `set_monthly_budget` / `get_monthly_budget_status`;
- `get_expense_report`: compare_previous, trend_months, by_item, previous_period, monthly_series;
- backend = факты; Hermes = нормализация + объяснения + осторожные советы;
- LLM memory ≠ источник финансовой аналитики;
- Этап 5.1 требования зафиксированы в v3.7; live status закрыт решением v3.9 ниже.
- repo tools/plugin = **21/1.0.4**.

## Решение заказчика (2026-07-13) — канонический SKILL и защита (история)

- Единственный канонический файл в git: `skills/mariyam/SKILL.md`.
- Отдельная protected copy SKILL в git **не создаётся**: дубликат мог бы расходиться с источником истины.
- Защита обеспечивается profile-scoped skill-protect config и постоянными SHA/contract tests.
- Canonical Stage 5.1 SHA-256: `b12311829a35e8faa9f97872b52a9edbb2b68f499b8c757b7204686e447147e4`.
- Копирование repo SKILL в runtime profile выполнено при разрешённом deploy с последующей проверкой SHA.
- Stage 5.1: **CLOSED / LIVE PASS**; repo/VPS tools/plugin = **21/1.0.4**, skill-protect active 4/4.

Это решение описывает live baseline Stage 5.1 и superseded для будущих prompt
изменений решением v3.14 ниже. Runtime до нового deploy остаётся на этом baseline.

## Решения заказчика (2026-07-14) — Stage 5.1 live acceptance

- Migration 002 применена; schema verification = **3 columns / 1 table / 1 index**.
- Runtime tools/dispatch/MCP discovery = **21/21/21**; identity plugin **1.0.4**; canonical SKILL SHA `b1231182…`; skill-protect **4/4**, `tool_progress` off.
- Controlled E2E на временном test-user подтвердил quantity/unit, analytics, previous month, 3-month trend, budget plan/fact и identity.
- Provider gate соблюдён: 6/7 requests, retry=0, exact cost $0.222808, dashboard delta $0.22.
- Cleanup восстановил DB baseline; admin не изменён; реальная Ойижон не подключалась.
- **Stage 5.1 = CLOSED / LIVE PASS.** Дополнительные правки этапа не требуются.

## Решение заказчика (2026-07-14) — vision smoke перед handover

- Перед handover выполнить Telegram vision smoke: скрин телефона с вопросом, фото счётчика, скрин коммунального кабинета или квитанции → объяснение узбекской кириллицей.
- Сначала использовать native image input Hermes и текущую модель.
- Backend и Hermes core не менять.
- Числа подтверждаются перед ручным сохранением; deterministic portal sync не требует подтверждения каждого snapshot.
- Отдельную vision-модель подключать только после фактического FAIL текущего model path.
- Это будущая проверка, не блокер Stage 5.1.

## Решение заказчика (2026-07-14) — ТЗ v3.10: household finance и utility cabinets

- Stage 5.1 **не переоткрывать**: CLOSED / LIVE PASS; current runtime **21 tools / plugin 1.0.4 / migration 002**.
- Stage 5.2–6 additions — **PLANNED / NOT IMPLEMENTED**; docs-only update не меняет code, VPS, Telegram, API, migrations, canonical SKILL или runtime.
- Stage 5.2: простые user-facing family reports без сложных финансовых терминов; общий report первым, details только по просьбе; unknown=`айтилмаган`; JSON/tool fields скрыты.
- Stage 5.3: последовательный family planning dialog, product quantity/unit/amount и nutrition guidance. Один web search на cycle, cache 30 дней; WHO/FAO/официальный Минздрав Узбекистана; не medical prescription и не universal meat norm.
- Migration 003 planned: `monthly_budget_items` + `monthly_plan_cycles`. Existing budget tools расширяются без нового count; Stage 5.3 count остаётся 21.
- Stage 5.3A: approval cycle 25/27/28/1; с 28 числа максимум одно admin notification/day до approve либо начала следующего месяца. `approve_monthly_plan` действует только до начала планового месяца; Oyijon self-only, admin narrow future-month target allowlist. После начала месяца cycle закрыт, активный plan корректирует только Oyijon self-only; admin edit текущего plan в v3.10 не заявлен. Planned count 22; cron identity gate обязателен, unknown job fail closed/downstream=0.
- Stage 5.4: electricity official cabinet only read-only после 9-point research gate. Priority official API → export/endpoint → narrow deterministic connector. Migration 004 + 3 tools planned, count 25. Газ/вода — только после подтверждения кабинетов.
- Utility credentials только VPS secrets и никогда LLM/PostgreSQL/git/SKILL/Telegram/logи; account masked; payments/top-up/settings/cards запрещены; drift fail closed; daily sync max 1, tariff check max weekly.
- Identity: `set_utility_threshold` — Oyijon self-only; admin narrow cross-target только `allowed_target_user_ids` и только threshold, без portal/payment/settings/transactions.
- Stage 6 extension: migration 005 recurring obligations + 2 tools; Hermes cron only; planned final count 27. `upsert_recurring_obligation`/`get_recurring_obligations` — Oyijon self-only, admin narrow cross-target только `allowed_target_user_ids`, без прав на transactions. Paid mark не создаёт duplicate expense.
- Operations budget: nutrition search 1/cycle + 30-day cache; utility sync daily max; no paid utility APIs/always-on extra agents без разрешения; target 10–15 USD/month.
- Out of scope: automatic payment, bank credentials/cards/app, utility writes, treatment diet/universal meat norm, backend scheduler/router/orchestrator, Hermes core changes, gas/water without confirmed cabinets.

## Решения заказчика (2026-07-15) — отчёты по продуктам и reference prices

### Общий отчёт Stage 5.2

- Разрешено естественное оформление: короткое вступление; `Сарфланди` или `Сарфлангани`; `Қолди` или `Қолгани`; строка `Жами`; отрицательный остаток с понятным пояснением.
- После общего отчёта обязательна дословная финальная фраза: `Ойижон, хоҳласангиз, бирор харажат гуруҳини батафсилроқ кўриб чиқамиз. Маълумотлар тайёр.` Фразу нельзя пропускать или перефразировать.

### Подробный отчёт Stage 5.2

При просьбе показать одну группу ответ состоит из двух частей. Сначала summary категории:

```text
Харажат гуруҳи | Режа | Сарфлангани | Қолгани
Озиқ-овқат | 500 000 сўм | 221 000 сўм | 279 000 сўм
```

Затем только фактические товары:

```text
Маҳсулот | Миқдор | Сарфлангани
Картошка | 10 кг | 70 000 сўм
Тухум | 12 та | 36 000 сўм
Ёғ | 3 л | 90 000 сўм
Шакар | — | 25 000 сўм
Жами | — | 221 000 сўм
```

Stage 5.2 не показывает продуктовый план: product-plan storage ещё не реализован.

### Пользовательские единицы

Canonical units в tools и БД не меняются: `kg / g / l / ml / pcs / pack`. Ойижон показывать: `kg → кг`, `g → г`, `l → л`, `ml → мл`, `pcs → та`, `pack → қадоқ`. Стандартное отображение `pcs` — `та`, не `дона`.

### Stage 5.3 — продуктовый план

Stage 5.3 остаётся **PLANNED / NOT IMPLEMENTED**, расширяет существующие budget tools и сохраняет tool count 21. Подробный planned-отчёт содержит summary категории и product rows:

```text
Озиқ-овқат | Режа | Сарфлангани | Қолди

Маҳсулот | Режа миқдор | Режа сўм | Сарфланган миқдор | Сарфланган сўм | Қолди сўм
Картошка | 30 кг | 150 000 | 25 кг | 100 000 | 50 000
Тухум | 60 та | 120 000 | 45 та | 90 000 | 30 000
Ёғ | 5 л | 150 000 | 3 л | 90 000 | 60 000
```

### Цены товаров и snapshot плана

- Unit price вычисляется только при наличии `item_name_normalized`, `amount`, `quantity` и `unit`; без quantity цену за единицу не вычислять.
- Последняя цена = `amount / quantity` самой поздней подходящей покупки.
- Средняя цена — только средневзвешенная: сумма подходящих покупок / общее количество одного товара в одной одинаковой canonical unit.
- Не смешивать `kg + g`, `l + ml`, `pcs + pack` (`кг + г`, `л + мл`, `та + қадоқ`).
- Обычный вопрос о цене → последняя цена; явный вопрос о средней → средневзвешенная; план следующего месяца → последняя цена по умолчанию. Ойижон может выбрать среднюю цену или назвать ручную.
- Migration 003 только planned: при сохранении плана сохраняется snapshot `reference_unit_price_uzs`, `price_basis` (`last / average / manual`) и `price_as_of`. История цен остаётся в `transactions`; отдельную таблицу цен сейчас не создавать; новый факт покупки не меняет старый план.
- Backend считает и возвращает только точные числа, Hermes спрашивает и объясняет. Ценовая логика не хранится в LLM memory.

## Решение заказчика (2026-07-15) — deterministic profile prompt v3.14

- Полный `SKILL.md` не считать автоматически загруженным prompt-слоем Hermes.
- Единственный canonical repo-source Мариям:
  `deploy/hermes_profile_mariyam_oyijon/SOUL.md`; дублирующий Mariyam SKILL удалён.
- `SOUL.md` — поддерживаемый гарантированный profile identity slot;
  `agent.disabled_toolsets: [skills]` сохраняется как security guard.
- `skills.enabled` удалён как неиспользуемый loader key Hermes v0.18.2.
- Общий family report выбирает `get_monthly_budget_status`; товарные строки без
  запроса конкретной группы запрещены. Report rules живут в одной decision-table.
- Tool descriptions/backend/core не меняются: root cause закрывается prompt-layer.
- Restart Gateway не заменяет persisted prompt. Порядок live gate: deploy → offline
  `build_system_prompt_parts()` preflight без API → `/new` → первый controlled turn →
  read-only check новой `sessions.system_prompt` по SHA/markers → остальные E2E.
  До первого agent turn поле `sessions.system_prompt` ещё не заполнено.
- Repo SOUL SHA-256:
  `713021c2cfd6c3abff206b6a79ec7423c06c6920645ce4a6c2d31158a108c98a`.
- Статус: **OFFLINE PASS / LIVE PENDING**; VPS и Telegram/API не менялись.

## Решение заказчика (2026-07-16) — обязательная category-summary таблица v3.15

- Controlled live: Message 1 PASS; Message 2 FAIL только потому, что summary
  категории был списком вместо таблицы; cleanup/rollback PASS.
- В `CATEGORY_DETAIL` summary разрешён только отдельной Markdown-таблицей с
  заголовком `Харажат гуруҳи | Режа | Сарфлангани | Қолгани` и минимум одной
  строкой выбранной категории. Маркированный/list summary запрещён.
- Сразу после summary обязательна таблица фактических товаров
  `Маҳсулот | Миқдор | Сарфлангани`.
- `GENERAL_FAMILY_REPORT` и остальные Stage 5.2 требования не меняются;
  Stage 5.3–6 не затрагиваются.
- Repo canonical LF SOUL SHA-256:
  `a9b584e14d704f08b4778b7928ca71a0cf095394583f769c5e9571097884b4e4`.
- Статус: **OFFLINE PASS / LIVE PENDING**. VPS = Stage 5.1 rollback baseline;
  narrow fix ещё не развёрнут и после него live retest не выполнялся.

## Решение заказчика (2026-07-16) — финальный product report Stage 5.3

- Окончательный подробный product report после category summary имеет ровно три
  колонки: `Маҳсулот | Режа: миқдор / сумма | Амалда: миқдор / сумма`.
- Сокращённая таблица `Маҳсулот | Миқдор | Сарфлангани` была временным форматом
  Stage 5.2 и не является финальным форматом Stage 5.3.
- Старый planned-формат с отдельными `Режа миқдор`, `Режа сўм`,
  `Сарфланган миқдор`, `Сарфланган сўм`, `Қолди сўм` заменён.
- Отдельную product-колонку остатка не добавлять. Точный remaining может
  возвращаться backend structured fact, но не становится колонкой ответа Ойижон.
- Неизвестное значение показывать как `—` или `айтилмаган`; quantity и price не
  угадывать, разные units не смешивать; `pcs → та`.
- Stage 5.3 реализуется без новых tools: расширяются `set_monthly_budget` и
  `get_monthly_budget_status`, inventory остаётся 21. Migration 003 хранит product
  rows и immutable reference price snapshot; `monthly_plan_cycles` — только
  подготовленная schema для ещё не реализованного Stage 5.3A.
- После локальных gates статус Stage 5.3 = **OFFLINE PASS / LIVE PENDING**. Repo
  содержит migration 003; VPS остаётся на migration 002 до отдельного deploy.
  Реальная Ойижон не подключена.

## Версионность ТЗ

Исполнять только `TZ_Hermes_Mariyam_FINAL_v3_0.md` (внутри — версия **3.17**, раздел 0.1–0.17 = changelog): §0.9 — Stage 5.1 CLOSED / LIVE PASS; §0.10 — household finance design; §0.11–0.16 — Stage 5.2 implementation/acceptance/closure; §0.17 — Stage 5.3 offline implementation, migration 003 и финальный трёхколоночный product report. Старые v1/v2/review-файлы не использовать как рабочие требования.
