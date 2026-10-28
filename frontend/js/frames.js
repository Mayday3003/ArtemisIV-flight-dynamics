// Marcos de referencia. Módulo puro (Float64, sin Three.js).
//
// Cada marco es una transformación afín  r_marco = M(t) · (r_ECI − o(t)):
//   eci  : M = I,                         o = 0
//   rot  : M = filas (e_Luna, e_⊥, h),     o = 0     → la Luna queda fija en (d, 0, 0)
//   moon : M = I,                         o = r_Luna(t)  (selenocéntrico, ejes ECI)
// Con θ = n·t + φ0 y (p, q, h) la base del plano lunar (ephemeris.LunarOrbitConfig.plane_basis):
//   e_Luna = cos θ p + sin θ q,   e_⊥ = −sin θ p + cos θ q.

export const FRAMES = {
  eci: "Inercial ECI J2000",
  rot: "Rotante Tierra–Luna",
  moon: "Selenocéntrico",
};

const IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1];

export function planeBasis(inclination, raan) {
  const ci = Math.cos(inclination);
  const si = Math.sin(inclination);
  const co = Math.cos(raan);
  const so = Math.sin(raan);
  return {
    p: [co, so, 0],
    q: [-so * ci, co * ci, si],
    h: [so * si, -co * si, ci],
  };
}

/** Crea las funciones de marco a partir de `bodies.moon` del JSON (km, rad, s). */
export function createFrames(moon) {
  const d = moon.orbit_radius_km;
  const n = moon.mean_motion_rad_s;
  const { p, q, h } = planeBasis(moon.inclination_rad, moon.raan_rad);
  const theta = (t) => n * t + moon.phase0_rad;

  function moonPosition(t) {
    const c = Math.cos(theta(t));
    const s = Math.sin(theta(t));
    return [d * (c * p[0] + s * q[0]), d * (c * p[1] + s * q[1]), d * (c * p[2] + s * q[2])];
  }

  /** Matriz 3×3 por filas. */
  function matrix(frame, t) {
    if (frame !== "rot") return IDENTITY;
    const c = Math.cos(theta(t));
    const s = Math.sin(theta(t));
    return [
      c * p[0] + s * q[0], c * p[1] + s * q[1], c * p[2] + s * q[2],
      -s * p[0] + c * q[0], -s * p[1] + c * q[1], -s * p[2] + c * q[2],
      h[0], h[1], h[2],
    ];
  }

  function origin(frame, t) {
    return frame === "moon" ? moonPosition(t) : [0, 0, 0];
  }

  /** Transforma un punto ECI (km) al marco en el instante t. */
  function toFrame(frame, r, t) {
    const o = origin(frame, t);
    return applyMatrix(matrix(frame, t), [r[0] - o[0], r[1] - o[1], r[2] - o[2]]);
  }

  /** Transforma una dirección (sin trasladar). */
  function directionToFrame(frame, v, t) {
    return applyMatrix(matrix(frame, t), v);
  }

  return { moonPosition, matrix, origin, toFrame, directionToFrame, radius: d, normal: h, meanMotion: n };
}

export function applyMatrix(M, v) {
  return [
    M[0] * v[0] + M[1] * v[1] + M[2] * v[2],
    M[3] * v[0] + M[4] * v[1] + M[5] * v[2],
    M[6] * v[0] + M[7] * v[1] + M[8] * v[2],
  ];
}
