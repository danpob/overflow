"""Run the pipeline: fetch -> gold files in web/data (local) or an output dir."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from pipeline.model import risk
from pipeline.publish import gold
from pipeline.sources import openmeteo, thaiwater
from pipeline.transform import crossings, network

ROOT = Path(__file__).resolve().parent.parent


def build_risk(L, snapped, out, layers):
    import json
    cents, outlets = network.basin_points(L)
    ids = list(cents)
    rain = disc = None
    try:
        rr = openmeteo.fetch_rain([cents[i] for i in ids])
        rain = dict(zip(ids, rr))
        layers["rain"] = {"status": "ok", "points": len(ids)}
    except thaiwater.SourceError as e:
        print(f"rain FAILED: {e}", file=sys.stderr)
        layers["rain"] = {"status": "stale", "error": str(e)}
    try:
        oid = list(outlets)
        dd = openmeteo.fetch_discharge([outlets[i][:2] for i in oid])
        disc = {}
        for i, d in zip(oid, dd):
            vals = [v for v in d["q"][:30] if v is not None]
            # GloFAS cells that miss the river read far below HydroRIVERS' mean flow -> unreliable
            if vals and sum(vals) / len(vals) >= 0.2 * outlets[i][2]:
                disc[i] = d
        layers["discharge"] = {"status": "ok", "points": len(oid), "usable": len(disc)}
    except thaiwater.SourceError as e:
        print(f"discharge FAILED: {e}", file=sys.stderr)
        layers["discharge"] = {"status": "stale", "error": str(e)}
    inputs = risk.basin_inputs(L.basins, snapped, rain, disc)
    names, provs = network.basin_names(L, snapped)
    res = risk.compute(L.basins, inputs, L.graph_basins, names, provs)
    (out / "basins_risk.json").write_text(json.dumps({"basins": res}, ensure_ascii=False, separators=(",", ":")))
    layers["risk"] = {"status": "ok" if rain else "stale", "basins": len(res)}
    live = crossings.build(L, snapped, {b: r["levels"] for b, r in res.items()})
    (out / "crossings_live.json").write_text(json.dumps(live, ensure_ascii=False, separators=(",", ":")))
    layers["crossings"] = {"status": "ok", "shown": len(live), "measured": sum(1 for c in live if c["t1"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "web" / "data"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    layers: dict[str, dict] = {}
    try:
        st = thaiwater.fetch_stations()
        gold.write_stations(st, out)
        layers_static = network.StaticLayers()
        snapped = network.snap_stations(network.stations_frame(st), layers_static)
        state = network.segment_state(snapped, layers_static)
        gold.write_flow_state(state, out)
        shutil.copy(ROOT / "static_layers" / "out" / "rivers.geojson", out)
        shutil.copy(ROOT / "static_layers" / "out" / "basins.geojson", out)
        shutil.copy(ROOT / "static_layers" / "out" / "provinces.geojson", out)
        layers["flow"] = {"status": "ok", "segments_with_data": len(state)}
        build_risk(layers_static, snapped, out, layers)
        times = sorted(s.observed_at for s in st if s.observed_at)
        layers["stations"] = {"status": "ok", "count": len(st), "latest_obs": times[-1] if times else None}
    except thaiwater.SourceError as e:
        print(f"stations FAILED: {e}", file=sys.stderr)
        layers["stations"] = {"status": "stale", "error": str(e)}
    if all(v["status"] != "ok" for v in layers.values()):
        print("no layer succeeded; not publishing", file=sys.stderr)
        return 1
    gold.write_meta(out, layers)
    print(layers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
