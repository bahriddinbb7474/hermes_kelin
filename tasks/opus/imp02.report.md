# imp02 (Opus) — отчёт v2: backend 23 deployed; cron-фаза на checkpoint

## Шаг 0 — закрыт
Вариант A утверждён, `open_monthly_plan_cycle` реализован (imp03) и расширен
(auto-generate draft, решение 2026-07-25). Draft-строку `waiting_oyijon`
создаёт job 25 через `open_monthly_plan_cycle(open)`; переход в `waiting_admin` —
job 28 через `escalate`. Конфликта с read-only больше нет.

## Шаг 1 — Controlled deploy backend 23 tools: PASS
- SSH разрешён заказчиком; deploy как `timeagent@time-agent-prod`.
- Backup: `~/hermes-mariyam-backups/backend-20260723T230952Z/` (db.py, server.py,
  deployed-origin-main). Прежний deployed commit `37dbba7`.
- Изменены только `backend/db.py` + `backend/server.py` (аддитивно, 2 новых tool);
  установлены canonical LF из repo HEAD `56a113b`, побайтно сверены sha256:
  - db.py `e0122678f5f6df19f31d1fef4e92dbdcb5a7321f354dcbff53ea80e41fb7adec`
  - server.py `674825a1ca18ea09841a0c06e29df52ffc8e970af69ddfc27025db6161358f81`
- `.deployed-origin-main` → `56a113b`. Restart только Mariyam Gateway.
- **Проверка runtime (non-destructive, `list_tools` без БД): TOOLS/DISPATCH/
  DISCOVERY = 23/23/23**; присутствуют `approve_monthly_plan`,
  `open_monthly_plan_cycle`.
- Health: Gateway `active`; PostgreSQL `healthy`; `time_agent_bot` не тронут;
  migration 003 (`monthly_plan_cycles`, `monthly_budget_items`) уже в prod БД.
- Транзиентный upstream HTTP 524 (LLM-провайдер) в момент рестарта — не связан с
  MCP backend, Gateway поднялся штатно.
- Rollback (не выполнялся): вернуть db.py/server.py из backup, `.deployed-origin-main`
  → `37dbba7`, restart Gateway, проверить 21/21/21.

Production cron-map остаётся `{"version":1,"jobs":{}}`; jobs не создавались;
Telegram-сообщения не отправлялись; тестовые данные БД не создавались.

## Шаги 2–6 — НЕ выполнены: два новых design-gap + live-фаза на подтверждении

**Gap 1 — нет read-tool для статуса цикла.** Jobs 27/28 должны знать, одобрила ли
Ойижон план. `get_monthly_budget_status` возвращает plan/actual, но не
`monthly_plan_cycles.status`. Job 28 обходится через возврат `escalate`
(ok→notify admin; `INVALID_STATUS_TRANSITION`→уже approved→молчать). Но **job 27
(read-only)** не может узнать статус → по ТЗ п.27 «при отсутствии ответа» он бы
напоминал Ойижон даже после её approve. Нужно решение (варианты в чате).

**Gap 2 — один `--deliver` на job.** Job 1: успех→Ойижон, `NO_PLAN_SOURCE`→админ;
job 28→админ. У одного cron job одна delivery-цель; ветвление получателя требует
либо отдельных jobs, либо проверки delivery-механики в live E2E.

**Live-фаза (jobs + fingerprints + mapping + Telegram E2E)** — outward-facing и
меняет постоянную конфигурацию + отправляет реальные сообщения тест-аккаунтам,
а design-док требует явного одобрения delivery targets. Остановлен на checkpoint
до решения по gap 1/2 и явного go-ahead на live-фазу.

Delivery targets (по ролям, id не раскрываются): тест-Ойижон = user_id 20
(role oyijon); админ = Бахриддин ака (user_id 1, `allowed_target_user_ids:[20]`).
Реальная Ойижон не подключена; доставка ей запрещена (CRON_AND_REMINDERS п.13).

## Коммит
Backend уже задеплоен из `56a113b` (imp01/imp03/extension коммиты). Этот отчёт —
docs. Feature-коммит `feat: Stage 5.3A production approval cycle live` будет после
завершения cron-фазы.
