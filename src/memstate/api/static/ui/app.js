const LS_KEY = "memstate_api_key";

/* ── Helpers ── */

function formatApiError(data) {
  const parts = [];
  if (data.detail != null) {
    let d =
      typeof data.detail === "object" ? JSON.stringify(data.detail) : String(data.detail);
    if (d.length > 2000) d = d.slice(0, 2000) + "…";
    parts.push(d);
  }
  if (data.hint) parts.push(String(data.hint));
  return parts.join(" — ") || "Request failed";
}

function headers() {
  const h = { "Content-Type": "application/json" };
  const k = localStorage.getItem(LS_KEY);
  if (k) h["X-API-Key"] = k;
  return h;
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { ...headers(), ...opts.headers },
  });
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }
  if (!r.ok) {
    throw new Error(formatApiError(data) || r.statusText || String(r.status));
  }
  return data;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

/* ── Toast ── */

function toast(message, type = "success") {
  const c = document.getElementById("toast-container");
  if (!c) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const icon =
    type === "error"
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
  el.innerHTML = icon + `<span>${escapeHtml(message)}</span>`;
  c.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove());
  }, 3500);
}

/* ── Status helper ── */

function setStatus(msg, isError = false, opts = {}) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("err", isError);
  const skipToast = opts.skipToast || /^loading/i.test(msg);
  if (!isError && msg && !skipToast) toast(msg);
  if (isError && msg) toast(msg, "error");
}

/* ── Backend banner ── */

async function checkBackendBanner() {
  const banner = document.getElementById("backend-banner");
  if (!banner) return;
  try {
    const r = await fetch("/health/graph");
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      /* ignore */
    }
    if (r.ok) {
      banner.hidden = true;
      banner.textContent = "";
      return;
    }
    banner.hidden = false;
    const msg = [data.error, data.hint].filter(Boolean).join(" ");
    banner.textContent =
      msg || "Embedded graph (Kuzu) unavailable — check MEMSTATE_KUZU_PATH.";
  } catch {
    banner.hidden = false;
    banner.textContent = "Could not reach /health/graph — is the API running?";
  }
}

/* ── Collapsible sections ── */

function wireCollapsible() {
  document.querySelectorAll(".section-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = btn.nextElementSibling;
      const wasOpen = body.classList.contains("open");
      btn.classList.toggle("active", !wasOpen);
      body.classList.toggle("open", !wasOpen);
    });
  });
}

/* ── Graph (vis-network: layout once, then drag freely — physics off after stabilize) ── */

const LABEL_MAX = 28;

const TITLE_FONT_SIZE = 11;
const TITLE_LINE_HEIGHT = 12;
const TITLE_MAX_LINES = 3;
const TITLE_CHARS_PER_LINE = 12;
const SALIENCE_FONT_SIZE = 10;

function shortLabel(text) {
  const s = String(text || "").trim();
  if (s.length <= LABEL_MAX) return s || "—";
  return s.slice(0, LABEL_MAX - 1) + "…";
}

/** Word-wrap title for inside-node display (SVG has no native wrap). */
function wrapTitleLines(text, maxCharsPerLine, maxLines) {
  const t = String(text || "").trim() || "—";
  const words = t.split(/\s+/).filter(Boolean);
  if (!words.length) return ["—"];
  const lines = [];
  let line = "";
  for (const w of words) {
    if (lines.length >= maxLines) break;
    const candidate = line ? `${line} ${w}` : w;
    if (candidate.length <= maxCharsPerLine) {
      line = candidate;
    } else {
      if (line) {
        lines.push(line);
        line = "";
      }
      if (w.length > maxCharsPerLine) {
        lines.push(`${w.slice(0, Math.max(1, maxCharsPerLine - 1))}…`);
        if (lines.length >= maxLines) break;
      } else {
        line = w;
      }
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (!lines.length) lines.push(t.slice(0, maxCharsPerLine));
  if (lines.length > maxLines) return lines.slice(0, maxLines);
  return lines;
}

function parseSalience(n) {
  const s = n.salience;
  if (typeof s === "number" && Number.isFinite(s)) return s;
  const v = parseFloat(s);
  return Number.isFinite(v) ? v : 0;
}

function formatSalience(s) {
  if (!Number.isFinite(s)) return "—";
  if (Math.abs(s - Math.round(s)) < 1e-6) return String(Math.round(s));
  return s.toFixed(2).replace(/\.?0+$/, "");
}

/** Map salience to fill opacity: low salience → more transparent. */
function salienceToFillOpacity(salience, minS, maxS) {
  const lo = 0.32;
  const hi = 1;
  if (maxS <= minS) return (lo + hi) / 2;
  const t = (salience - minS) / (maxS - minS);
  return lo + (hi - lo) * Math.max(0, Math.min(1, t));
}

/** Undirected connected components — fallback tint when API omits ``community``. */
function computeClusters(nodes, links) {
  const adj = new Map();
  for (const n of nodes) adj.set(n.id, []);
  for (const l of links) {
    const a = typeof l.source === "string" ? l.source : l.source.id;
    const b = typeof l.target === "string" ? l.target : l.target.id;
    if (!adj.has(a)) adj.set(a, []);
    if (!adj.has(b)) adj.set(b, []);
    adj.get(a).push(b);
    adj.get(b).push(a);
  }
  const clusterOf = new Map();
  let cid = 0;
  const visited = new Set();
  for (const n of nodes) {
    if (visited.has(n.id)) continue;
    const stack = [n.id];
    while (stack.length) {
      const id = stack.pop();
      if (visited.has(id)) continue;
      visited.add(id);
      clusterOf.set(id, cid);
      for (const nb of adj.get(id) || []) {
        if (!visited.has(nb)) stack.push(nb);
      }
    }
    cid++;
  }
  return { clusterOf, clusterCount: cid };
}

/**
 * Deterministic (x, y) per topic so each community sits in its own region (easier to scan large graphs).
 * Uses API `community` when present; otherwise connected-component ids from `computeClusters`.
 */
function computeCommunityClusterPositions(nodes, links) {
  const { clusterOf } = computeClusters(nodes, links);
  /** @type {Map<number, typeof nodes>} */
  const byComm = new Map();
  for (const n of nodes) {
    const cid =
      n.community != null && Number.isFinite(Number(n.community))
        ? Number(n.community)
        : clusterOf.get(n.id) ?? 0;
    if (!byComm.has(cid)) byComm.set(cid, []);
    byComm.get(cid).push(n);
  }
  const commIds = [...byComm.keys()].sort((a, b) => a - b);
  const nc = Math.max(commIds.length, 1);
  const nTopics = nodes.length;
  /** @type {Array<{ cx: number, cy: number }>} */
  const centers = [];
  if (nc <= 12) {
    const R = 240 + Math.sqrt(nTopics) * 34;
    for (let i = 0; i < nc; i++) {
      const theta = (2 * Math.PI * i) / nc;
      centers.push({ cx: R * Math.cos(theta), cy: R * Math.sin(theta) });
    }
  } else {
    const cols = Math.ceil(Math.sqrt(nc));
    const rows = Math.ceil(nc / cols);
    const cell = 260 + Math.min(70, nTopics / Math.max(nc, 1));
    for (let i = 0; i < nc; i++) {
      const row = Math.floor(i / cols);
      const col = i % cols;
      centers.push({
        cx: (col - (cols - 1) / 2) * cell,
        cy: (row - (rows - 1) / 2) * cell,
      });
    }
  }

  /** @type {Map<string, { x: number, y: number }>} */
  const positions = new Map();
  commIds.forEach((cid, idx) => {
    const { cx, cy } = centers[idx];
    const members = byComm.get(cid);
    const nm = members.length;
    const rLocal = 32 + Math.sqrt(nm) * 28;
    members.forEach((node, j) => {
      const phi = nm <= 1 ? 0 : (2 * Math.PI * j) / nm + idx * 0.11;
      let h = 0;
      for (let k = 0; k < node.id.length; k++) h = (h * 31 + node.id.charCodeAt(k)) | 0;
      const jx = ((h >>> 0) % 19) - 9;
      const jy = (((h >>> 8) % 23) - 11) * 0.9;
      positions.set(node.id, {
        x: cx + rLocal * Math.cos(phi) + jx * 2.8,
        y: cy + rLocal * Math.sin(phi) + jy * 2.2,
      });
    });
  });
  return positions;
}

/**
 * @param {Record<string, unknown>} apiNode
 * @param {number | null} community
 */
function buildTopicTooltipPayload(apiNode, community) {
  const head =
    (apiNode.title && String(apiNode.title).trim()) ||
    String(apiNode.label || "").trim() ||
    String(apiNode.id || "").slice(0, 8);
  const fields = (apiNode.fields || []).map((f) => ({
    name: String(f.name || ""),
    type: String(f.field_type || "—"),
    ref: f.ref_topic_id ? String(f.ref_topic_id).slice(0, 10) + "…" : null,
  }));
  return {
    kind: "topic",
    head,
    topicKind: apiNode.topic_kind || "—",
    salience: apiNode.salience,
    fieldCount: (apiNode.fields || []).length,
    community,
    archived: !!apiNode.archived,
    fields,
    idShort: String(apiNode.id || "").slice(0, 8) + "…",
  };
}

function renderTopicTooltipHtml(p) {
  const parts = [];
  parts.push(`<div class="graph-tooltip-head">${escapeHtml(p.head)}</div>`);
  parts.push('<dl class="graph-tooltip-meta">');
  parts.push(`<dt>Kind</dt><dd>${escapeHtml(String(p.topicKind))}</dd>`);
  parts.push(`<dt>Salience</dt><dd>${escapeHtml(String(p.salience ?? "—"))}</dd>`);
  parts.push(`<dt>Fields</dt><dd>${p.fieldCount}</dd>`);
  if (p.archived) parts.push("<dt>Status</dt><dd>archived</dd>");
  if (p.community != null && Number.isFinite(Number(p.community))) {
    parts.push(`<dt>Community</dt><dd>${escapeHtml(String(p.community))}</dd>`);
  }
  parts.push(`<dt>ID</dt><dd>${escapeHtml(p.idShort)}</dd>`);
  parts.push("</dl>");
  if (p.fields && p.fields.length) {
    parts.push('<ul class="graph-tooltip-fields">');
    const max = 12;
    for (let i = 0; i < Math.min(p.fields.length, max); i++) {
      const f = p.fields[i];
      const ref = f.ref
        ? ` <span style="opacity:.88">→ ${escapeHtml(f.ref)}</span>`
        : "";
      parts.push(
        `<li><strong>${escapeHtml(f.name)}</strong> (${escapeHtml(f.type)})${ref}</li>`
      );
    }
    if (p.fields.length > max) {
      parts.push(
        `<li style="border-left-color:var(--muted);opacity:.88">… +${p.fields.length - max} more</li>`
      );
    }
    parts.push("</ul>");
  }
  return parts.join("");
}

function hideGraphTooltip() {
  const tip = document.getElementById("graph-tooltip");
  if (tip) {
    tip.hidden = true;
    tip.innerHTML = "";
  }
}

/**
 * @param {HTMLElement} tipEl
 * @param {Record<string, unknown>} params
 */
function positionGraphTooltip(tipEl, params) {
  const wrap = graphView.container?.closest(".graph-wrap");
  if (!wrap || !tipEl) return;
  const r = wrap.getBoundingClientRect();
  const e = params.event;
  let x = 16;
  let y = 16;
  if (e && typeof e.clientX === "number") {
    x = e.clientX - r.left + 12;
    y = e.clientY - r.top + 12;
  } else {
    const p = params.pointer?.DOM;
    if (p && graphView.container) {
      const nr = graphView.container.getBoundingClientRect();
      x = nr.left - r.left + p.x + 12;
      y = nr.top - r.top + p.y + 12;
    }
  }
  tipEl.style.left = `${x}px`;
  tipEl.style.top = `${y}px`;
  const pad = 8;
  const tw = tipEl.offsetWidth;
  const th = tipEl.offsetHeight;
  if (x + tw > wrap.clientWidth - pad) x = Math.max(pad, wrap.clientWidth - tw - pad);
  if (y + th > wrap.clientHeight - pad) y = Math.max(pad, wrap.clientHeight - th - pad);
  tipEl.style.left = `${x}px`;
  tipEl.style.top = `${y}px`;
}

function wireGraphTooltip(net) {
  const tip = document.getElementById("graph-tooltip");
  if (!tip) return;

  net.on("hoverNode", (params) => {
    const id = params.node;
    const payload = graphView.nodeTooltipPayload?.get(id);
    const html = payload ? renderTopicTooltipHtml(payload) : "";
    if (!html) return;
    tip.innerHTML = html;
    tip.hidden = false;
    requestAnimationFrame(() => positionGraphTooltip(tip, params));
  });

  net.on("blurNode", () => hideGraphTooltip());
  net.on("dragStart", () => hideGraphTooltip());
  net.on("zoom", () => hideGraphTooltip());
}

function buildGraphData(data) {
  const rawList = data.nodes || [];
  const saliences = rawList.map((n) => parseSalience(n));
  const minS = saliences.length ? Math.min(...saliences) : 0;
  const maxS = saliences.length ? Math.max(...saliences) : 1;

  const nodes = rawList.map((n, i) => {
    const raw =
      (n.title && String(n.title).trim()) || n.label || n.id.slice(0, 8);
    const salience = saliences[i];
    const comm =
      n.community != null && Number.isFinite(Number(n.community)) ? Number(n.community) : null;
    return {
      id: String(n.id ?? "").trim(),
      labelLines: wrapTitleLines(raw, TITLE_CHARS_PER_LINE, TITLE_MAX_LINES),
      salience,
      salienceLabel: formatSalience(salience),
      fillOpacity: salienceToFillOpacity(salience, minS, maxS),
      tooltipPayload: buildTopicTooltipPayload(n, comm),
      archived: !!n.archived,
      community: comm,
    };
  });
  const links = [];
  const seen = new Set();
  for (const e of data.edges || []) {
    const key = `${e.from}|${e.to}|${e.kind}|${e.edge_type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const kind = (e.kind || "").trim();
    links.push({
      source: String(e.from ?? "").trim(),
      target: String(e.to ?? "").trim(),
      label: kind ? shortLabel(kind) : "",
      isRef: e.edge_type === "field_ref",
    });
  }
  return { nodes, links };
}

const graphView = {
  container: null,
  network: null,
  resizeObserver: null,
  layoutFallbackTimer: null,
  /** @type {string[] | null} */
  nodeIds: null,
  /** @type {Array<{ source: string, target: string }> | null} */
  lastRawLinks: null,
  /** @type {{ nodes: any, edges: any } | null} */
  visDataSets: null,
  /** @type {string | null} */
  expandedId: null,
  /** @type {Record<string, { x: number, y: number }> | null} */
  savedPositions: null,
  /** @type {Record<string, unknown> | null} */
  compactNodeBackup: null,
  /** @type {string | null} */
  expandPending: null,
  /** @type {Record<string, unknown> | null} */
  wizardTopicPayload: null,
  /** @type {Map<string, Record<string, unknown>> | null} */
  nodeTooltipPayload: null,
};

/**
 * @param {Record<string, unknown>} t
 */
function renderTopicWizardBody(t) {
  const parts = [];
  parts.push('<section class="topic-wizard-section"><h3 class="topic-wizard-h3">Topic</h3><dl class="topic-wizard-dl">');
  const meta = [
    ["ID", t.id],
    ["Title", t.title],
    ["Summary", t.summary],
    ["Kind", t.topic_kind],
    ["Salience", t.salience],
    ["Failed salience", t.failed_salience],
    ["Archived", t.archived],
    ["Created", t.created_at],
    ["Updated", t.updated_at],
  ];
  for (const [k, v] of meta) {
    if (v === undefined || v === null || v === "") continue;
    const disp = typeof v === "object" ? JSON.stringify(v) : String(v);
    parts.push(`<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(disp)}</dd>`);
  }
  parts.push("</dl></section>");

  const fields = t.fields && typeof t.fields === "object" ? t.fields : {};
  const names = Object.keys(fields).sort();
  if (names.length) {
    parts.push('<section class="topic-wizard-section"><h3 class="topic-wizard-h3">Fields</h3>');
    for (const name of names) {
      const f = fields[name];
      if (!f || typeof f !== "object") continue;
      parts.push(`<div class="topic-wizard-field-card"><h4 class="topic-wizard-h4">${escapeHtml(name)}</h4>`);
      parts.push('<dl class="topic-wizard-dl topic-wizard-field-meta">');
      parts.push(`<dt>Type</dt><dd>${escapeHtml(String(f.field_type ?? "—"))}</dd>`);
      if (f.ref_topic_id) {
        parts.push(`<dt>Ref topic</dt><dd>${escapeHtml(String(f.ref_topic_id))}</dd>`);
      }
      parts.push("</dl>");
      const hist = Array.isArray(f.history) ? f.history : [];
      if (hist.length) {
        parts.push('<div class="topic-wizard-history"><div class="topic-wizard-history-label">History</div>');
        for (let i = 0; i < hist.length; i++) {
          const e = hist[i];
          const when =
            e && typeof e === "object" && e.valid_from != null
              ? String(e.valid_from)
              : `Entry ${i + 1}`;
          const val = e && typeof e === "object" ? e.value : e;
          const valStr =
            typeof val === "object" && val !== null ? JSON.stringify(val, null, 2) : String(val ?? "—");
          parts.push(
            `<div class="topic-wizard-hist-row"><span class="topic-wizard-hist-time">${escapeHtml(when)}</span><pre class="topic-wizard-hist-val">${escapeHtml(valStr)}</pre></div>`
          );
        }
        parts.push("</div>");
      }
      parts.push("</div>");
    }
    parts.push("</section>");
  }

  parts.push(
    '<section class="topic-wizard-section topic-wizard-section-raw"><h3 class="topic-wizard-h3">Raw JSON</h3><pre class="topic-wizard-pre">'
  );
  parts.push(escapeHtml(JSON.stringify(t, null, 2)));
  parts.push("</pre></section>");
  return parts.join("");
}

/**
 * @param {Record<string, unknown>} t
 */
function showTopicWizard(t) {
  graphView.wizardTopicPayload = t;
  const root = document.getElementById("topic-wizard");
  const titleEl = document.getElementById("topic-wizard-title");
  const body = document.getElementById("topic-wizard-body");
  if (!root || !titleEl || !body) return;
  const title = (t.title && String(t.title).trim()) || String(t.id || "Topic");
  titleEl.textContent = title;
  body.innerHTML = renderTopicWizardBody(t);
  root.hidden = false;
  document.body.classList.add("topic-wizard-open");
}

function hideTopicWizard() {
  const root = document.getElementById("topic-wizard");
  const body = document.getElementById("topic-wizard-body");
  if (body) body.innerHTML = "";
  graphView.wizardTopicPayload = null;
  if (root) root.hidden = true;
  document.body.classList.remove("topic-wizard-open");
}

function collapseGraphExpand({ restorePositions = true } = {}) {
  const ds = graphView.visDataSets;
  const net = graphView.network;
  const id = graphView.expandedId;
  if (!id) return;

  hideTopicWizard();

  if (graphView.compactNodeBackup && ds) {
    ds.nodes.update(graphView.compactNodeBackup);
  }
  if (restorePositions && graphView.savedPositions && net) {
    for (const nid of Object.keys(graphView.savedPositions)) {
      const p = graphView.savedPositions[nid];
      net.moveNode(nid, p.x, p.y);
    }
  }
  graphView.expandedId = null;
  graphView.savedPositions = null;
  graphView.compactNodeBackup = null;
  graphView.expandPending = null;

  if (net && typeof net.unselectAll === "function") net.unselectAll();
  updateGraphDeleteTopicButton();
}

/**
 * @param {string} topicId
 */
async function expandGraphNode(topicId) {
  const net = graphView.network;
  const ds = graphView.visDataSets;
  if (!net || !ds || !graphView.nodeIds) return;

  graphView.expandPending = topicId;

  if (graphView.expandedId && graphView.expandedId !== topicId) {
    collapseGraphExpand({ restorePositions: true });
  }

  graphView.savedPositions = net.getPositions(graphView.nodeIds);
  const prev = ds.nodes.get(topicId);
  graphView.compactNodeBackup = prev ? { ...prev } : null;

  try {
    const t = await loadDetail(topicId);
    if (graphView.expandPending !== topicId) return;

    const bg =
      prev && prev.color && prev.color.background
        ? prev.color.background
        : "rgba(30, 64, 175, 0.92)";
    ds.nodes.update({
      id: topicId,
      shape: "ellipse",
      borderWidth: 3,
      color: {
        background: bg,
        border: "#93c5fd",
        highlight: { background: "#2563eb", border: "#bfdbfe" },
      },
    });

    showTopicWizard(t);
    graphView.expandedId = topicId;
    net.selectNodes([topicId]);
    net.fit({ animation: { duration: 320 } });
  } catch (e) {
    if (graphView.expandPending !== topicId) return;
    toast(String(e.message), "error");
    hideTopicWizard();
    if (graphView.compactNodeBackup) {
      ds.nodes.update(graphView.compactNodeBackup);
    }
    if (graphView.savedPositions) {
      for (const nid of Object.keys(graphView.savedPositions)) {
        const p = graphView.savedPositions[nid];
        net.moveNode(nid, p.x, p.y);
      }
    }
    graphView.savedPositions = null;
    graphView.compactNodeBackup = null;
    graphView.expandedId = null;
  }
}

function buildVisDatasets(nodes, links) {
  const { clusterOf } = computeClusters(nodes, links);
  const layoutPos = computeCommunityClusterPositions(nodes, links);
  const visNodes = nodes.map((n) => {
    const lines = n.labelLines || ["—"];
    const label = `${lines.join("\n")}\n${n.salienceLabel}`;
    const cid =
      n.community != null && Number.isFinite(Number(n.community))
        ? Number(n.community)
        : clusterOf.get(n.id) ?? 0;
    const hue = (cid * 47) % 360;
    const bg = n.archived
      ? `rgba(51, 65, 85, ${0.55 + n.fillOpacity * 0.45})`
      : `rgba(30, 64, 175, ${n.fillOpacity})`;
    const p = layoutPos.get(n.id);
    const vis = {
      id: n.id,
      label,
      color: {
        background: bg,
        border: n.archived ? "#64748b" : `hsl(${hue}, 62%, 72%)`,
        highlight: {
          background: n.archived ? "#475569" : "#2563eb",
          border: "#93c5fd",
        },
      },
      font: { color: "#f1f5f9", size: 11, multi: true, face: "Inter, Segoe UI, system-ui, sans-serif" },
      shape: "ellipse",
      borderWidth: 2,
      margin: 12,
    };
    if (p) {
      vis.x = p.x;
      vis.y = p.y;
    }
    return vis;
  });
  const visEdges = links.map((e, i) => ({
    id: `e${i}`,
    from: e.source,
    to: e.target,
    label: e.label || undefined,
    color: { color: e.isRef ? "#22c55e" : "#60a5fa", highlight: "#38bdf8" },
    dashes: e.isRef,
    arrows: { to: { enabled: true, scaleFactor: 0.65 } },
    font: { size: 10, color: "#cbd5e1", strokeWidth: 0, align: "middle" },
    smooth: { type: "dynamic" },
  }));
  return { visNodes, visEdges };
}

const VIS_NETWORK_OPTIONS = {
  physics: {
    enabled: true,
    stabilization: {
      enabled: true,
      iterations: 420,
      updateInterval: 30,
      fit: true,
    },
    barnesHut: {
      gravitationalConstant: -5200,
      centralGravity: 0.06,
      springLength: 195,
      springConstant: 0.042,
      damping: 0.58,
      avoidOverlap: 0.72,
    },
  },
  layout: { improvedLayout: true, randomSeed: 42 },
  interaction: {
    dragNodes: true,
    dragView: true,
    zoomView: true,
    hover: true,
    hoverConnectedEdges: true,
    tooltipDelay: 120,
  },
  nodes: {
    shape: "ellipse",
    widthConstraint: { maximum: 200 },
  },
  edges: { selectionWidth: 2 },
};

function initGraph(container) {
  graphView.container = container;
  if (graphView.resizeObserver) graphView.resizeObserver.disconnect();
  graphView.resizeObserver = new ResizeObserver(() => {
    if (!graphView.network || !graphView.container) return;
    const w = graphView.container.clientWidth;
    const h = graphView.container.clientHeight;
    graphView.network.setSize(w, h);
  });
  graphView.resizeObserver.observe(container);
}

/**
 * Selected topic on the graph.
 * Falls back to expanded topic when the network has no selection (e.g. after partial updates).
 */
function getPrimarySelectedTopicId() {
  const net = graphView.network;
  if (!net) return null;
  const ids = net.getSelectedNodes();
  for (const id of ids) {
    if (id) return id;
  }
  return graphView.expandedId;
}

function updateGraphDeleteTopicButton() {
  const btn = document.getElementById("btn-delete-selected-topic");
  if (!btn) return;
  btn.disabled = !getPrimarySelectedTopicId();
}

function wireGraphDeleteTopicButton() {
  const btn = document.getElementById("btn-delete-selected-topic");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const tid = getPrimarySelectedTopicId();
    if (!tid) {
      toast("Select a topic on the graph first (click a node).", "error");
      return;
    }
    let titleHint = tid.slice(0, 8) + "…";
    const ds = graphView.visDataSets?.nodes;
    if (ds) {
      try {
        const n = ds.get(tid);
        if (n && n.label) {
          titleHint = String(n.label).split("\n")[0].trim().slice(0, 56) || titleHint;
        }
      } catch (_) {
        /* ignore */
      }
    }
    if (!confirm(`Delete topic “${titleHint}”?\n\nThis removes the topic and cannot be undone.`)) return;
    try {
      if (graphView.expandedId === tid) {
        collapseGraphExpand({ restorePositions: false });
      }
      await api(`/api/ui/topics/${encodeURIComponent(tid)}`, { method: "DELETE" });
      setStatus("Deleted topic");
      await refreshGraph();
      updateGraphDeleteTopicButton();
    } catch (e) {
      setStatus(String(e.message), true);
    }
  });
}

function renderGraph(apiData) {
  graphView.expandedId = null;
  graphView.savedPositions = null;
  graphView.compactNodeBackup = null;
  graphView.expandPending = null;
  graphView.wizardTopicPayload = null;
  graphView.nodeIds = null;
  graphView.lastRawLinks = null;
  graphView.visDataSets = null;
  graphView.nodeTooltipPayload = null;
  hideGraphTooltip();
  hideTopicWizard();

  const { nodes: nodeIn, links: linkIn } = buildGraphData(apiData);
  graphView.nodeTooltipPayload = new Map();
  for (const n of nodeIn) {
    if (n.tooltipPayload) graphView.nodeTooltipPayload.set(n.id, n.tooltipPayload);
  }
  updateEmptyState(nodeIn.length);

  if (graphView.layoutFallbackTimer) {
    clearTimeout(graphView.layoutFallbackTimer);
    graphView.layoutFallbackTimer = null;
  }
  if (graphView.network) {
    graphView.network.destroy();
    graphView.network = null;
  }
  if (graphView.container) graphView.container.innerHTML = "";

  if (!nodeIn.length) {
    hideGraphTooltip();
    updateGraphDeleteTopicButton();
    return;
  }

  const nodes = nodeIn.map((d) => ({ ...d }));
  const links = linkIn.map((d) => ({ ...d }));
  const { visNodes, visEdges } = buildVisDatasets(nodes, links);

  const data = {
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  };

  graphView.nodeIds = nodes.map((n) => n.id);
  graphView.lastRawLinks = links;
  graphView.visDataSets = data;

  const net = new vis.Network(graphView.container, data, VIS_NETWORK_OPTIONS);
  graphView.network = net;

  let layoutFinalized = false;
  function finalizeLayout() {
    if (layoutFinalized) return;
    layoutFinalized = true;
    net.setOptions({ physics: false });
    net.fit({ animation: { duration: 380 } });
  }

  graphView.layoutFallbackTimer = setTimeout(finalizeLayout, 12000);
  net.on("stabilizationIterationsDone", () => {
    if (graphView.layoutFallbackTimer) {
      clearTimeout(graphView.layoutFallbackTimer);
      graphView.layoutFallbackTimer = null;
    }
    finalizeLayout();
  });

  net.on("click", (params) => {
    if (!params.nodes.length) return;
    const id = params.nodes[0];
    if (graphView.expandedId === id) {
      collapseGraphExpand({ restorePositions: true });
      return;
    }
    expandGraphNode(id);
  });

  net.on("doubleClick", (params) => {
    if (params.nodes.length === 0 && params.edges.length === 0) {
      net.fit({ animation: { duration: 320 } });
    }
  });

  net.on("select", () => updateGraphDeleteTopicButton());
  net.on("deselect", () => updateGraphDeleteTopicButton());
  updateGraphDeleteTopicButton();

  wireGraphTooltip(net);

  const w = graphView.container.clientWidth;
  const h = graphView.container.clientHeight;
  net.setSize(`${w}px`, `${h}px`);
}

function updateEmptyState(nodeCount) {
  const el = document.getElementById("empty-state");
  if (!el) return;
  el.classList.toggle("hidden", nodeCount > 0);
}

async function refreshGraph() {
  setStatus("Loading…", false, { skipToast: true });
  try {
    const data = await api("/api/ui/graph");
    const { nodes, links } = buildGraphData(data);
    renderGraph(data);
    const el = document.getElementById("status");
    const summary = `${nodes.length} topic${nodes.length !== 1 ? "s" : ""}, ${links.length} edge${links.length !== 1 ? "s" : ""}`;
    if (el) {
      el.textContent = summary;
      el.classList.remove("err");
    }
  } catch (e) {
    setStatus(String(e.message), true);
  }
}

/* ── LLM chat (Ollama / Groq + memory tools) ── */

const LS_OLLAMA_URL = "memstate_ollama_url";
const LS_LLM_PROVIDER = "memstate_llm_provider";
const LS_MODEL_OLLAMA = "memstate_llm_model_ollama";
const LS_MODEL_GROQ = "memstate_llm_model_groq";
const LS_CHAT_INTENT_TURNS = "memstate_chat_intent_turns";
/** Groq edge timeouts are common above ~tens of k chars—warn before send (single-shot only). */
const GROQ_LONG_MESSAGE_WARN_CHARS = 28000;
/** Above this character count, long ingest uses server-side Study (hierarchy + two phases). */
const CHAT_CHUNK_THRESHOLD = 10000;

const STUDY_STAGE_MESSAGES = [
  "Building document hierarchy…",
  "Study phase A — writing sandbox topics…",
  "Spacing requests (reduces Groq rate limits)…",
  "Study phase B — integrating with memory…",
];

function showStudyProgressInline() {
  const el = document.getElementById("study-progress-inline");
  if (!el) return;
  el.hidden = false;
  const status = document.getElementById("study-progress-status");
  let i = 0;
  if (status) status.textContent = STUDY_STAGE_MESSAGES[0];
  const interval = setInterval(() => {
    i = (i + 1) % STUDY_STAGE_MESSAGES.length;
    if (status) status.textContent = STUDY_STAGE_MESSAGES[i];
  }, 4800);
  el.dataset.studyInterval = String(interval);
}

function setStudyProgressLabel(text) {
  const status = document.getElementById("study-progress-status");
  if (status) status.textContent = text;
}

function hideStudyProgressInline() {
  const el = document.getElementById("study-progress-inline");
  if (!el) return;
  const id = el.dataset.studyInterval;
  if (id) {
    clearInterval(Number(id));
    delete el.dataset.studyInterval;
  }
  el.hidden = true;
}

const OLLAMA_MODELS = [
  { value: "llama3.2:latest", label: "llama3.2" },
  { value: "qwen2.5:latest", label: "qwen2.5" },
];
const GROQ_MODELS = [
  { value: "openai/gpt-oss-20b", label: "GPT-OSS 20B" },
  { value: "openai/gpt-oss-120b", label: "GPT-OSS 120B" },
];

const chatHistory = [];

/** Collapse very long message bodies; full text preserved for expand. */
const CHAT_BODY_PREVIEW_MAX = 900;

function truncateChatPreview(text, max) {
  const t = String(text ?? "");
  if (t.length <= max) return t;
  let cut = t.slice(0, max);
  const lastSp = cut.lastIndexOf(" ");
  if (lastSp > max * 0.55) cut = cut.slice(0, lastSp);
  return cut.trimEnd() + "…";
}

/**
 * @param {HTMLDivElement} wrapper
 * @param {string} fullText
 */
function fillCollapsibleChatBody(wrapper, fullText) {
  const t = String(fullText ?? "");
  wrapper.className = "chat-body";
  if (t.length <= CHAT_BODY_PREVIEW_MAX) {
    wrapper.textContent = t;
    return;
  }
  const preview = document.createElement("div");
  preview.className = "chat-body-text chat-body-text-preview";
  preview.textContent = truncateChatPreview(t, CHAT_BODY_PREVIEW_MAX);
  const full = document.createElement("div");
  full.className = "chat-body-text chat-body-text-full";
  full.hidden = true;
  full.textContent = t;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "chat-body-expand";
  btn.textContent = "Show more";
  btn.setAttribute("aria-expanded", "false");
  btn.addEventListener("click", () => {
    const expanded = btn.getAttribute("aria-expanded") === "true";
    const next = !expanded;
    btn.setAttribute("aria-expanded", String(next));
    preview.hidden = next;
    full.hidden = !next;
    btn.textContent = next ? "Show less" : "Show more";
  });
  wrapper.appendChild(preview);
  wrapper.appendChild(full);
  wrapper.appendChild(btn);
}

function fillLlmModelSelect(provider) {
  const sel = document.getElementById("llm-model");
  if (!sel) return;
  const opts = provider === "groq" ? GROQ_MODELS : OLLAMA_MODELS;
  sel.innerHTML = "";
  for (const o of opts) {
    const opt = document.createElement("option");
    opt.value = o.value;
    opt.textContent = o.label;
    sel.appendChild(opt);
  }
  const key = provider === "groq" ? LS_MODEL_GROQ : LS_MODEL_OLLAMA;
  const saved = localStorage.getItem(key);
  if (saved && [...sel.options].some((op) => op.value === saved)) {
    sel.value = saved;
  }
}

function syncProviderUi(provider) {
  const wrap = document.getElementById("ollama-url-wrap");
  const hint = document.getElementById("chat-hint-text");
  if (wrap) wrap.hidden = provider === "groq";
  if (hint) {
    if (provider === "groq") {
      hint.innerHTML =
        "Uses <strong>Groq</strong> in the cloud. Set <code>GROQ_API_KEY</code> in <code>.env</code> on the server.";
    } else {
      hint.innerHTML =
        "<strong>Ollama</strong> runs locally (ollama.com). Change URL if not on <code>127.0.0.1:11434</code>.";
    }
  }
}

function appendChatMessage(role, text) {
  const log = document.getElementById("chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = role === "user" ? "You" : "Assistant";
  const body = document.createElement("div");
  fillCollapsibleChatBody(body, text);
  div.appendChild(roleEl);
  div.appendChild(body);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

/**
 * Assistant reply with expandable "Thinking" trace (provider, model, tool calls + results).
 * @param {string} text
 * @param {{ provider?: string, model?: string, intent?: string, intent_source?: string, tool_log?: { tool: string, result: unknown }[] }} [meta]
 */
function appendAssistantMessage(text, meta) {
  const log = document.getElementById("chat-log");
  if (!log) return;

  const div = document.createElement("div");
  div.className = "chat-msg assistant";

  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = "Assistant";

  const body = document.createElement("div");
  fillCollapsibleChatBody(body, text || "(no reply)");

  const toolLog = Array.isArray(meta?.tool_log) ? meta.tool_log : [];
  const hasTools = toolLog.length > 0;
  const hasIntent = Boolean(meta?.intent);

  function intentRouteLabel(route) {
    if (route === "query") return "Query — read-only memory tools";
    if (route === "ingest") return "Ingest — write memory (+ read helpers)";
    if (route === "both") return "Both — full read/write tool set";
    return String(route || "—");
  }

  function intentSourceLabel(src) {
    if (src === "override") return "Client override (intent_override)";
    if (src === "classifier") return "LLM classifier (no tools, separate call)";
    return "—";
  }

  const thinking = document.createElement("div");
  thinking.className = "chat-thinking";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "chat-thinking-toggle";
  toggle.setAttribute("aria-expanded", "false");
  const chev = document.createElement("span");
  chev.className = "chat-thinking-chev";
  chev.setAttribute("aria-hidden", "true");
  chev.textContent = "▸";
  const toggleLabel = document.createElement("span");
  toggleLabel.textContent =
    hasIntent || hasTools ? "Thinking: intent, tools & trace" : "How this answer was built";
  toggle.appendChild(chev);
  toggle.appendChild(toggleLabel);

  const panel = document.createElement("div");
  panel.className = "chat-thinking-body";
  panel.hidden = true;

  const metaLine = document.createElement("div");
  metaLine.className = "chat-thinking-meta";
  const segHint =
    meta?.study_ingest && meta?.study_phases != null
      ? ` · Study (${meta.study_phases} phases)`
      : meta?.internal_chunked && meta?.segments != null
        ? ` · ${meta.segments} server segment${meta.segments !== 1 ? "s" : ""}`
        : "";
  metaLine.textContent = `${meta?.provider || "—"} · ${meta?.model || "—"}${segHint}`;
  panel.appendChild(metaLine);

  if (hasIntent) {
    const intentBlock = document.createElement("div");
    intentBlock.className = "chat-thinking-intent";
    const intentTitle = document.createElement("div");
    intentTitle.className = "chat-thinking-tool-name";
    intentTitle.textContent = "1. Intent classification";
    const intentBody = document.createElement("div");
    intentBody.className = "chat-thinking-intent-detail";
    intentBody.innerHTML = `<strong>${escapeHtml(String(meta.intent))}</strong> — ${escapeHtml(intentRouteLabel(meta.intent))}<br/><span class="chat-thinking-intent-source">${escapeHtml(intentSourceLabel(meta.intent_source))}</span>`;
    intentBlock.appendChild(intentTitle);
    intentBlock.appendChild(intentBody);
    panel.appendChild(intentBlock);
  }

  if (hasTools) {
    const stepOffset = hasIntent ? 2 : 1;
    toolLog.forEach((entry, i) => {
      const step = document.createElement("div");
      step.className = "chat-thinking-step";
      const nameEl = document.createElement("div");
      nameEl.className = "chat-thinking-tool-name";
      const seg = entry.segment != null ? `[seg ${entry.segment}] ` : "";
      nameEl.textContent = `${i + stepOffset}. ${seg}${entry.tool || "(unknown)"}`;
      const pre = document.createElement("pre");
      pre.className = "chat-thinking-json";
      let s;
      try {
        s = JSON.stringify(entry.result, null, 2);
      } catch {
        s = String(entry.result);
      }
      if (s.length > 8000) {
        s = `${s.slice(0, 8000)}\n… (${s.length} chars total, truncated)`;
      }
      pre.textContent = s;
      step.appendChild(nameEl);
      step.appendChild(pre);
      panel.appendChild(step);
    });
  } else {
    const p = document.createElement("p");
    p.className = "chat-thinking-none";
    p.textContent =
      "No tools were called. The model produced this reply without invoking memory tools (or tools are not shown for this response).";
    panel.appendChild(p);
  }

  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    panel.hidden = open;
    chev.textContent = open ? "▸" : "▾";
  });

  thinking.appendChild(toggle);
  thinking.appendChild(panel);

  div.appendChild(roleEl);
  div.appendChild(body);
  div.appendChild(thinking);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

/**
 * @param {string} userText
 * @param {{ intentOverride?: "query"|"ingest"|"both" }} [options]
 */
async function runChatTurn(userText, options = {}) {
  const { intentOverride } = options;
  const btn = document.getElementById("btn-chat-send");
  const ollamaUrl = document.getElementById("ollama-url");
  const prov = document.getElementById("llm-provider");
  const modelSel = document.getElementById("llm-model");
  const text = String(userText || "").trim();
  if (!text) return;

  const provider = prov?.value || "ollama";
  const useInternalChunk = text.length > CHAT_CHUNK_THRESHOLD;

  if (!useInternalChunk && provider === "groq" && text.length >= GROQ_LONG_MESSAGE_WARN_CHARS) {
    toast(
      "Heads up: very long messages often time out on Groq (HTTP 524). Consider using Ollama or shorten the text."
    );
  }
  if (useInternalChunk) {
    toast(
      `Long message (${text.length} chars): one request — the server runs Study ingest (hierarchy, two phases).`
    );
  }

  if (btn) btn.disabled = true;
  if (useInternalChunk) showStudyProgressInline();
  try {
    appendChatMessage("user", text);
    chatHistory.push({ role: "user", content: text });

    const messagesForApi = chatHistory
      .filter(
        (m) =>
          (m.role === "user" || m.role === "assistant") && String(m.content ?? "").trim()
      )
      .map((m) => ({ role: m.role, content: String(m.content).trim() }));
    const payload = {
      messages: messagesForApi,
      provider,
      model: modelSel?.value || undefined,
    };
    if (intentOverride === "query" || intentOverride === "ingest" || intentOverride === "both") {
      payload.intent_override = intentOverride;
    }
    const it = document.getElementById("chat-intent-turns");
    const kTurns = it ? parseInt(it.value, 10) : parseInt(localStorage.getItem(LS_CHAT_INTENT_TURNS) || "8", 10);
    if (Number.isFinite(kTurns) && kTurns >= 1 && kTurns <= 64) {
      payload.intent_turns = kTurns;
    }
    if (provider === "ollama") {
      const u = ollamaUrl?.value?.trim();
      if (u) {
        payload.ollama_base_url = u;
        localStorage.setItem(LS_OLLAMA_URL, u);
      }
      localStorage.setItem(LS_MODEL_OLLAMA, modelSel?.value || "");
    } else {
      localStorage.setItem(LS_MODEL_GROQ, modelSel?.value || "");
    }
    const data = await api("/api/llm/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (useInternalChunk) {
      setStudyProgressLabel("Visualizing graph…");
    }
    const replyText = data.reply || "(no reply)";
    chatHistory.push({ role: "assistant", content: replyText });
    appendAssistantMessage(replyText, {
      provider: data.provider,
      model: data.model,
      intent: data.intent,
      intent_source: data.intent_source,
      tool_log: data.tool_log || [],
      internal_chunked: data.internal_chunked,
      segments: data.segments,
      study_ingest: data.study_ingest,
      study_phases: data.study_phases,
    });
    if (data.tool_log && data.tool_log.length) {
      await refreshGraph();
    }
  } catch (err) {
    appendChatMessage("assistant", "Error: " + err.message);
    toast(err.message, "error");
  } finally {
    hideStudyProgressInline();
    if (btn) btn.disabled = false;
  }
}

function buildReorganizeUserMessage(operation, criteriaRaw) {
  const criteria = String(criteriaRaw || "").trim();
  const goals =
    criteria ||
    "Optimize memory size, retrieval performance, and reasoning quality; keep facts accurate.";
  const labels = {
    consolidation: "consolidation",
    merge_topics: "merge topics",
    split_topics: "split topics",
    connect_topics: "connect topics",
    retention_trim: "retention trim (RTC)",
  };
  const toolByOp = {
    consolidation: "memory_reorganize_consolidation",
    merge_topics: "memory_reorganize_merge_topics",
    split_topics: "memory_reorganize_split_topics",
    connect_topics: "memory_reorganize_connect_topics",
    retention_trim: "memory_reorganize_retention_trim",
  };
  const label = labels[operation] || operation;
  const tool = toolByOp[operation] || "memory_reorganize_consolidation";
  if (operation === "merge_topics") {
    return (
      `Memory reorganize: ${label}.\n\n` +
      `Criteria: ${goals}\n\n` +
      `Workflow: (1) Call ${tool} for topics_schema_snapshot (structure only). ` +
      `(2) Find merge candidates from overlapping schema (field names/types, kinds, titles, refs). ` +
      `(3) For candidates, use memory_get_topic_schema with detail current (or memory_get_topic) to compare **values**—look for overlap and intersection (shared strings, list overlap, same entity). ` +
      `(4) Merge only if merging improves organization; skip distinct entities. ` +
      `(5) Apply with write tools and summarize briefly.`
    );
  }
  return (
    `Memory reorganize: ${label}.\n\n` +
    `Criteria: ${goals}\n\n` +
    `Workflow: (1) Call ${tool} with these criteria to get the compact topics_schema_snapshot (structure only). ` +
    `(2) Plan from that snapshot. (3) Only if needed, use memory_get_topic_schema (minimal/current) or a single memory_get_topic—avoid loading the full graph. ` +
    `(4) Apply with write tools. Summarize changes briefly.`
  );
}

function wireReorganize() {
  const criteriaEl = document.getElementById("reorganize-criteria");
  document.querySelectorAll(".btn-reorg[data-reorg-op]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const op = btn.getAttribute("data-reorg-op");
      if (!op) return;
      const criteria = criteriaEl ? criteriaEl.value : "";
      const msg = buildReorganizeUserMessage(op, criteria);
      runChatTurn(msg, { intentOverride: "both" });
      const aside = document.querySelector("aside.panel-chat");
      if (aside) {
        requestAnimationFrame(() => aside.scrollIntoView({ behavior: "smooth", block: "nearest" }));
      }
    });
  });
}

function wireChat() {
  const form = document.getElementById("form-chat");
  const input = document.getElementById("chat-input");
  const btn = document.getElementById("btn-chat-send");
  const ollamaUrl = document.getElementById("ollama-url");
  const prov = document.getElementById("llm-provider");
  const modelSel = document.getElementById("llm-model");
  if (!form || !input || !btn) return;

  if (!localStorage.getItem(LS_MODEL_OLLAMA) && localStorage.getItem("memstate_ollama_model")) {
    localStorage.setItem(LS_MODEL_OLLAMA, localStorage.getItem("memstate_ollama_model"));
  }

  if (ollamaUrl) ollamaUrl.value = localStorage.getItem(LS_OLLAMA_URL) || "";
  const intentTurnsEl = document.getElementById("chat-intent-turns");
  if (intentTurnsEl) {
    const saved = localStorage.getItem(LS_CHAT_INTENT_TURNS);
    const n = saved != null ? parseInt(saved, 10) : 8;
    if (Number.isFinite(n) && n >= 1 && n <= 64) intentTurnsEl.value = String(n);
    intentTurnsEl.addEventListener("change", () => {
      const v = parseInt(intentTurnsEl.value, 10);
      if (Number.isFinite(v) && v >= 1 && v <= 64) {
        localStorage.setItem(LS_CHAT_INTENT_TURNS, String(v));
      }
    });
  }
  if (prov) {
    prov.value = localStorage.getItem(LS_LLM_PROVIDER) || "ollama";
    fillLlmModelSelect(prov.value);
    syncProviderUi(prov.value);
    prov.addEventListener("change", () => {
      localStorage.setItem(LS_LLM_PROVIDER, prov.value);
      fillLlmModelSelect(prov.value);
      syncProviderUi(prov.value);
    });
  }
  if (modelSel && prov) {
    modelSel.addEventListener("change", () => {
      const key = prov.value === "groq" ? LS_MODEL_GROQ : LS_MODEL_OLLAMA;
      localStorage.setItem(key, modelSel.value);
    });
  }
  if (ollamaUrl) {
    ollamaUrl.addEventListener("change", () => {
      localStorage.setItem(LS_OLLAMA_URL, ollamaUrl.value.trim());
    });
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    await runChatTurn(text);
  });
}

/* ── Topic wizard (graph click) ── */

async function loadDetail(topicId) {
  return api(`/api/ui/topics/${encodeURIComponent(topicId)}`);
}

function wireTopicWizard() {
  const backdrop = document.getElementById("topic-wizard-backdrop");
  const closeBtn = document.getElementById("btn-topic-wizard-close");
  const copyBtn = document.getElementById("btn-topic-wizard-copy");
  if (backdrop) {
    backdrop.addEventListener("click", () => collapseGraphExpand({ restorePositions: true }));
  }
  if (closeBtn) {
    closeBtn.addEventListener("click", () => collapseGraphExpand({ restorePositions: true }));
  }
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const t = graphView.wizardTopicPayload;
      if (!t) return;
      navigator.clipboard.writeText(JSON.stringify(t, null, 2)).then(
        () => toast("Copied topic JSON"),
        () => toast("Copy failed", "error")
      );
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const w = document.getElementById("topic-wizard");
    if (!w || w.hidden) return;
    collapseGraphExpand({ restorePositions: true });
  });
}

/* ── Forms ── */

function wireForms() {
  document.getElementById("api-key").addEventListener("change", (e) => {
    localStorage.setItem(LS_KEY, e.target.value.trim());
  });
  document.getElementById("api-key").value = localStorage.getItem(LS_KEY) || "";

  document.getElementById("btn-refresh").addEventListener("click", refreshGraph);

  document.getElementById("form-topic").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      title: fd.get("title") || "untitled",
      summary: fd.get("summary") || null,
      topic_kind: fd.get("topic_kind") || null,
      salience: parseFloat(fd.get("salience") || "1"),
    };
    try {
      const r = await api("/api/ui/topics", { method: "POST", body: JSON.stringify(body) });
      setStatus("Created topic " + r.topic_id);
      await refreshGraph();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById("form-rel").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const from_id = fd.get("from_id");
    const body = {
      to_topic_id: fd.get("to_topic_id"),
      kind: fd.get("kind"),
    };
    try {
      await api(`/api/ui/topics/${encodeURIComponent(from_id)}/relationships`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setStatus("Relationship added");
      await refreshGraph();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById("form-field").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const topic_id = fd.get("topic_id");
    const ref = (fd.get("ref_topic_id") || "").trim();
    const body = {
      field_name: fd.get("field_name"),
      value: fd.get("value") ?? "",
      field_type: fd.get("field_type") || "string",
      ref_topic_id: ref || null,
      provenance: "ui",
    };
    try {
      await api(`/api/ui/topics/${encodeURIComponent(topic_id)}/fields`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setStatus("Field updated");
      await refreshGraph();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  document.getElementById("form-delete").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const id = fd.get("topic_id");
    if (!confirm("Delete topic " + id + "?")) return;
    try {
      await api(`/api/ui/topics/${encodeURIComponent(id)}`, { method: "DELETE" });
      setStatus("Deleted");
      if (graphView.expandedId === id) hideTopicWizard();
      await refreshGraph();
    } catch (err) {
      setStatus(err.message, true);
    }
  });
}

/* ── Init ── */

document.addEventListener("DOMContentLoaded", async () => {
  const container = document.getElementById("network");
  if (typeof vis === "undefined" || !vis.Network || !vis.DataSet) {
    container.textContent = "vis-network failed to load.";
    return;
  }
  initGraph(container);

  wireCollapsible();
  wireForms();
  wireGraphDeleteTopicButton();
  wireChat();
  wireReorganize();
  wireTopicWizard();
  await checkBackendBanner();
  await refreshGraph();
});
