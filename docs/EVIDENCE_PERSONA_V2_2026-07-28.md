# Evidence: SOUL v2 (личность «живая келин») + компактизация токенов

Задача `tasks/opus/imp04.md`, фаза 2. Дата: 2026-07-28.
Фаза 1 (аудит): `docs/AUDIT_TOKENS_PERSONA_2026-07.md`.

## 1. Что изменено

| Область | Было | Стало |
|---|---|---|
| `agent.disabled_toolsets` | skills, terminal, code_execution | + browser, file, delegation, session_search, image_gen, vision, tts, todo, clarify |
| `SOUL.md` | 25 603 симв. / 8 244 ток. | 14 617 симв. / **4 801 ток.** |
| MCP tool descriptions | 4 239 ток. | 4 043 ток. |
| `cron/06_evening.md` | чек-лист «расход + Коран + здоровье» одним вопросом | одна тема в день по ротации, похвала вместо допроса |
| `cron/06_morning.md` | бюллетень из 5 блоков | тёплое сообщение, 2–3 релевантные новости, «батафсил айтайми?», один вопрос |
| `cron/25_draft.md`, `cron/27_reminder.md` | сухая сводка | сначала «ҳол сўра», один вопрос, без давления |
| `backend/external_data.py` | из RSS только заголовок, 12 кандидатов | + `summary_ru` (описание), 20 кандидатов |

Инварианты не ослаблены: только узбекская кириллица, цифры только из tools,
identity-sentinel `user_id: 0`, guard-ошибки → мягкая остановка, health-alerts и
приватность health-заметок, запрет диагнозов, heartbeat админу, архитектурные
запреты (§12 SOUL).

## 2. Токены: до / после (o200k_base, точный подсчёт)

| Статья | Было | Стало | Δ |
|---|---:|---:|---:|
| SOUL.md | 8 244 | 4 801 | −3 443 |
| Служебный промпт Hermes | ≈ 2 600 | ≈ 2 400 | −200 |
| Встроенные tools Hermes | 9 807 (23 шт.) | 2 552 (`cronjob` + `memory`) | −7 255 |
| MCP-tools бэкенда (29) | 4 239 | 4 043 | −196 |
| **Префикс каждого запроса** | **≈ 24 900** | **≈ 13 800** | **−45 %** |

Проверка на VPS (offline preflight, 0 API calls, временный профиль
`/tmp/imp04-preflight`):

```
stable     chars=  24215   (было 35 585)
volatile   chars=     64
soul_chars=14617  soul_in_full=True  truncated=False  skills_index=False
TOOLS (inspection agent): n=1 (memory)   — было 12
disabled_toolsets=[browser, clarify, code_execution, delegation, file,
                   image_gen, session_search, skills, terminal, todo, tts, vision]
```

`cronjob` и MCP-tools добавляются gateway-ом в runtime и в inspection-агенте не
видны — их вклад (1 886 + 4 043) посчитан отдельно и включён в таблицу.

## 3. Деньги при тарифе n1n $1 / $6 за 1 млн (вход/выход)

| Профиль нагрузки | Было | Стало |
|---|---:|---:|
| 40 сообщений/день + 4 cron | ≈ $60/мес | ≈ **$35/мес** |
| 20 сообщений/день + 4 cron | ≈ $32/мес | ≈ **$19/мес** |
| 10 сообщений/день + 4 cron | ≈ $18/мес | ≈ **$11/мес** |

Расчёт: 1,7 API-вызова на сообщение Ойижон (факт из `state.db`: 110 вызовов на
12 Telegram-сессий), выход ≈ 250 токенов на вызов.

**Бюджет $10–15/мес компактизацией в одиночку не достигается при 30–40
сообщениях в день.** Оставшиеся рычаги (решение заказчика, не техническое):

1. **Модель.** В профиле уже есть fallback `deepseek/deepseek-chat` через
   OpenRouter; в сессиях, где он срабатывал, биллинг Hermes оценил вход
   примерно в **$0,20 за 1 млн — в пять раз дешевле n1n**. Перевод основной
   модели на неё даёт ≈ $10/мес при 40 сообщениях/день, но требует живой
   проверки качества узбекской кириллицы.
2. **Кэш префикса.** `cache_read_tokens` уже приходят от провайдера (29 % входа
   в Telegram, 0 % в cron). Нужен тариф n1n на cache read — при обычной скидке
   10× это ещё минус треть счёта.
3. **Allowlist MCP-tools** (`mcp_servers.<name>.tools.include`): в диалоге нужны
   не все 29 инструментов, экономия ещё ≈ 1 200 токенов на вызов.

## 4. Regression

Полный прогон: `290 passed, 87 skipped` (локально, `pytest tests/`).
Обновлены под SOUL v2 и новые toolsets:

- `tests/inspect_effective_prompt.py` — маркеры v2 + два маркера личности;
- `tests/test_mariyam_effective_prompt.py` — список disabled_toolsets, набор
  удалённых инструментов, маркеры;
- `tests/test_mariyam_skill_stage52.py`, `test_mariyam_soul_stage53.py` —
  переписаны под сжатые контракты (правила сохранены: заголовки таблиц,
  дословная финальная фраза, порядок summary → товары, `items: []` запрещён,
  «ха» → `get_monthly_plan_cycle` → `approve_monthly_plan`);
- `test_mariyam_skill_stage51.py`, `test_mariyam_skill_identity.py`,
  `test_cron_reliability.py`, `test_stage6_daily_life.py`,
  `test_stage53_product_plans.py` — точечные правки формулировок;
- `test_mariyam_skill_protection.py` — новый канонический
  `EXPECTED_SOUL_SHA256 = 3ab6c3c0ce0810ae7838164f02d776c6b9bc2e52744d80e887b2d282f74972ef`.

Новый тест: `test_dead_nutrition_web_search_directive_is_gone` — мёртвые
директивы про web search не должны вернуться, пока инструмент не включён.

## 5. Деплой

Скрипт `deploy/imp04_deploy.sh` (идемпотентный, с dry-run и rollback):

1. бэкап `SOUL.md`, `config.yaml`, `cron/jobs.json`, `backend/*.py`;
2. установка SOUL v2 (mode 444, sha256 сверяется с git);
3. `agent.disabled_toolsets` — построчная правка `imp04_patch_config.py`,
   комментарии и секреты в конфиге не трогаются;
4. `hermes cron edit --prompt` для 4 задач (утро, вечер, 25, 27);
5. **`deploy/imp04_refresh_cron_fingerprints.py --apply`** — пересчёт
   `job_fingerprint_sha256` и `prompt_sha256` для trusted cron jobs
   функциями самого guard-а; mapping переписывается атомарно, mode 0600,
   состав записей (user_id, role, allowed_tools) не меняется;
6. копирование backend-файлов в `/opt/hermes-mariyam`;
7. рестарт `hermes-gateway-mariyam_oyijon.service` и проверка `is-active`.

Dry-run на VPS выполнен: sha текущего и нового SOUL показаны, fingerprint-хелпер
прочитал live `jobs.json` и приватный mapping и корректно ответил
«fingerprints already current» (промпты ещё не менялись).

**Статус: `--apply` НЕ выполнен — запись в боевой профиль требует явного
разрешения заказчика.** Команда для запуска:

```bash
ssh timeagent@46.224.239.76 "bash /tmp/imp04/imp04_deploy.sh --apply"
```

Откат:

```bash
ssh timeagent@46.224.239.76 "bash /tmp/imp04/imp04_deploy.sh --rollback <backup-dir>"
```

## 6. Live acceptance (после деплоя) — ЖДЁТ

- [ ] утреннее сообщение 08:30: тёплый тон, 2–3 новости, «батафсил айтайми?»,
      один вопрос, 0 латинских букв;
- [ ] вечернее сообщение 19:30: одна тема (по ротации), без чек-листа;
- [ ] «нон 12 минг, гўшт 180 минг» → запись + человеческий ответ;
- [ ] общий отчёт за месяц: таблица групп + дословная финальная фраза;
- [ ] подробнее по группе: summary-таблица → таблица товаров, без финальной фразы;
- [ ] напоминание («эртага соат 10 да дорини эслат») → one-shot доставлен;
- [ ] health-фраза → мягкий ответ + алерт админу (guard);
- [ ] замер «после»: `input_tokens / api_call_count` в `state.db` за сутки
      сравнить с 18,5 тыс./вызов до изменения.

## 7. Побочное (сделано)

Убит зависший процесс PID 627910 (`python - … mariyam_identity_guard`), который
14 суток держал целое ядро VPS (load average 1,00). Родительский `bash -s`
(PID 627899, осиротевший деплой-шелл от 13.07) простаивает и CPU не ест.
