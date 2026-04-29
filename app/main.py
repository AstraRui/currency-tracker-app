from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import DB_PATH, STATIC_DIR
from app.core.sync_service import safe_sync_today, sync_today
from app.database import init_db

logger = logging.getLogger(__name__)

app = FastAPI(title="Currency Tracker", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(router)

scheduler: BackgroundScheduler | None = None


@app.on_event("startup")
def _startup() -> None:
    global scheduler

    init_db(DB_PATH)
    try:
        sync_today()
    except Exception:
        logger.exception("Startup sync failed")

    scheduler = BackgroundScheduler()
    scheduler.add_job(safe_sync_today, "cron", hour=0, minute=5, id="daily_cbr_sync", replace_existing=True)
    scheduler.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None