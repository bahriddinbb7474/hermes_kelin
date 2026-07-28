# imp02 (Opus) — Deploy backend 23 tools + production cron jobs 25/27/28/1 (Stage 5.3A, финал)

> **v2 (2026-07-24): разблокировано.** Шаг 0 закрыт: вариант A утверждён,
> `open_monthly_plan_cycle` реализован (imp03, commit `b26b4bb`). Правки v2:
> deploy = **23** tools (не 22), inventory/dispatch/discovery = 23/23/23;
> allowlists: job 25 — read-only + `open_monthly_plan_cycle` (open);
> job 27 — read-only; job 28 — read-only + `open_monthly_plan_cycle` (escalate);
> job 1 — read-only + `approve_monthly_plan`. E2E п.4 дополнить: 25 создаёт
> cycle-строку `waiting_oyijon` через tool; 28 — escalate через tool.
> Остальное ниже без изменений (читать «22» как «23»).

## Контекст
Repo `main` (после `15d4777`). Готово: guard 1.1.0 deployed (cron identity,
evidence 2026-07-24), `approve_monthly_plan` в repo (inventory 22), deployed
backend — 21. Migration 003 active. Спеки:
`docs/TZ/CRON_IDENTITY_GATE_5_3A.md` (mapping/fingerprint процедура),
`docs/TZ/TOOLS_CONTRACTS.md` (контракт tool), ТЗ «Этап 5.3A» (~стр. 1484).
Решение заказчика: mutation только у job «1 число»; 25/27/28 — read-only +
сообщения. Реальная Ойижон не подключена — delivery на тестовый аккаунт.
Все сообщения Ойижон — только узбекская кириллица.

## Шаг 0 — обязательная сверка (STOP-условие)
Выяснить по фактическому коду, как создаётся draft-строка
`monthly_plan_cycles` (п.1 ТЗ: «25 число … status waiting_oyijon»).
`approve_monthly_plan` drafts не создаёт. Если для job 25 нужен mutating tool
(создание draft) — это конфликт с решением «25/27/28 read-only»:
ОСТАНОВИТЬСЯ, изложить варианты в отчёте и чате, код не писать до решения.
Если draft создаётся существующим безопасным путём (например, Telegram-turn
Ойижон или существующий tool) — зафиксировать это в отчёте и продолжить.

## Что сделать (после шага 0)
1. Controlled deploy backend с 22 tools на VPS: backup, deploy, restart,
   проверить inventory/dispatch/discovery = 22/22/22, health Gateway/PostgreSQL.
   Rollback-процедура описана (не выполнять).
2. Prompts для 4 production jobs (хранить в repo, напр.
   `deploy/hermes_profile_mariyam_oyijon/cron/`):
   - 25: draft следующего месяца (по трём последним месяцам, последнему
     approved, обязательным платежам), отправить Ойижон ОДИН раз, мягкий тон;
   - 27: если нет approve/change — одно мягкое напоминание, без нового draft
     и duplicate rows;
   - 28: перевод в waiting_admin; админу максимум 1 уведомление/сутки до
     approve, по возможности в 19:30, стоп сразу после approve;
   - 1: valid draft → `approve_monthly_plan(source=auto)`; поведение при
     отсутствии draft/прошлого плана — по контракту tool; `NO_PLAN_SOURCE` →
     сообщение админу.
3. Создать jobs через profile CLI, вычислить fingerprints, внести в
   `/opt/hermes-mariyam-secrets/cron-identity-map.json` по процедуре
   design-дока (0600/0700, umask 077). Allowlists: 25/27/28 — только
   read-only tools; 1 — read-only + `approve_monthly_plan`.
4. Controlled E2E без ожидания дат (ручной `cron run` каждого job):
   - 25 → draft + одно сообщение тест-Ойижон, кириллица, без technical traces;
   - 27 → одно напоминание, duplicate rows = 0;
   - 28 → waiting_admin + одно сообщение тест-админу;
   - Telegram «ха»-approve от тест-Ойижон → approved_by_oyijon;
   - 1 (на свежем draft другого тест-месяца) → auto_approved, idempotent
     replay при повторном run;
   - forged/unknown job probe → block (регрессия guard).
5. Cleanup тестовых данных БД (test-месяцы) до baseline; production jobs
   оставить активными, но задокументировать их job_ids (masked) в evidence.
6. Evidence `docs/EVIDENCE_STAGE_5_3A_E2E_<дата>.md` + статусы README/ROADMAP
   (5.3A: если все E2E PASS — CLOSED / LIVE PASS, deployed = 22).

## Запрещено
Менять Hermes core; трогать transactions; данные admin; прямые SQL-мутации
вне миграций; секреты/mapping в git/логи/Telegram.

## Отчёт
`tasks/opus/imp02.report.md`: шаг 0, фактические логи E2E (masked), cleanup,
hash коммитов; commit поимённо + push:
`feat: Stage 5.3A production approval cycle live` (+ evidence commit).
В чат заказчику: 2–3 предложения простым русским.
