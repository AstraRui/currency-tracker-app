# Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor U as Пользователь
    participant UI as Frontend (Browser)
    participant API as FastAPI Backend
    participant DB as SQLite
    participant CBR as API ЦБ РФ

    U->>UI: Открывает приложение
    UI->>API: GET /api/codes
    API->>DB: SELECT DISTINCT char_code
    DB-->>API: Список кодов
    API-->>UI: JSON codes

    U->>UI: Нажимает "Синхронизировать сегодня"
    UI->>API: POST /api/sync
    API->>CBR: Запрос XML Daily
    CBR-->>API: Курсы валют (XML)
    API->>DB: UPSERT exchange_rates
    API->>DB: UPDATE app_meta(last_sync)
    API-->>UI: JSON {synced, date}

    U->>UI: Выбирает валюту и период
    UI->>API: GET /api/rates/{CODE}?days=N
    API->>DB: SELECT rates by code/date
    DB-->>API: История значений
    API-->>UI: JSON points
    UI-->>U: Отрисовка графика Chart.js
```

Диаграмма последовательности описывает полный обмен данными между пользователем, интерфейсом, FastAPI, SQLite и API ЦБ РФ.  
На ней показаны три ключевых потока: первичная загрузка кодов валют, синхронизация актуальных курсов и запрос истории для графика.  
Схема демонстрирует, что фронтенд работает только через API бэкенда, а все операции чтения/записи выполняются на стороне сервера.
