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
    var roots = Object.keys(selectedByRoot()), tax = {};
    roots.forEach(function(r){ tax[r] = { radius_m: taxParams[r].radius, weight: taxParams[r].weight }; });
    return {
      candidates: Array.from(selected),
      taxonomy_root: tax,
      per_candidate: perCandidateParams,
      min_confidence: parseFloat(document.getElementById('confidence').value),
      P_max: parseInt(document.getElementById('pmax').value, 10),
      n_points: parseInt(document.getElementById('epsilon-steps').value, 10),
      lambda: [parseInt(balanceInput.value, 10), 100 - parseInt(balanceInput.value, 10)]
    };
  };
  bindRange('confidence',    'val-confidence',    function(v){ return parseFloat(v).toFixed(2); });
  bindRange('epsilon-steps', 'val-epsilon',       function(v){ return v; });

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
     3.5 — Mô phỏng pipeline chạy tối ưu (Pane 3 → Pane 4)
  --------------------------------------------------------------------- */
  var STAGES = [
    'Dựng covering constraints (build_base_template)…',
    'Nhân bản model theo từng epsilon (proto_copy)…',
    'Giải song song theo batch — CP-SAT subprocess…',
    'Truyền hint giữa các batch (inter-batch hint chaining)…',
    'Tổng hợp Pareto front, gắn cờ non-monotonic…'
  ];

  var btnRun = document.getElementById('btn-run');
  var pipelineEl = document.getElementById('pipeline');
  var fillEl = document.getElementById('pipeline-fill');
  var stageEl = document.getElementById('pipeline-stage');

  btnRun.addEventListener('click', function(){
    if (selected.size === 0) return;
    console.info('[run config]', window.getRunConfig());
    btnRun.disabled = true;
    pipelineEl.classList.add('is-visible');

    var i = 0;
    fillEl.style.width = '0%';

    function nextStage(){
      if (i >= STAGES.length){
        stageEl.innerHTML = '<b>Hoàn tất.</b> Đã tổng hợp Pareto front.';
        populateResults();
        btnRun.disabled = false;
        goToStep(4);
        return;
      }
      stageEl.innerHTML = '<b>' + (i + 1) + '/' + STAGES.length + '</b>&nbsp;' + STAGES[i];
      var pct = Math.round(((i + 1) / STAGES.length) * 100);
      if (!reduceMotion && window.gsap){
        gsap.to(fillEl, { width: pct + '%', duration: 0.5, ease: 'power1.inOut' });
      } else {
        fillEl.style.width = pct + '%';
      }
      i++;
      setTimeout(nextStage, reduceMotion ? 80 : 560);
    }
    nextStage();
  });

  /* ---------------------------------------------------------------------
     3.6 — Kết quả: scatter Pareto front (canvas) — Pane 4
  --------------------------------------------------------------------- */
  function populateResults(){
    document.getElementById('stat-points').textContent = 11;
    document.getElementById('stat-gap').textContent = '1.6 %';
    document.getElementById('stat-flagged').textContent = '1 / 11';
    drawPareto();
  }

  function drawPareto(){
    var canvas = document.getElementById('pareto-canvas');
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    var w = rect.width, h = rect.height;
    var pad = 34;

    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = '#263a30';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, 12); ctx.lineTo(pad, h - pad); ctx.lineTo(w - 12, h - pad);
    ctx.stroke();

    ctx.fillStyle = '#5c6d62';
    ctx.font = '11px IBM Plex Mono, monospace';
    ctx.fillText('f2 — cost →', w - 78, h - 12);
    ctx.save();
    ctx.translate(14, pad + 6);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('f1 — coverage →', 0, 0);
    ctx.restore();

    var n = 11;
    var points = [];
    for (var k = 0; k < n; k++){
      var t = k / (n - 1);
      var x = pad + t * (w - pad - 24);
      var y = (h - pad) - Math.pow(t, 0.62) * (h - pad - 24);
      points.push({ x: x, y: y, flagged: k === 7 });
    }

    function drawDots(alpha){
      ctx.clearRect(pad + 0.5, 0, w - pad - 0.5, h - pad - 0.5);
      ctx.strokeStyle = 'rgba(91,146,121,' + alpha + ')';
      ctx.beginPath();
      points.forEach(function(p, idx){ idx === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y); });
      ctx.stroke();
      points.forEach(function(p){
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.flagged ? 5 : 4, 0, Math.PI * 2);
        ctx.fillStyle = p.flagged ? '#b5602e' : '#d4a24e';
        ctx.globalAlpha = alpha;
        ctx.fill();
        ctx.globalAlpha = 1;
      });
    }

    if (!reduceMotion && window.gsap){
      var progress = { v: 0 };
      gsap.to(progress, { v: 1, duration: 0.8, ease: 'power2.out', onUpdate: function(){ drawDots(progress.v); } });
    } else {
      drawDots(1);
    }
  }

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
      wizardHint.textContent = 'Nhấn "Chạy tối ưu" bên dưới để xem kết quả';
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
