(function () {
    "use strict";
    // Sidebar toggle (mobile / tablet)
    var body = document.body;
    var open = document.getElementById("openSidebar");
    if (open) open.addEventListener("click", function () { body.classList.add("sidebar-open"); });
    document.querySelectorAll("[data-close-sidebar]").forEach(function (el) {
        el.addEventListener("click", function () { body.classList.remove("sidebar-open"); });
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") body.classList.remove("sidebar-open"); });

    // Live notifications: poll the feed and update the bell
    function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
    function refresh() {
        if (!window.PORTAL) return;
        fetch(window.PORTAL.feed, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data) return;
                var badge = document.getElementById("notifCount");
                if (badge) { badge.textContent = data.unread; badge.classList.toggle("d-none", !data.unread); }
                var list = document.getElementById("notifList");
                if (list) {
                    list.innerHTML = data.latest.length ? data.latest.map(function (n) {
                        return '<a class="notif-item" href="' + window.PORTAL.open + n.id + '/">' + esc(n.title) + '<br><small>' + esc(n.created_at) + '</small></a>';
                    }).join("") : '<div class="px-3 py-3 text-muted small">You are all caught up.</div>';
                }
            }).catch(function () {});
    }
    refresh();
    setInterval(refresh, 30000);

    // Charts: <canvas data-chart='{"type":"bar","labels":[],"datasets":[...]}'>
    var palette = ["#D3224D", "#2563eb", "#1f9d55", "#e6a100", "#7c3aed", "#0891b2", "#ea580c", "#64748b"];
    document.querySelectorAll("canvas[data-chart]").forEach(function (cv) {
        if (!window.Chart) return;
        var cfg = JSON.parse(cv.getAttribute("data-chart"));
        var multi = cfg.type === "doughnut" || cfg.type === "pie";
        cfg.datasets.forEach(function (ds, i) {
            if (!ds.backgroundColor) ds.backgroundColor = multi ? palette : palette[i % palette.length];
            if (!ds.borderColor && cfg.type === "line") { ds.borderColor = palette[i % palette.length]; ds.tension = 0.3; ds.fill = false; }
            if (cfg.type === "bar") ds.borderRadius = 6;
        });
        new Chart(cv, {
            type: cfg.type,
            data: { labels: cfg.labels, datasets: cfg.datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: multi || cfg.datasets.length > 1, position: "bottom" } },
                scales: multi ? {} : { y: { beginAtZero: true, max: cfg.max || undefined, grid: { color: "#eef1f5" } }, x: { grid: { display: false } } }
            }
        });
    });

    // Programmatic helper used by page scripts: drawChart("id", "bar", labels, [{label, data}], {max: 100})
    window.drawChart = function (id, type, labels, datasets, opts) {
        var cv = document.getElementById(id);
        if (!cv || !window.Chart) return;
        opts = opts || {};
        var multi = type === "doughnut" || type === "pie";
        if (!labels || !labels.length) {
            cv.parentNode.innerHTML = '<div class="empty"><i class="fa-solid fa-chart-simple"></i>No data yet</div>';
            return;
        }
        datasets.forEach(function (ds, i) {
            if (!ds.backgroundColor) ds.backgroundColor = multi ? palette : palette[i % palette.length];
            if (type === "line") { ds.borderColor = ds.borderColor || palette[i % palette.length]; ds.tension = 0.3; ds.fill = false; }
            if (type === "bar") ds.borderRadius = 6;
        });
        new Chart(cv, {
            type: type, data: { labels: labels, datasets: datasets },
            options: {
                responsive: true, maintainAspectRatio: false, indexAxis: opts.horizontal ? "y" : "x",
                plugins: { legend: { display: multi || datasets.length > 1, position: "bottom" } },
                scales: multi ? {} : { y: { beginAtZero: true, max: opts.max, grid: { color: "#eef1f5" } }, x: { grid: { display: false } } }
            }
        });
    };

    // Confirm destructive actions
    document.querySelectorAll("[data-confirm]").forEach(function (el) {
        el.addEventListener("click", function (e) { if (!confirm(el.getAttribute("data-confirm"))) e.preventDefault(); });
    });

    // Attendance helpers: mark all present / absent
    document.querySelectorAll("[data-mark-all]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var v = btn.getAttribute("data-mark-all");
            document.querySelectorAll('input[type=radio][value="' + v + '"]').forEach(function (r) { r.checked = true; });
        });
    });
})();
