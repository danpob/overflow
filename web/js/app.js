const GEOM = {};
const TREND = ["unknown", "falling", "stable", "rising", "rising_fast"];
const TREND_COLOR = { falling: "#0a6ee6", stable: "#8a94a0", rising: "#f0a202", rising_fast: "#d7301f" };
const RISK_COLORS = ["#bfe3b4", "#f7ec9a", "#fbbf66", "#ee6a4a", "#a8222c"];
const $ = (s) => document.querySelector(s);
let DAY = 0, RISK = null, META = null, PANEL = null;

// ---------- i18n ----------
let LANG = "en", STR = {}, PROV_TH = {};
const THAI_RE = /[฀-๿]/;
const t = (k, v = {}) => (STR[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => v[n] ?? "");
const provName = (en) => (en ? (LANG === "th" ? PROV_TH[en] || en : en) : "");
const lvlName = (i) => t("lvl" + i);

function storedLang() {
  try { const s = localStorage.getItem("rw_lang"); if (s === "en" || s === "th") return s; } catch (e) { /* storage blocked */ }
  return (navigator.language || "").toLowerCase().startsWith("th") ? "th" : "en";
}

function applyStatic() {
  document.documentElement.lang = LANG;
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-html]").forEach((el) => (el.innerHTML = t(el.dataset.i18nHtml)));
  document.querySelectorAll("[data-i18n-title]").forEach((el) => (el.title = t(el.dataset.i18nTitle)));
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
  $("#days").setAttribute("aria-label", t("days_aria"));
  document.querySelectorAll("#lang button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === LANG));
  updateCollapse();
  if (!META) $("#fresh").textContent = t("loading");
}
function updateCollapse() {
  $("#collapse").textContent = t("key") + ($("#panel").classList.contains("min") ? " ▸" : " ▾");
}

async function setLang(l, first = false) {
  LANG = l;
  try { localStorage.setItem("rw_lang", l); } catch (e) { /* storage blocked */ }
  if (!STR.__l || STR.__l !== l) {
    STR = await fetch(`i18n/${l}.json`).then((r) => r.json());
    STR.__l = l;
  }
  applyStatic();
  if (first) return;
  setBasemapLang();
  if (META) { freshness(META); renderDays(); renderWatchBtn(); }
  renderPanel();
}

function setBasemapLang() {
  if (!map.isStyleLoaded() && !map.getStyle()) return;
  const field = LANG === "th"
    ? ["coalesce", ["get", "name:th"], ["get", "name"]]
    : ["coalesce", ["get", "name_en"], ["get", "name:latin"], ["get", "name"]];
  for (const l of map.getStyle().layers) {
    const tf = l.layout && l.layout["text-field"];
    if (l.type === "symbol" && tf && JSON.stringify(tf).includes("name")) map.setLayoutProperty(l.id, "text-field", field);
  }
}

// ---------- helpers ----------
const levelExpr = (prop) => ["match", ["get", prop], 0, RISK_COLORS[0], 1, RISK_COLORS[1], 2, RISK_COLORS[2], 3, RISK_COLORS[3], 4, RISK_COLORS[4], "rgba(0,0,0,0)"];
function bboxCenter(geom) {
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  const walk = (c) => (typeof c[0] === "number" ? ((x0 = Math.min(x0, c[0])), (x1 = Math.max(x1, c[0])), (y0 = Math.min(y0, c[1])), (y1 = Math.max(y1, c[1]))) : c.forEach(walk));
  walk(geom.coordinates);
  return { center: [(x0 + x1) / 2, (y0 + y1) / 2], bounds: [[x0, y0], [x1, y1]] };
}
const getJSON = (u) => fetch(u, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNull = (v) => v === "null" || v == null;

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [100.9, 14.2], zoom: 5.3, minZoom: 4, maxZoom: 11,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

function freshness(meta) {
  const el = $("#fresh");
  const gen = new Date(meta.generated_at);
  const latest = meta.layers?.stations?.latest_obs; // "YYYY-MM-DD HH:MM" ICT
  const obs = latest ? new Date(latest.replace(" ", "T") + ":00+07:00") : gen;
  const ageH = (Date.now() - obs.getTime()) / 36e5;
  const hhmm = obs.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Bangkok" });
  const stale = Object.entries(meta.layers || {}).filter(([, v]) => v.status !== "ok").map(([k]) => k);
  el.textContent = ageH > 6 ? t("fresh_old", { h: Math.round(ageH), t: hhmm }) : t("fresh_ok", { t: hhmm });
  el.className = "badge " + (ageH > 6 || stale.length ? "warn" : "ok");
  el.title = stale.length ? t("fresh_stale_layers", { l: stale.join(", ") }) : "";
}

function pctColorExpr(prop) {
  return ["step", ["coalesce", ["get", prop], -1], "#d5d8dc", 0, "#2fa84f", 50, "#e6d630", 70, "#f28c28", 90, "#e0302b", 100, "#7d0b14"];
}

map.on("load", async () => {
  await langReady;
  const [meta, rivers, state, stations, provinces] = await Promise.all([
    getJSON("data/meta.json"), getJSON("data/rivers.geojson"), getJSON("data/flow_state.json"),
    getJSON("data/stations_latest.json"), getJSON("data/provinces.geojson"),
  ]);
  const basins = await getJSON("data/basins.geojson");
  const risk = await getJSON("data/basins_risk.json").catch(() => null);
  META = meta; RISK = risk;
  freshness(meta);
  setBasemapLang();

  // join dynamic state onto static river geometry
  for (const f of rivers.features) {
    const s = state[f.properties.hyriv_id];
    f.properties.pct = s ? s[0] : null;
    f.properties.trend = s ? TREND[s[1]] : "none";
    f.properties.has = s ? 1 : 0;
    f.properties.w = Math.max(0.6, Math.log10(f.properties.dis_av_cms + 1) * 1.1);
  }
  // join risk onto basin polygons
  for (const f of basins.features) {
    const r = risk?.basins?.[f.properties.hybas_id];
    for (let d = 0; d < 4; d++) f.properties["l" + d] = r ? r.levels[d] : null;
    GEOM[f.properties.hybas_id] = bboxCenter(f.geometry);
  }

  map.addSource("provinces", { type: "geojson", data: provinces });
  map.addSource("basins", { type: "geojson", data: basins, promoteId: "hybas_id" });
  map.addSource("rivers", { type: "geojson", data: rivers });
  map.addSource("stations", {
    type: "geojson",
    data: { type: "FeatureCollection", features: stations.map((s) => ({ type: "Feature", properties: s, geometry: { type: "Point", coordinates: [s.lon, s.lat] } })) },
  });

  map.addLayer({ id: "basins-fill", type: "fill", source: "basins", paint: { "fill-color": levelExpr("l0"), "fill-opacity": 0.4 } });
  map.addLayer({ id: "basins-line", type: "line", source: "basins", paint: { "line-color": "#6b7785", "line-width": 0.7, "line-opacity": 0.7 } });
  map.addLayer({ id: "provinces-hit", type: "fill", source: "provinces", paint: { "fill-color": "#000", "fill-opacity": 0 } });
  map.addLayer({ id: "basin-highlight", type: "line", source: "basins", filter: ["==", ["get", "hybas_id"], -1],
    paint: { "line-color": "#14202b", "line-width": 2.5 } });
  map.addLayer({ id: "provinces-line", type: "line", source: "provinces", layout: { visibility: "none" }, paint: { "line-color": "#556", "line-width": 0.8, "line-dasharray": [2, 2] } });

  // rivers with no data: thin neutral
  map.addLayer({ id: "flow-none", type: "line", source: "rivers", filter: ["==", ["get", "has"], 0],
    paint: { "line-color": "#c3cad1", "line-width": 0.6 } });
  // rivers with data: colour by trend, width by mean discharge
  for (const tr of Object.keys(TREND_COLOR)) {
    map.addLayer({ id: "flow-" + tr, type: "line", source: "rivers", filter: ["==", ["get", "trend"], tr],
      layout: { "line-cap": "round" },
      paint: { "line-color": TREND_COLOR[tr], "line-width": ["get", "w"], "line-opacity": 0.45 } });
    map.addLayer({ id: "flow-anim-" + tr, type: "line", source: "rivers", filter: ["==", ["get", "trend"], tr],
      paint: { "line-color": "#ffffff", "line-width": ["*", ["get", "w"], 0.55], "line-opacity": 0.9, "line-dasharray": [0, 4, 3] } });
  }
  // dots sit on a dark halo + white ring so they stay readable on top of the shaded risk areas
  const over = ["case", [">=", ["coalesce", ["get", "pct"], 0], 100]];
  // zoom must be the top-level input, so the optional extra (halo width) is added inside each stop
  const dotR = (a, b, c, extra = 0) => ["interpolate", ["linear"], ["zoom"],
    4, [...over, a + 1 + extra, a + extra], 8, [...over, b + 2 + extra, b + extra], 11, [...over, c + 2 + extra, c + extra]];
  map.addLayer({ id: "stations-halo", type: "circle", source: "stations",
    paint: { "circle-radius": dotR(3, 5, 8, 2.6), "circle-color": "#1b1f2a", "circle-opacity": 0.7 } });
  map.addLayer({
    id: "stations-circle", type: "circle", source: "stations",
    paint: {
      "circle-radius": dotR(3, 5, 8),
      "circle-color": pctColorExpr("pct"),
      "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.6, "circle-opacity": 1,
    },
  });
  animateFlow();

  // --- layer toggles
  const groups = {
    flow: () => map.getStyle().layers.filter((l) => l.id.startsWith("flow-")).map((l) => l.id),
    stations: () => ["stations-halo", "stations-circle"],
    basins: () => ["basins-fill", "basins-line"],
    provinces: () => ["provinces-line"],
  };
  document.querySelectorAll("[data-layer]").forEach((cb) => {
    const apply = () => groups[cb.dataset.layer]().forEach((id) => map.setLayoutProperty(id, "visibility", cb.checked ? "visible" : "none"));
    cb.addEventListener("change", apply);
    apply();
  });
  $("#collapse").onclick = () => { $("#panel").classList.toggle("min"); updateCollapse(); };
  if (innerWidth < 700) $("#collapse").click();

  // --- interactions
  const pointer = (id) => {
    map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
  };
  pointer("stations-circle"); pointer("basins-fill");
  map.on("click", "stations-circle", (e) => { e.originalEvent.stopPropagation_ = true; showStation(e.features[0].properties); });
  map.on("click", "basins-fill", (e) => {
    if (e.defaultPrevented || e.originalEvent.stopPropagation_) return;
    if (map.queryRenderedFeatures(e.point, { layers: ["stations-circle"] }).length) return;
    const prov = map.queryRenderedFeatures(e.point, { layers: ["provinces-hit"] })[0];
    showBasin(e.features[0].properties, prov?.properties.name);
  });
  renderDays();
  renderWatchBtn();
  $("#watchbtn").onclick = showWatchlist;
  $("#days").onclick = (e) => { const b = e.target.closest("button"); if (b) setDay(+b.dataset.d); };
  // the list follows the map view: refresh the count (and the list, if open) after the map settles
  let viewTimer;
  map.on("moveend", () => { clearTimeout(viewTimer); viewTimer = setTimeout(() => { renderWatchBtn(); if (PANEL?.k === "watch") renderWatchlist(); }, 250); });
  $("#close").onclick = closePanel;

  // --- geolocation: centre on the user if they are in Thailand (location never leaves the browser)
  const geo = new maplibregl.GeolocateControl({
    positionOptions: { enableHighAccuracy: false, timeout: 10000 },
    fitBoundsOptions: { maxZoom: 9 }, showAccuracyCircle: false,
  });
  map.addControl(geo, "bottom-right");
  const inThailand = (lat, lon) => lat > 5.5 && lat < 20.6 && lon > 97.3 && lon < 105.7;
  const flyToUser = (lat, lon) => {
    map.flyTo({ center: [lon, lat], zoom: 8.5, duration: 1800 });
    new maplibregl.Marker({ color: "#1b6ca8" }).setLngLat([lon, lat]).addTo(map);
    map.once("moveend", () => {
      const hit = map.queryRenderedFeatures(map.project([lon, lat]), { layers: ["basins-fill"] });
      const prov = map.queryRenderedFeatures(map.project([lon, lat]), { layers: ["provinces-hit"] })[0];
      if (hit.length && risk) showBasin(hit[0].properties, prov?.properties.name);
    });
  };
  if ("geolocation" in navigator) {
    navigator.geolocation.getCurrentPosition(
      (pos) => { const { latitude: lat, longitude: lon } = pos.coords; if (inThailand(lat, lon)) flyToUser(lat, lon); },
      () => {}, // denied or unavailable: stay on the national view
      { timeout: 10000, maximumAge: 600000 });
  }
});

// animated dashes: faster when water rises faster
function animateFlow() {
  const seq = [[0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5]];
  const speed = { falling: 0.6, stable: 0.3, rising: 1, rising_fast: 1.8 };
  const step = {};
  const tick = (ts) => {
    for (const tr of Object.keys(speed)) {
      const i = Math.floor((ts / 1000) * 8 * speed[tr]) % seq.length;
      if (step[tr] !== i && map.getLayer("flow-anim-" + tr)) { map.setPaintProperty("flow-anim-" + tr, "line-dasharray", seq[i]); step[tr] = i; }
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ---------- day buttons ----------
const dayPlus = (n) => (n === 1 ? t("day_plus_1") : t("day_plus_n", { n }));
const dayName = (d) => {
  if (d === 0) return t("day_today");
  const dt = new Date(new Date(META.generated_at).getTime() + d * 864e5);
  return dt.toLocaleDateString(LANG === "th" ? "th-TH" : "en-GB", { weekday: "short", timeZone: "Asia/Bangkok" });
};

function renderDays() {
  const box = $("#days");
  box.innerHTML = [0, 1, 2, 3].map((d) => `<button data-d="${d}" aria-pressed="${d === DAY}">${d === 0 ? t("day_today") : dayPlus(d)}</button>`).join("");
  box.style.display = RISK ? "" : "none";
}

function renderWatchBtn() {
  const n = watchEntries().incoming.length;
  const b = $("#watchbtn");
  b.title = t("watch_title");
  b.innerHTML = `${esc(t("watch_btn"))}${n ? `<b>${n}</b>` : ""}`;
}

function setDay(d) {
  DAY = d;
  document.querySelectorAll("#days button").forEach((b) => b.setAttribute("aria-pressed", +b.dataset.d === d));
  map.setPaintProperty("basins-fill", "fill-color", levelExpr("l" + d));
  if (PANEL?.k === "basin") renderPanel();   // keep an open panel in step
}

// ---------- driver sentences (data carries structure, text is made here) ----------
function stationName(d) {
  if (LANG === "th") return d.th || d.en;
  return THAI_RE.test(d.en) ? t("anon_station", { prov: provName(d.prov) }) : d.en;
}
function fmtDriver(d) {
  switch (d.t) {
    case "station": return t("d_station", { name: stationName(d), pct: d.pct, trend: t("trn_" + d.trend).toLowerCase() });
    case "rain_obs": return t("d_rain_obs", { mm: d.mm });
    case "rain_fc": return t("d_rain_fc", { mm: d.mm });
    case "disc": return t("d_disc", { x: d.x });
    case "up": return t("d_up", { prov: provName(d.prov) || t("up_generic"), lvl: lvlName(d.lvl), h: d.h });
    default: return "";
  }
}

// ---------- panels ----------
function closePanel() {
  PANEL = null;
  $("#detail").hidden = true;
  map.setFilter("basin-highlight", ["==", ["get", "hybas_id"], -1]);
}

function renderPanel() {
  if (!PANEL) return;
  if (PANEL.k === "watch") renderWatchlist();
  else if (PANEL.k === "basin") renderBasin();
  else if (PANEL.k === "station") renderStation();
}

function showStation(p) { PANEL = { k: "station", p }; map.setFilter("basin-highlight", ["==", ["get", "hybas_id"], -1]); renderStation(); }
function showWatchlist() { PANEL = { k: "watch", more: false }; map.setFilter("basin-highlight", ["==", ["get", "hybas_id"], -1]); renderWatchlist(); }
function showBasin(p, where, fromList = false) {
  PANEL = { k: "basin", p, where, fromList: fromList || (PANEL?.k === "basin" && PANEL.fromList) };
  map.setFilter("basin-highlight", ["==", ["get", "hybas_id"], +p.hybas_id]);
  renderBasin();
}

function renderStation() {
  const p = PANEL.p;
  const pct = isNull(p.pct) ? null : +p.pct;
  const bank = isNull(p.bank_level) ? "—" : (+p.bank_level).toFixed(2) + " m";
  const lvl = isNull(p.level_msl) ? "—" : (+p.level_msl).toFixed(2) + " m";
  const delta = isNull(p.delta) ? "—" : (+p.delta > 0 ? "+" : "") + (+p.delta).toFixed(2) + " m";
  const prov = LANG === "th" && !isNull(p.province_th) ? p.province_th : (isNull(p.province_en) ? "" : provName(p.province_en));
  let title = LANG === "th" ? p.name_th || p.name_en : p.name_en;
  let extra = "";
  if (LANG === "en" && THAI_RE.test(title)) { extra = title; title = t("anon_station", { prov }); }
  const river = LANG === "th" && !isNull(p.river) ? p.river : "";   // river names exist in Thai only
  const sub = [river, prov, extra].filter(Boolean).map(esc).join(" · ");
  const trend = t("trn_" + (p.trend in { falling: 1, stable: 1, rising: 1, rising_fast: 1 } ? p.trend : "unknown"));
  $("#detail-body").innerHTML = `
    <h2>${esc(title)}</h2><div class="sub">${sub}</div>
    <table>
      <tr><td>${t("s_level")}</td><td>${lvl}</td></tr>
      <tr><td>${t("s_bank")}</td><td>${bank}</td></tr>
      <tr><td>${t("s_pct")}</td><td><b>${pct == null ? "—" : pct.toFixed(0) + "%"}</b></td></tr>
      <tr><td>${t("s_change")}</td><td>${delta} (${trend})</td></tr>
      <tr><td>${t("s_observed")}</td><td>${esc(p.observed_at || "—")} ${LANG === "th" ? "น." : "ICT"}</td></tr>
      <tr><td>${t("s_source")}</td><td>${esc(p.source)}</td></tr>
    </table>`;
  $("#detail").hidden = false;
}

// "Incoming" = risk rising within 3 days, or a peak is on its way from an upstream area. Scoped to the map view.
const LVL_MIN_UP = 1, LVL_MIN_RISE = 2, VIEW_CAP = 8;
function watchEntries() {
  if (!RISK) return { incoming: [], steady: 0 };
  const bounds = map.getBounds();
  const incoming = []; let steady = 0;
  for (const [id, r] of Object.entries(RISK.basins)) {
    const g = GEOM[id];
    if (!g || !bounds.contains(g.center)) continue;
    const peak = Math.max(...r.scores), pd = r.scores.indexOf(peak), lvl = r.levels[pd];
    const rises = Math.max(...r.scores.slice(1)) - r.scores[0] >= 5 && lvl >= LVL_MIN_RISE;
    const ups = (r.upstream || []).filter((u) => u.level >= 2 && u.eta_h != null && u.eta_h <= 72)
      .sort((a, b) => b.level - a.level || a.eta_h - b.eta_h);
    const upstream = lvl >= LVL_MIN_UP && ups.length ? ups[0] : null;
    if (rises || upstream) incoming.push({ id, r, peak, pd, lvl, rises, upstream });
    else if (r.levels[0] >= 3) steady++;
  }
  incoming.sort((a, b) => b.peak - a.peak || (a.upstream?.eta_h ?? 99) - (b.upstream?.eta_h ?? 99));
  return { incoming, steady };
}

function entryReason(e) {
  const lines = [];
  if (e.upstream) {
    const pv = RISK.basins[e.upstream.id]?.provinces?.[0];
    lines.push(t("w_up", { prov: provName(pv) || t("up_generic"), lvl: lvlName(e.upstream.level), h: e.upstream.eta_h }));
  }
  if (e.rises) lines.push(t("w_rising", { lvl: lvlName(e.lvl), day: dayName(e.pd) }));
  return lines;
}

function renderWatchlist() {
  const { incoming, steady } = watchEntries();
  const shown = PANEL.more ? incoming.slice(0, 30) : incoming.slice(0, VIEW_CAP);
  const rest = incoming.length - shown.length;
  const summary = t(incoming.length ? "w_summary" : "w_summary0", { a: incoming.length, b: steady });
  $("#detail-body").innerHTML = `
    <h2>${t("w_title")}</h2>
    <div class="sub">${t("w_sub")}</div>
    <div class="sub" style="color:var(--fg)">${summary}</div>
    ${shown.map((e) => `<button class="wi" data-id="${e.id}"><div class="wt"><b>${esc(t("near", { x: provName(e.r.provinces[0]) || "—" }))}</b>
        <span class="pill" style="background:${e.lvl === 2 ? "#e08a1e" : e.lvl === 1 ? "#c9b400" : RISK_COLORS[e.lvl]}">${lvlName(e.lvl)} · ${e.pd === 0 ? t("now") : esc(dayName(e.pd))}</span></div>
        ${entryReason(e).map((x) => `<div class="wd">${esc(x)}</div>`).join("")}</button>`).join("")}
    ${incoming.length ? "" : `<div class="sub">${t("w_empty")}</div>`}
    ${rest > 0 ? `<button class="more" id="more">${t("w_more", { n: rest })}</button>` : ""}
    ${map.getZoom() < 7 && incoming.length > VIEW_CAP ? `<div class="sub" style="margin-top:6px">${t("w_zoom")}</div>` : ""}
    <div class="sub" style="margin-top:8px">${t("disclaimer")}</div>`;
  $("#detail").hidden = false;
  const m = $("#more"); if (m) m.onclick = () => { PANEL.more = true; renderWatchlist(); };
  $("#detail-body").querySelectorAll(".wi").forEach((b) => (b.onclick = () => {
    const id = b.dataset.id, g = GEOM[id], r = RISK.basins[id];
    map.fitBounds(g.bounds, { padding: { top: 140, bottom: 160, left: 40, right: 40 }, maxZoom: 8.5, duration: 900 });
    showBasin({ hybas_id: id }, r.provinces[0], true);
  }));
}

function renderBasin() {
  const { p, where, fromList } = PANEL;
  const r = RISK?.basins?.[p.hybas_id];
  const back = fromList ? `<button class="back" id="back">${t("back")}</button>` : "";
  if (!r) {
    $("#detail-body").innerHTML = `${back}<h2>${t("area_h")}</h2><div class="sub">${t("no_score")}</div>`;
    $("#detail").hidden = false; return;
  }
  const lvl = r.levels[DAY];
  const drivers = (r.drivers_by_day[DAY] || []).map((d) => `<li>${esc(fmtDriver(d))}</li>`).join("") || `<li>${t("no_drivers")}</li>`;
  const ups = (r.upstream || []).map((u) => {
    const pv = RISK.basins[u.id]?.provinces?.[0];
    return `<li>${esc(t("up_item", { prov: provName(pv) || t("up_generic"), lvl: lvlName(u.level) }))}${u.eta_h != null ? esc(t("up_eta", { h: u.eta_h })) : ""}</li>`;
  }).join("");
  const river = LANG === "th" && r.name && r.name !== "Sub-basin" ? ` (${esc(r.name)})` : "";
  const provs = (r.provinces || []).map(provName).join(LANG === "th" ? " " : ", ") || "—";
  const when = DAY === 0 ? t("risk_today") : t("risk_on", { d: dayName(DAY) });
  const pillBg = lvl === 0 ? "#4f8f45" : lvl === 2 ? "#e08a1e" : RISK_COLORS[lvl];
  $("#detail-body").innerHTML = `${back}
    <h2>${where ? esc(t("near", { x: provName(where) })) : t("area_h")}</h2>
    <div class="sub">${t("area_desc", { river, provs: esc(provs) })}</div>
    <div class="sub">${esc(when)} <span class="pill" style="background:${pillBg};color:${lvl === 1 ? "#222" : "#fff"}">${lvlName(lvl)} · ${r.scores[DAY]}</span></div>
    <table>${r.scores.map((s, i) => `<tr class="${i === DAY ? "sel" : ""}"><td>${i === 0 ? t("today") : esc(dayPlus(i)) + " (" + esc(dayName(i)) + ")"}</td><td>${lvlName(r.levels[i])} (${s})</td></tr>`).join("")}</table>
    <h3 style="font-size:12px;margin:12px 0 2px;color:var(--mut)">${t("why")}</h3><ol>${drivers}</ol>
    ${ups ? `<h3 style="font-size:12px;margin:12px 0 2px;color:var(--mut)">${t("upstream_h")}</h3><ol>${ups}</ol>` : ""}
    <div class="sub" style="margin-top:10px">${t("disclaimer")}</div>`;
  $("#detail").hidden = false;
  const bk = $("#back"); if (bk) bk.onclick = showWatchlist;
}

// ---------- boot ----------
document.querySelectorAll("#lang button").forEach((b) => (b.onclick = () => setLang(b.dataset.lang)));
var langReady = Promise.all([fetch("i18n/provinces_th.json").then((r) => r.json()).catch(() => ({})), setLang(storedLang(), true)])
  .then(([pt]) => { PROV_TH = pt; });
