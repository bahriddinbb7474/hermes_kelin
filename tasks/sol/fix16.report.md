# fix16 — n1n primary, routing rotation, malformed provider responses

Дата deploy и проверки: 2026-08-30, Asia/Tashkent. VPS `time-agent-prod`,
профиль `mariyam_oyijon`, Hermes v0.18.2.

## Итог

Primary возвращён на n1n с новым ключом заказчика; fallback остаётся той же
Luna через OpenRouter. Добавлен только профильный `mariyam_runtime_guard`,
Hermes core не менялся. Gateway после deploy `active`, `NRestarts=0`.

Live agent-вызов (не Telegram, source `tool`) подтверждён `agent.log`:

```text
2026-08-30 20:00:40 OpenAI client created ...
provider=custom base_url=https://api.n1n.ai/v1 model=gpt-5.6-luna
2026-08-30 20:00:45 API call #1: in=13992 out=8 total=14000 latency=3.9s
2026-08-30 20:00:45 Turn ended: ... finish_reason=stop ... response_len=4
```

## 1. Фактический маршрут до и после

### До

Production `config.yaml` содержал только legacy:

```yaml
model: gpt-5.6-luna
provider: custom
```

`base_url` отсутствовал. В Hermes v0.18.2 bare `custom` — неполный routable
identity: resolver использовал дефолтный OpenRouter endpoint, а credential pool
`openrouter` из `auth.json` давал ключ. Поэтому наличие `N1N_API_KEY` в `.env`
само по себе маршрут не меняло. До fix16 resolver и `agent.log` показывали:

```text
provider=custom base_url=https://openrouter.ai/api/v1 model=gpt-5.6-luna
```

### После

Маршрут закреплён именованным custom provider без секрета в YAML:

```yaml
model:
  default: gpt-5.6-luna
  provider: custom:n1n
providers:
  n1n:
    name: n1n
    base_url: https://api.n1n.ai/v1
    key_env: N1N_API_KEY
    default_model: gpt-5.6-luna
    transport: chat_completions
fallback_providers:
  - provider: openrouter
    model: openai/gpt-5.6-luna
```

Resolver после deploy:

```text
custom https://api.n1n.ai/v1 custom_provider:n1n
```

Новый `N1N_API_KEY` проверен прямым `GET /v1/models`: HTTP 200. Затем один
разрешённый заказчиком agent-вызов прошёл через n1n, что подтверждено строками
выше. OpenRouter не вызывался в этом успешном ходе.

## 2. auth.json, .env и мусорный cache

До backup credential pools были `openai-api` и `openrouter`. После:

```text
auth.json credential_pool = [openrouter]
```

Неиспользуемый `openai-api` удалён. n1n получает ключ строго через
`providers.n1n.key_env: N1N_API_KEY`; значение остаётся только в профильном
`.env`, mode 0600. При ранней диагностике в первой строке `.env` была замечена
случайно вставленная команда `sudo nano .../.env`; параллельный imp12 уже
удалил её до controlled deploy fix16. Текущий файл начинается с комментария и
корректно загружается.

`.models_dev_cache_wb3y4ug4.tmp` сохранён в первом backup и удалён из профиля.

## 3. Ротация routing при daily reset

Live root cause виден в журнале 23–30 августа: каждый день Hermes писал, что
route указывает на ended session, удалял stale entry, после чего generic DB
recovery снова открывал ту же `agent_close` session. Поэтому route Ойижон
оставался на сессии 04.08, а input вырос выше 100 тысяч токенов.

`mariyam_runtime_guard` оборачивает
`gateway.session.SessionStore.get_or_create_session`. До generic recovery он
вызывает штатный `_should_reset`; когда due reason = `daily`, выполняет
`reset_session(session_key)`. Штатный метод атомарно:

1. создаёт новый session id;
2. заменяет route в state.db и legacy `sessions/sessions.json`;
3. завершает старую сессию с `session_reset`;
4. сохраняет peer metadata.

Затем guard сохраняет `was_auto_reset`, `auto_reset_reason=daily` и факт
активности. `session_reset` уже совпадал с canonical snippet и не менялся:

```yaml
session_reset: {mode: daily, at_hour: 2, notify: false}
```

Тест-сторож проверяет точку `SessionStore.get_or_create_session` и служебные
методы `_should_reset`, `reset_session`, `_save_entries`. При переименовании
Hermes тест падает.

Ближайшая фактическая ночная ротация будет при первом сообщении после 02:00
31.08. На момент deploy это событие ещё не наступило; проверка нового session id
и тысяч, а не десятков тысяч input tokens остаётся post-deploy наблюдением.

## 4. Empty length без usage = provider failure

Guard оборачивает обе реальные provider-точки:

- `run_agent.AIAgent._interruptible_api_call`;
- `run_agent.AIAgent._interruptible_streaming_api_call`.

Malformed классифицируется только при одновременном выполнении условий:

```text
finish_reason=length
content пуст
reasoning/reasoning_content/reasoning_details пусты
tool_calls пусты
usage отсутствует
```

Настоящий partial content, reasoning, tool call или даже нулевой, но
присутствующий usage не попадает под правило. Первый malformed повторяется
один раз на текущем provider. Второй поднимается как provider-call failure;
дальше штатный Hermes выполняет retry/fallback. Если цепочка исчерпана,
gateway формирует provider error через `_gateway_provider_error_reply`, а
существующий `mariyam_outbound_filter::_ProviderFailureReply` заменяет его для
human chat на утверждённую узбекскую фразу. Программные поверхности сохраняют
диагностику.

Plugin discovery происходит во время импорта `run_agent.py`. Первая версия
deploy попыталась импортировать `AIAgent` слишком рано; офлайн-приёмка поймала
циклический import до live-теста. Исправлено: routing wrapper ставится сразу,
provider wrappers — через `pre_llm_call` после завершения импорта. После
повторного приватного backup и deploy ошибок загрузки нет; plugin list =
`mariyam_runtime_guard enabled 1.0.0`.

Тест-сторож импортирует установленный Hermes и требует наличия обеих AIAgent
точек и routing-точки. Отдельный offline runtime probe дважды подал malformed и
получил `MalformedProviderResponseError=true`; сетевой malformed намеренно не
провоцировался.

## 5. Проверки

- `GET https://api.n1n.ai/v1/models` с профильным ключом: HTTP 200;
- `hermes config check`: PASS;
- semantic resolver: `custom`, `https://api.n1n.ai/v1`,
  `custom_provider:n1n`;
- live agent call: n1n, `finish_reason=stop`, in/out `13992/8`;
- `mariyam_runtime_guard` 1.0.0: enabled;
- local regression: `54 passed` (`test_fix16_runtime_guard.py` + прежний
  `test_mariyam_skill_protection.py`);
- Python compile и `git diff --check`: PASS;
- gateway: `active`, `NRestarts=0`.

Приватные rollback bundles (файлы mode 0600):

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix16-20260830T145500Z
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix16-20260830T145940Z
```

## 6. Scope и что осталось

Не менялись `SOUL.md`, MEMORY/USER, cron-промпты, `get_daily_news`, семейная БД,
Telegram allowlist и Hermes core. imp12 был установлен и его gateway restart
завершён до начала fix16 deploy.

Осталось наблюдение ближайших реальных событий:

- первый Telegram turn после 02:00 — новый route/session и малый input;
- ближайшие штатные agent-cron слоты — отсутствие повторного empty-length или,
  если provider снова его отдаст, строки guard + штатное переключение fallback.
