# Overflow (Thailand Flood Tracker) — Progress & Plan

Source: `thailand-flood-tracker-PRD.md` (Draft v0.1). Last updated: 4 Oct 2026.
Legend: `[ ]` todo · `[~]` in progress · `[x]` done · 🔒 blocked on user input · ⚠️ risk / needs verification

## 0. Status snapshot
- **Live:** https://danpob.github.io/overflow/ · repo https://github.com/danpob/overflow (public) · data refreshes about every 3 h via GitHub Actions.
- App name: **Overflow** (renamed from Risewise). English + Thai UI.
- Working now: national map with drainage-area risk (Today to +3 days), animated river flow, 808 water-level stations, "Heading your way" list scoped to the map view, day buttons, EN/TH toggle, geolocation, mobile layout.
- Next: see §10 backlog. Top candidates: road-impact cues, true 24 h trend, rainfall overlay, GISTDA flood extent, reservoirs.

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

## 2. Inputs from the user (resolved)
- [x] Name Overflow, English first with Thai toggle, 3-hourly refresh, level-7 basins, non-commercial, history only as internal data
- [x] GitHub account `danpob`, public repo `overflow`, commits use the GitHub noreply email
- [ ] Past flood event to calibrate against (optional, still open)

## 3. Phase 0 — Foundations
- [x] 0.1 Repo, `.gitignore`, README, scaffolding; GitHub repo + Pages + Actions enabled (no branch protection)
- [x] 0.1 `ci.yml` (PR lint + tests) and `pipeline.yml` (cron, test, build, deploy to Pages, issue on failed scheduled run)
- [x] 0.2 `docs/sources.md` for all sources (ThaiWater terms not confirmed; GISTDA access not yet set up)
- [x] 0.3 ThaiWater fixture in `tests/fixtures`
- [x] 0.4 Static layers: 225 level-7 sub-basins, 5,634 river segments, river graph, provinces (terrain factor is an elevation proxy; HAND not built)
- [x] 0.5 Station snapping to river segments and basins (automatic; no manual override file)
- [x] 0.5 `config/risk_weights.yaml` (weights, normalisation, propagation, terrain). No separate `lags.yaml`.

## 4. Phase 1 — MVP "what's happening now"
- [x] 1.1 ThaiWater adapter with retries (also on 200-with-error bodies) and schema checks; dam endpoint not found
- [~] 1.2 Per-segment current state done; no bronze/silver Parquet archive yet (needed for true 24 h trend)
- [x] 1.3 Gold files: `stations_latest.json`, `flow_state.json` (joined to static rivers in the browser), `basins_risk.json`, `meta.json`
- [x] 1.3 Resilience: per-source failure marks layer stale; never publishes an empty map
- [x] 1.4 Scheduled workflow + Pages deploy (artifact deploy, not force-pushed gh-pages)
- [x] 1.5 Web: MapLibre map, layer key, station popups, animated flow (MapLibre dashes, not deck.gl)
- [x] 1.6 Freshness badge, disclaimer (collapses on phones), attribution
- [x] Colour palettes: green-to-red stations with ring + halo; purple dropped; blue made more saturated

## 5. Phase 2 — Risk and explanation
- [x] 2.1 Open-Meteo rain (past 72 h and next 72 h) per basin centroid
- [x] 2.2 GloFAS discharge per basin outlet (103 of 185 cells usable)
- [x] 2.3 Rule-based risk with config weights, downstream propagation with lags, structured drivers
- [x] 2.4 `basins_risk.json` D0 to D+3 with drivers by day and upstream list
- [x] 2.5 Choropleth, key, "why" panel, upstream list with arrival hours
- [ ] 2.6 Calibrate against a past event (weights are untuned; list may over-flag)

## 6. Phase 3 — Time and context (F6–F10)
- [~] 3.1 History archive: only needed internally for 24 h trends (later); no user-facing history
- [x] 3.2 Replaced by forecast day buttons (+0..+3) — past days dropped by decision
- [ ] 3.3 Rainfall overlay, GISTDA flood extent overlay, reservoir markers (GISTDA flood-extent API needs a free API key; open data portal opendata.gistda.or.th)
- [x] 3.4 Thai/English toggle (EN | ไทย): all UI text, legend, panels, risk reasons, province names, basemap labels; choice remembered, defaults to browser language

## 7. Phase 4 — Hardening (F12, F13, ML)
- [ ] 4.1 Shareable URLs
- [ ] 4.2 Back-testing + accuracy page
- [ ] 4.3 ML risk model
- [x] 4.4 Failure alerts (issue auto-opened when a scheduled run fails)

## 8. Risks / known issues ⚠️
- ThaiWater API is undocumented and no usage terms were found; the app credits and links to ThaiWater
- Risk scores are rule-based, untuned and unvalidated; "Heading your way" may over-flag
- Scores are per drainage area (large); two places in one area get the same score
- GloFAS cells off the river are discarded (82 of 185 outlets); those basins rely on stations and rain
- "Trend" is change since the previous reading, not a 24 h trend
- Scheduled GitHub workflows pause after 60 days without repo activity
- Payload 3.1 MB uncompressed (gzip is far smaller)

## 8b. Build notes
- [x] Scaffold, venv, requirements.txt, ruff/pytest (7 tests pass)
- [x] ThaiWater adapter (808 stations, retries incl. 200-with-error-body), fixture saved
- [x] Static layers: 225 sub-basins (HydroBASINS lev7), 5,634 river segments (upland >= 1000 km2), river graph, provinces
- [x] Station snapping to river segments (481/808) + basins; flow state propagated <= 40 km along the river
- [x] Open-Meteo rain (per basin) + GloFAS discharge (103/185 outlet cells usable), rule-based risk D0..D+3 with downstream propagation and drivers
- [x] Web: MapLibre map, basin risk choropleth, animated flow arrows, stations + popups, "why" panel, freshness badge, disclaimer, legend, mobile layout
- [x] Workflows written and verified on GitHub (scheduled and push-triggered deploys succeed)
- [x] Deviations from PRD: flow state is `flow_state.json` joined client-side to static rivers (smaller than flow_vectors.geojson); deploy via Pages artifact (no force-pushed gh-pages); animated dashes via MapLibre instead of deck.gl; terrain factor uses elevation proxy (no HAND yet); reservoirs weight unused (dam endpoint not found)
- [x] Forecast day buttons (Today/+1/+2/+3) recolour the map and the open panel; "Heading your way" list ranks areas at Elevated+ within 3 days, with a "getting worse" filter
- Decision (user): no historical view / past-days slider. History archive kept only as an optional later way to compute true 24 h trends (item 3)
- Not done: rainfall/flood-extent/reservoir layers, true 24 h trend, back-test
- [x] **Road crossings**: 715 crossings where motorway/trunk/primary/secondary road bridges (OpenStreetMap, 18,249 bridges scanned) pass within 450 m of a main-stem river (`static_layers/build_crossings.py` -> `static_layers/out/crossings.json`). Live state in `pipeline/transform/crossings.py` -> `web/data/crossings_live.json`. Diamond markers, nothing drawn unless needed: solid red = a station within 6 km (and connected along the river within 15 km) reads at least 100% of bank and 0.2 m over it (measured, Today only); hollow amber = its drainage area is forecast High or worse on the selected day (modelled). Zoom >= 7.5, overlapping markers hidden, click opens a panel (name/route, measured line, forecast line, 'not a closure notice'). No roads-to-watch list by decision; no GISTDA by decision.
- Mobile: footer collapses to one line; key panel sits above it using the measured footer height

## 9. Log
- 2026-10-03 — PRD analysed, progress plan created.
- 2026-10-03 — Local prototype built end to end; browser verification pending.
- 2026-10-03 — Added forecast day buttons and Heading-your-way watchlist; dropped historical slider.
- 2026-10-03 — Added English/Thai language toggle (i18n JSON files, structured risk reasons, Thai province names).
- 2026-10-03 — "Heading your way" now scoped to the map view, closed by default; incoming = risk rising >=5 pts (Elevated+) or an Elevated+ upstream peak arriving within 72 h; capped at 8 with Show more; count of already-High steady areas shown as a summary.
- 2026-10-03 — App renamed from Risewise to Overflow.
- 2026-10-03 — Published: repo danpob/overflow (public), Pages via Actions, first scheduled-pipeline run succeeded. Commits use the GitHub noreply address. Fixed station halo layer (invalid zoom expression).
- 2026-10-03 — Mobile fix: collapsible footer, key panel positioned above it. Progress file brought up to date.

## 10. Backlog / ideas
- ~~Road-impact cues~~ built as **road crossings** (see §8b). Possible follow-ups: observed flood extent or official closure feed as a third, stronger tier; district names for repeated province labels.
- True 24 h trend (needs a rolling history archive in the pipeline; no user-facing history view).
- Rainfall overlay, GISTDA observed flood extent, reservoir markers.
- Calibration against a past flood event; tune risk thresholds.
- Optional: finer drainage areas (level 8), shareable URLs.
- 2026-10-04 — Road crossings feature built (OSM bridges x HydroRIVERS main stems x stations), tests added (10 pass).
