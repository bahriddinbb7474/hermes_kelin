# Security And Privacy

Источник истины: `TZ_Hermes_Mariyam_FINAL_v3_0.md`

## Telegram allowlist

Доступ разрешён только Telegram ID Ойижон и Бахриддин ака.

Все остальные получают короткий отказ: `Кечирасиз, бу шахсий ёрдамчи.` Они не могут читать данные или вызывать tools.

## Секреты

- Bot token, DB URL, API keys, rclone credentials — только `.env` или переменные окружения.
- Не хранить секреты в коде, git, логах или Markdown.
- Для HTTP MCP tools на одном VPS слушать только localhost.

## Приватность

- Не хранить сырые voice-файлы дольше необходимого.
- Логи ротировать и не писать туда токены/ключи.
- В админ-отчётах не раскрывать лишние интимные детали.
- Cloud STT/TTS/LLM допустимы как осознанный компромисс, но передавать минимум данных.

## Backup

Backup должен включать:

- PostgreSQL dump;
- Hermes profile `mariyam_oyijon` с memory/skills/cron/sessions;
- конфиги tools без секретов.

Шифрование обязательно: `rclone crypt` или gpg-архив. Хранение: VPS + Google Drive через rclone.

## Restore и alerts

Restore нужно реально проверить до go-live: поднять чистое окружение, восстановить известный расход и сверить число строк.

Safety alerts: медицинские/критические фразы ловятся LLM + keyword-предохранителем; при срабатывании Hermes мягко отвечает Ойижон, уведомляет Бахриддин ака и пишет `alert_event`.
