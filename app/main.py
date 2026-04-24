from __future__ import annotations

from datetime import date
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.cbr_client import fetch_daily_rates
from app.database import (
    RateRow,
    get_available_codes,
    get_rates,
    has_rates_for_date,
    init_db,
    upsert_rates,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "currency.sqlite3"
TEMPLATE_PATH = BASE_DIR / "templates" / "index.html"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Currency Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

scheduler: BackgroundScheduler | None = None


def sync_today() -> dict:
    rates = fetch_daily_rates()
    if not rates:
        raise HTTPException(status_code=502, detail="CBR returned no rates")

    rates_date = rates[0].date
    if has_rates_for_date(DB_PATH, date.fromisoformat(rates_date)):
        return {"status": "ok", "synced": False, "date": rates_date, "reason": "already in db"}

    rows = [
        RateRow(date=r.date, char_code=r.char_code, nominal=r.nominal, value=r.value, name=r.name)
        for r in rates
    ]
    count = upsert_rates(DB_PATH, rows)
    return {"status": "ok", "synced": True, "date": rates_date, "rows_upserted": count}

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


@app.get("/api/rates/{char_code}")
def api_rates(char_code: str, days: int = 30) -> dict:
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

