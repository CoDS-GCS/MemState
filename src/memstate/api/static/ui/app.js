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

function tooltip(n) {
  const lines = [
    n.title || n.label,
    `kind: ${n.topic_kind || "—"}`,
    `salience: ${n.salience}`,
    `fields: ${(n.fields || []).length}`,
  ];
  if (n.community != null && Number.isFinite(Number(n.community))) {
    lines.push(`community: ${n.community} (embedding + refs)`);
  }
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
    const comm =
      n.community != null && Number.isFinite(Number(n.community)) ? Number(n.community) : null;
    return {
      id: String(n.id ?? "").trim(),
      labelLines: wrapTitleLines(raw, TITLE_CHARS_PER_LINE, TITLE_MAX_LINES),
      salience,
      salienceLabel: formatSalience(salience),
      fillOpacity: salienceToFillOpacity(salience, minS, maxS),
      title: tooltip({ ...n, community: comm }),
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
};

function buildVisDatasets(nodes, links) {
  const { clusterOf } = computeClusters(nodes, links);
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
    return {
      id: n.id,
      label,
      title: n.title,
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
      iterations: 220,
      updateInterval: 25,
      fit: true,
    },
    barnesHut: {
      gravitationalConstant: -2200,
      centralGravity: 0.14,
      springLength: 130,
      springConstant: 0.055,
      damping: 0.52,
      avoidOverlap: 0.45,
    },
  },
  layout: { improvedLayout: true },
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

function renderGraph(apiData) {
  const { nodes: nodeIn, links: linkIn } = buildGraphData(apiData);
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

  if (!nodeIn.length) return;

  const nodes = nodeIn.map((d) => ({ ...d }));
  const links = linkIn.map((d) => ({ ...d }));
  const { visNodes, visEdges } = buildVisDatasets(nodes, links);

  const data = {
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  };

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
    if (params.nodes.length) loadDetail(params.nodes[0]);
  });

  net.on("doubleClick", (params) => {
    if (params.nodes.length === 0 && params.edges.length === 0) {
      net.fit({ animation: { duration: 320 } });
    }
  });

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

const OLLAMA_MODELS = [
  { value: "llama3.2:latest", label: "llama3.2" },
  { value: "qwen2.5:latest", label: "qwen2.5" },
];
const GROQ_MODELS = [
  { value: "openai/gpt-oss-20b", label: "GPT-OSS 20B" },
  { value: "openai/gpt-oss-120b", label: "GPT-OSS 120B" },
];

const chatHistory = [];

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
  body.className = "chat-body";
  body.textContent = text;
  div.appendChild(roleEl);
  div.appendChild(body);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

/**
 * Assistant reply with expandable "Thinking" trace (provider, model, tool calls + results).
 * @param {string} text
 * @param {{ provider?: string, model?: string, intent?: string, tool_log?: { tool: string, result: unknown }[] }} [meta]
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
  body.className = "chat-body";
  body.textContent = text || "(no reply)";

  const toolLog = Array.isArray(meta?.tool_log) ? meta.tool_log : [];
  const hasTools = toolLog.length > 0;

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
  toggleLabel.textContent = hasTools ? "Thinking & tool trace" : "How this answer was built";
  toggle.appendChild(chev);
  toggle.appendChild(toggleLabel);

  const panel = document.createElement("div");
  panel.className = "chat-thinking-body";
  panel.hidden = true;

  const metaLine = document.createElement("div");
  metaLine.className = "chat-thinking-meta";
  const route = meta?.intent ? ` · ${meta.intent}` : "";
  metaLine.textContent = `${meta?.provider || "—"} · ${meta?.model || "—"}${route}`;
  panel.appendChild(metaLine);

  if (hasTools) {
    toolLog.forEach((entry, i) => {
      const step = document.createElement("div");
      step.className = "chat-thinking-step";
      const nameEl = document.createElement("div");
      nameEl.className = "chat-thinking-tool-name";
      nameEl.textContent = `${i + 1}. ${entry.tool || "(unknown)"}`;
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
    appendChatMessage("user", text);
    chatHistory.push({ role: "user", content: text });
    btn.disabled = true;
    try {
      const provider = prov?.value || "ollama";
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
      chatHistory.push({ role: "assistant", content: data.reply || "" });
      appendAssistantMessage(data.reply || "(no reply)", {
        provider: data.provider,
        model: data.model,
        intent: data.intent,
        tool_log: data.tool_log || [],
      });
      if (data.tool_log && data.tool_log.length) {
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
  if (typeof vis === "undefined" || !vis.Network || !vis.DataSet) {
    container.textContent = "vis-network failed to load.";
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
