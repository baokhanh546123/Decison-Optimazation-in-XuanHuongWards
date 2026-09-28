/* Load candidates from real GeoJSON via GET /api/candidates (geopandas backend).
 * Source: data/Xuanhuongward/XuanHuongWarsFeaturesClean.geojson
 * Maps lodging→accommodation, health_care→health_and_medicine.
 * Mutates the same `candidates` array used by renderGrid (shared via window.candidates).
 */
(function () {
  function taxMeta(tax) {
    if (typeof TAX !== "undefined" && TAX[tax]) return TAX[tax];
    return { label: tax || "other", dot: "dot-food" };
  }
  window.taxMeta = taxMeta;

  function applyList(list) {
    var mapped = list.map(function (c, i) {
      return {
        id: c.uid || ("C-" + String(i + 1).padStart(3, "0")),
        name: c.name || "Unnamed",
        taxonomy: c.taxonomy || "food_and_drink",
        taxonomy_root: c.taxonomy_root || c.taxonomy,
        confidence: c.confidence != null ? Number(c.confidence).toFixed(2) : "0.00",
        lat: c.lat,
        lng: c.lng,
        address: c.address || "",
        primary: c.primary || "",
        featureId: c.id
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
  }

  function loadCandidatesFromGeojson() {
    var grid = document.getElementById("candidate-grid");
    if (grid) {
      grid.innerHTML =
        '<div class="empty-state" style="grid-column:1/-1">Đang tải candidates từ GeoJSON (geopandas)…</div>';
    }
    fetch("/api/candidates?per_tax=40")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (payload) {
        var list = (payload && payload.candidates) ? payload.candidates : [];
        console.info(
          "[candidates]",
          "engine=", payload.engine,
          "source=", payload.source,
          "counts=", payload.counts_full,
          "roots=", payload.taxonomy_root_unique,
          "n=", list.length
        );
        applyList(list);
      })
      .catch(function (err) {
        console.error("Failed to load /api/candidates", err);
        if (grid) {
          grid.innerHTML =
            '<div class="empty-state" style="grid-column:1/-1"><b>Không tải được candidates.</b> ' +
            err.message + " — GET /api/candidates</div>";
        }
      });
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
