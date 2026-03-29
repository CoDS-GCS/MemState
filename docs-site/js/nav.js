/**
 * MemState docs — nav.js
 * Handles: sidebar injection · theme toggle · right-side TOC · scroll spy
 */
(function () {
  "use strict";

  /* -------------------------------------------------------
     0. Apply saved theme immediately (prevents FOUC)
     ------------------------------------------------------- */
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

  /* -------------------------------------------------------
     1. Sidebar nav injection
     ------------------------------------------------------- */
  function hrefBase() {
    var path = decodeURIComponent(window.location.pathname).replace(/\\/g, "/");
    var marker = "/docs-site/";
    var idx = path.toLowerCase().indexOf(marker);
    if (idx === -1) {
      var m = path.match(/docs-site\/(.+)/i);
      if (!m) return "./";
      var depth = m[1].split("/").filter(Boolean).length - 1;
      return depth > 0 ? "../".repeat(depth) : "./";
    }
    var rest = path.slice(idx + marker.length);
    var depth = rest.split("/").filter(Boolean).length - 1;
    return depth > 0 ? "../".repeat(depth) : "./";
  }

  var b = hrefBase();
  var page = document.body ? document.body.getAttribute("data-doc-page") || "" : "";

  var sections = [
    {
      title: "Home",
      items: [{ id: "index", href: b + "index.html", label: "System home" }],
    },
    {
      title: "Architecture",
      items: [
        { id: "architecture/overview",   href: b + "architecture/overview.html",   label: "Runtime overview" },
        { id: "architecture/storage",    href: b + "architecture/storage.html",    label: "Storage and schema" },
        { id: "architecture/reasoning",  href: b + "architecture/reasoning.html",  label: "Reasoner behavior" },
        { id: "architecture/http-stack", href: b + "architecture/http-stack.html", label: "HTTP, UI, LLM" },
      ],
    },
    {
      title: "Data Model",
      items: [
        { id: "data-model/overview",          href: b + "data-model/overview.html",          label: "Topic model" },
        { id: "data-model/fields",            href: b + "data-model/fields.html",            label: "Fields and history" },
        { id: "data-model/relationships",     href: b + "data-model/relationships.html",     label: "Relationships and refs" },
        { id: "data-model/limits-and-config", href: b + "data-model/limits-and-config.html", label: "Limits and stages" },
        { id: "data-model/diagram",           href: b + "data-model/diagram.html",           label: "Diagrams" },
      ],
    },
    {
      title: "Operations",
      items: [
        { id: "operations/ingest",      href: b + "operations/ingest.html",      label: "Ingest (client)" },
        { id: "operations/query",       href: b + "operations/query.html",       label: "Query (client)" },
        { id: "operations/revision",    href: b + "operations/revision.html",    label: "Revision (internal)" },
        { id: "operations/forget",      href: b + "operations/forget.html",      label: "Forget (internal)" },
        { id: "operations/high-level",  href: b + "operations/high-level.html",  label: "High-level API flow" },
        { id: "operations/low-level",   href: b + "operations/low-level.html",   label: "Low-level UI API" },
        { id: "operations/run-config",  href: b + "operations/run-config.html",  label: "Run and configuration" },
      ],
    },
    {
      title: "Reference",
      items: [
        { id: "api/index", href: b + "api/index.html", label: "HTTP endpoint index" },
      ],
    },
  ];

  function injectSidebar() {
    var aside = document.getElementById("doc-sidebar");
    if (!aside) return;

    var html = '<div class="sidebar-inner">';
    html += '<div class="sidebar-brand"><a href="' + b + 'index.html">';
    html += '<span class="sidebar-logo-mark"></span>MemState</a></div>';
    html += '<p class="sidebar-tag">Official system documentation</p>';

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

  /* -------------------------------------------------------
     2. Theme toggle button
     ------------------------------------------------------- */
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

  /* -------------------------------------------------------
     3. Right-side TOC panel + scroll spy
     ------------------------------------------------------- */
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
    if (headings.length < 3) return; /* skip pages with very few sections */

    /* Ensure IDs exist */
    headings.forEach(function (h) {
      if (!h.id) {
        h.id = slugify(h.textContent);
      }
    });

    /* Build TOC aside */
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

    /* Wrap .page-main + toc in .doc-body flex row */
    var footer = main.nextElementSibling; /* usually .page-footer */
    var docBody = document.createElement("div");
    docBody.className = "doc-body";
    main.parentNode.insertBefore(docBody, main);
    docBody.appendChild(main);
    docBody.appendChild(toc);

    /* Move footer back after doc-body if it was adjacent */
    if (footer && footer.classList && footer.classList.contains("page-footer")) {
      docBody.parentNode.insertBefore(footer, docBody.nextSibling);
    }

    /* Scroll spy */
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

  /* -------------------------------------------------------
     4. Init — safe to call with defer (DOM is parsed)
     ------------------------------------------------------- */
  injectSidebar();
  injectThemeToggle();
  injectTOC();
})();
