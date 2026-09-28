/* Load candidates from real GeoJSON via GET /api/candidates (geopandas backend).
 * Source: data/Xuanhuongward/XuanHuongWarsFeaturesClean.geojson
 * Nhóm (chip / bán kính / trọng số) lấy trực tiếp từ cột taxonomy_root — không đổi tên alias.
 * Mutates the same `candidates` array used by renderGrid (shared via window.candidates).
 */
(function () {
  function taxMeta(tax) {
    return (window.TAX && window.TAX[tax]) || { label: tax || "other", color: "#8ea092" };
  }
  window.taxMeta = taxMeta;

  function applyList(list) {
    var mapped = list.map(function (c, i) {
      return {
        id: c.uid || ("C-" + String(i + 1).padStart(3, "0")),
        name: c.name || "Unnamed",
        taxonomy: c.taxonomy_root || c.taxonomy || "other",
        taxonomy_root: c.taxonomy_root || c.taxonomy,
        confidence: c.confidence != null ? Number(c.confidence).toFixed(2) : "0.00",
        lat: c.lat,
        lng: c.lng,
        address: c.address || "",
        primary: c.primary || "",
        featureId: c.id,
        weight: c.weight,
        radius_m: c.radius_m
      };
    });

    if (window.candidates && Array.isArray(window.candidates)) {
      window.candidates.length = 0;
      for (var i = 0; i < mapped.length; i++) window.candidates.push(mapped[i]);
    } else {
      window.candidates = mapped;
    }

    if (typeof renderGrid === "function") renderGrid();
    if (typeof updateSummary === "function") updateSummary();
    if (typeof updateNav === "function") updateNav();
    if (typeof rebuildChips === "function") {
      var chips = [];
      var seen = {};
      mapped.forEach(function (c) {
        if (c.taxonomy && !seen[c.taxonomy]) { seen[c.taxonomy] = 1; chips.push(c.taxonomy); }
      });
      rebuildChips(chips.sort());
    }
  }

  function loadCandidatesFromGeojson() {
    var grid = document.getElementById("candidate-grid");
    if (grid) {
      grid.innerHTML =
        '<div class="empty-state" style="grid-column:1/-1">Đang tải candidates từ GeoJSON…</div>';
    }
    var urls = ["/static/candidates.json", "/static/candidates_xuanhuong.json", "/api/candidates?per_tax=40"];
    function tryFetch(i) {
      if (i >= urls.length) {
        if (grid) {
          grid.innerHTML =
            '<div class="empty-state" style="grid-column:1/-1"><b>Không tải được candidates.</b> Kiểm tra /static/candidates.json hoặc /api/candidates</div>';
        }
        return;
      }
      fetch(urls[i])
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (payload) {
          var list = (payload && payload.candidates) ? payload.candidates : [];
          console.info("[candidates]", "source=", payload.source, "n=", list.length);
          applyList(list);
        })
        .catch(function () { tryFetch(i + 1); });
    }
    tryFetch(0);
  }
  window.loadCandidatesFromGeojson = loadCandidatesFromGeojson;

  function boot() {
    if (typeof renderGrid === "function" && window.candidates) {
      loadCandidatesFromGeojson();
    } else {
      setTimeout(boot, 50);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
