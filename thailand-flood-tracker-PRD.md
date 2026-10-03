# Thailand Flood Tracker — Product Requirements Document

| | |
|---|---|
| **Status** | Draft v0.1 |
| **Owner** | Dan |
| **Last updated** | 3 Oct 2026 |
| **Hosting** | GitHub (Actions + Pages), public repo |

---

## 1. Summary

A public, map-based web app that shows **where flood water in Thailand is coming from, where it is heading, and which areas have the highest chance of flooding in the next few days**. It works at river-basin level, not street level. All data comes from public sources, is processed on a schedule by GitHub Actions, and is published as static files — no server and no database.

## 2. Problem and opportunity

Official Thai water data is rich (stations, dams, rainfall, satellite flood extent) but fragmented across agencies and presented as station lists and tables. A non-specialist cannot easily answer: *"Is the water upstream of me rising, and when will it get here?"* The app turns that data into a directional picture — flow arrows along rivers and a risk score per area — with a short forecast horizon.

## 3. Goals and non-goals

**Goals**

1. Show the current direction and intensity of water movement along Thailand's main river systems.
2. Rank sub-basins by flood likelihood for today and the next 1–3 days, with an explanation of why.
3. Let users scrub through time (past 7 days → +3 days forecast) to see the water "move".
4. Run at near-zero cost on GitHub, fully automated, refreshed every 1–3 hours.

**Non-goals**

- Street-level or building-level flood mapping.
- Official warnings or evacuation guidance (the app links to DDPM / TMD instead).
- User accounts, notifications or crowdsourced reports (possible later, see §12).
- Flash floods in small urban catchments (Bangkok drainage) — out of scope for v1.

## 4. Target users

| User | Need |
|---|---|
| Residents in flood-prone provinces | "Is it coming my way, and when?" |
| Businesses / logistics / factories in industrial estates | Early view of downstream risk to sites and routes |
| Journalists, NGOs, analysts | A clear national overview with traceable data |
| Dan (operator) | Low-maintenance pipeline that runs unattended |

## 5. Key concepts

- **Sub-basin** — the unit of analysis. Derived from HydroBASINS (level 6–7) clipped to Thailand, grouped under the national main river basins.
- **River segment** — a reach of the river network (HydroRIVERS) with a known downstream direction.
- **Flow vector** — a river segment's current state: direction (from the network), magnitude (discharge or level), trend (rising / stable / falling).
- **Risk score** — 0–100 per sub-basin per day, built from upstream signals and propagated downstream with a travel-time lag.
- **Risk level** — banded score for display: Low / Watch / Elevated / High / Severe.

## 6. Features

Priority: **P0** = MVP, **P1** = v1.0, **P2** = later.

### F1. National flood map (P0)
- Full-screen MapLibre map of Thailand with an open basemap (no API key).
- Sub-basin choropleth coloured by risk level, with a legend.
- Layer toggle panel (risk zones, flow arrows, stations, rainfall, flood extent).
- Responsive: usable on mobile.

### F2. Station layer (P0)
- Water-level stations as points coloured by % of bank capacity.
- Popup: station name (Thai/English), level, bank level, % capacity, 24 h trend, last update time, source.

### F3. Directional flow arrows (P0)
- Animated chevrons/dashes moving downstream along main rivers.
- Line width = discharge or level magnitude; colour = trend (blue falling, grey stable, amber rising, red rising fast).
- Rivers with no nearby data shown as thin neutral lines (no implied certainty).

### F4. Area risk score (P0 rule-based, P2 ML)
- Daily risk score per sub-basin for D0, D+1, D+2, D+3.
- Inputs (see §8): upstream level vs bank, trend, rainfall accumulation and forecast, discharge forecast, reservoir fullness, terrain lowness.
- Downstream propagation along the river graph with per-segment lag.

### F5. "Why is this area at risk?" panel (P0)
- Click a sub-basin → side panel with score, level, and top 3 contributing drivers (e.g. "Nan River at N.64 at 97% bank, rising").
- List of upstream sub-basins feeding it, and estimated arrival time of the upstream peak.

### F6. Time slider (P1)
- Scrub from −7 days to +3 days; risk zones and arrows update per step.
- Play button to animate.

### F7. Rainfall layer (P1)
- Past 72 h accumulated rainfall and next 72 h forecast as a gridded overlay.

### F8. Observed flood extent overlay (P1)
- Latest satellite-derived flood extent (GISTDA) as a semi-transparent layer, with the observation date clearly shown.

### F9. Reservoir status (P1)
- Major dams as markers sized by capacity, coloured by % storage, with today's release volume.

### F10. Language toggle (P1)
- Thai and English UI. Place names from source data in both where available.

### F11. Data freshness and disclaimer (P0)
- Header badge: "Updated HH:MM (ICT)"; warning state if data is older than 6 h.
- Persistent disclaimer and links to official sources (DDPM, TMD, ThaiWater).

### F12. Shareable views (P2)
- URL encodes map position, active layers and time step.

### F13. Model accuracy page (P2)
- Back-test of the risk score against observed flood extents; published hit rate / false alarm rate.

## 7. Data sources

| Source | Data used | Frequency | Notes |
|---|---|---|---|
| ThaiWater (HII) `api-v3.thaiwater.net` | Water level, bank level, rainfall stations, dam storage/release | Hourly–daily | Undocumented JSON API; wrap in an adapter. Confirm terms of use. |
| Open-Meteo Forecast API | Rainfall forecast (gridded points) | Hourly | Free for non-commercial use; paid plan if commercial. |
| Open-Meteo Flood API (GloFAS) | River discharge forecast and return-period context | Daily | ~5 km grid, daily resolution. |
| GISTDA flood maps | Observed flood extent (Sentinel / satellite) | Event-driven | Check download format/access; may need manual registration. |
| HydroSHEDS (HydroRIVERS, HydroBASINS) | River network with flow direction, catchments | Static | One-time preprocessing. |
| DEM / HAND layer (e.g. MERIT Hydro, Copernicus DEM) | Terrain lowness relative to nearest river | Static | One-time preprocessing. |
| Admin boundaries (e.g. geoBoundaries) | Province / district labels for search and panels | Static | One-time. |

## 8. Risk model (v1, rule-based)

For each sub-basin *b* and day *d*:

```
local(b, d) = w1·LevelRatio + w2·Trend + w3·Rain72h_obs + w4·Rain72h_fcst
            + w5·DischargeExceedance + w6·ReservoirFullness_upstream
upstream(b, d) = max over upstream neighbours u of [ risk(u, d − lag(u→b)) · decay ]
risk(b, d)  = clamp( max(local, upstream) · TerrainFactor(b), 0, 100 )
```

- All inputs normalised to 0–1; weights stored in `config/risk_weights.yaml` so they can be tuned without code changes.
- `lag(u→b)` from segment length and an assumed wave speed, overridden by known lags on key reaches (e.g. Nakhon Sawan → Chai Nat → Bangkok).
- Output includes the top contributing drivers for F5.
- v2 (P2): gradient-boosted model trained on archived inputs vs GISTDA extents.

## 9. Architecture

```
Public APIs ──► GitHub Actions (cron, Python)
                 ├─ bronze/  raw timestamped snapshots
                 ├─ silver/  cleaned, joined to sub-basins & segments (Parquet, DuckDB)
                 └─ gold/    small web-ready files
                        ├─ basins_risk.geojson
                        ├─ flow_vectors.geojson
                        ├─ stations_latest.json
                        ├─ reservoirs_latest.json
                        └─ meta.json (timestamps, versions)
                                │
                                ▼
                     GitHub Pages (static site + gold files)
                                │
                                ▼
                     Browser: MapLibre GL JS (+ deck.gl for animated flows)
```

**Storage decision: no database.** Gold files are the serving layer. History is a rolling Parquet archive (bronze/silver) kept outside the main branch — GitHub Release assets or Cloudflare R2 — to avoid repo bloat. Site is published to `gh-pages` with a single force-pushed commit.

**Repository layout**

```
/pipeline        Python package: sources/, transform/, model/, publish/
/config          risk_weights.yaml, stations_map.yaml, lags.yaml
/static_layers   preprocessing scripts + output (basins, rivers, HAND)
/web             index.html, js/, css/, i18n/
/tests           unit tests + sample API fixtures
/.github/workflows  pipeline.yml (cron), deploy.yml, ci.yml
```

## 10. Non-functional requirements

| Area | Requirement |
|---|---|
| Freshness | Pipeline runs every 1–3 h; site flags data older than 6 h. |
| Performance | First map render < 3 s on 4G; gold payload < 3 MB total. |
| Resilience | If one source fails, publish the rest and mark that layer stale; never publish an empty map. |
| Cost | $0 baseline (GitHub free tier); optional R2 within free tier. |
| Transparency | Every score traceable to inputs; sources and update times shown. |
| Accessibility | Colour palettes colour-blind safe; trend also encoded by arrow speed/pattern. |
| Legal | Respect each source's licence; attribution footer; clear non-official disclaimer. |

## 11. Delivery plan

### Phase 0 — Foundations (≈1 week)
| # | Task | Output |
|---|---|---|
| 0.1 | Create repo, enable Actions and Pages, branch protection | Live empty site |
| 0.2 | Confirm access and terms for ThaiWater, Open-Meteo, GISTDA | Source notes in `/docs` |
| 0.3 | Capture sample API responses as test fixtures | `/tests/fixtures` |
| 0.4 | Preprocess static layers: Thai sub-basins, river network graph, HAND/terrain factor | `static_layers/*.geojson` + graph |
| 0.5 | Map stations to river segments and sub-basins | `config/stations_map.yaml` |

### Phase 1 — MVP: "what's happening now" (≈2 weeks) — F1, F2, F3, F11
| # | Task |
|---|---|
| 1.1 | ThaiWater adapter (levels, bank levels, dams) with retries and schema checks |
| 1.2 | Bronze → silver transform; per-segment current state and 24 h trend |
| 1.3 | Gold writers: `stations_latest.json`, `flow_vectors.geojson`, `meta.json` |
| 1.4 | Scheduled workflow + deploy to `gh-pages` |
| 1.5 | Web: base map, layer panel, station popups, animated flow arrows |
| 1.6 | Freshness badge, disclaimer, attribution |

### Phase 2 — Risk and explanation (≈2 weeks) — F4, F5
| # | Task |
|---|---|
| 2.1 | Open-Meteo rainfall (observed + forecast) aggregated per upstream catchment |
| 2.2 | GloFAS discharge forecast per key segment |
| 2.3 | Rule-based risk score with config weights and downstream propagation |
| 2.4 | `basins_risk.geojson` with D0–D+3 and top drivers |
| 2.5 | Web: risk choropleth, legend, "why" panel with upstream list and arrival estimate |
| 2.6 | Sanity check against a past event (e.g. a recent rainy season) and tune weights |

### Phase 3 — Time and context (≈2 weeks) — F6–F10
| # | Task |
|---|---|
| 3.1 | History archive (Parquet on Release assets or R2) and time-indexed gold files |
| 3.2 | Time slider and playback |
| 3.3 | Rainfall overlay, GISTDA flood extent overlay, reservoir markers |
| 3.4 | Thai/English i18n |

### Phase 4 — Hardening and learning (ongoing) — F12, F13, ML
| # | Task |
|---|---|
| 4.1 | Shareable URLs |
| 4.2 | Back-testing and accuracy page |
| 4.3 | ML risk model trained on archived data vs observed extents |
| 4.4 | Monitoring: workflow failure alerts (GitHub notifications / issue auto-open) |

## 12. Future ideas (not committed)
LINE / email alerts for chosen provinces; Mekong (MRC) stations for the north-east; flash-flood indicators for small catchments; embeddable widget for news sites.

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| ThaiWater API changes without notice | Adapter layer, schema validation, fixture tests, stale-layer fallback |
| Users treat the app as an official warning | Prominent disclaimer, links to DDPM/TMD, conservative wording |
| Rule-based score is wrong in some basins | Explainable drivers, configurable weights, back-testing in Phase 4 |
| GitHub cron delays or pauses on inactive repos | Tolerate delays; keep-alive commit or external trigger if needed |
| Repo bloat from data | Single-commit `gh-pages`; history outside git |
| Licence limits on commercial use (e.g. Open-Meteo) | Keep project non-commercial or budget a paid plan |

## 14. Success metrics
- Pipeline success rate ≥ 95% of scheduled runs.
- Median data age shown to users < 3 h.
- Back-test: ≥ 70% of observed flooded sub-basins flagged Elevated or higher within the prior 48 h, with a tracked false-alarm rate.
- Qualitative: a first-time user can say which direction the water is moving within 10 seconds.

## 15. Open questions
1. Project name and domain (default `<user>.github.io/<repo>`)?
2. Refresh frequency: hourly or every 3 hours?
3. Sub-basin granularity: HydroBASINS level 6 (coarser, faster) or 7 (finer)?
4. Thai-first or English-first UI?
5. Any intent to use this commercially (affects data licences)?
6. Keep history in GitHub Releases or set up Cloudflare R2?
