# Stage 5.3A production cron jobs (25 / 27 / 28 / 1a / 1b)

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
