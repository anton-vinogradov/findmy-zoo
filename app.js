/* findmy-zoo — карта треков за последние сутки.
   Тянет /api/points, рисует по сущности: полилиния трека + маркер последней точки. */

const KIND_LABEL = { tag: "Метки", device: "Устройства", person: "Люди" };
const KIND_FALLBACK = { tag: "#f59e0b", device: "#3b82f6", person: "#10b981" };

const map = L.map("map", { zoomControl: true }).setView([55.75, 37.62], 3);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

let colors = {};
const off = new Set(JSON.parse(localStorage.getItem("fz-off") || "[]")); // скрытые типы
const layers = {};   // entity_id -> {track, marker, kind}
let firstFit = true;

function colorFor(kind) { return (colors[kind] || KIND_FALLBACK[kind] || "#9ca3af"); }

function ago(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return s + " с назад";
  if (s < 3600) return Math.floor(s / 60) + " мин назад";
  if (s < 86400) return Math.floor(s / 3600) + " ч назад";
  return Math.floor(s / 86400) + " дн назад";
}

function battStr(b) { return (b === null || b === undefined) ? "" : Math.round(b) + "%"; }

function render(data) {
  colors = data.colors || {};
  const names = data.names || {};
  const seen = new Set();
  const kinds = new Set();
  const bounds = [];

  for (const e of data.entities) {
    kinds.add(e.kind);
    const id = e.id;
    seen.add(id);
    const name = names[id] || e.name || id;
    const pts = e.points.filter((p) => p.lat != null && p.lon != null);
    if (!pts.length) continue;
    const last = pts[pts.length - 1];
    const col = colorFor(e.kind);
    const latlngs = pts.map((p) => [p.lat, p.lon]);
    const hidden = off.has(e.kind);

    if (!layers[id]) layers[id] = { kind: e.kind };
    const L0 = layers[id];
    L0.kind = e.kind;
    L0.name = name;
    L0.last = last;

    // трек
    if (L0.track) L0.track.setLatLngs(latlngs).setStyle({ color: col });
    else L0.track = L.polyline(latlngs, { color: col, weight: 3, opacity: 0.65 });
    // маркер последней точки
    const popup = `<b>${name}</b><br>${KIND_LABEL[e.kind] || e.kind}` +
      `<br>${ago(last.ts)}` +
      (last.batt != null ? `<br>батарея: ${battStr(last.batt)}` : "") +
      (last.acc != null ? `<br>точность: ±${Math.round(last.acc)} м` : "") +
      `<br>точек за сутки: ${pts.length}`;
    if (L0.marker) L0.marker.setLatLng(last).setStyle({ color: col, fillColor: col });
    else L0.marker = L.circleMarker(last, { radius: 7, color: col, fillColor: col, fillOpacity: 0.9, weight: 2 });
    L0.marker.bindPopup(popup);
    L0.marker.bindTooltip(name, { permanent: true, direction: "right", className: "pin-label", offset: [8, 0] });

    // видимость по фильтру
    for (const key of ["track", "marker"]) {
      if (hidden) map.removeLayer(L0[key]);
      else if (!map.hasLayer(L0[key])) L0[key].addTo(map);
    }
    if (!hidden) latlngs.forEach((ll) => bounds.push(ll));
  }

  // удалить исчезнувшие
  for (const id of Object.keys(layers)) {
    if (!seen.has(id)) {
      ["track", "marker"].forEach((k) => layers[id][k] && map.removeLayer(layers[id][k]));
      delete layers[id];
    }
  }

  renderFilters([...kinds].sort());
  renderList(names);
  document.getElementById("age").textContent =
    "обновлено " + ago(data.generated) + " · окно " + data.retentionH + " ч";
  document.getElementById("foot").textContent =
    `${data.entities.length} сущностей · трек за ${data.retentionH} ч`;

  if (firstFit && bounds.length) { map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 }); firstFit = false; }
}

function renderFilters(kinds) {
  const box = document.getElementById("filters");
  box.innerHTML = "";
  for (const k of kinds) {
    const el = document.createElement("span");
    el.className = "chip " + (off.has(k) ? "off" : "on");
    el.innerHTML = `<span class="sw" style="background:${colorFor(k)}"></span>${KIND_LABEL[k] || k}`;
    el.onclick = () => {
      off.has(k) ? off.delete(k) : off.add(k);
      localStorage.setItem("fz-off", JSON.stringify([...off]));
      load();
    };
    box.appendChild(el);
  }
}

function renderList(names) {
  const ul = document.getElementById("list");
  ul.innerHTML = "";
  const rows = Object.entries(layers)
    .filter(([, v]) => v.last && !off.has(v.kind))
    .sort((a, b) => b[1].last.ts - a[1].last.ts);
  for (const [id, v] of rows) {
    const li = document.createElement("li");
    li.innerHTML =
      `<span class="sw" style="background:${colorFor(v.kind)}"></span>` +
      `<span class="meta"><div class="nm">${v.name}</div>` +
      `<div class="sub">${ago(v.last.ts)}</div></span>` +
      `<span class="batt">${battStr(v.last.batt)}</span>`;
    li.onclick = () => { map.setView(v.last, 15); v.marker.openPopup(); };
    ul.appendChild(li);
  }
}

async function load() {
  try {
    const r = await fetch("/api/points", { cache: "no-store" });
    render(await r.json());
  } catch (e) {
    document.getElementById("age").textContent = "нет связи с hub";
  }
}

load();
setInterval(load, 30000);
