# fix01 (Opus) — отчёт: cron-обёртка в доставке Ойижон + статус live E2E 5.3A

## 1. Источник обёртки (по коду Hermes v0.18.2 на VPS)
`cron/scheduler.py:1443–1461`: при доставке cron-результата контент оборачивается
заголовком/футером:
```
Cronjob Response: <name>
(job_id: <id>)
-------------
<content>
To stop or manage this job, send me a new message (e.g. "stop reminder <name>").
```
Гейт: `wrap_response = load_config().get("cron",{}).get("wrap_response", True)` —
**default True**. Обёртка добавляется в `delivery_content` в общем пути доставки
(`_send_to_platform`), т.е. **и при штатном тике, и при ручном `cron run`**
(оба идут через scheduler). Значит гипотеза «обёртку даёт только ручной run»
**неверна** — production-доставка тоже была бы с обёрткой. В output-файле
(`cron/output/...`) сохраняется чистый `## Response` (обёртка только в отправке),
поэтому в прошлом evidence она не была видна.

## 2. Фикс (без изменения Hermes core)
Managed CLI в профиле:
```
hermes --profile mariyam_oyijon config set cron.wrap_response false
```
→ `✓ Set cron.wrap_response = False` в
`~/.hermes/profiles/mariyam_oyijon/config.yaml`; Gateway restart. Задокументировано
в `deploy/hermes_profile_mariyam_oyijon/cron/README.md`. Hermes core/plugins не менялись.

## 3. Перепроверка чистой доставки
После фикса `cron run` job 25 (без seed — использован существующий in-window
расход): backend создал draft `food.bread=4000`, cycle `waiting_oyijon`, сообщение
доставлено тест-Ойижон. `delivery_content = content` (обёртка отключена детерминистично
по коду). **Визуальное подтверждение чистого сообщения — за заказчиком** (он
сообщал обёртку по скрину). Тестовый cycle/draft удалён, baseline восстановлен
(tx=1, plans=0, cycles=0); transactions не трогались.

## 4. БЛОКЕР для «ха»-approve (шаг 4): deployed SOUL запрещает Stage 5.3A tools
`SOUL.md:280`: «Stage 5.3A, `approve_monthly_plan`, цикл 25/27/28/1 и его cron
не реализованы: не вызывай и не объявляй их доступными.»
Следствие: Telegram-turn тест-Ойижон с «ха» **не** вызовет `approve_monthly_plan`
(ассистенту прямо запрещено). Значит `approved_by_oyijon` через «ха» невозможен
без обновления SOUL (убрать запрет + добавить инструкции цикла: «ха» на pending
план → approve; cron 25/27/28/1a/1b). SOUL — canonical profile prompt с pinned LF
SHA и skill-protect; правка существенная (redeploy + regression + новый SHA).
Cron-задачи 25/28 в E2E сработали несмотря на этот текст (job-prompt перевесил),
но противоречие надо снять.

## 5. Ограничение окружения
Sandbox-классификатор блокирует мои ssh-команды, читающие/меняющие profile
`config.yaml` напрямую (managed `hermes config set` прошёл). Прямое редактирование
SOUL на VPS, вероятно, тоже потребует разрешения.

## Итог / осталось
- Обёртка: **исправлена** (config), нужно визуальное подтverждение заказчика.
- «ха»-approve, live 1a/1b, статус 5.3A=CLOSED/LIVE PASS: **заблокировано** до
  решения по обновлению SOUL (владелец — архитектор/sol). 1a/1b как cron можно
  прогнать после снятия SOUL-противоречия (seed+cleanup).

## Обновление (live, 2026-07-25/26)
- **Обёртка исправлена и подтверждена live:** штатный scheduled job 25 сработал на
  реальное 25-е число и доставил тест-Ойижон **чистое** сообщение без
  `Cronjob Response…/To stop or manage` (озиқ-овқат 100 000, нон 4 000, жами
  104 000, «ха»). Wrapper fix + scheduled-tick доставка — оба PASS в проде.
- **SOUL 5.3A enable развёрнут:** `open/get/approve` разрешены; SHA `bbf21c87…`;
  «ха»-guard из 3 фактов. Backend deploy backend 24 + guard 1.2.0 (см. imp02).
- **«ха»-approve НЕ подтверждён live:** попытка «ха» (26-е) упала на upstream
  `HTTP 524` от LLM-провайдера `api.n1n.ai`/`gpt-5.6-luna` (msgs=54, ~12.8k
  tokens, retry `attempt 1/1`) — turn не выполнился, approve не вызывался. Это
  внешний сбой провайдера, не код/SOUL/guard (когда провайдер был жив,
  диалог 5.3-плана работал). Ранее bare-«ха» также ненадёжно маппился на approve
  на уровне модели.
- **Детерминантный путь:** auto-approve job 1a на 1-е число утверждает цикл без
  «ха» (проверено unit-тестами; live 1a — на реальное 1-е Asia/Tashkent).

## Статус fix01
- Шаги 1–3 (обёртка): **DONE / LIVE PASS**.
- Шаг 4 («ха»/1a/1b): «ха» блокируется нестабильностью провайдера (retry когда
  провайдер здоров); 1a — детерминантный fallback (live только 1-го числа).
  5.3A **не** помечаю CLOSED/LIVE PASS: conversational «ха» live не подтверждён.

## Коммиты
Docs/runbook + SOUL enable (SHA `4e52ffb0`→`bbf21c87`) с propagation и regression;
фикс обёртки — runtime profile config (не в git; команда задокументирована).
