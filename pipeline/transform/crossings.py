"""Live state for road/river crossings.

Tier 1 (measured): a water-level station within MAX_KM along the river reads at/over its bank.
Tier 2 (modelled): the sub-basin is forecast High or worse (decided in the browser from basins_risk.json,
                   so the day buttons can switch it); here we only keep crossings that can ever matter.
"""
from __future__ import annotations

import json
from pathlib import Path

import math

import geopandas as gpd
import networkx as nx

from pipeline.transform.network import StaticLayers

OUT = Path(__file__).resolve().parents[2] / "static_layers" / "out"
MAX_KM = 6          # straight-line distance station <-> crossing
RIVER_KM = 15       # ...and the two must also be connected along the river within this distance
OVER_PCT = 100
MIN_OVER_M = 0.2    # clearly over the bank, not just touching it
HIGH = 3          # risk level that makes a crossing worth showing (High)


def _km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def load_crossings() -> list[dict]:
    p = OUT / "crossings.json"
    return json.loads(p.read_text()) if p.exists() else []


def _direction(down: dict, station_seg: int, crossing_seg: int, hops: int = 60) -> str:
    """'upstream' if the station is upstream of the crossing, 'downstream' if below it, else 'nearby'."""
    def reaches(a, b):
        cur = a
        for _ in range(hops):
            if cur == b:
                return True
            nxt = down.get(cur)
            if not nxt or nxt == cur:
                return False
            cur = nxt
        return False
    if station_seg == crossing_seg:
        return "here"
    if reaches(station_seg, crossing_seg):
        return "upstream"
    if reaches(crossing_seg, station_seg):
        return "downstream"
    return "nearby"


def build(layers: StaticLayers, snapped: gpd.GeoDataFrame, basin_levels: dict[int, list[int]]) -> list[dict]:
    items = load_crossings()
    if not items:
        return []
    G = nx.Graph()
    down = {}
    for sid, v in layers.graph_rivers.items():
        G.add_node(sid)
        down[sid] = v["down"]
        if v["down"] in layers.graph_rivers:
            G.add_edge(sid, v["down"], weight=v["km"])
    ok = snapped.dropna(subset=["segment", "pct_capacity", "level_msl", "bank_level"])
    ok = ok[(ok.pct_capacity >= OVER_PCT) & (ok.pct_capacity < 400) & (ok.level_msl - ok.bank_level >= MIN_OVER_M)]
    stations = [r for r in ok.itertuples() if int(r.segment) in G]

    out = []
    for c in items:
        t1 = None
        reach = nx.single_source_dijkstra_path_length(G, c["seg"], cutoff=RIVER_KM, weight="weight") if c["seg"] in G else {}
        best = None
        for st in stations:
            if int(st.segment) not in reach:
                continue
            d = _km(c["lat"], c["lon"], st.lat, st.lon)
            if d <= MAX_KM and (best is None or d < best[0]):
                best = (d, st)
        if best:
            d, st = best
            t1 = {"en": st.name_en, "th": st.name_th, "pct": round(float(st.pct_capacity)),
                  "over_m": round(float(st.level_msl - st.bank_level), 2), "km": round(d, 1),
                  "dir": _direction(down, int(st.segment), c["seg"])}
            if t1["dir"] == "here" and d > 0.5:
                t1["dir"] = "nearby"      # same river reach, but not literally at the crossing
        lv = basin_levels.get(c["basin"], [])
        if t1 or (lv and max(lv) >= HIGH):
            out.append({"id": c["id"], "lat": c["lat"], "lon": c["lon"], "ref": c["ref"], "name_en": c["name_en"],
                        "name_th": c["name_th"], "basin": c["basin"], "t1": t1})
    return out
