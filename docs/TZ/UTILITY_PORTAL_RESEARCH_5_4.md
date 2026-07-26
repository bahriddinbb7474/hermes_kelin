# Stage 5.4 — исследование официальных коммунальных кабинетов

Дата проверки: 2026-07-26

Регион проекта: Ташкент, Узбекистан

Статус: pre-code gate, код/connector/migration 004 не создавались

## Итог

**Решение: NO-GO для реализации Stage 5.4 сейчас.**

У электричества есть официальный web-кабинет и структурированный JSON API,
которым пользуется его frontend. Это не опубликованный API для сторонних
интеграций и не документированный export. Реалистичный технический кандидат —
второй приоритет ТЗ, **official frontend endpoint**, но только после проверки с
реальным аккаунтом и получения письменного разрешения или разъяснения
`Hududiy elektr tarmoqlari` (HET) о допустимости автоматического read-only
доступа.

Пользователь предоставил authenticated screenshot главной страницы реального
бытового аккаунта. Он подтверждает набор и единицы отображаемых полей, но не
JSON schema, срок access/refresh token и стабильность ежедневной синхронизации.
Публичные правила использования, разрешающие автоматизацию, не найдены.
Поэтому pre-code gate пока закрыт только в публично и визуально проверяемой
части.

## Границы и метод

- Проверены официальный сайт HET, публичная форма входа, опубликованные
  материалы HET, страницы HET Billing в магазинах приложений и публичные
  frontend bundles кабинета.
- Выполнены только безопасные `GET` без авторизации: получение CAPTCHA metadata
  и проверка защиты двух read-only endpoints.
- CAPTCHA не решалась. Запрос SMS/пароля не отправлялся. ONE.ID, платёжные и
  иные write-действия не запускались.
- Учётные данные и лицевой счёт заказчик не предоставлял. Персональных данных в
  репозиторий не переносились. Полученный screenshot содержит ФИО и полный
  лицевой счёт, поэтому сам файл не добавлен в git; в отчёте приведены только
  обезличенные поля.
- Проверка выполнена из Узбекистана. HET публично сообщал об ограничении
  иностранных IP; это отдельно учтено как эксплуатационный риск.

## 1. Официальный портал, приложение и владелец

| Объект | Результат |
|---|---|
| Официальная страница кабинета | [het.uz/ru/pages/view/personal_account](https://www.het.uz/ru/pages/view/personal_account) |
| Web-кабинет | [https://cabinet.het.uz/](https://cabinet.het.uz/) |
| API, используемый web-frontend | `https://cabinet-api.het.uz/` |
| Android | [HET Billing Mobile, package `uz.uzinfocom.het_billing`](https://play.google.com/store/apps/details?id=uz.uzinfocom.het_billing) |
| iOS/iPadOS | [HET Billing Mobile, id `6451301786`](https://apps.apple.com/uz/app/het-billing-mobile/id6451301786) |
| Поставщик услуги/владелец кабинета | АО `Hududiy elektr tarmoqlari` / АО «Региональные электрические сети», национальный оператор распределения и продажи электроэнергии конечным потребителям |
| Разработчик опубликованного мобильного приложения | UZINFOCOM |

Официальная страница HET сама ведёт бытовых и юридических потребителей на
`cabinet.het.uz`. HET создан постановлением Президента № ПП-4249 и управляет
территориальными сетями, распределяющими и продающими электроэнергию конечным
потребителям; см. [официальное описание HET](https://www.het.uz/oz/pages/view/general_info)
и [отчёт об устойчивом развитии](https://het.uz/uploads/564afb06-2850-6dc2-ff7f-a42349e3ee9d_media_.pdf).

## 2. Auth, CAPTCHA/2FA и сессия

### Подтверждено публично

На форме бытового потребителя есть:

- `Login`;
- `Пароль`;
- `Регистрация`;
- отдельный вход через ONE.ID.

Встроенная в официальный frontend инструкция описывает два способа входа:

1. лицевой счёт/«персональный номер» и пароль, полученный с короткого номера
   `2100`;
2. ONE.ID, после которого выбираются регион/район и вводится лицевой счёт.

Регистрация/получение пароля требует:

- регион и район;
- лицевой счёт;
- графическую CAPTCHA;
- SMS на телефон, указанный в договоре с HET.

Лицевой счёт описан как 11–13 цифр; текущая форма разделяет районный COATO-код и
6–8 цифр локального номера. Официальная инструкция говорит, что после каждого
входа через ONE.ID на договорный номер отправляется новый пароль.

Публичный frontend сообщает тайм-аут неактивности бытового кабинета **15 минут**.
Для юридического кабинета в том же bundle указано 35 минут; для Stage 5.4 это
значение не применяется.

### Технические признаки сессии

Frontend:

- получает `accessToken` после `POST .../user-login`;
- сохраняет `access-token` и `user-information` в `sessionStorage`;
- добавляет `Authorization: Bearer <token>` к read-запросам;
- содержит `refreshToken` и endpoint `.../refresh-token`;
- при `401/403` его API client выполняет logout и возвращает на `/login`.

Это подтверждает наличие access/refresh token, но **не подтверждает** их
фактический TTL и успешное автоматическое обновление. Нужен тест с реальным
аккаунтом: login → idle 15/20/60 минут → read → закрытие/повторный запуск →
refresh → logout.

### CAPTCHA и 2FA

- CAPTCHA подтверждена для получения/восстановления пароля.
- SMS подтверждено как канал выдачи пароля на договорный номер.
- На обычной форме `login + password` отдельная CAPTCHA и одноразовый SMS-код
  публично не видны.
- Называть обычный вход полноценным 2FA без account-теста нельзя. ONE.ID имеет
  собственный auth-flow и дополнительную отправку нового пароля HET.

## 3. Official API / export / frontend endpoints

### Классификация

- **Публично документированный API для сторонних клиентов: не найден.**
- **Публичный export CSV/PDF/JSON: не подтверждён.**
- **First-party JSON endpoints официального frontend: подтверждены.**

Следовательно, технический кандидат относится ко второму приоритету ТЗ —
`official export/endpoint`, а не к первому (`official API`). Это не означает
автоматического разрешения сторонней интеграции.

### Read-only endpoints, найденные в официальном frontend

Base URL: `https://cabinet-api.het.uz/`

| Метод | Path | Назначение по frontend |
|---|---|---|
| GET | `household-consumer/v1/mobile-cabinet/consumer-state` | текущее состояние счёта |
| GET | `household-consumer/v1/mobile-cabinet/user-details` | данные потребителя/договора |
| GET | `household-consumer/v1/mobile-cabinet/reading-histories` | история показаний |
| GET | `household-consumer/v1/mobile-cabinet/account-history` | история расчётов/счёта |
| GET | `household-consumer/v1/mobile-cabinet/payments-page` | платежная история/страница платежей |
| GET | `household-consumer/v1/mobile-cabinet/requisitions` | список обращений |

Frontend передаёт заголовки:

```text
Authorization: Bearer <masked>
Coato-Code: <masked>
lang: RU|UZ
```

### Masked фактические запросы/ответы без аккаунта

Публичная CAPTCHA:

```http
GET /household-consumer/v1/mobile-cabinet/captcha/generate
Host: cabinet-api.het.uz

HTTP/1.1 200
Content-Type: application/json
Cache-Control: no-cache, no-store, max-age=0, must-revalidate

{"image":"<base64 omitted>","key":"<masked>"}
```

Защита read endpoints:

```http
GET /household-consumer/v1/mobile-cabinet/consumer-state
Host: cabinet-api.het.uz

HTTP/1.1 401
<empty body>
```

```http
GET /household-consumer/v1/mobile-cabinet/user-details
Host: cabinet-api.het.uz

HTTP/1.1 401
<empty body>
```

Аутентифицированные запросы и ответы не зафиксированы: это требует реального
аккаунта. Придумывать JSON schema по названиям компонентов нельзя.

### Воспроизводимость frontend-наблюдений

Проверенные 2026-07-26 публичные assets:

| Asset | SHA-256 |
|---|---|
| `main-I5H3KLSE.js` | `D5103AB35C1BACE5E33A532A055C8572FB83598393D57399C87E1331D834B2B7` |
| `chunk-5J5HKLS2.js` | `FBDDBBD9F8621A776691843EF83A2049925402F0E43D31545E297A4C69241DC7` |
| `chunk-RY722Z4Q.js` | `1B2B8CEFD4B8DF10FF7D9DAE6A317857C996F1CAD2EEAAE16CE902D20554B232` |
| `chunk-YPQD5EGP.js` | `D3C2F1EC9B2DB7C5A3190B8BADB93794A3E0A63E6429E6F86FB8F22B419F46B9` |
| `chunk-DKPR7TGA.js` | `D11E794E5EACEB81ABE3F0E2A897B8D20D4828E01E3E7DCD01A9D1C9C7D07C28` |

Существенные masked фрагменты логики:

```text
GET  .../captcha/generate
POST .../captcha/validate?key=<masked>&value=<masked>
POST .../get-password
body: {coatoCodeAndPersonalAccount:"<masked>",
       captchaKey:"<masked>", captchaValue:"<masked>"}
```

```text
POST .../user-login
response -> accessToken + user-information -> sessionStorage
GET  .../reading-histories
GET  .../account-history
GET  .../consumer-state
```

## 4. Доступные поля

### Подтверждено официальными публичными источниками

HET и страницы приложения заявляют:

- показания счётчика;
- текущее состояние лицевого счёта;
- задолженность;
- историю платежей;
- статистику/расшифровку расчётов;
- потреблённое количество электроэнергии и остаток.

Официальное ТЗ на HET mobile/web также требует XML/JSON интеграцию с биллингом и
равный функционал web и mobile; см.
[опубликованное HET техническое задание](https://het.uz/uploads/d1e5087c-48ff-47b8-004c-dac353a488d2_media_.pdf).

### Видно в публичном frontend, но требует account-проверки

В labels/models присутствуют:

- meter reading и ASKUE reading;
- current/start/end/incoming balance;
- debt и prepayment;
- current/main tariff и tariff amount;
- current/previous consumption/calculation;
- payment amount/date;
- meter number/type;
- расчётный период.

### Подтверждено authenticated screenshot

На главной странице реального бытового аккаунта видны:

- текущий баланс с явной семантикой `предоплата`, в `so'm`;
- потребление с начала текущего месяца, в `kVt·s` (кВт·ч);
- начисленная за текущий месяц сумма;
- начисленная солнечная энергия, в `kVt·s`;
- помесячная диаграмма потребления;
- расчёт за выбранный месяц с итоговыми кВт·ч и суммой;
- тарифные ступени с ценой в `so'm` и рассчитанной суммой;
- история принятых платежей: дата, принимающая организация, сумма и тип;
- отдельная вкладка показаний счётчика.

ФИО, полный лицевой счёт и конкретные платёжные строки намеренно не
воспроизводятся. Screenshot не доказывает названия и типы JSON keys.

### Статус полей после визуальной проверки

| Поле Stage 5.4 | Статус |
|---|---|
| Показание | отдельная UI-вкладка подтверждена; значение и JSON key/type не проверены |
| Текущее/прошлое потребление | PASS для UI; текущий и помесячный расчёт в кВт·ч видны |
| Единица `кВт·ч` | PASS для UI (`kVt·s`) |
| Начислено UZS | PASS для UI; текущая и месячная рассчитанные суммы видны |
| Предоплата/остаток/долг | предоплата PASS для UI; сценарий долга и взаимная исключительность не проверены |
| Тариф | PASS для UI; ступени и цена в сумах видны |
| Дата обновления | даты платежей/расчётный месяц видны; provider `updated_at` не подтверждён |

До account-теста migration 004 нельзя фиксировать provider mapping, особенно
правило «отрицательный prepaid против отдельного debt».

## 5. Write/payment поверхность и правила

### Write/payment действия, которые существуют

Официальные источники и frontend подтверждают:

- оплату электроэнергии;
- смену телефонного номера;
- создание заявок/обращений;
- login/logout, получение нового пароля, ONE.ID flow;
- push token/уведомления;
- для юридических лиц — дополнительные отчётные и договорные write-функции.

Найденные бытовые POST endpoints включают:

```text
.../change-phonenumber
.../save-changed-phonenumber
.../requisition
.../get-password
.../user-login
.../user-logout
.../one-id/login
.../save-fcmtoken
```

Будущий connector должен иметь отдельный allowlist только из проверенных `GET`.
HTTP methods `POST/PUT/PATCH/DELETE`, payment URLs, redirects на банк/ONE.ID,
push registration и любые неизвестные paths должны быть заблокированы до
отправки запроса. Нельзя хранить карту, менять телефон/настройки, отправлять
обращения, получать новый пароль или выполнять оплату.

### Rules of use / законность автоматизации

Публичных ToS, API terms или правил, прямо разрешающих автоматизированное чтение
кабинета сторонним ПО, найти не удалось. Опубликованное HET ТЗ требовало
принятия пользователем оферты/соглашения после первого входа в mobile app, но
содержание принятого соглашения публично не подтверждено.

Следовательно:

- согласие владельца лицевого счёта необходимо, но само по себе не доказывает
  разрешение оператора на автоматизированный доступ;
- до кода нужен письменный ответ HET (`info@het.uz`, контакт-центр 1154) о
  read-only machine access к first-party endpoints, допустимой частоте и
  хранении токена;
- если HET не разрешит или не ответит, Stage 5.4 остаётся NO-GO; HTML scraping
  или обход защит не являются запасным вариантом.

Это инженерная оценка, не юридическое заключение.

## 6. Стабильность и риски

| Риск | Оценка | Доказательство/мера |
|---|---|---|
| API не документирован для третьих сторон | высокий | endpoints получены из hashed frontend bundles; контракт может меняться без уведомления |
| Частые изменения клиента | высокий | HET Billing публиковал много версий в 2024–2026; версия 1.0.19 датирована маем 2026 |
| Ошибки клиента/SMS | средний–высокий | публичные отзывы сообщают о проблемах регистрации, SMS и multi-account; это наблюдения пользователей, не SLA |
| Иностранные IP | высокий для VPS вне Узбекистана | [HET сообщал об ограничении иностранных IP](https://www.het.uz/ru/lists/view/1991) |
| CAPTCHA | высокий для bootstrap/recovery | CAPTCHA обязательна для получения пароля; обход запрещён |
| Короткая idle-сессия | высокий | официальная frontend-инструкция: 15 минут для бытового кабинета |
| Token/refresh drift | высокий | refresh присутствует, но TTL и успешность не проверены |
| Rate limits | неизвестно | публичные rate-limit headers не возвращались; password flow содержит backoff, по умолчанию 120 секунд |
| Блокировка устройства/аккаунта | средний–высокий | опубликованное HET ТЗ предусматривает блокировку по идентификаторам устройства |
| HTML drift | несущественен при JSON path | HTML не следует парсить; schema drift JSON обязан fail closed |

Оценка стабильности кандидата: **средняя-низкая до live soak test**. Даже при
успешном тесте connector должен синхронизировать не чаще раза в сутки, проверять
строгую JSON schema, не делать автоматический re-login через CAPTCHA/ONE.ID и
после двух ошибок уведомлять только администратора.

## 7. Газ и вода — только факт наличия

| Услуга | Официальный кабинет | Подтверждение |
|---|---|---|
| Газ | [https://cabinetaskug.hududgaz.uz/](https://cabinetaskug.hududgaz.uz/) | официальный материал `Hududgazta'minot` описывает web/android кабинет и ONE.ID: [стр. 7 документа](https://hududgaz.uz/files/4FCB5A94940623B030CAEC657869B7668E2FF84D54648516C14EF29A081CC077) |
| Вода | [https://cabinet.uzsuv.uz/](https://cabinet.uzsuv.uz/) | действующая форма авторизации АО `O'zsuvta'minot`; официальный журнал общества также описывает личный кабинет |

Это не разрешение подключать газ/воду. Их auth/API/terms не исследовались.

## Матрица девяти pre-code gates

| Gate | Статус | Вывод |
|---|---|---|
| 1. Official URL/owner | PASS | HET → `cabinet.het.uz`; API same-party `cabinet-api.het.uz` |
| 2. Auth method | PARTIAL | account+password/SMS и ONE.ID подтверждены; live flow не пройден |
| 3. CAPTCHA/2FA | PARTIAL | CAPTCHA/SMS подтверждены; обычный login/2FA требует live проверки |
| 4. Available fields | PARTIAL | UI и единицы подтверждены authenticated screenshot; JSON schema и debt-case не проверены |
| 5. Official API/export | PARTIAL | published API/export нет; frontend JSON endpoints есть |
| 6. Write/payment surface | PASS для публичного gate | поверхность перечислена; live routes могут расширить список |
| 7. Rules of use | FAIL | разрешение на automation не найдено |
| 8. Session stability | FAIL | idle 15 мин известен; TTL/refresh/soak не проверены |
| 9. Safe automation | FAIL до теста | архитектурно возможна, но legal/session/schema gates открыты |

## Что нужно от заказчика

1. Письменное согласие владельца лицевого счёта на контролируемый read-only тест.
2. В безопасном канале вне Telegram/git/LLM/logs:
   - masked лицевой счёт для планирования;
   - договорный телефон, доступный владельцу для SMS;
   - пароль только непосредственно в будущий VPS secret store, не в этот чат.
3. Разрешение запросить у HET письменное подтверждение автоматического read-only
   доступа и лимитов.
4. После ответа HET — отдельное разрешение на короткий live test из
   узбекистанского egress: без платежей/настроек, с ручным прохождением CAPTCHA
   владельцем при необходимости.

## Условия перехода в GO

Stage 5.4 можно перевести в GO только если одновременно:

- HET разрешил такой read-only способ или предоставил официальный API/export;
- один реальный аккаунт подтвердил точные request/response schemas;
- подтверждены `reading`, consumption+units, billed UZS,
  prepaid/remaining/debt, tariff и provider update date;
- измерены token TTL/refresh и повторный запуск без CAPTCHA automation;
- 7-дневный daily soak не создаёт SMS storms, блокировок или неожиданных writes;
- egress расположен в Узбекистане;
- connector технически не способен вызвать write/payment методы и fail closed
  при schema drift.

До выполнения этих условий migration 004 и три Stage 5.4 tools остаются
`PLANNED / NOT IMPLEMENTED`.

## Основные источники

- [Официальная страница личного кабинета HET](https://www.het.uz/ru/pages/view/personal_account)
- [Официальный web-кабинет HET](https://cabinet.het.uz/)
- [HET Billing Mobile — Google Play](https://play.google.com/store/apps/details?id=uz.uzinfocom.het_billing)
- [HET Billing Mobile — App Store](https://apps.apple.com/uz/app/het-billing-mobile/id6451301786)
- [Официальное ТЗ HET на mobile/web billing](https://het.uz/uploads/d1e5087c-48ff-47b8-004c-dac353a488d2_media_.pdf)
- [Уведомление HET об ограничении иностранных IP](https://www.het.uz/ru/lists/view/1991)
- [Официальный кабинет газа](https://cabinetaskug.hududgaz.uz/)
- [Официальный кабинет воды](https://cabinet.uzsuv.uz/)
