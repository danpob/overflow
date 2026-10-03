"""One-time preprocessing: find where major roads cross the main rivers.

1. Download bridges on motorway/trunk/primary/secondary roads from OpenStreetMap (Overpass), tile by tile.
2. Keep bridges that pass within BUFFER_M of a main-stem river (HydroRIVERS, upland >= 1000 km2).
3. Merge duplicate carriageways into one crossing and attach river segment + sub-basin ids.

Inputs : static_layers/out/{rivers,basins,provinces}.geojson
Output : static_layers/raw/osm_bridges.json (cache), static_layers/out/crossings.json
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import LineString, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
RAW, OUT = HERE / "raw", HERE / "out"
UA = {"User-Agent": "overflow-flood-tracker/0.1 (github.com/danpob/overflow; non-commercial)", "Accept": "application/json"}
ENDPOINT = "https://overpass-api.de/api/interpreter"
CLASSES = "motorway|trunk|primary|secondary"
TILE = 1.0
BUFFER_M = 450      # HydroRIVERS lines are ~15" resolution; allow for position error
MERGE_M = 250       # dual carriageways / adjacent spans become one crossing
MIN_LEN_M = 25
UTM = "EPSG:32647"


def clean(v):
    """NaN -> None (NaN is not valid JSON); empty strings -> None."""
    return v if isinstance(v, str) and v else None


def tiles(th_geom):
    x0, y0, x1, y1 = th_geom.bounds
    for i in range(math.floor(y0), math.ceil(y1)):
        for j in range(math.floor(x0), math.ceil(x1)):
            b = box(j, i, j + TILE, i + TILE)
            if b.intersects(th_geom):
                yield (i, j, i + TILE, j + TILE)


def fetch_tile(bb, retries=3, depth=0):
    """Fetch one bbox; if it keeps failing, split it in four (smaller queries are cheaper for Overpass)."""
    q = f'[out:json][timeout:180];way["highway"~"^({CLASSES})$"]["bridge"]["bridge"!="no"]({bb[0]},{bb[1]},{bb[2]},{bb[3]});out geom tags;'
    for a in range(retries):
        try:
            r = requests.post(ENDPOINT, data={"data": q}, headers=UA, timeout=200)
            if r.status_code == 200:
                return r.json()["elements"]
            time.sleep(8 * (a + 1))
        except (requests.RequestException, ValueError):
            time.sleep(8 * (a + 1))
    if depth >= 2:
        raise RuntimeError(f"tile {bb} failed")
    s_, w, n, e = bb
    my, mx = (s_ + n) / 2, (w + e) / 2
    out = []
    for sub in ((s_, w, my, mx), (s_, mx, my, e), (my, w, n, mx), (my, mx, n, e)):
        out += fetch_tile(sub, retries, depth + 1)
        time.sleep(2)
    return out


def download(th_geom):
    TILES = RAW / "osm_tiles"
    TILES.mkdir(parents=True, exist_ok=True)
    ts = list(tiles(th_geom))
    for n, bb in enumerate(ts, 1):
        f = TILES / f"{bb[0]:.0f}_{bb[1]:.0f}.json"
        if f.exists():
            continue                      # resume: tile already downloaded
        els = fetch_tile(bb)
        f.write_text(json.dumps([{"id": e["id"], "tags": e["tags"], "geom": [[p["lon"], p["lat"]] for p in e["geometry"]]}
                                 for e in els if len(e.get("geometry", [])) >= 2]))
        print(f"tile {n}/{len(ts)} saved ({len(els)} bridges)", flush=True)
        time.sleep(2)
    seen, out = set(), []
    for f in sorted(TILES.glob("*.json")):
        for b in json.loads(f.read_text()):
            if b["id"] not in seen:
                seen.add(b["id"])
                out.append(b)
    return out


def main():
    prov = gpd.read_file(OUT / "provinces.geojson")
    th = unary_union(prov.geometry).buffer(0.05)
    bridges = download(th)
    print(len(bridges), "bridges downloaded")

    g = gpd.GeoDataFrame(
        [{"osm": b["id"], "ref": b["tags"].get("ref"), "hwy": b["tags"].get("highway"),
          "name_en": b["tags"].get("name:en"), "name_th": b["tags"].get("name:th") or b["tags"].get("name"),
          "name": b["tags"].get("name")} for b in bridges],
        geometry=[LineString(b["geom"]) for b in bridges], crs="EPSG:4326").to_crs(UTM)
    g["len_m"] = g.length
    g = g[g.len_m >= MIN_LEN_M]

    rivers = gpd.read_file(OUT / "rivers.geojson").to_crs(UTM)[["hyriv_id", "upland_skm", "geometry"]]
    near = gpd.sjoin_nearest(g, rivers, how="inner", max_distance=BUFFER_M, distance_col="riv_m")
    near = near.sort_values("riv_m").drop_duplicates("osm").drop(columns="index_right")
    print(len(near), "bridges near a main-stem river")

    # merge duplicates: greedy, biggest river first, then longest bridge
    near = near.sort_values(["upland_skm", "len_m"], ascending=False).reset_index(drop=True)
    near["mid"] = near.geometry.interpolate(0.5, normalized=True)
    keep, taken = [], []
    for i, row in near.iterrows():
        if any(row.mid.distance(t) < MERGE_M for t in taken):
            continue
        keep.append(i)
        taken.append(row.mid)
    c = near.loc[keep].copy()
    c["geometry"] = c["mid"]
    c = gpd.GeoDataFrame(c.drop(columns="mid"), geometry="geometry", crs=UTM)

    basins = gpd.read_file(OUT / "basins.geojson").to_crs(UTM)[["hybas_id", "geometry"]]
    c = gpd.sjoin(c, basins, how="left", predicate="within").drop(columns="index_right").drop_duplicates("osm")
    c = c.to_crs("EPSG:4326")
    items = []
    for n, r in enumerate(c.itertuples(), 1):
        if r.hybas_id != r.hybas_id:   # NaN: outside our basins
            continue
        items.append({"id": n, "lat": round(r.geometry.y, 5), "lon": round(r.geometry.x, 5), "ref": clean(r.ref),
                      "name_en": clean(r.name_en), "name_th": clean(r.name_th), "cls": r.hwy, "len_m": int(r.len_m),
                      "seg": int(r.hyriv_id), "basin": int(r.hybas_id), "osm": int(r.osm)})
    (OUT / "crossings.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")))
    print(len(items), "crossings written;", round((OUT / "crossings.json").stat().st_size / 1e3), "KB")
    import collections
    print(collections.Counter(i["cls"] for i in items))


if __name__ == "__main__":
    main()
