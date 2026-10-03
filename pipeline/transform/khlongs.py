"""Khlong / small-river stretches, drawn only while their station is high.

static_layers/out/khlongs.json maps station id -> the named OpenStreetMap waterway near it (see build_khlongs.py).
A stretch is published only when its station reads at least SHOW_PCT of bank, coloured in the browser with the
same scale as the station dots. No flow direction is implied: khlongs are largely gate- and pump-controlled.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

OUT = Path(__file__).resolve().parents[2] / "static_layers" / "out"
SHOW_PCT = 90


def load_static() -> dict:
    p = OUT / "khlongs.json"
    return json.loads(p.read_text()) if p.exists() else {}


def build(snapped: gpd.GeoDataFrame, static: dict | None = None) -> dict:
    static = load_static() if static is None else static
    feats = []
    ok = snapped.dropna(subset=["pct_capacity"])
    ok = ok[(ok.pct_capacity >= SHOW_PCT) & (ok.pct_capacity < 400)]
    for r in ok.itertuples():
        k = static.get(str(int(r.id)))
        if not k:
            continue
        feats.append({"type": "Feature", "properties": {"sid": int(r.id), "pct": round(float(r.pct_capacity), 1)},
                      "geometry": {"type": "MultiLineString", "coordinates": k["lines"]}})
    return {"type": "FeatureCollection", "features": feats}
