/* Section 2 của Bước 4 — biểu đồ dựng bởi package `visualize` (visualize/visualize_plot.py).
 *   heatmap / dot -> GET /api/runs/{run_id}/map.html?mode=..[&point=k]  (pydeck, hiển thị trong iframe srcdoc)
 *   jpeg          -> GET /api/runs/{run_id}/map.jpg[?point=k]            (matplotlib, thẻ <img>)
 *
 * API:
 *   MCLPCharts.setRun(runId, nPoints, pickedIdx)  nhận kết quả mới (chưa tải, đợi activate)
 *   MCLPCharts.activate()                         gọi khi Bước 4 đã hiện -> bắt đầu tải biểu đồ
 *   MCLPCharts.setPoint(i)                        điểm Pareto đang xem ở Section 1 đổi
 */
(function () {
  "use strict";

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function fx() { return !!window.gsap && !reduce; }
  function $(id) { return document.getElementById(id); }

  var st = { runId: null, n: 0, view: "heatmap", scope: "all", point: 0, pending: false, token: 0 };
  var cache = {};             /* url -> { html } | { blob } */
  var spin = null;

  var tabs, ink, stage, loader, loaderTxt, errBox, frame, img, openA, hint, scopeBtn, scopeWrap;

  function url(view, scope) {
    var q = scope === "point" ? "point=" + st.point : "";
    var base = "/api/runs/" + encodeURIComponent(st.runId);
    if (view === "jpeg") return base + "/map.jpg" + (q ? "?" + q : "");
    return base + "/map.html?mode=" + view + (q ? "&" + q : "");
  }

  /* ---------- UI helpers ---------- */
  function moveInk(animate) {
    var a = tabs.querySelector(".tab.is-active");
    if (!a || !ink) return;
    var x = a.offsetLeft, w = a.offsetWidth;
    if (animate && fx()) gsap.to(ink, { x: x, width: w, duration: 0.4, ease: "power3.out" });
    else { ink.style.transform = "translateX(" + x + "px)"; ink.style.width = w + "px"; if (window.gsap) gsap.set(ink, { x: x, width: w }); }
  }

  function showLoader(msg) {
    loaderTxt.textContent = msg || "Đang dựng biểu đồ…";
    errBox.style.display = "none";
    loader.style.display = "flex";
    if (fx()) {
      gsap.to(loader, { autoAlpha: 1, duration: 0.2 });
      if (!spin) spin = gsap.to(loader.querySelector(".chart-loader__ring"), { rotation: 360, duration: 0.9, ease: "none", repeat: -1 });
      spin.play();
    } else { loader.style.opacity = 1; loader.style.visibility = "visible"; }
  }
  function hideLoader() {
    if (fx()) gsap.to(loader, { autoAlpha: 0, duration: 0.25, onComplete: function () { if (spin) spin.pause(); loader.style.display = "none"; } });
    else { loader.style.display = "none"; }
  }
  function showError(msg) {
    hideLoader();
    frame.style.display = "none"; img.style.display = "none";
    errBox.textContent = msg;
    errBox.style.display = "flex";
    if (fx()) gsap.fromTo(errBox, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.35 });
  }

  function reveal(el) {
    el.style.display = "block";
    if (fx()) {
      gsap.fromTo(el, { autoAlpha: 0, scale: 0.985, clipPath: "inset(0 0 100% 0)" },
        { autoAlpha: 1, scale: 1, clipPath: "inset(0 0 0% 0)", duration: 0.7, ease: "power3.out", clearProps: "clipPath,transform" });
    } else { el.style.opacity = 1; el.style.visibility = "visible"; }
  }

  /* ---------- tải ---------- */
  function errFrom(res) {
    return res.json().catch(function () { return {}; }).then(function (b) {
      return (b && b.detail) || ("HTTP " + res.status);
    });
  }

  function load() {
    if (!st.runId) return;
    var my = ++st.token;
    var view = st.view, u = url(view, st.scope);
    openA.href = u;
    hint.textContent = view === "jpeg"
      ? "Ảnh tĩnh (matplotlib) — không cần mạng."
      : "Bản đồ tương tác (pydeck) — cần mạng để tải deck.gl và nền bản đồ. Kéo để di chuyển, cuộn để zoom, rê chuột để xem chi tiết.";

    if (fx()) gsap.to([frame, img], { autoAlpha: 0, duration: 0.15 });
    frame.style.display = "none"; img.style.display = "none";
    showLoader(view === "jpeg" ? "Đang vẽ ảnh tĩnh (matplotlib)…" : "Đang dựng bản đồ (pydeck)…");

    var hit = cache[u];
    var p = hit ? Promise.resolve(hit) : fetch(u).then(function (res) {
      if (!res.ok) return errFrom(res).then(function (m) { throw new Error(m); });
      return view === "jpeg"
        ? res.blob().then(function (b) { return { blob: URL.createObjectURL(b) }; })
        : res.text().then(function (t) { return { html: t }; });
    });

    p.then(function (r) {
      if (my !== st.token) return;               /* người dùng đã đổi tab/phạm vi trong lúc chờ */
      cache[u] = r;
      /* iframe pydeck tải deck.gl từ CDN: nếu sự kiện load không tới (mạng chặn), vẫn gỡ loader sau 15 s */
      setTimeout(function () { if (my === st.token && loader.style.display !== "none") { hideLoader(); reveal(r.blob ? img : frame); } }, 15000);
      if (r.blob) {
        img.onload = function () { if (my === st.token) { hideLoader(); reveal(img); } };
        img.src = r.blob;
      } else {
        frame.onload = function () { if (my === st.token) { hideLoader(); reveal(frame); } };
        frame.srcdoc = r.html;
      }
    }).catch(function (e) {
      if (my === st.token) showError(e && e.message ? e.message : String(e));
    });
  }

  /* ---------- sự kiện ---------- */
  function setView(v) {
    if (v === st.view) return;
    st.view = v;
    tabs.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("is-active", t.dataset.view === v); });
    moveInk(true);
    if (!st.pending) load();
  }
  function setScope(sc) {
    if (sc === st.scope) return;
    st.scope = sc;
    scopeWrap.querySelectorAll(".seg__btn").forEach(function (b) { b.classList.toggle("is-active", b.dataset.scope === sc); });
    if (!st.pending) load();
  }
  function labelPoint() { scopeBtn.textContent = "Điểm #" + (st.point + 1); }

  function setRun(runId, nPoints, picked) {
    Object.keys(cache).forEach(function (k) { if (cache[k].blob) URL.revokeObjectURL(cache[k].blob); });
    cache = {};
    st.runId = runId || null; st.n = nPoints || 0; st.point = picked >= 0 ? picked : 0;
    st.pending = true; st.token++;
    labelPoint();
    scopeBtn.disabled = !st.n;
    frame.removeAttribute("srcdoc"); img.removeAttribute("src");
    frame.style.display = "none"; img.style.display = "none";
    if (!runId) showError(nPoints ? "Kết quả không kèm run_id — hãy chạy lại tối ưu." : "Không có điểm Pareto để vẽ.");
  }

  function activate() {
    moveInk(false);
    if (st.pending && st.runId) { st.pending = false; load(); }
  }

  function setPoint(i) {
    if (i == null || i < 0) return;
    st.point = i; labelPoint();
    if (st.scope === "point" && !st.pending) load();
    else if (fx()) gsap.fromTo(scopeBtn, { scale: 1.12 }, { scale: 1, duration: 0.35, ease: "back.out(3)" });
  }

  function init() {
    tabs = $("chart-tabs"); ink = $("tabs-ink"); stage = $("chart-stage"); loader = $("chart-loader");
    loaderTxt = $("chart-loader-txt"); errBox = $("chart-error"); frame = $("chart-frame"); img = $("chart-img");
    openA = $("chart-open"); hint = $("chart-hint"); scopeBtn = $("scope-point"); scopeWrap = $("chart-scope");
    if (!tabs || !stage) return;
    tabs.addEventListener("click", function (e) { var b = e.target.closest(".tab"); if (b) setView(b.dataset.view); });
    scopeWrap.addEventListener("click", function (e) { var b = e.target.closest(".seg__btn"); if (b && !b.disabled) setScope(b.dataset.scope); });
    window.addEventListener("resize", function () { moveInk(false); });
    if (window.gsap) gsap.set(ink, { x: 0, width: 0 });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
  window.MCLPCharts = { setRun: setRun, activate: activate, setPoint: setPoint };
})();
