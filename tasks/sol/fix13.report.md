# fix13 — отчёт

Дата: 2026-08-02. Результат: **PASS — актуальный SOUL развёрнут, данные не
изменены**.

## SHA до deploy

Канонический repo-файл перед выкладкой:

```text
5efff19dbbf824ba9d3736339e70dd0c8f514f5ad6e48e1fe12e1296d9bf5125
```

Активные файлы на VPS до deploy:

| профиль | SHA до | соответствующая версия |
|---|---|---|
| `mariyam_oyijon` | `6c3df8d8e80e01b83831da1014156d94f65358dfb17051708494657c0fe619c9` | `2c08193` — полнота чеков уже была на сервере |
| `mariyam_test` | `f757c0ea4c20e8d3c949bda9749c5bdf6fcb1af26749d5fc8f651b644ea95149` | `bbf6429` — правило намаза, без двух следующих SOUL-правок |

Следовательно, семейному профилю не хватало только `66fe5ab` с правилами
управления лентами. Тестовому профилю дополнительно не хватало `2c08193`:
записывать все строки чека и относить бытовую химию в `home`. Обе уже
закоммиченные правки вошли в единый канонический файл; иных отставших изменений
SOUL не обнаружено.

## Backup и deploy

Перед заменой созданы отдельные приватные backup:

```text
/home/timeagent/.hermes/profiles/mariyam_oyijon/backups/fix13-20260802T060000Z
/home/timeagent/.hermes/profiles/mariyam_test/backups/fix13-20260802T060000Z
```

Оба каталога имеют mode `0700`, оба файла `SOUL.md.before` — `0600`.
Канонический SOUL установлен mode `0600` в семейный и тестовый профили. В
обоих профилях `config check` прошёл.

После deploy фактический SHA обоих активных файлов:

```text
5efff19dbbf824ba9d3736339e70dd0c8f514f5ad6e48e1fe12e1296d9bf5125
```

Перезапущен только `hermes-gateway-mariyam_oyijon.service`:

```text
ActiveState=active
SubState=running
ExecMainStatus=0
NRestarts=0
```

## Техническая проверка

После deploy подтверждено:

```text
inventory: TOOLS/DISPATCH/list_tools = 30/30/30
migration_006_active=true
busy_ack_enabled=false
long_running_notifications=false
memory_notifications=off
tool_progress=false
session_reset={mode: daily, at_hour: 2, notify: false}
primary=gpt-5.6-luna via custom (n1n)
fallback=openai/gpt-5.6-luna via openrouter
mariyam_outbound_filter=enabled, version 1.0.2
```

Backend `manage_news_sources(action=list)` использован только read-only, без
модели. До deploy на VPS были сохранены только SHA-256-отпечатки состояния лент
и августовских расходов, без вывода идентификаторов, URL или финансовых строк.
После deploy повторная выборка дала:

```text
customer_feeds_unchanged=true
customer_expenses_unchanged=true
august_expense_total_matches_task=true
```

Таким образом, подключённые заказчиком ленты и реальные расходы не создавались,
не отключались, не редактировались и не удалялись. В семейном профиле не было
ручных запусков, вопросов модели, Telegram-сообщений, напоминаний или handover.

## Границы и Git

Изменений в SOUL, backend, migrations, tools, guards, cron и config в рамках
`fix13` не делалось — развёрнут только уже закоммиченный файл из `66fe5ab`.
Исходный commit: `66fe5ab` —
`soul: news feed control — topic hint, disable any feed, instant refresh`.

Первичный commit этого отчёта: `REPORT_COMMIT`; metadata commit с подстановкой
hash также отправлен в `origin/main`.
