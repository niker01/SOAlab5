# Запуск проєкту та приклади запитів

Цей документ містить інструкції з налаштування, запуску й перевірки проєкту через Postman, MCP Inspector та локальний стек моніторингу. Усі команди Docker виконуй у PowerShell з кореневої папки проєкту.

## Event Storming сесія
![Event Storming сесія](images/eventstorming.png)

## Діаграма контекстів і компонентів
![Діаграма контекстів і компонентів](images/diagram.png)

## Архітектура мікросервісної системи
![Архітектура мікросервісної системи](images/architecture.png)

## Мікросервісна діаграма викликів(Users)
![Мікросервісна діаграма викликів Users](images/users.png)

## Мікросервісна діаграма викликів(Tasks & Task Lists)
![Мікросервісна діаграма викликів Tasks & Task Lists](images/tasks.png)

## Мікросервісна діаграма викликів(Reminders & Notifications)
![Мікросервісна діаграма викликів Reminders & Notifications](images/reminders.png)

## Структура проєкту

```text
SOAlab/
├── ai-integration/
│   ├── a2a_agent.py          # A2A Producer і Consumer
│   ├── function_calling.py   # Function Calling endpoint, tools і mock-режим
│   ├── mcp_server.py         # MCP tools, resources і prompt
│   ├── api_client.py         # Спільний клієнт для REST-сервісів
│   ├── ai_database.py        # Облік використання токенів
│   ├── requirements.txt      # Залежності AI-сервісів
│   └── Dockerfile
├── user-service/
│   ├── main.py               # API профілів користувачів із Keycloak JWT
│   ├── database.py            # Робота з базою даних користувачів
│   ├── rabbitmq.py             # Обмін подіями через RabbitMQ
│   ├── requirements.txt
│   └── Dockerfile
├── task-service/
│   ├── main.py               # API задач і списків, планування reminder
│   ├── schemas.py             # Схеми задач і списків
│   ├── database.py            # База даних і outbox
│   ├── rabbitmq.py             # Обробка та передавання подій
│   ├── requirements.txt
│   └── Dockerfile
├── notification-service/
│   ├── main.py               # API reminders і notifications та reminder worker
│   ├── schemas.py             # Схеми нагадувань і сповіщень
│   ├── database.py            # База даних і outbox
│   ├── rabbitmq.py             # Отримання подій від інших сервісів
│   ├── requirements.txt
│   └── Dockerfile
├── monitoring/
│   ├── prometheus.yml       # Цілі збору метрик
│   ├── alerts.yml           # Правила сповіщень
│   ├── alertmanager.yml     # Передавання сповіщень у n8n
│   ├── grafana/             # Джерело Prometheus і dashboard
│   └── n8n/                 # Workflow створення Jira-інциденту
├── nginx/
│   └── nginx.conf             # Маршрутизація API-запитів до сервісів
├── auth.py                    # Спільна перевірка JWT, OAuth scopes і CORS
├── observability.py           # Метрики HTTP, trace context і структуровані логи
├── keycloak/
│   ├── soa-realm.json         # Realm, OAuth clients, scopes та PKCE
│   └── configure-atlassian.sh # Необов'язкове підключення Atlassian OIDC
├── docker-compose.yml         # Сервіси, Keycloak, мережа, порти й volumes
├── .env.example               # Шаблон змінних середовища
├── .dockerignore
├── .gitignore
└── PROJECT_EXPLANATION_UK.md  # Інструкція запуску й тестування
```

`docker-compose.yml` запускає сервіси та RabbitMQ у спільній Docker-мережі. Клієнтські запити до REST API та Function Calling проходять через Nginx. MCP-сервер і A2A-агенти запускаються окремими контейнерами, а всередині мережі звертаються до User, Task і Notification Service. Локальний `.env` містить власні налаштування та секрети, тому в структурі наведено лише безпечний шаблон `.env.example`.

## 1. Налаштування

Потрібні Docker Desktop із запущеним Docker Engine та Postman. Проєкт використовує Keycloak як OAuth 2.0 / OpenID Connect сервер: для захищених запитів отримуй JWT через Authorization Code flow з PKCE. Keycloak не запуститься, доки в `.env` не буде задано власний `KEYCLOAK_ADMIN_PASSWORD`. Не використовуй локальні навчальні значення в публічному розгортанні.

Якщо `.env` ще не існує, створи його з шаблону:

```powershell
Copy-Item .env.example .env
notepad .env
```

Задай у `.env` `KEYCLOAK_ADMIN_PASSWORD` на власне локальне значення. Якщо файл уже існує, не перезаписуй його: додай відсутні Keycloak-змінні, зберігши поточні налаштування. `.env` ігнорується Git і Docker build context.

Щоб увімкнути зовнішній вхід через Atlassian, зареєструй OAuth 2.0 (3LO) app у Atlassian Developer Console і додай у `.env` отримані `ATLASSIAN_CLIENT_ID` та `ATLASSIAN_CLIENT_SECRET`. Redirect URI для app:

```text
http://localhost:8081/realms/soa/broker/atlassian/endpoint
```

Після першого запуску Keycloak створи або онови Atlassian IdP:

```powershell
docker compose --profile idp-setup up --force-recreate keycloak-idp-setup
```

Якщо credentials порожні, скрипт пропустить налаштування провайдера. У production заміни локальні issuer/public URL та Atlassian callback на HTTPS-адресу Keycloak.

Function Calling можна запускати в `mock` режимі без OpenAI API-ключа або в `openai` режимі з ключем. Не додавай OpenAI чи Atlassian secrets до Postman, README або `.env.example`.

## 2. Запуск і зупинка

Зібрати образи та запустити всі сервіси у фоні:

```powershell
docker compose up --build -d
docker compose ps
```

Keycloak доступний на `http://localhost:8081`; realm і OAuth clients імпортуються з `keycloak/soa-realm.json` під час першого запуску. Адміністратор входить із credentials із `.env`. Realm `soa` дозволяє самостійну реєстрацію користувачів.

Переглянути логи:

```powershell
docker compose logs --tail=100 user-service
docker compose logs --tail=100 task-service
docker compose logs --tail=100 notification-service
docker compose logs --tail=100 producer-agent
docker compose logs --tail=100 consumer-agent
docker compose logs --tail=100 mcp-server
docker compose logs --tail=100 keycloak
```

## Моніторинг і автоматичне створення інцидентів

Prometheus, Grafana, Alertmanager, n8n та експортери запускаються разом із проєктом командою `docker compose up --build -d`.

Локальні адреси:

- Grafana: `http://localhost:3001`;
- Prometheus: `http://localhost:9090`;
- Alertmanager: `http://localhost:9093`;
- n8n: `http://localhost:6001`.

Початковий локальний пароль Grafana — `admin`. Зміни його у своєму `.env` через `GRAFANA_ADMIN_PASSWORD`; для користувача можна задати `GRAFANA_ADMIN_USER`. Не використовуй пароль за замовчуванням поза локальним середовищем. Під час першого відкриття n8n створи локальний обліковий запис.

Кожен FastAPI-сервіс надає `/metrics` та `/health`; наприклад, метрики Task Service доступні на `http://localhost:8002/metrics`. Prometheus збирає лічильники HTTP-запитів і гістограми тривалості запитів. Grafana автоматично налаштовує Prometheus як джерело та завантажує dashboard `SOAlab Overview`, де відображаються p50/p95/p99 затримки, пропускна здатність, частка відповідей 5xx, стан компонентів, черги RabbitMQ та розподіл запитів між сервісами й маршрутами.

Кожен HTTP-запит має W3C Trace Context (`traceparent`). Gateway передає його сервісам, а внутрішні HTTP-виклики A2A/REST поширюють той самий trace ID. Структуровані JSON-записи містять `trace_id`, `span_id`, назву сервісу, маршрут, код відповіді та тривалість. Переглядати їх можна через `docker compose logs`; токени та тіла запитів у журнал не записуються.

Prometheus формує сповіщення, коли компонент недоступний щонайменше хвилину, p99 затримка HTTP перевищує 1 секунду протягом 5 хвилин, частка відповідей 5xx перевищує 5% протягом 5 хвилин або в черзі RabbitMQ понад 10 повідомлень очікують протягом 2 хвилин.

Alertmanager передає активні сповіщення до webhook n8n. Щоб n8n автоматично створював Jira-інциденти:

1. Відкрий `http://localhost:6001` і створи локальний обліковий запис n8n.
2. Імпортуй workflow з `monitoring/n8n/alertmanager-jira.json`.
3. У n8n створи облікові дані **HTTP Basic Auth**: ім’я користувача — email Atlassian, пароль — Atlassian API token. Не використовуй пароль від Atlassian-акаунта.
4. У вузлі **Create Jira incident** вибери ці облікові дані. Заміни `YOUR-ATLASSIAN-SITE` на адресу сайту формату `назва.atlassian.net`, а `YOUR_PROJECT_KEY` — на ключ Jira-проєкту. Переконайся, що в проєкті доступний тип задачі `Task`.
5. Збережи й активуй workflow. Шлях `alertmanager` у webhook має збігатися з URL `http://n8n:5678/webhook/alertmanager`, налаштованим для Alertmanager у Docker-мережі.

**Обмеження архітектури:** SOAlab не використовує coordinator/shards і репліковану базу даних. Сервіси зберігають дані в окремих SQLite-базах. Тому dashboard показує здоров’я Gateway і сервісів та розподіл запитів між сервісами; shard distribution і replication lag у цій архітектурі відсутні. Кількість повідомлень RabbitMQ показана як backlog подій, а не як replication lag.

Зупинити сервіси, зберігши дані:

```powershell
docker compose down
```

Не додавай `-v`, якщо потрібно зберегти Keycloak-користувачів, локальні профілі й тестові дані у Docker volumes.

Основна адреса для запитів через Nginx — `http://localhost:8080`. Keycloak працює на `http://localhost:8081`. Сервіси також доступні напряму: User Service на `8001`, Task Service на `8002`, Notification Service на `8003`. Інтерфейси Swagger:

- `http://localhost:8001/docs`
- `http://localhost:8002/docs`
- `http://localhost:8003/docs`

## 3. Налаштування Postman

Створи колекцію `SOAlab` і, за бажанням, environment із такими змінними:

| Змінна | Значення |
|---|---|
| `base_url` | `http://localhost:8080` |
| `access_token` | заповнити після входу |
| `user_id` | `sub` з Keycloak access token |
| `task_id` | заповнити після створення задачі |
| `list_id` | заповнити після створення списку |

Для запитів із JSON вибирай **Body → raw → JSON**. Для запитів, що потребують авторизації, встанови **Authorization → Bearer Token** і значення `{{access_token}}`.

## 4. OAuth2 вхід через Postman

Реєстрація та пароль обробляються Keycloak; старі `/users/register` і `/users/login` більше не створюють локальні або підроблені токени. У Postman відкрий **Authorization → OAuth 2.0 → Get New Access Token** і задай:

Попередні `fake-jwt-token` та користувачі зі старого локального login flow не мігрують автоматично. Для нового тесту створи обліковий запис у Keycloak; якщо в локальній БД уже є профіль з таким email, User Service поверне `409`, щоб не прив’язати його непомітно до іншої identity.

| Налаштування | Значення |
|---|---|
| Grant Type | Authorization Code (With PKCE) |
| Callback URL | `https://oauth.pstmn.io/v1/callback` |
| Auth URL | `http://localhost:8081/realms/soa/protocol/openid-connect/auth` |
| Access Token URL | `http://localhost:8081/realms/soa/protocol/openid-connect/token` |
| Client ID | `soa-postman` |
| Client Secret | порожньо (public client) |
| Code Challenge Method | `S256` |

У запитуваних scopes вкажи тільки потрібні. Для повного набору Postman-прикладів можна використати:

```text
openid profile email users:read users:write tasks:read tasks:write notifications:read notifications:write ai:use mcp:use a2a:invoke
```

Натисни **Get New Access Token**, увійди локальним Keycloak-користувачем або вибери Atlassian, якщо IdP налаштовано, а потім **Use Token**. Збережи access token у `{{access_token}}` та передавай його як Bearer Token. У браузерному клієнті кафедри використовується client ID `cad-kpi-client`, Authorization Code з PKCE та redirect URI на `https://cad.kpi.ua`.

Scopes розділені за ресурсами:

| Scope | Доступ |
|---|---|
| `users:read`, `users:write` | читання профілю / видалення локального профілю |
| `tasks:read`, `tasks:write` | читання / зміна задач і списків |
| `notifications:read`, `notifications:write` | читання / зміна reminders і notifications |
| `ai:use` | виклик Function Calling |
| `mcp:use` | під'єднання до MCP tools |
| `a2a:invoke` | виклик A2A агентів |

Наприклад, створення reminder додатково потребує `tasks:read` для перевірки власності задачі та `notifications:write`. Мікросервіси перевіряють scope самостійно; одного дозволу на gateway недостатньо.

FastAPI дозволяє CORS-запити з `https://cad.kpi.ua` (і локальних адрес для тестування). Nginx явно передає `Authorization` та `Origin` до сервісу, а CORS-відповідь не перезаписує. Перевір preflight у PowerShell:

```powershell
$corsHeaders = @{
  Origin = "https://cad.kpi.ua"
  "Access-Control-Request-Method" = "GET"
  "Access-Control-Request-Headers" = "authorization,content-type"
}
Invoke-WebRequest -Method Options -Uri "http://localhost:8080/tasks" -Headers $corsHeaders
```

У відповіді очікуй `Access-Control-Allow-Origin: https://cad.kpi.ua`. Для іншого production hostname додай його до `CORS_ORIGINS` без wildcard.

OAuth access token — це підписаний JWT. Кожний API сервіс перевіряє підпис через Keycloak JWKS, `issuer`, `audience`, строк дії та потрібні scopes у [auth.py](./auth.py); відсутній scope повертає HTTP 403. Старий формат `fake-jwt-token-...` більше не приймається.

## 5. REST API через Postman

### Створити список

`POST {{base_url}}/lists`, Bearer Token `{{access_token}}`:

```json
{
  "title": "Навчання"
}
```

Збережи `id` зі створеного списку у `list_id`.

### Створити задачу

`POST {{base_url}}/tasks`, Bearer Token `{{access_token}}`:

```json
{
  "title": "Перевірити API",
  "description": "Тестова задача",
  "list_id": "{{list_id}}",
  "due_date": null
}
```

Збережи `task.id` у `task_id`. Для дати використовуй ISO 8601, наприклад `2030-01-02T15:30:00`. Створення задачі з датою запускає Saga для створення нагадування; для першої перевірки можна залишити `due_date` рівним `null`.

У Windows PowerShell для JSON-запиту зручніше використовувати `Invoke-RestMethod`, щоб уникнути проблем з екрануванням лапок у `curl.exe`:

```powershell
$headers = @{ Authorization = "Bearer $accessToken" }
$body = @{ title = "Перевірити API" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/tasks" -Headers $headers -ContentType "application/json" -Body $body
```

### Переглянути й оновити задачі

- `GET {{base_url}}/tasks` — список задач.
- `GET {{base_url}}/tasks/{{task_id}}` — одна задача.
- `PUT {{base_url}}/tasks/{{task_id}}` — змінити задачу:

```json
{
  "title": "Оновлена назва"
}
```

Для оновлення метод `PUT` приймає поля `title`, `description`, `status`, `due_date`.

### Створити нагадування

`POST {{base_url}}/reminders`, Bearer Token `{{access_token}}`:

```json
{
  "task_id": "{{task_id}}",
  "reminder_time": "2030-01-02T15:00:00",
  "is_active": true
}
```

Переглянути нагадування: `GET {{base_url}}/reminders`.

### Переглянути сповіщення

`GET {{base_url}}/notifications`, Bearer Token `{{access_token}}`.

Вручну надіслати тестове сповіщення можна так:

`POST {{base_url}}/notifications/send`, Bearer Token `{{access_token}}`:

```json
{
  "user_id": "{{user_id}}",
  "message": "Тестове сповіщення",
  "channel": "push"
}
```

### Видалити тестову задачу

`DELETE {{base_url}}/tasks/{{task_id}}`, Bearer Token `{{access_token}}`.

## 6. Function Calling через Postman

### Перевірка без OpenAI API-ключа

У `.env` установи:

```dotenv
AI_FUNCTION_CALLING_MODE=mock
```

Для цього режиму `OPENAI_API_KEY` не потрібен. Пересоздай лише Producer Agent, щоб він прочитав нову конфігурацію:

```powershell
docker compose up -d --force-recreate producer-agent
```

Образ перебудовувати не потрібно, якщо код не змінювався.

Створи запит `AI chat`:

- Method: `POST`
- URL: `{{base_url}}/ai/chat`
- Authorization: Bearer Token `{{access_token}}`
- Body:

```json
{
  "prompt": "Email: ai-test@example.com\nList my tasks.",
  "confirm_writes": false
}
```

Mock-режим шукає email у prompt, перевіряє його через tool `verify_account_email`, а потім викликає `list_tasks`. Відповідь містить `"mode": "mock"`, `"model": "mock"`, `"tokens_used": 0` і список `"tools_called"`; у `reply` виводяться назви знайдених задач або повідомлення, що задач немає. Це перевіряє зв'язок endpoint → tools → REST API, але не перевіряє справжню LLM.

Щоб перевірити створення тестової задачі, надішли:

```json
{
  "prompt": "Email: ai-test@example.com\nCreate task: Mock function calling test",
  "confirm_writes": true
}
```

Задача створиться через Task Service. Перевір її через `GET {{base_url}}/tasks`. Без `"confirm_writes": true` створення буде відхилено.

Для повернення до справжнього OpenAI-виклику зміни `AI_FUNCTION_CALLING_MODE=openai` у `.env` і пересоздай Producer Agent тією ж командою. Для цього режиму потрібен чинний OpenAI API-ключ і доступний API-білінг.

## 7. MCP через MCP Inspector

MCP — це окремий протокол, тому цей тест виконуй у MCP Inspector, а не звичайним REST-запитом у Postman:

1. Запусти потрібні сервіси командою `docker compose up -d --build mcp-server notification-service`.
2. Запусти Inspector в окремому вікні PowerShell:

   ```powershell
   docker run --rm -p 127.0.0.1:6274:6274 ghcr.io/modelcontextprotocol/inspector
   ```

   Перший запуск завантажить Docker-образ Inspector. Залиш це вікно відкритим і відкрий адресу, яку команда надрукує, або `http://localhost:6274`.
3. У MCP Inspector натисни **Add Servers → Add manually**, вибери транспорт **Streamable HTTP** і вкажи URL `http://host.docker.internal:8004/mcp`. Оскільки Inspector запущений у Docker, тут потрібен `host.docker.internal`, а не `localhost`.
4. Додай HTTP header `Authorization` зі значенням `Bearer <access_token>`.
5. Під'єднайся та перевір tools `get_current_account`, `list_tasks`, `list_task_lists`, `list_reminders` і `list_notifications`, а також URI templates `todo://me/account/{user_id}` і `todo://me/tasks/{user_id}`. Для `{user_id}` використовуй `id` із `get_current_account`; сервер звіряє його з автентифікованим акаунтом.
6. Для створення задачі виклич tool `create_task` з аргументами `title` і `confirmation: "CONFIRM"`. Для оновлення також додай `confirmation: "CONFIRM"`. Видалення вимагає `confirmation: "DELETE"`.
7. `create_reminder` перевіряє через Task Service, що задача існує й належить поточному користувачу. MCP не надає окремого tool для негайного надсилання notification: notification створюється reminder worker-ом, коли настає час нагадування.

Підтвердження у вигляді аргументу має передаватися MCP-клієнтом після погодження користувача; сам рядок не є криптографічним підтвердженням.

## 8. A2A Producer → Consumer через Postman

Повний флоу: Postman надсилає A2A-запит Producer-у → Producer створює задачу через Task Service → Task Service планує reminder на `due_date` → Producer передає `task_id` Consumer-у → Consumer перевіряє задачу й підтверджує обробку → коли настає `due_date`, Notification Service створює notification. До настання терміну notification не створюється.

Перед тестом переконайся, що запущені `producer-agent`, `consumer-agent`, `task-service`, `notification-service` і `rabbitmq` (`docker compose ps`), а в Postman після OAuth2 Authorization Code flow встановлена змінна `{{access_token}}`. Токен повинен містити `a2a:invoke`, `tasks:read` і `tasks:write`. Додай у Postman environment змінну `due_date` з майбутнім часом ISO 8601, наприклад `2030-01-02T15:00:00+02:00`. Щоб перевірити появу notification під час тесту, встанови її приблизно на 1–2 хвилини вперед від поточного локального часу. Перед запуском переглянь `GET {{base_url}}/tasks`, `GET {{base_url}}/reminders` і `GET {{base_url}}/notifications`, щоб відрізняти нові записи.

Створи запит `A2A create task and schedule reminder`:

- Method: `POST`
- URL: `{{base_url}}/a2a/jsonrpc`
- Authorization: Bearer Token `{{access_token}}`
- Headers:
  - `Content-Type: application/json`
  - `A2A-Version: 1.0`
- У вкладці Authorization обери тип **Bearer Token** і введи `{{access_token}}`.
- Body:

```json
{
  "jsonrpc": "2.0",
  "id": "{{$guid}}",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "{{$guid}}",
      "contextId": "{{$guid}}",
      "role": "ROLE_USER",
      "parts": [
        {
          "text": "{\"title\":\"A2A reminder flow test\",\"description\":\"Перевірка Producer, Consumer і reminder\",\"due_date\":\"{{due_date}}\"}"
        }
      ]
    }
  }
}
```

Переконайся, що заголовок `A2A-Version` увімкнений і має саме значення `1.0`. Метод `SendMessage` і роль `ROLE_USER` потрібні для A2A 1.0.

Успішна відповідь має містити `result.task.status.state: "TASK_STATE_COMPLETED"`. У `result.task.artifacts` відкрий текст результату: там буде створена задача та повідомлення, що reminder запланований, а notification буде створено, коли настане час. Це підтвердження обробки події Consumer-ом, а не відправка notification. Перевір результат запитами з тим самим Bearer-токеном:

- `GET {{base_url}}/tasks` — має з'явитися `A2A reminder flow test` із заданим `due_date`.
- `GET {{base_url}}/reminders` — має з'явитися активний reminder зі статусом `PENDING` і часом `due_date`.
- До настання `due_date` у `GET {{base_url}}/notifications` не має з'явитися новий запис для створеної задачі.

Дочекайся `due_date` плюс до 10 секунд: Notification Service перевіряє reminders кожні 10 секунд. Після цього `GET {{base_url}}/reminders` має показати статус `TRIGGERED`, а `GET {{base_url}}/notifications` — notification із `task_id`, що збігається з ID створеної задачі. Проєкт створює notification-запис у Notification Service; це не означає реальне надсилання push-повідомлення на пристрій.

Якщо передати `"due_date": null`, reminder і notification не створюються. A2A-відповідь `TASK_STATE_COMPLETED` підтверджує обробку події Consumer-ом, а не негайну відправку notification.

Якщо A2A-відповідь має стан `TASK_STATE_FAILED` або немає reminder, перевір логи:

```powershell
docker compose logs --tail=100 producer-agent consumer-agent
docker compose logs --tail=100 task-service notification-service
```

Agent Cards можна відкрити в Postman або браузері:

- Producer: `GET http://localhost:8010/.well-known/agent-card.json`
- Consumer: `GET http://localhost:8011/.well-known/agent-card.json`

> A2A передає той самий підписаний Bearer JWT у внутрішньому виклику Consumer-у. Не виставляй Keycloak у публічну мережу з локальними обліковими даними адміністратора або без HTTPS.
