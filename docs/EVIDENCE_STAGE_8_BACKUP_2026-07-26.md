# Stage 8 live evidence — 2026-07-26

VPS: `time-agent-prod`, user `timeagent`. Секреты, Telegram ID и OAuth credentials
не выводились и не сохранялись в git.

## Backup

- rclone v1.74.4, remote `hermes_mariyam_gdrive`.
- После перехода на собственный OAuth Client предупреждение shared client исчезло.
- Состав: PostgreSQL custom dump; `config.yaml`, `SOUL.md`;
  `/opt/hermes-mariyam-secrets`; manifest числа строк и известного расхода.
- GPG symmetric AES-256; passphrase только
  `/opt/hermes-mariyam-secrets/backup-gpg-passphrase`, mode 0600.
- Remote folder: `hermes-mariyam-backups`; retention: newest 30 archives.
- Daily timer `mariyam-backup.timer`: enabled/active.
- Installed sandboxed service live run: `Result=success`, `ExecMainStatus=0`;
  archive uploaded at `2026-07-26T07:47:25Z`.

## Restore check

Архив восстановлен в одноразовый PostgreSQL container. Production DB использовалась
только для `pg_dump`/read-only manifest. Profile state распакован в private temp dir.

| Table | Rows |
|---|---:|
| alert_events | 0 |
| expense_categories | 19 |
| health_notes | 0 |
| monthly_budget_items | 2 |
| monthly_budget_plans | 2 |
| monthly_plan_cycles | 1 |
| plan_notes | 0 |
| quran_progress | 0 |
| transactions | 9 |
| usage_costs | 0 |
| users | 2 |

Known expense matched: `id=7`, amount `12000 UZS`. All counts matched. Temporary
container was removed by the cleanup trap.

## Monitoring and isolation

Test heartbeat was delivered directly to the admin via Telegram Bot API.
`mariyam-heartbeat.timer` is enabled/active; backup `OnFailure` points to the
installed notification template. Ойижон не получала сообщений.
Gateway user-unit remained enabled/active, PostgreSQL healthy and Time-Agent running.
Gateway/SOUL/plugins/cron/mapping and `/opt/time-agent` were not modified or restarted.
