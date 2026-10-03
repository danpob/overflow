"""One-time preprocessing: clip HydroSHEDS layers to Thailand and build the river graph.

Inputs  (static_layers/raw): rivers/, basins7/, provinces.geojson
Outputs (static_layers/out): basins.geojson, rivers.geojson, provinces.geojson, graph.json
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
RAW, OUT = HERE / "raw", HERE / "out"
OUT.mkdir(exist_ok=True)
MIN_UPLAND_KM2 = 1000   # rivers drawn/used: main stems only
BUFFER_DEG = 0.0        # basins: keep any basin intersecting Thailand


def main():
    prov = gpd.read_file(RAW / "provinces.geojson")[["shapeName", "geometry"]]
    prov["name"] = prov.shapeName.str.replace(" Province", "", regex=False)
    prov = prov.drop(columns="shapeName")
    th = unary_union(prov.geometry)
    prov.geometry = prov.geometry.simplify(0.005)
    prov.to_file(OUT / "provinces.geojson", driver="GeoJSON")

    # --- basins (HydroBASINS level 7) ---
    b = gpd.read_file(RAW / "basins7" / "hybas_as_lev07_v1c.shp", mask=th.buffer(0.01))
    b = b[b.intersects(th)].copy()
    # share of each basin inside Thailand (to flag border basins)
    b["th_share"] = (b.geometry.intersection(th).area / b.geometry.area).round(2)
    b = b[b.th_share >= 0.05]
    b = b[["HYBAS_ID", "NEXT_DOWN", "MAIN_BAS", "SUB_AREA", "UP_AREA", "th_share", "geometry"]]
    b.geometry = b.geometry.simplify(0.004)
    b.columns = [c if c == "geometry" else c.lower() for c in b.columns]
    b.to_file(OUT / "basins.geojson", driver="GeoJSON", COORDINATE_PRECISION=3)

    # --- rivers ---
    shp = next((RAW / "rivers").rglob("*.shp"))
    r = gpd.read_file(shp, mask=th.buffer(0.3))
    r = r[r.UPLAND_SKM >= MIN_UPLAND_KM2][
        ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "DIS_AV_CMS", "ORD_STRA", "UPLAND_SKM", "geometry"]].copy()
    r.columns = [c if c == "geometry" else c.lower() for c in r.columns]
    r.geometry = r.geometry.simplify(0.002)
    r.to_file(OUT / "rivers.geojson", driver="GeoJSON", COORDINATE_PRECISION=3)

    # --- graph: segment -> downstream, length ---
    graph = {
        "rivers": {int(i): {"down": int(d), "km": round(float(km), 2), "dis": round(float(q), 2)}
                   for i, d, km, q in zip(r.hyriv_id, r.next_down, r.length_km, r.dis_av_cms)},
        "basins": {int(i): {"down": int(d), "area": round(float(a), 1), "th": float(s)}
                   for i, d, a, s in zip(b.hybas_id, b.next_down, b.sub_area, b.th_share)},
    }
    (OUT / "graph.json").write_text(json.dumps(graph, separators=(",", ":")))
    print(len(b), "basins;", len(r), "river segments")
    for f in OUT.glob("*.geojson"):
        print(f.name, round(f.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
