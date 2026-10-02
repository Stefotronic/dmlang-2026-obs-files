"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let config = null;

async function api(url, body) {
  const opts = body === undefined ? { cache: "no-store" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function update(patch) {
  await api("/api/display", patch);
  await refresh();
}

function setInput(id, prop, value) {
  const el = $(id);
  if (document.activeElement === el) return;
  el[prop] = value;
}

async function refresh() {
  try {
    const [status, disp, classes] = await Promise.all([api("/api/status"), api("/api/display"), api("/api/classes")]);
    config = disp.config;

    const m = status.meos;
    const fresh = m.connected && (m.age ?? 999) < 15;
    $("conn").innerHTML = fresh
      ? `<span class="ok">verbunden</span> (vor ${m.age}s aktualisiert)`
      : `<span class="bad">keine aktuellen Daten</span>`;
    $("conn").title = m.url;
    const c = status.competition;
    $("cmp").textContent = c.name
      ? `${c.name} · ${c.date} · Nullzeit ${c.zerotime} · ${status.counts.competitors} Läufer, ${status.counts.teams} Teams`
      : `Quelle: ${m.url}`;
    $("err").textContent = m.last_error ? `Letzter Fehler: ${m.last_error}` : "";

    const cur = disp.current.view;
    const mode = config.mode === "fixed" ? "fixiert" : "Rotation";
    $("now").textContent = cur.class_name
      ? `${cur.class_name} (Seite ${cur.page}/${cur.pages}) – ${mode}`
      : `– (${mode})`;
    $("btn-auto").classList.toggle("active", config.mode === "auto");

    setInput("page-seconds", "value", config.page_seconds);
    setInput("ticker-count", "value", config.ticker_count);
    setInput("show-ticker", "checked", config.show_ticker);
    setInput("hide-empty", "checked", config.hide_empty);

    $("classes").innerHTML = classes.map((k) => {
      const inRot = config.rotate_classes.includes(k.id);
      const fixed = config.mode === "fixed" && config.fixed_class === k.id;
      return `<tr>
        <td><input type="checkbox" data-rot="${k.id}" ${inRot ? "checked" : ""}></td>
        <td><b>${esc(k.name)}</b></td>
        <td>${k.type === "team" ? "Staffel/Team" : "Einzel"}</td>
        <td>${k.finished} / ${k.running} / ${k.entries}</td>
        <td><button data-fix="${k.id}" class="${fixed ? "active" : ""}">Anzeigen</button></td>
      </tr>`;
    }).join("");
  } catch (e) {
    $("conn").innerHTML = `<span class="bad">Python-Server nicht erreichbar</span>`;
  }
}

$("classes").addEventListener("click", (ev) => {
  const fix = ev.target.dataset.fix;
  if (fix) update({ mode: "fixed", fixed_class: Number(fix) });
  const rot = ev.target.dataset.rot;
  if (rot) {
    const id = Number(rot);
    const set = new Set(config.rotate_classes);
    if (ev.target.checked) set.add(id); else set.delete(id);
    update({ rotate_classes: [...set] });
  }
});

$("btn-auto").addEventListener("click", () => update({ mode: "auto" }));
$("btn-skip").addEventListener("click", async () => {
  if (config.mode !== "auto") await api("/api/display", { mode: "auto" });
  await api("/api/display/skip", {});
  refresh();
});
$("page-seconds").addEventListener("change", (e) => update({ page_seconds: Number(e.target.value) }));
$("ticker-count").addEventListener("change", (e) => update({ ticker_count: Number(e.target.value) }));
$("show-ticker").addEventListener("change", (e) => update({ show_ticker: e.target.checked }));
$("hide-empty").addEventListener("change", (e) => update({ hide_empty: e.target.checked }));

$("overlay-url").textContent = `${location.origin}/overlay`;
refresh();
setInterval(refresh, 2000);
