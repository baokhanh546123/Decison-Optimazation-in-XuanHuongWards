/* Hiệu ứng GSAP cho Bước 4 của runner (không chứa logic nghiệp vụ).
 *   MCLPFx.widen(on, onUpdate, onDone) mở rộng / thu hẹp thẻ wizard khi vào / rời Bước 4
 *   MCLPFx.enterResults()            vào sân: 2 section trượt lên, stat, hàng bảng, thẻ vị trí
 *   MCLPFx.countUp(el, to, opts)     đếm số từ 0 → to
 *   MCLPFx.facilitiesIn()            thẻ vị trí bật lên khi đổi điểm Pareto
 *   MCLPFx.pulseRec()                nhịp ★ điểm khuyến nghị
 * Tôn trọng prefers-reduced-motion và chạy được khi không có gsap (chỉ đổi trạng thái, không animate).
 */
(function () {
  "use strict";

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function on() { return !!window.gsap && !reduce; }
  function qsa(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  var BASE_W = 1180, MAX_W = 1640;
  var wide = false, widenTween = null, pulseTween = null;

  function mainEl() { return document.querySelector("main.wizard"); }
  function targetWidth() { return Math.round(Math.min(MAX_W, window.innerWidth * 0.96)); }

  function widen(flag, onUpdate, onDone) {
    var m = mainEl();
    if (!m || flag === wide) { if (onDone) onDone(); return; }
    wide = flag;
    if (widenTween) { widenTween.kill(); widenTween = null; }

    if (!on()) {                        /* không animate: đổi class, CSS lo phần còn lại */
      m.classList.toggle("is-wide", flag);
      if (onUpdate) onUpdate();
      if (onDone) onDone();
      return;
    }

    var from = m.getBoundingClientRect().width;
    var to = flag ? targetWidth() : BASE_W;
    m.style.maxWidth = from + "px";
    m.classList.remove("is-wide");
    widenTween = gsap.to(m, {
      maxWidth: to,
      duration: 0.75,
      ease: "power3.inOut",
      onUpdate: onUpdate || null,
      onComplete: function () {
        m.classList.toggle("is-wide", flag);
        m.style.maxWidth = "";
        widenTween = null;
        if (onUpdate) onUpdate();
        if (onDone) onDone();
      }
    });
  }

  function countUp(el, to, opts) {
    opts = opts || {};
    if (!el) return;
    var d = opts.decimals || 0, suf = opts.suffix || "", pre = opts.prefix || "";
    function txt(v) { return pre + Number(v).toFixed(d) + suf; }
    if (!on() || to == null || isNaN(to)) { el.textContent = (to == null || isNaN(to)) ? "—" : txt(to); return; }
    var o = { v: 0 };
    gsap.to(o, {
      v: to, duration: opts.duration || 1.1, delay: opts.delay || 0, ease: "power2.out",
      onStart: function () { el.textContent = txt(0); },
      onUpdate: function () { el.textContent = txt(o.v); },
      onComplete: function () { el.textContent = txt(to); }
    });
  }

  function enterResults() {
    if (!on()) return;
    var secs = qsa("#results2 .rsec");
    gsap.fromTo(secs, { autoAlpha: 0, y: 30 },
      { autoAlpha: 1, y: 0, duration: 0.75, ease: "power3.out", stagger: 0.16, delay: 0.25 });
    gsap.fromTo("#results2 .rsec__no", { scale: 0.3, opacity: 0, rotate: -12 },
      { scale: 1, opacity: 1, rotate: 0, duration: 0.6, ease: "back.out(2.4)", stagger: 0.16, delay: 0.4 });
    gsap.fromTo("#results2 .rsec__head p", { autoAlpha: 0, y: 8 },
      { autoAlpha: 1, y: 0, duration: 0.5, ease: "power2.out", stagger: 0.16, delay: 0.55 });
    gsap.fromTo(".stat-line", { autoAlpha: 0, x: 22 },
      { autoAlpha: 1, x: 0, duration: 0.5, ease: "power2.out", stagger: 0.09, delay: 0.6, clearProps: "transform" });
    gsap.fromTo("#pareto-list tbody tr", { autoAlpha: 0, x: -16 },
      { autoAlpha: 1, x: 0, duration: 0.4, ease: "power2.out", stagger: 0.045, delay: 0.85, clearProps: "transform,opacity,visibility" });
    gsap.fromTo(".chart-controls, .chart-foot", { autoAlpha: 0, y: 10 },
      { autoAlpha: 1, y: 0, duration: 0.5, ease: "power2.out", stagger: 0.1, delay: 0.75 });
    facilitiesIn(1.0);
    pulseRec();
  }

  function facilitiesIn(delay) {
    if (!on()) return;
    var nodes = qsa("#facility-panel .facility");
    if (!nodes.length) return;
    gsap.fromTo("#facility-panel .panel__title", { autoAlpha: 0, x: -10 },
      { autoAlpha: 1, x: 0, duration: 0.35, ease: "power2.out", delay: delay || 0 });
    gsap.fromTo(nodes, { autoAlpha: 0, y: 14, scale: 0.94 },
      { autoAlpha: 1, y: 0, scale: 1, duration: 0.45, ease: "back.out(1.7)", stagger: 0.06, delay: (delay || 0) + 0.05, clearProps: "transform,opacity,visibility" });
  }

  function pulseRec() {
    if (pulseTween) { pulseTween.kill(); pulseTween = null; }
    if (!on()) return;
    var t = qsa(".tag--rec");
    if (!t.length) return;
    pulseTween = gsap.to(t, { scale: 1.3, duration: 0.7, ease: "sine.inOut", yoyo: true, repeat: -1 });
  }

  window.MCLPFx = {
    on: on, widen: widen, countUp: countUp,
    enterResults: enterResults, facilitiesIn: facilitiesIn, pulseRec: pulseRec
  };
})();
