// SentinelTrace UI: drives the pipeline one stage at a time and renders the graph + table.
"use strict";

const STAGES = ["acquire", "normalise", "correlate", "attribute"];
const SOURCE_COLORS = { ShadowBazaar: "#e0b341", NullForum: "#6aa6ff", CryptVault: "#c77dff" };
const ACTOR_PALETTE = ["#ff8a3d", "#3ddc97", "#4cc9f0", "#f15bb5", "#9ef01a"];
const LONE_COLOR = "#5b6478";
const EDGE_COLORS = { hard: "#ff5d73", style: "#ffd166", infra: "#8a94a6" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = {
  completed: [],
  busy: false,
  nodes: new vis.DataSet(),
  edges: new vis.DataSet(),
  graph: { nodes: [], edges: [] },
  profiles: [],       // full attribution result
  results: [],        // current search result
  actorColors: {},
};

// ---- API ------------------------------------------------------------------

async function api(path, method = "GET") {
  const res = await fetch(path, { method });
  if (!res.ok) throw new Error(`${method} ${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

function searchParams() {
  const p = new URLSearchParams();
  if ($("q").value.trim()) p.set("q", $("q").value.trim());
  if ($("from").value) p.set("date_from", $("from").value);
  if ($("to").value) p.set("date_to", $("to").value);
  p.set("expand", $("expand").checked);
  return p.toString();
}

// ---- graph ----------------------------------------------------------------

const network = new vis.Network($("graph"), { nodes: state.nodes, edges: state.edges }, {
  nodes: {
    shape: "dot", size: 24, borderWidth: 2,
    font: { color: "#e6e9ef", size: 20, face: "system-ui", multi: "html" },
  },
  edges: {
    smooth: { type: "continuous" },
    font: { color: "#e6e9ef", size: 18, strokeWidth: 4, strokeColor: "#0b0f17", face: "system-ui" },
    selectionWidth: 2,
  },
  physics: {
    // Stronger springs + central gravity keep linked personas close and the graph compact.
    barnesHut: { gravitationalConstant: -4500, centralGravity: 0.3, springLength: 110, springConstant: 0.06, damping: 0.3, avoidOverlap: 0.6 },
    stabilization: { iterations: 150 },
  },
  interaction: { hover: true, tooltipDelay: 150 },
});

// Keep the whole graph in frame as it grows and settles.
function fitGraph() { network.fit({ animation: { duration: 600, easingFunction: "easeInOutQuad" } }); }
network.on("stabilized", fitGraph);

function edgeKind(e) {
  if (e.hard) return "hard";
  return e.kinds.includes("stylometry") ? "style" : "infra";
}

function edgeId(e) { return `${e.source}|${e.target}`; }

function visEdge(e, dimmed = false) {
  const kind = edgeKind(e);
  return {
    id: edgeId(e), from: e.source, to: e.target,
    label: String(e.confidence),
    width: 1 + e.confidence / 14,
    length: 260 - e.confidence * 1.6,
    dashes: kind === "style" ? [10, 7] : kind === "infra" ? [2, 5] : false,
    color: { color: EDGE_COLORS[kind], highlight: EDGE_COLORS[kind], hover: EDGE_COLORS[kind], opacity: dimmed ? 0.12 : 1 },
    title: e.reasons.join("\n"),
  };
}

function nodeLabel(n) {
  let label = `<b>${esc(n.handle)}</b>\n${esc(n.source)}`;
  if (n.actor && state.actorColors[n.actor]) label += `\n${esc(n.actor)}`;  // multi-persona actors only
  if (n.suggested_actor) label += `\n<i>alias? ${esc(n.suggested_actor)}</i>`;
  return label;
}

function visNode(n, { flash = false, dimmed = false } = {}) {
  let fill = SOURCE_COLORS[n.source] || LONE_COLOR;
  let border = fill;
  let borderDashes = false;
  if (n.actor) {  // after attribution: colour by actor
    fill = state.actorColors[n.actor] || LONE_COLOR;
    border = fill;
    if (n.suggested_actor) { border = state.actorColors[n.suggested_actor] || EDGE_COLORS.style; borderDashes = [4, 3]; }
  }
  if (flash) border = "#ffffff";
  return {
    id: n.id, label: nodeLabel(n),
    color: { background: fill, border, highlight: { background: fill, border: "#ffffff" }, hover: { background: fill, border: "#ffffff" } },
    borderWidth: flash ? 5 : n.suggested_actor ? 4 : 2,
    shapeProperties: { borderDashes },
    opacity: dimmed ? 0.2 : 1,
    title: `${n.handle} · ${n.source}`,
  };
}

function computeActorColors(nodes) {
  const counts = {};
  nodes.forEach((n) => { if (n.actor) counts[n.actor] = (counts[n.actor] || 0) + 1; });
  const multi = Object.keys(counts).filter((a) => counts[a] > 1).sort();
  state.actorColors = {};
  multi.forEach((a, i) => { state.actorColors[a] = ACTOR_PALETTE[i % ACTOR_PALETTE.length]; });
}

function renderGraphStatic() {
  // Rebuild the whole graph from state.graph (used on page load / after search).
  const visible = state.results.length ? new Set(state.results.map((p) => p.id)) : null;
  const filtering = visible && isFiltering();
  state.nodes.update(state.graph.nodes.map((n) => visNode(n, { dimmed: filtering && !visible.has(n.id) })));
  state.edges.update(state.graph.edges.map((e) =>
    visEdge(e, filtering && !(visible.has(e.source) && visible.has(e.target)))));
  $("graph-empty").hidden = state.graph.nodes.length > 0;
}

function isFiltering() {
  return Boolean($("q").value.trim() || $("from").value || $("to").value);
}

// ---- pipeline -------------------------------------------------------------

function setStageClass(stage, cls) {
  const li = document.querySelector(`#stages li[data-stage="${stage}"]`);
  li.classList.remove("running", "done");
  if (cls) li.classList.add(cls);
}

function logSummary(summary) {
  const log = $("log");
  if (log.querySelector(".muted")) log.innerHTML = "";
  const head = document.createElement("p");
  head.className = "head";
  head.textContent = `[${summary.stage}] ${summary.headline}`;
  log.appendChild(head);
  summary.details.forEach((d) => {
    const p = document.createElement("p");
    p.className = "detail" + (/alias|matches after cleaning|writing style/.test(d) ? " key" : "");
    p.textContent = d;
    log.appendChild(p);
  });
  log.scrollTop = log.scrollHeight;
}

async function runStage(stage) {
  setStageClass(stage, "running");
  await sleep(700);  // give the audience a beat to see which stage is running
  const { summary, status } = await api(`/api/pipeline/${stage}`, "POST");
  state.completed = status.completed;
  state.graph = await api("/api/graph");
  logSummary(summary);
  await animateStage(stage, summary);
  fitGraph();
  setStageClass(stage, "done");
}

async function animateStage(stage, summary) {
  if (stage === "acquire") {
    // Footprints appear one by one, coloured by source.
    for (const n of state.graph.nodes) {
      state.nodes.add(visNode(n));
      $("graph-empty").hidden = true;
      await sleep(60);
    }
  } else if (stage === "normalise") {
    // Flash the footprints whose identifiers only match after cleaning.
    const ids = new Set(summary.highlight || []);
    const flashed = state.graph.nodes.filter((n) => ids.has(n.id));
    for (let i = 0; i < 3; i++) {
      state.nodes.update(flashed.map((n) => visNode(n, { flash: true })));
      await sleep(250);
      state.nodes.update(flashed.map((n) => visNode(n)));
      await sleep(200);
    }
  } else if (stage === "correlate") {
    // Links are drawn strongest first, so hard evidence lands before the stylometry suggestion.
    for (const e of state.graph.edges) {
      state.edges.add(visEdge(e));
      await sleep(550);
    }
  } else if (stage === "attribute") {
    computeActorColors(state.graph.nodes);
    state.nodes.update(state.graph.nodes.map((n) => visNode(n)));
    await refreshResults();
  }
}

async function runAll() {
  if (state.busy) return;
  setBusy(true);
  try {
    await doReset();
    for (const stage of STAGES) await runStage(stage);
  } catch (err) { reportError(err); }
  setBusy(false);
}

async function stepOnce() {
  if (state.busy) return;
  const next = STAGES[state.completed.length];
  if (!next) return;
  setBusy(true);
  try { await runStage(next); } catch (err) { reportError(err); }
  setBusy(false);
}

async function doReset() {
  await api("/api/pipeline/reset", "POST");
  state.completed = [];
  state.graph = { nodes: [], edges: [] };
  state.profiles = [];
  state.results = [];
  state.actorColors = {};
  state.nodes.clear();
  state.edges.clear();
  STAGES.forEach((s) => setStageClass(s, null));
  $("log").innerHTML = '<p class="muted">Pipeline idle. Click <b>Run pipeline</b> to start.</p>';
  $("graph-empty").hidden = false;
  renderTable();
  showPanelIntro();
}

function setBusy(busy) {
  state.busy = busy;
  const finished = state.completed.length === STAGES.length;
  $("btn-run").disabled = busy;
  $("btn-step").disabled = busy || finished;
  $("btn-reset").disabled = busy;
  $("btn-csv").disabled = $("btn-json").disabled = busy || !finished;
}

function reportError(err) {
  console.error(err);
  const p = document.createElement("p");
  p.style.color = "var(--hard)";
  p.textContent = `Error: ${err.message}`;
  $("log").appendChild(p);
}

// ---- results table --------------------------------------------------------

async function refreshResults() {
  if (!state.completed.includes("attribute")) return;
  state.results = await api(`/api/actors?${searchParams()}`);
  if (!isFiltering()) state.profiles = state.results;
  renderTable();
  renderGraphStatic();
}

function actorTag(actor) {
  const color = state.actorColors[actor];
  const style = color ? `background:${color};color:#0b0f17` : `background:var(--surface-2);color:var(--muted)`;
  return `<span class="actor-tag" style="${style}">${esc(actor)}</span>`;
}

function short(v, n = 10) { return v ? (v.length > n + 2 ? v.slice(0, n) + "…" : v) : "–"; }

function renderTable() {
  const tbody = $("rows");
  if (!state.completed.includes("attribute")) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted center">Run the pipeline to build actor profiles.</td></tr>';
    return;
  }
  if (!state.results.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted center">No matches.</td></tr>';
    return;
  }
  tbody.innerHTML = state.results.map((p) => {
    const conf = p.confidence ?? 0;
    const color = p.top_link ? EDGE_COLORS[p.top_link.hard ? "hard" : /writing style/.test(p.top_link.reason) ? "style" : "infra"] : "transparent";
    return `<tr data-id="${esc(p.id)}" class="${isFiltering() && !p.direct_match ? "dim" : ""}">
      <td>${actorTag(p.actor)}${p.suggested_actor ? `<span class="alias-tag">⚑ possible alias of ${esc(p.suggested_actor)}</span>` : ""}</td>
      <td><b>${esc(p.handle)}</b></td>
      <td>${esc(p.source)}</td>
      <td class="ids">PGP ${esc(short(p.pgp_fingerprint))}<br>BTC ${esc(short(p.btc_wallet, 12))}</td>
      <td>${p.confidence == null ? '<span class="muted">–</span>' :
        `<div class="conf"><div class="bar"><i style="width:${conf}%;background:${color}"></i></div><b>${conf}</b></div>`}</td>
      <td>${p.top_link ? `→ ${esc(p.top_link.handle)}<br><span class="muted">${esc(p.top_link.reason)}</span>` : '<span class="muted">no links</span>'}</td>
      <td>${esc(p.last_seen)}</td>
    </tr>`;
  }).join("");
}

// ---- evidence panel -------------------------------------------------------

function showPanelIntro() {
  $("panel").innerHTML = '<h2>Evidence</h2><p class="muted">Click a node or a link in the graph, or a row in the table.</p>';
}

function profileById(id) {
  return state.profiles.find((p) => p.id === id);
}

function showNode(id) {
  const p = profileById(id);
  const n = state.graph.nodes.find((x) => x.id === id);
  if (!n) return;
  if (!p) {  // before attribution only the basics are known
    $("panel").innerHTML = `<h2>Footprint</h2><h3>${esc(n.handle)}</h3><p class="muted">${esc(n.source)}</p>
      <p class="note">Run the remaining pipeline stages to see identifiers and links.</p>`;
    return;
  }
  $("panel").innerHTML = `
    <h2>Footprint</h2>
    <h3>${esc(p.handle)}</h3>
    <div>${actorTag(p.actor)} ${p.suggested_actor ? `<span class="alias-tag" style="display:inline">⚑ possible alias of ${esc(p.suggested_actor)}</span>` : ""}</div>
    <dl>
      <dt>Source</dt><dd>${esc(p.source)}</dd>
      <dt>PGP</dt><dd class="mono">${esc(p.pgp_fingerprint || "–")}</dd>
      <dt>Wallet</dt><dd class="mono">${esc(p.btc_wallet || "–")}</dd>
      <dt>SSL CN</dt><dd class="mono">${esc(p.ssl_cert_cn || "–")}</dd>
      <dt>Banner</dt><dd class="mono">${esc(p.server_banner || "–")}</dd>
      <dt>Last seen</dt><dd>${esc(p.last_seen)}</dd>
    </dl>
    <h2>Writing sample</h2>
    <div class="sample">${esc(p.writing_sample)}</div>
    <h2>Links (${p.links.length})</h2>
    <ul class="links">${p.links.map((l) =>
      `<li data-edge="${esc([p.id, l.id].sort().join("|"))}"><b>${l.confidence}</b> → ${esc(l.handle)} <span class="muted">· ${esc(l.reason)}</span></li>`
    ).join("") || '<li class="muted">none</li>'}</ul>`;
}

// Words shared by both writing samples, excluding very common ones, for highlighting.
const STOP = new Set("a an the and or of to in on for is are be it i me my you your if with at by this that as".split(" "));
function tokenKey(t) { return t.toLowerCase().replace(/^[^\w!~]+|[^\w!~]+$/g, ""); }
function highlightShared(text, other) {
  const otherKeys = new Set(other.split(/\s+/).map(tokenKey).filter((k) => k && !STOP.has(k)));
  return text.split(/(\s+)/).map((t) => {
    const k = tokenKey(t);
    return k && !STOP.has(k) && otherKeys.has(k) ? `<mark>${esc(t)}</mark>` : esc(t);
  }).join("");
}

function showEdge(id) {
  const e = state.graph.edges.find((x) => edgeId(x) === id);
  if (!e) return;
  const a = state.graph.nodes.find((n) => n.id === e.source);
  const b = state.graph.nodes.find((n) => n.id === e.target);
  const pa = profileById(a.id), pb = profileById(b.id);
  const kind = edgeKind(e);
  const title = { hard: "Hard evidence", style: "Stylometry suggestion", infra: "Infrastructure overlap" }[kind];
  let samples = "";
  if (e.kinds.includes("stylometry") && pa && pb) {
    samples = `<h2>Writing samples (shared tokens highlighted)</h2>
      <div class="sample"><b>${esc(pa.handle)}:</b> ${highlightShared(pa.writing_sample, pb.writing_sample)}</div>
      <div class="sample"><b>${esc(pb.handle)}:</b> ${highlightShared(pb.writing_sample, pa.writing_sample)}</div>`;
  }
  $("panel").innerHTML = `
    <h2>${title}</h2>
    <h3>${esc(a.handle)} ↔ ${esc(b.handle)}</h3>
    <p class="muted">${esc(a.source)} ↔ ${esc(b.source)}</p>
    <div class="big" style="color:${EDGE_COLORS[kind]}">${e.confidence}<small style="font-size:14px;color:var(--muted)"> / 100</small></div>
    <h2 style="margin-top:12px">Why</h2>
    ${e.reasons.map((r) => `<div class="reason">${esc(r)}</div>`).join("")}
    ${samples}
    <p class="note">${kind === "style"
      ? "No shared key or wallet. This link comes from writing style alone (character n-gram TF-IDF, cosine similarity). Treat it as a lead for an analyst to review, not as proof."
      : kind === "hard"
        ? "Signals are combined with noisy-OR: 1 − Π(1 − cᵢ). Independent evidence adds up, but confidence never reaches 100: attribution is never certain."
        : "Infrastructure overlap on its own is weak evidence. Stock server banners are common."}</p>`;
}

// ---- wiring ---------------------------------------------------------------

network.on("click", (params) => {
  if (params.nodes.length) showNode(params.nodes[0]);
  else if (params.edges.length) showEdge(params.edges[0]);
});

$("panel").addEventListener("click", (ev) => {
  const li = ev.target.closest("li[data-edge]");
  if (li) { network.selectEdges([li.dataset.edge]); showEdge(li.dataset.edge); }
});

$("rows").addEventListener("click", (ev) => {
  const tr = ev.target.closest("tr[data-id]");
  if (!tr) return;
  network.selectNodes([tr.dataset.id]);
  network.focus(tr.dataset.id, { scale: 1.1, animation: { duration: 500 } });
  showNode(tr.dataset.id);
});

let searchTimer;
function onSearchChange() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => refreshResults().catch(reportError), 200);
}
["q", "from", "to"].forEach((id) => $(id).addEventListener("input", onSearchChange));
$("expand").addEventListener("change", onSearchChange);

$("btn-run").addEventListener("click", runAll);
$("btn-step").addEventListener("click", stepOnce);
$("btn-reset").addEventListener("click", async () => {
  if (state.busy) return;
  setBusy(true);
  try { await doReset(); } catch (err) { reportError(err); }
  setBusy(false);
});
$("btn-csv").addEventListener("click", () => { window.location = `/api/export.csv?${searchParams()}`; });
$("btn-json").addEventListener("click", () => { window.location = `/api/export.json?${searchParams()}`; });

// On page load, restore whatever the server has already run (e.g. after a browser refresh).
(async function init() {
  try {
    const status = await api("/api/pipeline");
    state.completed = status.completed;
    STAGES.forEach((s) => setStageClass(s, state.completed.includes(s) ? "done" : null));
    if (state.completed.length) {
      state.graph = await api("/api/graph");
      if (state.completed.includes("attribute")) computeActorColors(state.graph.nodes);
      state.nodes.add(state.graph.nodes.map((n) => visNode(n)));
      state.edges.add(state.graph.edges.map((e) => visEdge(e)));
      $("graph-empty").hidden = true;
      $("log").innerHTML = `<p class="muted">Restored: ${state.completed.join(" → ")} complete.</p>`;
      await refreshResults();
    }
  } catch (err) { reportError(err); }
  setBusy(false);
})();
