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

## Rollback (задокументировано, не выполнялось)
- Backend: восстановить db.py/server.py из backup, `.deployed-origin-main`
  предыдущий, restart Gateway.
- Guard: восстановить `__init__.py`/`plugin.yaml` из plugin-backup, restart.
- Mapping: атомарно вернуть `{"version":1,"jobs":{}}`; jobs remove/pause.
