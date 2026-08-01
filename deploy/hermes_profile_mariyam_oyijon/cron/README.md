# Production cron jobs — Stage 5.3A + Stage 6 + Stage 7

Canonical base prompts for the monthly plan approval cycle. Files here are the
source of truth for each job's `prompt`; `prompt_sha256` in the private cron
identity map is computed from the exact stored prompt.

## Jobs

| File | Schedule (Asia/Tashkent) | Deliver | Purpose | allowed_tools |
|---|---|---|---|---|
| `25_draft.md` | `0 9 25 * *` | тест‑Ойижон | open cycle (backend auto-generates draft) → предложить Ойижон | read-only + `open_monthly_plan_cycle` |
| `27_reminder.md` | `0 9 27 * *` | тест‑Ойижон | мягкое напоминание, только если ещё не approved | read-only + `get_monthly_plan_cycle` |
| `28_escalate.md` | `0 9 28 * *` | админ | escalate → waiting_admin; уведомить админа один раз | read-only + `open_monthly_plan_cycle` + `get_monthly_plan_cycle` |
| `01a_autoapprove_oyijon.md` | `0 8 1 * *` | тест‑Ойижон | `approve_monthly_plan(source=auto)`; сообщить Ойижон | read-only + `approve_monthly_plan` |
| `01b_fallback_admin.md` | `10 8 1 * *` | админ | read-only fallback: если плана нет — уведомить админа | read-only + `get_monthly_plan_cycle` |

Read-only set = `get_monthly_budget_status`, `get_expense_report`,
`get_balance_summary`, `get_monthly_plan_cycle`.

Identity: все 5 jobs — trusted cron с `user_id`=тест‑Ойижон (role oyijon,
self-only) в private mapping. `user_id=0` в промпте → guard переписывает на
mapped user. Delivery-цель отдельная от tool-identity.

## Deploy (operator; секреты/ID не в git)

1. Создать jobs: `hermes --profile mariyam_oyijon cron create '<schedule>' "$(cat <file>)" --name <name> --deliver telegram:<chat_id>`.
2. Прочитать выданные 12-hex job IDs из `$HERMES_HOME/cron/jobs.json`.
3. Fingerprints вычислять **функциями самого guard** (`cron_job_fingerprint(job)`
   и `sha256(prompt)`), чтобы совпасть с resolver.
4. Записать `MARIYAM_CRON_IDENTITY_MAP_FILE` атомарно, `umask 077`, mode 0600,
   owner = service user: version 1, jobs{ id → {user_id, role:"oyijon", purpose,
   allowed_tools, job_fingerprint_sha256, prompt_sha256} }.
5. Offline/controlled E2E (`cron run` каждого job) + forged/unknown probe → block.

Реальная Ойижон не подключена; доставка ей запрещена (CRON_AND_REMINDERS п.13).

## Stage 6 daily-life jobs

Согласовано заказчиком 2026-07-29: Kun.uz остаётся, УзА удалён; мировые
RSS и темы задаются `backend/news_sources.json`. Утро **08:00**, вечер
**19:30**, часовой пояс `Asia/Tashkent`.

| File | Schedule | Deliver | Purpose | mapped allowed_tools |
|---|---|---|---|---|
| `06_morning.md` | `0 8 * * *` | тест‑Ойижон | приветствие, заботливая погода, 1–2 разговорные новости | внешние read-only tools; news identity injected by guard |
| `06_obligation_reminders.md` | `15 9 * * *` | тест‑Ойижон | заранее / due / due+1, без мутаций, максимум одно сообщение | `get_recurring_obligations` |
| `06_evening.md` | `30 19 * * *` | тест‑Ойижон | один мягкий вопрос, только если за день данных нет | `get_admin_report_data` |
| `07_admin_report.md` | `30 19 * * *` | тест‑админ | фактический отчёт день/месяц/план/обязательства/alerts, без health-текстов | `get_admin_report_data` |

Все mapped allowlists строго read-only. Внешние tools
`get_tashkent_weather`, `get_tashkent_prayer_times` не имеют
`user_id`. `get_daily_news` owner-bound и объединяет стандартные ленты с
активными лентами владельца. Результат кэшируется backend на день; stale
возвращается с честной пометкой.

Отдельный user-systemd timer `mariyam-prayer-scheduler.timer` после полуночи
получает свежий Aladhan-кэш и создаёт шесть finite one-shot: список времён в
07:45 и пять напоминаний за 10 минут до намаза. Все они `no_agent=true`,
печатают утверждённый кириллический шаблон и не добавляют LLM-вызовов.
Ротация зависит от даты и не повторяет вчерашний вариант того же слота.

Фразы «сплю»/«ухлаяпман» включают тишину до 08:00, «Қуръон ўқияпман» — на
90 минут. В сами окна намаза (20 минут от начала) non-critical delivery
пропускается без отложенного дубля. No-agent script выдаёт пустой stdout, а
LLM cron получает штатный `[SILENT]`; health-alert админу проходит независимо.

Пользовательский `cronjob` для фразы вроде «Эртага соат 10 да дорини эслат»
остаётся **untrusted**: его job ID не добавляется в private mapping. Profile
plugin `mariyam_cron_reliability` заменяет будущий ISO one-shot от mapped
test/Oyijon на private script с `no_agent=true`, `repeat=1`, `deliver=origin`.
Script печатает уже готовый текст дословно и сам удаляется; при наступлении
срока LLM/provider не вызывается. Recurring/admin jobs и все trusted identity
jobs не переписываются; у trusted jobs по-прежнему `script=null`,
`no_agent=false`.

## +15-minute watchdog

System timer `mariyam-cron-watchdog.timer` проверяет раз в пять минут восемь
критичных recurring jobs: цикл 25/27/28/1a/1b, morning, obligations и admin
report. После 15-минутного grace он требует одновременно:

- успешный `last_run_at`/`last_status` без `last_delivery_error`;
- новый cron output;
- exact schedule, enabled state, trusted mapping и запрет script/no-agent.

При доказанном failed/missing tick выполняется ровно один штатный `cron run`.
Claim хранится в private SQLite, поэтому следующий timer tick не создаёт
дубликат. Повторный сбой или неоднозначное состояние (output уже есть, но
delivery state не зафиксирован) отправляет test-admin прямой Telegram alert
механизмом Stage 8; LLM не участвует. Interrupted claim не повторяет user
delivery и через 10 минут эскалируется админу.

## Чистая доставка (без cron-обёртки) — обязательно

Hermes по умолчанию оборачивает КАЖДУЮ cron-доставку заголовком
`Cronjob Response: <name> (job_id: …)` и футером «To stop or manage this job…»
(`cron/scheduler.py`, `cron.wrap_response` default `true`). Это technical traces
и риск случайной остановки job Ойижон. Отключить в профиле:

```
hermes --profile mariyam_oyijon config set cron.wrap_response false
```

(пишет `cron.wrap_response: false` в profile `config.yaml`; restart Gateway).
Проверять доставку только с этим выключенным флагом.

## Fallback-модели (резерв при 524 провайдера)

Провайдер `api.n1n.ai` периодически отдаёт Cloudflare **524** (таймаут 120 с) —
ход агента падает, tool-calls не выполняются. Hermes распознаёт 524 и после
исчерпания попыток переключается на fallback-цепочку. Настроено (profile
`config.yaml`, top-level `fallback_providers`, тот же провайдер/креды):

```yaml
fallback_providers:
  - {provider: openrouter, model: deepseek/deepseek-chat}   # вне n1n.ai, дёшево
```

Единственное звено — `deepseek/deepseek-chat` через **OpenRouter**: независимый
провайдер (спасает и при падении всего n1n.ai) и дешёвый.
`OPENROUTER_API_KEY` уже в profile `.env`.

**Terra/Sol сознательно НЕ используются** (решение заказчика 2026-07-26): по
биллингу n1n.ai Terra ≈ $0.16–0.31 за запрос против ≈ $0.02 у Luna (коэффициент
1.25 + групповой множитель) — при бюджете $10–15/мес это неприемлемо.

**LIVE PASS 2026-07-26:** Luna таймаут 145 s → авто-переключение на резерв (2–3 s) →
«ха» от тест-Ойижон → `approve_monthly_plan` → `approved_by_oyijon` в БД
(проверялось на Terra до её удаления из цепочки).

Проверка: `hermes --profile mariyam_oyijon fallback list`; сброс: `fallback clear`.

Язык: DeepSeek **проверялся заказчиком ранее** — узбекская кириллица в порядке,
поэтому как резерв для ответов Ойижон допустим. Отдельного нового языкового AC
не требуется.
