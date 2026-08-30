# fix15 — восстановление agent-контура Mariyam

Дата диагностики и восстановления: 2026-08-30, Asia/Tashkent. VPS:
`time-agent-prod`, профиль `mariyam_oyijon`.

## Итог

Диалог и agent-cron восстановлены без смены модели, без изменения `SOUL.md`,
памяти, конфигурации или семейной БД. Сделан приватный backup, сброшена только
зависшая routing-запись Telegram-сессии Ойижон и перезапущен только
`hermes-gateway-mariyam_oyijon.service`.

Живая проверка после восстановления:

- Telegram Web → реальный бот `Мариям`: ответ за 3,8 с, узбекская кириллица,
  `finish_reason=stop`, `in=15392`, `out=53`;
- `mariyam_daily_morning`: штатный ручной запуск `succeeded`, нормальный текст;
- `mariyam_obligation_reminders`: штатный ручной запуск `succeeded`, корректный
  `[SILENT]`, потому что подходящих обязательств на момент прогона не было.

## 1. Инвентаризация дрейфа 29 августа

### Репозиторий и SOUL

- repo `deploy/hermes_profile_mariyam_oyijon/SOUL.md`:
  `fc34275c1ae882d3e9a19d9368a88b28071078ad9e310e1fb769dec76287eb38`,
  33 193 байта;
- VPS `~/.hermes/profiles/mariyam_oyijon/SOUL.md`: тот же полный SHA и размер,
  mtime `2026-08-03 23:05:01 +05`, mode `0444`;
- `SOUL.md` 29 августа не менялся.

`/opt/time-agent` не содержит файлов с mtime после `2026-08-29 00:00`.
Существующий git-drift там старше окна: изменён `docker-compose.yml`, лежат
`docker-compose.override.yml.applied-by-ta-imp03` и
`docker-compose.override.yml.backup`. В fix15 эти файлы не трогались.

### Что меняли 29 августа вне GitHub

1. `config.yaml` получил mtime `2026-08-29 21:34:20 +05`, но его SHA
   `53940fc7...` полностью совпадает с backup
   `backups/imp08-20260802T101055Z/config.yaml.before`. То есть файл лишь
   переписали/коснулись, семантического diff нет.
2. `auth.json` изменён `2026-08-29 22:15:08 +05`. Сейчас в нём credential pools
   `openrouter` и `openai-api`; приватного backup перед этой правкой нет.
3. Рядом остался временный файл `.models_dev_cache_wb3y4ug4.tmp`, 98 370 байт,
   mtime `22:15:09`. Это недокументированный мусор вчерашней диагностики; он не
   удалялся, потому что диагнозу не мешает.
4. `.bundled_manifest` обновлён в `22:45`; в `state.db` видны CLI-пробы
   `21:47–22:45`. Первые пробы дали те же четыре пустых `length`, последние две
   завершились успешно. До fix15 профильного backup за 29 августа не было.
5. Gateway 29 августа не рестартовали: до fix15 `ActiveEnterTimestamp` был
   `2026-08-04 03:18:40 +05`, `NRestarts=0`. Поэтому вчерашняя работа не
   включала контролируемый restart/приёмку долгоживущего gateway.

В `~/.bash_history` нет команд, объясняющих правку production-профиля; найденные
provider-команды относятся к другим каталогам (`/opt/hermes-assistant` и
`/opt/time-agent`). Ничего по ним не откатывалось.

### Версия Hermes

Hermes не обновлялся в дни сбоя:

```text
Hermes Agent v0.18.2 (2026.7.7.2)
upstream 1e21fe86; local 3b2ef789 (+1 carried commit)
Python 3.11.15; OpenAI SDK 2.24.0
```

`agent/conversation_loop.py` и `hermes_cli/main.py` имеют mtime 11 июля;
checkout чист, кроме служебного untracked `.install_method`.

## 2. Причина с цифрами

### Фактический provider

Во всех исследованных падениях реальный маршрут из `agent.log`:

```text
provider=custom base_url=https://openrouter.ai/api/v1 model=gpt-5.6-luna
```

То есть описание задачи про активный n1n уже не соответствует runtime. Fallback
также ведёт на OpenRouter и ту же `openai/gpt-5.6-luna`, поэтому независимого
резерва нет.

Баланс OpenRouter исправен:

- `/api/v1/credits`: HTTP 200, total credits `$10`, usage `$6.522470629`;
- `/api/v1/key`: limit `$3`, remaining `$2.99140291`, key не free-tier и без
  срока истечения.

n1n не является рабочим резервом: запрос `/v1/models` с текущим
`N1N_API_KEY` вернул HTTP 401; два billing URL вернули 404. Баланс через этот
ключ проверить невозможно, но это не причина наблюдавшихся ответов: они
фактически шли через OpenRouter.

### Первый сбой и пять характерных ходов

Первый успешно завершённый ход перед серией: 28.08 21:26, основной Telegram
контекст `in=89372`, `out=8`, `finish_reason=stop`. Первый терминальный сбой:
29.08 примерно 05:05:42–05:05:54 после обработки фотографий. До него 27.08
20:31 был единичный оборванный stream, но Hermes восстановился следующим
вызовом; это не терминальный `truncated after 4`.

Примеры терминальных падений:

| Время +05 | Ход | System prompt | Результат четырёх ответов |
|---|---|---:|---|
| 29.08 05:05 | Telegram, фото | 29 131–29 133 chars | 4 × `length`, все поля пусты |
| 29.08 05:25 | `Тушинмадим` | тот же | 4 × `length`, все поля пусты |
| 29.08 08:00 | `mariyam_daily_morning` | 29 133 chars | 4 × `length`, все поля пусты |
| 29.08 09:15 | `mariyam_obligation_reminders` | 29 133 chars | 4 × `length`, все поля пусты |
| 30.08 08:00 / 09:15 | те же два cron | 29 131 chars | по 4 × `length`, все поля пусты |

Для каждого такого assistant-row в `state.db`:

```text
finish_reason=length
len(content)=0
len(reasoning)=0
len(reasoning_content)=0
len(reasoning_details)=0
token_count=NULL
```

В `agent.log` для них нет обычной строки `API call ... in=... out=...`: provider
не передал usable usage. Hermes v0.18.2 затем воспринимает каждый такой ответ
как честное достижение output cap, добавляет continuation prompt и после
четвёртого возвращает `Response remained truncated after 4 continuation
attempts`.

Это **не настоящее исчерпание output tokens и не reasoning budget**. Успешный
повтор утреннего cron 30.08 08:15 на том же provider дал:

```text
call 1: in=12267 out=102
call 2: in=16274 out=301
finish_reason=stop
```

Успешный повтор obligations 09:30 дал `out=142` и `out=70`, затем
`finish_reason=stop`. В успешных строках `state.db` reasoning реально есть
(например 402/425 символов), в ошибочных он нулевой. Поэтому корень —
периодический malformed/empty `finish_reason=length` на маршруте OpenRouter,
усиленный тем, что старый gateway жил с 04.08 и routing Ойижон продолжал
указывать на уже завершённую сессию.

### Почему это не окно контекста

- Старый Telegram-диалог действительно разросся примерно до 89 тыс. input
  tokens, но свежие cron-сессии с ~12 тыс. input tokens падали идентично.
- Успешные повторы тех же cron имели те же 12–16 тыс. input tokens.
- System prompt свежих cron стабилен: 29 131–29 191 символ, а не 100К+.

Гипотеза переполненного окна отвергнута как общая причина.

### Память

Текущие файлы:

- `MEMORY.md`: 3 708 байт, 30 строк; backup 02.08: 1 228 байт, 2 строки;
- `USER.md`: 2 861 байт, 15 строк; backup 02.08: 2 094 байта, 10 строк.

Рост обоих файлов вместе около 3,2 КБ. Это не объясняет падение свежего cron и
не требует аварийной обрезки. Память не менялась: семейные факты, родственные
связи, восемь внуков, обязательства и план сохранены как были.

## 3. Что изменено

Перед изменением gateway остановлен, создан приватный backup mode 0600:

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix15-20260830T133000Z
```

Сохранены `config.yaml`, `auth.json`, `sessions/sessions.json`, `state.db`.

Минимальный обратимый diff runtime:

1. из `sessions/sessions.json` удалена ровно routing-запись
   `agent:main:telegram:dm:<Ойижон>` → старая session
   `20260804_043137_906140b4`;
2. из `state.db.gateway_routing` удалена ровно соответствующая строка;
3. сами session/messages не удалялись (`history_deleted=false`);
4. запущен только `hermes-gateway-mariyam_oyijon.service`.

После запуска: service `active`, новый PID `4124559`, `NRestarts=0`, Time-Agent
container `running`, restart count `0`, SOUL SHA не изменился.

Конфиг в репозитории не менялся: текущий production `config.yaml` уже полностью
совпадает с августовским backup, а явный output limit не лечит пустой ответ без
usage/reasoning. Поэтому config snippet и commit с конфигурацией не нужны.

## 4. Живая проверка

### Telegram

Через авторизованный Telegram Web в реальный чат бота отправлено:

> Ассалому алайкум, яхшимисиз? Ўзбекча кириллда қисқа жавоб беринг.

Ответ:

> Ва алайкум ассалом, Ойижон! Яхшиман, раҳмат 😊 Сиз-чи?

`agent.log`: `in=15392`, `out=53`, `finish_reason=stop`, response 53 chars,
3,8 с, маршрут OpenRouter.

### Cron

30.08 около 18:34 +05:

- `hermes ... cron run e5a1c6506d59` → `Ran now: succeeded`; две API call:
  `12267/96` и `16185/246`, финал `stop`, 420 chars;
- `hermes ... cron run 668fbef5b5d5` → `Ran now: succeeded`; две API call:
  `12111/164` и `12424/8`, финал `stop`, результат `[SILENT]`.

Один успешный прогон сам по себе не доказывает исчезновение периодической
ошибки провайдера, но одновременно прошли три независимых agent-хода, включая
долгоживущий gateway и два свежих cron-процесса.

## 5. Потерянные записи — в БД не внесены

По точным inbound-строкам `agent.log` в окне сбоя отсутствуют последующие
успешные tool calls. Заказчику нужно дозанести:

### Расходы

- туйана — 200 000 сум;
- катык — 12 000 сум;
- укув куроллари — 210 000 сум;
- стоматолог — 200 000 сум;
- такси — 59 000 сум;
- тухум — 42 000 сум;
- нон — 8 000 сум.

### Напоминания

- стоматолог — 01.09.2026, 15:00;
- стоматолог — 05.09.2026, 16:00.

В `cron/jobs.json` соответствующих стоматологических задач на 01.09/05.09 нет.
Повторяющиеся строки в логе — это повторные попытки одной и той же просьбы,
не дополнительные напоминания.

## 6. Что осталось

- OpenRouter может снова эпизодически вернуть пустой `length`; для полного
  постоянного исправления нужен отдельный патч Hermes: response с `length`, но
  одновременно пустыми content/reasoning/tool_calls и отсутствующим usage,
  классифицировать как malformed provider response/retry/fallback, а не как
  output-cap continuation. Core в аварийном fix15 не менялся.
- n1n credential сейчас отвечает 401 и не является рабочим независимым
  резервом. Возвращать n1n или менять модель можно только отдельным решением.
- Завтрашние штатные слоты 08:00 и 09:15 остаются полезной контрольной точкой;
  watchdog продолжит штатный retry и alert при повторе.
