// Interpolación del estado entre muestras: el mismo Hermite cúbico que
// artemis_sim.export.hermite_interpolate (posición con la velocidad como derivada,
// velocidad y masa lineales). Módulo puro: sin Three.js, se prueba con Node.

/** Convierte el bloque `samples` del JSON a arreglos tipados (Float64 para no perder precisión). */
export function toTypedSamples(samples) {
  const out = {};
  for (const k of ["t", "x", "y", "z", "vx", "vy", "vz", "m"]) out[k] = Float64Array.from(samples[k]);
  out.phase = Int32Array.from(samples.phase_index);
  out.n = out.t.length;
  return out;
}

/** Índice k tal que t[k] <= tq < t[k+1] (búsqueda binaria, acotado a [0, n-2]). */
export function findSegment(t, tq) {
  let lo = 0;
  let hi = t.length - 1;
  if (tq <= t[0]) return 0;
  if (tq >= t[hi]) return hi - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (t[mid] <= tq) lo = mid;
    else hi = mid;
  }
  return lo;
}

/** Estado interpolado en tq: { r: [km], v: [km/s], m: [t], k }. */
export function hermiteState(s, tq) {
  const tc = Math.min(Math.max(tq, s.t[0]), s.t[s.n - 1]);
  const k = findSegment(s.t, tc);
  const h = s.t[k + 1] - s.t[k];
  const u = (tc - s.t[k]) / h;
  const u2 = u * u;
  const u3 = u2 * u;
  const h00 = 2 * u3 - 3 * u2 + 1;
  const h10 = u3 - 2 * u2 + u;
  const h01 = -2 * u3 + 3 * u2;
  const h11 = u3 - u2;
  const pos = (p, v) => h00 * p[k] + h10 * h * v[k] + h01 * p[k + 1] + h11 * h * v[k + 1];
  const lin = (a) => (1 - u) * a[k] + u * a[k + 1];
  return {
    r: [pos(s.x, s.vx), pos(s.y, s.vy), pos(s.z, s.vz)],
    v: [lin(s.vx), lin(s.vy), lin(s.vz)],
    m: lin(s.m),
    k,
  };
}

/**
 * Puntos para dibujar: subdivide con Hermite los tramos que giran más de maxDeg, para que la
 * curva no se vea facetada en el perilunio. Devuelve { t, x, y, z, phase, n }.
 */
export function densify(s, maxDeg = 2, maxSub = 24) {
  const out = { t: [], x: [], y: [], z: [], phase: [] };
  const push = (t, r, phase) => {
    out.t.push(t);
    out.x.push(r[0]);
    out.y.push(r[1]);
    out.z.push(r[2]);
    out.phase.push(phase);
  };
  for (let k = 0; k < s.n - 1; k++) {
    const a = Math.hypot(s.vx[k], s.vy[k], s.vz[k]);
    const b = Math.hypot(s.vx[k + 1], s.vy[k + 1], s.vz[k + 1]);
    const dot = s.vx[k] * s.vx[k + 1] + s.vy[k] * s.vy[k + 1] + s.vz[k] * s.vz[k + 1];
    const deg = (Math.acos(Math.min(Math.max(dot / (a * b || 1), -1), 1)) * 180) / Math.PI;
    const sub = Math.min(Math.max(Math.ceil(deg / maxDeg), 1), maxSub);
    push(s.t[k], [s.x[k], s.y[k], s.z[k]], s.phase[k]);
    for (let i = 1; i < sub; i++) {
      const t = s.t[k] + (i / sub) * (s.t[k + 1] - s.t[k]);
      push(t, hermiteState(s, t).r, s.phase[k + 1]);
    }
  }
  const e = s.n - 1;
  push(s.t[e], [s.x[e], s.y[e], s.z[e]], s.phase[e]);
  return {
    t: Float64Array.from(out.t), x: Float64Array.from(out.x), y: Float64Array.from(out.y),
    z: Float64Array.from(out.z), phase: Int32Array.from(out.phase), n: out.t.length,
  };
}
