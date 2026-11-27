/*
 * Hero "audit field": a Canvas2D field of test-case nodes linked to verifier
 * nodes. The pointer is a probe (nodes brighten, show pass/fail glyphs and
 * bend away like a lens), a click or tap sends a mutation ripple that makes
 * nodes re-run, and every few seconds one node turns out to be backed by a
 * lying verifier: it flashes the accent colour and a trace runs back to its
 * verifier.
 *
 * Vanilla TS, no dependencies. State lives in typed arrays and nothing is
 * allocated per frame. The loop pauses off-screen and in hidden tabs, and
 * prefers-reduced-motion gets one static, composed frame with no loop.
 */

type RGB = [number, number, number];

const TAU = Math.PI * 2;
const MAX_RIPPLES = 4;
const MAX_LIARS = 2;

function hexToRgb(value: string, fallback: RGB): RGB {
  const m = /^#?([0-9a-f]{6})$/i.exec(value.trim());
  if (!m) return fallback;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function token(name: string, fallback: RGB): RGB {
  return hexToRgb(getComputedStyle(document.documentElement).getPropertyValue(name), fallback);
}

const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

/** Deterministic integer hash -> [0, 1). */
function hash(a: number, b = 0): number {
  let h = (a * 374761393 + b * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
function smoothstep(a: number, b: number, v: number) {
  const t = clamp01((v - a) / (b - a));
  return t * t * (3 - 2 * t);
}
const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

function makeSprite(c: RGB, size: number, core: number): HTMLCanvasElement {
  const s = document.createElement("canvas");
  s.width = s.height = size;
  const g = s.getContext("2d")!;
  const r = size / 2;
  const grad = g.createRadialGradient(r, r, 0, r, r, r);
  grad.addColorStop(0, rgba(c, 1));
  grad.addColorStop(core, rgba(c, 1));
  grad.addColorStop(Math.min(1, core + 0.18), rgba(c, 0.35));
  grad.addColorStop(1, rgba(c, 0));
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  return s;
}

export function mountHeroField(root: HTMLElement) {
  const canvas = root.querySelector("canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;
  const host = (root.parentElement ?? root) as HTMLElement;

  // Current site tokens only (global.css @theme); fallbacks mirror them.
  const PAPER = token("--color-paper", [243, 239, 230]);
  const GOLD = token("--color-gold", [215, 181, 109]);
  const GOLD_B = token("--color-gold-bright", [240, 211, 146]);
  const OK = token("--color-ok", [143, 191, 159]);
  const ERR = token("--color-error", [224, 112, 88]);

  const dotSprite = makeSprite(PAPER, 32, 0.32);
  const goldSprite = makeSprite(GOLD_B, 32, 0.3);
  const glowSprite = makeSprite(GOLD, 64, 0.04);

  const reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let reduced = reduceQuery.matches;

  // ---- geometry / state -------------------------------------------------
  let W = 0;
  let H = 0;
  let dpr = 1;
  let maxDpr = Math.min(window.devicePixelRatio || 1, 2);
  let spacing = 40;
  let cols = 0;
  let rows = 0;
  let n = 0;
  let narrow = false;

  // Struct-of-arrays, sized once per layout. cell index -> node index (or -1).
  let cellNode = new Int32Array(0);
  let bx = new Float32Array(0);
  let by = new Float32Array(0);
  let px = new Float32Array(0);
  let py = new Float32Array(0);
  let z = new Float32Array(0);
  let phase = new Float32Array(0);
  let wgt = new Float32Array(0);
  let heat = new Float32Array(0);
  let heatT = new Float32Array(0);
  let flick = new Float32Array(0);
  let col = new Int16Array(0);
  let row = new Int16Array(0);
  let ver = new Int32Array(0); // verifier node index for tasks, -1 if none / is a verifier
  let kind = new Uint8Array(0); // 0 task, 1 verifier
  let fail = new Uint8Array(0); // result glyph: 0 pass, 1 fail
  let linked = new Uint8Array(0);
  let lastRipple = new Uint8Array(0);
  let verList = new Int32Array(0);
  let verCount = 0;
  let verPulse = new Float32Array(0); // per node, used for verifiers
  let quiet = new Uint8Array(0); // 1 = sits under hero copy: kept dim, no glyphs
  // Padded boxes of the hero copy (root-relative), refreshed on layout.
  const MAX_BOXES = 24;
  const boxes = new Float32Array(MAX_BOXES * 4);
  let boxCount = 0;

  // Probe
  let probeX = 0;
  let probeY = 0;
  let probeS = 0; // strength 0..1
  let ptrX = 0;
  let ptrY = 0;
  let ptrInside = false;
  let ptrLast = -1e9;
  let probeR = 150;

  // Ripples
  const rpX = new Float32Array(MAX_RIPPLES);
  const rpY = new Float32Array(MAX_RIPPLES);
  const rpT = new Float32Array(MAX_RIPPLES).fill(-1e9);
  const rpId = new Uint8Array(MAX_RIPPLES);
  let rpNext = 0;
  let rpSerial = 1;

  // Lying verifiers
  const lzNode = new Int32Array(MAX_LIARS).fill(-1);
  const lzT = new Float32Array(MAX_LIARS).fill(-1e9);
  let lzNext = 0;
  let lzDue = 2.2;
  let lzSeed = 7;

  const LIAR_LIFE = 2.6;

  function weightAt(x: number, y: number): number {
    const u = x / W;
    const v = y / H;
    const vert = smoothstep(0, 0.06, v) * (1 - smoothstep(0.42, 0.98, v));
    // Narrow screens: text spans the width, so the field lives mostly in the top band.
    if (narrow) return smoothstep(0, 0.03, v) * (1 - smoothstep(0.1, 0.62, v)) * (0.6 + 0.4 * smoothstep(0.2, 1, u));
    // Quiet behind the headline column on the left, full strength on the right.
    return vert * (0.22 + 0.78 * smoothstep(0.2, 0.7, u));
  }

  function readCopyBoxes(rect: DOMRect) {
    boxCount = 0;
    const els = host.querySelectorAll("h1, h2, p, pre, dl, .cmd-label");
    const pad = 14;
    const range = document.createRange();
    for (let e = 0; e < els.length && boxCount < MAX_BOXES; e++) {
      // Tight text boxes (line rects), not the full-width block boxes.
      range.selectNodeContents(els[e]);
      const rs = range.getClientRects();
      for (let k = 0; k < rs.length && boxCount < MAX_BOXES; k++) {
        const r = rs[k];
        if (r.width < 1 || r.top - rect.top > rect.height) continue;
        boxes[boxCount * 4] = r.left - rect.left - pad;
        boxes[boxCount * 4 + 1] = r.top - rect.top - pad;
        boxes[boxCount * 4 + 2] = r.right - rect.left + pad;
        boxes[boxCount * 4 + 3] = r.bottom - rect.top + pad;
        boxCount++;
      }
    }
  }

  function inCopy(x: number, y: number): boolean {
    for (let b = 0; b < boxCount; b++) {
      const o = b * 4;
      if (x >= boxes[o] && x <= boxes[o + 2] && y >= boxes[o + 1] && y <= boxes[o + 3]) return true;
    }
    return false;
  }

  function layout() {
    const rect = root.getBoundingClientRect();
    readCopyBoxes(rect);
    W = Math.max(1, Math.round(rect.width));
    H = Math.max(1, Math.round(rect.height));
    narrow = W < 760;
    dpr = Math.min(maxDpr, 2);
    canvas!.width = Math.round(W * dpr);
    canvas!.height = Math.round(H * dpr);
    spacing = narrow ? 30 : Math.max(34, Math.min(46, W / 34));
    probeR = narrow ? 110 : 160;
    cols = Math.ceil(W / spacing) + 1;
    rows = Math.ceil(H / spacing) + 1;
    const cells = cols * rows;
    cellNode = new Int32Array(cells).fill(-1);
    bx = new Float32Array(cells);
    by = new Float32Array(cells);
    px = new Float32Array(cells);
    py = new Float32Array(cells);
    z = new Float32Array(cells);
    phase = new Float32Array(cells);
    wgt = new Float32Array(cells);
    heat = new Float32Array(cells);
    heatT = new Float32Array(cells);
    flick = new Float32Array(cells);
    col = new Int16Array(cells);
    row = new Int16Array(cells);
    ver = new Int32Array(cells).fill(-1);
    kind = new Uint8Array(cells);
    fail = new Uint8Array(cells);
    linked = new Uint8Array(cells);
    lastRipple = new Uint8Array(cells);
    verPulse = new Float32Array(cells);
    quiet = new Uint8Array(cells);
    const verTmp: number[] = [];

    const ox = (W - (cols - 1) * spacing) / 2;
    const oy = (H - (rows - 1) * spacing) / 2;
    const VC = 6; // verifier block size in cells
    const VR = 5;
    n = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const isVer = c % VC === 3 && r % VR === 2;
        const h0 = hash(c, r);
        if (!isVer && h0 < 0.16) continue; // break up the grid
        const i = n++;
        cellNode[r * cols + c] = i;
        const jit = isVer ? 0.12 : 0.3;
        const x = ox + c * spacing + (hash(c + 101, r) - 0.5) * 2 * jit * spacing;
        const y = oy + r * spacing + (hash(c, r + 211) - 0.5) * 2 * jit * spacing;
        bx[i] = px[i] = x;
        by[i] = py[i] = y;
        z[i] = isVer ? 0.85 : Math.pow(hash(c + 7, r + 3), 1.25);
        phase[i] = hash(c + 31, r + 17) * TAU;
        quiet[i] = inCopy(x, y) ? 1 : 0;
        wgt[i] = weightAt(x, y) * (quiet[i] ? 0.3 : 1);
        col[i] = c;
        row[i] = r;
        kind[i] = isVer ? 1 : 0;
        fail[i] = hash(c + 53, r + 59) < 0.14 ? 1 : 0;
        linked[i] = !isVer && hash(c + 71, r + 13) < 0.42 ? 1 : 0;
        if (isVer) verTmp.push(i);
      }
    }
    verList = Int32Array.from(verTmp);
    verCount = verTmp.length;
    // Assign each task to the verifier of its block.
    for (let i = 0; i < n; i++) {
      if (kind[i]) continue;
      const vc = Math.min(Math.floor(col[i] / VC) * VC + 3, cols - 1);
      const vr = Math.min(Math.floor(row[i] / VR) * VR + 2, rows - 1);
      const vi = cellNode[vr * cols + vc];
      ver[i] = vi >= 0 && kind[vi] ? vi : -1;
      if (ver[i] < 0) linked[i] = 0;
    }
    if (!ptrInside) {
      probeX = ghostX(now());
      probeY = ghostY(now());
    }
  }

  const ghostX = (t: number) => W * (narrow ? 0.62 + 0.22 * Math.sin(t * 0.17) : 0.7 + 0.15 * Math.sin(t * 0.13));
  const ghostY = (t: number) => (narrow ? 34 + 10 * Math.sin(t * 0.23 + 1) : H * (0.3 + 0.13 * Math.sin(t * 0.21 + 1.3)));

  // ---- events -------------------------------------------------------------
  let rectLeft = 0;
  let rectTop = 0;
  const refreshRect = () => {
    const r = root.getBoundingClientRect();
    rectLeft = r.left;
    rectTop = r.top;
  };

  function onMove(e: PointerEvent) {
    refreshRect();
    const x = e.clientX - rectLeft;
    const y = e.clientY - rectTop;
    ptrInside = x >= 0 && y >= 0 && x <= W && y <= H * 0.9;
    if (ptrInside) {
      ptrX = x;
      ptrY = y;
      ptrLast = now();
    }
  }
  function onLeave(e: PointerEvent) {
    if (!e.relatedTarget) ptrInside = false;
  }
  function onDown(e: PointerEvent) {
    if (e.button !== 0) return;
    const t = e.target as Element | null;
    if (t && t.closest && t.closest("a,button,pre,code,input,select,textarea,summary,dl")) return;
    onMove(e);
    if (!ptrInside) return;
    ripple(ptrX, ptrY, now());
  }
  function ripple(x: number, y: number, t: number) {
    const k = rpNext;
    rpNext = (rpNext + 1) % MAX_RIPPLES;
    rpX[k] = x;
    rpY[k] = y;
    rpT[k] = t;
    rpSerial = (rpSerial % 250) + 1;
    rpId[k] = rpSerial;
  }

  // ---- simulation -------------------------------------------------------
  const t0 = performance.now();
  const now = () => (performance.now() - t0) / 1000;

  function spawnLiar(t: number) {
    // Pick a visible, linked task node; prefer the brighter right-hand side.
    for (let tries = 0; tries < 200; tries++) {
      lzSeed++;
      const i = Math.floor(hash(lzSeed, 991) * n);
      if (kind[i] || quiet[i] || ver[i] < 0 || wgt[i] < (narrow ? 0.4 : 0.6)) continue;
      if (narrow && (by[i] > 52 || by[i] < 14)) continue; // keep clear of the kicker and headline
      const k = lzNext;
      lzNext = (lzNext + 1) % MAX_LIARS;
      lzNode[k] = i;
      lzT[k] = t;
      return;
    }
  }

  function step(t: number, dt: number, settle: boolean) {
    // Probe target: the pointer while it is active, otherwise a slow ghost.
    const active = ptrInside && t - ptrLast < 3;
    const tx = active ? ptrX : ghostX(t);
    const ty = active ? ptrY : ghostY(t);
    const ts = active ? 1 : reduced ? 0.9 : narrow ? 0.5 : 0.62;
    if (settle) {
      probeX = tx;
      probeY = ty;
      probeS = ts;
    } else {
      const kp = 1 - Math.exp(-dt * (active ? 10 : 2.2));
      probeX += (tx - probeX) * kp;
      probeY += (ty - probeY) * kp;
      probeS += (ts - probeS) * (1 - Math.exp(-dt * 3));
    }

    if (!settle && t >= lzDue) {
      spawnLiar(t);
      lzDue = t + 3.8 + hash(lzSeed, 5) * 2.6;
    }

    const parX = ((probeX / W) - 0.5) * 10;
    const parY = ((probeY / H) - 0.5) * 6;
    const R = probeR;
    const R2 = R * R;
    const kUp = settle ? 1 : 1 - Math.exp(-dt * 14);
    const kDown = settle ? 1 : 1 - Math.exp(-dt * 1.8);
    const kFl = settle ? 1 : dt * 2.2;

    // Base motion for every node (breathing + parallax + ripples).
    for (let i = 0; i < n; i++) {
      const zz = z[i];
      const amp = 1.2 + 1.8 * zz;
      let x = bx[i] + Math.sin(t * 0.33 + phase[i]) * amp + parX * zz;
      let y = by[i] + Math.cos(t * 0.27 + phase[i] * 1.3) * amp + parY * zz;
      for (let k = 0; k < MAX_RIPPLES; k++) {
        const age = t - rpT[k];
        if (age < 0 || age > 2.2) continue;
        const rad = age * 640;
        const dx = bx[i] - rpX[k];
        const dy = by[i] - rpY[k];
        const d = Math.sqrt(dx * dx + dy * dy) + 0.001;
        const band = 1 - Math.abs(d - rad) / 46;
        if (band <= 0) continue;
        const fade = 1 - age / 2.2;
        const push = band * band * 7 * fade;
        x += (dx / d) * push;
        y += (dy / d) * push;
        if (band > 0.55 && lastRipple[i] !== rpId[k]) {
          lastRipple[i] = rpId[k];
          flick[i] = 1;
        }
      }
      px[i] = x;
      py[i] = y;
      heatT[i] = 0;
      if (flick[i] > 0) {
        flick[i] = Math.max(0, flick[i] - kFl);
        if (flick[i] === 0 && !quiet[i]) heat[i] = Math.max(heat[i], 0.95); // re-run done: show its result
      }
    }

    // Probe neighbourhood via the grid (only cells within the radius).
    const pc = Math.round(probeX / spacing);
    const pr = Math.round(probeY / spacing);
    const reach = Math.ceil(R / spacing) + 1;
    const c0 = Math.max(0, pc - reach);
    const c1 = Math.min(cols - 1, pc + reach);
    const r0 = Math.max(0, pr - reach);
    const r1 = Math.min(rows - 1, pr + reach);
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const i = cellNode[r * cols + c];
        if (i < 0) continue;
        const dx = px[i] - probeX;
        const dy = py[i] - probeY;
        const d2 = dx * dx + dy * dy;
        if (d2 >= R2) continue;
        const d = Math.sqrt(d2) + 0.001;
        const f = 1 - d / R;
        const fall = f * f * (3 - 2 * f);
        // Lens: a soft bulge that pushes nodes outward near the probe.
        const push = f * f * R * 0.16 * probeS;
        px[i] += (dx / d) * push;
        py[i] += (dy / d) * push;
        heatT[i] = fall * probeS * (quiet[i] ? 0.22 : 1);
      }
    }

    for (let i = 0; i < n; i++) {
      const target = heatT[i];
      const h = heat[i];
      heat[i] = target > h ? h + (target - h) * kUp : h + (target - h) * kDown;
      if (verPulse[i] > 0) verPulse[i] = Math.max(0, verPulse[i] - dt * 1.4);
    }

    for (let k = 0; k < MAX_LIARS; k++) {
      const i = lzNode[k];
      if (i < 0) continue;
      const age = t - lzT[k];
      if (age > LIAR_LIFE) {
        lzNode[k] = -1;
        continue;
      }
      if (age > 1.15 && age - dt <= 1.15 && ver[i] >= 0) verPulse[ver[i]] = 1;
    }
  }

  // ---- drawing ------------------------------------------------------------
  function strokeGlyph(i: number, a: number) {
    const x = px[i] + 6.5;
    const y = py[i] - 6.5;
    const s = 3;
    ctx!.globalAlpha = a;
    ctx!.beginPath();
    if (fail[i]) {
      ctx!.strokeStyle = rgba(ERR, 1);
      ctx!.moveTo(x - s, y - s);
      ctx!.lineTo(x + s, y + s);
      ctx!.moveTo(x + s, y - s);
      ctx!.lineTo(x - s, y + s);
    } else {
      ctx!.strokeStyle = rgba(OK, 1);
      ctx!.moveTo(x - s, y + 0.2);
      ctx!.lineTo(x - s * 0.25, y + s * 0.85);
      ctx!.lineTo(x + s * 1.1, y - s * 0.9);
    }
    ctx!.stroke();
  }

  // Precomputed style strings (no per-frame string building for the hot path).
  const EDGE_STYLE = rgba(PAPER, 1);
  const HOT_EDGE_STYLE = rgba(GOLD, 1);
  const GOLD_STYLE = rgba(GOLD, 1);
  const GOLD_B_STYLE = rgba(GOLD_B, 1);
  const PAPER_STYLE = rgba(PAPER, 1);
  const DASH = [1.5, 6];
  const NO_DASH: number[] = [];

  function draw(t: number) {
    const g = ctx!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    g.lineCap = "round";
    g.lineJoin = "round";

    // Soft spotlight under the probe gives the field depth.
    if (probeS > 0.05) {
      const sz = probeR * 2.4;
      g.globalAlpha = 0.07 * probeS * (0.35 + 0.65 * weightAt(probeX, probeY)) * (inCopy(probeX, probeY) ? 0.5 : 1);
      g.drawImage(glowSprite, probeX - sz / 2, probeY - sz / 2, sz, sz);
    }

    // Edges, bucketed by weight so the whole web is a handful of strokes.
    g.lineWidth = 0.6;
    g.strokeStyle = EDGE_STYLE;
    for (let b = 0; b < 3; b++) {
      const lo = b / 3;
      const hi = (b + 1) / 3;
      g.beginPath();
      for (let i = 0; i < n; i++) {
        if (!linked[i]) continue;
        const w = wgt[i];
        if (w < lo || w >= hi || w < 0.05) continue;
        const v = ver[i];
        g.moveTo(px[i], py[i]);
        g.lineTo(px[v], py[v]);
      }
      g.globalAlpha = 0.12 * (lo + hi) * 0.5;
      g.stroke();
    }
    // Edges inside the probe glow faintly gold.
    g.strokeStyle = HOT_EDGE_STYLE;
    for (let b = 0; b < 3; b++) {
      const lo = 0.12 + b * 0.29;
      const hi = lo + 0.29;
      g.beginPath();
      let any = false;
      for (let i = 0; i < n; i++) {
        if (!linked[i] || quiet[i] || quiet[ver[i]]) continue;
        const h = heat[i] * (0.4 + 0.6 * wgt[i]);
        if (h < lo || h >= hi) continue;
        const v = ver[i];
        g.moveTo(px[i], py[i]);
        g.lineTo(px[v], py[v]);
        any = true;
      }
      if (!any) continue;
      g.globalAlpha = 0.34 * (lo + hi) * 0.5;
      g.stroke();
    }

    // Ripple rings.
    g.lineWidth = 1;
    g.strokeStyle = GOLD_STYLE;
    for (let k = 0; k < MAX_RIPPLES; k++) {
      const age = t - rpT[k];
      if (age < 0 || age > 2.2) continue;
      const fade = 1 - age / 2.2;
      g.globalAlpha = 0.3 * fade * fade;
      g.beginPath();
      g.arc(rpX[k], rpY[k], age * 640, 0, TAU);
      g.stroke();
      if (age > 0.12) {
        g.globalAlpha = 0.12 * fade * fade;
        g.beginPath();
        g.arc(rpX[k], rpY[k], (age - 0.12) * 640, 0, TAU);
        g.stroke();
      }
    }

    // Nodes.
    for (let i = 0; i < n; i++) {
      const w = wgt[i];
      const h = heat[i];
      if (w < 0.02 && h < 0.02) continue;
      const zz = z[i];
      let a = w * (0.2 + 0.5 * zz) + h * 0.6 * (0.45 + 0.55 * w);
      if (flick[i] > 0) a *= hash(i, Math.floor(t * 28)) > 0.45 ? (quiet[i] ? 1.2 : 1.9) : 0.25;
      if (a < 0.01) continue;
      if (kind[i]) {
        // Verifier: a small ring.
        const rr = 3.2 + zz;
        g.globalAlpha = Math.min(0.8, a * 0.8 + 0.03);
        g.strokeStyle = h > 0.25 ? GOLD_B_STYLE : PAPER_STYLE;
        g.lineWidth = 1;
        g.beginPath();
        g.arc(px[i], py[i], rr, 0, TAU);
        g.stroke();
        const p = verPulse[i];
        if (p > 0) {
          const e = easeOutCubic(1 - p);
          g.globalAlpha = p * 0.8;
          g.strokeStyle = GOLD_B_STYLE;
          g.beginPath();
          g.arc(px[i], py[i], rr + e * 22, 0, TAU);
          g.stroke();
          g.globalAlpha = p * 0.55;
          g.drawImage(glowSprite, px[i] - 22, py[i] - 22, 44, 44);
        }
        continue;
      }
      const size = 2.8 + 4 * zz + h * 3.4;
      g.globalAlpha = Math.min(0.9, a);
      g.drawImage(dotSprite, px[i] - size / 2, py[i] - size / 2, size, size);
      if (h > 0.08) {
        g.globalAlpha = Math.min(0.9, h * (0.35 + 0.5 * w));
        g.drawImage(goldSprite, px[i] - size / 2, py[i] - size / 2, size, size);
      }
    }

    // Pass/fail glyphs on probed or freshly re-run nodes.
    g.lineWidth = 1.3;
    for (let i = 0; i < n; i++) {
      const h = heat[i];
      if (h < 0.42 || kind[i] || quiet[i]) continue;
      const a = smoothstep(0.42, 0.85, h) * (0.45 + 0.5 * wgt[i]);
      if (a > 0.02) strokeGlyph(i, a);
    }

    // Lying verifiers: accent flash on the node, then a trace back to its verifier.
    for (let k = 0; k < MAX_LIARS; k++) {
      const i = lzNode[k];
      if (i < 0) continue;
      const age = t - lzT[k];
      const v = ver[i];
      const flash = age < 0.3 ? easeOutCubic(age / 0.3) : Math.max(0, 1 - (age - 0.3) / (LIAR_LIFE - 0.3));
      g.globalAlpha = 0.75 * flash;
      g.drawImage(glowSprite, px[i] - 26, py[i] - 26, 52, 52);
      g.globalAlpha = Math.min(1, flash * 1.2);
      g.drawImage(goldSprite, px[i] - 4.5, py[i] - 4.5, 9, 9);
      // small diamond marker
      g.strokeStyle = GOLD_B_STYLE;
      g.lineWidth = 1;
      g.globalAlpha = 0.9 * flash;
      g.beginPath();
      const m = 7 + (1 - flash) * 3;
      g.moveTo(px[i], py[i] - m);
      g.lineTo(px[i] + m, py[i]);
      g.lineTo(px[i], py[i] + m);
      g.lineTo(px[i] - m, py[i]);
      g.closePath();
      g.stroke();
      if (v < 0) continue;
      const tp = clamp01((age - 0.25) / 0.9);
      if (tp <= 0) continue;
      const head = easeInOutCubic(tp);
      const tail = easeInOutCubic(clamp01((age - 0.55) / 1.3));
      const x0 = px[i] + (px[v] - px[i]) * tail;
      const y0 = py[i] + (py[v] - py[i]) * tail;
      const x1 = px[i] + (px[v] - px[i]) * head;
      const y1 = py[i] + (py[v] - py[i]) * head;
      g.globalAlpha = 0.85 * (1 - tail * 0.6);
      g.strokeStyle = GOLD_B_STYLE;
      g.lineWidth = 1.25;
      g.beginPath();
      g.moveTo(x0, y0);
      g.lineTo(x1, y1);
      g.stroke();
      if (tp < 1) {
        g.globalAlpha = 0.9;
        g.drawImage(goldSprite, x1 - 3, y1 - 3, 6, 6);
      }
    }

    // Probe reticle: a quiet crosshair, never louder than the content.
    if (probeS > 0.05) {
      const a = 0.26 * probeS * (0.4 + 0.6 * weightAt(probeX, probeY)) * (inCopy(probeX, probeY) ? 0.35 : 1);
      const r = 15;
      g.globalAlpha = a;
      g.strokeStyle = GOLD_STYLE;
      g.lineWidth = 1;
      g.beginPath();
      g.arc(probeX, probeY, r, 0, TAU);
      g.moveTo(probeX - r - 7, probeY);
      g.lineTo(probeX - r - 2, probeY);
      g.moveTo(probeX + r + 2, probeY);
      g.lineTo(probeX + r + 7, probeY);
      g.moveTo(probeX, probeY - r - 7);
      g.lineTo(probeX, probeY - r - 2);
      g.moveTo(probeX, probeY + r + 2);
      g.lineTo(probeX, probeY + r + 7);
      g.stroke();
      g.globalAlpha = a * 0.55;
      g.setLineDash(DASH);
      g.beginPath();
      g.arc(probeX, probeY, probeR * 0.98, 0, TAU);
      g.stroke();
      g.setLineDash(NO_DASH);
    }
    g.globalAlpha = 1;
  }

  // ---- static frame for reduced motion -------------------------------------
  function drawStatic() {
    const t = 14;
    ptrInside = false;
    for (let i = 0; i < n; i++) {
      heat[i] = 0;
      flick[i] = 0;
      verPulse[i] = 0;
    }
    rpT.fill(-1e9);
    lzNode.fill(-1);
    step(t, 0, true);
    probeS = 1;
    step(t, 0, true);
    probeS = 1;
    // One composed "finding": a liar mid-trace on the right-hand side.
    let best = -1;
    let bestScore = -1;
    for (let i = 0; i < n; i++) {
      if (kind[i] || ver[i] < 0) continue;
      const s = wgt[i] - Math.abs(px[i] / W - 0.82) - Math.abs(py[i] / H - 0.18);
      if (s > bestScore) {
        bestScore = s;
        best = i;
      }
    }
    if (best >= 0) {
      lzNode[0] = best;
      lzT[0] = t - 0.85;
    }
    draw(t);
    lzNode.fill(-1);
  }

  // ---- loop / lifecycle ---------------------------------------------------
  let raf = 0;
  let running = false;
  // The composed static frame shows first; the loop arms on the first user
  // interaction or after a few idle seconds, so it never competes with load.
  let armed = false;
  let inView = true;
  let last = 0;
  // Frame governor: samples the frame interval (which includes canvas raster
  // and compositing, not just our JS) over frames 4-13. Slow devices drop to
  // DPR 1, and if still slow they get the static frame instead of a loop, so
  // the field never costs more than it is worth.
  const SAMPLES = 10;
  const WARMUP = 12;
  const samples = new Float32Array(SAMPLES);
  let sampleN = -WARMUP;
  let tier = 0; // 0 full, 1 DPR 1, 2 static
  // ?field=full skips the governor (screen recordings and benchmarks only).
  const governed = !/[?&]field=full\b/.test(location.search);
  const median = () => {
    const a = Array.from(samples).sort((x, y) => x - y);
    return (a[4] + a[5]) / 2;
  };

  function frame() {
    raf = requestAnimationFrame(frame);
    const t = now();
    const dt = Math.min(0.05, Math.max(0, t - last));
    const rawDt = t - last;
    last = t;
    step(t, dt, false);
    draw(t);
    if (governed && tier < 2 && sampleN < SAMPLES) {
      if (sampleN >= 0) samples[sampleN] = rawDt * 1000;
      sampleN++;
      if (sampleN === SAMPLES) {
        const m = median();
        root.dataset.frameMs = m.toFixed(1);
        if (m > 24 && (tier === 1 || maxDpr <= 1 || m > 45)) {
          tier = 2;
          root.dataset.tier = "2";
          running = false;
          cancelAnimationFrame(raf);
          drawStatic();
        } else if (m > 24) {
          tier = 1;
          root.dataset.tier = "1";
          maxDpr = 1;
          layout();
          sampleN = -WARMUP;
        }
      }
    }
  }

  function update() {
    const should = armed && inView && !document.hidden && !reduced && tier < 2;
    if (should && !running) {
      running = true;
      last = now();
      if (sampleN > -WARMUP && sampleN < SAMPLES) sampleN = -WARMUP; // resample after a pause
      raf = requestAnimationFrame(frame);
    } else if (!should && running) {
      running = false;
      cancelAnimationFrame(raf);
    }
  }

  function render() {
    layout();
    if (reduced || tier === 2 || !armed) drawStatic();
    else draw(now());
  }

  let resizeQueued = false;
  const ro = new ResizeObserver(() => {
    if (resizeQueued) return;
    resizeQueued = true;
    requestAnimationFrame(() => {
      resizeQueued = false;
      render();
    });
  });
  ro.observe(root);

  const io = new IntersectionObserver((entries) => {
    inView = entries[entries.length - 1].isIntersecting;
    update();
  });
  io.observe(root);

  document.addEventListener("visibilitychange", update);
  reduceQuery.addEventListener("change", (e) => {
    reduced = e.matches;
    render();
    update();
  });

  window.addEventListener("pointermove", onMove, { passive: true });
  window.addEventListener("pointerdown", (e) => {
    if (host.contains(e.target as Node)) onDown(e);
  }, { passive: true });
  document.addEventListener("pointerout", onLeave, { passive: true });

  const arm = () => {
    if (armed) return;
    armed = true;
    for (const ev of ARM_EVENTS) window.removeEventListener(ev, arm);
    clearTimeout(armTimer);
    update();
  };
  const ARM_EVENTS = ["pointermove", "pointerdown", "wheel", "scroll", "keydown", "touchstart"] as const;
  for (const ev of ARM_EVENTS) window.addEventListener(ev, arm, { passive: true });
  const armTimer = setTimeout(arm, 6000);

  render();
  update();
  root.classList.add("is-ready");

}
