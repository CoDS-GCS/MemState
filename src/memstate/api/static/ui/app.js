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

/**
 * Groq Whisper on the server (requires GROQ_API_KEY in .env).
 * @param {Blob} blob
 * @param {string} [filename]
 */
async function transcribeChatAudioBlob(blob, filename) {
  const h = {};
  const k = localStorage.getItem(LS_KEY);
  if (k) h["X-API-Key"] = k;
  const name = filename || "capture.webm";
  const paths = ["/api/ui/transcribe", "/api/llm/transcribe"];
  let lastDetail = "";
  for (const path of paths) {
    const fd = new FormData();
    fd.append("audio", blob, name);
    const r = await fetch(path, { method: "POST", headers: h, body: fd });
    const text = await r.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { detail: text };
    }
    if (r.ok) {
      return String(data.text || "").trim();
    }
    lastDetail = formatApiError(data) || r.statusText || String(r.status);
    if (r.status === 404) {
      continue;
    }
    throw new Error(lastDetail);
  }
  throw new Error(
    lastDetail ||
      "Transcription API not found (404). Restart the MemState API process so it loads the latest code with POST /api/ui/transcribe."
  );
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function setSystemContextCard(data) {
  const badge = document.getElementById("system-context-badge");
  const form = document.getElementById("form-system-context");
  if (!badge || !form) return;
  const roleInput = form.querySelector('input[name="system_role"]');
  const runtimeInput = form.querySelector('textarea[name="runtime_context"]');
  const adminInput = form.querySelector('input[name="admin_key"]');
  if (!roleInput || !runtimeInput) return;
  const configured = !!(data && data.configured);
  // Auto-open the panel section when unconfigured so the form is visible.
  const section = document.querySelector('.panel-section[data-section="system-context"]');
  if (section && !section.dataset.userToggled) {
    const toggle = section.querySelector(".section-toggle");
    const body = section.querySelector(".section-body");
    if (toggle && body) {
      const shouldOpen = !configured;
      toggle.classList.toggle("active", shouldOpen);
      body.classList.toggle("open", shouldOpen);
    }
  }
  if (!configured || !data.system_context) {
    badge.textContent = "Not configured";
    badge.classList.remove("is-configured");
    roleInput.value = "";
    runtimeInput.value = "";
    if (adminInput) adminInput.value = "";
    return;
  }
  badge.textContent = "Configured";
  badge.classList.add("is-configured");
  roleInput.value = String(data.system_context.system_role || "");
  runtimeInput.value = String(data.system_context.runtime_context || "");
  if (adminInput) adminInput.value = "";
}

async function refreshSystemContextCard() {
  try {
    const data = await api("/api/ui/system-context");
    setSystemContextCard(data);
  } catch (_) {
    /* keep UI usable even if this call fails */
  }
}

let chatMarkdownConfigured = false;

function ensureChatMarkdownConfigured() {
  if (chatMarkdownConfigured) return;
  chatMarkdownConfigured = true;
  if (typeof marked !== "undefined" && typeof marked.setOptions === "function") {
    marked.setOptions({
      breaks: true,
      gfm: true,
      headerIds: false,
      mangle: false,
    });
  }
  if (typeof DOMPurify !== "undefined" && typeof DOMPurify.addHook === "function") {
    DOMPurify.addHook("afterSanitizeAttributes", (node) => {
      if (node.tagName === "A" && node instanceof HTMLAnchorElement) {
        const href = node.getAttribute("href") || "";
        if (/^https?:\/\//i.test(href)) {
          node.setAttribute("target", "_blank");
          node.setAttribute("rel", "noopener noreferrer");
        }
      }
    });
  }
}

/**
 * @param {string} raw
 * @returns {string | null} HTML or null if libraries unavailable
 */
function renderChatMarkdown(raw) {
  const t = String(raw ?? "");
  ensureChatMarkdownConfigured();
  if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
    const dirty = marked.parse(t);
    return DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true } });
  }
  return null;
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
      const section = btn.closest(".panel-section");
      if (section) section.dataset.userToggled = "1";
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

/**
 * Wrap arbitrary text into N lines (word-aware).
 * @param {unknown} text
 * @param {number} maxCharsPerLine
 * @param {number} maxLines
 */
function wrapTextLines(text, maxCharsPerLine, maxLines) {
  return wrapTitleLines(String(text ?? ""), maxCharsPerLine, maxLines);
}

/**
 * Compact type hint for the schema column inside a topic card.
 * @param {string} rawType
 * @param {boolean} [isRef]
 */
function abbreviateFieldType(rawType, isRef) {
  const t = String(rawType || "").toLowerCase().trim();
  if (isRef) return "ref";
  if (!t) return "—";
  if (t === "string" || t === "str") return "str";
  if (t === "number" || t === "num" || t === "int" || t === "float") return "num";
  if (t === "boolean" || t === "bool") return "bool";
  if (t === "json" || t === "object" || t === "dict") return "json";
  if (t === "list" || t === "array") return "list";
  return t.slice(0, 6);
}

/**
 * Canvas helper: rounded rectangle path. Does not fill or stroke.
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} x
 * @param {number} y
 * @param {number} w
 * @param {number} h
 * @param {number} r
 */
function pathRoundRect(ctx, x, y, w, h, r) {
  const rr = Math.max(0, Math.min(r, Math.min(w, h) / 2));
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.lineTo(x + w - rr, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
  ctx.lineTo(x + w, y + h - rr);
  ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
  ctx.lineTo(x + rr, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
  ctx.lineTo(x, y + rr);
  ctx.quadraticCurveTo(x, y, x + rr, y);
  ctx.closePath();
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
  const fields = (apiNode.fields || []).map((f) => {
    const row = {
      name: String(f.name || ""),
      type: String(f.field_type || "—"),
      ref: f.ref_topic_id ? String(f.ref_topic_id).slice(0, 10) + "…" : null,
      nested: null,
    };
    const nf = f.nested_fields;
    if (Array.isArray(nf) && nf.length) {
      row.nested = nf.map((sf) => ({
        name: String(sf.name || ""),
        type: String(sf.field_type || "—"),
      }));
    }
    return row;
  });
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

function hideGraphTooltip() {
  /* legacy no-op: node hover tooltip removed (use click → topic wizard). */
}

function buildGraphData(data) {
  const rawList = data.nodes || [];
  const saliences = rawList.map((n) => parseSalience(n));
  const minS = saliences.length ? Math.min(...saliences) : 0;
  const maxS = saliences.length ? Math.max(...saliences) : 1;

  const nodes = rawList.map((n, i) => {
    const raw =
      (n.title && String(n.title).trim()) || n.label || n.id.slice(0, 8);
    const summary = n.summary != null ? String(n.summary) : "";
    const salience = saliences[i];
    const comm =
      n.community != null && Number.isFinite(Number(n.community)) ? Number(n.community) : null;
    const fieldSchema = Array.isArray(n.fields)
      ? n.fields
          .map((f) => {
            const name = String((f && f.name) || "").trim();
            if (!name) return null;
            const rawType = String((f && f.field_type) || "").trim();
            const typeShort = abbreviateFieldType(rawType, f && f.ref_topic_id);
            return { name, type: typeShort, ref: !!(f && f.ref_topic_id) };
          })
          .filter(Boolean)
          .sort((a, b) => a.name.localeCompare(b.name))
      : [];
    return {
      id: String(n.id ?? "").trim(),
      titleRaw: raw,
      summaryRaw: summary,
      fieldSchema,
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

/** @param {unknown} entry */
function parseHistoryValidFromMs(entry) {
  if (!entry || typeof entry !== "object") return null;
  const raw = /** @type {{ valid_from?: unknown }} */ (entry).valid_from;
  if (raw == null || raw === "") return null;
  const n = Date.parse(String(raw));
  return Number.isFinite(n) ? n : null;
}

/**
 * Opacity for history row: current (index 0) = 1; older rows fade by time span or by index.
 * @param {unknown[]} hist
 * @param {number} index
 */
function historyTimelineOpacity(hist, index) {
  if (index === 0) return 1;
  if (!hist.length) return 1;
  const tNewest = parseHistoryValidFromMs(hist[0]);
  const tSelf = parseHistoryValidFromMs(hist[index]);
  const tOldest = parseHistoryValidFromMs(hist[hist.length - 1]);
  if (tNewest != null && tSelf != null && tOldest != null && tNewest >= tOldest) {
    const span = Math.max(tNewest - tOldest, 1);
    const age = Math.max(0, tNewest - tSelf);
    const u = Math.min(1, age / span);
    return Math.max(0.12, 1 - 0.88 * u);
  }
  const maxIdx = Math.max(hist.length - 1, 1);
  const u = index / maxIdx;
  return Math.max(0.12, 1 - 0.82 * u);
}

/**
 * @param {unknown[]} hist
 * @param {{ variant?: "default" | "compact" }} [opts]
 */
function renderFieldTimelineHtml(hist, opts = {}) {
  const compact = opts.variant === "compact";
  const parts = [];
  const h = Array.isArray(hist) ? hist : [];
  if (h.length) {
    const wrapClass = compact
      ? "topic-wizard-field-timeline topic-wizard-field-timeline--compact"
      : "topic-wizard-field-timeline";
    parts.push(`<div class="${wrapClass}">`);
    parts.push(
      compact
        ? '<div class="topic-wizard-timeline-heading topic-wizard-timeline-heading--compact">History</div>'
        : '<div class="topic-wizard-timeline-heading">Value timeline</div>',
    );
    parts.push('<ul class="topic-wizard-timeline" role="list">');
    for (let i = 0; i < h.length; i++) {
      const e = h[i];
      let timeHtml;
      if (e && typeof e === "object" && e.valid_from != null && String(e.valid_from).trim() !== "") {
        const raw = String(e.valid_from);
        const ms = Date.parse(raw);
        if (Number.isFinite(ms)) {
          timeHtml = `<time class="topic-wizard-timeline-time" datetime="${escapeHtml(new Date(ms).toISOString())}">${escapeHtml(raw)}</time>`;
        } else {
          timeHtml = `<span class="topic-wizard-timeline-time">${escapeHtml(raw)}</span>`;
        }
      } else {
        timeHtml = `<span class="topic-wizard-timeline-time">${escapeHtml(i === 0 ? "—" : `Step ${i + 1}`)}</span>`;
      }
      const val = e && typeof e === "object" ? e.value : e;
      const isCurrent = i === 0;
      const op = historyTimelineOpacity(h, i);
      const itemClass = isCurrent
        ? "topic-wizard-timeline-item topic-wizard-timeline-item--current"
        : "topic-wizard-timeline-item topic-wizard-timeline-item--past";
      const badge = isCurrent
        ? '<span class="topic-wizard-timeline-badge">Current</span>'
        : compact
          ? '<span class="topic-wizard-timeline-badge topic-wizard-timeline-badge--past" title="Earlier revision">Prior</span>'
          : '<span class="topic-wizard-timeline-badge topic-wizard-timeline-badge--past">Earlier</span>';
      const opRaw = e && typeof e === "object" && e.operation != null ? String(e.operation).trim() : "";
      const opTag = opRaw
        ? `<span class="topic-wizard-timeline-op" title="Revision operation">${escapeHtml(opRaw)}</span>`
        : "";
      const ariaCur = isCurrent ? ' aria-current="true"' : "";
      parts.push(
        `<li class="${itemClass}" style="opacity:${op}"${ariaCur}>` +
          '<span class="topic-wizard-timeline-dot" aria-hidden="true"></span>' +
          '<div class="topic-wizard-timeline-body">' +
          `<div class="topic-wizard-timeline-meta">${badge}${opTag}${timeHtml}</div>` +
          `<div class="topic-wizard-timeline-value">${formatWizardFieldValueHtml(val)}</div>` +
          "</div></li>"
      );
    }
    parts.push("</ul></div>");
  } else {
    parts.push('<p class="topic-wizard-no-history">No revision history for this field.</p>');
  }
  return parts.join("");
}

/**
 * @param {Record<string, unknown>} f
 */
function nestedInnerFromFieldRecord(f) {
  if (!f || typeof f !== "object") return null;
  const hist = Array.isArray(f.history) ? f.history : [];
  const cur = hist[0];
  if (!cur || typeof cur !== "object") return null;
  const val = cur.value;
  if (!val || typeof val !== "object") return null;
  const o = /** @type {Record<string, unknown>} */ (val);
  if (o._memstate_nested !== true) return null;
  const inner = o.fields;
  if (!inner || typeof inner !== "object") return null;
  return /** @type {Record<string, Record<string, unknown>>} */ (inner);
}

/**
 * @param {string} subName
 * @param {Record<string, unknown>} sub
 */
function renderNestedSubFieldCardHtml(subName, sub) {
  const parts = [];
  parts.push('<div class="topic-wizard-field-card topic-wizard-field-card--nested-item">');
  parts.push(`<h5 class="topic-wizard-h5">${escapeHtml(subName)}</h5>`);
  parts.push('<dl class="topic-wizard-dl topic-wizard-field-meta">');
  parts.push(`<dt>Type</dt><dd>${escapeHtml(String(sub.field_type ?? "—"))}</dd>`);
  if (sub.ref_topic_id) {
    const rid = String(sub.ref_topic_id).trim();
    parts.push(
      `<dt>Ref topic</dt><dd class="topic-wizard-ref-dd"><div class="topic-wizard-ref-single">${formatWizardRefLinkRowHtml(rid, getWizardRefLinkLabel(rid), null)}</div></dd>`
    );
  }
  parts.push("</dl>");
  parts.push(renderFieldTimelineHtml(/** @type {unknown[]} */ (sub.history)));
  parts.push("</div>");
  return parts.join("");
}

/** @param {unknown} val */
function formatFieldValueText(val) {
  if (val === undefined || val === null) return "—";
  if (typeof val === "object") return JSON.stringify(val, null, 2);
  return String(val);
}

const TOPIC_UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** @param {unknown} s */
function isLikelyTopicIdString(s) {
  return typeof s === "string" && TOPIC_UUID_RE.test(s.trim());
}

/**
 * Short title for a topic id when rendering ref links (graph payload or node label).
 * @param {string} topicId
 */
function getWizardRefLinkLabel(topicId) {
  const payload = graphView.nodeTooltipPayload?.get(topicId);
  if (payload && payload.head) {
    const h = String(payload.head).trim();
    if (h) return h.length > 56 ? h.slice(0, 55) + "…" : h;
  }
  const ds = graphView.visDataSets?.nodes;
  if (ds) {
    try {
      const n = ds.get(topicId);
      if (n && n.label) {
        const line = String(n.label).split("\n")[0].trim().slice(0, 56);
        if (line) return line;
      }
    } catch (_) {
      /* ignore */
    }
  }
  return topicId.slice(0, 8) + "…";
}

/**
 * One row: same visual language as graph "field ref" edges (dashed green rail).
 * @param {string} topicId
 * @param {string} label
 * @param {number | null} index1Based
 */
function formatWizardRefLinkRowHtml(topicId, label, index1Based) {
  const idx =
    index1Based != null
      ? `<span class="topic-wizard-ref-idx" aria-hidden="true">${index1Based}.</span>`
      : "";
  return (
    `${idx}<button type="button" class="topic-wizard-ref-link" data-topic-id="${escapeHtml(topicId)}" title="Open topic">` +
      '<span class="topic-wizard-ref-link-main">' +
      '<span class="topic-wizard-ref-link-kind">field ref</span>' +
      `<span class="topic-wizard-ref-link-label">${escapeHtml(label)}</span>` +
      `<code class="topic-wizard-ref-link-id">${escapeHtml(topicId)}</code>` +
      "</span></button>"
  );
}

/**
 * HTML for a field value: UUID strings / lists of UUIDs → ref-edge rows; else escaped JSON/pre.
 * @param {unknown} val
 */
function formatWizardFieldValueHtml(val) {
  if (val === undefined || val === null) {
    return '<span class="topic-wizard-value-scalar">—</span>';
  }
  if (typeof val === "string") {
    if (isLikelyTopicIdString(val)) {
      const tid = val.trim();
      return `<div class="topic-wizard-ref-single">${formatWizardRefLinkRowHtml(tid, getWizardRefLinkLabel(tid), null)}</div>`;
    }
    return `<pre class="topic-wizard-timeline-value-pre">${escapeHtml(val)}</pre>`;
  }
  if (typeof val === "number" || typeof val === "boolean") {
    return `<span class="topic-wizard-value-scalar">${escapeHtml(String(val))}</span>`;
  }
  if (Array.isArray(val)) {
    if (val.length === 0) {
      return '<span class="topic-wizard-value-scalar">[]</span>';
    }
    const allTopicIds = val.every((item) => typeof item === "string" && isLikelyTopicIdString(item));
    const caption = allTopicIds
      ? '<div class="topic-wizard-ref-edges-caption">Linked topics (same as <span class="topic-wizard-ref-caption-legend">field ref</span> edges on the graph)</div>'
      : "";
    const lis = val.map((item, i) => {
      if (typeof item === "string" && isLikelyTopicIdString(item)) {
        const tid = item.trim();
        return `<li class="topic-wizard-ref-edge-li">${formatWizardRefLinkRowHtml(tid, getWizardRefLinkLabel(tid), i + 1)}</li>`;
      }
      const chunk =
        typeof item === "object" && item !== null
          ? JSON.stringify(item, null, 2)
          : String(item ?? "—");
      return `<li class="topic-wizard-ref-edge-li topic-wizard-ref-edge-li--raw"><pre class="topic-wizard-timeline-value-pre">${escapeHtml(chunk)}</pre></li>`;
    });
    return `${caption}<ul class="topic-wizard-ref-edges" role="list">${lis.join("")}</ul>`;
  }
  return `<pre class="topic-wizard-timeline-value-pre">${escapeHtml(JSON.stringify(val, null, 2))}</pre>`;
}

/**
 * @param {unknown} topicHistory
 * @returns {{ child_topic_id: string, relationship_kind?: string }[]}
 */
function nestedPromotionTargetsFromHistory(topicHistory) {
  const arr = Array.isArray(topicHistory) ? topicHistory : [];
  /** @type {Map<string, { child_topic_id: string, relationship_kind?: string }>} */
  const m = new Map();
  for (const ev of arr) {
    if (!ev || typeof ev !== "object") continue;
    const o = /** @type {Record<string, unknown>} */ (ev);
    if (o.kind !== "nested_topic_promoted" || !o.detail || typeof o.detail !== "object") continue;
    const d = /** @type {Record<string, unknown>} */ (o.detail);
    const cid = d.child_topic_id != null ? String(d.child_topic_id).trim() : "";
    if (!cid) continue;
    const rk = d.relationship_kind != null ? String(d.relationship_kind).trim() : "";
    m.set(cid, {
      child_topic_id: cid,
      relationship_kind: rk || undefined,
    });
  }
  return [...m.values()];
}

/**
 * @param {unknown} topicHistory
 */
function lastNestedParentFromHistory(topicHistory) {
  const arr = Array.isArray(topicHistory) ? topicHistory : [];
  for (let i = arr.length - 1; i >= 0; i--) {
    const ev = arr[i];
    if (!ev || typeof ev !== "object") continue;
    const o = /** @type {Record<string, unknown>} */ (ev);
    if (o.kind !== "nested_topic_from_parent" || !o.detail || typeof o.detail !== "object") continue;
    const d = /** @type {Record<string, unknown>} */ (o.detail);
    const pid = d.parent_topic_id != null ? String(d.parent_topic_id).trim() : "";
    if (!pid) continue;
    const rk = d.relationship_kind != null ? String(d.relationship_kind).trim() : "";
    return {
      parent_topic_id: pid,
      relationship_kind: rk || undefined,
    };
  }
  return null;
}

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

  const tid = t.id != null ? String(t.id) : "";
  const th = t.topic_history;
  if (tid) {
    const promotions = nestedPromotionTargetsFromHistory(th);
    if (promotions.length) {
      parts.push('<section class="topic-wizard-section topic-wizard-nested-undo">');
      parts.push('<h3 class="topic-wizard-h3">Undo nested detail</h3>');
      parts.push(
        '<p class="topic-wizard-help">Merge a detail topic back into this topic and remove the child node (reverses nested grouping—not a graph split).</p>'
      );
      for (const p of promotions) {
        const short = p.child_topic_id.length > 10 ? `${p.child_topic_id.slice(0, 8)}…` : p.child_topic_id;
        const kindAttr = p.relationship_kind ? escapeHtml(p.relationship_kind) : "";
        parts.push(
          `<button type="button" class="btn btn-danger btn-topic-wizard-undo-nested" data-undo-parent="${escapeHtml(tid)}" data-undo-child="${escapeHtml(p.child_topic_id)}" data-undo-kind="${kindAttr}">Undo → merge child <code>${escapeHtml(short)}</code></button>`
        );
      }
      parts.push("</section>");
    }
  }

  const nestParent = lastNestedParentFromHistory(th);
  if (tid && nestParent) {
    parts.push('<section class="topic-wizard-section topic-wizard-nested-undo">');
    parts.push('<h3 class="topic-wizard-h3">Nested under parent</h3>');
    parts.push(
      '<p class="topic-wizard-help">Merge these fields back into the parent and remove this detail topic (same subject, not a split).</p>'
    );
    parts.push(
      `<p class="topic-wizard-undo-meta">Parent: ${formatWizardRefLinkRowHtml(nestParent.parent_topic_id, getWizardRefLinkLabel(nestParent.parent_topic_id), null)}</p>`
    );
    const kindAttr = nestParent.relationship_kind ? escapeHtml(nestParent.relationship_kind) : "";
    parts.push(
      `<button type="button" class="btn btn-danger btn-topic-wizard-undo-nested" data-undo-parent="${escapeHtml(nestParent.parent_topic_id)}" data-undo-child="${escapeHtml(tid)}" data-undo-kind="${kindAttr}">Undo nesting (merge into parent)</button>`
    );
    parts.push("</section>");
  }

  const fields = t.fields && typeof t.fields === "object" ? t.fields : {};
  const names = Object.keys(fields).sort();
  if (names.length) {
    parts.push('<section class="topic-wizard-section"><h3 class="topic-wizard-h3">Fields</h3>');
    for (const name of names) {
      const f = fields[name];
      if (!f || typeof f !== "object") continue;
      const inner = nestedInnerFromFieldRecord(/** @type {Record<string, unknown>} */ (f));
      if (inner) {
        parts.push(
          `<div class="topic-wizard-field-card topic-wizard-field-card--nested-root" data-nest-root="${escapeHtml(name)}">`
        );
        parts.push(
          `<h4 class="topic-wizard-h4"><button type="button" class="topic-wizard-field-name-btn" data-field-name="${escapeHtml(name)}" title="Open field history">${escapeHtml(name)}</button> <span class="topic-wizard-nested-pill">nested fields</span></h4>`
        );
        parts.push('<dl class="topic-wizard-dl topic-wizard-field-meta">');
        parts.push("<dt>Type</dt><dd>json <span class=\"topic-wizard-nested-pill\">same topic</span></dd>");
        parts.push("</dl>");
        parts.push('<div class="topic-wizard-nested-inner">');
        for (const subName of Object.keys(inner).sort()) {
          const sub = inner[subName];
          if (sub && typeof sub === "object") {
            parts.push(renderNestedSubFieldCardHtml(subName, /** @type {Record<string, unknown>} */ (sub)));
          }
        }
        parts.push("</div>");
        if (tid) {
          parts.push(
            `<button type="button" class="btn btn-danger btn-topic-wizard-unnest" data-unnest-topic="${escapeHtml(tid)}" data-unnest-key="${escapeHtml(name)}">Unnest (restore top-level fields)</button>`
          );
        }
        parts.push("</div>");
        continue;
      }
      parts.push(
        `<div class="topic-wizard-field-card"><h4 class="topic-wizard-h4"><button type="button" class="topic-wizard-field-name-btn" data-field-name="${escapeHtml(name)}" title="Open field history">${escapeHtml(name)}</button></h4>`
      );
      parts.push('<dl class="topic-wizard-dl topic-wizard-field-meta">');
      parts.push(`<dt>Type</dt><dd>${escapeHtml(String(f.field_type ?? "—"))}</dd>`);
      if (f.ref_topic_id) {
        const rid = String(f.ref_topic_id).trim();
        parts.push(
          `<dt>Ref topic</dt><dd class="topic-wizard-ref-dd"><div class="topic-wizard-ref-single">${formatWizardRefLinkRowHtml(rid, getWizardRefLinkLabel(rid), null)}</div></dd>`
        );
      }
      parts.push("</dl>");
      parts.push(renderFieldTimelineHtml(/** @type {unknown[]} */ (f.history)));
      parts.push("</div>");
    }
    parts.push("</section>");
    if (tid && names.length) {
      parts.push(
        `<section class="topic-wizard-section topic-wizard-nest-in-topic" data-topic-id="${escapeHtml(tid)}">`
      );
      parts.push('<h3 class="topic-wizard-h3">Nest fields (same topic)</h3>');
      parts.push(
        '<p class="topic-wizard-help">Fold related fields into one <strong>json group on this topic</strong>—no new graph node, no RELATED edge, no ref. The graph still shows one topic; nested fields appear indented here and in the tooltip.</p>'
      );
      parts.push('<div class="topic-wizard-promote-fields">');
      for (const name of names) {
        parts.push(
          `<label class="topic-wizard-promote-label"><input type="checkbox" name="nest-field" value="${escapeHtml(name)}" /> <span>${escapeHtml(name)}</span></label>`
        );
      }
      parts.push("</div>");
      parts.push('<div class="topic-wizard-promote-form">');
      parts.push(
        '<label class="topic-wizard-promote-row">Group field name <input type="text" class="topic-wizard-promote-input" id="topic-wizard-nest-key" placeholder="e.g. professional_details" autocomplete="off" /></label>'
      );
      parts.push(
        '<button type="button" class="btn btn-primary btn-topic-wizard-nest" id="btn-topic-wizard-nest">Nest selected fields</button>'
      );
      parts.push('<p class="topic-wizard-promote-status" id="topic-wizard-nest-status" hidden></p>');
      parts.push("</div></section>");
    }
  }

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

/** @type {{ closer: (e: MouseEvent) => void } | null} */
let graphNodeMenuDismiss = null;

function hideGraphNodeMenu() {
  const m = document.getElementById("graph-node-menu");
  if (m) {
    m.hidden = true;
    m.innerHTML = "";
    delete m.dataset.topicId;
  }
  if (graphNodeMenuDismiss) {
    document.removeEventListener("click", graphNodeMenuDismiss.closer, true);
    graphNodeMenuDismiss = null;
  }
}

/**
 * @param {string} tid
 */
function getTopicTitleHint(tid) {
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
  return titleHint;
}

/**
 * @param {string} tid
 */
async function deleteGraphTopic(tid) {
  if (!tid) return;
  hideGraphNodeMenu();
  const titleHint = getTopicTitleHint(tid);
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
}

/**
 * @param {number} clientX
 * @param {number} clientY
 * @param {string} topicId
 */
function showGraphNodeMenu(clientX, clientY, topicId) {
  hideGraphNodeMenu();
  const m = document.getElementById("graph-node-menu");
  const wrap = graphView.container?.closest(".graph-wrap");
  if (!m || !wrap) return;
  m.dataset.topicId = topicId;
  m.innerHTML = `
    <button type="button" class="graph-node-menu-item" data-action="open" role="menuitem">Open details</button>
    <button type="button" class="graph-node-menu-item graph-node-menu-danger" data-action="delete" role="menuitem">Delete topic…</button>
  `;
  m.hidden = false;
  const br = wrap.getBoundingClientRect();
  const place = () => {
    let left = clientX - br.left;
    let top = clientY - br.top;
    const mw = m.offsetWidth;
    const mh = m.offsetHeight;
    left = Math.max(8, Math.min(left, br.width - mw - 8));
    top = Math.max(8, Math.min(top, br.height - mh - 8));
    m.style.left = `${left}px`;
    m.style.top = `${top}px`;
  };
  requestAnimationFrame(place);

  m.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const tid = m.dataset.topicId;
      const action = btn.dataset.action;
      hideGraphNodeMenu();
      if (action === "open" && tid) void expandGraphNode(tid);
      else if (action === "delete" && tid) void deleteGraphTopic(tid);
    });
  });

  const closer = (e) => {
    if (!m.hidden && !m.contains(e.target)) hideGraphNodeMenu();
  };
  setTimeout(() => {
    document.addEventListener("click", closer, true);
  }, 0);
  graphNodeMenuDismiss = { closer };
}

function collapseGraphExpand({ restorePositions = true } = {}) {
  hideGraphNodeMenu();
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
  hideGraphNodeMenu();
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

const CARD_FONT = 'Inter, "Segoe UI", system-ui, -apple-system, sans-serif';
const CARD_MONO = 'ui-monospace, "Cascadia Code", "JetBrains Mono", monospace';
const CARD_W = 230;
const CARD_PAD_X = 12;
const CARD_PAD_T = 10;
const CARD_PAD_B = 11;
const CARD_TITLE_LH = 15;
const CARD_SUMMARY_LH = 12;
const CARD_FIELD_LH = 13;
const CARD_MAX_TITLE_LINES = 2;
const CARD_MAX_SUMMARY_LINES = 2;
const CARD_MAX_FIELDS = 6;
const CARD_TITLE_CHARS = 28;
const CARD_SUMMARY_CHARS = 34;
const CARD_FIELD_NAME_MAX = 18;

/**
 * Prepare render-time layout for a topic card (strings + geometry).
 * @param {Record<string, any>} n
 */
function buildCardLayout(n) {
  const titleLines = wrapTitleLines(
    String(n.titleRaw || "—"),
    CARD_TITLE_CHARS,
    CARD_MAX_TITLE_LINES,
  );
  const summaryRaw = String(n.summaryRaw || "").trim();
  const summaryLines = summaryRaw
    ? wrapTextLines(summaryRaw, CARD_SUMMARY_CHARS, CARD_MAX_SUMMARY_LINES)
    : [];
  const schema = Array.isArray(n.fieldSchema) ? n.fieldSchema : [];
  const shown = schema.slice(0, CARD_MAX_FIELDS);
  const overflow = Math.max(0, schema.length - CARD_MAX_FIELDS);

  let h = CARD_PAD_T;
  h += titleLines.length * CARD_TITLE_LH;
  if (summaryLines.length) h += 2 + summaryLines.length * CARD_SUMMARY_LH;
  if (shown.length) h += 8 + 1 + 7 + shown.length * CARD_FIELD_LH;
  if (overflow > 0) h += CARD_FIELD_LH;
  if (!shown.length && !overflow) h += 2;
  h += CARD_PAD_B;

  return {
    titleLines,
    summaryLines,
    schemaShown: shown,
    overflow,
    fieldCount: schema.length,
    width: CARD_W,
    height: Math.max(62, Math.round(h)),
  };
}

/** @param {number} community */
function communityHue(community) {
  const c = Number.isFinite(community) ? community : 0;
  return ((c * 47) % 360 + 360) % 360;
}

/**
 * Build a ctxRenderer for a single topic card.
 * @param {Record<string, any>} n
 * @param {number} cid
 */
function makeCardRenderer(n, cid) {
  const layout = buildCardLayout(n);
  const hue = communityHue(cid);
  const accent = n.archived ? "#64748b" : `hsl(${hue}, 72%, 65%)`;
  const accentMuted = n.archived ? "rgba(100,116,139,0.25)" : `hsla(${hue}, 72%, 65%, 0.18)`;
  const fillT = Math.max(0.55, Math.min(1, Number(n.fillOpacity) || 0.8));
  const bgTop = n.archived
    ? `rgba(30, 41, 59, ${0.55 + fillT * 0.3})`
    : `rgba(22, 30, 46, ${0.82 + fillT * 0.15})`;
  const bgBot = n.archived
    ? `rgba(15, 23, 42, ${0.85})`
    : `rgba(10, 14, 22, ${0.92})`;
  const bodyText = n.archived ? "#94a3b8" : "#e6edf3";
  const mutedText = n.archived ? "#64748b" : "#8b949e";

  return function ctxRenderer({ ctx, x, y, state }) {
    const { width: W, height: H, titleLines, summaryLines, schemaShown, overflow } = layout;
    const left = x - W / 2;
    const top = y - H / 2;
    const selected = !!(state && (state.selected || state.hover));

    return {
      drawNode() {
        ctx.save();

        // Soft drop shadow under card
        ctx.shadowColor = "rgba(0, 0, 0, 0.45)";
        ctx.shadowBlur = selected ? 18 : 10;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 3;
        pathRoundRect(ctx, left, top, W, H, 9);
        const grad = ctx.createLinearGradient(left, top, left, top + H);
        grad.addColorStop(0, bgTop);
        grad.addColorStop(1, bgBot);
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.restore();

        // Border
        pathRoundRect(ctx, left + 0.5, top + 0.5, W - 1, H - 1, 8.5);
        ctx.strokeStyle = selected ? "#93c5fd" : "rgba(148, 163, 184, 0.22)";
        ctx.lineWidth = selected ? 1.75 : 1;
        ctx.stroke();

        // Left accent bar (community color)
        ctx.save();
        pathRoundRect(ctx, left, top, 3, H, 0);
        ctx.fillStyle = accent;
        ctx.fill();
        ctx.restore();

        // Header underline fill (very subtle)
        const headerH = CARD_PAD_T + titleLines.length * CARD_TITLE_LH + 2;
        ctx.save();
        pathRoundRect(ctx, left + 3, top, W - 3, headerH, 8.5);
        const headGrad = ctx.createLinearGradient(left, top, left, top + headerH);
        headGrad.addColorStop(0, accentMuted);
        headGrad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = headGrad;
        ctx.fill();
        ctx.restore();

        // Cursor starts below top padding
        let cy = top + CARD_PAD_T + 11;

        // Title
        ctx.fillStyle = bodyText;
        ctx.font = `600 12px ${CARD_FONT}`;
        ctx.textAlign = "left";
        ctx.textBaseline = "alphabetic";
        for (const line of titleLines) {
          ctx.fillText(line, left + CARD_PAD_X, cy);
          cy += CARD_TITLE_LH;
        }

        // Salience chip (top-right)
        const chipText = String(n.salienceLabel ?? "—");
        ctx.font = `600 9px ${CARD_FONT}`;
        const chipTextW = ctx.measureText(chipText).width;
        const chipW = chipTextW + 14;
        const chipH = 15;
        const chipX = left + W - chipW - 8;
        const chipY = top + 8;
        pathRoundRect(ctx, chipX, chipY, chipW, chipH, 7);
        ctx.fillStyle = "rgba(61, 139, 253, 0.18)";
        ctx.fill();
        ctx.strokeStyle = "rgba(61, 139, 253, 0.4)";
        ctx.lineWidth = 0.8;
        ctx.stroke();
        ctx.fillStyle = "#bfdbfe";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(chipText, chipX + chipW / 2, chipY + chipH / 2 + 0.5);

        // Summary
        ctx.textAlign = "left";
        ctx.textBaseline = "alphabetic";
        if (summaryLines.length) {
          cy += 2;
          ctx.fillStyle = mutedText;
          ctx.font = `400 10px ${CARD_FONT}`;
          for (const line of summaryLines) {
            ctx.fillText(line, left + CARD_PAD_X, cy);
            cy += CARD_SUMMARY_LH;
          }
        }

        // Divider + fields list
        if (schemaShown.length || overflow) {
          cy += 8;
          ctx.strokeStyle = "rgba(148, 163, 184, 0.14)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(left + CARD_PAD_X, cy + 0.5);
          ctx.lineTo(left + W - CARD_PAD_X, cy + 0.5);
          ctx.stroke();
          cy += 10;

          const typeColX = left + W - CARD_PAD_X;
          const nameX = left + CARD_PAD_X + 6;
          const bulletX = left + CARD_PAD_X;

          for (const f of schemaShown) {
            // bullet
            ctx.fillStyle = f.ref ? "#22c55e" : "rgba(148, 163, 184, 0.6)";
            ctx.beginPath();
            ctx.arc(bulletX, cy - 3, 1.7, 0, Math.PI * 2);
            ctx.fill();

            // name (truncated)
            ctx.fillStyle = bodyText;
            ctx.font = `500 10px ${CARD_MONO}`;
            const name =
              f.name.length > CARD_FIELD_NAME_MAX
                ? f.name.slice(0, CARD_FIELD_NAME_MAX - 1) + "…"
                : f.name;
            ctx.textAlign = "left";
            ctx.fillText(name, nameX, cy);

            // type hint (right-aligned, muted)
            ctx.font = `500 9px ${CARD_MONO}`;
            ctx.fillStyle = f.ref ? "#86efac" : mutedText;
            ctx.textAlign = "right";
            ctx.fillText(f.type, typeColX, cy);

            cy += CARD_FIELD_LH;
          }

          if (overflow > 0) {
            ctx.fillStyle = mutedText;
            ctx.font = `500 9px ${CARD_FONT}`;
            ctx.textAlign = "left";
            ctx.fillText(`+${overflow} more field${overflow === 1 ? "" : "s"}`, nameX, cy);
            cy += CARD_FIELD_LH;
          }
        } else {
          cy += 4;
          ctx.fillStyle = mutedText;
          ctx.font = `italic 9.5px ${CARD_FONT}`;
          ctx.fillText("no fields", left + CARD_PAD_X + 6, cy + 2);
        }
      },
      nodeDimensions: { width: W, height: H },
    };
  };
}

/**
 * Custom d3-force that separates axis-aligned rectangular nodes.
 * Each sim node must expose numeric `w` and `h`. Much cleaner than
 * circle-based collision for card-shaped topics.
 */
function rectangleCollideForce(padding = 12, iterations = 2) {
  /** @type {Array<{ x:number, y:number, w:number, h:number }>} */
  let nodes = [];
  function force() {
    const n = nodes.length;
    for (let iter = 0; iter < iterations; iter++) {
      for (let i = 0; i < n; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < n; j++) {
          const b = nodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const minDX = (a.w + b.w) / 2 + padding;
          const minDY = (a.h + b.h) / 2 + padding;
          const ox = minDX - Math.abs(dx);
          const oy = minDY - Math.abs(dy);
          if (ox > 0 && oy > 0) {
            if (ox < oy) {
              const s = (ox / 2) * (dx >= 0 ? 1 : -1);
              a.x -= s;
              b.x += s;
            } else {
              const s = (oy / 2) * (dy >= 0 ? 1 : -1);
              a.y -= s;
              b.y += s;
            }
          }
        }
      }
    }
  }
  force.initialize = (_nodes) => {
    nodes = _nodes;
  };
  return force;
}

/**
 * Compute a community-aware force-directed layout using d3-force.
 * Returns null if d3 is unavailable so the caller can fall back.
 *
 * Forces:
 *  - link   (attracts connected topics at a moderate distance)
 *  - charge (global repulsion)
 *  - x/y    (pulls nodes toward their community centroid)
 *  - collide (rectangle-aware, uses actual card bbox → no overlap)
 */
function runForceLayout(nodes, links, cidOf) {
  if (typeof d3 === "undefined" || !d3.forceSimulation) return null;
  if (!nodes.length) return new Map();

  try {
    const simNodes = nodes.map((n) => {
      const layout = n._cardLayout || buildCardLayout(n);
      n._cardLayout = layout;
      return {
        id: n.id,
        w: layout.width,
        h: layout.height,
        community: cidOf(n),
        x: 0,
        y: 0,
      };
    });

    const nodeIds = new Set(simNodes.map((s) => s.id));

    const byComm = new Map();
    for (const s of simNodes) {
      if (!byComm.has(s.community)) byComm.set(s.community, []);
      byComm.get(s.community).push(s);
    }
    const cids = [...byComm.keys()].sort(
      (a, b) => byComm.get(b).length - byComm.get(a).length,
    );
    const nc = cids.length;
    const centers = new Map();
    if (nc <= 1) {
      centers.set(cids[0] ?? 0, { x: 0, y: 0 });
    } else {
      const R = 260 + Math.sqrt(simNodes.length) * 42;
      cids.forEach((cid, i) => {
        const theta = (2 * Math.PI * i) / nc - Math.PI / 2;
        centers.set(cid, { x: R * Math.cos(theta), y: R * Math.sin(theta) });
      });
    }
    for (const s of simNodes) {
      const c = centers.get(s.community) || { x: 0, y: 0 };
      let h = 0;
      for (let k = 0; k < s.id.length; k++) h = (h * 31 + s.id.charCodeAt(k)) | 0;
      const jx = (((h >>> 0) % 1000) / 1000 - 0.5) * 140;
      const jy = (((h >>> 10) % 1000) / 1000 - 0.5) * 140;
      s.x = c.x + jx;
      s.y = c.y + jy;
    }

    // Drop dangling edges (ids that aren't in the node set) before d3 sees
    // them — otherwise d3.forceLink throws `node not found: <id>` and aborts.
    const simLinks = links
      .filter(
        (l) => l.source !== l.target && nodeIds.has(l.source) && nodeIds.has(l.target),
      )
      .map((l) => ({ source: l.source, target: l.target }));

    const sim = d3
      .forceSimulation(simNodes)
      .force(
        "link",
        d3
          .forceLink(simLinks)
          .id((d) => d.id)
          .distance(340)
          .strength(0.18),
      )
      .force(
        "charge",
        d3.forceManyBody().strength(-2600).distanceMin(24).distanceMax(1800),
      )
      .force(
        "x",
        d3
          .forceX()
          .x((d) => (centers.get(d.community) || { x: 0 }).x)
          .strength(0.09),
      )
      .force(
        "y",
        d3
          .forceY()
          .y((d) => (centers.get(d.community) || { y: 0 }).y)
          .strength(0.09),
      )
      .force("collide", rectangleCollideForce(28, 1))
      .alpha(1)
      .alphaDecay(0.022)
      .velocityDecay(0.42)
      .stop();

    const ticks = Math.min(600, 320 + simNodes.length * 6);
    for (let i = 0; i < ticks; i++) sim.tick();

    // Final pure-separation pass — guarantees no visible card overlap and
    // gives edges more room to curve around neighbours.
    const separate = rectangleCollideForce(32, 1);
    separate.initialize(simNodes);
    for (let i = 0; i < 120; i++) separate();

    const out = new Map();
    for (const s of simNodes) out.set(s.id, { x: s.x, y: s.y });
    return out;
  } catch (err) {
    // Never let a layout hiccup blank out the whole graph — fall back.
    // eslint-disable-next-line no-console
    console.warn("[graph] d3 force layout failed, falling back:", err);
    return null;
  }
}

function buildVisDatasets(nodes, links) {
  const { clusterOf } = computeClusters(nodes, links);
  const cidOf = (n) =>
    n.community != null && Number.isFinite(Number(n.community))
      ? Number(n.community)
      : clusterOf.get(n.id) ?? 0;

  const nodeIds = new Set(nodes.map((n) => n.id));
  // Only keep edges whose endpoints exist; dangling refs corrupt layout + vis.
  const safeLinks = links.filter(
    (e) => nodeIds.has(e.source) && nodeIds.has(e.target),
  );
  if (safeLinks.length !== links.length) {
    // eslint-disable-next-line no-console
    console.warn(
      `[graph] dropped ${links.length - safeLinks.length} edges with missing endpoints`,
    );
  }

  const forcePos = runForceLayout(nodes, safeLinks, cidOf);
  const fallback = forcePos
    ? null
    : computeCommunityClusterPositions(nodes, safeLinks);
  const positionsReady = Boolean(forcePos);

  const visNodes = nodes.map((n) => {
    const cid = cidOf(n);
    const p = forcePos ? forcePos.get(n.id) : fallback?.get(n.id);
    const layout = n._cardLayout || buildCardLayout(n);
    n._cardLayout = layout;
    // vis-network's first layout pass runs before ctxRenderer reports
    // nodeDimensions; `size` seeds a sane bbox so edge intersections and
    // arrowheads are not computed for a tiny default circle.
    const vis = {
      id: n.id,
      shape: "custom",
      size: Math.ceil(Math.max(layout.width, layout.height) / 2),
      ctxRenderer: makeCardRenderer(n, cid),
      label: undefined,
      physics: false,
    };
    if (p) {
      vis.x = p.x;
      vis.y = p.y;
    }
    return vis;
  });

  // Distribute roundness + alternate curve direction among parallel edges so
  // they don't stack on top of each other.
  const pairKey = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);
  /** @type {Map<string, number>} */
  const pairCounts = new Map();
  for (const e of safeLinks) {
    const k = pairKey(e.source, e.target);
    pairCounts.set(k, (pairCounts.get(k) || 0) + 1);
  }
  /** @type {Map<string, number>} */
  const pairSeen = new Map();

  const visEdges = safeLinks.map((e, i) => {
    const k = pairKey(e.source, e.target);
    const count = pairCounts.get(k) || 1;
    const idx = pairSeen.get(k) || 0;
    pairSeen.set(k, idx + 1);
    // Alternate clockwise / counter-clockwise curves for parallel edges;
    // single edges get a gentle curve so they bend around neighbour cards
    // instead of slicing straight through them.
    let smoothType = "curvedCW";
    let roundness = 0.28;
    if (count > 1) {
      const step = 0.22;
      const isEven = idx % 2 === 0;
      smoothType = isEven ? "curvedCW" : "curvedCCW";
      roundness = 0.2 + Math.floor(idx / 2) * step;
    } else {
      // Hash-based alternating for visual variety when many single edges
      // arrive at the same node.
      let h = 0;
      for (let c = 0; c < k.length; c++) h = (h * 31 + k.charCodeAt(c)) | 0;
      smoothType = (h & 1) === 0 ? "curvedCW" : "curvedCCW";
    }

    const relKind = e.isRef ? "field ref" : e.label || "RELATED";
    const labelText = e.label || (e.isRef ? "ref" : "");
    return {
      id: `e${i}`,
      from: e.source,
      to: e.target,
      // Labels hidden by default (they overlapped cards); shown as tooltip +
      // as edge label only on hover / selection via `hoverEdge` handler.
      label: undefined,
      originalLabel: labelText,
      title: e.label ? `${relKind}: ${e.label}` : relKind,
      color: {
        color: e.isRef ? "#34d399" : "#60a5fa",
        highlight: e.isRef ? "#86efac" : "#bfdbfe",
        hover: e.isRef ? "#86efac" : "#bfdbfe",
        opacity: 0.72,
      },
      // Solid strokes: canvas dashes often leave the last gap short of the
      // arrowhead, so the head looks "floating"; ref vs RELATED is color.
      dashes: false,
      width: e.isRef ? 1.05 : 1.25,
      selectionWidth: 2.0,
      hoverWidth: 0.8,
      arrows: { to: { enabled: true, scaleFactor: 0.68, type: "arrow" } },
      // Must be true or vis ignores endPointOffset in bezier border math
      // (see vis-network bezier-edge-base.ts).
      arrowStrikethrough: true,
      // Positive = stop slightly outside the true border so tips sit on the
      // card edge instead of clipping into rounded corners / shadow.
      endPointOffset: { from: 4, to: 6 },
      font: {
        size: 10,
        color: "#cbd5f5",
        strokeWidth: 4,
        strokeColor: "rgba(10, 14, 22, 0.95)",
        align: "middle",
        face: CARD_FONT,
      },
      labelHighlightBold: false,
      smooth: {
        enabled: true,
        type: smoothType,
        roundness,
      },
    };
  });
  return { visNodes, visEdges, positionsReady };
}

const VIS_NETWORK_OPTIONS = {
  physics: {
    enabled: false,
  },
  layout: { improvedLayout: false, randomSeed: 42 },
  interaction: {
    dragNodes: true,
    dragView: true,
    zoomView: true,
    hover: true,
    hoverConnectedEdges: true,
    tooltipDelay: 120,
  },
  nodes: {
    shape: "custom",
    borderWidth: 0,
    borderWidthSelected: 0,
    shadow: false,
  },
  edges: {
    selectionWidth: 1.6,
    arrowStrikethrough: true,
    endPointOffset: { from: 4, to: 6 },
  },
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
    await deleteGraphTopic(tid);
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
  hideGraphNodeMenu();

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
  const { visNodes, visEdges, positionsReady } = buildVisDatasets(nodes, links);

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

  if (positionsReady) {
    // Positions were pre-computed by d3-force; fit the view on next tick.
    requestAnimationFrame(finalizeLayout);
  } else {
    graphView.layoutFallbackTimer = setTimeout(finalizeLayout, 12000);
    net.on("stabilizationIterationsDone", () => {
      if (graphView.layoutFallbackTimer) {
        clearTimeout(graphView.layoutFallbackTimer);
        graphView.layoutFallbackTimer = null;
      }
      finalizeLayout();
    });
  }

  net.on("click", (params) => {
    hideGraphNodeMenu();
    if (!params.nodes.length) return;
    const id = params.nodes[0];
    if (graphView.expandedId === id) {
      collapseGraphExpand({ restorePositions: true });
      return;
    }
    expandGraphNode(id);
  });

  net.on("oncontext", (params) => {
    const ev = params.event;
    if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    hideGraphTooltip();
    /** Right-click does not populate `nodes` by default — resolve via pointer (vis docs). */
    let id =
      params.nodes && params.nodes.length
        ? params.nodes[0]
        : params.pointer && params.pointer.DOM && typeof net.getNodeAt === "function"
          ? net.getNodeAt(params.pointer.DOM)
          : null;
    if (id != null && id !== "") {
      id = String(id);
      net.selectNodes([id]);
      updateGraphDeleteTopicButton();
      const cx = ev && typeof ev.clientX === "number" ? ev.clientX : 0;
      const cy = ev && typeof ev.clientY === "number" ? ev.clientY : 0;
      showGraphNodeMenu(cx, cy, id);
    } else {
      hideGraphNodeMenu();
    }
  });

  net.on("doubleClick", (params) => {
    if (params.nodes.length === 0 && params.edges.length === 0) {
      net.fit({ animation: { duration: 320 } });
    }
  });

  net.on("select", () => updateGraphDeleteTopicButton());
  net.on("deselect", () => updateGraphDeleteTopicButton());
  updateGraphDeleteTopicButton();

  // Reveal edge label on hover / selection — keeps the graph readable while
  // still exposing relationship kinds (e.g. "memberOf", "authors", ref fields).
  const showEdgeLabel = (id) => {
    if (!id) return;
    const edge = data.edges.get(id);
    if (!edge || !edge.originalLabel) return;
    data.edges.update({ id, label: edge.originalLabel });
  };
  const hideEdgeLabel = (id) => {
    if (!id) return;
    data.edges.update({ id, label: undefined });
  };
  net.on("hoverEdge", (params) => showEdgeLabel(params.edge));
  net.on("blurEdge", (params) => hideEdgeLabel(params.edge));
  net.on("selectEdge", (params) => (params.edges || []).forEach(showEdgeLabel));
  net.on("deselectEdge", (params) =>
    ((params.previousSelection && params.previousSelection.edges) || []).forEach(
      hideEdgeLabel,
    ),
  );

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
const LS_CHAT_SOUND = "memstate_chat_sound";
const LS_CHAT_VOICE = "memstate_chat_voice";
/** Silence this long after last loud audio → stop recording, transcribe, send to chat. */
const CHAT_VOICE_PAUSE_MS = 5000;
/** Time-domain RMS above this counts as speech (silence detection). */
const CHAT_VOICE_RMS_THRESHOLD = 0.01;
/** Peak sample deviation (0–1); catches speech that RMS misses on quiet mics. */
const CHAT_VOICE_PEAK_THRESHOLD = 0.035;
/** Encoded chunk size (bytes) that suggests real audio activity (resets pause timer). */
const CHAT_VOICE_CHUNK_ACTIVITY_BYTES = 80;
/** Stop recording automatically after this long (ms). */
const CHAT_VOICE_MAX_CAPTURE_MS = 120000;
/** If the mic never sees speech-level audio, give up (ms). */
const CHAT_VOICE_NO_SPEECH_GIVEUP_MS = 45000;

let uiAudioCtx = null;

let chatRequestInFlight = false;
let chatVoiceListening = false;

function voiceChatEnabled() {
  const el = document.getElementById("chat-voice-enabled");
  if (el && el instanceof HTMLInputElement) return el.checked;
  return localStorage.getItem(LS_CHAT_VOICE) === "1";
}

function getVoiceCaptureSupported() {
  return Boolean(
    typeof MediaRecorder !== "undefined" &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function" &&
      (typeof AudioContext !== "undefined" || typeof window.webkitAudioContext !== "undefined")
  );
}

function pickMediaRecorderMime() {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"];
  for (const t of candidates) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

/**
 * Strip markdown-ish syntax so TTS reads naturally.
 * @param {string} md
 */
function markdownToSpeakablePlain(md) {
  let s = String(md ?? "");
  s = s.replace(/```[\s\S]*?```/g, (block) => {
    const inner = block.replace(/^```\w*\n?/, "").replace(/```$/, "").trim();
    if (!inner) return " ";
    return inner.length > 220 ? ` Code snippet: ${inner.slice(0, 220)}… ` : ` ${inner} `;
  });
  s = s.replace(/`([^`]+)`/g, "$1");
  s = s.replace(/!?\[([^\]]*)\]\([^)]+\)/g, "$1");
  s = s.replace(/^\s{0,3}[-*+]\s+/gm, " ");
  s = s.replace(/^\s{0,3}\d+\.\s+/gm, " ");
  s = s.replace(/<[^>]+>/g, " ");
  s = s.replace(/[#>*_~|]+/g, "");
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

function stopChatSpeech() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  updateChatVoiceChrome();
}

function updateChatVoiceChrome() {
  const stopBtn = document.getElementById("btn-chat-stop-speech");
  if (!stopBtn) return;
  const speaking = Boolean(window.speechSynthesis && window.speechSynthesis.speaking);
  stopBtn.hidden = !speaking;
  stopBtn.disabled = !speaking;
}

/**
 * Read assistant (or error) text aloud when Voice chat is on.
 * @param {string} rawText
 */
function speakChatReply(rawText) {
  if (!voiceChatEnabled()) return;
  const synth = window.speechSynthesis;
  if (!synth) return;
  stopChatSpeech();
  const plain = markdownToSpeakablePlain(rawText);
  if (!plain || plain.length < 2) return;
  const max = 32000;
  const toSpeak =
    plain.length > max
      ? `${plain.slice(0, max)}. Stopping here; the reply was long.`
      : plain;
  const u = new SpeechSynthesisUtterance(toSpeak);
  u.rate = 1;
  u.pitch = 1;
  u.lang = document.documentElement.lang || navigator.language || "en-US";
  u.onend = () => updateChatVoiceChrome();
  u.onerror = () => updateChatVoiceChrome();
  synth.speak(u);
  updateChatVoiceChrome();
}

function syncChatInputChrome() {
  const sendBtn = document.getElementById("btn-chat-send");
  const mic = document.getElementById("btn-chat-voice");
  const ok = getVoiceCaptureSupported();
  if (sendBtn) sendBtn.disabled = chatRequestInFlight || chatVoiceListening;
  if (mic) mic.disabled = !ok || chatRequestInFlight;
}

function setChatVoiceListening(on) {
  chatVoiceListening = !!on;
  const mic = document.getElementById("btn-chat-voice");
  if (mic) {
    mic.classList.toggle("chat-voice-mic--listening", chatVoiceListening);
    mic.setAttribute("aria-pressed", String(chatVoiceListening));
  }
  syncChatInputChrome();
}

function refreshChatVoiceMicHint() {
  const mic = document.getElementById("btn-chat-voice");
  const ok = getVoiceCaptureSupported();
  if (!mic) return;
  mic.title = !ok
    ? "Voice needs a browser with MediaRecorder + microphone access."
    : `Mic: record → server Whisper (needs GROQ_API_KEY). Click again to stop. Voice chat = read replies only.`;
}

/**
 * @param {HTMLTextAreaElement} input
 */
function wireChatVoiceControls(input) {
  const mic = document.getElementById("btn-chat-voice");
  const stopSpeech = document.getElementById("btn-chat-stop-speech");
  const supported = getVoiceCaptureSupported();
  if (mic) mic.disabled = !supported;
  refreshChatVoiceMicHint();

  let capStream = null;
  let capAudioCtx = null;
  let capAnalyser = null;
  let capRecorder = null;
  let capChunks = [];
  let capSilenceInterval = 0;
  let capFinalizing = false;
  let capMime = "";
  let capExt = "webm";
  let capSessionStart = 0;
  let capLastLoudAt = 0;
  let capHadLoud = false;

  function touchVoiceActivity() {
    capHadLoud = true;
    capLastLoudAt = performance.now();
  }

  function stopSilenceLoop() {
    if (capSilenceInterval) {
      clearInterval(capSilenceInterval);
      capSilenceInterval = 0;
    }
  }

  function startSilenceLoop() {
    stopSilenceLoop();
    capSilenceInterval = setInterval(silenceTick, 100);
  }

  function teardownTracks() {
    if (capStream) {
      capStream.getTracks().forEach((t) => t.stop());
      capStream = null;
    }
  }

  function teardownAudioGraph() {
    try {
      capAnalyser?.disconnect();
    } catch {
      /* ignore */
    }
    capAnalyser = null;
    try {
      void capAudioCtx?.close();
    } catch {
      /* ignore */
    }
    capAudioCtx = null;
  }

  function sampleRmsAndPeak() {
    if (!capAnalyser) return { rms: 0, peak: 0 };
    const n = capAnalyser.fftSize;
    const buf = new Uint8Array(n);
    capAnalyser.getByteTimeDomainData(buf);
    let sum = 0;
    let peak = 0;
    for (let i = 0; i < n; i++) {
      const x = (buf[i] - 128) / 128;
      sum += x * x;
      peak = Math.max(peak, Math.abs(x));
    }
    return { rms: Math.sqrt(sum / n), peak };
  }

  function silenceTick() {
    const now = performance.now();
    if (!chatVoiceListening || capFinalizing) {
      stopSilenceLoop();
      return;
    }
    if (now - capSessionStart > CHAT_VOICE_MAX_CAPTURE_MS) {
      void finalizeVoiceCaptureAndSend();
      return;
    }
    const { rms, peak } = sampleRmsAndPeak();
    if (rms >= CHAT_VOICE_RMS_THRESHOLD || peak >= CHAT_VOICE_PEAK_THRESHOLD) {
      touchVoiceActivity();
    }
    if (capHadLoud && now - capLastLoudAt >= CHAT_VOICE_PAUSE_MS && now - capSessionStart >= 400) {
      void finalizeVoiceCaptureAndSend();
      return;
    }
    if (!capHadLoud && now - capSessionStart > CHAT_VOICE_NO_SPEECH_GIVEUP_MS) {
      toast("No speech detected — speak up or check the mic.", "error");
      void cancelVoiceCapture();
    }
  }

  function restoreVoiceInputPlaceholder() {
    const h = input.dataset.voiceHoldPh;
    if (h != null) {
      input.placeholder = h;
      delete input.dataset.voiceHoldPh;
    }
  }

  async function cancelVoiceCapture() {
    stopSilenceLoop();
    setChatVoiceListening(false);
    restoreVoiceInputPlaceholder();
    const rec = capRecorder;
    capRecorder = null;
    if (rec && rec.state !== "inactive") {
      rec.onstop = () => {
        capChunks = [];
        teardownAudioGraph();
        teardownTracks();
      };
      try {
        rec.requestData?.();
        rec.stop();
      } catch {
        capChunks = [];
        teardownAudioGraph();
        teardownTracks();
      }
    } else {
      teardownAudioGraph();
      teardownTracks();
    }
    capFinalizing = false;
  }

  function buildBlobFromRecordedChunks() {
    return new Blob(capChunks, { type: capMime || "audio/webm" });
  }

  async function transcribeBlobAndSend(blob) {
    if (blob.size < 180) {
      toast("Recording too short — speak a bit longer, then click the mic again to stop.", "error");
      return;
    }
    try {
      toast("Transcribing with Groq Whisper…");
      const text = await transcribeChatAudioBlob(blob, `capture.${capExt}`);
      if (!text.trim()) {
        toast("No words recognized.", "error");
        return;
      }
      input.value = "";
      await runChatTurn(text);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }

  async function finalizeVoiceCaptureAndSend() {
    if (capFinalizing) return;
    capFinalizing = true;
    try {
      stopSilenceLoop();
      restoreVoiceInputPlaceholder();

      const rec = capRecorder;
      capRecorder = null;
      setChatVoiceListening(false);

      const blob = await new Promise((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          try {
            if (rec) rec.onstop = null;
          } catch {
            /* ignore */
          }
          const b = buildBlobFromRecordedChunks();
          capChunks = [];
          resolve(b);
        };

        if (!rec || rec.state === "inactive") {
          finish();
          return;
        }

        rec.onstop = finish;
        try {
          rec.requestData?.();
          rec.stop();
        } catch {
          finish();
        }
      });

      teardownAudioGraph();
      teardownTracks();
      await transcribeBlobAndSend(blob);
    } finally {
      capFinalizing = false;
    }
  }

  stopSpeech?.addEventListener("click", () => {
    stopChatSpeech();
  });

  mic?.addEventListener("click", () => {
    void (async () => {
      if (!supported || mic.disabled) return;
      if (chatVoiceListening) {
        await finalizeVoiceCaptureAndSend();
        return;
      }
      if (!window.isSecureContext) {
        toast("Voice capture needs HTTPS or http://localhost.", "error");
        return;
      }
      stopChatSpeech();
      input.value = "";
      capChunks = [];
      capFinalizing = false;
      capSessionStart = performance.now();
      capLastLoudAt = capSessionStart;
      capHadLoud = false;
      if (input.dataset.voiceHoldPh == null) {
        input.dataset.voiceHoldPh = input.placeholder;
      }
      input.placeholder = "Recording… click mic again to stop & transcribe";

      try {
        try {
          capStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch {
          capStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              channelCount: 1,
              echoCancellation: true,
              noiseSuppression: true,
            },
          });
        }
        const ACtx = window.AudioContext || window.webkitAudioContext;
        capAudioCtx = new ACtx();
        await capAudioCtx.resume().catch(() => {});
        const src = capAudioCtx.createMediaStreamSource(capStream);
        capAnalyser = capAudioCtx.createAnalyser();
        capAnalyser.fftSize = 2048;
        capAnalyser.smoothingTimeConstant = 0.35;
        src.connect(capAnalyser);

        capMime = pickMediaRecorderMime();
        capExt = capMime.includes("mp4") || capMime.includes("aac") ? "m4a" : "webm";
        const opts = capMime ? { mimeType: capMime } : undefined;
        try {
          capRecorder = opts ? new MediaRecorder(capStream, opts) : new MediaRecorder(capStream);
        } catch {
          capRecorder = new MediaRecorder(capStream);
          capMime = "";
          capExt = "webm";
        }
        capRecorder.onerror = () => {
          toast("Microphone recording error — try again or use another browser.", "error");
        };
        capRecorder.ondataavailable = (ev) => {
          if (!ev.data || ev.data.size <= 0) return;
          capChunks.push(ev.data);
          if (ev.data.size >= CHAT_VOICE_CHUNK_ACTIVITY_BYTES) {
            touchVoiceActivity();
          }
        };
        capRecorder.start(250);
        setChatVoiceListening(true);
        startSilenceLoop();
      } catch (e) {
        restoreVoiceInputPlaceholder();
        teardownAudioGraph();
        teardownTracks();
        capRecorder = null;
        capChunks = [];
        setChatVoiceListening(false);
        const msg = e instanceof Error ? e.message : String(e);
        toast(`Microphone: ${msg || "could not start"}`, "error");
      }
    })();
  });
}

function chatSoundEnabled() {
  const el = document.getElementById("chat-sound-enabled");
  if (el && el instanceof HTMLInputElement) return el.checked;
  return localStorage.getItem(LS_CHAT_SOUND) !== "0";
}

function ensureUiAudioContext() {
  if (uiAudioCtx) return uiAudioCtx;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  uiAudioCtx = new Ctx();
  return uiAudioCtx;
}

/**
 * @param {"user" | "assistant" | "error"} kind
 */
function playChatSound(kind) {
  if (!chatSoundEnabled()) return;
  const ctx = ensureUiAudioContext();
  if (!ctx) return;
  void ctx.resume().catch(() => {});
  const now = ctx.currentTime;
  const master = ctx.createGain();
  master.connect(ctx.destination);
  const peak = kind === "error" ? 0.09 : 0.065;
  master.gain.setValueAtTime(0.0001, now);
  master.gain.exponentialRampToValueAtTime(peak, now + 0.012);
  const fadeEnd =
    kind === "assistant" ? now + 0.26 : kind === "error" ? now + 0.2 : now + 0.085;
  master.gain.exponentialRampToValueAtTime(0.0001, fadeEnd);

  if (kind === "user") {
    const o = ctx.createOscillator();
    o.type = "sine";
    o.frequency.setValueAtTime(620, now);
    o.connect(master);
    o.start(now);
    o.stop(now + 0.06);
  } else if (kind === "assistant") {
    const freqs = [523.25, 659.25];
    freqs.forEach((freq, i) => {
      const o = ctx.createOscillator();
      o.type = "sine";
      const t = now + i * 0.08;
      o.frequency.setValueAtTime(freq, t);
      o.connect(master);
      o.start(t);
      o.stop(t + 0.11);
    });
  } else if (kind === "error") {
    const o = ctx.createOscillator();
    o.type = "triangle";
    o.frequency.setValueAtTime(220, now);
    o.frequency.exponentialRampToValueAtTime(105, now + 0.14);
    o.connect(master);
    o.start(now);
    o.stop(now + 0.16);
  }
}

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
 * @param {{ markdown?: boolean }} [opts]
 */
function fillCollapsibleChatBody(wrapper, fullText, opts) {
  const markdown = opts?.markdown === true;
  const t = String(fullText ?? "");
  wrapper.className = "chat-body" + (markdown ? " chat-body--markdown" : "");

  if (markdown) {
    wrapper.replaceChildren();
    const mdHtml = renderChatMarkdown(t);
    const inner = document.createElement("div");
    inner.className = "chat-body-md";
    if (mdHtml) {
      inner.innerHTML = mdHtml;
    } else {
      inner.classList.add("chat-body-md-fallback");
      inner.textContent = t;
    }
    if (t.length > CHAT_BODY_PREVIEW_MAX) {
      inner.classList.add("chat-body-md--clamped");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-body-expand";
      btn.textContent = "Show more";
      btn.setAttribute("aria-expanded", "false");
      btn.addEventListener("click", () => {
        const expanded = inner.classList.toggle("chat-body-md--expanded");
        btn.setAttribute("aria-expanded", String(expanded));
        btn.textContent = expanded ? "Show less" : "Show more";
      });
      wrapper.appendChild(inner);
      wrapper.appendChild(btn);
    } else {
      wrapper.appendChild(inner);
    }
    return;
  }

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
  fillCollapsibleChatBody(body, text || "(no reply)", { markdown: true });

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
  const ollamaUrl = document.getElementById("ollama-url");
  const prov = document.getElementById("llm-provider");
  const modelSel = document.getElementById("llm-model");
  const text = String(userText || "").trim();
  if (!text) return;

  stopChatSpeech();

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

  chatRequestInFlight = true;
  syncChatInputChrome();
  if (useInternalChunk) showStudyProgressInline();
  try {
    appendChatMessage("user", text);
    playChatSound("user");
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
    if (voiceChatEnabled()) speakChatReply(replyText);
    else playChatSound("assistant");
    if (data.tool_log && data.tool_log.length) {
      await refreshGraph();
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (voiceChatEnabled()) speakChatReply(`Sorry. ${msg}`);
    else playChatSound("error");
    appendChatMessage("assistant", "Error: " + msg);
    toast(msg, "error");
  } finally {
    hideStudyProgressInline();
    chatRequestInFlight = false;
    syncChatInputChrome();
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
    nested_topic: "nested fields (same topic)",
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
  if (operation === "nested_topic") {
    return (
      `Memory reorganize: ${label}.\n\n` +
      `Criteria / intent: ${goals}\n\n` +
      `**Do not ask the user which topic.** Scan the whole graph yourself using tools.\n\n` +
      `Goal: **Group related fields inside the same topic**—one json bundle (\`nest_key\`), **no** new Topic node, **no** RELATED edge, **no** ref on the bundle. ` +
      `Write: **memory_nest_fields_in_topic**; undo: **memory_unnest_fields_in_topic**.\n\n` +
      `Phase A — schema-only sweep (no values): Call **memory_topics_schema_page** in a loop. Start \`offset=0\`, \`limit\` 15–50. ` +
      `Each response has \`topics\`, \`total\`, \`has_more\`, \`next_offset\`. Repeat with \`offset = next_offset\` until \`has_more\` is false. ` +
      `From **field names, field_type, ref_topic_id, nested_field_names** only, mark topics that look overloaded with many related flat attributes (same subject, many sibling fields). Skip topics with few fields or already-clean structure.\n\n` +
      `Phase B — confirm, then nest: For **each** flagged \`topic_id\` only, call **memory_get_topic_schema** with detail **current** (or memory_get_topic if needed). ` +
      `If current values support a sensible group name, call **memory_nest_fields_in_topic** with \`field_names\` and \`nest_key\`. ` +
      `If uncertain, skip that topic. Summarize counts and examples—do **not** paste long UUID lists unless asked.\n\n` +
      `Rules: Do **not** use memory_promote_fields_to_nested_topic for this (separate Topic + edge). ` +
      `Do **not** use memory_reorganize_split_topics to “nest”. The UI topic wizard can nest/unnest manually.`
    );
  }
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
  const soundEl = document.getElementById("chat-sound-enabled");
  if (soundEl && soundEl instanceof HTMLInputElement) {
    const saved = localStorage.getItem(LS_CHAT_SOUND);
    soundEl.checked = saved === null ? true : saved === "1";
    soundEl.addEventListener("change", () => {
      localStorage.setItem(LS_CHAT_SOUND, soundEl.checked ? "1" : "0");
      if (soundEl.checked) playChatSound("assistant");
    });
  }
  const voiceEl = document.getElementById("chat-voice-enabled");
  if (voiceEl && voiceEl instanceof HTMLInputElement) {
    voiceEl.checked = localStorage.getItem(LS_CHAT_VOICE) === "1";
    voiceEl.addEventListener("change", () => {
      localStorage.setItem(LS_CHAT_VOICE, voiceEl.checked ? "1" : "0");
      refreshChatVoiceMicHint();
    });
  }
  wireChatVoiceControls(input);
  syncChatInputChrome();
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
    stopChatSpeech();
    input.value = "";
    await runChatTurn(text);
  });
}

/* ── Topic wizard (graph click) ── */

async function loadDetail(topicId) {
  return api(`/api/ui/topics/${encodeURIComponent(topicId)}`);
}

async function loadFieldDetail(topicId, fieldName) {
  return api(
    `/api/ui/topics/${encodeURIComponent(topicId)}/fields/${encodeURIComponent(fieldName)}?with_history=true`
  );
}

function hideFieldWizard() {
  const root = document.getElementById("field-wizard");
  const body = document.getElementById("field-wizard-body");
  if (body) body.innerHTML = "";
  if (root) root.hidden = true;
}

/**
 * @param {{ topic_id: string, topic_title?: string, field_name: string, field_type?: string, ref_topic_id?: string | null, history?: unknown[] }} payload
 */
function showFieldWizard(payload) {
  const root = document.getElementById("field-wizard");
  const titleEl = document.getElementById("field-wizard-title");
  const body = document.getElementById("field-wizard-body");
  if (!root || !titleEl || !body) return;

  const topicId = String(payload.topic_id || "").trim();
  const fieldName = String(payload.field_name || "").trim() || "Field";
  const topicTitle = String(payload.topic_title || "").trim() || getWizardRefLinkLabel(topicId);

  titleEl.textContent = fieldName;
  const parts = [];
  parts.push(
    `<button type="button" class="field-wizard-topic-link" data-topic-id="${escapeHtml(topicId)}" title="Open topic">` +
      `<span>Topic: <strong>${escapeHtml(topicTitle)}</strong></span>` +
      `<code>${escapeHtml(topicId)}</code>` +
      `</button>`
  );
  parts.push('<section class="topic-wizard-section">');
  parts.push('<dl class="topic-wizard-dl">');
  parts.push(`<dt>Field</dt><dd>${escapeHtml(fieldName)}</dd>`);
  if (payload.field_type != null && String(payload.field_type).trim()) {
    parts.push(`<dt>Type</dt><dd>${escapeHtml(String(payload.field_type))}</dd>`);
  }
  if (payload.ref_topic_id) {
    const rid = String(payload.ref_topic_id).trim();
    parts.push(
      `<dt>Ref topic</dt><dd class="topic-wizard-ref-dd"><div class="topic-wizard-ref-single">${formatWizardRefLinkRowHtml(rid, getWizardRefLinkLabel(rid), null)}</div></dd>`
    );
  }
  parts.push("</dl>");
  parts.push(
    renderFieldTimelineHtml(Array.isArray(payload.history) ? payload.history : [], {
      variant: "compact",
    }),
  );
  parts.push("</section>");
  body.innerHTML = parts.join("");

  root.hidden = false;
  document.body.classList.add("topic-wizard-open");
}

/**
 * @param {HTMLElement} body
 */
async function handleTopicWizardNestInTopic(body) {
  const sec = body.querySelector(".topic-wizard-nest-in-topic");
  const st = body.querySelector("#topic-wizard-nest-status");
  if (!sec || !st) return;
  const topicId = sec.getAttribute("data-topic-id");
  const checks = sec.querySelectorAll('input[name="nest-field"]:checked');
  const field_names = Array.from(checks)
    .map((c) => c.value)
    .filter(Boolean);
  const nestKeyEl = sec.querySelector("#topic-wizard-nest-key");
  const nest_key = nestKeyEl && nestKeyEl.value ? nestKeyEl.value.trim() : "";
  if (!topicId || !field_names.length || !nest_key) {
    st.hidden = false;
    st.textContent = "Select at least one field and enter a group field name (e.g. professional_details).";
    st.classList.add("topic-wizard-promote-status--err");
    return;
  }
  st.hidden = false;
  st.classList.remove("topic-wizard-promote-status--err");
  st.textContent = "Working…";
  try {
    await api(`/api/ui/topics/${encodeURIComponent(topicId)}/nest-fields`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field_names, nest_key }),
    });
    st.textContent = `Grouped into field “${nest_key}”.`;
    await refreshGraph();
    showTopicWizard(await loadDetail(topicId));
    setStatus("Nested fields on same topic");
    toast("Fields nested");
  } catch (err) {
    st.classList.add("topic-wizard-promote-status--err");
    st.textContent = String(err.message || err);
    setStatus(String(err.message || err), true);
  }
}

/**
 * @param {string} topicId
 * @param {string} nestKey
 */
async function handleTopicWizardUnnestBundle(topicId, nestKey) {
  if (!topicId || !nestKey) return;
  if (!confirm("Restore nested fields to the top level of this topic?")) return;
  try {
    await api(`/api/ui/topics/${encodeURIComponent(topicId)}/unnest-fields`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nest_key: nestKey }),
    });
    await refreshGraph();
    showTopicWizard(await loadDetail(topicId));
    setStatus("Restored top-level fields");
    toast("Unnested");
  } catch (err) {
    setStatus(String(err.message || err), true);
    toast(String(err.message || err), "error");
  }
}

/**
 * @param {string} parentId
 * @param {string} childId
 * @param {string} [relationshipKind]
 */
async function handleTopicWizardUndoNested(parentId, childId, relationshipKind) {
  if (!parentId || !childId) return;
  if (
    !confirm(
      "Merge this nested topic back into the parent and delete the child topic?\n\nOther links to the child will be removed."
    )
  ) {
    return;
  }
  const payload = { child_topic_id: childId };
  if (relationshipKind && String(relationshipKind).trim()) {
    payload.relationship_kind = String(relationshipKind).trim();
  }
  try {
    await api(`/api/ui/topics/${encodeURIComponent(parentId)}/undo-nested`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await refreshGraph();
    const parentTopic = await loadDetail(parentId);
    showTopicWizard(parentTopic);
    setStatus("Merged nested topic into parent");
    toast("Undo nesting complete");
  } catch (err) {
    setStatus(String(err.message || err), true);
    toast(String(err.message || err), "error");
  }
}

function wireTopicWizard() {
  const body = document.getElementById("topic-wizard-body");
  if (body && !body.dataset.refLinksDelegated) {
    body.dataset.refLinksDelegated = "1";
    body.addEventListener("click", (e) => {
      const fieldBtn = e.target.closest(".topic-wizard-field-name-btn");
      if (fieldBtn && body.contains(fieldBtn)) {
        e.preventDefault();
        const fieldName = fieldBtn.getAttribute("data-field-name") || "";
        const t = graphView.wizardTopicPayload;
        const tid = t && t.id != null ? String(t.id) : "";
        if (!tid || !fieldName) return;
        void (async () => {
          try {
            const fd = await loadFieldDetail(tid, fieldName);
            showFieldWizard({
              topic_id: tid,
              topic_title: (t && t.title) || "",
              field_name: fieldName,
              field_type: fd.field_type,
              ref_topic_id: fd.ref_topic_id,
              history: fd.history,
            });
          } catch (err) {
            toast(String(err.message || err), "error");
          }
        })();
        return;
      }
      const undoBtn = e.target.closest(".btn-topic-wizard-undo-nested");
      if (undoBtn && body.contains(undoBtn)) {
        e.preventDefault();
        const p = undoBtn.getAttribute("data-undo-parent");
        const c = undoBtn.getAttribute("data-undo-child");
        const k = undoBtn.getAttribute("data-undo-kind") || "";
        if (p && c) void handleTopicWizardUndoNested(p, c, k);
        return;
      }
      const unnestBundleBtn = e.target.closest(".btn-topic-wizard-unnest");
      if (unnestBundleBtn && body.contains(unnestBundleBtn)) {
        e.preventDefault();
        const tid = unnestBundleBtn.getAttribute("data-unnest-topic");
        const nk = unnestBundleBtn.getAttribute("data-unnest-key");
        if (tid && nk) void handleTopicWizardUnnestBundle(tid, nk);
        return;
      }
      const nestBtn = e.target.closest(".btn-topic-wizard-nest");
      if (nestBtn && body.contains(nestBtn)) {
        e.preventDefault();
        void handleTopicWizardNestInTopic(body);
        return;
      }
      const btn = e.target.closest(".topic-wizard-ref-link");
      if (!btn || !body.contains(btn)) return;
      e.preventDefault();
      const tid = btn.getAttribute("data-topic-id");
      if (tid) void expandGraphNode(tid);
    });
  }

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
    const fw = document.getElementById("field-wizard");
    if (fw && !fw.hidden) {
      hideFieldWizard();
      e.preventDefault();
      return;
    }
    const menu = document.getElementById("graph-node-menu");
    if (menu && !menu.hidden) {
      hideGraphNodeMenu();
      e.preventDefault();
      return;
    }
    const w = document.getElementById("topic-wizard");
    if (!w || w.hidden) return;
    collapseGraphExpand({ restorePositions: true });
  });
}

function wireFieldWizard() {
  const root = document.getElementById("field-wizard");
  const backdrop = document.getElementById("field-wizard-backdrop");
  const closeBtn = document.getElementById("btn-field-wizard-close");
  const body = document.getElementById("field-wizard-body");
  if (!root || !body) return;

  function close() {
    hideFieldWizard();
    const tw = document.getElementById("topic-wizard");
    if (!tw || tw.hidden) document.body.classList.remove("topic-wizard-open");
  }

  backdrop?.addEventListener("click", close);
  closeBtn?.addEventListener("click", close);
  body.addEventListener("click", (e) => {
    const openTopicBtn = e.target.closest(".field-wizard-topic-link");
    if (openTopicBtn && body.contains(openTopicBtn)) {
      e.preventDefault();
      const tid = openTopicBtn.getAttribute("data-topic-id");
      if (tid) {
        close();
        void expandGraphNode(tid);
      }
      return;
    }
    const refBtn = e.target.closest(".topic-wizard-ref-link");
    if (refBtn && body.contains(refBtn)) {
      e.preventDefault();
      const tid = refBtn.getAttribute("data-topic-id");
      if (tid) void expandGraphNode(tid);
    }
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

  const systemForm = document.getElementById("form-system-context");
  if (systemForm) {
    systemForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(systemForm);
      const system_role = String(fd.get("system_role") || "").trim();
      const runtime_context = String(fd.get("runtime_context") || "").trim();
      const admin_key = String(fd.get("admin_key") || "").trim();
      if (!system_role || !runtime_context) {
        setStatus("Role and runtime context are required", true);
        return;
      }
      const extraHeaders = {};
      if (admin_key) extraHeaders["X-Admin-Key"] = admin_key;
      try {
        await api("/api/ui/system-context", {
          method: "PUT",
          headers: extraHeaders,
          body: JSON.stringify({ system_role, runtime_context }),
        });
        setStatus("Saved fixed system context");
        await refreshSystemContextCard();
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  }
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
  wireFieldWizard();
  await refreshSystemContextCard();
  await checkBackendBanner();
  await refreshGraph();
});
