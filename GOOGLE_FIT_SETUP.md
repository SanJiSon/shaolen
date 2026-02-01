# Настройка Google Fit

Для отображения шагов из Google Fit в профиле пользователя необходимо настроить OAuth в Google Cloud.

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

## 4. Примечания

- **Google Fit API** планируется к отключению в 2026 году. Рекомендуется ознакомиться с [Health Connect](https://developer.android.com/guide/health-and-fitness/health-connect) для будущей миграции.
- Шаги отображаются на вкладке «Профиль» (виджет «Шаги (Google Fit)») после подключения аккаунта в настройках.
