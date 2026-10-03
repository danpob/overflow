"""Open-Meteo adapters: rainfall (forecast API) and river discharge (GloFAS flood API)."""
from __future__ import annotations

import time

import requests

from pipeline.sources.thaiwater import SourceError

FORECAST = "https://api.open-meteo.com/v1/forecast"
FLOOD = "https://flood-api.open-meteo.com/v1/flood"
BATCH = 50


def _get(url: str, params: dict, retries: int = 3):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(15 * (i + 1))
                continue
            r.raise_for_status()
            j = r.json()
            return j if isinstance(j, list) else [j]
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(2 ** i)
    raise SourceError(f"open-meteo: {last}")


def _batched(points, fn):
    out = []
    for i in range(0, len(points), BATCH):
        out.extend(fn(points[i:i + BATCH]))
        time.sleep(0.3)
    return out


def fetch_rain(points: list[tuple[float, float]]) -> list[dict]:
    """Per point: {'dates': [7 days: today-3..today+3], 'rain': [mm...], 'elev': m}."""
    def one(chunk):
        res = _get(FORECAST, {
            "latitude": ",".join(f"{p[0]:.3f}" for p in chunk), "longitude": ",".join(f"{p[1]:.3f}" for p in chunk),
            "daily": "precipitation_sum", "past_days": 3, "forecast_days": 4, "timezone": "Asia/Bangkok"})
        if len(res) != len(chunk):
            raise SourceError("open-meteo rain: result count mismatch")
        return [{"dates": r["daily"]["time"], "rain": [v or 0.0 for v in r["daily"]["precipitation_sum"]],
                 "elev": r.get("elevation")} for r in res]
    return _batched(points, one)


def fetch_discharge(points: list[tuple[float, float]]) -> list[dict]:
    """Per point: {'dates', 'q' (m3/s, 30 past days + 3 forecast days + today)}."""
    def one(chunk):
        res = _get(FLOOD, {
            "latitude": ",".join(f"{p[0]:.3f}" for p in chunk), "longitude": ",".join(f"{p[1]:.3f}" for p in chunk),
            "daily": "river_discharge", "past_days": 30, "forecast_days": 4})
        if len(res) != len(chunk):
            raise SourceError("open-meteo flood: result count mismatch")
        return [{"dates": r["daily"]["time"], "q": r["daily"]["river_discharge"]} for r in res]
    return _batched(points, one)
