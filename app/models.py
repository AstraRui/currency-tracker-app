from __future__ import annotations

from sqlalchemy import Column, Float, Integer, MetaData, String, Table

metadata = MetaData()

exchange_rates = Table(
    "exchange_rates",
    metadata,
    Column("date", String, primary_key=True, nullable=False),
    Column("char_code", String, primary_key=True, nullable=False),
    Column("nominal", Integer, nullable=False),
    Column("value", Float, nullable=False),
    Column("name", String, nullable=False),
)

app_meta = Table(
    "app_meta",
    metadata,
    Column("key", String, primary_key=True, nullable=False),
    Column("value", String, nullable=False),
)

