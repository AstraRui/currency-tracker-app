from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.cbr_client import fetch_daily_rates, fetch_daily_rates_for
from app.database import (
    RateRow,
    get_available_codes,
    get_rates,
    get_stats,
    has_rates_for_date,
    init_db,
    touch_last_sync,
    upsert_rates,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "currency.sqlite3"
TEMPLATE_PATH = BASE_DIR / "templates" / "index.html"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Currency Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

scheduler: BackgroundScheduler | None = None


def _backfill_days(days: int) -> int:
    """
    Fill missing daily snapshots for the last N days (best-effort).
    Returns number of days attempted to fetch.
    """
    days = max(1, min(int(days), 60))
    attempted = 0
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=i)
        if has_rates_for_date(DB_PATH, d):
            continue
        attempted += 1
        try:
            rates = fetch_daily_rates_for(d)
            if not rates:
                continue
            rows = [
                RateRow(date=r.date, char_code=r.char_code, nominal=r.nominal, value=r.value, name=r.name)
                for r in rates
            ]
            upsert_rates(DB_PATH, rows)
        except Exception:
            # Ignore single-day failures (weekends/network/etc.)
            continue
    return attempted


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

def _safe_sync_today() -> None:
    try:
        init_db(DB_PATH)
        sync_today()
    except Exception:
        pass


@app.on_event("startup")
def _startup() -> None:
    global scheduler

    init_db(DB_PATH)
    try:
        sync_today()
    except Exception:
        pass

    scheduler = BackgroundScheduler()
    scheduler.add_job(_safe_sync_today, "cron", hour=0, minute=5, id="daily_cbr_sync", replace_existing=True)
    scheduler.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="template not found")
    return HTMLResponse(TEMPLATE_PATH.read_text(encoding="utf-8"))


@app.get("/api/codes")
def api_codes() -> dict:
    return {"codes": get_available_codes(DB_PATH)}

@app.get("/api/stats")
def api_stats() -> dict:
    return get_stats(DB_PATH)

def _per1(value: float, nominal: int) -> float | None:
    if nominal <= 0:
        return None
    try:
        v = float(value) / float(nominal)
    except Exception:
        return None
    return v

def _pick_last(items: list[dict]) -> dict | None:
    return items[-1] if items else None

def _pick_prev(items: list[dict]) -> dict | None:
    return items[-2] if len(items) >= 2 else None

def _pick_days_ago(items: list[dict], days_ago: int) -> dict | None:
    if not items:
        return None
    target = items[-1]["date"]
    try:
        d_last = date.fromisoformat(str(target))
    except Exception:
        return None
    want = d_last.toordinal() - int(days_ago)
    best: dict | None = None
    for it in items:
        try:
            d = date.fromisoformat(str(it["date"])).toordinal()
        except Exception:
            continue
        if d <= want:
            best = it
    return best


@app.get("/api/favorites")
def api_favorites(limit: int = 10, spark_days: int = 14) -> dict:
    init_db(DB_PATH)
    limit = max(3, min(int(limit), 20))
    spark_days = max(7, min(int(spark_days), 60))

    preferred = ["USD", "EUR", "CNY", "GBP", "KZT", "JPY", "CHF", "TRY", "AED", "BYN", "GEL", "AMD"]
    available = get_available_codes(DB_PATH)
    ordered = [c for c in preferred if c in available]
    for c in available:
        if c not in ordered:
            ordered.append(c)
        if len(ordered) >= limit:
            break

    out: list[dict] = []
    for code in ordered:
        payload = None
        try:
            payload = api_rates(code, days=max(spark_days + 2, 9))
        except HTTPException:
            payload = None
        if not payload:
            continue

        items = payload.get("items") or []
        last = _pick_last(items)
        prev = _pick_prev(items)
        week = _pick_days_ago(items, 7)

        last_per1 = _per1(float(last["value"]), int(payload.get("nominal") or 1)) if last else None
        prev_per1 = _per1(float(prev["value"]), int(payload.get("nominal") or 1)) if prev else None
        week_per1 = _per1(float(week["value"]), int(payload.get("nominal") or 1)) if week else None

        delta_day = None
        if last_per1 is not None and prev_per1 is not None:
            delta_day = last_per1 - prev_per1

        delta7_pct = None
        if last_per1 is not None and week_per1 is not None and week_per1 != 0:
            delta7_pct = (last_per1 - week_per1) / week_per1 * 100.0

        spark = []
        for it in items[-spark_days:]:
            v = _per1(float(it["value"]), int(payload.get("nominal") or 1))
            if v is not None:
                spark.append({"date": it["date"], "value": v})

        out.append(
            {
                "code": payload.get("char_code") or code,
                "name": payload.get("name") or code,
                "nominal": int(payload.get("nominal") or 1),
                "as_of": last["date"] if last else None,
                "value_per_1": last_per1,
                "delta_day": delta_day,
                "delta7_pct": delta7_pct,
                "spark": spark,
            }
        )

    return {"items": out, "spark_days": spark_days, "limit": limit}


@app.get("/api/rates/{char_code}")
def api_rates(char_code: str, days: int = 30) -> dict:
    init_db(DB_PATH)
    days = max(1, min(int(days), 3650))
    # If user asks for more history than we likely have, pull recent days from CBR.
    # This turns the chart range control into something that works immediately.
    if days > 4:
        _backfill_days(min(days, 60))
    items = get_rates(DB_PATH, char_code=char_code, days=days)
    if not items:
        raise HTTPException(status_code=404, detail="no data for currency (try /api/sync)")
    return {
        "char_code": items[0].char_code,
        "name": items[0].name,
        "nominal": items[0].nominal,
        "days": days,
        "items": [{"date": r.date, "value": r.value} for r in items],
    }


@app.post("/api/sync")
def api_sync() -> dict:
    init_db(DB_PATH)
    return sync_today()

