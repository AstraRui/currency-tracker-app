from __future__ import annotations

from datetime import date, timedelta
from time import monotonic

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.core.config import DB_PATH, TEMPLATE_PATH
from app.core.sync_service import backfill_days, sync_today
from app.database import get_available_codes, get_rates, get_stats, init_db

router = APIRouter()
_FAVORITES_CACHE_TTL_S = 30.0
_RATES_CACHE_TTL_S = 15.0
_favorites_cache: dict[tuple[int, int], tuple[float, dict]] = {}
_rates_cache: dict[tuple[str, int], tuple[float, dict]] = {}


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="template not found")
    return HTMLResponse(TEMPLATE_PATH.read_text(encoding="utf-8"))


@router.get("/api/codes")
def api_codes() -> dict:
    return {"codes": get_available_codes(DB_PATH)}


@router.get("/api/stats")
def api_stats() -> dict:
    return get_stats(DB_PATH)


def _per1(value: float, nominal: int) -> float | None:
    if nominal <= 0:
        return None
    try:
        normalized = float(value) / float(nominal)
    except Exception:
        return None
    return normalized


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
    for item in items:
        try:
            d = date.fromisoformat(str(item["date"])).toordinal()
        except Exception:
            continue
        if d <= want:
            best = item
    return best


@router.get("/api/favorites")
def api_favorites(limit: int = 10, spark_days: int = 14) -> dict:
    init_db(DB_PATH)
    limit = max(3, min(int(limit), 20))
    spark_days = max(7, min(int(spark_days), 60))
    cache_key = (limit, spark_days)
    cached = _favorites_cache.get(cache_key)
    now = monotonic()
    if cached and (now - cached[0]) < _FAVORITES_CACHE_TTL_S:
        return cached[1]

    preferred = ["USD", "EUR", "CNY", "GBP", "KZT", "JPY", "CHF", "TRY", "AED", "BYN", "GEL", "AMD"]
    available = get_available_codes(DB_PATH)
    ordered = [code for code in preferred if code in available]
    for code in available:
        if code not in ordered:
            ordered.append(code)
        if len(ordered) >= limit:
            break
    ordered = ordered[:limit]

    out: list[dict] = []
    for code in ordered:
        items_rows = get_rates(DB_PATH, char_code=code, days=max(spark_days + 2, 9))
        if not items_rows:
            continue

        nominal = int(items_rows[0].nominal or 1)
        name = items_rows[0].name
        items = [{"date": row.date, "value": row.value} for row in items_rows]
        last = _pick_last(items)
        prev = _pick_prev(items)
        week = _pick_days_ago(items, 7)

        last_per1 = _per1(float(last["value"]), nominal) if last else None
        prev_per1 = _per1(float(prev["value"]), nominal) if prev else None
        week_per1 = _per1(float(week["value"]), nominal) if week else None

        delta_day = None
        if last_per1 is not None and prev_per1 is not None:
            delta_day = last_per1 - prev_per1

        delta7_pct = None
        if last_per1 is not None and week_per1 is not None and week_per1 != 0:
            delta7_pct = (last_per1 - week_per1) / week_per1 * 100.0

        spark = []
        for item in items[-spark_days:]:
            value_per_1 = _per1(float(item["value"]), nominal)
            if value_per_1 is not None:
                spark.append({"date": item["date"], "value": value_per_1})

        out.append(
            {
                "code": code,
                "name": name or code,
                "nominal": nominal,
                "as_of": last["date"] if last else None,
                "value_per_1": last_per1,
                "delta_day": delta_day,
                "delta7_pct": delta7_pct,
                "spark": spark,
            }
        )

    response = {"items": out, "spark_days": spark_days, "limit": limit}
    _favorites_cache[cache_key] = (now, response)
    return response


@router.get("/api/rates/{char_code}")
def api_rates(char_code: str, days: int = 30) -> dict:
    init_db(DB_PATH)
    code = char_code.upper()
    days = max(1, min(int(days), 3650))
    cache_key = (code, days)
    cached = _rates_cache.get(cache_key)
    now = monotonic()
    if cached and (now - cached[0]) < _RATES_CACHE_TTL_S:
        return cached[1]

    items = get_rates(DB_PATH, char_code=code, days=days)
    if days > 1:
        should_backfill = not items
        if items:
            dates = sorted({date.fromisoformat(row.date) for row in items})
            oldest = dates[0]
            latest = dates[-1]
            requested_from = date.today() - timedelta(days=days - 1)
            # On a fresh device there is often only "today", so proactively backfill history.
            sparse_history = len(dates) < min(3, days)
            does_not_cover_range = oldest > (requested_from + timedelta(days=2))
            stale_tail = (date.today() - latest).days > 2
            should_backfill = sparse_history or does_not_cover_range or stale_tail
        if should_backfill:
            backfill_days(min(max(days, 7), 60))
            items = get_rates(DB_PATH, char_code=code, days=days)
    if not items:
        raise HTTPException(status_code=404, detail="no data for currency (try /api/sync)")
    response = {
        "char_code": items[0].char_code,
        "name": items[0].name,
        "nominal": items[0].nominal,
        "days": days,
        "items": [{"date": row.date, "value": row.value} for row in items],
    }
    _rates_cache[cache_key] = (now, response)
    return response


@router.post("/api/sync")
def api_sync() -> dict:
    init_db(DB_PATH)
    result = sync_today()
    _favorites_cache.clear()
    _rates_cache.clear()
    return result
