# Thailand Flood Tracker — Progress & Plan

Source: `thailand-flood-tracker-PRD.md` (Draft v0.1). Last updated: 3 Oct 2026.
Legend: `[ ]` todo · `[~]` in progress · `[x]` done · 🔒 blocked on user input · ⚠️ risk / needs verification

## 0. Status snapshot
- Current phase: **Local prototype built (Phase 0–2 core). Not yet pushed to GitHub.**
- Repo name: `risewise` (local git initialised on `main`, nothing committed/pushed yet)
- Open: visual check in browser, GitHub push, Phase 3 items, dam endpoint, HAND terrain layer

## 1. Working assumptions (used unless the user says otherwise)
| Topic | Default | PRD ref |
|---|---|---|
| Refresh cadence | Every 3 h (cron), upgradable to hourly | §15.2 |
| Sub-basin granularity | HydroBASINS level 7 if payload < 3 MB after simplification, else level 6 | §15.3 |
| UI language | English-first with Thai toggle (i18n keys from day 1) | §15.4 |
| History storage | GitHub Release assets (no extra account) | §15.6 |
| Usage | Non-commercial | §15.5 |
| Stack | Python 3.12 (pandas/geopandas/DuckDB/pyarrow/networkx), vanilla JS + MapLibre GL + deck.gl, no build step beyond a light bundler if needed | §9 |
| Repo layout | As in PRD §9 | §9 |

## 2. Inputs needed from the user 🔒
See the end of the chat reply; tracked here so they are not lost.
- [ ] GitHub account/org + repo name, public repo, permission for me to push (or `gh` authenticated locally)
- [ ] Answers to PRD §15 open questions (name/domain, cadence, level 6 vs 7, language, commercial intent, history store)
- [ ] Confirmation of network access in my environment to: `api-v3.thaiwater.net`, `api.open-meteo.com`, `flood-api.open-meteo.com`, HydroSHEDS, GISTDA
- [ ] ThaiWater terms of use / permission (or go-ahead to proceed on best-effort public use)
- [ ] GISTDA access route (public download vs. registration)
- [ ] Any known past flood event to calibrate against (e.g. Sept–Oct 2024 or 2025 northern/central floods)
- [ ] Domain expert input on key reach lags and station→segment mapping (optional; I will derive defaults)

## 3. Phase 0 — Foundations
- [ ] 0.1 Init git repo, `.gitignore`, README, LICENSE, project scaffolding per PRD §9 layout
- [ ] 0.1 GitHub: create repo, enable Actions + Pages, branch protection 🔒
- [ ] 0.1 `ci.yml` (lint + tests) and empty `deploy.yml` publishing a placeholder site
- [ ] 0.2 `/docs/sources.md`: access, terms, rate limits, attribution for ThaiWater, Open-Meteo, GISTDA, HydroSHEDS, geoBoundaries 🔒
- [ ] 0.3 Capture sample API responses → `/tests/fixtures` (needs network)
- [ ] 0.4 `static_layers/` preprocessing scripts:
  - [ ] Download HydroBASINS + HydroRIVERS, clip to Thailand, group under national main basins
  - [ ] Build river graph (segment id → downstream id, length) with networkx
  - [ ] Terrain factor per sub-basin (HAND from MERIT Hydro / Copernicus DEM; fallback: mean slope/elevation)
  - [ ] Simplify geometry to hit payload budget (< 3 MB gold total)
- [ ] 0.5 `config/stations_map.yaml`: auto-snap stations to nearest segment + sub-basin, manual overrides file
- [ ] 0.5 `config/risk_weights.yaml`, `config/lags.yaml` with defaults

## 4. Phase 1 — MVP "what's happening now" (F1, F2, F3, F11)
- [ ] 1.1 ThaiWater adapter: water level, bank level, dams; retries, timeouts, schema validation (pydantic), fixture tests
- [ ] 1.2 Bronze → silver: timestamped snapshots, Parquet/DuckDB, per-segment state + 24 h trend
- [ ] 1.3 Gold writers: `stations_latest.json`, `flow_vectors.geojson`, `meta.json`
- [ ] 1.3 Resilience: per-source failure → mark layer stale, never publish empty map
- [ ] 1.4 `pipeline.yml` cron + deploy to `gh-pages` (single force-pushed commit)
- [ ] 1.5 Web: MapLibre base map (open basemap, no key), layer panel, station popups, animated flow arrows (deck.gl), mobile responsive
- [ ] 1.6 Freshness badge (>6 h warning), disclaimer, attribution footer, links to DDPM/TMD/ThaiWater
- [ ] Colour-blind-safe palettes; trend also encoded by animation speed/pattern

## 5. Phase 2 — Risk and explanation (F4, F5)
- [ ] 2.1 Open-Meteo rainfall (observed + forecast) aggregated per upstream catchment
- [ ] 2.2 Open-Meteo Flood API (GloFAS) discharge per key segment
- [ ] 2.3 Rule-based risk model (PRD §8) with config weights, lag-based downstream propagation, top-driver output
- [ ] 2.4 `basins_risk.geojson` with D0–D+3 + drivers
- [ ] 2.5 Web: choropleth, legend, "why" side panel, upstream list, arrival estimate
- [ ] 2.6 Sanity check against a past event; tune weights; document results

## 6. Phase 3 — Time and context (F6–F10)
- [~] 3.1 History archive: only needed internally for 24 h trends (later); no user-facing history
- [x] 3.2 Replaced by forecast day buttons (+0..+3) — past days dropped by decision
- [ ] 3.3 Rainfall overlay, GISTDA flood extent overlay, reservoir markers
- [x] 3.4 Thai/English toggle (EN | ไทย): all UI text, legend, panels, risk reasons, province names, basemap labels; choice remembered, defaults to browser language

## 7. Phase 4 — Hardening (F12, F13, ML)
- [ ] 4.1 Shareable URLs
- [ ] 4.2 Back-testing + accuracy page
- [ ] 4.3 ML risk model
- [ ] 4.4 Failure alerts (auto-open issue on workflow failure)

## 8. Risks to verify early ⚠️
- ThaiWater API is undocumented — confirm endpoints/schema/terms in Phase 0 before building on it
- Sandbox/network access to external APIs and large HydroSHEDS downloads
- GISTDA data may need manual registration → F8 may slip
- Gold payload budget (< 3 MB) vs. sub-basin level choice
- Station→segment snapping errors (validate visually)
- GitHub cron delays / repo inactivity pause

## 8b. Done so far (local)
- [x] Scaffold, venv, requirements.txt, ruff/pytest (7 tests pass)
- [x] ThaiWater adapter (808 stations, retries incl. 200-with-error-body), fixture saved
- [x] Static layers: 225 sub-basins (HydroBASINS lev7), 5,634 river segments (upland >= 1000 km2), river graph, provinces
- [x] Station snapping to river segments (481/808) + basins; flow state propagated <= 40 km along the river
- [x] Open-Meteo rain (per basin) + GloFAS discharge (103/185 outlet cells usable), rule-based risk D0..D+3 with downstream propagation and drivers
- [x] Web: MapLibre map, basin risk choropleth, animated flow arrows, stations + popups, "why" panel, freshness badge, disclaimer, legend, mobile layout
- [x] Workflows written (pipeline.yml cron+Pages deploy+failure issue, ci.yml) - untested until on GitHub
- [x] Deviations from PRD: flow state is `flow_state.json` joined client-side to static rivers (smaller than flow_vectors.geojson); deploy via Pages artifact (no force-pushed gh-pages); animated dashes via MapLibre instead of deck.gl; terrain factor uses elevation proxy (no HAND yet); reservoirs weight unused (dam endpoint not found)
- [x] Forecast day buttons (Today/+1/+2/+3) recolour the map and the open panel; "Heading your way" list ranks areas at Elevated+ within 3 days, with a "getting worse" filter
- Decision (user): no historical view / past-days slider. History archive kept only as an optional later way to compute true 24 h trends (item 3)
- Not done: rainfall/flood-extent/reservoir layers, true 24 h trend, back-test
- Known: gold payload 3.1 MB uncompressed (gzip on Pages is much smaller); "trend" = change since previous reading, not 24 h

## 9. Log
- 2026-10-03 — PRD analysed, progress plan created.
- 2026-10-03 — Local prototype built end to end; browser verification pending.
- 2026-10-03 — Added forecast day buttons and Heading-your-way watchlist; dropped historical slider.
- 2026-10-03 — Added English/Thai language toggle (i18n JSON files, structured risk reasons, Thai province names).
- 2026-10-03 — "Heading your way" now scoped to the map view, closed by default; incoming = risk rising >=5 pts (Elevated+) or an Elevated+ upstream peak arriving within 72 h; capped at 8 with Show more; count of already-High steady areas shown as a summary.
