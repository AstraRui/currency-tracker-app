from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import HTTPException

from app.cbr_client import fetch_daily_rates, fetch_daily_rates_for
from app.core.config import DB_PATH
from app.database import RateRow, has_rates_for_date, init_db, touch_last_sync, upsert_rates

logger = logging.getLogger(__name__)


def backfill_days(days: int) -> int:
    days = max(1, min(int(days), 60))
    attempted = 0
    today = date.today()
    for i in range(days):
        target_day = today - timedelta(days=i)
        if has_rates_for_date(DB_PATH, target_day):
            continue
        attempted += 1
        try:
            rates = fetch_daily_rates_for(target_day)
            if not rates:
                continue
            rows = [
                RateRow(date=r.date, char_code=r.char_code, nominal=r.nominal, value=r.value, name=r.name)
                for r in rates
            ]
            upsert_rates(DB_PATH, rows)
        except Exception:
            logger.exception("Backfill failed for %s", target_day.isoformat())
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
    except HTTPException as exc:
        touch_last_sync(DB_PATH, ok=False, detail=f"HTTP {exc.status_code}: {exc.detail}")
        raise
    except Exception as exc:
        touch_last_sync(DB_PATH, ok=False, detail=f"{type(exc).__name__}: {exc}")
        raise


def safe_sync_today() -> None:
    try:
        init_db(DB_PATH)
        sync_today()
    except Exception:
        logger.exception("Scheduled daily sync failed")
