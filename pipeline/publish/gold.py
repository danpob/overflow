"""Gold writers: small web-ready files served by the static site."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.sources.thaiwater import Station

ICT = timezone(timedelta(hours=7))


def trend_of(s: Station, eps: float = 0.02, fast: float = 0.15) -> str:
    if s.level_msl is None or s.level_prev_msl is None:
        return "unknown"
    d = s.level_msl - s.level_prev_msl
    if d >= fast:
        return "rising_fast"
    if d >= eps:
        return "rising"
    if d <= -eps:
        return "falling"
    return "stable"


def write_stations(stations: list[Station], out: Path) -> Path:
    rows = []
    for s in stations:
        rows.append({
            "id": s.id, "name_en": s.name_en, "name_th": s.name_th,
            "lat": round(s.lat, 5), "lon": round(s.lon, 5),
            "river": s.river_name, "basin_en": s.basin_en, "province_en": s.province_en, "province_th": s.province_th,
            "level_msl": s.level_msl, "bank_level": s.bank_level,
            "pct": None if s.pct_capacity is None else round(s.pct_capacity, 1),
            "trend": trend_of(s),
            "delta": None if None in (s.level_msl, s.level_prev_msl) else round(s.level_msl - s.level_prev_msl, 3),
            "observed_at": s.observed_at, "source": "ThaiWater / " + (s.agency or "HII"),
        })
    p = out / "stations_latest.json"
    p.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    return p


def write_meta(out: Path, layers: dict[str, dict]) -> Path:
    now = datetime.now(ICT)
    meta = {"generated_at": now.isoformat(timespec="minutes"), "version": 1, "layers": layers}
    p = out / "meta.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    return p


def write_flow_state(state: dict, out: Path) -> Path:
    """Compact segment state keyed by HydroRIVERS id; geometry lives in the static rivers layer."""
    p = out / "flow_state.json"
    p.write_text(json.dumps({str(k): v for k, v in state.items()}, separators=(",", ":")))
    return p
