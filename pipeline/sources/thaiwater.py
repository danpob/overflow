"""ThaiWater (HII) adapter: fetch + validate water-level stations.

The API is undocumented, so every field is parsed defensively and a
schema check fails loudly (the pipeline then marks the layer stale).
"""
from __future__ import annotations

import time

import requests
from pydantic import BaseModel, ValidationError

BASE = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public"
UA = {"User-Agent": "Mozilla/5.0 (overflow flood tracker; non-commercial)"}


class SourceError(RuntimeError):
    pass


def fetch_json(endpoint: str, retries: int = 3, timeout: int = 60) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}/{endpoint}", headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise SourceError(f"{endpoint}: {last}")


class Station(BaseModel):
    id: int
    name_en: str
    name_th: str
    lat: float
    lon: float
    river_name: str | None = None
    river_gid: int | None = None
    basin_en: str | None = None
    basin_th: str | None = None
    province_en: str | None = None
    province_th: str | None = None
    agency: str | None = None
    level_msl: float | None = None
    level_prev_msl: float | None = None
    ground_level: float | None = None
    bank_level: float | None = None
    pct_capacity: float | None = None
    situation_level: int | None = None
    observed_at: str | None = None  # ICT, "YYYY-MM-DD HH:MM"
    kind: str | None = None


def _f(x) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def parse_waterlevel(payload: dict) -> list[Station]:
    try:
        rows = payload["waterlevel_data"]["data"]
    except (KeyError, TypeError) as e:
        raise SourceError(f"unexpected waterlevel payload shape: {e}")
    if not isinstance(rows, list) or len(rows) < 50:
        raise SourceError(f"suspiciously few stations: {len(rows) if isinstance(rows, list) else rows}")
    out: list[Station] = []
    for r in rows:
        try:
            st = r.get("station") or {}
            lat, lon = _f(st.get("tele_station_lat")), _f(st.get("tele_station_long"))
            if lat is None or lon is None or not (5 < lat < 21 and 97 < lon < 106):
                continue
            nm = st.get("tele_station_name") or {}
            geo = r.get("geocode") or {}
            prov = geo.get("province_name") or {}
            basin = (r.get("basin") or {}).get("basin_name") or {}
            ground, bank = _f(st.get("ground_level")), _f(st.get("min_bank"))
            level = _f(r.get("waterlevel_msl"))
            pct = _f(r.get("storage_percent"))
            if pct is None and None not in (level, ground, bank) and bank > ground:
                pct = (level - ground) / (bank - ground) * 100
            out.append(Station(
                id=st["id"], name_en=nm.get("en") or nm.get("th") or str(st["id"]),
                name_th=nm.get("th") or nm.get("en") or str(st["id"]),
                lat=lat, lon=lon, river_name=r.get("river_name"), river_gid=r.get("river_gid"),
                basin_en=basin.get("en"), basin_th=basin.get("th"),
                province_en=prov.get("en"), province_th=prov.get("th"),
                agency=((r.get("agency") or {}).get("agency_shortname") or {}).get("en"),
                level_msl=level, level_prev_msl=_f(r.get("waterlevel_msl_previous")),
                ground_level=ground, bank_level=bank, pct_capacity=pct,
                situation_level=r.get("situation_level"),
                observed_at=r.get("waterlevel_datetime"), kind=r.get("station_type"),
            ))
        except (ValidationError, KeyError, TypeError):
            continue
    if len(out) < 50:
        raise SourceError(f"only {len(out)} valid stations after validation")
    return out


def fetch_stations(attempts: int = 4) -> list[Station]:
    # ThaiWater occasionally answers 200 with a backend error body; retry those too.
    for i in range(attempts):
        try:
            return parse_waterlevel(fetch_json("waterlevel_load"))
        except SourceError:
            if i == attempts - 1:
                raise
            time.sleep(10 * (i + 1))
