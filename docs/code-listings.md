# Листинги ключевых фрагментов кода

Ниже приведены 2 наиболее важных фрагмента проекта: интеграция с внешним API ЦБ РФ и серверная синхронизация данных в базу.

---

## Листинг 1. Интеграция с API ЦБ РФ и парсинг XML

Файл: `app/cbr_client.py`

```python
CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

def _parse_rates_xml(content: bytes) -> list[CbrRate]:
    root = etree.fromstring(content)
    rates_date = _parse_cbr_date(root.attrib.get("Date", date.today().strftime("%d.%m.%Y")))

    out: list[CbrRate] = []
    for valute in root.findall("Valute"):
        char_code = (valute.findtext("CharCode") or "").strip().upper()
        nominal = int((valute.findtext("Nominal") or "1").strip())
        name = (valute.findtext("Name") or "").strip()
        value = _parse_ru_decimal((valute.findtext("Value") or "0").strip())
        if not char_code:
            continue
        out.append(
            CbrRate(
                date=rates_date,
                char_code=char_code,
                nominal=nominal,
                value=value,
                name=name,
            )
        )
    return out

def fetch_daily_rates(timeout_s: float = 10.0) -> list[CbrRate]:
    resp = requests.get(CBR_DAILY_URL, timeout=timeout_s)
    resp.raise_for_status()
    return _parse_rates_xml(resp.content)
```

Этот фрагмент отвечает за получение официальных курсов валют с сайта ЦБ РФ.  
После HTTP-запроса сервер парсит XML-ответ, нормализует формат даты и чисел, и преобразует данные в типизированные объекты `CbrRate`.  
Именно этот модуль является точкой интеграции внешнего источника данных с внутренней логикой приложения.

---

## Листинг 2. Синхронизация данных и запись в БД

Файл: `app/main.py`

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

        rows = [
            RateRow(date=r.date, char_code=r.char_code, nominal=r.nominal, value=r.value, name=r.name)
            for r in rates
        ]
        count = upsert_rates(DB_PATH, rows)
        touch_last_sync(DB_PATH, ok=True, detail=f"rows_upserted={count}")
        return {"status": "ok", "synced": True, "date": rates_date, "rows_upserted": count}
    except HTTPException as e:
        touch_last_sync(DB_PATH, ok=False, detail=f"HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:
        touch_last_sync(DB_PATH, ok=False, detail=f"{type(e).__name__}: {e}")
        raise
```

Этот фрагмент показывает бизнес-логику синхронизации: получить актуальные курсы, проверить дубли и выполнить upsert в SQLite.  
Функция дополнительно записывает результат синхронизации в служебные метаданные, что полезно для диагностики и мониторинга состояния приложения.  
На этом этапе связываются внешний API, внутренняя модель данных и постоянное хранение в базе.
