# fix14 — отчёт: бот молчал из-за Telegram allowlist

Дата: 2026-08-02. Результат: **PASS — причина найдена и исправлена, gateway
принимает Telegram ID Ойижон**.

## Причина по журналу

Оба Telegram update дошли до профильного gateway, но были остановлены его
allowlist до создания сессии и до identity guard. Дословные строки журнала:

```text
2026-08-02T20:19:35+05:00 time-agent-prod python[1699032]: WARNING hermes_plugins.telegram_platform.adapter: [Telegram] Blocked unauthorized user 320418599 in chat 320418599
2026-08-02T20:21:55+05:00 time-agent-prod python[1699032]: WARNING hermes_plugins.telegram_platform.adapter: [Telegram] Blocked unauthorized user 320418599 in chat 320418599
```

То есть Telegram polling работал, сообщения были доставлены боту, но активный
`TELEGRAM_ALLOWED_USERS` всё ещё содержал прежний тестовый ID.

## Сверка ID и исправление

Состояние до исправления:

| место | значение |
|---|---|
| фактический отправитель по журналу | `320418599` |
| `users.telegram_id`, `users.id=20` | `320418599` |
| ключ `identity-map.json` | `320418599` |
| `.env`, `TELEGRAM_ALLOWED_USERS` | `65193215,7847505044` |
| `channel_directory.json` | `7847505044` |
| семь активных `cron/jobs.json` delivery target | `telegram:7847505044` |
| зеркало маршрутов `sessions/sessions.json` | активный ключ со старым ID |
| `state.db`, таблица `gateway_routing` | активный ключ со старым ID |

Перед изменениями создан точечный backup:

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix14-20260802T152941Z
```

Каталог имеет mode `0700`, файлы — `0600`. SHA-256 исходных файлов:

| файл | SHA-256 |
|---|---|
| `profile.env` | `48ebb5edf5f2c4ca7880d81e47a9aa21b8f207807da74853d7ad2a992a34e65b` |
| `channel_directory.json` | `b9a2f6f3235743da604066964bb350ffeeaac9eb44e68d157e44fac8b140cd72` |
| `cron-jobs.json` | `95d0390bdba4feb8065c88bddd9defc7605480204dda830f87354971a5bb6e0f` |
| `sessions.json` | `5361a86fd2caed6f2535732318ca01fd8a19dfd13cf248cb8392c4f977ef540a` |
| `state.db` | `b2d6045805494703811500aed01b294ee29885dbbbd6e900a144e33fb7370d63` |
| `identity-map.json` | `c40a6c93dadb044773e55c5aae3c0e3058673a9a5c61384fecc6c48ef6d2e1d5` |

Исправлено только значение идентификатора:

- allowlist стал `65193215,320418599`; администраторский ID сохранён;
- ID в каталоге каналов заменён на `320418599`;
- семь cron delivery target заменены на `telegram:320418599`;
- старый активный session route удалён из зеркала и `gateway_routing`, а не
  перенесён новой Ойижон со старым system prompt;
- БД и `identity-map.json` уже были правильными и не изменялись.

После `config check` перезапущен только
`hermes-gateway-mariyam_oyijon.service`. Проверка `/proc/<MainPID>/environ`
подтвердила, что работающий процесс загрузил новый allowlist без старого ID.

## Контроль после исправления

```text
database_identity=true
single_oyijon=true
admin_preserved=true
running_allowlist=true
august_expenses=1712208
august_expense_records=44
recurring_obligations=9
default_feeds_active=4
custom_feeds=0
migration_006=true
busy_ack_enabled=false
long_running_notifications=false
memory_notifications=off
tool_progress=false
session_reset=daily/02:00/notify=false
fallback=openrouter/openai-gpt-5.6-luna
mariyam_outbound_filter=1.0.2
SOUL=f3377d9c... mode=0444
```

Сервис:

```text
ActiveState=active
SubState=running
ExecMainStatus=0
NRestarts=0
```

После запуска gateway подключился к Telegram без `ERROR`/`CRITICAL`. Старые
заблокированные updates уже потреблены Telegram-шлюзом и повторно не придут,
поэтому нужен один новый живой запрос от Ойижон. От себя в её чат ничего не
отправлялось.

## Git

Коммит отчёта и подтверждение push будут добавлены после фиксации файла.
