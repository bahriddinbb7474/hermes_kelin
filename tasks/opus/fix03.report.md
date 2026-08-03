# fix03 — отчёт

## 1. Что именно было сломано

`identity_guard`, ветка `admin` в `_compute_effective_args`: `user_id: 0`
проходил три проверки и не подходил ни под одну.

- `requested is None`? Нет, ноль передан явно.
- `requested == actor_user_id`? Нет, у админа `user_id=1`.
- кросс-цель? `_is_pos_int(0)` = False (ноль не положительный) → `IDENTITY_TARGET_FORBIDDEN`.

Плюс `get_monthly_budget_status` вообще не входил в `ADMIN_CROSS_TARGET_TOOLS`,
то есть был недоступен админу даже с явным `user_id: 20`. Отсюда оба
сорванных кейса: общий отчёт не проходил ни при каком аргументе, детальный —
только если бы модель сама догадалась подставить внутренний id мамы, чего
SOUL ей делать не велит.

Ветка `oyijon` от этого не страдала никогда: она форсирует свой id до всех
проверок, поэтому у мамы отчёты работали.

## 2. Что сделано

`deploy/hermes_plugins/mariyam_identity_guard/__init__.py`:

**2.1.** Новый явный список — только читающие инструменты:

```python
ADMIN_ZERO_TARGET_READ_TOOLS = frozenset({
    "get_expense_report",
    "get_balance_summary",
    "get_monthly_budget_status",
})
assert ADMIN_ZERO_TARGET_READ_TOOLS <= ADMIN_CROSS_TARGET_TOOLS
```

`assert` на уровне модуля — чтобы список нельзя было расширить в обход
кросс-таргетной политики: плагин просто не загрузится.

**2.2.** В ветке `admin`, после self-проверок и **до** общей кросс-цели:

```python
if _is_zero_target(requested) and tool_name in ADMIN_ZERO_TARGET_READ_TOOLS:
    if (not isinstance(allowed_targets, list)
            or len(allowed_targets) != 1
            or not _is_pos_int(allowed_targets[0])):
        return None, "IDENTITY_TARGET_FORBIDDEN"
    out = copy.deepcopy(args)
    out["user_id"] = allowed_targets[0]
    return bind_actor(out), None
```

Ноль трактуется строго: `_is_zero_target` принимает только целочисленный `0` и
явно отвергает `bool`. `"0"`, `0.0`, `False`, `[0]` идут прежним путём и
получают отказ — послабление не должно открываться похожим на ноль мусором.

**2.3.** `get_monthly_budget_status` добавлен в `ADMIN_CROSS_TARGET_TOOLS`
(чтение). `set_monthly_budget` намеренно оставлен снаружи: план семьи ставит
Ойижон, и админ не должен переписывать его ни с id, ни с нулём.

**2.4.** Версия плагина `1.4.0` → `1.5.0`, описание дополнено. Два теста,
прибивающие версию в манифесте (`cron_identity_guard`, `stage53_guard`),
обновлены — эта привязка и существует для того, чтобы смена версии была
осознанной.

Чего не менял: ветка `oyijon`, cron-путь, `USER_SCOPED_TOOLS`, `GLOBAL_TOOLS`,
`ensure_user`, fail-closed поведение, состав и число инструментов (30).

## 3. Почему запись осталась запрещённой и чем это закреплено

Ноль резолвится **только** для трёх инструментов из списка. Любой мутирующий
инструмент падает на прежней проверке кросс-цели: `_is_pos_int(0)` = False.

Тест `test_fix03_admin_zero_sentinel_never_writes_to_oyijon` параметризован по
пятнадцати записывающим инструментам и требует `IDENTITY_TARGET_FORBIDDEN` для
каждого: `save_expense`, `save_income`, `update_expense`, `update_last_expense`,
`delete_expense`, `delete_last_expense`, `set_monthly_budget`,
`save_quran_progress`, `save_health_note`, `save_alert_event`, `save_plan_note`,
`upsert_recurring_obligation`, `manage_news_sources`, `approve_monthly_plan`,
`open_monthly_plan_cycle`.

Отдельно `test_fix03_zero_read_list_contains_no_mutating_tool` проверяет само
множество, а не поведение: список записи не пересекается со списком чтения, а
список чтения — подмножество кросс-таргетного. Если кто-то завтра допишет в
читающий список мутирующий инструмент, красным станет и этот тест, и
параметризованный.

## 4. Границы из задания — как выполнены

| требование | как закрыто |
|---|---|
| ровно одна цель, иначе отказ | `len(allowed_targets) != 1` → отказ; тест на `[]`, `[20, 21]`, `"20"` и отсутствующий ключ |
| ветка `oyijon` не меняется | `test_fix03_oyijon_branch_is_untouched`: пять инструментов, `user_id` 0 и 1 — всегда 20 |
| приватность здоровья не расширена | `save_health_note`/`save_alert_event` не в списках; `get_quran_progress` с нулём от админа — отказ (тест). `get_admin_report_data` в нулевой список **не** добавлен намеренно: он содержит health-алерты, и админ по-прежнему получает его только явным id или из своего вечернего cron |
| fail-closed на неизвестной роли | `test_fix03_unknown_role_still_fails_closed`: роль `superadmin` → отказ |

## 5. Проверка

`pytest tests`: **501 passed, 5 skipped, 0 failed** (было 466 — добавлено 35
проверок, в основном параметризованных).

Живая проверка политики на VPS: выполнил **задеплоенный** файл плагина против
**настоящей** карты личностей (только чтение, Telegram не задействован,
реальные id в вывод не попадают):

```
get_monthly_budget_status    admin=PASS user_id=20   oyijon=PASS user_id=20
get_expense_report           admin=PASS user_id=20   oyijon=PASS user_id=20
get_balance_summary          admin=PASS user_id=20   oyijon=PASS user_id=20
save_expense                 admin=BLOCK IDENTITY_TARGET_FORBIDDEN   oyijon=PASS user_id=20
set_monthly_budget           admin=BLOCK IDENTITY_TARGET_FORBIDDEN   oyijon=PASS user_id=20
save_health_note             admin=BLOCK IDENTITY_TARGET_FORBIDDEN   oyijon=PASS user_id=20
manage_news_sources          admin=BLOCK IDENTITY_TARGET_FORBIDDEN   oyijon=PASS user_id=20
get_quran_progress           admin=BLOCK IDENTITY_TARGET_FORBIDDEN   oyijon=PASS user_id=20
```

Остаётся живой кейс за заказчиком: «Бу ой қанча харажат бўлди?» со своего
аккаунта должно ответить цифрами. Всё, что можно проверить без его Telegram,
проверено.

## 6. Deploy

- `__init__.py` → `~/.hermes/profiles/mariyam_oyijon/plugins/mariyam_identity_guard/`,
  SHA-256 `c48a983e3410fd3a4bd71e1cbebf9ac78c18a1444e1446d7956cd495ac3a53e4`;
  `plugin.yaml` — версия `1.5.0`;
- бэкап прежней пары — `/home/timeagent/fix03-backup/`
  (`__init__.py` = `2e90e8c2…`, `plugin.yaml` = `e42578ff…`);
- перезапущен только `hermes-gateway-mariyam_oyijon.service`: `active`,
  30 инструментов, плагины загружены, новых ошибок нет.

Откат: вернуть обе копии из `/home/timeagent/fix03-backup/` и перезапустить
тот же сервис.

**Замечание по дрейфу.** Прежний файл на VPS отличался от репозитория хешем, но
**только переводами строк**: после `tr -d '\r'` он байт в байт совпал с `HEAD`
(`84f97eb8…`). То есть кто-то заливал его из Windows. Смысловой правки на VPS
не было. Теперь лежит LF-версия, и хеш сравним с репозиторием напрямую.

## 7. Найдено попутно — не входит в fix03

**7.1. Три cron-задачи молча заблокированы сегодня.** В `errors.log` за
2026-08-03:

```
08:00 cron_e5a1c6506d59 get_daily_news             CRON_JOB_UNTRUSTED
09:15 cron_668fbef5b5d5 get_recurring_obligations  CRON_JOB_UNTRUSTED
19:30 cron_a87fdf592250 get_admin_report_data      CRON_JOB_UNTRUSTED
```

Это утренняя сводка новостей, напоминания об обязательствах и вечерний
админ-отчёт: они отработали без данных. Отпечатки в приватной cron-карте
разошлись с задачами — ровно тот класс дефекта, что чинился в `imp07`. К fix03
отношения не имеет: всё это происходило под **старым** плагином 1.4.0 (шлюз
работал с 23:03 02.08 и до моего перезапуска в 20:50 03.08), и cron-путь я не
трогал. Похоже на последствие выкатки SOUL 02.08 в 23:03 без пересчёта
отпечатков (`imp04_refresh_cron_fingerprints.py`). Нужна отдельная задача, и
лучше сегодня — иначе мама третий день не получает новости и напоминания.

**7.2. Мелочь в старом коде guard.** `requested == actor_user_id` пропускает
`user_id: true` как «свой id» (в Python `True == 1`, а админ — это `user_id=1`),
и в backend уходит булево значение. Приватность не страдает (данные всё равно
свои), поэтому в рамках fix03 не трогал, чтобы не менять поведение мимо
задания. Чинится одной строкой, если решите.

## 8. Коммит

- `d726459` — плагин, манифест 1.5.0 и тесты;
- отчёт и `REGISTRY.md` — коммитом ниже.

Push в `origin/main` подтверждён.
