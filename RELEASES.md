# Публикация релизов в канал @shaolenai

Канал: [https://t.me/shaolenai](https://t.me/shaolenai)

## Чеклист задач (всё выполнено)

- [x] **CHANGELOG.md** — формат версии + блок `<!-- TELEGRAM_POST ... -->` для поста в канал.
- [x] **Скрипт** `scripts/publish_release_to_telegram.py` — определяет новую версию по файлу `VERSION` и публикует пост в [t.me/shaolenai](https://t.me/shaolenai) через MTProto (Premium-сессия).
- [x] **Документация** — запуск вручную, cron, systemd timer; признак опубликованной версии в самом файле `VERSION` (знак `+` после версии), без отдельного `.last_published_version`.

## Условия

- Аккаунт с **Premium-сессией** (тот же, что для `/todo`) должен быть **администратором** канала @shaolenai.
- В `.env` заданы: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `PREMIUM_SESSION_PATH` (путь к `.session` файлу).

## Как это устроено

**Версия хранится только в репозитории** (файл `VERSION` и блок в `CHANGELOG.md`). Из Telegram-канала версия **не читается** — в канал только отправляется пост.

1. Вы записываете новую версию в файл `VERSION` (первая строка — текущая версия; следующая строка — предыдущая с `+`, и т.д.) или запускаете `scripts/bump_version.py` (новая версия добавляется первой строкой, предыдущая уходит в следующую с `+`).
2. Скрипт `scripts/publish_release_to_telegram.py` читает **первую строку VERSION**. Если после версии **нет знака `+`** — считает релиз неопубликованным.
3. Публикует пост в канал через MTProto и **добавляет `+` к первой строке VERSION** (например, `1.1.0` → `1.1.0+`). Отдельный файл `.last_published_version` не используется.

## Запуск вручную

После деплоя с обновлённым CHANGELOG:

```bash
cd /path/to/telegram_goals_bot
./venv/bin/python scripts/publish_release_to_telegram.py
```

## Автоматический запуск (cron)

Раз в час (или после деплоя — раз в 5 минут):

```bash
# Открыть crontab
crontab -e

# Добавить строку (подставьте путь к проекту и venv)
0 * * * * /root/shaolen/venv/bin/python /root/shaolen/scripts/publish_release_to_telegram.py >> /root/shaolen/logs/publish_release.log 2>&1
```

## Автоматический запуск (systemd timer)

Создайте два файла в `/etc/systemd/system/`:

**goals-publish-release.service**

```ini
[Unit]
Description=Publish release to Telegram channel @shaolenai
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/shaolen
EnvironmentFile=/root/shaolen/.env
ExecStart=/root/shaolen/venv/bin/python /root/shaolen/scripts/publish_release_to_telegram.py
```

**goals-publish-release.timer**

```ini
[Unit]
Description=Run publish release every hour

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

Включить и запустить таймер:

```bash
sudo systemctl daemon-reload
sudo systemctl enable goals-publish-release.timer
sudo systemctl start goals-publish-release.timer
```

Проверка: `sudo systemctl list-timers goals-publish-release.timer`

## Добавление новой версии

При внесении изменений в проект:

1. **Запишите новую версию в файл `VERSION`** (одна строка, например `1.1.1` или `1.2.0`). Либо запустите:
   ```bash
   ./venv/bin/python scripts/bump_version.py        # patch: 1.1.0 → 1.1.1
   ./venv/bin/python scripts/bump_version.py minor  # 1.1.0 → 1.2.0
   ./venv/bin/python scripts/bump_version.py major  # 1.1.0 → 2.0.0
   ```
2. Откройте `CHANGELOG.md` и вставьте **новый блок в начало** (сразу после `---` под описанием формата).
3. Укажите ту же версию (например `v1.1.1`), дату и список изменений.
4. В конце блока добавьте комментарий с текстом поста:

   ```markdown
   <!-- TELEGRAM_POST
   Краткий текст для канала (1–3 абзаца).
   -->
   ```

5. Сохраните. При следующем запуске скрипт прочитает первую строку `VERSION`; если там нет `+`, отправит пост в канал и поставит `+` после версии.

## Файл VERSION: формат

- **Первая строка** — текущая версия. Если без `+`, пост ещё не опубликован; после публикации скрипт допишет `+`.
- **Следующие строки** — предыдущие версии с `+` (история). При `bump_version.py` новая версия добавляется первой строкой, предыдущая — второй с `+`.

Пример:
```
1.1.1
1.1.0+
```
После публикации 1.1.1 скрипт изменит на:
```
1.1.1+
1.1.0+
```
