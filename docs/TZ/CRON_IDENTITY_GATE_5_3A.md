# Stage 5.3A — cron identity gate для Hermes v0.18.2

Дата исследования: 2026-07-23.
Среда: VPS `time-agent-prod`, профиль `mariyam_oyijon`.

## Решение

Stage 5.3A можно реализовать безопасно без изменения Hermes core и backend, но
сначала существующий profile plugin `mariyam_identity_guard` нужно узко расширить
отдельной веткой cron identity. Текущий runtime уже безопасен: любой
user-scoped MCP call из cron блокируется до backend. Он пока не умеет разрешать
ни один доверенный cron job.

Целевая цепочка:

```text
server-created cron session
  → exact job_id из session_id
  → persisted session.source == "cron", без Telegram origin
  → неизменённая job definition + prompt текущего запуска
  → private cron mapping 0600
  → internal users.id + role + allowlisted tools
  → принудительная замена model-supplied user_id
  → MCP backend
```

Unknown job, отсутствующая/битая job definition, несовпавший prompt/fingerprint,
неразрешённый tool, битый mapping или небезопасные права файла дают fail closed
до MCP backend.

## Проверенные факты Hermes v0.18.2

### Версия и размещение

На VPS фактически запущен:

- `Hermes Agent v0.18.2 (2026.7.7.2)`;
- upstream `56e2ba5e`, local commit
  `3b2ef789dfcf92f5b7b18c08c59d25948e50857f`;
- Python `/home/timeagent/.hermes/hermes-agent/venv/bin/python`;
- Gateway:
  `python -m hermes_cli.main --profile mariyam_oyijon gateway run`;
- `HERMES_HOME=/home/timeagent/.hermes/profiles/mariyam_oyijon`.

### Как объявляются и хранятся jobs

Jobs можно создать:

- CLI: `hermes --profile mariyam_oyijon cron create ...`;
- модельным tool `cronjob` (в чате также доступна команда `/cron`);
- внутренним Python API `cron.jobs.create_job(...)`.

Отдельного scheduler-сервиса нет. В Gateway работает profile-scoped ticker.
Каноническое хранилище:

`~/.hermes/profiles/mariyam_oyijon/cron/jobs.json`

Output каждого запуска:

`~/.hermes/profiles/mariyam_oyijon/cron/output/<job_id>/<timestamp>.md`

Это подтверждено кодом VPS:

- `cron/jobs.py:54-71` — profile isolation и пути `cron/jobs.json`;
- `cron/jobs.py:1033-1113` — API создания и случайный 12-hex `job_id`;
- `cron/jobs.py:1178-1210` — persisted job fields: prompt, model/provider,
  script, schedule, repeat, state и timestamps;
- `tools/cronjob_tools.py:659-959` — create/list/update/remove/run для модели;
- `hermes_cli/subcommands/cron.py` — CLI create/edit/pause/resume/run/remove.

До теста профиль содержал `cron/` и ticker/lock-файлы, но `jobs.json` отсутствовал,
а `hermes cron list` отвечал `No scheduled jobs`.

### Что происходит при срабатывании

Обычный agent cron job создаёт новый, эфемерный `AIAgent`, а не продолжает
Telegram turn:

- `cron/scheduler.py:2611-2625` — создаётся отдельный agent и `SessionDB`;
- `cron/scheduler.py:2677-2679` — новый session id:
  `cron_<job_id>_<YYYYMMDD_HHMMSS>`;
- `cron/scheduler.py:2685-2719` — ставится cron marker, но inbound
  `HERMES_SESSION_PLATFORM/CHAT_ID/CHAT_NAME` намеренно очищаются;
- `cron/scheduler.py:3025-3044` — MCP tools discovery выполняется для cron;
- `cron/scheduler.py:3046-3077` — новый `AIAgent`, `platform="cron"`,
  `session_id=<cron session>`, тот же SOUL и profile tool/plugin configuration;
- `cron/scheduler.py:3134-3139` — запускается новый conversation;
- `cron/scheduler.py:3332-3355` — session завершается как `cron_complete`.

Delivery origin хранится в job отдельно и используется только после agent run.
Он не является sender identity (`cron/scheduler.py:2694-2714`). Поэтому наличие
Telegram delivery target нельзя использовать для авторизации.

В SQLite фактический тестовый cron session имел:

- `source="cron"`;
- `user_id=NULL`;
- `origin_json=NULL`;
- `end_reason="cron_complete"`.

Telegram session, напротив, получает persisted Telegram `origin_json`. Поэтому на
plugin-уровне типы turn различимы детерминированно.

### Middleware и MCP

Cron agent загружает те же profile plugins. `agent/tool_executor.py:293-321`
передаёт в `tool_execution` middleware не model arguments контекста, а
`agent.session_id`, `turn_id` и `tool_call_id`. Терминальный MCP call выполняется
только после всей middleware chain (`hermes_cli/middleware.py:192-210,240-302`).

Значит LLM может подделать поле `user_id` в JSON arguments, но не может заменить
middleware `session_id` или перепрыгнуть `next_call`.

## Controlled live probe

Создан один временный job `imp01-cron-identity-probe`, ID `3831b7e88a89`,
delivery `local`, repeat `1`. Prompt требовал ровно один read-only call
`get_balance_summary(user_id=999999999, period="month")`.

Фактический лог 2026-07-23 22:34 Asia/Tashkent:

```text
Job '3831b7e88a89': 21 MCP tool(s) available
conversation turn: session=cron_3831b7e88a89_20260723_223417 ... platform=cron
mariyam_identity_guard: identity_guard BLOCKED ... get_balance_summary code=IDENTITY_UNRESOLVED
tool ... get_balance_summary completed (0.00s, 161 chars)
Turn ended ... api_calls=2/6 ... tool_turns=1
```

Saved cron response был ровно `IDENTITY_UNRESOLVED`.

Почему downstream calls = 0: deployed
`mariyam_identity_guard/__init__.py:438-510` для user-scoped tool вызывает
`_resolve_actor(session_id, map)`. Resolver
`mariyam_identity_guard/__init__.py:257-288` принимает только persisted
`origin_json.platform == "telegram"`. При cron session он возвращает `None`, а
middleware возвращает safe error на строках 469-471, не вызывая `next_call`.
Фактическая длительность 0.00s и guard log подтверждают именно этот путь.

После прогона удалены:

- job record (one-shot Hermes убрал сам);
- `cron/output/3831b7e88a89`;
- созданный пустой `cron/jobs.json`, которого не было до теста;
- exact cron session и его 4 messages через `SessionDB.delete_session`.

Финальная проверка: scheduled jobs отсутствуют; matching sessions/messages = 0.
Production PostgreSQL, config, SOUL, plugins и `/opt/time-agent` не изменялись.

## Текущее поведение identity guard

Runtime plugin 1.0.4:

1. получает реальный `session_id` от Hermes;
2. для Telegram читает persisted session origin;
3. загружает private identity mapping;
4. валидирует весь mapping и mode `0600`;
5. вычисляет actor/target policy;
6. принудительно заменяет `user_id`;
7. только затем вызывает downstream MCP.

Текущий mapping:

`/opt/hermes-mariyam-secrets/identity-map.json`

Проверено без чтения содержимого: regular non-symlink, owner = service user,
file mode `0600`; parent non-symlink mode `0700`.

Для cron шаг 2 всегда возвращает unresolved. Это правильный pre-code baseline:
неизвестный cron job не проходит, но доверенных jobs ещё нет.

## Минимальное расширение profile plugin

Расширять существующий `mariyam_identity_guard`, не создавать router или второй
identity plugin. Telegram branch 1.0.4 оставить без изменения.

### Private mapping

Новый файл:

`/opt/hermes-mariyam-secrets/cron-identity-map.json`

Пример схемы (значения условные):

```json
{
  "version": 1,
  "jobs": {
    "0123456789ab": {
      "user_id": 2,
      "role": "oyijon",
      "purpose": "monthly_plan_cycle",
      "allowed_tools": [
        "get_monthly_budget_status",
        "approve_monthly_plan",
        "save_plan_note"
      ],
      "job_fingerprint_sha256": "<64 lowercase hex>",
      "prompt_sha256": "<64 lowercase hex>"
    }
  }
}
```

Обязательные ограничения:

- root schema и каждая запись валидируются целиком;
- `job_id` — exact 12 lowercase hex;
- `user_id` — positive int, `bool` запрещён;
- `role` для Stage 5.3A — только `oyijon` (self-only);
- `allowed_tools` — непустой уникальный allowlist только нужных user-scoped
  tools;
- hashes — exact 64 lowercase hex;
- unknown keys отклоняются, чтобы опечатка не ослабляла policy.

`job_fingerprint_sha256` считается по canonical JSON неизменяемых полей job:
`id`, `name`, `prompt`, `schedule`, `repeat`, `deliver`, `origin`, `skills`,
`script`, `no_agent`, `context_from`, `enabled_toolsets`, `workdir`, `model`,
`provider`, `base_url`. Для trusted identity jobs запретить `script`,
`context_from`, `workdir` и `no_agent`; delivery target должен быть явно
одобрен.

`prompt_sha256` связывает mapping с base prompt. Во время tool call plugin также
проверяет, что первое user-message текущего cron session содержит именно этот
base prompt. Это закрывает атаку `cronjob update → run malicious prompt →
restore definition`: одного совпадения текущего `jobs.json` недостаточно.

### Кто создаёт mapping

Только deploy operator:

1. создаёт production jobs через profile-scoped CLI;
2. читает выданные Hermes job IDs;
3. проверяет delivery/schedule/prompt;
4. вычисляет fingerprints локальным audited helper;
5. атомарно пишет mapping с `umask 077`, owner service user, mode `0600`;
6. выполняет offline negative/positive gates;
7. перезапускает только Mariyam Gateway, если path задаётся впервые.

LLM, Telegram turn и сам cron job mapping не создают и не меняют. Job,
созданный модельным `cronjob`, по умолчанию untrusted и не имеет identity.

Path задаётся как `MARIYAM_CRON_IDENTITY_MAP_FILE` в private profile `.env`;
содержимое не попадает в git, profile prompt, Telegram или logs.

### Resolver cron identity

Для user-scoped tool resolver выполняет по порядку:

1. Если persisted session — Telegram, использует неизменённую ветку 1.0.4.
2. Иначе требует session id regex
   `^cron_([0-9a-f]{12})_[0-9]{8}_[0-9]{6}$`.
3. В `state.db` требует exact row: `id=session_id`, `source="cron"`,
   `user_id IS NULL`, `origin_json IS NULL`.
4. Под shared lock безопасно читает profile `cron/jobs.json`, находит exact
   `job_id`, требует job active for the current run.
5. Безопасно загружает private cron mapping:
   absolute path, parent owner/mode `0700`, file owner, regular non-symlink,
   mode exactly `0600`, bounded size, strict JSON/schema.
6. Требует mapping entry, allowed tool, job fingerprint и prompt binding.
7. Создаёт trusted actor из mapping, игнорируя model `user_id`.
8. Применяет существующую self-only policy и заменяет effective `user_id`.
9. Только после этого делегирует следующему middleware/MCP.

Job ID не считается секретом. Доверие появляется только из сочетания
server-created cron session, persisted source, private mapping, immutable job
fingerprint и prompt текущего запуска.

### Fail-closed matrix

| Ситуация | Результат |
|---|---|
| Unknown/unmapped job | `CRON_IDENTITY_UNRESOLVED`, downstream 0 |
| Session pattern есть, но persisted source не `cron` | block, downstream 0 |
| Job отсутствует/удалён/не совпал fingerprint | `CRON_JOB_UNTRUSTED`, downstream 0 |
| Current session prompt не совпал | `CRON_JOB_UNTRUSTED`, downstream 0 |
| Tool не в entry allowlist | `CRON_TOOL_FORBIDDEN`, downstream 0 |
| Mapping missing/malformed/oversize | block всего cron identity, downstream 0 |
| File/parent symlink, wrong owner или mode | permissions error, downstream 0 |
| LLM передал другой `user_id` | значение игнорируется, mapping user принудителен |
| Ошибка resolver/plugin | safe generic error, downstream 0 |

Raw Telegram IDs, mapping body, internal target IDs и полные session IDs не
логировать. Допустимы masked session, job id, tool и safe error code.

## `max_turns=6` и duplicate breaker

Cron читает `agent.max_turns` из того же profile config
(`cron/scheduler.py:2898-2900`) и передаёт его как `AIAgent.max_iterations`
(`3046-3055`). Live probe подтвердил `api_calls=2/6`: лимит 6 действует и для
cron.

Существующий `mariyam_stage53_guard` загружается после identity guard. После
добавления trusted cron branch он будет получать уже принудительный `user_id`.
Его duplicate claim ключуется `session_id + turn_id + canonical tool args`,
поэтому:

- повтор идентичной mutation в одном cron turn блокируется;
- exception/unknown outcome оставляет durable claim и блокирует retry;
- explicit `ok:false` освобождает claim;
- TTL остаётся 30 минут.

Но каждый cron firing получает новый session id. Поэтому Stage 5.3 duplicate
breaker не даёт cross-run idempotency и сейчас не включает planned
`approve_monthly_plan`. Для Stage 5.3A повтор 25/27/28/1 должен дополнительно
останавливаться semantic state/unique constraints `monthly_plan_cycles` и
детерминированным контрактом нового tool. Cron identity gate нельзя считать
заменой business idempotency.

## Обязательные тесты перед deploy

Offline:

1. Telegram regression suite 1.0.4 без изменений.
2. Trusted cron: forged model `user_id` заменён mapping value.
3. Unknown job, fake cron-shaped Telegram session, missing session row.
4. Modified prompt/job definition и update-then-restore simulation.
5. Tool вне allowlist.
6. Missing, malformed, oversize mapping; wrong mode/owner; file/parent symlink.
7. Middleware exception → downstream counter remains 0.
8. Order identity → Stage 5.3 guard; duplicate same turn = one downstream.
9. Два разных cron firings показывают, что cross-run duplicate требует
   business idempotency.
10. `max_turns=6`, inventory/dispatch/discovery остаются `21/21/21`.

Controlled VPS:

1. backup private config/profile state;
2. один unknown-job read-only probe → block/downstream 0;
3. один mapped admin/test-user read-only probe → correct internal user;
4. forged `user_id` probe → тот же correct internal user;
5. unmapped/mutated job → block/downstream 0;
6. удалить все test jobs, outputs и cron sessions;
7. подтвердить Gateway active, production jobs unchanged, PostgreSQL baseline
   unchanged и `/opt/time-agent` untouched.

## Открытые вопросы перед кодом Stage 5.3A

- Production job IDs ещё не созданы; mapping создаётся только после утверждения
  окончательных prompts/schedules/delivery targets.
- Нужно утвердить точный allowlist каждого шага 25/27/28/1 и какой из них вообще
  имеет право на mutation.
- Контракт `approve_monthly_plan` должен определить cross-run idempotency на
  уровне `monthly_plan_cycles`; текущий Stage 5.3 guard этого не обеспечивает.

Эти вопросы не блокируют реализацию самого cron identity resolver, но блокируют
включение production Stage 5.3A jobs.
