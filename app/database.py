from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class RateRow:
    date: str
    char_code: str
    nominal: int
    value: float
    name: str


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exchange_rates (
                date TEXT NOT NULL,
                char_code TEXT NOT NULL,
                nominal INTEGER NOT NULL,
                value REAL NOT NULL,
                name TEXT NOT NULL,
                PRIMARY KEY (date, char_code)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exchange_rates_code_date "
            "ON exchange_rates(char_code, date)"
        )


def upsert_rates(db_path: Path, rates: list[RateRow]) -> int:
    if not rates:
        return 0
    with _connect(db_path) as conn:
        cur = conn.executemany(
            """
            INSERT INTO exchange_rates(date, char_code, nominal, value, name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, char_code) DO UPDATE SET
                nominal=excluded.nominal,
                value=excluded.value,
                name=excluded.name
            """,
            [(r.date, r.char_code, r.nominal, r.value, r.name) for r in rates],
        )
        return cur.rowcount


def get_available_codes(db_path: Path) -> list[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT char_code FROM exchange_rates ORDER BY char_code"
        ).fetchall()
        return [str(r["char_code"]) for r in rows]


def get_rates(db_path: Path, char_code: str, days: int = 30) -> list[RateRow]:
    days = max(1, min(int(days), 3650))
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT date, char_code, nominal, value, name
            FROM exchange_rates
            WHERE char_code = ?
              AND date >= date('now', ?)
            ORDER BY date ASC
            """,
            (char_code.upper(), f"-{days} days"),
        ).fetchall()
        return [
            RateRow(
                date=str(r["date"]),
                char_code=str(r["char_code"]),
                nominal=int(r["nominal"]),
                value=float(r["value"]),
                name=str(r["name"]),
            )
            for r in rows
        ]


def has_rates_for_date(db_path: Path, d: date) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM exchange_rates WHERE date = ? LIMIT 1", (d.isoformat(),)
        ).fetchone()
        return row is not None

