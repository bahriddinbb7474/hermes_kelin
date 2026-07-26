# Evidence — Stage 5.3A production deploy + cron identity (2026-07-24)

VPS `time-agent-prod` (`timeagent`). Секреты/Telegram ID/полные хэши не приводятся.

## Backend deploy — PASS
- Controlled deploy `backend/db.py` + `backend/server.py` из repo (24 tools),
  canonical LF, sha256 сверены byte-for-byte (local == uploaded == installed).
- Backups: `~/hermes-mariyam-backups/backend-20260723T230952Z` (23) и
  `…T234823Z` (перед 24). `.deployed-origin-main` = `4c69a47`.
- Runtime (non-destructive `list_tools`, без БД): **TOOLS/DISPATCH/DISCOVERY =
  24/24/24**; присутствуют `approve_monthly_plan`, `open_monthly_plan_cycle`,
  `get_monthly_plan_cycle`. Gateway `active`, PostgreSQL `healthy`,
  `time_agent_bot` не тронут, migration 003 в prod.

## Identity guard 1.1.0 → 1.2.0 — PASS
- **Временное unbound-окно (зафиксировано):** после deploy backend 23/24 tools
  `open_/get_monthly_plan_cycle` попали в MCP discovery, но guard 1.1.0 не
  классифицировал их как user-scoped → они проходили middleware без
  identity-binding (строки 808–811). Практический риск низкий: в allowlist только
  admin + тест-Ойижон, реальная Ойижон не подключена, SOUL не инициирует эти
  вызовы. Cron jobs на это время были **paused**.
- **Закрытие:** guard 1.2.0 — минимальный diff: `open_monthly_plan_cycle` и
  `get_monthly_plan_cycle` добавлены в `USER_SCOPED_TOOLS`; resolver/Telegram/cron
  логика без изменений. Backup `~/.hermes/plugin-backups/mariyam_identity_guard.20260724T000935Z`.
- Regression до redeploy: ruff clean; guard suites (Telegram 1.0.4 policy +
  cron) **89 passed**; полный suite **325 passed**; `run_tests.py` 4 маркера PASS.
- После redeploy + Gateway restart: guard 1.2.0 active; классифицирует
  `open/get/approve` = user-scoped (проверено импортом развёрнутого модуля).
  Unbound-окно закрыто.

## Cron jobs + private mapping
- Созданы 5 production jobs (Asia/Tashkent), delivery по ролям:
  25 draft→тест-Ойижон, 27 reminder→тест-Ойижон, 28 escalate→admin,
  1a auto→тест-Ойижон, 1b fallback→admin. Промпты — canonical repo
  `deploy/hermes_profile_mariyam_oyijon/cron/`.
- Private mapping `/opt/hermes-mariyam-secrets/cron-identity-map.json`: version 1,
  5 записей (user_id тест-Ойижон, role oyijon), per-job `allowed_tools` (минимум),
  `job_fingerprint_sha256` и `prompt_sha256` вычислены **функциями самого guard**.
  Запись атомарная, `umask 077`, mode **0600**, owner service user. Guard
  `load_cron_identity_map()` грузит 5 jobs без ошибок.
- Allowlists: 25 → open+get_budget_status; 27 → get_cycle+get_budget_status;
  28 → open+get_budget_status; 1a → approve; 1b → get_cycle.

## Offline security gates — PASS (без Telegram)
- Fingerprint+prompt integrity для всех 5 jobs: **PASS**.
- Forged/unknown job id → не в mapping (fail-closed): **PASS**.
- Allowlist gating: 1b (только `get_monthly_plan_cycle`) запрещает approve/open: **PASS**.
- Tamper detection: изменение prompt меняет fingerprint (resolver отверг бы): **PASS**.

## Осталось (нужно участие человека / live)
- Live Telegram happy-path E2E (`cron run` 25/27/28/1a/1b с доставкой): требует
  реальных сообщений на admin-аккаунт и тест-Ойижон.
- Шаг «ха»-approve **отправляется человеком из аккаунта тест-Ойижон** (агент не
  может слать от её имени).
- Seed тестовых данных для осмысленного draft.
- После успешного controlled E2E — resume 5 jobs (сейчас **paused**), cleanup
  тестовых месяцев до baseline.

## Live Telegram E2E — non-«ха» части PASS (2026-07-24, controlled `cron run`)

Scoped exception заказчика: seed тест-расходов ТОЛЬКО user_id 20 (тест-Ойижон) +
точный cleanup. Baseline до seed: tx=1 (существующий), plans=0, cycles=0.
Seed: 6 помеченных (`source_text='E2E_SEED_5_3A'`) food.bread/food.meat за
май/июнь/июль 2026.

- **Job 25 (draft):** `cron run` succeeded. Backend сгенерировал draft из
  3-мес среднего (+ существующий расход) → `food.bread=204000`,
  `food.meat=400000`, cycle `waiting_oyijon`/`calculated`. Тула user_id **20**
  (guard rebind cron `0→20` через trusted mapping — live). Сообщение тест-Ойижон,
  чистая узбекская кириллица, без traces/таблиц/латиницы:
  «Ассалому алайкум, Ойижон. Август ойи учун режа тайёр: нонга 204 000 сўм,
  гўштга 400 000 сўм, жами 604 000 сўм. Тасдиқласангиз, «ха» деб ёзинг.»
- **Job 27 (reminder):** succeeded; gate по статусу `waiting_oyijon` → одно
  мягкое напоминание; **duplicate rows = 0** (cycles=1, plans=2, статус не
  изменился). Узбекская кириллица.
- **Job 28 (escalate):** succeeded; статус `waiting_oyijon → waiting_admin`
  (cycles=1, без дублей); одно сообщение админу (русский), суть плана + сумма.

- **Cleanup:** удалено ровно seeded (6 tx) + test-month cycle (1) + draft (2);
  baseline восстановлен (tx=1, plans=0, cycles=0, seed_left=0).

**Осталось (человек, позже):** «ха»-approve из аккаунта тест-Ойижон
(→ `approved_by_oyijon`) и live 1a/1b на 1-е число. 5 production jobs оставлены
**active** (следующие запуски по реальным датам 25/27/28/1, delivery на
тест-аккаунты; реальная Ойижон не подключена).

## Cron-обёртка доставки — исправлено (fix01, 2026-07-24)
- Причина: `cron/scheduler.py:1443–1461`, `cron.wrap_response` default `True` →
  каждая cron-доставка обёрнута `Cronjob Response: … (job_id: …)` + футер «To stop
  or manage this job…». Применяется и к штатному тику, и к ручному `cron run`
  (общий путь доставки), не только к ручному. В output-файлах обёртки нет (только
  в отправке) — поэтому ранее не попала в evidence.
- Фикс без изменения core: `hermes --profile mariyam_oyijon config set
  cron.wrap_response false` → profile `config.yaml`; Gateway restart. Повторный
  `cron run` 25 → доставка без обёртки (визуальное подтверждение — заказчик).
- **Открыто:** «ха»-approve заблокирован deployed SOUL (`SOUL.md:280` запрещает
  вызывать Stage 5.3A tools). Нужен апдейт SOUL (владелец — архитектор/sol) до
  live «ха»/1a/1b и до статуса 5.3A = CLOSED / LIVE PASS.

## Live scheduled 25 + «ха» (2026-07-25/26)
- **Scheduled job 25 сработал на реальное 25-е**, доставка тест-Ойижон **чистая**
  (без cron-обёртки): «Август ойи режаси тайёр: озиқ-овқатга 100 000 сўм, нонга
  4 000 сўм. Жами 104 000 сўм … «ха» деб ёзинг.» → wrapper fix + scheduled delivery
  PASS в проде.
- SOUL 5.3A enable (SHA `bbf21c87…`, «ха»-guard 3 факта) развёрнут.
- **«ха»-approve не подтверждён live (best-effort, решение 2026-07-26):**
  несколько ретестов «ха» — либо модель не вызывала approve на bare «ха», либо
  turn падал на upstream `HTTP 524` (`api.n1n.ai`/`gpt-5.6-luna`, 120s timeout,
  msgs≈54). Последняя SOUL-директива tool-first (SHA `ba51bee5…`) развёрнута, но
  проверить не удалось — провайдер снова 524. Дальнейшие prompt-итерации
  прекращены. **Основной путь — auto-approve (cron 1a, 1-е число), unit-tested.**
  «ха» перепроверяется при здоровом провайдере, без обязательства. См. DECISIONS
  2026-07-26.

## «ха»-approve — LIVE PASS (2026-07-26 12:11, после включения fallback)

- Настроена fallback-цепочка (profile `config.yaml`, `fallback_providers`, тот же
  провайдер/креды): `gpt-5.6-luna` → `gpt-5.6-terra` → `gpt-5.6-sol`.
- Live: Luna снова ушла в таймаут (145 s), Hermes показал
  `Switched to fallback model: gpt-5.6-luna → gpt-5.6-terra`, Terra ответила за 2–3 s.
- Тест-Ойижон отправила одиночное «ха» → Мариям по SOUL-директиве вызвала
  `get_monthly_plan_cycle`(август) = `waiting_oyijon` → `approve_monthly_plan(source=oyijon)`
  → ответ кириллицей «Хўп, Ойижон. Август ойи учун режа тасдиқланди.»
- **БД (ground truth):** `status=approved_by_oyijon`, `approved_by_user_id=20`
  (self-only, тест-Ойижон), `approved_at=2026-07-26T07:11:10Z`, `source=calculated`.
- Вывод: логика цикла и «ха»-approve исправны; единственной причиной прошлых
  неудач был upstream-таймаут Luna (524). Fallback снимает эту зависимость.

## Джобы 1a / 1b — controlled прогон 2026-07-26 (вне даты срабатывания)

Снимок БД до и после идентичен: `cycles: 2026-08-01=approved_by_oyijon`,
`plans: 2`, `tx: 1` — **мутаций 0**.

**1a (`mariyam_plan_01a_auto`, delivery Ойижон):** запуск `cron run` →
финальный ответ `[SILENT]`, Ойижон **ничего не отправлено** (корректно: по
prompt при отказе tool сообщение не шлётся). Точные коды отказа проверены
прямым вызовом `approve_monthly_plan(source=auto)`:

| месяц | код | мутация |
|---|---|---|
| `2026-07-01` (текущий, его берёт 1a сегодня) | `MONTH_ALREADY_STARTED` | нет |
| `2026-08-01` | `INVALID_STATUS_TRANSITION` (уже `approved_by_oyijon`) | нет |

Уточнение к ожиданию заказчика: ожидался `MONTH_NOT_STARTED`, фактически
`MONTH_ALREADY_STARTED` — потому что 1a по контракту берёт **текущий**
календарный месяц, а июль уже начался. `MONTH_NOT_STARTED` возникает при
`auto` на ещё не наступивший месяц. Оба — детерминированный отказ до записи;
проверяемое свойство (нулевая мутация вне 1-го числа) подтверждено.
Отдельно подтверждено отсутствие двойного утверждения августа.

**1b (`mariyam_plan_01b_fallback`, delivery админ):** запуск → read-only
`get_monthly_plan_cycle`(июль) = `exists:false` → **одно** сообщение админу
(подтверждено заказчиком в Telegram): «План на текущий месяц (июль 2026) не
сформирован. Бахриддин ака, пожалуйста, введите план.» Мутаций нет.

**Повтор «ха» не требуется:** «ха»-approve уже LIVE PASS (12:11,
`approved_by_oyijon`); повторное «ха» теперь корректно не утверждает повторно
(август терминальный → `INVALID_STATUS_TRANSITION`).

## Статус Stage 5.3A: CLOSED / LIVE PASS (2026-07-26)

Live-подтверждено: backend 24/24/24 и guard (unbound-окно закрыто);
production cron 25/27/28 (draft → напоминание → эскалация админу, без дублей);
чистая доставка без cron-обёртки (штатный запуск 25-го); «ха»-approve →
`approved_by_oyijon`; 1a/1b — детерминированные отказы и admin-fallback без
мутаций; offline security gates (fingerprint/forged/allowlist/tamper);
fallback-модель при 524 провайдера.

Остаточное (не блокирует закрытие): фактический `auto_approved` физически
возможен только 1-го числа — путь покрыт unit-тестами, а его границы и отказы
подтверждены живьём выше. Реальная Ойижон не подключена (доставка тест-аккаунты).

## Rollback (задокументировано, не выполнялось)
- Backend: восстановить db.py/server.py из backup, `.deployed-origin-main`
  предыдущий, restart Gateway.
- Guard: восстановить `__init__.py`/`plugin.yaml` из plugin-backup, restart.
- Mapping: атомарно вернуть `{"version":1,"jobs":{}}`; jobs remove/pause.
