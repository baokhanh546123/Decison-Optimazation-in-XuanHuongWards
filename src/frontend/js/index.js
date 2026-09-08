 // ================================================================
    // PART 1: GSAP + ScrollTrigger for marketing sections (infinite loop panels style)
    // ================================================================
    import gsap from 'https://cdn.esm.sh/gsap@3.12.2';
    import { ScrollTrigger } from 'https://cdn.esm.sh/gsap@3.12.2/ScrollTrigger.js';

    gsap.registerPlugin(ScrollTrigger);

    // Challenge cards
    gsap.to('.challenge-card', {
      opacity: 1,
      y: 0,
      duration: 0.6,
      stagger: 0.12,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: '.challenge-grid',
        start: 'top 82%',
        toggleActions: 'play none none none'
      }
    });

    // Team cards
    gsap.to('.team-card', {
      opacity: 1,
      y: 0,
      duration: 0.55,
      stagger: 0.1,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: '.team-grid',
        start: 'top 82%',
        toggleActions: 'play none none none'
      }
    });

    // Hero proof counters animation (simple)
    gsap.from('.proof-item__val', {
      opacity: 0,
      y: 16,
      duration: 0.7,
      stagger: 0.15,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: '.hero__proof',
        start: 'top 85%',
        toggleActions: 'play none none none'
      }
    });

    // Smooth reveal for hero content
    gsap.from('.hero__inner > *', {
      opacity: 0,
      y: 24,
      duration: 0.6,
      stagger: 0.1,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: '.hero',
        start: 'top 80%',
        toggleActions: 'play none none none'
      }
    });

    // Final CTA fade
    gsap.from('.final-cta__inner', {
      opacity: 0,
      y: 30,
      duration: 0.7,
      ease: 'power2.out',
      scrollTrigger: {
        trigger: '.final-cta',
        start: 'top 80%',
        toggleActions: 'play none none none'
      }
    });

    // Topbar scroll shadow
    const topbar = document.getElementById('topbar');
    window.addEventListener('scroll', () => {
      if (window.scrollY > 20) topbar.classList.add('scrolled');
      else topbar.classList.remove('scrolled');
    }, { passive: true });

    // ================================================================
    // PART 2: 3D SCROLLYTELLING (from index.html — preserved)
    // ================================================================
    // Import Three.js and other deps
    import * as THREE from 'three';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
    import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

    // DOM refs for 3D section
    const sceneCol = document.getElementById('sceneCol');
    const textCol = document.getElementById('textCol');
    const sections = document.querySelectorAll('.section-text');
    const progressBar = document.getElementById('scrollProgressBar');
    const sceneHud = document.getElementById('sceneHud');
    const hudSection = document.getElementById('hudSection');
    const hudRadius = document.getElementById('hudRadius');
    const sectionNav = document.getElementById('sectionNav');

    // Build section nav dots
    sections.forEach((sec, i) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('aria-label', `Section ${i + 1}`);
      btn.addEventListener('click', () => {
        sec.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      sectionNav.appendChild(btn);
    });
    const navButtons = sectionNav.querySelectorAll('button');

    // ================================================================
    // DATA — demand & candidate
    // ================================================================
    const CITY = {
      roadAxes: [0, -3.2, 3.2],
      mainHalf: 0.22,
      secHalf: 0.18,
      clearMain: 0.22 + 0.28,
      clearSec: 0.18 + 0.28,
      cityMin: -4.9,
      cityMax: 4.9,
    };

    function onAsphalt(x, z, extra = 0) {
      for (const a of CITY.roadAxes) {
        const half = a === 0 ? CITY.clearMain : CITY.clearSec;
        if (Math.abs(z - a) < half + extra) return true;
        if (Math.abs(x - a) < half + extra) return true;
      }
      if (Math.hypot(x, z) < 0.85 + extra) return true;
      return false;
    }

    function buildDemandPoints() {
      const pts = [];
      const bands = [
        [-4.85, -3.2 - CITY.clearSec],
        [-3.2 + CITY.clearSec, -CITY.clearMain],
        [CITY.clearMain, 3.2 - CITY.clearSec],
        [3.2 + CITY.clearSec, 4.85],
      ];
      let id = 0;
      for (const [x0, x1] of bands) {
        for (const [z0, z1] of bands) {
          const bw = x1 - x0;
          const bd = z1 - z0;
          if (bw < 0.4 || bd < 0.4) continue;
          const cols = Math.max(2, Math.round(bw / 0.55));
          const rows = Math.max(2, Math.round(bd / 0.55));
          for (let i = 0; i < cols; i++) {
            for (let j = 0; j < rows; j++) {
              const u = (i + 0.35 + ((i * 3 + j) % 3) * 0.12) / cols;
              const v = (j + 0.35 + ((j * 5 + i) % 3) * 0.12) / rows;
              const x = x0 + u * bw;
              const z = z0 + v * bd;
              if (onAsphalt(x, z, 0.08)) continue;
              if (Math.hypot(x, z) > 5.15) continue;
              const dist = Math.hypot(x, z);
              const w = THREE.MathUtils.clamp(0.95 - dist * 0.1 + ((id * 13) % 7) * 0.04, 0.28, 1);
              pts.push({ id: id++, x, y: z, w });
            }
          }
        }
      }
      return pts;
    }

    function buildCandidateSites() {
      const sites = [];
      const cornerInset = 0.55;
      const junctions = [0, -3.2, 3.2];
      let id = 0;
      for (const jx of junctions) {
        for (const jz of junctions) {
          const signs = [[1,1],[1,-1],[-1,1],[-1,-1]];
          for (const [sx, sz] of signs) {
            const x = jx + sx * cornerInset;
            const z = jz + sz * cornerInset;
            if (Math.abs(x) > 5.0 || Math.abs(z) > 5.0) continue;
            if (onAsphalt(x, z, 0.05)) continue;
            if (Math.hypot(x, z) < 0.9) continue;
            const dist = Math.hypot(x, z);
            const cost = THREE.MathUtils.clamp(0.35 + dist * 0.08 + (id % 5) * 0.03, 0.35, 0.95);
            sites.push({ id: id++, x, y: z, cost });
          }
        }
      }
      const mids = [
        [1.6,1.6],[1.6,-1.6],[-1.6,1.6],[-1.6,-1.6],
        [1.6,4.0],[-1.6,4.0],[1.6,-4.0],[-1.6,-4.0],
        [4.0,1.6],[4.0,-1.6],[-4.0,1.6],[-4.0,-1.6],
        [4.0,4.0],[4.0,-4.0],[-4.0,4.0],[-4.0,-4.0],
      ];
      for (const [x, z] of mids) {
        if (onAsphalt(x, z, 0.05)) continue;
        const dist = Math.hypot(x, z);
        const cost = THREE.MathUtils.clamp(0.4 + dist * 0.07, 0.4, 0.95);
        sites.push({ id: id++, x, y: z, cost });
      }
      return sites;
    }

    const demandData = buildDemandPoints();
    const candidateData = buildCandidateSites();

    const numPareto = 20;
    const paretoData = [];
    for (let i = 0; i < numPareto; i++) {
      const coverage = 0.6 + (i / (numPareto - 1)) * 0.35;
      const cost = 0.6 - (i / (numPareto - 1)) * 0.4;
      const numFac = Math.floor(5 + cost * 20);
      const shuffled = [...Array(candidateData.length).keys()];
      for (let j = shuffled.length - 1; j > 0; j--) {
        const k = Math.floor(Math.random() * (j + 1));
        [shuffled[j], shuffled[k]] = [shuffled[k], shuffled[j]];
      }
      const indices = shuffled.slice(0, Math.min(numFac, shuffled.length));
      paretoData.push({ coverage, cost, dominated: false, facilityAssignment: indices });
    }
    for (let i = 0; i < paretoData.length; i++) {
      let dominated = false;
      for (let j = 0; j < paretoData.length; j++) {
        if (i === j) continue;
        const a = paretoData[i];
        const b = paretoData[j];
        if (b.coverage >= a.coverage && b.cost <= a.cost && (b.coverage > a.coverage || b.cost < a.cost)) {
          dominated = true;
          break;
        }
      }
      paretoData[i].dominated = dominated;
    }
    const selectedSolutionIndex = paretoData.findIndex(p => !p.dominated);

    document.getElementById('demandCount').textContent = demandData.length;
    document.getElementById('candidateCount').textContent = candidateData.length;

    // ================================================================
    // THREE.JS SETUP
    // ================================================================
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x070b14);
    scene.fog = new THREE.FogExp2(0x070b14, 0.045);

    const camera = new THREE.PerspectiveCamera(38, sceneCol.clientWidth / sceneCol.clientHeight, 0.1, 40);
    camera.position.set(0, 6.8, 9.5);
    camera.lookAt(0, 0.2, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    renderer.setSize(sceneCol.clientWidth, sceneCol.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    sceneCol.prepend(renderer.domElement);

    // Lighting
    const ambient = new THREE.AmbientLight(0x2a3a55, 0.55);
    scene.add(ambient);

    const mainLight = new THREE.DirectionalLight(0xfff0e0, 1.85);
    mainLight.position.set(7, 14, 5);
    mainLight.castShadow = true;
    mainLight.shadow.mapSize.set(1024, 1024);
    const d = 9;
    mainLight.shadow.camera.left = -d;
    mainLight.shadow.camera.right = d;
    mainLight.shadow.camera.top = d;
    mainLight.shadow.camera.bottom = -d;
    mainLight.shadow.camera.near = 1;
    mainLight.shadow.camera.far = 25;
    mainLight.shadow.bias = -0.0008;
    scene.add(mainLight);

    const fillLight = new THREE.DirectionalLight(0x6a9fff, 0.55);
    fillLight.position.set(-5, 3, 7);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0x88c8ff, 0.35);
    rimLight.position.set(0, 2, -8);
    scene.add(rimLight);

    // Ground
    const groundGeo = new THREE.CircleGeometry(6.8, 64);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x0a121c,
      roughness: 0.95,
      metalness: 0.03,
      side: THREE.DoubleSide,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.04;
    ground.receiveShadow = true;
    scene.add(ground);

    const ringGeo = new THREE.RingGeometry(6.2, 6.8, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x152030,
      transparent: true,
      opacity: 0.7,
      side: THREE.DoubleSide,
    });
    const outerRing = new THREE.Mesh(ringGeo, ringMat);
    outerRing.rotation.x = -Math.PI / 2;
    outerRing.position.y = 0.005;
    scene.add(outerRing);

    // Sun
    const sunGroup = new THREE.Group();
    const sunCore = new THREE.Mesh(
      new THREE.SphereGeometry(0.35, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xfff0c0 })
    );
    sunGroup.add(sunCore);
    const sunGlow = new THREE.Mesh(
      new THREE.SphereGeometry(0.55, 16, 16),
      new THREE.MeshBasicMaterial({
        color: 0xffcc66,
        transparent: true,
        opacity: 0.35,
        depthWrite: false,
      })
    );
    sunGroup.add(sunGlow);
    const sunHalo = new THREE.Mesh(
      new THREE.SphereGeometry(0.9, 16, 16),
      new THREE.MeshBasicMaterial({
        color: 0xffaa44,
        transparent: true,
        opacity: 0.12,
        depthWrite: false,
      })
    );
    sunGroup.add(sunHalo);
    sunGroup.position.set(5.5, 4.2, -4.5);
    scene.add(sunGroup);

    // Roads
    const roadsGroup = new THREE.Group();
    const roadMat = new THREE.MeshStandardMaterial({
      color: 0x1a2230,
      roughness: 0.9,
      metalness: 0.05,
    });
    const lineMat = new THREE.MeshBasicMaterial({
      color: 0xc8b060,
      transparent: true,
      opacity: 0.55,
    });
    const sidewalkMat = new THREE.MeshStandardMaterial({
      color: 0x2a3548,
      roughness: 0.85,
      metalness: 0.05,
    });

    function addRoadSegment(x1, z1, x2, z2, width = 0.38) {
      const dx = x2 - x1;
      const dz = z2 - z1;
      const len = Math.sqrt(dx * dx + dz * dz);
      const angle = Math.atan2(dz, dx);
      const midX = (x1 + x2) / 2;
      const midZ = (z1 + z2) / 2;

      const sw = new THREE.Mesh(
        new THREE.BoxGeometry(len + 0.08, 0.015, width + 0.22),
        sidewalkMat
      );
      sw.position.set(midX, 0.008, midZ);
      sw.rotation.y = -angle;
      sw.receiveShadow = true;
      roadsGroup.add(sw);

      const road = new THREE.Mesh(
        new THREE.BoxGeometry(len, 0.02, width),
        roadMat
      );
      road.position.set(midX, 0.018, midZ);
      road.rotation.y = -angle;
      road.receiveShadow = true;
      roadsGroup.add(road);

      const dashCount = Math.max(2, Math.floor(len / 0.35));
      for (let i = 0; i < dashCount; i++) {
        if (i % 2 === 0) continue;
        const t = (i + 0.5) / dashCount;
        const lx = x1 + dx * t;
        const lz = z1 + dz * t;
        const dash = new THREE.Mesh(
          new THREE.BoxGeometry(0.14, 0.008, 0.025),
          lineMat
        );
        dash.position.set(lx, 0.03, lz);
        dash.rotation.y = -angle;
        roadsGroup.add(dash);
      }
    }

    addRoadSegment(-5.2, 0, 5.2, 0, 0.42);
    addRoadSegment(0, -5.2, 0, 5.2, 0.42);
    addRoadSegment(-5.0, -3.2, 5.0, -3.2, 0.34);
    addRoadSegment(-5.0, 3.2, 5.0, 3.2, 0.34);
    addRoadSegment(-3.2, -5.0, -3.2, 5.0, 0.34);
    addRoadSegment(3.2, -5.0, 3.2, 5.0, 0.34);
    scene.add(roadsGroup);

    // Bus stops
    const busStopsGroup = new THREE.Group();
    function createBusStop(x, z, rotY = 0) {
      const g = new THREE.Group();
      const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.02, 0.025, 0.45, 6),
        new THREE.MeshStandardMaterial({ color: 0x8899aa, metalness: 0.6, roughness: 0.3 })
      );
      pole.position.y = 0.22;
      pole.castShadow = true;
      g.add(pole);
      const sign = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, 0.12, 0.02),
        new THREE.MeshStandardMaterial({
          color: 0x2a6aaa,
          emissive: 0x1a4a88,
          emissiveIntensity: 0.4,
          metalness: 0.2,
          roughness: 0.4,
        })
      );
      sign.position.set(0, 0.42, 0.02);
      g.add(sign);
      const roof = new THREE.Mesh(
        new THREE.BoxGeometry(0.35, 0.02, 0.2),
        new THREE.MeshStandardMaterial({ color: 0x445566, metalness: 0.3, roughness: 0.5 })
      );
      roof.position.set(0.08, 0.38, 0);
      g.add(roof);
      const bench = new THREE.Mesh(
        new THREE.BoxGeometry(0.28, 0.03, 0.1),
        new THREE.MeshStandardMaterial({ color: 0x5a4a3a, roughness: 0.7 })
      );
      bench.position.set(0.08, 0.12, 0);
      g.add(bench);
      g.position.set(x, 0, z);
      g.rotation.y = rotY;
      return g;
    }
    const busStopPositions = [
      [1.8, 0.35, 0], [-2.1, -0.35, Math.PI], [0.35, 2.0, Math.PI/2],
      [-0.35, -2.2, -Math.PI/2], [3.5, 3.5, 0.4], [-3.4, 3.0, -0.5],
    ];
    busStopPositions.forEach(([x, z, r]) => busStopsGroup.add(createBusStop(x, z, r)));
    scene.add(busStopsGroup);

    // Buildings (procedural)
    const buildings = new THREE.Group();
    scene.add(buildings);

    const ROAD_HALF = { main: 0.22, secondary: 0.18 };
    const SIDEWALK = 0.18;
    const LOT_PAD = 0.06;
    const MIN_LOT = 0.45;

    const ROAD_LINES = [
      { axis: 'z', value: 0, half: ROAD_HALF.main + SIDEWALK },
      { axis: 'x', value: 0, half: ROAD_HALF.main + SIDEWALK },
      { axis: 'z', value: -3.2, half: ROAD_HALF.secondary + SIDEWALK },
      { axis: 'z', value: 3.2, half: ROAD_HALF.secondary + SIDEWALK },
      { axis: 'x', value: -3.2, half: ROAD_HALF.secondary + SIDEWALK },
      { axis: 'x', value: 3.2, half: ROAD_HALF.secondary + SIDEWALK },
    ];

    function nearRoad(x, z, footprintR = 0.15) {
      for (const r of ROAD_LINES) {
        if (r.axis === 'z' && Math.abs(z - r.value) < r.half + footprintR) return true;
        if (r.axis === 'x' && Math.abs(x - r.value) < r.half + footprintR) return true;
      }
      if (Math.hypot(x, z) < 0.95 + footprintR) return true;
      if (Math.hypot(x, z) > 5.45) return true;
      return false;
    }

    function buildFixedParcels() {
      const cuts = [-5.2, -3.2, 0, 3.2, 5.2];
      const margin = Math.max(ROAD_HALF.main, ROAD_HALF.secondary) + SIDEWALK;
      const parcels = [];
      let id = 0;
      for (let bi = 0; bi < cuts.length - 1; bi++) {
        for (let bj = 0; bj < cuts.length - 1; bj++) {
          const x0 = cuts[bi] + margin;
          const x1 = cuts[bi + 1] - margin;
          const z0 = cuts[bj] + margin;
          const z1 = cuts[bj + 1] - margin;
          const bw = x1 - x0;
          const bd = z1 - z0;
          if (bw < MIN_LOT || bd < MIN_LOT) continue;
          const midX = (x0 + x1) / 2;
          const midZ = (z0 + z1) / 2;
          if (Math.abs(midX) < 1.1 && Math.abs(midZ) < 1.1) {
            parcels.push({
              id: id++, cx: midX, cz: midZ,
              hx: bw * 0.35, hz: bd * 0.35,
              use: 'park', block: { bi, bj },
            });
            continue;
          }
          let cols = bw >= 1.6 ? 2 : 1;
          let rows = bd >= 1.6 ? 2 : 1;
          if (bw / cols < MIN_LOT) cols = 1;
          if (bd / rows < MIN_LOT) rows = 1;
          const cellW = bw / cols;
          const cellD = bd / rows;
          for (let i = 0; i < cols; i++) {
            for (let j = 0; j < rows; j++) {
              const cx = x0 + (i + 0.5) * cellW;
              const cz = z0 + (j + 0.5) * cellD;
              const hx = cellW * 0.5 - LOT_PAD;
              const hz = cellD * 0.5 - LOT_PAD;
              if (hx < 0.16 || hz < 0.16) continue;
              if (nearRoad(cx, cz, 0.12)) continue;
              const isParkCorner = cols * rows >= 4 && i === 0 && j === 0;
              parcels.push({
                id: id++,
                cx, cz, hx, hz,
                use: isParkCorner ? 'park' : 'building',
                block: { bi, bj },
              });
            }
          }
        }
      }
      return parcels;
    }

    const buildingColors = [
      0xd8c0a8, 0xa8c0d8, 0xb8d0b0, 0xe0c8a0, 0xc0b0d0, 0xc8b8a0,
      0xb0c8d8, 0xd0b8a0, 0xa0b8c8, 0xc8c0b0, 0xb8a890, 0x90a8b8,
    ];

    function createResidential(x, z, w, d, h, color) {
      const g = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(w, h, d),
        new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.08 })
      );
      body.position.y = h / 2;
      body.castShadow = true;
      body.receiveShadow = true;
      g.add(body);
      const roofH = h * 0.2;
      const roof = new THREE.Mesh(
        new THREE.ConeGeometry(Math.max(w, d) * 0.72, roofH, 4),
        new THREE.MeshStandardMaterial({ color: new THREE.Color(color).multiplyScalar(0.55), roughness: 0.75 })
      );
      roof.position.y = h + roofH * 0.45;
      roof.rotation.y = Math.PI / 4;
      roof.castShadow = true;
      g.add(roof);
      const winMat = new THREE.MeshBasicMaterial({ color: 0xffe8a0, transparent: true, opacity: 0.55 + Math.random() * 0.35 });
      const floors = Math.max(1, Math.floor(h / 0.28));
      for (let f = 0; f < floors; f++) {
        if (Math.random() > 0.35) {
          const win = new THREE.Mesh(new THREE.BoxGeometry(w * 0.55, 0.045, 0.015), winMat);
          win.position.set(0, 0.18 + f * 0.28, d / 2 + 0.01);
          g.add(win);
        }
      }
      g.position.set(x, 0, z);
      return g;
    }

    function createOffice(x, z, w, d, h, color) {
      const g = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(w, h, d),
        new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.35 })
      );
      body.position.y = h / 2;
      body.castShadow = true;
      body.receiveShadow = true;
      g.add(body);
      const ledge = new THREE.Mesh(
        new THREE.BoxGeometry(w * 1.08, 0.035, d * 1.08),
        new THREE.MeshStandardMaterial({ color: 0x334455, metalness: 0.4, roughness: 0.4 })
      );
      ledge.position.y = h + 0.02;
      g.add(ledge);
      const glassMat = new THREE.MeshStandardMaterial({
        color: 0x88aacc, emissive: 0x446688, emissiveIntensity: 0.22,
        metalness: 0.55, roughness: 0.2, transparent: true, opacity: 0.85,
      });
      const floors = Math.max(2, Math.floor(h / 0.24));
      for (let f = 0; f < floors; f++) {
        const strip = new THREE.Mesh(new THREE.BoxGeometry(w * 0.88, 0.05, 0.02), glassMat);
        strip.position.set(0, 0.14 + f * 0.24, d / 2 + 0.01);
        g.add(strip);
      }
      g.position.set(x, 0, z);
      return g;
    }

    function createTower(x, z, w, d, h, color) {
      const g = new THREE.Group();
      const base = new THREE.Mesh(
        new THREE.BoxGeometry(w * 1.12, h * 0.22, d * 1.12),
        new THREE.MeshStandardMaterial({ color: new THREE.Color(color).multiplyScalar(0.85), roughness: 0.5, metalness: 0.2 })
      );
      base.position.y = h * 0.11;
      base.castShadow = true;
      g.add(base);
      const mid = new THREE.Mesh(
        new THREE.BoxGeometry(w, h * 0.55, d),
        new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.25 })
      );
      mid.position.y = h * 0.22 + h * 0.275;
      mid.castShadow = true;
      g.add(mid);
      const top = new THREE.Mesh(
        new THREE.BoxGeometry(w * 0.7, h * 0.23, d * 0.7),
        new THREE.MeshStandardMaterial({ color: new THREE.Color(color).multiplyScalar(1.08), roughness: 0.35, metalness: 0.3 })
      );
      top.position.y = h * 0.77 + h * 0.115;
      top.castShadow = true;
      g.add(top);
      const crown = new THREE.Mesh(
        new THREE.BoxGeometry(w * 0.45, 0.04, d * 0.45),
        new THREE.MeshBasicMaterial({ color: 0xffe8a0 })
      );
      crown.position.y = h + 0.02;
      g.add(crown);
      g.position.set(x, 0, z);
      return g;
    }

    function createShop(x, z, w, d, h, color) {
      const g = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(w, h, d),
        new THREE.MeshStandardMaterial({ color, roughness: 0.65, metalness: 0.05 })
      );
      body.position.y = h / 2;
      body.castShadow = true;
      body.receiveShadow = true;
      g.add(body);
      const awning = new THREE.Mesh(
        new THREE.BoxGeometry(w * 1.05, 0.03, 0.1),
        new THREE.MeshStandardMaterial({
          color: [0xc04040, 0x4080c0, 0x40a060, 0xc08030][Math.floor(Math.random() * 4)],
          roughness: 0.6,
        })
      );
      awning.position.set(0, h * 0.55, d / 2 + 0.04);
      g.add(awning);
      const store = new THREE.Mesh(
        new THREE.BoxGeometry(w * 0.7, h * 0.32, 0.02),
        new THREE.MeshBasicMaterial({ color: 0xfff0c8, transparent: true, opacity: 0.7 })
      );
      store.position.set(0, h * 0.26, d / 2 + 0.01);
      g.add(store);
      g.position.set(x, 0, z);
      return g;
    }

    function makeProceduralBuildingForParcel(parcel) {
      const { cx, cz, hx, hz } = parcel;
      const w = Math.min(Math.max(hx * 1.7, 0.35), 0.95);
      const d = Math.min(Math.max(hz * 1.7, 0.35), 0.95);
      const color = buildingColors[(parcel.id * 7) % buildingColors.length];
      const roll = ((parcel.id * 17) % 100) / 100;
      let b;
      if (roll < 0.30) {
        b = createResidential(cx, cz, w * 0.92, d * 0.92, 0.45 + (parcel.id % 5) * 0.1, color);
      } else if (roll < 0.55) {
        b = createOffice(cx, cz, w, d, 0.7 + (parcel.id % 6) * 0.14, color);
      } else if (roll < 0.75) {
        const tw = Math.min(w, d) * 0.8;
        b = createTower(cx, cz, tw, tw, 1.15 + (parcel.id % 7) * 0.16, color);
      } else {
        b = createShop(cx, cz, w * 1.05, d * 0.9, 0.35 + (parcel.id % 4) * 0.06, color);
      }
      b.rotation.y = 0;
      return b;
    }

    // Trees
    const treesGroup = new THREE.Group();
    scene.add(treesGroup);

    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a3a22, roughness: 0.85, metalness: 0.05 });
    const leafMats = [
      new THREE.MeshStandardMaterial({ color: 0x2d6b3a, roughness: 0.75, metalness: 0.05 }),
      new THREE.MeshStandardMaterial({ color: 0x3a8a4a, roughness: 0.7, metalness: 0.05 }),
      new THREE.MeshStandardMaterial({ color: 0x1f5a30, roughness: 0.8, metalness: 0.05 }),
      new THREE.MeshStandardMaterial({ color: 0x4a9a55, roughness: 0.72, metalness: 0.05 }),
    ];

    function createTree(x, z, scale = 1) {
      const g = new THREE.Group();
      const trunkH = 0.18 * scale;
      const trunk = new THREE.Mesh(
        new THREE.CylinderGeometry(0.018 * scale, 0.028 * scale, trunkH, 6),
        trunkMat
      );
      trunk.position.y = trunkH / 2;
      trunk.castShadow = true;
      g.add(trunk);
      const leafMat = leafMats[Math.floor(Math.abs(x * 10 + z * 7)) % leafMats.length];
      const style = Math.floor(Math.abs(x * 3 + z * 5)) % 3;
      if (style === 0) {
        for (let i = 0; i < 3; i++) {
          const r = (0.11 - i * 0.025) * scale;
          const h = 0.16 * scale;
          const cone = new THREE.Mesh(new THREE.ConeGeometry(r, h, 7), leafMat);
          cone.position.y = trunkH + 0.06 * scale + i * 0.1 * scale;
          cone.castShadow = true;
          g.add(cone);
        }
      } else if (style === 1) {
        const canopy = new THREE.Mesh(
          new THREE.SphereGeometry(0.12 * scale, 8, 6),
          leafMat
        );
        canopy.position.y = trunkH + 0.1 * scale;
        canopy.scale.y = 0.85;
        canopy.castShadow = true;
        g.add(canopy);
      } else {
        const c1 = new THREE.Mesh(new THREE.SphereGeometry(0.1 * scale, 8, 6), leafMat);
        c1.position.set(0, trunkH + 0.1 * scale, 0);
        c1.castShadow = true;
        g.add(c1);
        const c2 = new THREE.Mesh(new THREE.SphereGeometry(0.08 * scale, 7, 5), leafMat);
        c2.position.set(0.04 * scale, trunkH + 0.14 * scale, -0.02 * scale);
        c2.castShadow = true;
        g.add(c2);
      }
      g.position.set(x, 0, z);
      return g;
    }

    function plantPark(parcel) {
      const { cx, cz, hx, hz } = parcel;
      const pts = [
        [cx, cz],
        [cx - hx * 0.45, cz - hz * 0.45],
        [cx + hx * 0.45, cz - hz * 0.45],
        [cx - hx * 0.45, cz + hz * 0.45],
        [cx + hx * 0.45, cz + hz * 0.45],
      ];
      const count = Math.min(pts.length, hx < 0.28 ? 1 : hz < 0.28 ? 2 : 5);
      for (let i = 0; i < count; i++) {
        const [tx, tz] = pts[i];
        if (nearRoad(tx, tz, 0.08)) continue;
        const sc = 0.75 + ((parcel.id + i) % 4) * 0.12;
        treesGroup.add(createTree(tx, tz, sc));
      }
    }

    function plantStreetTrees() {
      const offsets = [
        { axis: 'z', road: 0, side: ROAD_HALF.main + 0.14, along: 'x' },
        { axis: 'z', road: 0, side: -(ROAD_HALF.main + 0.14), along: 'x' },
        { axis: 'x', road: 0, side: ROAD_HALF.main + 0.14, along: 'z' },
        { axis: 'x', road: 0, side: -(ROAD_HALF.main + 0.14), along: 'z' },
        { axis: 'z', road: 3.2, side: ROAD_HALF.secondary + 0.12, along: 'x' },
        { axis: 'z', road: 3.2, side: -(ROAD_HALF.secondary + 0.12), along: 'x' },
        { axis: 'z', road: -3.2, side: ROAD_HALF.secondary + 0.12, along: 'x' },
        { axis: 'z', road: -3.2, side: -(ROAD_HALF.secondary + 0.12), along: 'x' },
        { axis: 'x', road: 3.2, side: ROAD_HALF.secondary + 0.12, along: 'z' },
        { axis: 'x', road: 3.2, side: -(ROAD_HALF.secondary + 0.12), along: 'z' },
        { axis: 'x', road: -3.2, side: ROAD_HALF.secondary + 0.12, along: 'z' },
        { axis: 'x', road: -3.2, side: -(ROAD_HALF.secondary + 0.12), along: 'z' },
      ];
      const step = 1.35;
      for (const o of offsets) {
        for (let t = -4.6; t <= 4.6; t += step) {
          let x, z;
          if (o.along === 'x') { x = t; z = o.road + o.side; }
          else { z = t; x = o.road + o.side; }
          if (Math.abs(x) < 0.7 || Math.abs(z) < 0.7) continue;
          if (Math.abs(Math.abs(x) - 3.2) < 0.65) continue;
          if (Math.abs(Math.abs(z) - 3.2) < 0.65) continue;
          if (Math.hypot(x, z) > 5.15) continue;
          treesGroup.add(createTree(x, z, 0.65 + (Math.abs(x + z) % 0.25)));
        }
      }
    }

    // Traffic furniture
    const trafficGroup = new THREE.Group();
    scene.add(trafficGroup);

    function createTrafficLight(x, z) {
      const g = new THREE.Group();
      const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.025, 0.03, 0.55, 6),
        new THREE.MeshStandardMaterial({ color: 0x3a3a42, metalness: 0.5, roughness: 0.4 })
      );
      pole.position.y = 0.275;
      pole.castShadow = true;
      g.add(pole);
      const housing = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.2, 0.06),
        new THREE.MeshStandardMaterial({ color: 0x1a1a20, roughness: 0.5, metalness: 0.3 })
      );
      housing.position.y = 0.52;
      g.add(housing);
      const colors = [0xff2222, 0xffcc00, 0x22cc44];
      colors.forEach((c, i) => {
        const lamp = new THREE.Mesh(
          new THREE.SphereGeometry(0.022, 8, 8),
          new THREE.MeshStandardMaterial({
            color: c,
            emissive: c,
            emissiveIntensity: i === 2 ? 0.85 : 0.25,
          })
        );
        lamp.position.set(0, 0.58 - i * 0.055, 0.04);
        g.add(lamp);
      });
      const sign = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.05, 0.012),
        new THREE.MeshStandardMaterial({
          color: 0x1a4a8a,
          emissive: 0x0a2a50,
          emissiveIntensity: 0.35,
          metalness: 0.2,
          roughness: 0.45,
        })
      );
      sign.position.set(0.12, 0.4, 0);
      g.add(sign);
      g.position.set(x, 0, z);
      return g;
    }

    function createStopSign(x, z, rotY = 0) {
      const g = new THREE.Group();
      const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.018, 0.35, 5),
        new THREE.MeshStandardMaterial({ color: 0x888890, metalness: 0.4, roughness: 0.45 })
      );
      pole.position.y = 0.175;
      g.add(pole);
      const board = new THREE.Mesh(
        new THREE.CylinderGeometry(0.07, 0.07, 0.02, 8),
        new THREE.MeshStandardMaterial({
          color: 0xc02828,
          emissive: 0x501010,
          emissiveIntensity: 0.3,
          metalness: 0.15,
          roughness: 0.5,
        })
      );
      board.rotation.x = Math.PI / 2;
      board.position.y = 0.38;
      g.add(board);
      g.position.set(x, 0, z);
      g.rotation.y = rotY;
      return g;
    }

    function placeTrafficFurniture() {
      const junctions = [
        [0,0], [0,3.2], [0,-3.2], [3.2,0], [-3.2,0],
        [3.2,3.2], [3.2,-3.2], [-3.2,3.2], [-3.2,-3.2],
      ];
      const cornerOff = 0.42;
      for (const [jx, jz] of junctions) {
        trafficGroup.add(createTrafficLight(jx + cornerOff, jz + cornerOff));
        if (Math.abs(jx) > 0.1 || Math.abs(jz) > 0.1) {
          trafficGroup.add(createStopSign(jx - cornerOff, jz - cornerOff, Math.PI / 4));
        }
      }
    }

    function placeCityFromParcels() {
      const parcels = buildFixedParcels();
      for (const p of parcels) {
        if (p.use === 'building') {
          buildings.add(makeProceduralBuildingForParcel(p));
        } else {
          plantPark(p);
        }
      }
      plantStreetTrees();
      placeTrafficFurniture();
    }
    placeCityFromParcels();

    // Cars
    const carsGroup = new THREE.Group();
    const carColors = [0xe05040, 0x4080d0, 0xf0e0a0, 0x50a060, 0xc0c0c8, 0x303040, 0xe08030];

    function createCar(color) {
      const g = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.07, 0.12),
        new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.4 })
      );
      body.position.y = 0.06;
      body.castShadow = true;
      g.add(body);
      const cabin = new THREE.Mesh(
        new THREE.BoxGeometry(0.12, 0.06, 0.11),
        new THREE.MeshStandardMaterial({ color: 0x223344, roughness: 0.3, metalness: 0.5 })
      );
      cabin.position.set(-0.02, 0.12, 0);
      g.add(cabin);
      const hl = new THREE.Mesh(
        new THREE.BoxGeometry(0.02, 0.02, 0.08),
        new THREE.MeshBasicMaterial({ color: 0xffffcc })
      );
      hl.position.set(0.11, 0.06, 0);
      g.add(hl);
      return g;
    }

    const carPaths = [
      { a: [-5.0, 0.12], b: [5.0, 0.12], speed: 1.0 },
      { a: [5.0, -0.12], b: [-5.0, -0.12], speed: 0.9 },
      { a: [0.12, -5.0], b: [0.12, 5.0], speed: 0.85 },
      { a: [-0.12, 5.0], b: [-0.12, -5.0], speed: 1.1 },
      { a: [-3.9, -3.35], b: [3.9, -3.35], speed: 0.7 },
      { a: [3.9, 3.35], b: [-3.9, 3.35], speed: 0.75 },
      { a: [-3.35, 3.9], b: [-3.35, -3.9], speed: 0.8 },
      { a: [3.35, -3.9], b: [3.35, 3.9], speed: 0.65 },
    ];

    const cars = [];
    for (let i = 0; i < 14; i++) {
      const path = carPaths[i % carPaths.length];
      const car = createCar(carColors[i % carColors.length]);
      const offset = Math.random();
      cars.push({ mesh: car, path, offset, lane: i });
      carsGroup.add(car);
    }
    scene.add(carsGroup);

    // Pedestrians
    const pedestriansGroup = new THREE.Group();
    function createPedestrian(hue) {
      const g = new THREE.Group();
      const bodyColor = new THREE.Color().setHSL(hue, 0.4, 0.45);
      const torso = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.07, 0.03),
        new THREE.MeshStandardMaterial({ color: bodyColor, roughness: 0.7 })
      );
      torso.position.y = 0.1;
      g.add(torso);
      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.022, 6, 6),
        new THREE.MeshStandardMaterial({ color: 0xe0c0a0, roughness: 0.6 })
      );
      head.position.y = 0.155;
      g.add(head);
      const legs = new THREE.Mesh(
        new THREE.BoxGeometry(0.035, 0.05, 0.025),
        new THREE.MeshStandardMaterial({ color: 0x2a3040, roughness: 0.8 })
      );
      legs.position.y = 0.04;
      g.add(legs);
      return g;
    }

    const pedPaths = [
      { a: [-4.5, 0.45], b: [4.5, 0.45] },
      { a: [4.5, -0.45], b: [-4.5, -0.45] },
      { a: [0.45, -4.5], b: [0.45, 4.5] },
      { a: [-0.45, 4.5], b: [-0.45, -4.5] },
      { a: [-3.0, 3.55], b: [3.0, 3.55] },
      { a: [3.0, -3.55], b: [-3.0, -3.55] },
    ];
    const pedestrians = [];
    for (let i = 0; i < 18; i++) {
      const path = pedPaths[i % pedPaths.length];
      const ped = createPedestrian(Math.random());
      pedestrians.push({ mesh: ped, path, offset: Math.random(), speed: 0.4 + Math.random() * 0.4 });
      pedestriansGroup.add(ped);
    }
    scene.add(pedestriansGroup);

    // Airplane
    const planeGroup = new THREE.Group();
    const planeBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.03, 0.55, 8),
      new THREE.MeshStandardMaterial({ color: 0xe8eef5, metalness: 0.5, roughness: 0.3 })
    );
    planeBody.rotation.z = Math.PI / 2;
    planeGroup.add(planeBody);
    const wing = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.015, 0.55),
      new THREE.MeshStandardMaterial({ color: 0xc8d0dc, metalness: 0.4, roughness: 0.35 })
    );
    planeGroup.add(wing);
    const tail = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.12, 0.02),
      new THREE.MeshStandardMaterial({ color: 0x5bb8f5, metalness: 0.3, roughness: 0.4 })
    );
    tail.position.set(-0.22, 0.06, 0);
    planeGroup.add(tail);
    const navL = new THREE.Mesh(
      new THREE.SphereGeometry(0.02, 6, 6),
      new THREE.MeshBasicMaterial({ color: 0xff2020 })
    );
    navL.position.set(0, 0, 0.28);
    planeGroup.add(navL);
    const navR = new THREE.Mesh(
      new THREE.SphereGeometry(0.02, 6, 6),
      new THREE.MeshBasicMaterial({ color: 0x20ff40 })
    );
    navR.position.set(0, 0, -0.28);
    planeGroup.add(navR);
    planeGroup.position.set(-8, 3.5, -3);
    planeGroup.visible = false;
    scene.add(planeGroup);

    // Celebration
    const celebrateGroup = new THREE.Group();
    celebrateGroup.visible = false;
    scene.add(celebrateGroup);

    const celebratePos = { x: -2.35, y: 0.8 };

    function createCelebrationTower() {
      const g = new THREE.Group();
      const H = 2.35;
      const base = new THREE.Mesh(
        new THREE.BoxGeometry(0.72, H * 0.18, 0.72),
        new THREE.MeshStandardMaterial({
          color: 0xd8c8b0, roughness: 0.45, metalness: 0.15,
          emissive: 0xffd090, emissiveIntensity: 0.12,
        })
      );
      base.position.y = H * 0.09;
      base.castShadow = true;
      base.receiveShadow = true;
      g.add(base);
      const shaft = new THREE.Mesh(
        new THREE.BoxGeometry(0.58, H * 0.62, 0.58),
        new THREE.MeshStandardMaterial({
          color: 0x6a90b8, roughness: 0.25, metalness: 0.45,
          emissive: 0x2a5078, emissiveIntensity: 0.2,
        })
      );
      shaft.position.y = H * 0.18 + H * 0.31;
      shaft.castShadow = true;
      g.add(shaft);
      const glassMat = new THREE.MeshStandardMaterial({
        color: 0xa8d0f0, emissive: 0x5080b0, emissiveIntensity: 0.45,
        metalness: 0.6, roughness: 0.15, transparent: true, opacity: 0.9,
      });
      const floors = 10;
      for (let f = 0; f < floors; f++) {
        const strip = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.04, 0.02), glassMat);
        strip.position.set(0, H * 0.22 + f * 0.12, 0.3);
        g.add(strip);
        const strip2 = strip.clone();
        strip2.position.z = -0.3;
        g.add(strip2);
      }
      const top = new THREE.Mesh(
        new THREE.BoxGeometry(0.48, H * 0.16, 0.48),
        new THREE.MeshStandardMaterial({
          color: 0x8ab0d0, roughness: 0.2, metalness: 0.5,
          emissive: 0x406090, emissiveIntensity: 0.25,
        })
      );
      top.position.y = H * 0.8 + H * 0.08;
      top.castShadow = true;
      g.add(top);
      const crown = new THREE.Mesh(
        new THREE.BoxGeometry(0.3, 0.08, 0.3),
        new THREE.MeshStandardMaterial({
          color: 0xffe8a0, emissive: 0xffc040, emissiveIntensity: 0.9,
          metalness: 0.4, roughness: 0.3,
        })
      );
      crown.position.y = H + 0.04;
      g.add(crown);
      const spire = new THREE.Mesh(
        new THREE.CylinderGeometry(0.02, 0.04, 0.28, 6),
        new THREE.MeshStandardMaterial({
          color: 0xffd070, emissive: 0xffa020, emissiveIntensity: 0.7,
        })
      );
      spire.position.y = H + 0.22;
      g.add(spire);
      const crossMat = new THREE.MeshBasicMaterial({ color: 0x4ade80 });
      const crossV = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.2, 0.03), crossMat);
      crossV.position.set(0, 0.55, 0.37);
      g.add(crossV);
      const crossH = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.05, 0.03), crossMat);
      crossH.position.set(0, 0.55, 0.37);
      g.add(crossH);
      const pad = new THREE.Mesh(
        new THREE.CylinderGeometry(0.55, 0.58, 0.04, 20),
        new THREE.MeshStandardMaterial({
          color: 0x2a3a50, emissive: 0x1a4060, emissiveIntensity: 0.35, roughness: 0.55,
        })
      );
      pad.position.y = 0.02;
      g.add(pad);
      const glowRing = new THREE.Mesh(
        new THREE.RingGeometry(0.45, 0.95, 48),
        new THREE.MeshBasicMaterial({
          color: 0x5bb8f5, transparent: true, opacity: 0.55,
          side: THREE.DoubleSide, depthWrite: false,
        })
      );
      glowRing.rotation.x = -Math.PI / 2;
      glowRing.position.y = 0.04;
      g.add(glowRing);
      g.userData.glowRing = glowRing;
      const glowOuter = new THREE.Mesh(
        new THREE.RingGeometry(0.95, 1.45, 48),
        new THREE.MeshBasicMaterial({
          color: 0xf0b27a, transparent: true, opacity: 0.25,
          side: THREE.DoubleSide, depthWrite: false,
        })
      );
      glowOuter.rotation.x = -Math.PI / 2;
      glowOuter.position.y = 0.035;
      g.add(glowOuter);
      g.userData.glowOuter = glowOuter;
      const pillar = new THREE.Mesh(
        new THREE.CylinderGeometry(0.35, 0.55, H * 1.05, 16, 1, true),
        new THREE.MeshBasicMaterial({
          color: 0x8ec8ff, transparent: true, opacity: 0.12,
          side: THREE.DoubleSide, depthWrite: false,
          blending: THREE.AdditiveBlending,
        })
      );
      pillar.position.y = H * 0.52;
      g.add(pillar);
      g.userData.glowPillar = pillar;
      const pl = new THREE.PointLight(0x7ec8ff, 0.0, 4.5, 2);
      pl.position.set(0, H * 0.6, 0);
      g.add(pl);
      g.userData.pointLight = pl;
      g.userData.fullHeight = H;
      return g;
    }

    let serviceBuilding = createCelebrationTower();
    serviceBuilding.position.set(celebratePos.x, 0, celebratePos.y);
    serviceBuilding.scale.set(0.01, 0.01, 0.01);
    celebrateGroup.add(serviceBuilding);

    const celebrateTrees = [];
    const CELEBRATE_TREE_RADIUS = 0.95;
    function collectCelebrateTrees() {
      celebrateTrees.length = 0;
      treesGroup.children.forEach((t) => {
        const dx = t.position.x - celebratePos.x;
        const dz = t.position.z - celebratePos.y;
        if (Math.hypot(dx, dz) < CELEBRATE_TREE_RADIUS) {
          if (!t.userData.baseScale) t.userData.baseScale = t.scale.x || 1;
          celebrateTrees.push(t);
        }
      });
      if (celebrateTrees.length < 4) {
        const offsets = [
          [0,0], [0.35,0.25], [-0.3,0.35], [0.25,-0.35], [-0.35,-0.25], [0.45,0],
        ];
        for (const [ox, oz] of offsets) {
          if (celebrateTrees.length >= 6) break;
          const tx = celebratePos.x + ox;
          const tz = celebratePos.y + oz;
          const tree = createTree(tx, tz, 0.85 + celebrateTrees.length * 0.08);
          tree.userData.baseScale = tree.scale.x || 1;
          treesGroup.add(tree);
          celebrateTrees.push(tree);
        }
      }
    }
    setTimeout(collectCelebrateTrees, 0);

    // Fireworks
    const FW_COUNT = 120;
    const fwPositions = new Float32Array(FW_COUNT * 3);
    const fwVelocities = [];
    const fwColors = new Float32Array(FW_COUNT * 3);
    const fwLife = new Float32Array(FW_COUNT);
    const fwPalette = [
      [1.0, 0.35, 0.2], [1.0, 0.7, 0.15], [0.3, 0.85, 1.0],
      [0.4, 1.0, 0.5], [1.0, 0.4, 0.8], [0.9, 0.9, 1.0],
    ];
    for (let i = 0; i < FW_COUNT; i++) {
      fwPositions[i * 3] = 0;
      fwPositions[i * 3 + 1] = 0;
      fwPositions[i * 3 + 2] = 0;
      fwVelocities.push(new THREE.Vector3());
      fwLife[i] = 0;
      const c = fwPalette[i % fwPalette.length];
      fwColors[i * 3] = c[0];
      fwColors[i * 3 + 1] = c[1];
      fwColors[i * 3 + 2] = c[2];
    }
    const fwGeo = new THREE.BufferGeometry();
    fwGeo.setAttribute('position', new THREE.BufferAttribute(fwPositions, 3));
    fwGeo.setAttribute('color', new THREE.BufferAttribute(fwColors, 3));
    const fwMat = new THREE.PointsMaterial({
      size: 0.12,
      vertexColors: true,
      transparent: true,
      opacity: 0.95,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    const fireworks = new THREE.Points(fwGeo, fwMat);
    fireworks.visible = false;
    celebrateGroup.add(fireworks);

    let celebrateTriggered = false;
    let celebrateAnimT = 0;
    let fwBurstActive = false;
    let fwBurstTime = 0;

    function triggerFireworksBurst() {
      fwBurstActive = true;
      fwBurstTime = 0;
      fireworks.visible = true;
      const origin = new THREE.Vector3(celebratePos.x, 2.2, celebratePos.y);
      for (let i = 0; i < FW_COUNT; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.random() * Math.PI * 0.55;
        const speed = 1.2 + Math.random() * 2.2;
        fwVelocities[i].set(
          Math.sin(phi) * Math.cos(theta) * speed,
          Math.cos(phi) * speed * 1.15,
          Math.sin(phi) * Math.sin(theta) * speed
        );
        fwPositions[i * 3] = origin.x;
        fwPositions[i * 3 + 1] = origin.y;
        fwPositions[i * 3 + 2] = origin.z;
        fwLife[i] = 0.7 + Math.random() * 0.5;
        const c = fwPalette[Math.floor(Math.random() * fwPalette.length)];
        fwColors[i * 3] = c[0];
        fwColors[i * 3 + 1] = c[1];
        fwColors[i * 3 + 2] = c[2];
      }
      fwGeo.attributes.position.needsUpdate = true;
      fwGeo.attributes.color.needsUpdate = true;
    }

    function updateFireworks(dt) {
      if (!fwBurstActive) return;
      fwBurstTime += dt;
      const pos = fwGeo.attributes.position.array;
      let alive = 0;
      for (let i = 0; i < FW_COUNT; i++) {
        if (fwLife[i] <= 0) continue;
        fwLife[i] -= dt * 0.55;
        fwVelocities[i].y -= 2.8 * dt;
        fwVelocities[i].multiplyScalar(0.985);
        pos[i * 3] += fwVelocities[i].x * dt;
        pos[i * 3 + 1] += fwVelocities[i].y * dt;
        pos[i * 3 + 2] += fwVelocities[i].z * dt;
        if (fwLife[i] > 0) alive++;
      }
      fwGeo.attributes.position.needsUpdate = true;
      fwMat.opacity = Math.max(0, 1 - fwBurstTime * 0.45);
      fwMat.size = 0.12 + Math.sin(fwBurstTime * 8) * 0.03;
      if (alive === 0 || fwBurstTime > 3.5) {
        fwBurstActive = false;
        fireworks.visible = false;
      }
    }

    // Demand points
    const demandGroup = new THREE.Group();
    const demandMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.25,
      metalness: 0.2,
      emissive: 0xff4400,
      emissiveIntensity: 0.45,
      vertexColors: true,
    });
    const demandGeo = new THREE.SphereGeometry(0.06, 12, 12);
    const demandMesh = new THREE.InstancedMesh(demandGeo, demandMat, demandData.length);
    demandMesh.castShadow = true;
    demandMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    const demandHaloMat = new THREE.MeshBasicMaterial({
      color: 0xff6622,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const demandHaloGeo = new THREE.RingGeometry(0.08, 0.16, 24);
    const demandHaloMesh = new THREE.InstancedMesh(demandHaloGeo, demandHaloMat, demandData.length);
    demandHaloMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    const dummy = new THREE.Object3D();
    const haloDummy = new THREE.Object3D();
    const demandColors = new Float32Array(demandData.length * 3);
    for (let i = 0; i < demandData.length; i++) {
      const p = demandData[i];
      const s = 0.9 + p.w * 0.55;
      dummy.position.set(p.x, 0.1, p.y);
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      demandMesh.setMatrixAt(i, dummy.matrix);
      haloDummy.position.set(p.x, 0.02, p.y);
      haloDummy.rotation.x = -Math.PI / 2;
      const hs = 0.9 + p.w * 0.7;
      haloDummy.scale.set(hs, hs, hs);
      haloDummy.updateMatrix();
      demandHaloMesh.setMatrixAt(i, haloDummy.matrix);
      const intensity = 0.4 + p.w * 0.6;
      demandColors[i * 3] = 1.0 * intensity;
      demandColors[i * 3 + 1] = 0.42 * intensity;
      demandColors[i * 3 + 2] = 0.1 * intensity;
    }
    demandMesh.instanceMatrix.needsUpdate = true;
    demandHaloMesh.instanceMatrix.needsUpdate = true;
    demandMesh.geometry.setAttribute('instanceColor', new THREE.InstancedBufferAttribute(demandColors, 3));
    demandGroup.add(demandMesh);
    demandGroup.add(demandHaloMesh);
    scene.add(demandGroup);
    demandGroup.visible = false;

    // Candidate sites
    const candidateGroup = new THREE.Group();
    const siteMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.28,
      metalness: 0.3,
      emissive: 0x2a6aaa,
      emissiveIntensity: 0.35,
      vertexColors: true,
    });
    const siteGeo = new THREE.CylinderGeometry(0.055, 0.08, 0.32, 8);
    const siteMesh = new THREE.InstancedMesh(siteGeo, siteMat, candidateData.length);
    siteMesh.castShadow = true;
    siteMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    const beaconMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.2,
      metalness: 0.4,
      emissive: 0x5bb8f5,
      emissiveIntensity: 0.85,
      vertexColors: true,
    });
    const beaconGeo = new THREE.SphereGeometry(0.045, 10, 10);
    const beaconMesh = new THREE.InstancedMesh(beaconGeo, beaconMat, candidateData.length);
    beaconMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    const siteRingMat = new THREE.MeshBasicMaterial({
      color: 0x5bb8f5,
      transparent: true,
      opacity: 0.3,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const siteRingGeo = new THREE.RingGeometry(0.1, 0.16, 28);
    const siteRingMesh = new THREE.InstancedMesh(siteRingGeo, siteRingMat, candidateData.length);
    siteRingMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    const siteDummy = new THREE.Object3D();
    const beaconDummy = new THREE.Object3D();
    const ringDummy = new THREE.Object3D();
    const siteColorsInit = new Float32Array(candidateData.length * 3);
    for (let i = 0; i < candidateData.length; i++) {
      const p = candidateData[i];
      siteDummy.position.set(p.x, 0.16, p.y);
      siteDummy.scale.set(1, 1, 1);
      siteDummy.updateMatrix();
      siteMesh.setMatrixAt(i, siteDummy.matrix);
      beaconDummy.position.set(p.x, 0.36, p.y);
      beaconDummy.scale.set(1, 1, 1);
      beaconDummy.updateMatrix();
      beaconMesh.setMatrixAt(i, beaconDummy.matrix);
      ringDummy.position.set(p.x, 0.025, p.y);
      ringDummy.rotation.x = -Math.PI / 2;
      ringDummy.scale.set(1, 1, 1);
      ringDummy.updateMatrix();
      siteRingMesh.setMatrixAt(i, ringDummy.matrix);
      siteColorsInit[i * 3] = 0.35;
      siteColorsInit[i * 3 + 1] = 0.7;
      siteColorsInit[i * 3 + 2] = 0.98;
    }
    siteMesh.instanceMatrix.needsUpdate = true;
    beaconMesh.instanceMatrix.needsUpdate = true;
    siteRingMesh.instanceMatrix.needsUpdate = true;
    siteMesh.geometry.setAttribute('instanceColor', new THREE.InstancedBufferAttribute(siteColorsInit, 3));
    beaconMesh.geometry.setAttribute('instanceColor', new THREE.InstancedBufferAttribute(siteColorsInit.slice(), 3));
    candidateGroup.add(siteMesh);
    candidateGroup.add(beaconMesh);
    candidateGroup.add(siteRingMesh);
    scene.add(candidateGroup);
    candidateGroup.visible = false;

    // Coverage circles
    const circleGroup = new THREE.Group();
    const circleMat = new THREE.MeshBasicMaterial({
      color: 0x5bb8f5,
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const circleGeo = new THREE.RingGeometry(0.92, 1.0, 48);
    const circleInstanced = new THREE.InstancedMesh(circleGeo, circleMat, candidateData.length);
    circleInstanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    const circleDummy = new THREE.Object3D();
    for (let i = 0; i < candidateData.length; i++) {
      const p = candidateData[i];
      circleDummy.position.set(p.x, 0.03, p.y);
      circleDummy.rotation.x = -Math.PI / 2;
      circleDummy.scale.set(0.01, 0.01, 0.01);
      circleDummy.updateMatrix();
      circleInstanced.setMatrixAt(i, circleDummy.matrix);
    }
    circleInstanced.instanceMatrix.needsUpdate = true;
    circleGroup.add(circleInstanced);
    scene.add(circleGroup);
    circleGroup.visible = false;

    const diskMat = new THREE.MeshBasicMaterial({
      color: 0x5bb8f5,
      transparent: true,
      opacity: 0.06,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const diskGeo = new THREE.CircleGeometry(1, 32);
    const diskInstanced = new THREE.InstancedMesh(diskGeo, diskMat, candidateData.length);
    diskInstanced.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    for (let i = 0; i < candidateData.length; i++) {
      const p = candidateData[i];
      circleDummy.position.set(p.x, 0.025, p.y);
      circleDummy.rotation.x = -Math.PI / 2;
      circleDummy.scale.set(0.01, 0.01, 0.01);
      circleDummy.updateMatrix();
      diskInstanced.setMatrixAt(i, circleDummy.matrix);
    }
    diskInstanced.instanceMatrix.needsUpdate = true;
    circleGroup.add(diskInstanced);

    // ================================================================
    // SCROLLTRIGGER for 3D section
    // ================================================================
    const progress = { value: 0 };
    const sectionLabels = [
      'Tổng quan', 'Bối cảnh', 'Demand', 'Ứng viên',
      'Bán kính R', 'Max Coverage', 'Min Cost', 'Pareto', 'Nghiệm chọn'
    ];
    const SECTION_COUNT = sections.length;

    const cameraTimeline = gsap.timeline({
      scrollTrigger: {
        trigger: textCol,
        start: 'top top',
        end: 'bottom bottom',
        scrub: 0.85,
        invalidateOnRefresh: true,
        snap: {
          snapTo: (value) => {
            const step = 1 / Math.max(1, SECTION_COUNT - 1);
            return Math.round(value / step) * step;
          },
          duration: { min: 0.12, max: 0.35 },
          delay: 0.02,
          ease: 'power1.inOut',
        },
        onUpdate: (self) => {
          progress.value = self.progress;
          updateScene(progress.value);
          progressBar.style.width = (self.progress * 100) + '%';
        },
      },
    });
    cameraTimeline.to(progress, { value: 1, duration: 1, ease: 'none' });

    // Per-section reveal
    sections.forEach((sec, i) => {
      if (!sec.querySelector('.section-inner')) {
        const inner = document.createElement('div');
        inner.className = 'section-inner';
        while (sec.firstChild) inner.appendChild(sec.firstChild);
        sec.appendChild(inner);
      }
      const inner = sec.querySelector('.section-inner');
      const bits = inner.querySelectorAll('.badge, h2, p, .formula, .stat-row');
      gsap.set(bits, { opacity: 0, y: 18 });

      ScrollTrigger.create({
        trigger: sec,
        start: 'top 60%',
        end: 'bottom 40%',
        onEnter: () => activateSection(sec, i, bits),
        onEnterBack: () => activateSection(sec, i, bits),
        onLeave: () => deactivateSection(sec, bits),
        onLeaveBack: () => deactivateSection(sec, bits),
      });
    });

    function activateSection(sec, i, bits) {
      sec.classList.add('active');
      navButtons.forEach((b, j) => b.classList.toggle('active', j === i));
      gsap.to(bits, {
        opacity: 1,
        y: 0,
        duration: 0.45,
        stagger: 0.06,
        ease: 'power2.out',
        overwrite: 'auto',
      });
    }

    function deactivateSection(sec, bits) {
      sec.classList.remove('active');
      gsap.to(bits, {
        opacity: 0,
        y: 12,
        duration: 0.25,
        stagger: 0.03,
        ease: 'power1.in',
        overwrite: 'auto',
      });
    }

    // ================================================================
    // SCENE UPDATE
    // ================================================================
    const matrix4 = new THREE.Matrix4();
    const posVec2 = new THREE.Vector3();
    const scaleVec2 = new THREE.Vector3();
    const quat2 = new THREE.Quaternion();

    function updateScene(p) {
      const totalSections = 9;
      const seg = 1 / totalSections;
      const section = Math.min(Math.floor(p / seg), totalSections - 1);
      const localT = (p - section * seg) / seg;

      demandGroup.visible = section >= 2 && section < 8;
      candidateGroup.visible = section >= 3 && section < 8;
      circleGroup.visible = section >= 4 && section <= 6;

      if (section >= 2) {
        sceneHud.classList.add('visible');
        hudSection.textContent = sectionLabels[section] || 'Scene';
      } else {
        sceneHud.classList.remove('visible');
      }

      const keyframes = [
        { pos: [0, 5.5, 9.0], target: [0, 0.15, 0] },
        { pos: [0, 6.2, 8.0], target: [0, 0.2, 0] },
        { pos: [0.4, 6.8, 6.5], target: [0, 0.1, 0] },
        { pos: [-0.3, 6.0, 6.2], target: [0, 0.1, 0] },
        { pos: [0, 6.5, 7.0], target: [0, 0.1, 0] },
        { pos: [0.25, 5.8, 7.2], target: [0, 0.1, 0] },
        { pos: [-0.15, 5.5, 7.5], target: [0, 0.1, 0] },
        { pos: [-1.5, 5.4, 6.5], target: [-2.0, 0.5, 0.7] },
        { pos: [-1.8, 4.6, 5.8], target: [-2.35, 1.0, 0.8] },
      ];
      const idx = Math.min(Math.floor(p * (keyframes.length - 1)), keyframes.length - 2);
      const t = (p * (keyframes.length - 1)) % 1;
      const a = keyframes[idx];
      const b = keyframes[idx + 1] || a;
      const easeT = t * t * (3 - 2 * t);
      camera.position.set(
        a.pos[0] + (b.pos[0] - a.pos[0]) * easeT,
        a.pos[1] + (b.pos[1] - a.pos[1]) * easeT,
        a.pos[2] + (b.pos[2] - a.pos[2]) * easeT
      );
      camera.lookAt(
        a.target[0] + (b.target[0] - a.target[0]) * easeT,
        a.target[1] + (b.target[1] - a.target[1]) * easeT,
        a.target[2] + (b.target[2] - a.target[2]) * easeT
      );

      if (section === 4) {
        const radius = 0.15 + localT * 1.85;
        hudRadius.textContent = radius.toFixed(2);
        for (let i = 0; i < candidateData.length; i++) {
          const pnt = candidateData[i];
          circleDummy.position.set(pnt.x, 0.03, pnt.y);
          circleDummy.rotation.x = -Math.PI / 2;
          circleDummy.scale.set(radius, radius, radius);
          circleDummy.updateMatrix();
          circleInstanced.setMatrixAt(i, circleDummy.matrix);
          circleDummy.position.set(pnt.x, 0.025, pnt.y);
          circleDummy.scale.set(radius, radius, radius);
          circleDummy.updateMatrix();
          diskInstanced.setMatrixAt(i, circleDummy.matrix);
        }
        circleInstanced.instanceMatrix.needsUpdate = true;
        diskInstanced.instanceMatrix.needsUpdate = true;
        circleMat.opacity = 0.12 + localT * 0.14;
        diskMat.opacity = 0.04 + localT * 0.05;

        const colors = demandMesh.geometry.attributes.instanceColor;
        if (colors) {
          for (let i = 0; i < demandData.length; i++) {
            const dp = demandData[i];
            let minDist = Infinity;
            for (const site of candidateData) {
              const dx = dp.x - site.x;
              const dy = dp.y - site.y;
              const dist = Math.sqrt(dx * dx + dy * dy);
              if (dist < minDist) minDist = dist;
            }
            const covered = minDist < radius;
            if (covered) {
              colors.setXYZ(i, 0.25, 0.85, 0.45);
            } else {
              const intensity = 0.35 + dp.w * 0.65;
              colors.setXYZ(i, 1.0 * intensity, 0.45 * intensity, 0.12 * intensity);
            }
          }
          colors.needsUpdate = true;
        }
      } else {
        hudRadius.textContent = '—';
      }

      if (section === 5) {
        const covered = Math.floor(localT * demandData.length);
        document.getElementById('coveredCounter').textContent = covered;
      }

      if (section === 6) {
        const finalSolution = paretoData[selectedSolutionIndex];
        const finalFacilityCount = finalSolution ? finalSolution.facilityAssignment.length : 8;
        const startFacilities = candidateData.length;
        const currentFacilities = Math.round(startFacilities - (startFacilities - finalFacilityCount) * localT);
        document.getElementById('facilityCounter').textContent = currentFacilities;

        const siteColors = siteMesh.geometry.attributes.instanceColor;
        const beaconColors = beaconMesh.geometry.attributes.instanceColor;
        if (siteColors) {
          for (let i = 0; i < candidateData.length; i++) {
            const active = i < currentFacilities;
            if (active) {
              siteColors.setXYZ(i, 0.35, 0.7, 0.98);
              if (beaconColors) beaconColors.setXYZ(i, 0.4, 0.75, 1.0);
            } else {
              siteColors.setXYZ(i, 0.1, 0.1, 0.12);
              if (beaconColors) beaconColors.setXYZ(i, 0.08, 0.08, 0.1);
            }
          }
          siteColors.needsUpdate = true;
          if (beaconColors) beaconColors.needsUpdate = true;
        }
      }

      if (section === 8 || section === 7) {
        const sol = paretoData[selectedSolutionIndex];
        if (sol) {
          if (section === 8) {
            document.getElementById('finalCoverage').textContent = Math.round(sol.coverage * 100);
            document.getElementById('finalFacilities').textContent = sol.facilityAssignment.length;
          }
          const siteColors = siteMesh.geometry.attributes.instanceColor;
          const beaconColors = beaconMesh.geometry.attributes.instanceColor;
          if (siteColors) {
            const selectedSet = new Set(sol.facilityAssignment);
            for (let i = 0; i < candidateData.length; i++) {
              if (selectedSet.has(i)) {
                siteColors.setXYZ(i, 1.0, 0.62, 0.22);
                if (beaconColors) beaconColors.setXYZ(i, 1.0, 0.7, 0.25);
              } else {
                siteColors.setXYZ(i, 0.1, 0.1, 0.12);
                if (beaconColors) beaconColors.setXYZ(i, 0.08, 0.08, 0.1);
              }
            }
            siteColors.needsUpdate = true;
            if (beaconColors) beaconColors.needsUpdate = true;
          }
        }
      }

      // Celebration
      if (section === 8) {
        celebrateGroup.visible = true;
        if (celebrateTrees.length === 0) collectCelebrateTrees();

        const treeT = Math.min(1, localT / 0.35);
        const easeTree = treeT * treeT;
        celebrateTrees.forEach((t) => {
          const s = Math.max(0.001, (1 - easeTree) * (t.userData.baseScale || 1));
          t.scale.setScalar(s);
          t.position.y = -easeTree * 0.35;
          t.visible = s > 0.02;
        });

        const growT = Math.min(1, Math.max(0, (localT - 0.2) / 0.55));
        const easeGrow = 1 - Math.pow(1 - growT, 3);
        serviceBuilding.scale.setScalar(0.01 + easeGrow * 0.99);
        serviceBuilding.rotation.y = 0;
        const pulse = 0.5 + 0.5 * Math.sin(time * 3.2);
        if (serviceBuilding.userData.glowRing) {
          serviceBuilding.userData.glowRing.material.opacity = 0.25 + easeGrow * (0.45 + pulse * 0.2);
          serviceBuilding.userData.glowRing.scale.setScalar(0.85 + easeGrow * 0.35 + pulse * 0.08);
        }
        if (serviceBuilding.userData.glowOuter) {
          serviceBuilding.userData.glowOuter.material.opacity = 0.08 + easeGrow * (0.28 + pulse * 0.12);
          serviceBuilding.userData.glowOuter.scale.setScalar(0.9 + easeGrow * 0.25 + pulse * 0.1);
        }
        if (serviceBuilding.userData.glowPillar) {
          serviceBuilding.userData.glowPillar.material.opacity = easeGrow * (0.08 + pulse * 0.06);
        }
        if (serviceBuilding.userData.pointLight) {
          serviceBuilding.userData.pointLight.intensity = easeGrow * (1.2 + pulse * 0.6);
        }
        serviceBuilding.traverse((ch) => {
          if (ch.isMesh && ch.material && ch.material.emissiveIntensity !== undefined) {
            ch.material.emissiveIntensity = Math.max(ch.material.emissiveIntensity, 0.15 + easeGrow * 0.55);
          }
        });

        if (!celebrateTriggered && localT > 0.55) {
          celebrateTriggered = true;
          triggerFireworksBurst();
          celebrateAnimT = 0;
        }
        if (celebrateTriggered) {
          celebrateAnimT += 0.016;
          if (celebrateAnimT > 0.85 && celebrateAnimT < 0.95 && !fwBurstActive) {
            triggerFireworksBurst();
          }
          if (celebrateAnimT > 1.7 && celebrateAnimT < 1.8 && !fwBurstActive) {
            triggerFireworksBurst();
          }
        }
      } else if (section < 8) {
        celebrateTriggered = false;
        celebrateAnimT = 0;
        celebrateGroup.visible = false;
        serviceBuilding.scale.set(0.01, 0.01, 0.01);
        fireworks.visible = false;
        fwBurstActive = false;
        celebrateTrees.forEach((t) => {
          t.scale.setScalar(t.userData.baseScale || 1);
          t.position.y = 0;
          t.visible = true;
        });
      }

      // Cars
      cars.forEach((c) => {
        const tCar = ((p * c.path.speed * 2.2) + c.offset) % 1;
        const x = c.path.a[0] + (c.path.b[0] - c.path.a[0]) * tCar;
        const z = c.path.a[1] + (c.path.b[1] - c.path.a[1]) * tCar;
        c.mesh.position.set(x, 0, z);
        const angle = Math.atan2(c.path.b[1] - c.path.a[1], c.path.b[0] - c.path.a[0]);
        c.mesh.rotation.y = -angle;
      });

      // Pedestrians
      pedestrians.forEach((ped) => {
        const tPed = ((p * ped.speed * 1.5) + ped.offset) % 1;
        const x = ped.path.a[0] + (ped.path.b[0] - ped.path.a[0]) * tPed;
        const z = ped.path.a[1] + (ped.path.b[1] - ped.path.a[1]) * tPed;
        ped.mesh.position.set(x, 0, z);
        const angle = Math.atan2(ped.path.b[1] - ped.path.a[1], ped.path.b[0] - ped.path.a[0]);
        ped.mesh.rotation.y = -angle;
      });

      // Airplane
      planeGroup.visible = true;
      const planeT = (p * 1.15) % 1;
      planeGroup.position.set(
        -7 + planeT * 14,
        3.2 + Math.sin(planeT * Math.PI) * 0.8,
        -4 + planeT * 3.5
      );
      planeGroup.rotation.y = -0.35;
      planeGroup.rotation.z = Math.sin(planeT * Math.PI * 2) * 0.08;

      // Sun
      sunGroup.position.set(
        5.2 + Math.sin(p * Math.PI) * 0.6,
        4.0 + p * 0.5,
        -4.2 - p * 0.4
      );
    }

    // ================================================================
    // RESIZE
    // ================================================================
    function onResize() {
      const w = sceneCol.clientWidth;
      const h = sceneCol.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      ScrollTrigger.refresh();
    }
    window.addEventListener('resize', onResize);

    // ================================================================
    // RENDER LOOP
    // ================================================================
    let time = 0;
    gsap.ticker.add((t, delta) => {
      time += delta * 0.001;
      if (demandGroup.visible) {
        demandMat.emissiveIntensity = 0.35 + Math.sin(time * 2.2) * 0.12;
        demandHaloMat.opacity = 0.16 + Math.sin(time * 2.2) * 0.08;
      }
      if (candidateGroup.visible) {
        beaconMat.emissiveIntensity = 0.7 + Math.sin(time * 1.8) * 0.2;
      }
      if (sunGlow) {
        sunGlow.scale.setScalar(1 + Math.sin(time * 0.8) * 0.06);
        sunHalo.scale.setScalar(1 + Math.sin(time * 0.5) * 0.08);
      }
      updateFireworks(delta * 0.001);
      const idle = 0.0004 * delta;
      const pNow = progress.value;
      cars.forEach((c) => {
        c.offset = (c.offset + idle * c.path.speed) % 1;
        const tCar = ((pNow * c.path.speed * 2.2) + c.offset) % 1;
        const x = c.path.a[0] + (c.path.b[0] - c.path.a[0]) * tCar;
        const z = c.path.a[1] + (c.path.b[1] - c.path.a[1]) * tCar;
        c.mesh.position.set(x, 0, z);
        c.mesh.rotation.y = -Math.atan2(c.path.b[1] - c.path.a[1], c.path.b[0] - c.path.a[0]);
      });
      pedestrians.forEach((ped) => {
        ped.offset = (ped.offset + idle * ped.speed * 0.55) % 1;
        const tPed = ((pNow * ped.speed * 1.5) + ped.offset) % 1;
        const x = ped.path.a[0] + (ped.path.b[0] - ped.path.a[0]) * tPed;
        const z = ped.path.a[1] + (ped.path.b[1] - ped.path.a[1]) * tPed;
        ped.mesh.position.set(x, 0, z);
        ped.mesh.rotation.y = -Math.atan2(ped.path.b[1] - ped.path.a[1], ped.path.b[0] - ped.path.a[0]);
      });
      renderer.render(scene, camera);
    });
    gsap.ticker.lagSmoothing(0);

    // ================================================================
    // REDUCED MOTION
    // ================================================================
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      cameraTimeline.scrollTrigger?.disable();
      camera.position.set(0, 5.5, 9);
      camera.lookAt(0, 0.15, 0);
      sections.forEach(sec => sec.classList.add('active'));
      progressBar.style.width = '100%';
      demandGroup.visible = true;
      candidateGroup.visible = true;
      circleGroup.visible = true;
      sceneHud.classList.add('visible');
    }

    // ================================================================
    // PERFORMANCE
    // ================================================================
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) gsap.ticker.pause();
      else gsap.ticker.resume();
    });

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) gsap.ticker.resume();
        else gsap.ticker.pause();
      });
    }, { threshold: 0.08 });
    observer.observe(sceneCol);

    console.log('✅ MCLP Scrollytelling + Marketing Homepage merged.');