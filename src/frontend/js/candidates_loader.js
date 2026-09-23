/* Load candidates from GeoJSON taxonomy_root via backend API.
 * Maps lodging→accommodation, health_care→health_and_medicine.
 * Expects globals: TAX, candidates, renderGrid, selected, grid (from runner.html)
 */
(function () {
  function taxMeta(tax) {
    if (typeof TAX !== "undefined" && TAX[tax]) return TAX[tax];
    return { label: tax || "other", dot: "dot-food" };
  }
  window.taxMeta = taxMeta;

  function loadCandidatesFromGeojson() {
    fetch("/api/candidates?per_tax=40")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (payload) {
        var list = (payload && payload.candidates) ? payload.candidates : [];
        window.candidates = list.map(function (c, i) {
          return {
            id: c.uid || ("C-" + String(i + 1).padStart(3, "0")),
            name: c.name || "Unnamed",
            taxonomy: c.taxonomy || "food_and_drink",
            taxonomy_root: c.taxonomy_root || c.taxonomy,
            confidence: c.confidence != null ? c.confidence : 0,
            lat: c.lat,
            lng: c.lng,
            address: c.address || "",
            primary: c.primary || "",
            featureId: c.id
          };
        });
        if (typeof renderGrid === "function") renderGrid();
        if (typeof updateSummary === "function") updateSummary();
        if (typeof updateNav === "function") updateNav();
      })
      .catch(function (err) {
        console.error("Failed to load /api/candidates", err);
        var g = document.getElementById("candidate-grid");
        if (g) {
          g.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><b>Không tải được candidates từ GeoJSON.</b> GET /api/candidates</div>';
        }
      });
  }
  window.loadCandidatesFromGeojson = loadCandidatesFromGeojson;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadCandidatesFromGeojson);
  } else {
    setTimeout(loadCandidatesFromGeojson, 0);
  }
})();
