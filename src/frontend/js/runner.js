    /* ========== JS ========== */

    // ---------- Data ----------
    const CANDIDATES = [
      { id: 'C1', name: 'Khu Công nghệ Đà Lạt', cost: 45, lat: 28, lng: 32, demandNearby: 12 },
      { id: 'C2', name: 'Trung tâm Phường 1', cost: 38, lat: 45, lng: 55, demandNearby: 18 },
      { id: 'C3', name: 'Khu Du lịch Hồ Xuân Hương', cost: 52, lat: 62, lng: 38, demandNearby: 9 },
      { id: 'C4', name: 'Cảng hàng không Liên Khương', cost: 67, lat: 22, lng: 68, demandNearby: 7 },
      { id: 'C5', name: 'Khu dân cư Lâm Viên', cost: 29, lat: 55, lng: 72, demandNearby: 15 },
      { id: 'C6', name: 'Khu công nghiệp Phú Hội', cost: 41, lat: 78, lng: 48, demandNearby: 11 },
      { id: 'C7', name: 'Trung tâm thương mại BigC', cost: 48, lat: 40, lng: 25, demandNearby: 14 },
      { id: 'C8', name: 'Khu nghỉ dưỡng Tuyền Lâm', cost: 58, lat: 70, lng: 65, demandNearby: 6 },
    ];

    const DEMANDS = Array.from({ length: 24 }, (_, i) => ({
      id: `D${i + 1}`,
      lat: 15 + Math.random() * 70,
      lng: 15 + Math.random() * 70,
      profit: Math.floor(8 + Math.random() * 25)
    }));

    let selected = new Set();
    let thresholds = {}; // { C1: { coverage: 0.7, risk: 0.3 }, ... }
    let radius = 5;
    let confidence = 0.85;
    let budget = 120;
    let alpha = 0.7;

    // ---------- Three.js background ----------
    (function initThree() {
      const canvas = document.getElementById('bg-canvas');
      const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(window.innerWidth, window.innerHeight);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
      camera.position.z = 18;

      const geo = new THREE.BufferGeometry();
      const count = 900;
      const pos = new Float32Array(count * 3);
      for (let i = 0; i < count * 3; i++) pos[i] = (Math.random() - 0.5) * 40;
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));

      const mat = new THREE.PointsMaterial({
        size: 0.06,
        color: 0x22d3ee,
        transparent: true,
        opacity: 0.55,
        sizeAttenuation: true
      });
      const points = new THREE.Points(geo, mat);
      scene.add(points);

      // subtle connecting lines
      const lineGeo = new THREE.BufferGeometry();
      const linePos = new Float32Array(120 * 3);
      for (let i = 0; i < 120 * 3; i++) linePos[i] = (Math.random() - 0.5) * 30;
      lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
      const lineMat = new THREE.LineBasicMaterial({ color: 0xa78bfa, transparent: true, opacity: 0.12 });
      const lines = new THREE.LineSegments(lineGeo, lineMat);
      scene.add(lines);

      function animate() {
        requestAnimationFrame(animate);
        points.rotation.y += 0.0008;
        points.rotation.x += 0.0003;
        lines.rotation.y -= 0.0005;
        renderer.render(scene, camera);
      }
      animate();

      window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
      });
    })();

    // ---------- Render candidates ----------
    function renderCandidates() {
      const list = document.getElementById('candidate-list');
      list.innerHTML = '';
      CANDIDATES.forEach(c => {
        const el = document.createElement('div');
        el.className = 'candidate-item' + (selected.has(c.id) ? ' selected' : '');
        el.dataset.id = c.id;
        el.innerHTML = `
          <div class="candidate-check">
            <svg viewBox="0 0 24 24" fill="none"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <div class="candidate-info">
            <div class="candidate-name">${c.name}</div>
            <div class="candidate-meta">Cost ${c.cost} · Demand ~${c.demandNearby}</div>
          </div>
          <span class="candidate-badge">${c.id}</span>
        `;
        el.addEventListener('click', () => toggleCandidate(c.id));
        list.appendChild(el);
      });
      document.getElementById('selected-count').textContent = `${selected.size} chọn`;
      renderThresholdCards();
      renderMapNodes();
    }

    function toggleCandidate(id) {
      if (selected.has(id)) {
        selected.delete(id);
        delete thresholds[id];
      } else {
        selected.add(id);
        thresholds[id] = { coverage: 0.75, risk: 0.25 };
      }
      renderCandidates();
      anime({
        targets: `.candidate-item[data-id="${id}"]`,
        scale: [0.96, 1],
        duration: 280,
        easing: 'easeOutElastic(1, .6)'
      });
    }

    // ---------- Threshold cards ----------
    function renderThresholdCards() {
      const container = document.getElementById('threshold-cards');
      container.innerHTML = '';
      CANDIDATES.forEach(c => {
        const active = selected.has(c.id);
        const t = thresholds[c.id] || { coverage: 0.75, risk: 0.25 };
        const card = document.createElement('div');
        card.className = 'threshold-card' + (active ? ' active' : '');
        card.innerHTML = `
          <div class="name">${c.id} — ${c.name.split(' ').slice(0, 3).join(' ')}</div>
          <div class="slider-group">
            <div class="slider-label">
              <span>Coverage threshold</span>
              <span id="th-cov-${c.id}">${t.coverage.toFixed(2)}</span>
            </div>
            <input type="range" min="0.4" max="0.95" step="0.05" value="${t.coverage}"
              data-id="${c.id}" data-key="coverage" ${active ? '' : 'disabled'} />
          </div>
          <div class="slider-group">
            <div class="slider-label">
              <span>Risk tolerance</span>
              <span id="th-risk-${c.id}">${t.risk.toFixed(2)}</span>
            </div>
            <input type="range" min="0.05" max="0.6" step="0.05" value="${t.risk}"
              data-id="${c.id}" data-key="risk" ${active ? '' : 'disabled'} />
          </div>
        `;
        container.appendChild(card);
      });

      container.querySelectorAll('input[type="range"]').forEach(input => {
        input.addEventListener('input', e => {
          const id = e.target.dataset.id;
          const key = e.target.dataset.key;
          const val = parseFloat(e.target.value);
          if (!thresholds[id]) thresholds[id] = {};
          thresholds[id][key] = val;
          document.getElementById(key === 'coverage' ? `th-cov-${id}` : `th-risk-${id}`).textContent = val.toFixed(2);
        });
      });
    }

    // ---------- Map nodes ----------
    function renderMapNodes() {
      const area = document.getElementById('map-placeholder');
      // clear old nodes & rings
      area.querySelectorAll('.node, .coverage-ring').forEach(n => n.remove());

      DEMANDS.forEach(d => {
        const n = document.createElement('div');
        n.className = 'node demand';
        n.style.left = d.lng + '%';
        n.style.top = d.lat + '%';
        n.title = `${d.id} · profit ${d.profit}`;
        area.appendChild(n);
      });

      CANDIDATES.forEach(c => {
        const n = document.createElement('div');
        n.className = 'node' + (selected.has(c.id) ? ' selected-candidate' : '');
        n.style.left = c.lng + '%';
        n.style.top = c.lat + '%';
        n.title = c.name;
        area.appendChild(n);

        if (selected.has(c.id)) {
          const ring = document.createElement('div');
          ring.className = 'coverage-ring';
          ring.style.left = c.lng + '%';
          ring.style.top = c.lat + '%';
          const size = radius * 8; // visual scale
          ring.style.width = size + 'px';
          ring.style.height = size + 'px';
          area.appendChild(ring);
          gsap.to(ring, { opacity: 0.7, duration: 0.5, ease: 'power2.out' });
        }
      });
    }

    // ---------- Global sliders ----------
    function bindGlobalSliders() {
      const map = [
        { id: 'slider-radius', val: 'val-radius', pill: 'pill-radius', key: 'radius', fmt: v => v.toFixed(1), suffix: ' km' },
        { id: 'slider-confidence', val: 'val-confidence', pill: 'pill-conf', key: 'confidence', fmt: v => v.toFixed(2) },
        { id: 'slider-budget', val: 'val-budget', key: 'budget', fmt: v => v },
        { id: 'slider-alpha', val: 'val-alpha', key: 'alpha', fmt: v => v.toFixed(2) }
      ];

      map.forEach(m => {
        const el = document.getElementById(m.id);
        el.addEventListener('input', e => {
          const v = parseFloat(e.target.value);
          window[m.key] = v;
          document.getElementById(m.val).textContent = m.fmt(v);
          if (m.pill) {
            const label = m.key === 'radius' ? `Bán kính: ${m.fmt(v)}${m.suffix || ''}` : `Confidence: ${m.fmt(v)}`;
            document.getElementById(m.pill).textContent = label;
          }
          if (m.key === 'radius') renderMapNodes();
        });
      });
    }

    // ---------- Optimize (simulated) ----------
    document.getElementById('btn-optimize').addEventListener('click', () => {
      if (selected.size === 0) {
        anime({
          targets: '#panel-candidates',
          translateX: [-8, 8, -6, 6, 0],
          duration: 400,
          easing: 'easeInOutSine'
        });
        return;
      }

      const status = document.getElementById('run-status');
      status.classList.add('visible');

      // simulate solver
      setTimeout(() => {
        const totalCost = [...selected].reduce((s, id) => {
          const c = CANDIDATES.find(x => x.id === id);
          return s + (c ? c.cost : 0);
        }, 0);

        const coverRatio = Math.min(0.98, 0.55 + selected.size * 0.08 + (radius - 3) * 0.03);
        const profit = Math.floor(coverRatio * 420 + confidence * 80);

        document.getElementById('stat-profit').textContent = profit;
        document.getElementById('stat-cost').textContent = totalCost;
        document.getElementById('stat-facilities').textContent = selected.size;
        document.getElementById('pill-cover').textContent = `Phủ: ${(coverRatio * 100).toFixed(0)}%`;

        document.getElementById('obj-profit').textContent = profit;
        document.getElementById('obj-cost').textContent = totalCost;
        document.getElementById('obj-cover').textContent = (coverRatio * 100).toFixed(0) + '%';

        gsap.to('#prog-profit', { width: `${Math.min(100, coverRatio * 100)}%`, duration: 0.8 });
        gsap.to('#prog-cost', { width: `${Math.min(100, (totalCost / budget) * 100)}%`, duration: 0.8 });
        gsap.to('#prog-cover', { width: `${coverRatio * 100}%`, duration: 0.8 });

        status.classList.remove('visible');

        // celebrate nodes
        anime({
          targets: '.node.selected-candidate',
          scale: [1, 1.6, 1],
          duration: 600,
          delay: anime.stagger(80),
          easing: 'easeOutElastic(1, .5)'
        });
      }, 1400);
    });

    document.getElementById('btn-reset').addEventListener('click', () => {
      selected.clear();
      thresholds = {};
      document.getElementById('slider-radius').value = 5;
      document.getElementById('slider-confidence').value = 0.85;
      document.getElementById('slider-budget').value = 120;
      document.getElementById('slider-alpha').value = 0.7;
      radius = 5; confidence = 0.85; budget = 120; alpha = 0.7;
      document.getElementById('val-radius').textContent = '5.0';
      document.getElementById('val-confidence').textContent = '0.85';
      document.getElementById('val-budget').textContent = '120';
      document.getElementById('val-alpha').textContent = '0.70';
      document.getElementById('pill-radius').textContent = 'Bán kính: 5.0 km';
      document.getElementById('pill-conf').textContent = 'Confidence: 0.85';
      document.getElementById('pill-cover').textContent = 'Phủ: —';
      document.getElementById('stat-profit').textContent = '—';
      document.getElementById('stat-cost').textContent = '—';
      document.getElementById('stat-facilities').textContent = '0';
      ['prog-profit', 'prog-cost', 'prog-cover'].forEach(id => {
        document.getElementById(id).style.width = '0%';
      });
      renderCandidates();
    });

    // ---------- Entrance animations ----------
    gsap.from('#panel-candidates', { x: -40, opacity: 0, duration: 0.7, ease: 'power3.out' });
    gsap.from('#panel-viz', { y: 30, opacity: 0, duration: 0.7, delay: 0.15, ease: 'power3.out' });
    gsap.from('#panel-params', { x: 40, opacity: 0, duration: 0.7, delay: 0.25, ease: 'power3.out' });

    // Init
    bindGlobalSliders();
    renderCandidates();