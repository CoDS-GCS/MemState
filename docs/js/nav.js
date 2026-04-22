/**

 * MemState docs — nav.js

 * Sidebar · audience strip · dev notes · theme · TOC · code tabs

 */

(function () {

  "use strict";



  var THEME_KEY = "ms-theme";

  (function () {

    var t = "dark";

    try {

      var stored = localStorage.getItem(THEME_KEY);

      if (stored === "light" || stored === "dark") {

        t = stored;

      } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {

        t = "light";

      }

    } catch (_) {}

    document.documentElement.setAttribute("data-theme", t);

  })();



  var page = document.body ? document.body.getAttribute("data-doc-page") || "" : "";

  var audience = document.body ? document.body.getAttribute("data-doc-audience") || "developer" : "developer";



  function rootBase() {

    if (!page || page === "index") return "./";

    var depth = page.split("/").filter(Boolean).length - 1;

    return depth > 0 ? "../".repeat(depth) : "./";

  }



  var rb = rootBase();



  function partnerRelPath() {

    if (audience === "product") {

      if (page === "index") return "developer/index";

      if (page.indexOf("product/") === 0) {

        var rest = page.slice("product/".length);

        if (rest === "developers/integration") return "developers/quickstart";

        return rest;

      }

      return null;

    }

    if (audience === "developer") {

      if (page === "developer/index") return "index";

      if (page === "developers/quickstart") return "product/developers/integration";

      return "product/" + page;

    }

    return null;

  }



  function partnerHref() {

    var pr = partnerRelPath();

    if (!pr) return null;

    return rb + pr + ".html";

  }



  var productSections = [

    {

      title: "Product",

      items: [{ id: "index", href: rb + "index.html", label: "Overview" }],

    },

    {

      title: "Using MemState",

      items: [

        {

          id: "product/developers/integration",

          href: rb + "product/developers/integration.html",

          label: "Agent integration",

        },

      ],

    },

    {

      title: "Capabilities",

      items: [

        { id: "product/data-model/overview", href: rb + "product/data-model/overview.html", label: "Topic memory" },

        { id: "product/data-model/fields", href: rb + "product/data-model/fields.html", label: "Field history" },

        { id: "product/data-model/relationships", href: rb + "product/data-model/relationships.html", label: "Links between topics" },

        { id: "product/data-model/limits-and-config", href: rb + "product/data-model/limits-and-config.html", label: "Retention and retrieval" },

        { id: "product/data-model/diagram", href: rb + "product/data-model/diagram.html", label: "Visual maps" },

      ],

    },

    {

      title: "How it runs",

      items: [

        { id: "product/architecture/overview", href: rb + "product/architecture/overview.html", label: "System shape" },

        { id: "product/architecture/storage", href: rb + "product/architecture/storage.html", label: "Durability" },

        { id: "product/architecture/reasoning", href: rb + "product/architecture/reasoning.html", label: "Background care" },

        { id: "product/architecture/http-stack", href: rb + "product/architecture/http-stack.html", label: "Ways to talk to MemState" },

      ],

    },

    {

      title: "Operations",

      items: [

        { id: "product/operations/ingest", href: rb + "product/operations/ingest.html", label: "Observations" },

        { id: "product/operations/query", href: rb + "product/operations/query.html", label: "Context retrieval" },

        { id: "product/operations/revision", href: rb + "product/operations/revision.html", label: "Cleaning duplicates" },

        { id: "product/operations/forget", href: rb + "product/operations/forget.html", label: "Letting memory fade" },

        { id: "product/operations/high-level", href: rb + "product/operations/high-level.html", label: "End-to-end flow" },

        { id: "product/operations/low-level", href: rb + "product/operations/low-level.html", label: "Power-user tools" },

        { id: "product/operations/run-config", href: rb + "product/operations/run-config.html", label: "Deployment choices" },

      ],

    },

    {

      title: "Interfaces",

      items: [{ id: "product/api/index", href: rb + "product/api/index.html", label: "What you can call" }],

    },

  ];



  var developerSections = [

    {

      title: "Product",

      items: [{ id: "___product", href: rb + "index.html", label: "Product overview" }],

    },

    {

      title: "Developers",

      items: [

        { id: "developer/index", href: rb + "developer/index.html", label: "Developer hub" },

        { id: "developers/quickstart", href: rb + "developers/quickstart.html", label: "Quickstart" },

        { id: "api/index", href: rb + "api/index.html", label: "API reference" },

      ],

    },

    {

      title: "Concepts",

      items: [

        { id: "data-model/overview", href: rb + "data-model/overview.html", label: "Topic model" },

        { id: "data-model/fields", href: rb + "data-model/fields.html", label: "Fields and history" },

        { id: "data-model/relationships", href: rb + "data-model/relationships.html", label: "Relationships and refs" },

        { id: "data-model/limits-and-config", href: rb + "data-model/limits-and-config.html", label: "Limits and stages" },

        { id: "data-model/diagram", href: rb + "data-model/diagram.html", label: "Diagrams" },

      ],

    },

    {

      title: "Architecture",

      items: [

        { id: "architecture/overview", href: rb + "architecture/overview.html", label: "Runtime overview" },

        { id: "architecture/storage", href: rb + "architecture/storage.html", label: "Storage and schema" },

        { id: "architecture/reasoning", href: rb + "architecture/reasoning.html", label: "Reasoner behavior" },

        { id: "architecture/http-stack", href: rb + "architecture/http-stack.html", label: "HTTP, UI, LLM" },

      ],

    },

    {

      title: "Operations",

      items: [

        { id: "operations/ingest", href: rb + "operations/ingest.html", label: "Ingest (observations)" },

        { id: "operations/query", href: rb + "operations/query.html", label: "Query (context)" },

        { id: "operations/revision", href: rb + "operations/revision.html", label: "Revision (internal)" },

        { id: "operations/forget", href: rb + "operations/forget.html", label: "Forget (internal)" },

        { id: "operations/high-level", href: rb + "operations/high-level.html", label: "High-level API flow" },

        { id: "operations/low-level", href: rb + "operations/low-level.html", label: "Low-level UI API" },

        { id: "operations/run-config", href: rb + "operations/run-config.html", label: "Run and configuration" },

      ],

    },

  ];



  var sections = audience === "product" ? productSections : developerSections;



  var DEV_IMPL_NOTES = {

    "data-model/overview": "Kuzu-backed topic nodes; embeddings default to 384 dimensions on title+summary text.",

    "data-model/fields": "Field JSON stores typed values and ordered revision stacks; Executor owns append semantics.",

    "data-model/relationships": "RELATED edges and field refs are merged in GraphStore; expansion depth is query-controlled.",

    "data-model/limits-and-config": "Thresholds and stage lists are settings-driven; some ladder stages are partial vs full paper model.",

    "data-model/diagram": "Mermaid sources are also exposed via the UI API for the live explorer.",

    "architecture/overview": "Single FastAPI process; BackgroundTasks for reasoner; shared deps singletons.",

    "architecture/storage": "Schema matches src store migrations; paths via MEMSTATE_KUZU_PATH.",

    "architecture/reasoning": "Revise + forget hooks run post-response; not all policy events are user-pluggable yet.",

    "architecture/http-stack": "Three routers share GraphStore; LLM path may bypass v1 ingest (see ingest dev page).",

    "operations/ingest": "Agent contract: observations in; MemState applies revise/forget internally. POST /v1/ingest may still require explicit placement in this build; LLM flows may use MemoryToolRunner instead.",

    "operations/query": "Agent-facing context retrieval: Executor runs semantic then optional structural and temporal enrich stages.",

    "operations/revision": "Internal after traffic; not an agent API. Duplicate merge is title-based today; semantic dedupe is roadmap.",

    "operations/forget": "Internal policy; not an agent API. Archive is non-destructive; summarize/detach stages are partial vs full ladder.",

    "operations/high-level": "Documents cross-module sequencing; verify against FastAPI route handlers when changing code.",

    "operations/low-level": "UI API is wider surface; less stability guarantees than /v1.",

    "operations/run-config": "Env vars in memstate.settings; defaults documented in repo README.",

    "api/index": "Route table generated from code inspection; update when adding routers.",

    "developers/quickstart": "Examples assume local uvicorn; API key optional when MEMSTATE_API_KEY unset.",

    "developer/index": "This hub links every technical page; product twin is the root overview.",

  };



  function injectSidebar() {

    var aside = document.getElementById("doc-sidebar");

    if (!aside) return;



    var tag =

      audience === "product"

        ? "What MemState does for agent memory"

        : "Implementation, APIs, and current behavior";



    var html = '<div class="sidebar-inner">';

    html += '<div class="sidebar-brand"><a href="' + rb + 'index.html">';

    html += '<span class="sidebar-logo-mark"></span>MemState</a></div>';

    html += '<p class="sidebar-tag">' + tag + "</p>";



    sections.forEach(function (sec) {

      html += '<section class="nav-section"><h3 class="nav-section-title">' + sec.title + "</h3><ul>";

      sec.items.forEach(function (it) {

        var active = it.id === page ? " is-active" : "";

        html +=

          '<li><a class="nav-link' + active + '" href="' + it.href +

          '" data-nav-id="' + it.id + '">' + it.label + "</a></li>";

      });

      html += "</ul></section>";

    });



    html += "</div>";

    aside.innerHTML = html;

  }



  function injectAudienceStrip() {

    var href = partnerHref();

    if (!href) return;

    var header = document.querySelector(".doc-inner > .page-header");

    if (!header || !header.parentNode) return;



    var strip = document.createElement("div");

    strip.className = "audience-strip";

    strip.setAttribute("role", "navigation");

    strip.setAttribute("aria-label", "Documentation edition");



    var tag = document.createElement("span");

    tag.className = "audience-strip__tag";

    tag.textContent = audience === "product" ? "Product guide" : "Developer docs";



    var a = document.createElement("a");

    a.className = "audience-strip__link";

    a.href = href;

    a.textContent =

      audience === "product"

        ? "Open technical edition for this topic"

        : "Open product guide for this topic";



    strip.appendChild(tag);

    strip.appendChild(document.createTextNode(" "));

    strip.appendChild(a);

    header.parentNode.insertBefore(strip, header.nextSibling);

  }



  function injectDevImplNote() {

    if (audience !== "developer") return;

    var text = DEV_IMPL_NOTES[page];

    if (!text) return;

    var main = document.querySelector(".page-main");

    if (!main) return;



    var aside = document.createElement("aside");

    aside.className = "dev-impl-note";

    aside.setAttribute("aria-label", "Implementation status");



    var h = document.createElement("h2");

    h.textContent = "Implementation notes";

    var p = document.createElement("p");

    p.textContent = text;



    aside.appendChild(h);

    aside.appendChild(p);

    main.appendChild(aside);

  }



  var SVG_SUN =

    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" ' +

    'stroke-linecap="round" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +

    '<circle cx="10" cy="10" r="3.5"/>' +

    '<path d="M10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2' +

    'M3.9 3.9l1.4 1.4M14.7 14.7l1.4 1.4M3.9 16.1l1.4-1.4M14.7 5.3l1.4-1.4"/>' +

    "</svg>";



  var SVG_MOON =

    '<svg viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +

    '<path d="M17.3 14.4A8 8 0 0 1 5.6 2.7a8.1 8.1 0 1 0 11.7 11.7z"/>' +

    "</svg>";



  function currentTheme() {

    return document.documentElement.getAttribute("data-theme") || "dark";

  }



  function setTheme(t) {

    document.documentElement.setAttribute("data-theme", t);

    try { localStorage.setItem(THEME_KEY, t); } catch (_) {}

  }



  function injectThemeToggle() {

    var header = document.querySelector(".page-header");

    if (!header) return;



    var btn = document.createElement("button");

    btn.id = "theme-toggle";

    btn.setAttribute("aria-label", "Toggle color theme");



    function sync() {

      var t = currentTheme();

      btn.innerHTML = t === "dark" ? SVG_SUN : SVG_MOON;

      btn.title = t === "dark" ? "Switch to light mode" : "Switch to dark mode";

    }



    btn.addEventListener("click", function () {

      setTheme(currentTheme() === "dark" ? "light" : "dark");

      sync();

    });



    sync();

    header.appendChild(btn);

  }



  function slugify(text) {

    return text

      .trim()

      .toLowerCase()

      .replace(/[^a-z0-9\s-]/g, "")

      .replace(/\s+/g, "-")

      .replace(/-+/g, "-")

      .replace(/^-|-$/g, "");

  }



  function injectTOC() {

    var main = document.querySelector(".page-main");

    if (!main) return;



    var headings = Array.prototype.slice.call(main.querySelectorAll("h2, h3"));

    if (headings.length < 3) return;



    headings.forEach(function (h) {

      if (!h.id) {

        h.id = slugify(h.textContent);

      }

    });



    var toc = document.createElement("aside");

    toc.id = "toc-panel";

    toc.setAttribute("aria-label", "On this page");



    var tocTitle = document.createElement("div");

    tocTitle.className = "toc-title";

    tocTitle.textContent = "On this page";

    toc.appendChild(tocTitle);



    var list = document.createElement("ul");

    list.className = "toc-list";



    headings.forEach(function (h) {

      var li = document.createElement("li");

      li.className = "toc-item" + (h.tagName === "H3" ? " toc-item--h3" : "");

      var a = document.createElement("a");

      a.href = "#" + h.id;

      a.className = "toc-link";

      a.textContent = h.textContent.trim();

      li.appendChild(a);

      list.appendChild(li);

    });



    toc.appendChild(list);



    var footer = main.nextElementSibling;

    var docBody = document.createElement("div");

    docBody.className = "doc-body";

    main.parentNode.insertBefore(docBody, main);

    docBody.appendChild(main);

    docBody.appendChild(toc);



    if (footer && footer.classList && footer.classList.contains("page-footer")) {

      docBody.parentNode.insertBefore(footer, docBody.nextSibling);

    }



    var tocLinks = Array.prototype.slice.call(list.querySelectorAll(".toc-link"));

    var raf = null;



    function updateActive() {

      var threshold = 80;

      var active = headings[0];



      for (var i = 0; i < headings.length; i++) {

        var top = headings[i].getBoundingClientRect().top;

        if (top < threshold) {

          active = headings[i];

        } else {

          break;

        }

      }



      tocLinks.forEach(function (a) {

        var on = active && a.getAttribute("href") === "#" + active.id;

        if (on) a.classList.add("is-active");

        else    a.classList.remove("is-active");

      });

    }



    window.addEventListener(

      "scroll",

      function () {

        if (raf) cancelAnimationFrame(raf);

        raf = requestAnimationFrame(updateActive);

      },

      { passive: true }

    );



    updateActive();

  }



  function initCodeTabs() {

    var groups = document.querySelectorAll(".code-tabs");

    groups.forEach(function (group) {

      var tabs = Array.prototype.slice.call(group.querySelectorAll(".code-tabs__tab"));

      var panels = Array.prototype.slice.call(group.querySelectorAll(".code-tabs__panel"));

      if (!tabs.length || !panels.length) return;



      function activate(idx) {

        tabs.forEach(function (t, i) {

          t.setAttribute("aria-selected", i === idx ? "true" : "false");

          t.setAttribute("tabindex", i === idx ? "0" : "-1");

        });

        panels.forEach(function (p, i) {

          p.setAttribute("data-active", i === idx ? "true" : "false");

        });

      }



      tabs.forEach(function (tab, i) {

        tab.setAttribute("role", "tab");

        tab.setAttribute("aria-selected", i === 0 ? "true" : "false");

        tab.setAttribute("tabindex", i === 0 ? "0" : "-1");

        tab.addEventListener("click", function () { activate(i); });

        tab.addEventListener("keydown", function (e) {

          if (e.key === "ArrowRight") { activate((i + 1) % tabs.length); tabs[(i + 1) % tabs.length].focus(); }

          if (e.key === "ArrowLeft")  { activate((i - 1 + tabs.length) % tabs.length); tabs[(i - 1 + tabs.length) % tabs.length].focus(); }

        });

      });

      panels.forEach(function (p, i) { p.setAttribute("data-active", i === 0 ? "true" : "false"); });

    });

  }



  injectSidebar();

  injectAudienceStrip();

  injectThemeToggle();

  injectTOC();

  injectDevImplNote();

  initCodeTabs();

})();


