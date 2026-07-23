# imp02 — отчёт

## Результат

В существующий `mariyam_identity_guard` добавлен fail-closed cron identity
resolver по утверждённому design `CRON_IDENTITY_GATE_5_3A.md`. Версия repo
plugin поднята до `1.1.0`; deployed VPS остаётся на `1.0.4`, deploy не
выполнялся.

Telegram policy 1.0.4 сохранена: неизменённый
`tests/test_mariyam_identity_guard.py` прошёл полностью.

## Реализация

- Cron session принимается только по exact regex
  `cron_<12 lowercase hex>_<YYYYMMDD_HHMMSS>`.
- Persisted session обязан иметь `source="cron"`, `user_id IS NULL`,
  `origin_json IS NULL`.
- Exact job читается из profile `cron/jobs.json` под shared lock.
- Trusted jobs запрещают `script`, `context_from`, `workdir`, `no_agent`.
- Private mapping v1 читается из `MARIYAM_CRON_IDENTITY_MAP_FILE`: absolute
  path, bounded size, strict schema/unknown-key rejection, regular non-symlink,
  owner service user, file `0600`, parent `0700`.
- Проверяются immutable job fingerprint и prompt текущего session, поэтому
  update → malicious run → restore не даёт доверенную identity.
- Tool обязан входить в per-job `allowed_tools`; model `user_id` игнорируется и
  заменяется mapping `users.id`; cron role только `oyijon` (self-only).
- Unknown job/session, modified job/prompt, forbidden tool, malformed mapping,
  unsafe permissions/symlink и internal exception дают safe error до
  downstream.
- Логи cron не содержат raw session/user/target IDs или mapping body.
- `approve_monthly_plan` заранее классифицирован как user-scoped, но tool не
  добавлен в inventory; фактический count остаётся 21.

## Решения заказчика

В `docs/TZ/DECISIONS.md` зафиксировано:

1. Jobs 25/27/28 — read-only; mutation разрешена только job «1 число»
   (auto-approve).
2. Cross-run idempotency принадлежит будущему контракту
   `approve_monthly_plan` и unique constraints `monthly_plan_cycles`, не
   guard-плагинам.

## Изменённые файлы

- `deploy/hermes_plugins/mariyam_identity_guard/__init__.py`
- `deploy/hermes_plugins/mariyam_identity_guard/plugin.yaml`
- `tests/test_mariyam_cron_identity_guard.py`
- `tests/test_mariyam_stage53_guard.py`
- `README.md`
- `docs/ROADMAP.md`
- `docs/TZ/DECISIONS.md`
- `tasks/sol/imp02.report.md`

`mariyam_stage53_guard`, Hermes core, backend, migrations и БД не менялись.

## Тесты

Целевые прогоны:

```text
tests/test_mariyam_cron_identity_guard.py
15 passed

tests/test_mariyam_identity_guard.py
73 passed

tests/test_mariyam_stage53_guard.py
37 passed
```

Финальный полный прогон на локальном установленном Hermes v0.18.2 / Python
3.11:

```text
python -m pytest tests -q
235 passed, 31 skipped in 19.59s
```

Покрыты все 10 offline gates design-дока: Telegram regression, trusted cron
rewrite, unknown/fake session, job/prompt tampering, tool allowlist, malformed
mapping/permissions/symlinks/size, exception downstream=0, middleware order,
same-turn duplicate, разные firings, `max_turns=6`, inventory 21 и manifest
1.1.0.

## Коммиты

- Design/base: `205ce51`
- Implementation:
  `d435c932ee0d67e220b1e2ee38b6999caf495093`
- Этот отчёт: отдельный docs commit после implementation; его hash указан в
  финальном handoff.

## Осталось до deploy

Отдельной задачей:

1. создать окончательные production jobs 25/27/28/1;
2. утвердить exact prompts, delivery targets и per-job tool allowlists;
3. оператором вычислить fingerprints и создать private VPS mapping `0600`;
4. controlled deploy plugin 1.1.0 с backup/rollback;
5. выполнить negative/positive VPS gates и cleanup;
6. отдельно реализовать `approve_monthly_plan` и cross-run business
   idempotency.

Production jobs/mapping, Telegram/API calls и VPS deploy в imp02 не
выполнялись.
