const LS_KEY = "memstate_api_key";

/* ── Helpers ── */

function formatApiError(data) {
  const parts = [];
  if (data.detail != null) {
    parts.push(
      typeof data.detail === "object" ? JSON.stringify(data.detail) : String(data.detail)
    );
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

/* ── Graph (D3 force + zoom) ── */

const LABEL_MAX = 28;

/** Circle radius for topic nodes (labels + salience fit inside). */
const NODE_RADIUS = 44;
/** Stroke width on node circles (must match renderGraph). */
const NODE_STROKE_WIDTH = 2.5;
/**
 * Distance from node center to outer visible edge (fill + half stroke).
 * Edges are drawn between these boundaries so lines do not cross the disk.
 */
const EDGE_TRIM_RADIUS = NODE_RADIUS + NODE_STROKE_WIDTH / 2;
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

/** Line segment from source disk edge to target disk edge (not center-to-center). */
function linkEdgeEndpoints(sx, sy, tx, ty, trim) {
  const dx = tx - sx;
  const dy = ty - sy;
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) {
    return { x1: sx, y1: sy, x2: tx, y2: ty };
  }
  const ux = dx / len;
  const uy = dy / len;
  const half = len / 2 - 0.5;
  const t = half > 0 ? Math.min(trim, half) : 0;
  return {
    x1: sx + ux * t,
    y1: sy + uy * t,
    x2: tx - ux * t,
    y2: ty - uy * t,
  };
}

function tooltip(n) {
  const lines = [
    n.title || n.label,
    `kind: ${n.topic_kind || "—"}`,
    `salience: ${n.salience}`,
    `fields: ${(n.fields || []).length}`,
  ];
  for (const f of n.fields || []) {
    lines.push(
      `  ${f.name} (${f.field_type})${f.ref_topic_id ? " → " + f.ref_topic_id.slice(0, 8) : ""}`
    );
  }
  return lines.join("\n");
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
    return {
      id: n.id,
      labelLines: wrapTitleLines(raw, TITLE_CHARS_PER_LINE, TITLE_MAX_LINES),
      salience,
      salienceLabel: formatSalience(salience),
      fillOpacity: salienceToFillOpacity(salience, minS, maxS),
      title: tooltip(n),
      archived: !!n.archived,
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
      source: e.from,
      target: e.to,
      label: kind ? shortLabel(kind) : "",
      isRef: e.edge_type === "field_ref",
    });
  }
  return { nodes, links };
}

const graphView = {
  container: null,
  svg: null,
  gZoom: null,
  gPlot: null,
  zoom: null,
  simulation: null,
  width: 400,
  height: 300,
  resizeObserver: null,
};

function measureGraph() {
  if (!graphView.container) return;
  const w = graphView.container.clientWidth;
  const h = graphView.container.clientHeight;
  graphView.width = Math.max(w, 80);
  graphView.height = Math.max(h, 80);
  if (graphView.svg) {
    graphView.svg.attr("viewBox", `0 0 ${graphView.width} ${graphView.height}`);
  }
}

function graphDrag(simulation) {
  function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.35).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
  }
  function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
  }
  function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
  }
  return d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended);
}

function fitGraphView(nodes) {
  if (!graphView.svg || !graphView.zoom || !nodes.length) return;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    if (n.x == null || n.y == null) continue;
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y);
  }
  if (!isFinite(minX)) return;
  const pad = 100;
  const bw = Math.max(maxX - minX, 100);
  const bh = Math.max(maxY - minY, 100);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const k = Math.min(
    (graphView.width - 2 * pad) / bw,
    (graphView.height - 2 * pad) / bh,
    2.5
  );
  const tx = graphView.width / 2 - k * cx;
  const ty = graphView.height / 2 - k * cy;
  graphView.svg
    .transition()
    .duration(450)
    .call(graphView.zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
}

function resetGraphZoom() {
  if (!graphView.svg || !graphView.zoom) return;
  graphView.svg.transition().duration(280).call(graphView.zoom.transform, d3.zoomIdentity);
}

function initGraph(container) {
  container.innerHTML = "";
  graphView.container = container;
  measureGraph();

  const svg = d3
    .select(container)
    .append("svg")
    .attr("class", "graph-svg")
    .attr("role", "img")
    .attr("aria-label", "Topic graph: wheel to zoom, drag background to pan, drag nodes to rearrange, double-click to reset zoom");

  const defs = svg.append("defs");
  defs
    .append("marker")
    .attr("id", "memstate-arrow-related")
    .attr("viewBox", "0 0 10 10")
    .attr("refX", 10)
    .attr("refY", 5)
    .attr("markerWidth", 6)
    .attr("markerHeight", 6)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M 0 0 L 10 5 L 0 10 z")
    .attr("fill", "#60a5fa");
  defs
    .append("marker")
    .attr("id", "memstate-arrow-ref")
    .attr("viewBox", "0 0 10 10")
    .attr("refX", 10)
    .attr("refY", 5)
    .attr("markerWidth", 6)
    .attr("markerHeight", 6)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M 0 0 L 10 5 L 0 10 z")
    .attr("fill", "#22c55e");

  const gZoom = svg.append("g").attr("class", "graph-zoom-layer");
  const gPlot = gZoom.append("g").attr("class", "graph-plot");

  const zoom = d3
    .zoom()
    .scaleExtent([0.08, 12])
    .on("zoom", (event) => {
      gZoom.attr("transform", event.transform);
    });

  svg.call(zoom);
  svg.on("dblclick.zoom", null);
  svg.on("dblclick", (event) => {
    if (event.target === svg.node()) resetGraphZoom();
  });

  graphView.svg = svg;
  graphView.gZoom = gZoom;
  graphView.gPlot = gPlot;
  graphView.zoom = zoom;

  graphView.resizeObserver = new ResizeObserver(() => {
    measureGraph();
    if (graphView.simulation) {
      graphView.simulation.force(
        "center",
        d3.forceCenter(graphView.width / 2, graphView.height / 2)
      );
      graphView.simulation.alpha(0.2).restart();
    }
  });
  graphView.resizeObserver.observe(container);
}

function renderGraph(apiData) {
  const { nodes: nodeIn, links: linkIn } = buildGraphData(apiData);
  measureGraph();
  updateEmptyState(nodeIn.length);

  if (graphView.simulation) {
    graphView.simulation.stop();
    graphView.simulation = null;
  }
  graphView.gPlot.selectAll("*").remove();

  if (!nodeIn.length) return;

  const nodes = nodeIn.map((d) => ({ ...d }));
  const links = linkIn.map((d) => ({ ...d }));

  const simulation = d3
    .forceSimulation(nodes)
    .force(
      "link",
      d3
        .forceLink(links)
        .id((d) => d.id)
        .distance(180)
        .strength(0.55)
    )
    .force("charge", d3.forceManyBody().strength(-520))
    .force("center", d3.forceCenter(graphView.width / 2, graphView.height / 2))
    .force("collide", d3.forceCollide(NODE_RADIUS + 6))
    .alphaDecay(0.022)
    .velocityDecay(0.35);

  graphView.simulation = simulation;

  const g = graphView.gPlot;
  const linkG = g.append("g").attr("class", "links");

  const linkLine = linkG
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("stroke", (d) => (d.isRef ? "#22c55e" : "#60a5fa"))
    .attr("stroke-width", (d) => (d.isRef ? 1.75 : 2.25))
    .attr("stroke-dasharray", (d) => (d.isRef ? "7 5" : null))
    .attr("stroke-opacity", 0.95)
    .attr("marker-end", (d) =>
      d.isRef ? "url(#memstate-arrow-ref)" : "url(#memstate-arrow-related)"
    );

  const linkLbl = linkG
    .selectAll("text.link-label")
    .data(links.filter((l) => l.label))
    .join("text")
    .attr("class", "link-label")
    .attr("fill", "#cbd5e1")
    .attr("font-size", 10)
    .attr("font-family", "Inter, Segoe UI, system-ui, sans-serif")
    .attr("text-anchor", "middle")
    .attr("pointer-events", "none")
    .text((d) => d.label);

  const nodeG = g
    .append("g")
    .attr("class", "nodes")
    .selectAll("g.node")
    .data(nodes)
    .join("g")
    .attr("class", "node")
    .style("cursor", "grab")
    .call(graphDrag(simulation))
    .on("click", (event, d) => {
      event.stopPropagation();
      loadDetail(d.id);
    })
    .on("dblclick", (event) => event.stopPropagation());

  nodeG
    .append("circle")
    .attr("r", NODE_RADIUS)
    .attr("fill", (d) => (d.archived ? "#334155" : "#1e40af"))
    .attr("fill-opacity", (d) => d.fillOpacity)
    .attr("stroke", (d) => (d.archived ? "#64748b" : "#93c5fd"))
    .attr("stroke-width", NODE_STROKE_WIDTH);

  const labelG = nodeG
    .append("g")
    .attr("class", "node-inner-label")
    .attr("pointer-events", "none");

  labelG.each(function (d) {
    const g = d3.select(this);
    const lines = d.labelLines || ["—"];
    const n = lines.length;
    const gap = 4;
    const titleBlockH = (n - 1) * TITLE_LINE_HEIGHT;
    const firstY = -(titleBlockH / 2) - (SALIENCE_FONT_SIZE + gap) / 2;

    lines.forEach((line, i) => {
      g.append("text")
        .attr("text-anchor", "middle")
        .attr("y", firstY + i * TITLE_LINE_HEIGHT)
        .attr("dominant-baseline", "middle")
        .attr("fill", "#f1f5f9")
        .attr("font-size", TITLE_FONT_SIZE)
        .attr("font-family", "Inter, Segoe UI, system-ui, sans-serif")
        .text(line);
    });

    const salY = firstY + n * TITLE_LINE_HEIGHT + gap + SALIENCE_FONT_SIZE / 2;
    g.append("text")
      .attr("class", "node-salience")
      .attr("text-anchor", "middle")
      .attr("y", salY)
      .attr("dominant-baseline", "middle")
      .attr("fill", "#38bdf8")
      .attr("font-size", SALIENCE_FONT_SIZE)
      .attr("font-family", "Inter, Segoe UI, system-ui, sans-serif")
      .attr("opacity", 0.92)
      .text(d.salienceLabel);
  });

  nodeG.append("title").text((d) => d.title);

  let fitted = false;
  simulation.on("tick", () => {
    linkLine.each(function (d) {
      const p = linkEdgeEndpoints(
        d.source.x,
        d.source.y,
        d.target.x,
        d.target.y,
        EDGE_TRIM_RADIUS
      );
      d3.select(this).attr("x1", p.x1).attr("y1", p.y1).attr("x2", p.x2).attr("y2", p.y2);
    });

    linkLbl.each(function (d) {
      const p = linkEdgeEndpoints(
        d.source.x,
        d.source.y,
        d.target.x,
        d.target.y,
        EDGE_TRIM_RADIUS
      );
      d3.select(this).attr("x", (p.x1 + p.x2) / 2).attr("y", (p.y1 + p.y2) / 2);
    });

    nodeG.attr("transform", (d) => `translate(${d.x},${d.y})`);
  });

  simulation.on("end", () => {
    if (!fitted) {
      fitted = true;
      fitGraphView(nodes);
    }
  });
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

/* ── LLM chat (Ollama + memory tools) ── */

const chatHistory = [];

function appendChatMessage(role, text) {
  const log = document.getElementById("chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = role === "user" ? "You" : "Assistant";
  const body = document.createElement("div");
  body.textContent = text;
  div.appendChild(roleEl);
  div.appendChild(body);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function wireChat() {
  const form = document.getElementById("form-chat");
  const input = document.getElementById("chat-input");
  const btn = document.getElementById("btn-chat-send");
  if (!form || !input || !btn) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    appendChatMessage("user", text);
    chatHistory.push({ role: "user", content: text });
    btn.disabled = true;
    try {
      const data = await api("/api/llm/chat", {
        method: "POST",
        body: JSON.stringify({ messages: chatHistory }),
      });
      chatHistory.push({ role: "assistant", content: data.reply || "" });
      appendChatMessage("assistant", data.reply || "(no reply)");
      if (data.tool_log && data.tool_log.length) {
        const line = data.tool_log.map((x) => x.tool).join(" · ");
        const log = document.getElementById("chat-log");
        const div = document.createElement("div");
        div.className = "chat-msg tools";
        div.innerHTML = `<div class="role">Tools</div><div>${escapeHtml(line)}</div>`;
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
        await refreshGraph();
      }
    } catch (err) {
      appendChatMessage("assistant", "Error: " + err.message);
      toast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  });
}

/* ── Detail ── */

async function loadDetail(topicId) {
  const pre = document.getElementById("detail");
  pre.textContent = "Loading…";
  try {
    const t = await api(`/api/ui/topics/${encodeURIComponent(topicId)}`);
    pre.textContent = JSON.stringify(t, null, 2);
  } catch (e) {
    pre.textContent = "Error: " + e.message;
  }
}

/* ── Copy detail ── */

function wireCopyDetail() {
  const btn = document.getElementById("btn-copy-detail");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const pre = document.getElementById("detail");
    if (!pre || !pre.textContent) return;
    navigator.clipboard.writeText(pre.textContent).then(
      () => toast("Copied to clipboard"),
      () => toast("Copy failed", "error")
    );
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
      document.getElementById("detail").textContent = "";
      await refreshGraph();
    } catch (err) {
      setStatus(err.message, true);
    }
  });
}

/* ── Init ── */

document.addEventListener("DOMContentLoaded", async () => {
  const container = document.getElementById("network");
  if (typeof d3 === "undefined") {
    container.textContent = "D3 failed to load.";
    return;
  }
  initGraph(container);

  wireCollapsible();
  wireForms();
  wireChat();
  wireCopyDetail();
  await checkBackendBanner();
  await refreshGraph();
});
