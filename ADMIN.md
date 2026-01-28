# Админка и круглосуточная работа бота

## Круглосуточный запуск (systemd)

Чтобы бот и веб-сервер не отключались при закрытии ноутбука и перезапускались при сбоях:

1. Скопируйте файлы из `systemd/` в systemd:
   ```bash
   sudo cp systemd/goals-bot.service /etc/systemd/system/
   sudo cp systemd/goals-webapp.service /etc/systemd/system/
   ```

2. Отредактируйте пути и пользователя в обоих файлах:
   - `User=YOUR_USER` — ваш пользователь на сервере
   - `WorkingDirectory=/path/to/telegram_goals_bot` — полный путь к папке проекта
   - `EnvironmentFile=/path/to/telegram_goals_bot/.env`
   - `ExecStart=/usr/bin/python3 /path/to/telegram_goals_bot/bot.py` (и аналогично webapp_server.py)

3. Включите и запустите:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable goals-bot goals-webapp
   sudo systemctl start goals-bot goals-webapp
   ```

4. Проверка статуса и логов:
   ```bash
   sudo systemctl status goals-bot
   sudo systemctl status goals-webapp
   journalctl -u goals-bot -f
   journalctl -u goals-webapp -f
   ```

Логи также пишутся в папку `logs/`: `logs/bot.log` и `logs/webapp.log` — их можно смотреть в админ-странице в реальном времени.

## Админ-страница

Добавьте в `.env` переменную:
```
ADMIN_TOKEN=ваш_секретный_токен
```

Откройте в браузере (с того же домена, где развёрнут API):
```
https://ваш-домен.ru/admin.html?token=ваш_секретный_токен
```
или сохраните токен на странице в поле «ADMIN_TOKEN из .env» и нажмите «Сохранить и загрузить».

На админ-странице доступно:
- **Процессы** — запущены ли bot.py и webapp_server.py (по systemd), кнопки «Запустить» / «Остановить»
- **Логи** — последние 500 строк из `bot.log` или `webapp.log`, автообновление каждые 3 сек
- **Пользователи** — таблица: id, имя, @username, число миссий/целей/привычек, число запросов к Шаолень; сводка: всего пользователей и сколько делали запросы к мастеру
- **Запросы к Шаолень** — таблица с датой, пользователем, кратким текстом запроса и пометкой «фото». По клику на строку раскрывается полный запрос и ответ; кнопка «Скопировать запрос в буфер»

Запуск/остановка через админку вызывает `systemctl start/stop goals-bot` и `goals-webapp`. Для этого процесс веб-сервера должен иметь права на выполнение systemctl (например, запуск от пользователя с passwordless sudo для этих команд, либо отдельный скрипт с setuid).

## История в боте (веб-приложение)

В чате с мастером Шаолень по кнопке «История» каждая строка стала раскрываемой: нажмите по строке — отобразится полный текст запроса и ответа. Кнопка «Скопировать запрос в буфер» копирует запрос и ответ в буфер обмена.
