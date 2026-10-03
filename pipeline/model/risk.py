"""Rule-based flood risk per sub-basin for D0..D+3 (PRD §8)."""
from __future__ import annotations

import math
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config" / "risk_weights.yaml").read_text())
DAYS = 4
THAI = re.compile("[\u0e00-\u0e7f]")
TREND_VAL = {"rising_fast": 1.0, "rising": 0.6, "stable": 0.2, "falling": 0.0, "unknown": None}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def level_of(score: float) -> int:
    return sum(score >= b for b in CFG["bands"])


def basin_inputs(basins: gpd.GeoDataFrame, snapped: gpd.GeoDataFrame, rain: dict | None, disc: dict | None):
    """Collect per-basin raw signals. rain/disc: hybas_id -> openmeteo dict (or None if source failed)."""
    n = CFG["normalisation"]
    inputs = {}
    sn = snapped.dropna(subset=["hybas_id"])
    st_by_basin = {k: g for k, g in sn.groupby(sn.hybas_id.astype("int64"))}
    for hid in basins.hybas_id:
        hid = int(hid)
        d = {"drivers_src": []}
        g = st_by_basin.get(hid)
        if g is not None:
            g = g.dropna(subset=["pct_capacity"])
            g = g[(g.pct_capacity > -50) & (g.pct_capacity < 400)]
        if g is not None and len(g):
            top = g.sort_values("pct_capacity", ascending=False).iloc[0]
            d["level"] = clamp((top.pct_capacity - n["level_ratio_floor_pct"]) / (n["level_ratio_ceiling_pct"] - n["level_ratio_floor_pct"]))
            d["trend"] = TREND_VAL.get(top.trend)
            d["station"] = {"t": "station", "en": top["name_en"], "th": top["name_th"], "prov": top.province_en,
                            "pct": round(float(top.pct_capacity)), "trend": top.trend}
        r = (rain or {}).get(hid)
        if r:
            rr = r["rain"]  # index 0..6 = today-3..today+3
            d["rain_series"] = rr
            d["elev"] = r.get("elev")
        q = (disc or {}).get(hid)
        if q:
            d["q"] = q
        inputs[hid] = d
    return inputs


def local_scores(d: dict):
    """-> list[DAYS] of (score0to1, [(contribution, text)])."""
    w, n = CFG["weights"], CFG["normalisation"]
    out = []
    for k in range(DAYS):
        terms = {}  # name -> (value, text)
        if "level" in d:
            terms["level_ratio"] = (d["level"], d["station"])
            if d.get("trend") is not None:
                terms["trend"] = (d["trend"] * (0.7 ** k), None)
        if "rain_series" in d:
            rr = d["rain_series"]
            i = 3 + k  # rr[3] is today
            obs = sum(rr[i - 2:i + 1])
            fc = sum(rr[i + 1:i + 4])
            terms["rain_obs_72h"] = (clamp(obs / n["rain_72h_full_mm"]), {"t": "rain_obs", "mm": round(obs)} if k == 0 else None)
            terms["rain_fcst_72h"] = (clamp(fc / n["rain_72h_full_mm"]), {"t": "rain_fc", "mm": round(fc)} if fc >= 10 else None)
        if "q" in d:
            dq = d["q"]
            hist = [v for v in dq["q"][:30] if v is not None]
            fut = dq["q"][30 + k] if len(dq["q"]) > 30 + k else None
            if hist and fut is not None:
                med = max(float(np.median(hist)), 1e-3)
                ratio = fut / med
                terms["discharge_exceedance"] = (clamp((ratio - 1) / (n["discharge_ratio_full"] - 1)),
                                                 {"t": "disc", "x": round(ratio, 1)} if ratio >= 1.5 else None)
        if not terms:
            out.append((None, []))
            continue
        tw = sum(w[t] for t in terms)
        score = sum(w[t] * v for t, (v, _) in terms.items()) / tw
        contrib = sorted(((w[t] * v / tw, txt) for t, (v, txt) in terms.items() if txt), key=lambda c: -c[0])
        out.append((score, contrib))
    return out


def terrain_factor(elev):
    t = CFG["terrain"]
    if elev is None:
        return 1.0
    f = clamp((elev - t["low_elev_m"]) / (t["high_elev_m"] - t["low_elev_m"]))
    return t["factor_high"] + f * (t["factor_low"] - t["factor_high"])


def compute(basins: gpd.GeoDataFrame, inputs: dict, graph_basins: dict, names: dict, provs: dict) -> dict:
    p = CFG["propagation"]
    ids = [int(i) for i in basins.hybas_id]
    idset = set(ids)
    cent = basins.to_crs("EPSG:32647").geometry.centroid
    pos = {int(h): (c.x / 1000, c.y / 1000) for h, c in zip(basins.hybas_id, cent)}
    ups = {i: [] for i in ids}
    for i in ids:
        dn = graph_basins[i]["down"]
        if dn in idset:
            ups[dn].append(i)
    # topological order: headwaters first
    order, seen = [], set()
    def visit(i):
        if i in seen: return
        seen.add(i)
        for u in ups[i]: visit(u)
        order.append(i)
    for i in ids: visit(i)

    risk, driver, eta = {}, {}, {}
    for b in order:
        loc = local_scores(inputs[b])
        tf = terrain_factor(inputs[b].get("elev"))
        r = [0.0] * DAYS
        drv = [[] for _ in range(DAYS)]
        up_info = []
        for u in ups[b]:
            dist = math.dist(pos[u], pos[b])
            lag_d = dist / p["wave_speed_km_per_day"]
            up_info.append((u, lag_d))
        for k in range(DAYS):
            ls = loc[k][0] if loc[k][0] is not None else 0.0
            best_up, best_u = 0.0, None
            for u, lag_d in up_info:
                src = risk[u][min(DAYS - 1, max(0, k - int(round(lag_d))))]
                v = src / 100 * p["hop_decay"]
                if v > best_up: best_up, best_u = v, (u, lag_d)
            score = clamp(max(ls, best_up) * tf) * 100
            r[k] = round(score)
            drv[k] = loc[k][1][:3]
            if best_u and best_up > ls:
                u, lag_d = best_u
                src_level = level_of(risk[u][min(DAYS - 1, max(0, k - round(lag_d)))])
                txt = {"t": "up", "prov": provs[u][0] if provs.get(u) else None, "lvl": src_level, "h": int(lag_d * 24)}
                drv[k] = [(best_up, txt)] + drv[k][:2]
        risk[b] = r
        driver[b] = drv
        eta[b] = up_info
    result = {}
    for b in ids:
        r = risk[b]
        top_ups = sorted(ups[b], key=lambda u: -risk[u][0])[:3]
        result[b] = {
            "name": names.get(b, "Sub-basin"), "provinces": provs.get(b, []),
            "scores": r, "levels": [level_of(x) for x in r],
            "drivers": [t for _, t in driver[b][0]],
            "upstream": [{"id": u, "level": level_of(risk[u][0]),
                          "eta_h": int(math.dist(pos[u], pos[b]) / p["wave_speed_km_per_day"] * 24)}
                         for u in top_ups if risk[u][0] >= 20],
            "drivers_by_day": [[t for _, t in d] for d in driver[b]],
        }
    return result
