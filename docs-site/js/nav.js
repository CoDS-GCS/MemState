/**
 * Injects the left sidebar.
 * Set <body data-doc-page="architecture/overview"> for active link highlighting.
 */
(function () {
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
  var page = document.body.getAttribute("data-doc-page") || "";

  var sections = [
    {
      title: "Home",
      items: [{ id: "index", href: b + "index.html", label: "System home" }],
    },
    {
      title: "Architecture",
      items: [
        { id: "architecture/overview", href: b + "architecture/overview.html", label: "Runtime overview" },
        { id: "architecture/storage", href: b + "architecture/storage.html", label: "Storage and schema" },
        { id: "architecture/reasoning", href: b + "architecture/reasoning.html", label: "Reasoner behavior" },
        { id: "architecture/http-stack", href: b + "architecture/http-stack.html", label: "HTTP, UI, LLM" },
      ],
    },
    {
      title: "Data Model",
      items: [
        { id: "data-model/overview", href: b + "data-model/overview.html", label: "Topic model" },
        { id: "data-model/fields", href: b + "data-model/fields.html", label: "Fields and history" },
        { id: "data-model/relationships", href: b + "data-model/relationships.html", label: "Relationships and refs" },
        { id: "data-model/limits-and-config", href: b + "data-model/limits-and-config.html", label: "Limits and stages" },
        { id: "data-model/diagram", href: b + "data-model/diagram.html", label: "Diagrams" },
      ],
    },
    {
      title: "Operations",
      items: [
        { id: "operations/ingest", href: b + "operations/ingest.html", label: "Ingest (client)" },
        { id: "operations/query", href: b + "operations/query.html", label: "Query (client)" },
        { id: "operations/revision", href: b + "operations/revision.html", label: "Revision (internal)" },
        { id: "operations/forget", href: b + "operations/forget.html", label: "Forget (internal)" },
      ],
    },
    {
      title: "Reference",
      items: [{ id: "api/index", href: b + "api/index.html", label: "HTTP endpoint index" }],
    },
  ];

  var aside = document.getElementById("doc-sidebar");
  if (!aside) return;

  var html = '<div class="sidebar-inner">';
  html += '<div class="sidebar-brand"><a href="' + b + 'index.html">MemState</a></div>';
  html += '<p class="sidebar-tag">Official system documentation</p>';

  sections.forEach(function (sec) {
    html += '<section class="nav-section"><h3 class="nav-section-title">' + sec.title + "</h3><ul>";
    sec.items.forEach(function (it) {
      var active = it.id === page ? " is-active" : "";
      html +=
        '<li><a class="nav-link' +
        active +
        '" href="' +
        it.href +
        '" data-nav-id="' +
        it.id +
        '">' +
        it.label +
        "</a></li>";
    });
    html += "</ul></section>";
  });

  html += "</div>";
  aside.innerHTML = html;
})();
