# Currency Tracker

**Тема практики:** Осуществление интеграции программных модулей
**Номер и название темы:** Интеграция валютных данных ЦБ РФ в систему учета.
**Группа:**  9-3 РПО 2023/1

## 1. СОСТАВ КОМАНДЫ

- Павел Якоби (Роль: DevOps/Архитектор, Backend, Frontend) - ответственность: архитектура проекта, серверная логика, интеграция с API ЦБ РФ, работа с базой данных, интерфейс, визуализация и сборка.

## 2. ТЕХНИЧЕСКИЙ СТЕК

- Язык программирования: Python 3.12, JavaScript
- Бэкенд фреймворк: FastAPI
- База данных: SQLite
- Внешние интеграции: API Центрального банка РФ (XML Daily)
- Ключевые библиотеки: requests, APScheduler, Alembic, Pydantic, Chart.js, Tailwind CSS, FlyonUI

## 3. ЛОГИКА РАБОТЫ И ИНТЕГРАЦИИ

Фронтенд запрашивает данные у бэкенда через REST API.  
Бэкенд обращается к API ЦБ РФ, получает и обрабатывает курсы валют, сохраняет их в SQLite.  
Затем подготовленные данные возвращаются на фронтенд для отображения карточек валют, таблиц и графика динамики курса.

Для ускорения интерфейса в API используется краткоживущий in-memory cache:
- `/api/favorites` кэшируется на 30 секунд;
- `/api/rates/{char_code}?days=N` кэшируется на 15 секунд;
- после `POST /api/sync` кэш очищается, чтобы фронтенд получил актуальные данные.

## 4. ИНСТРУКЦИЯ ПО ЗАПУСКУ

Шаг 1: Клонирование репозитория командой:

```powershell
git clone https://github.com/AstraRui/currency-tracker-app.git
cd currency-tracker-app
```

Шаг 2: Установка зависимостей:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv sync
npm install
```

Шаг 3: Запуск проекта:

```powershell
npm run build:css
uv run uvicorn app.main:app --reload
```

После запуска откройте в браузере `http://127.0.0.1:8000/`.

## Структура проекта

- `app/main.py` - точка входа приложения (инициализация FastAPI, scheduler, подключение роутов).
- `app/api/routes.py` - HTTP-эндпоинты и обработчики API.
- `app/core/sync_service.py` - бизнес-логика синхронизации и backfill курсов.
- `app/core/config.py` - пути и базовые настройки приложения.
- `app/schema.py` - SQLAlchemy metadata для Alembic.
- `app/database.py` - работа с SQLite (query, upsert, stats, meta).

## 5. ФУНКЦИОНАЛЬНЫЕ ВОЗМОЖНОСТИ

- Получение актуальных курсов валют из API ЦБ РФ и синхронизация в локальную базу.
- Построение графика изменений курса выбранной валюты за заданное количество дней.
- Отображение популярных валют и дневных изменений с удобным интерфейсом.
- Ускоренная выдача данных для графика и блока популярных валют за счет короткого серверного кэша.

## 6. СКРИНШОТ ПРИЛОЖЕНИЯ

![Скриншот интерфейса Currency Tracker](assets/app-screenshot-day6.png)

## 7. МАТЕРИАЛЫ ДЛЯ ОТЧЕТА

Ниже собраны UML-схемы и ключевые листинги в формате раскрывающихся блоков.

<details>
  <summary><strong>Use Case Diagram</strong> (роли и варианты использования)</summary>

```mermaid
flowchart LR
    User["Пользователь"]:::actor
    Admin["Администратор/Разработчик"]:::actor
    CBR["API ЦБ РФ"]:::external

    subgraph System["Currency Tracker"]
      UC1(("Просмотр текущих курсов"))
      UC2(("Просмотр графика за период"))
      UC3(("Выбор валюты и диапазона дней"))
      UC4(("Синхронизация курсов"))
      UC5(("Просмотр популярных валют"))
      UC6(("Переключение темы интерфейса"))
      UC7(("Хранение истории в БД"))
    end

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC5
    User --> UC6

    Admin --> UC4
    UC4 --> CBR
    UC4 --> UC7
    UC1 --> UC7
    UC2 --> UC7
    UC5 --> UC7

    classDef actor fill:#eef6ff,stroke:#2563eb,color:#111827;
    classDef external fill:#fff7ed,stroke:#ea580c,color:#111827;
```

Источник: `docs/uml/use-case.md`
</details>

<details>
  <summary><strong>Sequence Diagram</strong> (процесс обмена данными)</summary>

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
    alt Есть свежий cache (15s)
        API-->>UI: JSON points (from cache)
    else Cache miss
        API->>DB: SELECT rates by code/date
        DB-->>API: История значений
        alt История отсутствует и days > 4
            API->>CBR: Backfill недостающих дат (до 14 дней)
            CBR-->>API: Курсы валют (XML)
            API->>DB: UPSERT backfill rows
        end
    end
    API-->>UI: JSON points
    UI-->>U: Отрисовка графика Chart.js
```

Источник: `docs/uml/sequence.md`
</details>

<details>
  <summary><strong>Database Schema (ER)</strong></summary>

```mermaid
erDiagram
    EXCHANGE_RATES {
        string date PK "Дата курса"
        string char_code PK "Код валюты (USD, EUR...)"
        int nominal "Номинал"
        float value "Значение курса"
        string name "Название валюты"
    }

    APP_META {
        string key PK "Ключ метаданных"
        string value "Значение"
    }
```

Источник: `docs/uml/database-schema.md`
</details>

<details>
  <summary><strong>Листинги ключевого кода</strong> (интеграция + синхронизация)</summary>

Полная версия листингов: `docs/code-listings.md`

```python
def fetch_daily_rates(timeout_s: float = 10.0) -> list[CbrRate]:
    resp = requests.get(CBR_DAILY_URL, timeout=timeout_s)
    resp.raise_for_status()
    return _parse_rates_xml(resp.content)
```

```python
def sync_today() -> dict:
    try:
        rates = fetch_daily_rates()
        if not rates:
            raise HTTPException(status_code=502, detail="CBR returned no rates")
        rates_date = rates[0].date
        if has_rates_for_date(DB_PATH, date.fromisoformat(rates_date)):
            touch_last_sync(DB_PATH, ok=True, detail="already in db")
            return {"status": "ok", "synced": False, "date": rates_date, "reason": "already in db"}
        rows = [RateRow(date=r.date, char_code=r.char_code, nominal=r.nominal, value=r.value, name=r.name) for r in rates]
        count = upsert_rates(DB_PATH, rows)
        touch_last_sync(DB_PATH, ok=True, detail=f"rows_upserted={count}")
        return {"status": "ok", "synced": True, "date": rates_date, "rows_upserted": count}
    except HTTPException as exc:
        touch_last_sync(DB_PATH, ok=False, detail=f"HTTP {exc.status_code}: {exc.detail}")
        raise
```

Источник реализации: `app/core/sync_service.py`
</details>