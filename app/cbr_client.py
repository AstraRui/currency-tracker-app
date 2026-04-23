from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import requests
from lxml import etree

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


@dataclass(frozen=True)
class CbrRate:
    date: str
    char_code: str
    nominal: int
    value: float
    name: str


def _parse_cbr_date(s: str) -> str:
    d = datetime.strptime(s, "%d.%m.%Y").date()
    return d.isoformat()


def _parse_ru_decimal(s: str) -> float:
    return float(s.replace(",", "."))


def fetch_daily_rates(timeout_s: float = 10.0) -> list[CbrRate]:
    resp = requests.get(CBR_DAILY_URL, timeout=timeout_s)
    resp.raise_for_status()

    root = etree.fromstring(resp.content)
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