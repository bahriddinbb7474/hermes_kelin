# fix10 — отчёт

Дата: 2026-08-02. Результат: **исправлено и развёрнуто**.

## Диагностика

До любых изменений прямой вызов `get_tashkent_weather` и чтение
`/opt/hermes-mariyam/var/external-data-cache.json` показали последнюю успешную
weather-запись:

```text
cache_entry[weather_tashkent]={"data":{"city":"Tashkent","condition_ru":"ясно","feels_like_c":31.8,"humidity_percent":16,"observed_at":"2026-07-27T17:25:11+00:00","source":"OpenWeather","source_url":"https://openweathermap.org/city/1512569","temperature_c":34.1,"wind_m_s":6.4},"fetched_at":"2026-07-27T17:26:42.933998+00:00"}
same_tashkent_day[weather_tashkent]=False
```

Следовательно, последнее успешное обновление было 27 июля в 22:26
Asia/Tashkent; начиная с 28 июля новые дневные запросы не могли получить свежую
погоду и честно возвращали этот fallback с `stale=true`. Сбой начался раньше
deploy imp11 от 1 августа 23:27 UTC, связи с imp11 нет.

`_same_tashkent_day()` работал правильно: для старой записи вернул `False`.
После ошибки `_daily_cached()` по действующему контракту брал последнюю удачную
запись и ставил `stale=true`; причину upstream-кэша он намеренно не логировал.

## Точная причина

Ключ не истёк, квота не закончилась, OpenWeather не блокирует VPS:

```text
openweather_key_present=True length=32
openweather_live=PASS status=200 body={"cod":200,"dt":1785642902,"main":{"feels_like":30.77,"grnd_level":958,"humidity":15,"pressure":1005,"sea_level":1005,"temp":33.1,"temp_max":33.1,"temp_min":33.1},"weather":[{"description":"ясно","icon":"01d","id":800,"main":"Clear"}]}
```

Private `.env` и `/opt/hermes-mariyam-secrets/backend.env` содержали непустой
`OPENWEATHER_API_KEY`, но:

```text
gateway_initial_env_has_openweather=False
mcp_env_names=['DATABASE_URL', 'MCP_TRANSPORT', 'PYTHONPATH']
```

Hermes запускает stdio MCP с явным allowlist `mcp_servers.mariyam_backend.env`.
Поэтому даже наличие ключа в private env не передавало его в `backend.server`.
Удачный cache от 27 июля был создан controlled deploy-прогоном с вручную
загруженным env; штатные cron-процессы этот env не наследовали.

## Исправление

Backend и cache-логику менять не понадобилось.

1. Добавлен systemd drop-in
   `deploy/hermes-gateway-mariyam_oyijon.service.d/10-profile-env.conf`, который
   загружает существующий private profile `.env`. Drop-in выбран потому, что
   Hermes пересоздаёт основной generated gateway unit при `config check`.
2. `deploy/fix10_patch_mcp_env.py` идемпотентно добавляет в
   `mcp_servers.mariyam_backend.env` только placeholder
   `${OPENWEATHER_API_KEY}`. Секрет в `config.yaml`, git и отчёт не попадает;
   скрипт сравнивает YAML до/после и отказывается менять что-либо ещё.
3. Обновлена deploy-инструкция и добавлены regression tests для drop-in,
   отсутствия секрета в unit, узкого и идемпотентного config patch.

На VPS сохранён backup:

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix10-20260802T040323Z
```

`config check=PASS`; перезапущен только
`hermes-gateway-mariyam_oyijon.service`. Итог:

```text
ActiveState=active
SubState=running
ExecMainStatus=0
NRestarts=0
mcp_placeholder_exact=True
gateway_env_has_openweather=True
exact backend.server: has_database_url=True, has_openweather=True
```

SOUL, cron schedule/prompts, guard-плагины, fallback providers, значения
ключей, session reset, outbound filter, imp11, планы и расходы не менялись.
Ручной job в семейном профиле не запускался и Telegram-сообщение семье не
отправлялось.

## Проверка 1 — прямой weather tool

После живого ответа OpenWeather tool перезаписал дневной кэш и дословно вернул:

```text
weather_tool={"cache":{"fetched_at":"2026-08-02T03:56:47.960313+00:00","hit":false,"stale":false},"city":"Tashkent","condition_ru":"ясно","feels_like_c":30.8,"humidity_percent":15,"observed_at":"2026-08-02T03:55:02+00:00","ok":true,"source":"OpenWeather","source_url":"https://openweathermap.org/city/1512569","temperature_c":33.1,"wind_m_s":2.2}
```

Итог: `ok=true`, `stale=false`, наблюдение и fetched_at сегодняшние,
температура 33,1 °C.

## Проверка 2 — утренний cron в mariyam_test

В пустом `mariyam_test` создан временный job с точным `06_morning.md`, local
delivery и без Telegram token. Job после прогона удалён. Сохранённая секция
Response дословно:

> Хайрли тонг, Ойижон, кунингиз баракали бўлсин! Тошкентда ҳаво очиқ, ҳарорат 33,1 даража экан, бундай иссиқда сув ичиб, ўзингизни авайлаб юрган яхши-а. Кун.уз хабарига кўра, талабалар ётоқхонасига жойлашиш учун аризалар қабули бошланибди. Батафсил айтайми ёки ўзингизни қизиқтирган нарсани сўранг — тезда билиб айтаман.

Проверки результата: температура `33,1` присутствует; `stale=true` отсутствует;
слова `кечаги`, `эскироқ`, `олдинги маълумот` отсутствуют.

Первичный n1n-вызов этого тестового job получил provider 5xx и Hermes один раз
автоматически перешёл на уже настроенный OpenRouter fallback. Повторный платный
прогон не выполнялся; fallback-конфигурация не менялась. CLI напечатал
`Ran now: failed`, хотя output имеет обычный заголовок (не `(FAILED)`) и полную
Response: это особенность Hermes manual-run с `repeat=1` — job удаляется до
повторного чтения `last_status`, поэтому `_execute_job_now()` видит пустую
запись. Содержательная acceptance погоды пройдена, семейная доставка не
использовалась.

## Намаз

Соседний Aladhan-кэш не залип. Дословно:

```text
cache_entry[prayer_tashkent_hanafi]={"data":{"asr":"17:32","calculation_method":"Muslim World League","city":"Tashkent","date":"02-08-2026","dhuhr":"12:29","fajr":"03:27","isha":"21:23","maghrib":"19:39","school":"Hanafi","source":"Aladhan","source_url":"https://aladhan.com/prayer-times-api","sunrise":"05:19"},"fetched_at":"2026-08-01T19:20:24.885984+00:00"}
same_tashkent_day[prayer_tashkent_hanafi]=True
prayer_direct=PASS
```

Дата Aladhan — 02-08-2026, Hanafi; прямой ответ совпал с кэшем.

## Тесты

Целевая регрессия:

```text
11 passed in 0.74s
```

Полный локальный запуск: `332 passed, 88 skipped, 9 failed`. Все девять
падений относятся к отсутствующему локальному Hermes Python 3.11/runtime, а не
к fix10: два `test_mariyam_effective_prompt`, шесть интеграционных тестов
`test_mariyam_identity_guard` и один
`test_real_hermes_chain_orders_identity_before_stage53_and_blocks_duplicate`.
На VPS runtime/config/systemd проверки прошли.

## Git и действия заказчика

Функциональный commit: `fa7b769` (`fix: pass weather key to Mariyam MCP`).
После добавления этого отчёта оба коммита отправлены в `origin/main`.

От заказчика ничего не требуется: ключ и OpenWeather исправны. Если внешний
API снова временно упадёт, действующий tool по-прежнему честно вернёт старый
cache с `stale=true`; отдельный мониторинг этого состояния не внедрялся без
согласования.
