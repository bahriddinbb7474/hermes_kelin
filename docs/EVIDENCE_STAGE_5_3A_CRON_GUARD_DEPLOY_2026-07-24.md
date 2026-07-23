# Stage 5.3A — controlled cron identity guard deploy

Дата завершения: 2026-07-24 Asia/Tashkent.
Статус: **CONTROLLED DEPLOY / LIVE PROBES PASS**.

## Scope

В профиль `mariyam_oyijon` развёрнут только
`mariyam_identity_guard` 1.1.0. Hermes core, backend, PostgreSQL schema/data,
`mariyam_stage53_guard`, SOUL и `/opt/time-agent` не изменялись.

Production cron jobs 25/27/28/1 и production mapping entries не создавались.
Все jobs ниже были временными one-shot/read-only.

## Backup и private config

Backup:

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/imp03-20260723T184146Z/
  mariyam_identity_guard-1.0.4.tar.gz
  mariyam_identity_guard.dir/
  profile.env.before
  baseline.hashes
```

Private cron mapping:

```text
/opt/hermes-mariyam-secrets/cron-identity-map.json
owner: service user
file mode: 0600
parent mode: 0700
final schema: {"version":1,"jobs":{}}
```

В private profile `.env` добавлен один
`MARIYAM_CRON_IDENTITY_MAP_FILE`; значение и содержимое mapping в git/logs не
попадали.

Live deploy обнаружил edge case: разрешённая cleanup-процедурой пустая схема
mapping первоначально отклонялась валидатором. Валидатор и regression test
исправлены; targeted Telegram+cron suites после исправления: `89 passed`.

## Cron probes

### Unknown job

Job `3cac06921f0d`, mapping entry отсутствует.

```text
identity_guard BLOCKED session=c*******************************1
tool=mcp__mariyam_backend__get_balance_summary
code=CRON_IDENTITY_UNRESOLVED
```

Результат: PASS, downstream MCP = 0.

### Mapped test-user + forged model user_id

Job `0051e51b0ac3`, private mapping указывал на test-user с ролью `oyijon`;
prompt передавал заведомо чужой `user_id`. Значения ID не логировались.

```text
identity_guard cron_job=0051e51b0ac3
tool=mcp__mariyam_backend__get_balance_summary
decision=oyijon_self
```

Результат: PASS. Operator assertion сопоставил mapping с exact test-user из
`users`; middleware проигнорировал forged argument, принудительно передал
mapping user и read-only backend call завершился успешно.

### Job definition mutated after fingerprint

Job `d64220b57a0c`; mapping/fingerprint созданы до изменения имени job.

```text
identity_guard BLOCKED session=c*******************************3
tool=mcp__mariyam_backend__get_balance_summary
code=CRON_JOB_UNTRUSTED
```

Результат: PASS, downstream MCP = 0.

### Tool outside allowlist

Job `d4456d3e77f5`; mapping разрешал другой read-only tool.

```text
identity_guard BLOCKED session=c*******************************8
tool=mcp__mariyam_backend__get_quran_progress
code=CRON_TOOL_FORBIDDEN
```

Результат: PASS, downstream MCP = 0.

Во всех прогонах MCP discovery оставался равен 21.

## Telegram regression

Из тестового Telegram-аккаунта отправлен обычный read-only запрос баланса.
Первый turn не дошёл до tool-call из-за transient model-provider failure.
Один контролируемый повтор завершился нормально:

```text
identity_guard tool=mcp__mariyam_backend__get_balance_summary
actor_role=oyijon actor_user_id=<masked>
requested=<masked> effective=<masked> decision=oyijon_self
tool mcp__mariyam_backend__get_balance_summary completed
Turn ended: reason=text_response
Telegram: Flushing text batch
```

Ответ пользователю был нормальным; финансовые значения, Telegram ID и session
ID в evidence не записаны.

## Cleanup и baseline

```text
temporary jobs:                 0
temporary output directories:  0
temporary cron sessions:       0
temporary cron messages:       0
private mapping entries:       0
Gateway:                       active
PostgreSQL:                    healthy
admin row fingerprint:         unchanged
rows created/updated since deploy in all mutable domain tables: 0
tools/dispatch/discovery:       21/21/21
SOUL SHA-256:                   0ec1eeed95ec90030f1e7e11dd88a1428076cdd44a9a8ffa93c57c4b5726012f
```

Первичный raw `pg_dump` hash нельзя использовать как equality proof:
PostgreSQL добавляет случайные `\restrict`/`\unrestrict` tokens, поэтому даже
два последовательных read-only dump дают разные hashes. После исключения этих
служебных строк повторный hash стабилен; дополнительно проверены zero
created/updated rows и неизменный admin fingerprint.

## Rollback readiness

Rollback описан, но **не выполнялся**. Из service-user shell:

```bash
set -e
P=/home/timeagent/.hermes/profiles/mariyam_oyijon
B=$P/backups/imp03-20260723T184146Z
systemctl --user stop hermes-gateway-mariyam_oyijon.service
mv "$P/plugins/mariyam_identity_guard" "$B/mariyam_identity_guard-1.1.0.rollback"
cp -a "$B/mariyam_identity_guard.dir" "$P/plugins/mariyam_identity_guard"
cp -p "$B/profile.env.before" "$P/.env"
systemctl --user start hermes-gateway-mariyam_oyijon.service
systemctl --user is-active hermes-gateway-mariyam_oyijon.service
```

Ожидаемый результат rollback: identity plugin 1.0.4 и прежний private profile
environment; cron mapping файл может остаться неиспользуемым private-файлом
`0600`.
