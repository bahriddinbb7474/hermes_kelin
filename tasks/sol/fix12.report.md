# fix12 — отчёт

Дата: 2026-08-02. Результат deploy: **PASS**. Семантическая проверка
`mariyam_test`: **FAIL — модель не вызвала tool**, хотя новое правило находится
в её фактическом system prompt.

## Что было отставшим

До deploy оба профиля на VPS содержали SOUL с SHA-256:

```text
2daae3d1529db976036e503369b26580b05dc89b23c2703e1d393b93b34b6705
```

Это версия из `2456094` (`imp07`). По сравнению с ней в каноническом SOUL
отставала только правка Terra `fix09`, commit `bbf6429`: обязательный вызов
`get_tashkent_prayer_times` и вывод шести времён вместе с
`hijri_display_uz`. Других накопившихся изменений SOUL между активной версией
и `main` не обнаружено.

Перед deploy SHA репо-файла был сверен с заданием:

```text
f757c0ea4c20e8d3c949bda9749c5bdf6fcb1af26749d5fc8f651b644ea95149
```

## Backup и deploy

Семейный профиль:

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix12-20260802T053500Z
```

Тестовый профиль:

```text
/home/timeagent/.hermes/profiles/mariyam_test/backups/fix12-20260802T053500Z
```

Оба каталога имеют mode `0700`, оба `SOUL.md.before` — `0600`. Тестовый
профиль получил тот же канонический SOUL, иначе требуемая проверка продолжала
бы использовать старое правило. В обоих профилях `config check` прошёл.

После deploy фактический SHA в `mariyam_oyijon` и `mariyam_test` одинаков:

```text
f757c0ea4c20e8d3c949bda9749c5bdf6fcb1af26749d5fc8f651b644ea95149
```

Перезапущен только `hermes-gateway-mariyam_oyijon.service`. Состояние после
перезапуска:

```text
ActiveState=active
SubState=running
ExecMainStatus=0
NRestarts=0
```

## Защищённые настройки

Allowlist-проверка после deploy:

```text
busy_ack_enabled=false
long_running_notifications=false
memory_notifications=off
tool_progress=false
session_reset={mode: daily, at_hour: 2, notify: false}
primary=gpt-5.6-luna via custom (n1n)
fallback=openai/gpt-5.6-luna via openrouter
mariyam_outbound_filter=enabled, version 1.0.2
migration_006_active=true
```

SOUL, backend, migrations, tools, guards, cron-расписание, config,
`news_sources.json`, fallback и остальные перечисленные настройки не
редактировались: выполнена только установка уже закоммиченного SOUL.

## Проверка mariyam_test

Вопрос отправлен один раз только в изолированный `mariyam_test`, без Telegram,
с явно заданными `provider=custom`, `model=gpt-5.6-luna`:

```text
бугунги намоз вақтлари?
```

Дословный ответ:

> Ойижон, ҳозир намоз вақтларини аниқ олиб бўлмаяпман. Кейинроқ яна сўрасангиз, текшириб айтиб бераман.

Узкая проверка сохранённой тестовой сессии подтвердила:

```text
latest_test_prompt_has_fix12=true
latest_test_tool_call_count=0
messages=[user, assistant]
```

То есть deploy SOUL сработал и новое правило присутствовало в фактическом
system prompt, но Luna его не исполнила и не вызвала tool. Ожидание проверки
(шесть времён и `19 САФАР (1448)`) не выполнено. Повторный платный вопрос не
отправлялся, семейный профиль вручную не запускался, тестовых записей,
напоминаний или сообщений в чат заказчика не создавалось. Исправление поведения
потребовало бы новой правки за границами `fix12`, где прямо запрещено что-либо
менять.

## Git

Развёрнутый source commit: `bbf6429` —
`soul: always call prayer tool and report hijri date` (уже находился в
`origin/main`). Первичный commit этого отчёта: `REPORT_COMMIT`; metadata commit
с подстановкой hash также отправлен в `origin/main`.
