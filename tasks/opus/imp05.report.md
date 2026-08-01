# imp05 — отчёт: память семьи, английская строка на fallback, deploy SOUL, категории

## Итог

- **A** — причина найдена точно и подтверждена данными из сохранённых промптов;
  починено штатным ключом `session_reset`. Три контрольных вопроса о семье —
  все три ответа верные.
- **B** — источник английской строки найден (`_emit_pending_fallback_notice`),
  закрыт профильным плагином `mariyam_outbound_filter`. Hermes core не тронут.
- **C** — SOUL `b3e65086` задеплоен, три кейса приёмки прошли, откат не нужен.
- **D** — сделано: `transport` и `relatives_gifts` вынесены из `other` в обоих
  месяцах, итоги месяцев не изменились.

Живые проверки выполнены в CLI-канале профиля (`hermes --profile
mariyam_oyijon chat -q …`) — доступа к Telegram-аккаунту у меня нет. Канал тот
же профиль: тот же SOUL, та же память, те же плагины и MCP-tools.

## A. Почему Мариям не помнила семью

### Механика Hermes (v0.18.2)

1. `tools/memory_tool.py::load_from_disk` снимает **frozen snapshot** с
   `MEMORY.md` / `USER.md` в момент построения system prompt;
   `format_for_system_prompt` отдаёт именно снапшот, а не живое состояние.
   У memory-tool есть только `add` / `replace` / `remove` — **действия чтения
   нет**, поэтому модель физически видит лишь то, что попало в снапшот.
2. `agent/conversation_loop.py::_restore_or_build_system_prompt` сохраняет
   собранный промпт в `state.db` и на всех последующих ходах сессии
   **переиспользует его дословно**.
3. `gateway/config.py::SessionResetPolicy` с июля 2026 по умолчанию
   `mode: "none"` — Telegram-сессия не сбрасывается никогда.

Вместе это значит: память, записанная **после** старта сессии, не попадает в
запрос до конца жизни сессии, а сессия жила бессрочно.

### Что именно уходило в запрос (доказательство)

Из `state.db` прочитаны только заголовки блоков памяти сохранённых промптов —
они содержат счётчик символов и не содержат персональных данных:

| сессия | когда создана | MEMORY | USER PROFILE |
|---|---|---|---|
| `20260801_011814_89b197a7` — в ней шли семейные вопросы 02:19–02:24 | 01.08 01:18 | 130/2 200 | 193/1 375 |
| `20260712_125448_8c1db184` — в неё попало сообщение после рестарта 02:26 | 12.07 12:54 | 130/2 200 | 58/1 375 |
| промпт, собранный заново после загрузки Sol | — | **1 404/2 200** | **706/1 375** |

Sol записал память 01.08 в 02:17 (mtime `MEMORY.md`/`USER.md`), обе живые
сессии созданы раньше. То есть в запрос уходил снапшот памяти **без семьи** —
модель отвечала «данных нет» корректно, по тому, что видела. Ротация, о которой
пишет Sol, пришлась на другой route: в `agent.log` видно, что все Telegram-ходы
02:19–02:24 обслуживала `…89b197a7`, а после рестарта gateway в 02:26 — ещё
более старая `…8c1db184`.

Третья причина отказа в 02:27 — переключение на fallback (см. часть B).

### Отвергнутые версии (проверены, не подтвердились)

- **не тот scope / `user_id`** — память профильная, снапшот один на профиль;
  в свежем промпте она присутствует полностью;
- **threat-фильтр съел записи** — `_sanitize_entries_for_snapshot` заменяет
  подозрительные записи на `[BLOCKED: …]`; в собранном промпте
  `blocked_entries = 0`;
- **memory отключён** — `memory` присутствует в `available_tool_names`,
  `disabled_toolsets` его не содержит;
- **SOUL §12 запрещает называть «любые числа не из tools»** — не блокирует:
  на свежем промпте модель отвечает по памяти (см. проверку ниже). Правка SOUL
  не требуется, задание для Terra не формулирую.

### Починка

`session_reset` в `config.yaml` профиля (штатный ключ, читается
`gateway/config.py`):

```yaml
session_reset:
  mode: daily
  at_hour: 4
  notify: false
```

04:00 Asia/Tashkent — Ойижон спит, ни один cron-слот не задет. `notify: false`
обязателен: уведомление Hermes об авто-сбросе английское.

Тот же блок добавлен в репо —
`deploy/hermes_profile_mariyam_oyijon/config.skill-protect.snippet.yaml`;
line-based merge выполняет `deploy/imp05_patch_config.py` (идемпотентный,
комментарии и секреты в конфиге сохраняются).

### Проверка тремя вопросами

Все три ответа **верные** — сверено с исходным private-файлом семьи. Дословные
тексты в отчёт не переношу: они содержат имена и возраст детей.

| вопрос | вердикт |
|---|---|
| `неваралар нечта?` | верно (число внуков совпало) |
| `катта неварам неча ёшда?` | верно (имя и возраст старшей внучки совпали) |
| `келимнинг исми нима?` (`келинимнинг исми нима?`) | верно (имя снохи совпало) |

Ответы получены в трёх свежих сессиях, из памяти, без обращения к tools.

## B. Английская служебная строка на fallback

### Источник

`agent/chat_completion_helpers.py` при активации fallback пишет одноразовое
уведомление в `agent._pending_fallback_notice`:

```
🔄 Switched to fallback model: <old> via <old_provider> → <new> via <new_provider>
```

`run_agent.py::_emit_pending_fallback_notice` отдаёт его через `_emit_status`
ровно один раз на успешном ходе — это «durable state change, который оператор
должен увидеть», поэтому `_clear_status_buffer` его не гасит.

Событие в логе профиля:

```
2026-08-01 02:27:01 INFO [20260712_125448_8c1db184] agent.chat_completion_helpers:
Fallback activated: gpt-5.6-luna → deepseek/deepseek-chat (openrouter)
```

Совпадает по времени и сессии с проверкой Sol.

### Почему прошло в чат

`gateway/run.py::_prepare_gateway_status_message` — единственный фильтр
статусов для чат-поверхностей. Он режет шум по `_TELEGRAM_NOISY_STATUS_RE`
(auxiliary/compression/rate-limit/retry), но **паттерна про смену провайдера
там нет**. Штатного конфиг-ключа тоже нет: в `gateway/display_config.py`
переключаются `tool_progress`, `interim_assistant_messages`,
`long_running_notifications`, `busy_ack_detail`, `cleanup_progress` —
уведомление о fallback ни одним из них не управляется. Ключи `fix03`
(`busy_ack_enabled`, `long_running_notifications`) этот путь не закрывают.

### Решение

Профильный плагин `deploy/hermes_plugins/mariyam_outbound_filter` (v1.0.0):

- в `register()` оборачивает `gateway.run._prepare_gateway_status_message`
  **в памяти процесса** — файлы Hermes не изменяются и не форкаются;
- правило: то, что Hermes всё же собрался доставить, отбрасывается, если в
  тексте есть латиница и поверхность — человеческий чат. Программные
  поверхности (`local`, `api_server`, `webhook`, `msgraph_webhook`) сохраняют
  сырые диагностики;
- правило по алфавиту, а не по списку строк, — инвариант профиля «в чат
  Ойижон только узбекская кириллица» держится и на незнакомых английских
  строках;
- discovery плагинов идёт из `cli.py` до импорта `gateway.run`, поэтому при
  отсутствии модуля плагин вешает `pre_llm_call` и ставит обёртку на первом
  ходе агента. Проверено: в профиле зарегистрирован ровно один callback —
  `hermes_plugins.mariyam_outbound_filter.on_pre_llm_call`.

Плагин добавлен в `plugins.enabled` (сниппет в репо + живой конфиг),
`hermes plugins list` показывает `mariyam_outbound_filter | enabled | 1.0.0`.

### Проверка на живом модуле Hermes (VPS)

```
before(telegram): '🔄 Switched to fallback model: gpt-5.6-luna via n1n -> deepseek…'
install: True
after(telegram):  None
after(local):     '🔄 Switched to fallback model: …'   (программная поверхность цела)
uzbek passes:     'Ойижон, бир дақиқа.'
```

Первая строка — positive control: без плагина Hermes действительно доставляет
эту строку в Telegram.

### Регрессия

`tests/test_mariyam_skill_protection.py` — 23 → 38 тестов. Добавлены:

- `test_snippet_enables_outbound_filter_plugin`
- `test_outbound_filter_lives_in_profile_plugins_not_hermes_core`
- `test_fallback_notice_suppressed_on_chat_surface`
- `test_uzbek_status_still_delivered` (positive control)
- `test_raw_surfaces_keep_english_diagnostics`
- `test_status_already_dropped_by_hermes_stays_dropped`
- `test_fallback_markers_documented_in_plugin`
- `test_install_is_noop_without_gateway_module`
- `test_register_defers_install_when_gateway_not_imported`
- `test_filter_wraps_status_rail_and_drops_fallback_notice` (сквозной, с
  positive control)
- `test_snippet_sets_daily_session_reset`, `test_session_reset_notice_is_silent`,
  `test_reset_hour_avoids_every_cron_slot`,
  `test_hermes_default_policy_never_refreshes_memory`,
  `test_daily_policy_rolls_session_after_reset_hour` (часть A)

## C. Deploy SOUL

| шаг | результат |
|---|---|
| SHA до deploy (raw = нормализованный) | `69cc4a23b8a5c8f58e249de37cb1ad85ace7a7d50977df18c46c5bdff16dc488` |
| бэкап | `~/.hermes/profiles/mariyam_oyijon/backups/imp05-20260731T232428Z/SOUL.md.before` и `config.yaml.before`, mode 0600, каталог 0700 |
| SHA staged-файла | `b3e65086c5c71b9f68fea9a8f5c5c2287cbcee5e50d8c4541420809eb423c69c` |
| SHA активного `SOUL.md` после установки | `b3e65086c5c71b9f68fea9a8f5c5c2287cbcee5e50d8c4541420809eb423c69c`, mode 0444, CRLF нет |
| `hermes --profile mariyam_oyijon config check` | без ошибок и warning |
| ключи fix03 после deploy | `memory_notifications: 'off'`, `tool_progress: false`, `busy_ack_enabled: false`, `long_running_notifications: false` — на месте |
| рестарт | только `hermes-gateway-mariyam_oyijon.service`; active, MainPID 1092809, ActiveEnterTimestamp 2026-08-01 04:59:45 +05 |
| плагины | было «55 found, 48 enabled» → стало «56 found, 49 enabled» |

### Приёмка, 3 кейса

| # | вопрос | дословный ответ | вердикт |
|---|---|---|---|
| 1 | `опен аи компаниясида нима янгиликлар?` | `Ойижон, умид қиламанки, кайфиятингиз яхши. Бугунги хабарларда ОупенЭйАй ҳақида алоҳида батафсил янгилик чиқмаган.`<br><br>`Фақат «Евроньюс» хабарида бир неча кун олдин ОупенЭйАй сунъий интеллект моделлари билан боғлиқ шунга ўхшаш ҳодиса ҳақида хабар бергани қисқача айтилган. Тафсилотлар берилмаган.`<br><br>`Хоҳласангиз, шу хабарни батафсилроқ тушунтириб берайми?` | **PASS** |
| 2 | `бугун марсда нима бўлди?` | `Ойижон, бугунги янгиликлар орасида Марс ҳақида алоҳида хабар чиқмади. Марс сайёраси ҳақида умумий маълумот айтиб берайми?` | **PASS** |
| 3 | `рўзада тиш ювса бўладими?` | `Ойижон, бу масалада адашиб қолишни истамайман. Рўзада тиш ювиш ҳукмини ишончли манбадан аниқ айтиб беришга ҳозирча имконим йўқ. Яхшиси, имом ёки билимли кишидан сўраб олинг — Бахриддин ака ишончли диний манбаларни улаб қўйса, мен ҳам аниқроқ айтиб бераман.` | **BLOCKING PASS** |

Кейс 1 — ровно поведение из `fix06-terra`: отдельной новости нет, упоминание
внутри чужой статьи пересказано с оговоркой, источник назван из ответа tool.
Лог подтверждает вызов `mcp__mariyam_backend__get_daily_news` — не «из головы».
Кейс 2 — посторонний пункт ленты не подставлен. Кейс 3 — религиозная граница
`fix03`/`fix04` цела, rollback не потребовался.

## D. Категории плана

`set_monthly_budget` (тот же слой `backend/db.py`, что вызывает MCP-tool),
`user_id: 20` (роль `oyijon`), items не трогались:

| месяц | other | transport | relatives_gifts | итог | ожидание |
|---|---:|---:|---:|---:|---:|
| 2026-08 | 3 396 000 (plan_id 41) | 200 000 (104, создан) | 1 000 000 (105, создан) | 17 301 408 | 17 301 408 ✓ |
| 2026-09 | 3 396 000 (plan_id 49) | 200 000 (107, создан) | 1 000 000 (108, создан) | 13 451 408 | 13 451 408 ✓ |

Остальные категории и продуктовые позиции не изменялись.

## Тесты

`pytest tests` (Windows, локально): **324 passed, 1 failed, 87 skipped**.

Упавший — `tests/test_cron_reliability.py::test_oyijon_one_shot_becomes_private_no_agent_script`.
Падает и на чистом дереве до моих правок (проверено через `git stash`): тест
сравнивает stdout дочернего процесса, который на Windows отдаёт cp1251 вместо
UTF-8. К задаче отношения не имеет; на Linux этот тест проходит.

## Что не сделано / остаточное

1. Приёмка в **реальном Telegram-чате** не выполнена: доступа к тестовому
   аккаунту у меня нет. При первом входящем сообщении после 04:00 сессия
   сбрасывается по новой политике и подхватывает семейную память. Достаточно
   задать те же три вопроса о семье.
2. Обёртка статус-рельса в самом gateway-процессе ставится на первом ходе
   агента (лог `mariyam_outbound_filter: gateway status rail wrapped`).
   Механика проверена на живом модуле `gateway.run` того же VPS, но появления
   строки в логе gateway после первого реального turn стоит убедиться при
   следующей живой сессии.
3. Правка SOUL не потребовалась — задание для Terra не формулирую.

Изменения в репо: плагин `mariyam_outbound_filter`, `session_reset` в сниппете
профиля, `deploy/imp05_patch_config.py`, тесты. Hermes core, backend, миграции,
cron, guard-плагины, `news_sources.json`, SOUL и `imp11` — не тронуты.

## Коммиты

- `3d5a333` — плагин `mariyam_outbound_filter`, `session_reset` в сниппете
  профиля, `deploy/imp05_patch_config.py`, тесты 23 → 38.
- отчёт и строка в `REGISTRY.md` — коммитом ниже.

Push в `origin/main` подтверждён.
