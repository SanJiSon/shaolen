# Настройка Google Fit

Для отображения шагов из Google Fit в профиле пользователя необходимо настроить OAuth в Google Cloud.

**Для пользователей бота:** каждому пользователю достаточно один раз открыть **Настройки** → **Авторизация Google Fit** → **Подключить** и войти в свой Google-аккаунт. После этого шаги будут отображаться на вкладке **Профиль** (блок «Общие»). Никакой отдельной настройки на каждого пользователя не требуется — токены хранятся в базе по Telegram user_id.

## 1. Google Cloud Console

1. Откройте [Google Cloud Console](https://console.cloud.google.com/).
2. Создайте проект или выберите существующий.
3. Включите **Fitness API**: APIs & Services → Library → найдите "Fitness API" → Enable.
4. Создайте учётные данные OAuth 2.0:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Web application**
   - Name: например "Goals Bot WebApp"
   - Authorized redirect URIs: `https://ВАШ_ДОМЕН/api/google-fit/callback`  
     (замените ВАШ_ДОМЕН на ваш домен, например `shaolen.duckdns.org`)
5. Скопируйте **Client ID** и **Client secret**.

## 2. Переменные окружения (.env)

Добавьте в `.env`:

```
GOOGLE_FIT_CLIENT_ID=ваш_client_id.apps.googleusercontent.com
GOOGLE_FIT_CLIENT_SECRET=ваш_client_secret
WEBAPP_BASE_URL=https://ваш-домен.com
```

`WEBAPP_BASE_URL` — базовый URL вашего приложения (без слэша в конце). По этому URL должны быть доступны:
- API: `{WEBAPP_BASE_URL}/api/...`
- Страница успеха: `{WEBAPP_BASE_URL}/google-fit-success.html`

## 3. Страница успеха

Файл `webapp/google-fit-success.html` должен отдаваться по адресу `/google-fit-success.html`. Если статику отдаёт Nginx, убедитесь, что этот файл доступен.

## 4. Ошибка «OAuth client was not found» / 401 invalid_client

Если при переходе по ссылке авторизации Google показывает эту ошибку:

1. **Проверьте Client ID**
   - В [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → **Credentials**.
   - Откройте ваш OAuth 2.0 Client ID (тип **Web application**).
   - Скопируйте **Client ID** целиком (формат: `123456789012-xxxxxxxxxx.apps.googleusercontent.com`).
   - В `.env` должно быть: `GOOGLE_FIT_CLIENT_ID=этот_значение` — без пробелов, кавычек и лишних символов.

2. **Тип учётных данных**
   - Должен быть именно **OAuth client ID** с типом приложения **Web application** (не Desktop, не Android).
   - Если создали не тот тип — создайте новый «OAuth client ID» → Application type: **Web application**.

3. **Redirect URI**
   - В настройках OAuth client в поле **Authorized redirect URIs** должна быть строка **точно**:
     `https://ВАШ_ДОМЕН/api/google-fit/callback`
   - Протокол `https://`, без слэша в конце, путь `/api/google-fit/callback`.
   - Домен — тот же, что в `WEBAPP_BASE_URL` (тот, с которого открывается веб-приложение).

4. **Перезапуск**
   - После изменений в `.env` перезапустите веб-сервер (uvicorn / systemd), чтобы переменные подхватились.

5. **Проверка значений на сервере**
   - Убедитесь, что `GOOGLE_FIT_CLIENT_ID` и `WEBAPP_BASE_URL` действительно читаются приложением (например, временно залогировать в эндпоинте `/api/user/.../google-fit/auth-url` без вывода секретов).

## 5. Ошибка «Access denied» / 403

Если Google показывает **403 Access denied** при попытке авторизации (параметры запроса при этом выглядят правильно):

1. **Режим «Тестирование» (Testing)**
   - В [Google Cloud Console](https://console.cloud.google.com/) откройте **APIs & Services** → **OAuth consent screen**.
   - Если вверху указано **Publishing status: Testing**, то входить могут только **тестовые пользователи**.
   - Прокрутите до блока **Test users** → нажмите **+ ADD USERS**.
   - Добавьте **адрес Gmail**, с которого вы заходите в приложение (тот же аккаунт, с которого авторизуетесь в Google Fit).
   - Сохраните. Повторите попытку входа через бота.

2. **Проверка Fitness API**
   - **APIs & Services** → **Library** → найдите **Fitness API** → убедитесь, что API **включён** (Enabled) для этого проекта.

3. **Публикация приложения (по желанию)**
   - Для доступа любых пользователей (не только из списка Test users) нужно отправить приложение на проверку Google (**Publish app** на OAuth consent screen). Для личного использования достаточно добавить себя в Test users (п. 1).

## 6. Примечания

- **Google Fit API** планируется к отключению в 2026 году. Рекомендуется ознакомиться с [Health Connect](https://developer.android.com/guide/health-and-fitness/health-connect) для будущей миграции.
- Шаги отображаются на вкладке «Профиль» (виджет «Шаги (Google Fit)») после подключения аккаунта в настройках.
