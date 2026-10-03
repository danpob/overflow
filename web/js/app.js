const TREND = ["unknown", "falling", "stable", "rising", "rising_fast"];
const TREND_LABEL = { unknown: "Unknown", falling: "Falling", stable: "Stable", rising: "Rising", rising_fast: "Rising fast" };
const TREND_COLOR = { falling: "#2c7fb8", stable: "#8a94a0", rising: "#f0a202", rising_fast: "#d7301f" };
const RISK_LEVELS = ["Low", "Watch", "Elevated", "High", "Severe"];
const RISK_COLORS = ["#bfe3b4", "#f7ec9a", "#fbbf66", "#ee6a4a", "#a8222c"];
const $ = (s) => document.querySelector(s);
const getJSON = (u) => fetch(u, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });

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
  el.textContent = ageH > 6 ? `⚠ Data is ${Math.round(ageH)} h old (${hhmm} ICT)` : `Updated ${hhmm} ICT`;
  el.className = "badge " + (ageH > 6 || stale.length ? "warn" : "ok");
  if (stale.length) el.title = "Stale layers: " + stale.join(", ");
}

function pctColorExpr(prop) {
  return ["step", ["coalesce", ["get", prop], -1], "#d5d8dc", 0, "#ddd8ee", 50, "#cbc9e2", 70, "#9e9ac8", 90, "#756bb1", 100, "#54278f"];
}

map.on("load", async () => {
  const [meta, rivers, state, stations, provinces] = await Promise.all([
    getJSON("data/meta.json"), getJSON("data/rivers.geojson"), getJSON("data/flow_state.json"),
    getJSON("data/stations_latest.json"), getJSON("data/provinces.geojson"),
  ]);
  const basins = await getJSON("data/basins.geojson");
  const risk = await getJSON("data/basins_risk.json").catch(() => null);
  freshness(meta);

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
    f.properties.score = r ? r.scores[0] : null;
    f.properties.level = r ? r.levels[0] : null;
  }

  map.addSource("provinces", { type: "geojson", data: provinces });
  map.addSource("basins", { type: "geojson", data: basins, promoteId: "hybas_id" });
  map.addSource("rivers", { type: "geojson", data: rivers });
  map.addSource("stations", {
    type: "geojson",
    data: { type: "FeatureCollection", features: stations.map((s) => ({ type: "Feature", properties: s, geometry: { type: "Point", coordinates: [s.lon, s.lat] } })) },
  });

  map.addLayer({
    id: "basins-fill", type: "fill", source: "basins",
    paint: {
      "fill-color": ["match", ["get", "level"], 0, RISK_COLORS[0], 1, RISK_COLORS[1], 2, RISK_COLORS[2], 3, RISK_COLORS[3], 4, RISK_COLORS[4], "rgba(0,0,0,0)"],
      "fill-opacity": 0.5,
    },
  });
  map.addLayer({ id: "basins-line", type: "line", source: "basins", paint: { "line-color": "#6b7785", "line-width": 0.7, "line-opacity": 0.7 } });
  map.addLayer({ id: "provinces-hit", type: "fill", source: "provinces", paint: { "fill-color": "#000", "fill-opacity": 0 } });
  map.addLayer({ id: "basin-highlight", type: "line", source: "basins", filter: ["==", ["get", "hybas_id"], -1],
    paint: { "line-color": "#14202b", "line-width": 2.5 } });
  map.addLayer({ id: "provinces-line", type: "line", source: "provinces", layout: { visibility: "none" }, paint: { "line-color": "#556", "line-width": 0.8, "line-dasharray": [2, 2] } });

  // rivers with no data: thin neutral
  map.addLayer({ id: "flow-none", type: "line", source: "rivers", filter: ["==", ["get", "has"], 0],
    paint: { "line-color": "#c3cad1", "line-width": 0.6 } });
  // rivers with data: colour by trend, width by mean discharge
  for (const t of Object.keys(TREND_COLOR)) {
    map.addLayer({ id: "flow-" + t, type: "line", source: "rivers", filter: ["==", ["get", "trend"], t],
      layout: { "line-cap": "round" },
      paint: { "line-color": TREND_COLOR[t], "line-width": ["get", "w"], "line-opacity": 0.45 } });
    map.addLayer({ id: "flow-anim-" + t, type: "line", source: "rivers", filter: ["==", ["get", "trend"], t],
      paint: { "line-color": "#ffffff", "line-width": ["*", ["get", "w"], 0.55], "line-opacity": 0.9, "line-dasharray": [0, 4, 3] } });
  }
  map.addLayer({
    id: "stations-circle", type: "circle", source: "stations",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        4, ["case", [">=", ["coalesce", ["get", "pct"], 0], 100], 4, 3],
        8, ["case", [">=", ["coalesce", ["get", "pct"], 0], 100], 7, 5],
        11, ["case", [">=", ["coalesce", ["get", "pct"], 0], 100], 10, 8]],
      "circle-color": pctColorExpr("pct"),
      "circle-stroke-color": "#2b2150", "circle-stroke-width": 0.9, "circle-opacity": 1,
    },
  });
  animateFlow();

  // --- layer toggles
  const groups = {
    flow: () => map.getStyle().layers.filter((l) => l.id.startsWith("flow-")).map((l) => l.id),
    stations: () => ["stations-circle"],
    basins: () => ["basins-fill", "basins-line"],
    provinces: () => ["provinces-line"],
  };
  document.querySelectorAll("[data-layer]").forEach((cb) => {
    const apply = () => groups[cb.dataset.layer]().forEach((id) => map.setLayoutProperty(id, "visibility", cb.checked ? "visible" : "none"));
    cb.addEventListener("change", apply);
    apply();
  });
  $("#collapse").onclick = () => { const m = $("#panel").classList.toggle("min"); $("#collapse").setAttribute("aria-expanded", !m); $("#collapse").textContent = m ? "Key ▸" : "Key ▾"; };
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
    const hit = map.queryRenderedFeatures(e.point, { layers: ["stations-circle"] });
    if (hit.length) return;
    const prov = map.queryRenderedFeatures(e.point, { layers: ["provinces-hit"] })[0];
    showBasin(e.features[0].properties, risk, prov?.properties.name);
  });
  $("#close").onclick = () => { $("#detail").hidden = true; map.setFilter("basin-highlight", ["==", ["get", "hybas_id"], -1]); };

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
      if (hit.length && risk) showBasin(hit[0].properties, risk, prov?.properties.name);
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
    for (const t of Object.keys(speed)) {
      const i = Math.floor((ts / 1000) * 8 * speed[t]) % seq.length;
      if (step[t] !== i && map.getLayer("flow-anim-" + t)) { map.setPaintProperty("flow-anim-" + t, "line-dasharray", seq[i]); step[t] = i; }
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function showStation(p) {
  const pct = p.pct === "null" || p.pct == null ? null : +p.pct;
  const bank = p.bank_level === "null" || p.bank_level == null ? null : (+p.bank_level).toFixed(2) + " m";
  const lvl = p.level_msl === "null" || p.level_msl == null ? "—" : (+p.level_msl).toFixed(2) + " m";
  const delta = p.delta === "null" || p.delta == null ? "—" : (+p.delta > 0 ? "+" : "") + (+p.delta).toFixed(2) + " m";
  $("#detail-body").innerHTML = `
    <h2>${esc(p.name_en)}</h2><div class="sub">${esc(p.river || "")} ${p.province_en && p.province_en !== "null" ? "· " + esc(p.province_en) : ""}</div>
    <table>
      <tr><td>Water level (MSL)</td><td>${lvl}</td></tr>
      <tr><td>Bank level</td><td>${bank || "—"}</td></tr>
      <tr><td>% of bank capacity</td><td><b>${pct == null ? "—" : pct.toFixed(0) + "%"}</b></td></tr>
      <tr><td>Change since last reading</td><td>${delta} (${TREND_LABEL[p.trend] || "—"})</td></tr>
      <tr><td>Observed</td><td>${esc(p.observed_at || "—")} ICT</td></tr>
      <tr><td>Source</td><td>${esc(p.source)}</td></tr>
    </table>`;
  $("#detail").hidden = false;
}

function showBasin(p, risk, where) {
  const r = risk?.basins?.[p.hybas_id];
  map.setFilter("basin-highlight", ["==", ["get", "hybas_id"], +p.hybas_id]);
  if (!r) {
    $("#detail-body").innerHTML = `<h2>Drainage area</h2><div class="sub">Risk score not available yet.</div>`;
    $("#detail").hidden = false; return;
  }
  const days = ["Today", "+1 day", "+2 days", "+3 days"];
  const drivers = r.drivers.map((d) => `<li>${esc(d)}</li>`).join("") || "<li>No significant drivers</li>";
  const ups = (r.upstream || []).map((u) => `<li>Upstream area ${u.id} — risk ${RISK_LEVELS[u.level]}${u.eta_h != null ? `, peak reaches here in ~${u.eta_h} h` : ""}</li>`).join("");
  $("#detail-body").innerHTML = `
    <h2>${where ? "Near " + esc(where) : "Drainage area"}</h2>
    <div class="sub">The outlined <b>drainage area</b> — all land whose rain flows to the same river stretch${r.name && r.name !== "Sub-basin" ? " (" + esc(r.name) + ")" : ""}. It covers ${esc((r.provinces || []).join(", ") || "—")} and gets one score.</div>
    <div class="sub">Risk today: <span class="pill" style="background:${r.levels[0] === 0 ? "#4f8f45" : RISK_COLORS[r.levels[0]]};color:${r.levels[0] === 1 ? "#222" : "#fff"}">${RISK_LEVELS[r.levels[0]]} · ${r.scores[0]}</span></div>
    <table>${r.scores.map((s, i) => `<tr><td>${days[i]}</td><td>${RISK_LEVELS[r.levels[i]]} (${s})</td></tr>`).join("")}</table>
    <h3 style="font-size:12px;margin:12px 0 2px;color:var(--mut)">WHY</h3><ol>${drivers}</ol>
    ${ups ? `<h3 style="font-size:12px;margin:12px 0 2px;color:var(--mut)">UPSTREAM AREAS FEEDING THIS ONE</h3><ol>${ups}</ol>` : ""}
    <div class="sub" style="margin-top:10px">Rule-based indicator, not an official forecast.</div>`;
  $("#detail").hidden = false;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
