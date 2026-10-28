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
