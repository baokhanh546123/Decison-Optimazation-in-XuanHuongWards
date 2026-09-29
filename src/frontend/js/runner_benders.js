/* Client API cho thuật toán Benders — dùng bởi runner_page.js.
 *   POST /api/optimize        -> { job_id }
 *   GET  /api/jobs/{job_id}   -> { state, elapsed_s, error, result }
 * Không đụng DOM; chỉ trả Promise + gọi hooks.onProgress(job) mỗi lần poll.
 */
(function () {
  "use strict";

  var POLL_MS = 1000;

  function errMsg(body, status) {
    var d = body && body.detail;
    if (Array.isArray(d)) {
      d = d.map(function (x) { return ((x.loc || []).slice(1).join(".") || "request") + ": " + x.msg; }).join("; ");
    }
    return d || (body && body.error) || ("HTTP " + status);
  }

  function asJson(r) {
    return r.json().catch(function () { return {}; }).then(function (b) {
      if (!r.ok) throw new Error(errMsg(b, r.status));
      return b;
    });
  }

  /* cfg = window.getRunConfig() (runner_page.js) */
  function buildBody(cfg) {
    return {
      candidates: cfg.candidates,
      taxonomy_root: cfg.taxonomy_root,
      per_candidate: cfg.per_candidate,
      min_confidence: cfg.min_confidence,
      P_max: cfg.P_max,
      n_points: cfg.n_points,
      "lambda": cfg.lambda,
      benders_max_iters: cfg.benders_max_iters,
      benders_master_time_limit_s: cfg.benders_master_time_limit_s,
      time_limit_s: cfg.time_limit_s
    };
  }

  function run(cfg, hooks) {
    hooks = hooks || {};
    return fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildBody(cfg))
    }).then(asJson).then(function (sub) {
      return new Promise(function (resolve, reject) {
        (function tick() {
          fetch("/api/jobs/" + encodeURIComponent(sub.job_id)).then(asJson).then(function (job) {
            if (hooks.onProgress) hooks.onProgress(job);
            if (job.state === "done") resolve(job.result);
            else if (job.state === "failed") reject(new Error(job.error || "Job thất bại"));
            else setTimeout(tick, POLL_MS);
          }).catch(reject);
        })();
      });
    });
  }

  window.MCLPBenders = { run: run, buildBody: buildBody };
})();
