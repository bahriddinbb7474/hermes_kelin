# imp01 (Terra) — Stage 8: backup, restore-проверка, автозапуск, heartbeat

## Контекст
Проект Hermes/Mariyam, VPS `/opt/time-agent`, профиль `mariyam_oyijon`,
PostgreSQL (127.0.0.1:5432, БД Мариям), секреты `/opt/hermes-mariyam-secrets/`
(0600/0700). Требования — ТЗ `docs/TZ/TZ_Hermes_Mariyam_FINAL_v3_0.md`,
«Этап 8» + AC v3.1. Backend tools `backup_data`/`get_backup_status` уже
существуют и возвращают `NOT_CONFIGURED` — так и должно быть до завершения
этапа; после — реальный статус.

ВАЖНО: параллельно на VPS Opus завершает Stage 5.3A (Gateway, SOUL, cron jobs).
Не рестартовать Gateway и не трогать профиль/SOUL/plugins/cron jobs/mapping.
Твоя зона: БД (только чтение/dump), новые скрипты, systemd units, rclone.

## Шаг 0 — STOP-условие
Проверить наличие настроенного rclone remote для Google Drive (пункт 8
«Что нужно от заказчика»). Нет remote/credentials — остановиться, написать
заказчику в чат, что именно нужно (без выполнения остального).

## Что сделать
1. Backup-скрипт: pg_dump БД Мариям + канонический profile state
   (SOUL, конфиги профиля; секреты — включать зашифрованными) → один архив →
   шифрование (gpg symmetric, ключ в `/opt/hermes-mariyam-secrets/`, 0600) →
   rclone в Google Drive; ротация (хранить разумное число копий).
2. Расписание — systemd timer (ежесуточно). Это ops-контур; запрет «отдельного
   scheduler» относится к диалоговому/бизнес-контуру и сюда не распространяется
   (решение архитектора, зафиксировать в DECISIONS.md).
3. Restore-проверка по AC: в чистое окружение (temp DB / docker на VPS)
   восстановить backup; подтвердить известный расход и совпадение числа строк
   по таблицам. Скрипт restore — часть поставки, процедура — в docs.
4. Автозапуск: все сервисы Мариям поднимаются после reboot (systemd enabled;
   reboot-тест согласовать с заказчиком по времени, чтобы не мешать Opus).
5. Heartbeat: админ получает периодический короткий status и уведомление при
   падении бота (минимальное решение: systemd OnFailure + ежесуточный status
   через Telegram Bot API напрямую админу; Ойижон ничего не видит).
6. `backup_data`/`get_backup_status` перевести с `NOT_CONFIGURED` на реальный
   статус последнего бэкапа (read-only, без запуска backup из LLM-контура —
   если текущий контракт иной, привести к этому и обновить TOOLS_CONTRACTS.md).
7. Тесты: unit на скрипты где осмысленно + фактические прогоны на VPS
   (backup → restore → сверка) с логами в evidence
   `docs/EVIDENCE_STAGE_8_BACKUP_<дата>.md`. README/ROADMAP статус Stage 8.

## Запрещено
Секреты/ключи/токены в git и логи; изменение данных БД; Gateway/SOUL/plugins/
cron jobs; сообщения Ойижон.

## Отчёт
`tasks/terra/imp01.report.md`: состав backup, расписание, результат
restore-сверки (числа), reboot-тест, hash коммитов. Commit поимённо + push:
`feat: Stage 8 encrypted backup, restore check, heartbeat`.
В чат заказчику: 2–3 предложения простым русским.
