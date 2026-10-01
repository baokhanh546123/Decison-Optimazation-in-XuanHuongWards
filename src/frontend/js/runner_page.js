(function(){
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------------------------------------------------------------
     3.1 — Dữ liệu candidate mô phỏng
  --------------------------------------------------------------------- */
  /* [interface] TAX chỉ còn là registry: root -> { label, color }.
     Nhãn đẹp và màu chấm được sinh tự động cho MỌI taxonomy, dùng chung ở chip / thẻ / threshold / bước 3. */
  var TAX = {};


  var STREETS = ['Trần Hưng Đạo', 'Hồ Xuân Hương', 'Yersin', 'Phù Đổng Thiên Vương',
    'Nguyễn Chí Thanh', 'Bùi Thị Xuân', 'Xô Viết Nghệ Tĩnh', 'Ba Tháng Hai',
    'Nguyễn Văn Trỗi', 'Lê Đại Hành', 'Phan Đình Phùng', 'Trần Phú',
    'Đống Đa', 'Hoàng Văn Thụ'];

  var TAX_KEYS = ['food_and_drink', 'accommodation', 'health_and_medicine'];

  var candidates = STREETS.map(function(street, i){
    var tax = TAX_KEYS[i % TAX_KEYS.length];
    return {
      id: 'C-' + String(i + 1).padStart(2, '0'),
      name: 'Trục ' + street,
      taxonomy: tax,
      confidence: (0.62 + (i % 5) * 0.07).toFixed(2)
    };
  });

  /* [interface] taxonomy ngoài 3 nhóm gốc vẫn render được (dữ liệu thật có ~13 nhóm) */
  /* 'food_and_drink' -> 'Food & Drink', 'health_care' -> 'Health Care' */
  function prettyLabel(t){
    return String(t || 'other').split('_').map(function(w){
      return w === 'and' ? '&' : w.charAt(0).toUpperCase() + w.slice(1);
    }).join(' ');
  }
  function hashHue(t){ var h = 0; for (var i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % 360; return h; }

  /* mỗi taxonomy 1 màu duy nhất: hue theo golden-angle để các màu cách xa nhau */
  function registerTax(list){
    list.slice().sort().forEach(function(t, idx){
      TAX[t] = { label: prettyLabel(t), color: 'hsl(' + Math.round((idx * 137.508 + 38) % 360) + ',55%,62%)' };
    });
  }
  function meta(t){
    if (!TAX[t]) TAX[t] = { label: prettyLabel(t), color: 'hsl(' + hashHue(String(t)) + ',55%,62%)' };
    return TAX[t];
  }
  function dot(t){ return '<span class="chip__dot" style="background:' + meta(t).color + '"></span>'; }
  registerTax(TAX_KEYS);
  window.TAX = TAX;
  window.candidates = candidates;

  var selected = new Set();
  var activeFilter = 'all';

  /* ---------------------------------------------------------------------
     3.2 — Render candidate grid (Pane 1)
  --------------------------------------------------------------------- */
  var grid = document.getElementById('candidate-grid');
  var selectedCountEl = document.getElementById('selected-count');
  var visibleCountEl = document.getElementById('visible-count');

  function renderGrid(){
    grid.innerHTML = '';
    var visible = candidates.filter(function(c){
      return activeFilter === 'all' || c.taxonomy === activeFilter;
    });
    visibleCountEl.textContent = visible.length;

    visible.forEach(function(c){
      var card = document.createElement('div');
      card.className = 'candidate' + (selected.has(c.id) ? ' is-selected' : '');
      card.dataset.id = c.id;
      card.tabIndex = 0; card.setAttribute('role', 'checkbox');
      card.setAttribute('aria-checked', selected.has(c.id));
      card.addEventListener('keydown', function(e){
        if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); toggleCandidate(c.id, card); }
      });
      card.innerHTML =
        '<div class="candidate__top">' +
          '<span class="candidate__id">' + c.id + '</span>' +
          '<span class="candidate__check"></span>' +
        '</div>' +
        '<div class="candidate__name">' + c.name + '</div>' +
        '<div class="candidate__meta">' +
          '<span class="candidate__tax">' + dot(c.taxonomy) + meta(c.taxonomy).label + '</span>' +
          '<span class="candidate__conf">conf ' + c.confidence + '</span>' +
        '</div>';
      card.addEventListener('click', function(){ toggleCandidate(c.id, card); });
      grid.appendChild(card);
    });
  }

  function toggleCandidate(id, cardEl){
    if (selected.has(id)) { selected.delete(id); }
    else { selected.add(id); }
    cardEl.classList.toggle('is-selected');
    cardEl.setAttribute('aria-checked', selected.has(id));

    if (!reduceMotion && window.gsap){
      gsap.fromTo(cardEl, { scale: 0.97 }, { scale: 1, duration: 0.22, ease: 'back.out(3)' });
    }

    selectedCountEl.textContent = selected.size;
    renderThresholdList();
    renderTaxParams();
    updateSummary();
    updateNav();
  }

  document.getElementById('filter-group').addEventListener('click', function(e){
    var btn = e.target.closest('.chip');
    if (!btn) return;
    document.querySelectorAll('#filter-group .chip').forEach(function(c){ c.classList.remove('is-active'); });
    btn.classList.add('is-active');
    activeFilter = btn.dataset.filter;
    renderGrid();
  });

  window.renderGrid = renderGrid;
  window.rebuildChips = function(list){
    registerTax(list);   /* gán màu đồng bộ cho toàn bộ taxonomy thật */
    var group = document.getElementById('filter-group');
    group.innerHTML = '<button class="chip is-active" data-filter="all">Tất cả</button>';
    list.forEach(function(t){
      var b = document.createElement('button');
      b.className = 'chip'; b.dataset.filter = t;
      b.innerHTML = dot(t) + meta(t).label;
      group.appendChild(b);
    });
    activeFilter = 'all';
    renderGrid();
    renderTaxParams();
  };

  /* ---------------------------------------------------------------------
     3.3 — Render threshold rows (Pane 2)
  --------------------------------------------------------------------- */
  var thresholdList = document.getElementById('threshold-list');
  var thresholdEmpty = document.getElementById('threshold-empty');
  var perCandidateParams = {};

  function renderThresholdList(){
    var ids = Array.from(selected);
    thresholdList.querySelectorAll('.threshold-row').forEach(function(el){ el.remove(); });

    if (ids.length === 0){
      thresholdEmpty.style.display = 'block';
      return;
    }
    thresholdEmpty.style.display = 'none';

    ids.forEach(function(id){
      var c = candidates.find(function(x){ return x.id === id; });
      if (!perCandidateParams[id]) {
        perCandidateParams[id] = { demand: 0.5, conf: parseFloat(c.confidence) };
      }
      var p = perCandidateParams[id];

      var row = document.createElement('div');
      row.className = 'threshold-row';
      row.innerHTML =
        '<div class="threshold-row__head">' +
          '<span class="threshold-row__name">' + c.name + '<span>' + c.id + ' · ' + dot(c.taxonomy) + meta(c.taxonomy).label + '</span></span>' +
        '</div>' +
        '<div class="threshold-grid">' +
          '<div class="field">' +
            '<div class="field__label">Demand-weight threshold<b class="dw-val">' + p.demand.toFixed(2) + '</b></div>' +
            '<input type="range" class="dw-slider" min="0" max="1" step="0.01" value="' + p.demand + '">' +
          '</div>' +
          '<div class="field">' +
            '<div class="field__label">Confidence tối thiểu<b class="cf-val">' + p.conf.toFixed(2) + '</b></div>' +
            '<input type="range" class="cf-slider" min="0" max="1" step="0.01" value="' + p.conf + '">' +
          '</div>' +
        '</div>';

      row.querySelector('.dw-slider').addEventListener('input', function(e){
        p.demand = parseFloat(e.target.value);
        row.querySelector('.dw-val').textContent = p.demand.toFixed(2);
      });
      row.querySelector('.cf-slider').addEventListener('input', function(e){
        p.conf = parseFloat(e.target.value);
        row.querySelector('.cf-val').textContent = p.conf.toFixed(2);
      });

      thresholdList.appendChild(row);
    });
  }

  /* ---------------------------------------------------------------------
     3.4 — Pane 3: tham số toàn cục
  --------------------------------------------------------------------- */
  function bindRange(id, valId, fmt){
    var input = document.getElementById(id);
    var out = document.getElementById(valId);
    input.addEventListener('input', function(){
      out.textContent = fmt(input.value);
      updateSummary();
    });
  }

  /* [interface] bán kính + trọng số theo taxonomy_root của các cell đã chọn.
     Mặc định lấy từ candidate.radius_m / candidate.weight (nguồn: taxonomy_config.py). */
  var taxParams = {};   /* root -> { radius, weight } — giữ lại giá trị người dùng đã chỉnh */
  var taxHost = document.getElementById('tax-params');
  var taxEmpty = document.getElementById('tax-empty');

  function selectedByRoot(){
    var out = {};
    selected.forEach(function(id){
      var c = candidates.find(function(x){ return x.id === id; });
      if (!c) return;
      (out[c.taxonomy] = out[c.taxonomy] || []).push(c);
    });
    return out;
  }

  function paintFill(input, fill){
    fill.style.width = ((input.value - input.min) / (input.max - input.min) * 100) + '%';
  }

  function taxSlider(label, min, max, step, value, fmt, onChange){
    var f = document.createElement('div');
    f.className = 'field';
    f.innerHTML = '<div class="field__label"><span>' + label + '</span><b></b></div>' +
      '<div class="slider-wrap"><div class="slider-fill"></div>' +
      '<input type="range" min="' + min + '" max="' + max + '" step="' + step + '" value="' + value + '"></div>';
    var input = f.querySelector('input'), out = f.querySelector('b'), fill = f.querySelector('.slider-fill');
    function sync(){ out.textContent = fmt(input.value); paintFill(input, fill); }
    input.addEventListener('input', function(){ onChange(parseFloat(input.value)); sync(); updateSummary(); });
    sync();
    return f;
  }

  function renderTaxParams(){
    if (!taxHost) return;
    var by = selectedByRoot(), roots = Object.keys(by).sort();
    taxHost.innerHTML = '';
    taxEmpty.style.display = roots.length ? 'none' : 'block';
    roots.forEach(function(root){
      var first = by[root][0];
      var p = taxParams[root] || (taxParams[root] = {
        radius: Math.min(2000, Math.max(50, first.radius_m != null ? +first.radius_m : 300)),
        weight: Math.min(2, first.weight != null ? +first.weight : 0.5)
      });
      var card = document.createElement('div');
      card.className = 'tax-card';
      card.innerHTML = '<div class="tax-card__head"><span class="tax-card__name">' +
        dot(root) + meta(root).label + '</span><span class="tax-card__n">' + by[root].length + ' cell</span></div>';
      var grid = document.createElement('div'); grid.className = 'params-grid';
      grid.appendChild(taxSlider('Bán kính phủ radius_m', 50, 2000, 10, p.radius,
        function(v){ return v + ' m'; }, function(v){ p.radius = v; }));
      grid.appendChild(taxSlider('Trọng số p_i (weight)', 0, 2, 0.05, p.weight,
        function(v){ return parseFloat(v).toFixed(2); }, function(v){ p.weight = v; }));
      card.appendChild(grid);
      taxHost.appendChild(card);
    });
  }

  /* cấu hình gửi backend — cùng tên trường với TaxonomyUpdateRequest / OptimizeRequest */
  window.getRunConfig = function(){
    var roots = Object.keys(selectedByRoot()), tax = {}, per = {};
    roots.forEach(function(r){ tax[r] = { radius_m: taxParams[r].radius, weight: taxParams[r].weight }; });
    selected.forEach(function(id){ if (perCandidateParams[id]) per[id] = perCandidateParams[id]; });
    return {
      candidates: Array.from(selected),
      taxonomy_root: tax,
      per_candidate: per,
      min_confidence: parseFloat(document.getElementById('confidence').value),
      P_max: parseInt(document.getElementById('pmax').value, 10),
      n_points: parseInt(document.getElementById('epsilon-steps').value, 10),
      lambda: [parseInt(balanceInput.value, 10), 100 - parseInt(balanceInput.value, 10)],
      benders_max_iters: parseInt(document.getElementById('benders-max-iters').value, 10),
      benders_master_time_limit_s: parseFloat(document.getElementById('benders-master-time').value),
      time_limit_s: parseInt(document.getElementById('benders-time-limit').value, 10)
    };
  };
  bindRange('confidence',    'val-confidence',    function(v){ return parseFloat(v).toFixed(2); });
  bindRange('epsilon-steps', 'val-epsilon',       function(v){ return v; });
  bindRange('benders-max-iters',   'val-bmax',    function(v){ return v; });
  bindRange('benders-master-time', 'val-bmaster', function(v){ return v; });
  bindRange('benders-time-limit',  'val-btime',   function(v){ return v; });

  document.getElementById('pmax').addEventListener('input', updateSummary);

  var balanceInput = document.getElementById('balance');
  var balanceReadout = document.getElementById('balance-readout');
  balanceInput.addEventListener('input', function(){
    var v = parseInt(balanceInput.value, 10);
    balanceReadout.textContent = v + ' / ' + (100 - v);
  });

  window.updateSummary = updateSummary;
  function updateSummary(){
    document.getElementById('sum-candidates').textContent = selected.size;
    var rs = Object.keys(selectedByRoot()).map(function(r){ return taxParams[r] && taxParams[r].radius; }).filter(Boolean);
    document.getElementById('sum-radius').textContent =
      rs.length ? Math.min.apply(null, rs) + '–' + Math.max.apply(null, rs) + ' m' : '—';
    document.getElementById('sum-confidence').textContent =
      parseFloat(document.getElementById('confidence').value).toFixed(2);
    document.getElementById('sum-pmax').textContent = document.getElementById('pmax').value;
  }

  /* ---------------------------------------------------------------------
     3.5 — Chạy tối ưu bằng Benders qua API (Pane 3 → Pane 4)
  --------------------------------------------------------------------- */
  var btnRun = document.getElementById('btn-run');
  var pipelineEl = document.getElementById('pipeline');
  var fillEl = document.getElementById('pipeline-fill');
  var stageEl = document.getElementById('pipeline-stage');

  var lastResult = null;   /* { points, recommended_index, summary, meta } từ /api/jobs/{id} */
  var pickedIdx = -1;      /* điểm Pareto đang xem chi tiết */
  var dotHits = [];        /* toạ độ pixel các chấm trên canvas để bắt click */

  function esc(t){
    return String(t == null ? '' : t).replace(/[&<>"']/g, function(ch){
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function fmt(n, d){ return (n == null || isNaN(n)) ? '—' : Number(n).toFixed(d); }
  function setProgress(pct){
    if (!reduceMotion && window.gsap){ gsap.to(fillEl, { width: pct + '%', duration: 0.6, ease: 'power1.out' }); }
    else { fillEl.style.width = pct + '%'; }
  }
  function showError(msg){
    pipelineEl.classList.add('is-visible');
    stageEl.innerHTML = '<b class="pipeline__err">Lỗi.</b>&nbsp;' + esc(msg);
  }

  btnRun.addEventListener('click', function(){
    if (selected.size === 0 || btnRun.disabled) return;
    if (!window.MCLPBenders){ showError('Thiếu /js/runner_benders.js'); return; }
    var cfg = window.getRunConfig();
    if (!(cfg.P_max >= 1)){ showError('P_max phải ≥ 1.'); return; }
    console.info('[run config]', cfg);

    btnRun.disabled = true;
    pipelineEl.classList.add('is-visible');
    fillEl.style.width = '0%';
    setProgress(4);
    stageEl.innerHTML = '<b>1/2</b>&nbsp;Gửi cấu hình tới <code>POST /api/optimize</code>…';

    window.MCLPBenders.run(cfg, {
      onProgress: function(job){
        var el = job.elapsed_s || 0;
        if (job.state === 'queued'){
          stageEl.innerHTML = '<b>2/2</b>&nbsp;Đang xếp hàng chờ solver…';
        } else {
          stageEl.innerHTML = '<b>2/2</b>&nbsp;Benders đang chạy — giải master (x<sub>j</sub>, η), subproblem dạng đóng, thêm cắt lõm… ' +
            '<span class="pipeline__t">' + el.toFixed(0) + ' s</span>';
        }
        /* solver không báo % thật -> thanh tiến độ tiệm cận 92%, chỉ để thấy job còn sống */
        setProgress(Math.round(92 * (1 - Math.exp(-el / 45))) + 4);
      }
    }).then(function(result){
      setProgress(100);
      stageEl.innerHTML = '<b>Hoàn tất.</b> Đã tổng hợp Pareto front bằng Benders.';
      populateResults(result);
      btnRun.disabled = false;
      goToStep(4);
    }).catch(function(err){
      btnRun.disabled = false;
      setProgress(0);
      showError(err && err.message ? err.message : String(err));
    });
  });

  /* ---------------------------------------------------------------------
     3.6 — Kết quả thật: scatter Pareto (canvas) + bảng điểm + vị trí được chọn (Pane 4)
  --------------------------------------------------------------------- */
  function populateResults(res){
    lastResult = res;
    var pts = (res && res.points) || [], sum = (res && res.summary) || {}, meta = (res && res.meta) || {};
    var fx = window.MCLPFx;
    function stat(id, to, o){ var el = document.getElementById(id); if (fx) fx.countUp(el, to, o); else el.textContent = to == null ? '—' : (to.toFixed(o.decimals || 0) + (o.suffix || '')); }
    stat('stat-points', pts.length, { delay: 0.75 });
    stat('stat-gap', sum.mean_gap_pct, { decimals: 2, suffix: ' %', delay: 0.85 });
    stat('stat-converged', sum.n_converged || 0, { suffix: ' / ' + pts.length, delay: 0.95 });
    stat('stat-flagged', sum.n_flagged || 0, { suffix: ' / ' + pts.length, delay: 1.05 });

    var note = document.getElementById('result-note');
    if (!pts.length){
      note.innerHTML = 'Không tìm được nghiệm khả thi. Thử nới P_max, hạ confidence hoặc tăng bán kính phủ.';
    } else {
      var cov = meta.coverable_profit && meta.total_profit ? (100 * meta.coverable_profit / meta.total_profit) : null;
      note.innerHTML =
        '<b>' + esc(meta.n_demand) + '</b> demand · <b>' + esc(meta.n_candidates) + '</b>/' + esc(meta.n_candidates_requested) +
        ' candidate · P<sub>max</sub>=<b>' + esc(meta.P_max == null ? '—' : meta.P_max) + '</b>' +
        (cov != null ? ' · phủ tối đa lý thuyết <b>' + fmt(cov, 1) + '%</b>' : '') +
        (meta.dropped_by_confidence && meta.dropped_by_confidence.length
          ? ' · <span class="warn">' + meta.dropped_by_confidence.length + ' candidate bị loại vì confidence</span>' : '');
    }
    pickedIdx = pts.length ? (res.recommended_index != null ? res.recommended_index : 0) : -1;
    renderPointList();
    renderFacilities();
    if (window.MCLPCharts) window.MCLPCharts.setRun(res.run_id, pts.length, pickedIdx);
  }

  function renderPointList(){
    var host = document.getElementById('pareto-list');
    var pts = (lastResult && lastResult.points) || [];
    if (!pts.length){ host.innerHTML = ''; return; }
    var rows = pts.map(function(q, i){
      var ok = q.status === 'BENDERS_CONVERGED';
      return '<tr data-i="' + i + '" tabindex="0" class="' + (i === pickedIdx ? 'is-picked' : '') + '">' +
        '<td>' + (q.is_recommended ? '<span class="tag tag--rec" title="Điểm khuyến nghị theo λ">★</span>' : '') + (i + 1) + '</td>' +
        '<td>' + fmt(q.epsilon, 3) + '</td>' +
        '<td>' + fmt(q.f1_covering_profit, 1) + '</td>' +
        '<td>' + fmt(q.coverage_pct, 1) + '%</td>' +
        '<td>' + fmt(q.f2_cost, 3) + '</td>' +
        '<td>' + q.n_facilities + '</td>' +
        '<td>' + fmt(q.optimality_gap_pct, 2) + '%</td>' +
        '<td>' + (q.n_benders_iters == null ? '—' : q.n_benders_iters) + '</td>' +
        '<td><span class="tag ' + (ok ? 'tag--ok' : 'tag--warn') + '">' + (ok ? 'hội tụ' : 'hết vòng/giờ') + '</span>' +
          (q.flagged_non_monotonic ? ' <span class="tag tag--warn">non-monotonic</span>' : '') + '</td>' +
        '</tr>';
    }).join('');
    host.innerHTML = '<div class="pareto-list__scroll"><table><thead><tr>' +
      '<th>#</th><th>ε</th><th>f₁ profit</th><th>Phủ</th><th>f₂ cost</th><th>Số CS</th><th>Gap</th><th>Vòng</th><th>Trạng thái</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
    if (window.MCLPFx) window.MCLPFx.pulseRec();
    host.querySelectorAll('tbody tr').forEach(function(tr){
      function pick(){ pickPoint(parseInt(tr.dataset.i, 10)); }
      tr.addEventListener('click', pick);
      tr.addEventListener('keydown', function(e){ if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); pick(); } });
    });
  }

  function renderFacilities(){
    var host = document.getElementById('facility-panel');
    var pts = (lastResult && lastResult.points) || [];
    var q = pts[pickedIdx];
    if (!q){ host.innerHTML = ''; return; }
    var items = q.chosen_uids.map(function(uid, k){
      var c = candidates.find(function(x){ return x.id === uid; });
      var tax = c ? c.taxonomy : '';
      return '<div class="facility">' +
        '<span class="facility__id">' + esc(uid) + '</span>' +
        '<span class="facility__name">' + esc((c && c.name) || q.chosen_names[k] || uid) + '</span>' +
        (c ? '<span class="facility__tax">' + dot(tax) + esc(meta(tax).label) + '</span>' : '') +
        (c && c.lat != null ? '<span class="facility__pos">' + Number(c.lat).toFixed(5) + ', ' + Number(c.lng).toFixed(5) + '</span>' : '') +
        '</div>';
    }).join('');
    host.innerHTML = '<p class="panel__title">Điểm #' + (pickedIdx + 1) + (q.is_recommended ? ' (khuyến nghị)' : '') +
      ' — ' + q.n_facilities + ' vị trí · f₁ = ' + fmt(q.f1_covering_profit, 1) + ' · f₂ = ' + fmt(q.f2_cost, 3) + '</p>' +
      '<div class="facility-grid">' + items + '</div>';
    if (renderFacilities.animate && window.MCLPFx) window.MCLPFx.facilitiesIn(0);
    renderFacilities.animate = true;
  }

  function pickPoint(i){
    if (!lastResult || !lastResult.points[i]) return;
    pickedIdx = i;
    renderPointList();
    renderFacilities();
    drawPareto(false);
    if (window.MCLPCharts) window.MCLPCharts.setPoint(i);
  }

  var drawTween = null;
  function drawPareto(animate){
    animate = animate === true;
    var canvas = document.getElementById('pareto-canvas');
    var pts = (lastResult && lastResult.points) || [];
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;          /* pane đang ẩn -> vẽ lại khi vào Bước 4 */
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var w = rect.width, h = rect.height, padL = 46, padB = 34, padT = 14, padR = 16;
    if (drawTween){ drawTween.kill(); drawTween = null; }

    function axes(){
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = '#263a30'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke();
      ctx.fillStyle = '#5c6d62'; ctx.font = '11px IBM Plex Mono, monospace';
      ctx.fillText('f2 — cost →', w - 84, h - 10);
      ctx.save(); ctx.translate(12, h - padB - 6); ctx.rotate(-Math.PI / 2); ctx.fillText('f1 — covering profit →', 0, 0); ctx.restore();
    }
    dotHits = [];
    axes();
    if (!pts.length) return;

    var xs = pts.map(function(q){ return q.f2_cost; }), ys = pts.map(function(q){ return q.f1_covering_profit; });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    var dx = (x1 - x0) || 1, dy = (y1 - y0) || 1;
    function px(v){ return padL + 10 + (v - x0) / dx * (w - padL - padR - 20); }
    function py(v){ return (h - padB - 10) - (v - y0) / dy * (h - padB - padT - 20); }
    var order = pts.map(function(_, i){ return i; }).sort(function(a, b){ return pts[a].f2_cost - pts[b].f2_cost; });
    var P = order.map(function(i){ return { i: i, q: pts[i], x: px(pts[i].f2_cost), y: py(pts[i].f1_covering_profit) }; });
    P.forEach(function(p){ dotHits.push({ i: p.i, x: p.x, y: p.y }); });

    /* t ∈ [0,1]: đường nối mọc dần từ trái sang phải, mỗi chấm bật lên (back-out) khi đường chạm tới */
    function frame(t){
      axes();
      ctx.fillStyle = '#8ea092';
      ctx.fillText(fmt(x0, 2), padL + 4, h - padB + 14);
      ctx.fillText(fmt(x1, 2), w - padR - 34, h - padB + 14);
      ctx.fillText(fmt(y0, 0), 4, h - padB - 2);
      ctx.fillText(fmt(y1, 0), 4, padT + 10);

      var segs = Math.max(P.length - 1, 1), reach = t * segs;
      ctx.strokeStyle = 'rgba(91,146,121,0.9)'; ctx.lineWidth = 1.2;
      ctx.beginPath();
      P.forEach(function(p, k){
        if (k === 0){ ctx.moveTo(p.x, p.y); return; }
        if (k - 1 >= reach) return;
        var f = Math.min(1, reach - (k - 1)), a = P[k - 1];
        ctx.lineTo(a.x + (p.x - a.x) * f, a.y + (p.y - a.y) * f);
      });
      ctx.stroke();

      P.forEach(function(p, k){
        var born = P.length === 1 ? 0 : k / segs;
        var u = Math.max(0, Math.min(1, (t - born) / 0.12));
        if (u <= 0) return;
        var back = u < 1 ? 1 + 0.45 * Math.sin(u * Math.PI) : 1;
        var r = (p.q.is_recommended ? 6 : 4.5) * u * back;
        ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fillStyle = p.q.flagged_non_monotonic ? '#b5602e' : (p.q.is_recommended ? '#e3b568' : '#d4a24e');
        ctx.fill();
        if (p.i === pickedIdx && u >= 1){ ctx.strokeStyle = '#e7eae2'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(p.x, p.y, 9, 0, Math.PI * 2); ctx.stroke(); }
      });
    }

    if (animate && !reduceMotion && window.gsap){
      var prog = { t: 0 };
      frame(0);
      drawTween = gsap.to(prog, { t: 1, duration: 1.2, delay: 0.1, ease: 'power2.inOut', onUpdate: function(){ frame(prog.t); }, onComplete: function(){ drawTween = null; } });
    } else {
      frame(1);
    }
  }
  window.__drawPareto = drawPareto;

  document.getElementById('pareto-canvas').addEventListener('click', function(e){
    var r = this.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, best = -1, bd = 14;
    dotHits.forEach(function(d){ var dist = Math.hypot(d.x - mx, d.y - my); if (dist < bd){ bd = dist; best = d.i; } });
    if (best >= 0) pickPoint(best);
  });
  window.addEventListener('resize', function(){ if (currentStep === 4) drawPareto(false); });

  /* ---------------------------------------------------------------------
     3.7 — Điều hướng wizard: stepper + Back/Next + transition GSAP
  --------------------------------------------------------------------- */
  var currentStep = 1;
  var wizardBody = document.getElementById('wizard-body');
  var stepperItems = document.querySelectorAll('.stepper__item');
  var stepperLines = document.querySelectorAll('.stepper__line');
  var btnBack = document.getElementById('btn-back');
  var btnNext = document.getElementById('btn-next');
  var wizardHint = document.getElementById('wizard-hint');

  function renderStepper(step){
    stepperItems.forEach(function(it){
      var s = parseInt(it.dataset.step, 10);
      it.classList.toggle('is-active', s === step);
      it.classList.toggle('is-done', s < step);
      it.dataset.clickable = (s < step) ? 'true' : 'false';
    });
    stepperLines.forEach(function(line, i){
      line.classList.toggle('is-done', (i + 1) < step);
    });
  }

  window.updateNav = updateNav;
  function updateNav(){
    btnBack.disabled = currentStep === 1;

    if (currentStep === 1){
      btnNext.style.display = 'inline-block';
      btnNext.textContent = 'Tiếp tục →';
      btnNext.disabled = selected.size === 0;
      wizardHint.textContent = selected.size === 0 ? 'Chọn ít nhất 1 candidate để tiếp tục' : '';
    } else if (currentStep === 2){
      btnNext.style.display = 'inline-block';
      btnNext.textContent = 'Tiếp tục →';
      btnNext.disabled = false;
      wizardHint.textContent = '';
    } else if (currentStep === 3){
      btnNext.style.display = 'none';
      wizardHint.textContent = 'Nhấn "Chạy tối ưu" — Benders giải trên server, có thể mất vài chục giây';
    } else {
      btnNext.style.display = 'none';
      wizardHint.textContent = 'Hoàn tất — dùng "Quay lại" để chỉnh tham số khác';
    }
  }

  function goToStep(target){
    if (target === currentStep || target < 1 || target > 4) return;
    var direction = target > currentStep ? 1 : -1;
    var fromPane = wizardBody.querySelector('.wizard__pane[data-pane="' + currentStep + '"]');
    var toPane = wizardBody.querySelector('.wizard__pane[data-pane="' + target + '"]');

    function finish(){
      currentStep = target;
      renderStepper(currentStep);
      updateNav();
      var fx = window.MCLPFx;
      if (currentStep === 4){
        var cv = document.getElementById('pareto-canvas');
        cv.getContext('2d').clearRect(0, 0, cv.width, cv.height);   /* bỏ bitmap cũ trước khi width đổi */
        if (fx) fx.widen(true, null, function(){ drawPareto(true); });   /* canvas chỉ đo/vẽ sau khi width ổn định */
        else drawPareto(true);
        if (fx) fx.enterResults();
        if (window.MCLPCharts) window.MCLPCharts.activate();
      } else if (fx){
        fx.widen(false, null);
      }
    }

    if (reduceMotion || !window.gsap){
      fromPane.classList.remove('is-active');
      toPane.classList.add('is-active');
      finish();
      return;
    }

    gsap.to(fromPane, {
      opacity: 0, x: -24 * direction, duration: 0.2, ease: 'power1.in',
      onComplete: function(){
        fromPane.classList.remove('is-active');
        gsap.set(toPane, { opacity: 0, x: 24 * direction });
        toPane.classList.add('is-active');
        gsap.to(toPane, { opacity: 1, x: 0, duration: 0.32, ease: 'power2.out' });
        finish();
      }
    });
  }

  btnNext.addEventListener('click', function(){ goToStep(currentStep + 1); });
  btnBack.addEventListener('click', function(){ goToStep(currentStep - 1); });

  stepperItems.forEach(function(it){
    it.addEventListener('click', function(){
      if (it.dataset.clickable === 'true'){ goToStep(parseInt(it.dataset.step, 10)); }
    });
  });

  /* ---------------------------------------------------------------------
     3.8 — Canvas nền hero: đường đồng mức + điểm demand pulse
  --------------------------------------------------------------------- */
  (function initContourCanvas(){
    var canvas = document.getElementById('contour-canvas');
    if (!canvas) return; /* [interface] shell mới dùng #three-bg thay canvas hero */
    var ctx = canvas.getContext('2d');
    var w, h, dpr = window.devicePixelRatio || 1;

    function resize(){
      var rect = canvas.parentElement.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    var lines = 7;
    var dots = Array.from({ length: 9 }).map(function(){
      return { x: Math.random(), y: 0.15 + Math.random() * 0.7, r: 20 + Math.random() * 40, phase: Math.random() * Math.PI * 2 };
    });

    var t = 0;
    function frame(){
      t += reduceMotion ? 0 : 0.006;
      ctx.clearRect(0, 0, w, h);

      for (var i = 0; i < lines; i++){
        ctx.beginPath();
        var base = h * (0.12 + i * (0.8 / lines));
        for (var x = 0; x <= w; x += 8){
          var y = base + Math.sin(x * 0.006 + t * 2 + i * 0.7) * 14 + Math.sin(x * 0.014 + t * 1.3 + i) * 6;
          x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.strokeStyle = 'rgba(94,124,105,' + (0.10 + i * 0.01) + ')';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      dots.forEach(function(d){
        var cx = d.x * w, cy = d.y * h;
        var pulse = (Math.sin(t * 1.4 + d.phase) + 1) / 2;
        ctx.beginPath();
        ctx.arc(cx, cy, d.r * (0.5 + pulse * 0.5), 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(212,162,78,' + (0.14 * (1 - pulse)) + ')';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(cx, cy, 2.2, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(212,162,78,0.7)';
        ctx.fill();
      });

      if (!reduceMotion) requestAnimationFrame(frame);
    }
    frame();
  })();


  /* ---------------------------------------------------------------------
     3.10 — [interface] slider-fill, custom cursor, nền three.js
  --------------------------------------------------------------------- */
  document.querySelectorAll('.slider-wrap').forEach(function(wrap){
    var input = wrap.querySelector('input[type="range"]');
    var fill = wrap.querySelector('.slider-fill');
    if (!input || !fill) return;
    function paint(){
      var min = +input.min || 0, max = +input.max || 100;
      fill.style.width = ((input.value - min) / (max - min) * 100) + '%';
    }
    input.addEventListener('input', paint);
    paint();
  });

  (function initCursor(){
    var dot = document.getElementById('custom-cursor');
    var ring = document.getElementById('cursor-follower');
    var fine = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    if (!dot || !ring || !fine) { if (dot) dot.remove(); if (ring) ring.remove(); return; }
    document.body.classList.add('has-cursor');
    var mx = 0, my = 0, rx = 0, ry = 0;
    document.addEventListener('mousemove', function(e){
      mx = e.clientX; my = e.clientY;
      dot.style.left = mx + 'px'; dot.style.top = my + 'px';
      ring.classList.toggle('is-hover', !!e.target.closest('button, .candidate, .chip, .stepper__item[data-clickable="true"], input'));
    });
    (function follow(){
      rx += (mx - rx) * 0.18; ry += (my - ry) * 0.18;
      ring.style.left = rx + 'px'; ring.style.top = ry + 'px';
      requestAnimationFrame(follow);
    })();
  })();

  (function initThreeBg(){
    var host = document.getElementById('three-bg');
    if (!host || !window.THREE || reduceMotion) return;
    var renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    host.appendChild(renderer.domElement);
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.z = 18;
    var pos = new Float32Array(420 * 3);
    for (var i = 0; i < pos.length; i++) pos[i] = (Math.random() - 0.5) * 40;
    var geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    var pts = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.07, color: 0xd4a24e, transparent: true, opacity: 0.35 }));
    scene.add(pts);
    window.addEventListener('resize', function(){
      renderer.setSize(window.innerWidth, window.innerHeight);
      camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix();
    });
    (function loop(){ pts.rotation.y += 0.0006; pts.rotation.x += 0.0002; renderer.render(scene, camera); requestAnimationFrame(loop); })();
  })();

  /* ---------------------------------------------------------------------
     3.9 — Khởi tạo
  --------------------------------------------------------------------- */
  renderGrid();
  renderThresholdList();
  updateSummary();
  renderStepper(currentStep);
  updateNav();

})();
