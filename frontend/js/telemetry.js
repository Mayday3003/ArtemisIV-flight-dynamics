// Telemetría derivada del estado ECI. Módulo puro: sin DOM ni Three.js.
// Cerca de la Luna la velocidad se da respecto a su superficie: la velocidad ECI incluye
// ~1 km/s del movimiento orbital de la Luna y escondería el contacto a 1 m/s.

/** st: estado ECI interpolado; moonPos: posición ECI de la Luna; frames: createFrames(). */
export function telemetry(st, moonPos, frames, bodies) {
  const rel = st.r.map((x, i) => x - moonPos[i]);
  const dE = Math.hypot(...st.r);
  const dM = Math.hypot(...rel);
  const nearMoon = dM - bodies.moon.radius_km < dE - bodies.earth.radius_km;
  const alt = Math.max(nearMoon ? dM - bodies.moon.radius_km : dE - bodies.earth.radius_km, 0);
  const v = nearMoon ? frames.moonFixedVelocity(st.r, st.v) : st.v;
  const speed = Math.hypot(...v);
  const up = (nearMoon ? rel : st.r).map((x) => x / (nearMoon ? dM : dE));
  const vertical = v[0] * up[0] + v[1] * up[1] + v[2] * up[2];
  const horizontal = Math.sqrt(Math.max(speed * speed - vertical * vertical, 0));
  return { nearMoon, alt, speed, vertical, horizontal, distMoon: dM };
}

/** Longitud en km con la unidad que se lee mejor. */
export function formatAltitude(km, fmt) {
  return km < 10 ? `${fmt(km * 1000, km < 0.1 ? 1 : 0)} m` : `${fmt(km, 1)} km`;
}

/** Velocidad en km/s, o en m/s si es menor que 1 km/s. */
export function formatSpeed(kms, fmt) {
  return Math.abs(kms) < 1 ? `${fmt(kms * 1000, 1)} m/s` : `${fmt(kms, 3)} km/s`;
}
