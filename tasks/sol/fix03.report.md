# fix03 — отчёт

## Результат

Для профиля `mariyam_oyijon` штатными ключами Hermes отключены все
англоязычные busy-уведомления, одноразовая подсказка `/busy` и соседний
heartbeat долгой задачи. Hermes core, `SOUL.md`, backend, tools, cron,
guard-плагины и `/opt/time-agent` этой задачей не изменялись.

## Где лежат строки и как они управляются

Проверен установленный на VPS Hermes Agent v0.18.2
(`upstream d9165d7a`, install dir
`/home/timeagent/.hermes/hermes-agent`):

- `gateway/run.py:1605-1606` переносит
  `display.busy_ack_enabled` в
  `HERMES_GATEWAY_BUSY_ACK_ENABLED`;
- `gateway/run.py:5510-5513` при значении `false` возвращается до отправки
  acknowledgement, но после обработки режима interrupt/queue/steer; входящее
  сообщение не теряется;
- `gateway/run.py:5574-5610` формирует строки `Steered into current run`,
  `Subagent working`, `Compressing context`, `Queued for the next turn` и
  `Interrupting current task`;
- `gateway/run.py:5612+` добавляет first-touch hint только к этому же busy ack;
- `agent/onboarding.py:37-60` содержит три варианта `First-time tip` и команды
  `/busy`;
- `cli-config.yaml.example` и
  `website/docs/user-guide/messaging/index.md` прямо документируют
  `display.busy_ack_enabled: false`: поведение входного сообщения сохраняется,
  исчезает только служебный ответ;
- соседний английский heartbeat `⏳ Working — N min` управляется штатным
  `display.long_running_notifications`; он также выключен для профиля.

Выбран штатный profile-level config, потому что он поддерживается Hermes
v0.18.2, действует только на Мариям и переживёт обновление Hermes. Форк и патч
Hermes не нужны.

## Изменение config

```yaml
display:
  memory_notifications: "off"
  busy_ack_enabled: false
  long_running_notifications: false
  tool_progress: false
```

Repo-source:
`deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml`.
На VPS ключи применены через `hermes --profile mariyam_oyijon config set`.
Перед изменением создан rollback-файл
`~/.hermes/profiles/mariyam_oyijon/backups/fix03-20260731/config.yaml.before`
с mode `0600`. Перезапущен только
`hermes-gateway-mariyam_oyijon.service`; итоговый статус `active`.

## Другие найденные строки того же слоя

Одним `busy_ack_enabled: false` закрыты:

- `⚡ Interrupting current task…`;
- `⏳ Queued for the next turn…`;
- `⏩ Steered into current run…`;
- `⏳ Subagent working…`;
- `⏳ Compressing context…`;
- все три `First-time tip` с `/busy interrupt|queue|steer|status`;
- optional detail: elapsed minutes, iteration и имя текущего tool.

Отдельным дешёвым ключом `long_running_notifications: false` закрыт
`⏳ Working — N min`. Уже существующий `tool_progress: false` закрывает
tool-progress и связанную onboarding-подсказку `/verbose`.

Найденные в tool-коде строки вида `MCP call interrupted: user sent a new
message` являются внутренним результатом tool для модели, а не прямым
gateway-сообщением в Telegram; общего profile display-переключателя для них
нет, дополнительный фильтр не добавлялся. Restart/resume notices относятся к
отдельному gateway lifecycle config, а не к busy/interrupt ack.

## Регрессия

В `tests/test_mariyam_skill_protection.py` добавлены:

- проверка обоих новых profile keys;
- модель раннего busy-ack gate;
- suppression test для acknowledgement и first-time tip;
- positive control: при Hermes default `true` обе строки и `/busy queue`
  действительно проходят;
- список соседних busy/queue/steer/status/heartbeat маркеров.

Полный прогон: **310 passed, 87 skipped** (`pytest -q`, 19.18 s). Для полного
локального прогона использован исправный bundled Python вместе с установленным
Hermes venv `site-packages`, потому что штатный Windows venv launcher ссылался
на удалённый Python; временный bootstrap после теста удалён.

## Живая проверка Telegram

Проверка выполнена через уже авторизованный второй аккаунт заказчика в чате
бота «Мариям», не на Telegram реальной Ойижон.

1. Длинный анализ расходов за 30 дней; во время активного ответа отправлено
   «Аввало энг катта харажатни бир жумла билан айтинг». Пришёл только ответ
   Мариям: `Энг катта харажатингиз — нонга 12 000 сўм.` Ни английской строки,
   ни `/busy` не было.
2. Перед повтором clean-state восстановлен командой
   `hermes --profile mariyam_oyijon config set
   onboarding.seen.busy_input_prompt false`. Затем запущен длинный анализ за
   24 месяца и через 10 секунд отправлено уточнение. Пришёл только ответ
   Мариям узбекской кириллицей: `Энг муҳим хулоса: сўнгги 24 ойда ...`.
   Английских busy/status строк и `/busy` не было.

После второго прогона `onboarding.seen.busy_input_prompt` остался `false`:
при выключенном busy ack Hermes возвращается раньше `mark_seen`, то есть тест
действительно прошёл из чистого состояния и first-time tip был подавлен, а не
просто считался уже показанным.

## Git

- `90330ea` — основной busy-ack fix, regression и docs;
- `f74c6c3` — соседний long-running heartbeat fix и regression;
- оба коммита успешно pushed в `origin/main`.
