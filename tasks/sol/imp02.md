# imp02 — Cron identity resolver в mariyam_identity_guard (Stage 5.3A, шаг 1)

## Контекст
Спецификация — твой утверждённый design-док
`docs/TZ/CRON_IDENTITY_GATE_5_3A.md` (commit `205ce51`). Реализовать ровно его,
разделы «Минимальное расширение profile plugin», «Resolver cron identity»,
«Fail-closed matrix», «Обязательные тесты перед deploy → Offline».

Решения заказчика (утверждены 2026-07-23, зафиксировать в DECISIONS.md):
1. Mutation в цикле 25/27/28/1 разрешён только шагу «1 число» (auto-approve).
   Jobs 25/27/28 — строго read-only + отправка сообщений; их mapping entries
   не содержат mutating tools в `allowed_tools`.
2. Cross-run idempotency — ответственность контракта `approve_monthly_plan`
   и unique constraints `monthly_plan_cycles`, НЕ guard'а. В этой задаче
   tool не реализуется.

## Объём
Только plugin + offline-тесты. БЕЗ: production cron jobs, mapping-файла на VPS,
`approve_monthly_plan`, изменений Hermes core/backend/БД, deploy.

1. Расширить `deploy/hermes_plugins/mariyam_identity_guard/`:
   - Telegram-ветка 1.0.4 — байт-в-байт без изменений поведения;
   - cron-ветка строго по design-доку: session regex → persisted
     `source="cron"`, `user_id IS NULL`, `origin_json IS NULL` → exact job в
     `cron/jobs.json` под shared lock → private mapping
     (`MARIYAM_CRON_IDENTITY_MAP_FILE`, schema v1 из design-дока, mode 0600,
     parent 0700, owner, non-symlink, bounded size, unknown keys → reject) →
     job fingerprint + prompt binding → allowlist tool → принудительный
     `user_id` из mapping → self-only policy → next middleware;
   - вся fail-closed matrix из design-дока, safe error codes
     (`CRON_IDENTITY_UNRESOLVED`, `CRON_JOB_UNTRUSTED`, `CRON_TOOL_FORBIDDEN`);
   - логирование: masked, без raw IDs/mapping body/полных session ids;
   - версия plugin → `1.1.0` в plugin.yaml.
2. Offline-тесты — все 10 пунктов раздела «Обязательные тесты перед deploy →
   Offline» design-дока, в `tests/` рядом с существующими
   (`test_mariyam_identity_guard.py` не ломать — Telegram regression suite
   должен пройти без правок тестов).
3. Обновить доки минимально: DECISIONS.md (2 решения выше + версия 1.1.0),
   README/ROADMAP строку runtime версии plugin пометить как
   «repo 1.1.0 / deployed 1.0.4» — deploy отдельной задачей.

## Ограничения
- Никаких новых plugins/routers — только расширение существующего.
- Tool count остаётся 21; discovery/inventory не менять.
- `mariyam_stage53_guard` не менять; порядок chain identity → stage53 сохранить.
- Коммитить поимённо, не захватывать CRLF-шум чужих файлов.

## Отчёт
- `tasks/sol/imp02.report.md`: изменённые файлы, вывод полного тестового прогона
  (все suites), hash коммитов, что осталось до deploy.
- Commit(ы) в `main` + push, message вида
  `feat: cron identity resolver in mariyam_identity_guard (5.3A)`.
- В чат заказчику: 2–3 предложения простым русским.
