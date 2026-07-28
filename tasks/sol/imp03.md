# imp03 — Controlled VPS deploy identity guard 1.1.0 + cron probes (Stage 5.3A)

## Контекст
Repo `main` = `f87209a`: `mariyam_identity_guard` 1.1.0 с cron identity resolver
(imp02, offline-гейты PASS). Deployed на VPS — 1.0.4. Спецификация probe-чек-листа —
`docs/TZ/CRON_IDENTITY_GATE_5_3A.md`, раздел «Обязательные тесты перед deploy →
Controlled VPS». Профиль `mariyam_oyijon`, `/opt/time-agent`, secrets
`/opt/hermes-mariyam-secrets/`. Production cron jobs 25/27/28/1 НЕ создаются
(их prompts/allowlists ещё не утверждены). Реальная Ойижон не подключена.

## Что сделать
1. Backup: текущий deployed plugin dir + private profile config (пути в отчёт).
2. Deploy plugin 1.1.0 в профиль Мариям; `MARIYAM_CRON_IDENTITY_MAP_FILE`
   задать в private profile `.env`. Gateway restart. Hermes core, backend, БД,
   `mariyam_stage53_guard`, SOUL — не трогать.
3. Пустой/базовый cron mapping создать по процедуре design-дока
   (umask 077, owner service user, mode 0600, parent 0700).
4. Probes по чек-листу (все read-only, только временные one-shot jobs):
   a) unknown job (без mapping entry) → block, downstream = 0;
   b) временный test job + mapping entry на **test-user** (не admin, не Ойижон):
      read-only tool из allowlist → корректный internal users.id;
   c) тот же job, prompt с forged `user_id` чужого пользователя → в MCP ушёл
      тот же mapping user (подмена доказана логом);
   d) мутация job definition (update) после fingerprint → block
      `CRON_JOB_UNTRUSTED`, downstream = 0;
   e) tool вне allowlist → `CRON_TOOL_FORBIDDEN`, downstream = 0.
5. Telegram regression live: один обычный read-only запрос с тестового
   Telegram-аккаунта → поведение как при 1.0.4 (identity PASS, ответ нормальный).
6. Cleanup: все test jobs, outputs, cron sessions удалить; test mapping entries
   убрать (файл с mode 0600 оставить, если пустая схема валидна); подтвердить:
   Gateway active, PostgreSQL baseline не изменён, admin не изменён,
   inventory/dispatch/discovery = 21/21/21.
7. Rollback-готовность: одна команда/процедура возврата на 1.0.4 — описать,
   не выполнять.

## Отчёт
- `tasks/sol/imp03.report.md` + evidence
  `docs/EVIDENCE_STAGE_5_3A_CRON_GUARD_DEPLOY_<дата>.md`:
  фактические логи каждого probe (masked), результаты cleanup-проверок.
- Обновить статусы (README/ROADMAP: deployed plugin = 1.1.0) — минимально.
- Commit(ы) поимённо + push, message:
  `docs: Stage 5.3A cron guard controlled deploy evidence`.
- В чат заказчику: 2–3 предложения простым русским.

## Запрещено
Production jobs 25/27/28/1; изменение admin/Ойижон данных; мутирующие tools в
probes; секреты/mapping в git, логи или Telegram.
