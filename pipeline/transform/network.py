"""Join stations to the river network / sub-basins and derive per-segment flow state."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd

from pipeline.publish.gold import trend_of
from pipeline.sources.thaiwater import Station

OUT = Path(__file__).resolve().parents[2] / "static_layers" / "out"
UTM = "EPSG:32647"
SNAP_M = 3000          # station must lie within this of a main-stem segment
INFLUENCE_KM = 40      # data is propagated along the river at most this far
TREND_CODE = {"unknown": 0, "falling": 1, "stable": 2, "rising": 3, "rising_fast": 4}


class StaticLayers:
    def __init__(self, out: Path = OUT):
        self.rivers = gpd.read_file(out / "rivers.geojson")
        self.basins = gpd.read_file(out / "basins.geojson")
        g = json.loads((out / "graph.json").read_text())
        self.graph_rivers = {int(k): v for k, v in g["rivers"].items()}
        self.graph_basins = {int(k): v for k, v in g["basins"].items()}


def stations_frame(stations: list[Station]) -> gpd.GeoDataFrame:
    df = pd.DataFrame([s.model_dump() for s in stations])
    df["trend"] = [trend_of(s) for s in stations]
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")


def snap_stations(gs: gpd.GeoDataFrame, layers: StaticLayers) -> gpd.GeoDataFrame:
    riv = layers.rivers[["hyriv_id", "geometry"]].to_crs(UTM)
    snapped = gpd.sjoin_nearest(gs.to_crs(UTM), riv, how="left", max_distance=SNAP_M, distance_col="snap_m")
    snapped = snapped.sort_values("snap_m").drop_duplicates("id")
    snapped = snapped.rename(columns={"hyriv_id": "segment"}).drop(columns="index_right", errors="ignore")
    # basin membership
    bas = layers.basins[["hybas_id", "geometry"]].to_crs(UTM)
    snapped = gpd.sjoin(snapped, bas, how="left", predicate="within").drop(columns="index_right", errors="ignore")
    snapped = snapped.drop_duplicates("id")
    return snapped.to_crs("EPSG:4326")


def segment_state(snapped: gpd.GeoDataFrame, layers: StaticLayers) -> dict[int, list]:
    """segment_id -> [pct, trend_code, dist_km]. Only segments within INFLUENCE_KM of a station."""
    G = nx.Graph()
    for sid, v in layers.graph_rivers.items():
        G.add_node(sid)
        if v["down"] in layers.graph_rivers:
            G.add_edge(sid, v["down"], weight=v["km"])
    ok = snapped.dropna(subset=["segment", "pct_capacity"])
    ok = ok[(ok.pct_capacity > -50) & (ok.pct_capacity < 400)]
    by_seg = ok.groupby(ok.segment.astype(int)).agg(pct=("pct_capacity", "median"),
                                                  trend=("trend", lambda t: t.value_counts().index[0]))
    sources = [s for s in by_seg.index if s in G]
    if not sources:
        return {}
    dist, paths = nx.multi_source_dijkstra(G, sources, cutoff=INFLUENCE_KM, weight="weight")
    state = {}
    for seg, d in dist.items():
        src = paths[seg][0]
        state[int(seg)] = [round(float(by_seg.loc[src, "pct"]), 1), TREND_CODE[by_seg.loc[src, "trend"]], round(d, 1)]
    return state


def basin_points(layers: StaticLayers):
    """-> (centroid lat/lon per basin, outlet-river midpoint lat/lon + mean discharge per basin)."""
    b = layers.basins.to_crs(UTM)
    cen = b.geometry.centroid.to_crs("EPSG:4326")
    cents = {int(h): (p.y, p.x) for h, p in zip(b.hybas_id, cen)}
    r = layers.rivers.copy()
    r["mid"] = r.geometry.interpolate(0.5, normalized=True)
    mids = gpd.GeoDataFrame(r.drop(columns="geometry"), geometry=r["mid"], crs="EPSG:4326")
    j = gpd.sjoin(mids, layers.basins[["hybas_id", "geometry"]], predicate="within")
    j = j.sort_values("upland_skm", ascending=False).drop_duplicates("hybas_id")
    outlets = {int(h): (g.y, g.x, float(q)) for h, g, q in zip(j.hybas_id, j.geometry, j.dis_av_cms)}
    return cents, outlets


def basin_names(layers: StaticLayers, snapped: gpd.GeoDataFrame) -> tuple[dict[int, str], dict[int, list[str]]]:
    """-> (display name, provinces covered by area share, largest first)."""
    prov = gpd.read_file(OUT / "provinces.geojson").to_crs(UTM)
    bas = layers.basins[["hybas_id", "geometry"]].to_crs(UTM)
    ov = gpd.overlay(bas, prov[["name", "geometry"]], how="intersection")
    ov["a"] = ov.area
    ov = ov.sort_values("a", ascending=False)
    provs = {int(h): list(g.name.head(4)) for h, g in ov.groupby("hybas_id")}
    sn = snapped.dropna(subset=["hybas_id", "river_name"])
    rivers = sn.groupby(sn.hybas_id.astype("int64")).river_name.agg(lambda s: s.value_counts().index[0])
    names = {}
    for h in layers.basins.hybas_id:
        h = int(h)
        names[h] = rivers[h] if h in rivers.index else "Sub-basin"
    return names, provs
