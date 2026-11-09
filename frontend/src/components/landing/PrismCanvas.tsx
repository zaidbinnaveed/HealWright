import { useEffect, useRef } from "react";

type V = [number, number];
interface Seg {
  a: V;
  b: V;
  e: number;
  inside: boolean;
  key: string;
}

const WAVES = 48; // spec: 72; 48 keeps the band smooth at a third less work per frame
const LAMBDA = Array.from({ length: WAVES }, (_, i) => 410 + (i * (695 - 410)) / (WAVES - 1));
const IOR = LAMBDA.map((l) => 1.2 + 0.1 / (l / 1000) ** 2); // Cauchy, λ in µm

function spectrum(l: number): [number, number, number] {
  // piecewise visible-spectrum approximation (violet/blue, cyan, green, yellow, red)
  let r = 0;
  let g = 0;
  let b = 0;
  if (l < 440) [r, g, b] = [(440 - l) / 30, 0, 1];
  else if (l < 490) [r, g, b] = [0, (l - 440) / 50, 1];
  else if (l < 510) [r, g, b] = [0, 1, (510 - l) / 20];
  else if (l < 580) [r, g, b] = [(l - 510) / 70, 1, 0];
  else if (l < 645) [r, g, b] = [1, (645 - l) / 65, 0];
  else [r, g, b] = [1, 0, 0];
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}
const VIVID = LAMBDA.map(spectrum);

const sub = (a: V, b: V): V => [a[0] - b[0], a[1] - b[1]];
const add = (a: V, b: V): V => [a[0] + b[0], a[1] + b[1]];
const mul = (a: V, k: number): V => [a[0] * k, a[1] * k];
const dot = (a: V, b: V) => a[0] * b[0] + a[1] * b[1];
const norm = (a: V): V => {
  const l = Math.hypot(a[0], a[1]) || 1;
  return [a[0] / l, a[1] / l];
};
const lerp = (a: V, b: V, t: number): V => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];

function intersect(o: V, d: V, p: V, q: V): number | null {
  const e = sub(q, p);
  const den = d[0] * e[1] - d[1] * e[0];
  if (Math.abs(den) < 1e-9) return null;
  const w = sub(p, o);
  const t = (w[0] * e[1] - w[1] * e[0]) / den;
  const u = (w[0] * d[1] - w[1] * d[0]) / den;
  return t > 1e-6 && u >= 0 && u <= 1 ? t : null;
}

function trace(
  verts: V[],
  normals: V[],
  o: V,
  d: V,
  n: number,
  inside: boolean,
  skip: number,
  depth: number,
  energy: number,
  key: string,
  far: number,
  out: Seg[],
) {
  let best: { t: number; e: number } | null = null;
  for (let e = 0; e < 3; e++) {
    if (e === skip) continue;
    const t = intersect(o, d, verts[e] as V, verts[(e + 1) % 3] as V);
    if (t !== null && (!best || t < best.t)) best = { t, e };
  }
  if (!best) {
    out.push({ a: o, b: add(o, mul(d, far)), e: energy, inside, key });
    return;
  }
  const hit = add(o, mul(d, best.t));
  out.push({ a: o, b: hit, e: energy, inside, key });
  if (depth >= 7) return;
  const outward = normals[best.e] as V;
  const nrm: V = inside ? mul(outward, -1) : outward; // faces the incident side
  const [n1, n2] = inside ? [n, 1] : [1, n];
  const eta = n1 / n2;
  const cosi = -dot(nrm, d);
  const k = 1 - eta * eta * (1 - cosi * cosi);
  const refl = norm(add(d, mul(nrm, 2 * cosi)));
  if (k < 0) {
    trace(verts, normals, hit, refl, n, inside, best.e, depth + 1, energy, `${key}R${String(best.e)}`, far, out);
    return;
  }
  const cost = Math.sqrt(k);
  const rs = ((n1 * cosi - n2 * cost) / (n1 * cosi + n2 * cost)) ** 2;
  const rp = ((n1 * cost - n2 * cosi) / (n1 * cost + n2 * cosi)) ** 2;
  const R = (rs + rp) / 2;
  const tdir = norm(add(mul(d, eta), mul(nrm, eta * cosi - cost)));
  if (energy * (1 - R) > 0.08)
    trace(verts, normals, hit, tdir, n, !inside, best.e, depth + 1, energy * (1 - R), `${key}T${String(best.e)}`, far, out);
  if (energy * R > 0.12)
    trace(verts, normals, hit, refl, n, inside, best.e, depth + 1, energy * R, `${key}R${String(best.e)}`, far, out);
}

/** Incidence angle (deg) from pointer height: -35° (top) → 60° (middle) → 75° (bottom). */
function incidence(y: number): number {
  return y < 0.5 ? -35 + (95 * y) / 0.5 : 60 + (15 * (y - 0.5)) / 0.5;
}

export function PrismCanvas({ copyRef }: { copyRef: React.RefObject<HTMLElement | null> }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cvMaybe = canvas.current;
    if (!cvMaybe) return;
    const cv: HTMLCanvasElement = cvMaybe;
    const ctxMaybe = cv.getContext("2d");
    const light = document.createElement("canvas");
    const lctxMaybe = light.getContext("2d");
    if (!ctxMaybe || !lctxMaybe) return;
    const ctx: CanvasRenderingContext2D = ctxMaybe;
    const lctx: CanvasRenderingContext2D = lctxMaybe;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

    let W = 0;
    let H = 0;
    let dpr = 1;
    let S = 0;
    let cx = 0;
    let cy = 0;
    let mobile = false;
    let verts: V[] = [];
    let normals: V[] = [];
    const scale = 0.5; // light canvas resolution (bloom hides it)

    const target = { x: 0.62, y: 0.42 };
    const aim = { x: 0.62, y: 0.42 };
    let lastMove = performance.now();
    let visible = true;
    let raf = 0;
    const motes = Array.from({ length: 70 }, () => ({
      t: Math.random(),
      off: (Math.random() - 0.5) * 2,
      r: 0.5 + Math.random() * 1.1,
      ph: Math.random() * Math.PI * 2,
      sp: 0.02 + Math.random() * 0.04,
    }));

    function layout() {
      const rect = cv.getBoundingClientRect();
      W = rect.width;
      H = rect.height;
      dpr = Math.min(devicePixelRatio || 1, 2);
      mobile = W < 820;
      cv.width = Math.round(W * dpr);
      cv.height = Math.round(H * dpr);
      light.width = Math.round(W * scale);
      light.height = Math.round(H * scale);
      if (mobile) {
        const copyBottom = copyRef.current ? copyRef.current.getBoundingClientRect().bottom - rect.top : H * 0.45;
        S = Math.min(W * 0.72, H * 0.4, 400);
        cx = W / 2;
        cy = Math.max(copyBottom + 30 + S * 0.62, (copyBottom + 30 + H) / 2);
      } else {
        S = Math.min(W * 0.36, H * 0.62);
        cx = 0.66 * W;
        cy = 0.53 * H;
      }
      const R = S / Math.sqrt(3);
      verts = [
        [cx, cy - R],
        [cx + S / 2, cy + R / 2],
        [cx - S / 2, cy + R / 2],
      ];
      normals = [0, 1, 2].map((e) => {
        const p = verts[e] as V;
        const q = verts[(e + 1) % 3] as V;
        const ed = sub(q, p);
        let nn = norm([ed[1], -ed[0]]);
        const mid = lerp(p, q, 0.5);
        if (dot(nn, sub(mid, [cx, cy])) < 0) nn = mul(nn, -1);
        return nn;
      });
    }

    function frame(now: number) {
      raf = 0;
      if (!visible) return;
      const idle = mobile || now - lastMove > 6000;
      if (idle && !reduce) {
        const a = (now / 18000) * Math.PI * 2;
        target.x = 0.5 + 0.34 * Math.cos(a);
        target.y = 0.5 + 0.34 * Math.sin(a);
      }
      aim.x += (target.x - aim.x) * 0.12;
      aim.y += (target.y - aim.y) * 0.12;
      draw(now);
      if (!reduce) raf = requestAnimationFrame(frame);
    }

    function draw(now: number) {
      const far = Math.hypot(W, H) * 1.5;
      const top = verts[0] as V;
      const right = verts[1] as V;
      const inward = mul(normals[0] as V, -1);
      const th = (incidence(aim.y) * Math.PI) / 180;
      const dir = norm([inward[0] * Math.cos(th) - inward[1] * Math.sin(th), inward[0] * Math.sin(th) + inward[1] * Math.cos(th)]);
      const entry = lerp(top, right, 0.08 + 0.84 * aim.x);
      const src = sub(entry, mul(dir, far));

      lctx.setTransform(scale, 0, 0, scale, 0, 0);
      lctx.globalCompositeOperation = "source-over";
      lctx.clearRect(0, 0, W, H);
      lctx.globalCompositeOperation = "lighter";
      lctx.lineCap = "round";

      // incoming beam + dust
      const k = mobile ? 0.8 : 1;
      lctx.strokeStyle = "rgba(255,255,255,0.3)";
      lctx.lineWidth = 12 * k;
      lctx.beginPath();
      lctx.moveTo(src[0], src[1]);
      lctx.lineTo(entry[0], entry[1]);
      lctx.stroke();
      lctx.strokeStyle = "rgba(255,255,255,1)";
      lctx.lineWidth = 4.5 * k;
      lctx.stroke();
      const perp: V = [-dir[1], dir[0]];
      for (const m of motes) {
        m.t = (m.t + m.sp / 60) % 1;
        const along = 1 - m.t;
        const p = add(sub(entry, mul(dir, along * Math.min(far, W))), mul(perp, m.off * (6 + along * 40)));
        const a = (0.3 + 0.7 * (0.5 + 0.5 * Math.sin(now / 400 + m.ph))) * 0.75;
        lctx.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        lctx.beginPath();
        lctx.arc(p[0], p[1], m.r, 0, Math.PI * 2);
        lctx.fill();
      }

      // dispersed light, grouped by path key so neighbouring wavelengths fill a band
      const paths = IOR.map((n) => {
        const segs: Seg[] = [];
        trace(verts, normals, src, dir, n, false, -1, 0, 1, "", far, segs);
        return segs.slice(1); // first segment = the incoming beam, already drawn
      });
      for (let i = 0; i < WAVES - 1; i++) {
        const a = paths[i] ?? [];
        const b = paths[i + 1] ?? [];
        const byKey = new Map(b.map((s) => [s.key, s]));
        const [r, g, bl] = VIVID[i] ?? [255, 255, 255];
        for (const s of a) {
          const t = byKey.get(s.key);
          if (!t) continue;
          const alpha = s.e * (s.inside ? 0.5 : 0.55); // spec .78 outside; softer so the copy stays readable
          if (s.inside) {
            lctx.fillStyle = `rgba(${String(r)},${String(g)},${String(bl)},${alpha.toFixed(3)})`;
          } else {
            const gr = lctx.createLinearGradient(s.a[0], s.a[1], s.b[0], s.b[1]);
            gr.addColorStop(0, `rgba(${String(r)},${String(g)},${String(bl)},${alpha.toFixed(3)})`);
            gr.addColorStop(0.3, `rgba(${String(r)},${String(g)},${String(bl)},${(alpha * 0.75).toFixed(3)})`);
            gr.addColorStop(0.7, `rgba(${String(r)},${String(g)},${String(bl)},${(alpha * 0.25).toFixed(3)})`);
            gr.addColorStop(1, `rgba(${String(r)},${String(g)},${String(bl)},0)`);
            lctx.fillStyle = gr;
          }
          lctx.beginPath();
          lctx.moveTo(s.a[0], s.a[1]);
          lctx.lineTo(s.b[0], s.b[1]);
          lctx.lineTo(t.b[0], t.b[1]);
          lctx.lineTo(t.a[0], t.a[1]);
          lctx.closePath();
          lctx.fill();
        }
      }
      // white-balanced core lines (thin, low alpha per wavelength; they sum towards white)
      for (let i = 0; i < WAVES; i++) {
        const [r, g, bl] = VIVID[i] ?? [255, 255, 255];
        for (const s of paths[i] ?? []) {
          const alpha = (s.e * 2.2) / WAVES;
          lctx.strokeStyle = `rgba(${String(Math.round((r + 255) / 2))},${String(Math.round((g + 255) / 2))},${String(Math.round((bl + 255) / 2))},${alpha.toFixed(3)})`;
          lctx.lineWidth = s.inside ? 4 : 3.4;
          lctx.beginPath();
          lctx.moveTo(s.a[0], s.a[1]);
          lctx.lineTo(s.b[0], s.b[1]);
          lctx.stroke();
        }
      }
      // edge glints where the beam crosses a face
      const glint = (p: V) => {
        const gr = lctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], 0.2 * S);
        gr.addColorStop(0, "rgba(255,255,255,0.9)");
        gr.addColorStop(1, "rgba(255,255,255,0)");
        lctx.strokeStyle = gr;
        lctx.lineWidth = 2;
        lctx.beginPath();
        lctx.moveTo((verts[0] as V)[0], (verts[0] as V)[1]);
        for (const v of [verts[1], verts[2], verts[0]] as V[]) lctx.lineTo(v[0], v[1]);
        lctx.stroke();
        lctx.fillStyle = "white";
        lctx.beginPath();
        lctx.arc(p[0], p[1], 2.6, 0, Math.PI * 2);
        lctx.fill();
      };
      glint(entry);
      const mid = paths[Math.floor(WAVES / 2)]?.[0];
      if (mid) glint(mid.b);

      // composite: soft bloom only (no unblurred pass), then the thin prism outline (fallback path)
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, cv.width, cv.height);
      ctx.globalCompositeOperation = "screen";
      for (const [blur, alpha] of [
        [34, 0.6],
        [12, 0.9],
        [3.2, 1],
      ] as const) {
        ctx.filter = `blur(${String(blur * dpr)}px)`;
        ctx.globalAlpha = alpha;
        ctx.drawImage(light, 0, 0, cv.width, cv.height);
      }
      ctx.filter = "none";
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const glass = ctx.createLinearGradient(cx, cy - S / 2, cx, cy + S / 2);
      glass.addColorStop(0, "rgba(255,255,255,0.07)");
      glass.addColorStop(1, "rgba(255,255,255,0.015)");
      ctx.fillStyle = glass;
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 1;
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo((verts[0] as V)[0], (verts[0] as V)[1]);
      ctx.lineTo((verts[1] as V)[0], (verts[1] as V)[1]);
      ctx.lineTo((verts[2] as V)[0], (verts[2] as V)[1]);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    const kick = () => {
      if (!raf && visible) raf = requestAnimationFrame(frame);
    };
    let resizeTimer = 0;
    const onResize = () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        layout();
        kick();
        if (reduce) draw(performance.now());
      }, 60);
    };
    const onMove = (e: PointerEvent) => {
      if (!e.isPrimary || mobile) return;
      const r = cv.getBoundingClientRect();
      target.x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      target.y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
      lastMove = performance.now();
      if (reduce) {
        aim.x = target.x;
        aim.y = target.y;
        draw(lastMove);
      }
      kick();
    };
    const io = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting && !document.hidden;
      kick();
    });
    const onVis = () => {
      visible = !document.hidden;
      kick();
    };

    layout();
    void document.fonts.ready.then(() => {
      layout();
      if (reduce) draw(performance.now());
    });
    io.observe(cv);
    window.addEventListener("resize", onResize);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("visibilitychange", onVis);
    if (reduce) draw(performance.now());
    else kick();
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [copyRef]);

  return <canvas ref={canvas} aria-hidden="true" className="absolute inset-0 h-full w-full animate-fade" />;
}
