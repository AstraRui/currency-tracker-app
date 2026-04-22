from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.cbr_client import fetch_daily_rates
from app.database import RateRow, get_available_codes, get_rates, has_rates_for_date, init_db, upsert_rates


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "currency.sqlite3"
TEMPLATE_PATH = BASE_DIR / "templates" / "index.html"

app = FastAPI(title="Currency Tracker", version="0.1.0")


def sync_today() -> dict:
    today = date.today()
    if has_rates_for_date(DB_PATH, today):
        return {"status": "ok", "synced": False, "date": today.isoformat(), "reason": "already in db"}

    rates = fetch_daily_rates()
    rows = [
        RateRow(date=r.date, char_code=r.char_code, nominal=r.nominal, value=r.value, name=r.name)
        for r in rates
    ]
    count = upsert_rates(DB_PATH, rows)
    return {"status": "ok", "synced": True, "date": today.isoformat(), "rows_upserted": count}


@app.on_event("startup")
def _startup() -> None:
    init_db(DB_PATH)
    try:
        sync_today()
    except Exception:
        pass


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

