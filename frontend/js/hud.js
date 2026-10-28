// Telemetría en vivo (todo en km, km/s y t, como llega del JSON).
import { formatMET } from "./timeline.js";

const fmt = (x, d = 1) => x.toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d });

export function createHud(dom, bodies) {
  const rE = bodies.earth.radius_km;
  const rM = bodies.moon.radius_km;

  /** st: estado ECI interpolado; moonPos: posición ECI de la Luna; frameName: texto. */
  function update(t, st, phaseName, moonPos, frameName) {
    const dE = Math.hypot(...st.r);
    const rel = st.r.map((x, i) => x - moonPos[i]);
    const dM = Math.hypot(...rel);
    // Cuerpo "más cercano" por altitud sobre la superficie
    const nearMoon = dM - rM < dE - rE;
    dom.met.textContent = formatMET(t);
    dom.phase.textContent = phaseName;
    dom.altLabel.textContent = nearMoon ? "Altitud (Luna)" : "Altitud (Tierra)";
    dom.alt.textContent = `${fmt(nearMoon ? dM - rM : dE - rE)} km`;
    dom.distMoon.textContent = `${fmt(dM, 0)} km`;
    dom.speed.textContent = `${fmt(Math.hypot(...st.v), 3)} km/s`;
    dom.mass.textContent = `${fmt(st.m, 1)} t`;
    dom.frame.textContent = frameName;
  }

  let toastTimer = 0;
  function toast(text) {
    dom.toast.textContent = text;
    dom.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => dom.toast.classList.remove("show"), 2500);
  }

  return { update, toast };
}
