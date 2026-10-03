"""One-time preprocessing: find the khlong / small-river line that belongs to each station that is NOT on a main-stem river.

ThaiWater gives every station a waterway name (e.g. คลองท่าดี). We look for OpenStreetMap waterways with that name
within SEARCH_M of the station and keep the part of each line within KEEP_M of the station.

Stations with no named match fall back to the nearest HydroRIVERS small stream within HYDRO_SNAP_M (coarser, "approximate").

Input : static_layers/raw/thailand-latest.osm.pbf  (https://download.geofabrik.de/asia/thailand-latest.osm.pbf)
Output: static_layers/out/khlongs.json  {station_id: {"name": str, "lines": [[[lon, lat], ...], ...]}}
Run   : PYTHONPATH=. python static_layers/build_khlongs.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

from pipeline.sources.thaiwater import parse_waterlevel
from pipeline.transform import network

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
PBF = HERE / "raw" / "thailand-latest.osm.pbf"
FIXTURE = HERE.parent / "tests" / "fixtures" / "waterlevel_load.json"
SEARCH_M, KEEP_M = 6000, 5000
HYDRO_SNAP_M = 500
UTM = "EPSG:32647"


def norm(s: str) -> str:
    """Compare names ignoring spaces, zero-width characters and bracketed notes."""
    return re.sub(r"[\s​]+", "", re.sub(r"\(.*?\)", "", s or ""))


PREFIXES = ("ลำคลอง", "ลำน้ำ", "ลำห้วย", "แม่น้ำ", "ลำธาร", "คลอง", "ห้วย", "ลำ", "น้ำ")


def core(name: str) -> str:
    """Name without its generic type word, so 'แม่น้ำแม่วงก์' and 'คลองแม่วงก์' compare equal."""
    n = norm(name)
    for pre in PREFIXES:
        if n.startswith(pre) and len(n) > len(pre) + 1:
            return n[len(pre):]
    return n


def fallback_hydro(todo, result, unmatched):
    """Second pass: follow the nearest HydroRIVERS stream (main path up and down) for stations OSM could not name-match."""
    miss = todo[~todo.id.isin(list(result))]
    prov = gpd.read_file(OUT / "provinces.geojson")
    shp = next((HERE / "raw" / "rivers").rglob("*.shp"))
    r = gpd.read_file(shp, mask=unary_union(prov.geometry).buffer(0.2))[["HYRIV_ID", "NEXT_DOWN", "UPLAND_SKM", "geometry"]].to_crs(UTM)
    geom = dict(zip(r.HYRIV_ID, r.geometry))
    down = dict(zip(r.HYRIV_ID, r.NEXT_DOWN))
    area = dict(zip(r.HYRIV_ID, r.UPLAND_SKM))
    parents = {}
    for rid, nd in down.items():
        if nd:
            parents.setdefault(nd, []).append(rid)
    pts = gpd.GeoDataFrame(miss[["id", "river_name"]], geometry=miss.geometry, crs="EPSG:4326").to_crs(UTM)
    j = gpd.sjoin_nearest(pts, r[["HYRIV_ID", "geometry"]], how="inner", max_distance=HYDRO_SNAP_M, distance_col="d")
    j = j.sort_values("d").drop_duplicates("id")
    n = 0
    for row in j.itertuples():
        zone = row.geometry.buffer(KEEP_M)
        chain, cur = [], row.HYRIV_ID
        for _ in range(300):                       # downstream
            chain.append(cur)
            cur = down.get(cur) or 0
            if not cur or cur not in geom or not geom[cur].intersects(zone):
                break
        cur = row.HYRIV_ID
        for _ in range(300):                       # upstream: stay on the main (largest) branch
            ps = [p for p in parents.get(cur, []) if p in geom]
            if not ps:
                break
            cur = max(ps, key=lambda p: area[p])
            if not geom[cur].intersects(zone):
                break
            chain.append(cur)
        lines = []
        for rid in chain:
            part = geom[rid].intersection(zone)
            for seg in (part.geoms if isinstance(part, MultiLineString) else [part]):
                if isinstance(seg, LineString) and seg.length > 50:
                    lines.append(seg)
        if lines:
            ll = gpd.GeoSeries(lines, crs=UTM).simplify(25).to_crs("EPSG:4326")
            result[int(row.id)] = {"name": row.river_name.strip(), "approx": True,
                                   "lines": [[[round(x, 4), round(y, 4)] for x, y in g.coords] for g in ll if not g.is_empty]}
            n += 1
    print(f"fallback: {n} more stations matched to the nearest HydroRIVERS stream (approximate)")


def main():
    stations = parse_waterlevel(json.loads(FIXTURE.read_text()))
    layers = network.StaticLayers()
    sn = network.snap_stations(network.stations_frame(stations), layers)
    todo = sn[sn.segment.isna() & sn.river_name.notna()]
    todo = todo[todo.river_name.str.strip() != ""]
    print(len(todo), "stations on smaller waterways with a name")

    gw = pyogrio.read_dataframe(PBF, layer="lines", columns=["name", "waterway"],
                                where="waterway IN ('river','canal','stream','drain') AND name IS NOT NULL")
    gw = gw.set_crs("EPSG:4326", allow_override=True).to_crs(UTM)
    gw["key"] = gw["name"].map(norm)
    gw["core"] = gw["name"].map(core)
    print(len(gw), "named waterway lines in the OpenStreetMap extract")
    by_name = {k: g for k, g in gw.groupby("key")}
    by_core = {k: g for k, g in gw.groupby("core")}

    result, unmatched = {}, []
    for r in todo.itertuples():
        p = gpd.GeoSeries([Point(r.lon, r.lat)], crs="EPSG:4326").to_crs(UTM).iloc[0]
        lines = []
        # exact name first; if nothing is near the station, fall back to the same core name with another type word
        for pool, key in ((by_name, norm(r.river_name)), (by_core, core(r.river_name))):
            cand = pool.get(key)
            near = cand[cand.intersects(p.buffer(SEARCH_M))] if cand is not None else None
            if near is None or near.empty:
                continue
            zone = p.buffer(KEEP_M)
            for g in near.geometry:
                part = g.intersection(zone)
                if part.is_empty:
                    continue
                for seg in (part.geoms if isinstance(part, MultiLineString) else [part]):
                    if isinstance(seg, LineString) and seg.length > 50:
                        lines.append(seg)
            if lines:
                break
        if lines:
            ll = gpd.GeoSeries(lines, crs=UTM).simplify(15).to_crs("EPSG:4326")
            result[int(r.id)] = {"name": r.river_name.strip(),
                                 "lines": [[[round(x, 4), round(y, 4)] for x, y in g.coords] for g in ll if not g.is_empty]}
        else:
            unmatched.append(r.river_name.strip())
    fallback_hydro(todo, result, unmatched)
    (OUT / "khlongs.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(result)}/{len(todo)} stations have a khlong stretch;", round((OUT / "khlongs.json").stat().st_size / 1e3), "KB")
    print("unmatched examples:", unmatched[:12])


if __name__ == "__main__":
    main()
