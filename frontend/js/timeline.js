// Reloj de misión y barra de tiempo.
// La barra no es lineal en t: cada fase ocupa un ancho proporcional a log(duración), así el
// ascenso (8 min) no queda aplastado frente al tránsito (4 días).
import { PHASE_COLORS } from "./palette.js";

export const SPEEDS = [1, 10, 100, 1000, 10000, 50000];

export function createPhaseScale(phases) {
  const w = phases.map((p) => Math.log1p(p.t_end - p.t_start));
  const total = w.reduce((a, b) => a + b, 0);
  const edges = [0];
  for (const x of w) edges.push(edges[edges.length - 1] + x / total);

  function toFraction(t) {
    const i = Math.max(0, phases.findIndex((p) => t <= p.t_end));
    const p = phases[i];
    const u = Math.min(Math.max((t - p.t_start) / (p.t_end - p.t_start), 0), 1);
    return edges[i] + u * (edges[i + 1] - edges[i]);
  }

  function toTime(f) {
    let i = edges.findIndex((e, k) => k > 0 && f <= e) - 1;
    if (i < 0) i = phases.length - 1;
    const p = phases[i];
    const u = (f - edges[i]) / (edges[i + 1] - edges[i]);
    return p.t_start + Math.min(Math.max(u, 0), 1) * (p.t_end - p.t_start);
  }

  return { toFraction, toTime, edges };
}

export function formatMET(t) {
  const s = Math.max(0, t);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const pad = (x) => String(x).padStart(2, "0");
  return `T+ ${d}d ${pad(h)}:${pad(m)}:${pad(sec)}`;
}

/**
 * Conecta la barra y los botones. `state` = { t, playing, speedIndex } se modifica en sitio.
 * onEvent(label) se llama al cruzar un evento mientras se reproduce.
 */
export function createTimeline(dom, mission, state, onEvent) {
  const { phases, events } = mission;
  const scale = createPhaseScale(phases);
  const tEnd = phases[phases.length - 1].t_end;

  // Bandas de fase y marcas de eventos
  phases.forEach((p, i) => {
    const band = document.createElement("div");
    band.className = "phase-band";
    band.style.left = `${scale.edges[i] * 100}%`;
    band.style.width = `${(scale.edges[i + 1] - scale.edges[i]) * 100}%`;
    band.style.background = PHASE_COLORS[p.id] ?? "#888";
    band.title = p.name;
    band.textContent = p.name;
    dom.track.appendChild(band);
  });
  for (const e of events) {
    const tick = document.createElement("button");
    tick.className = "event-tick";
    tick.style.left = `${scale.toFraction(e.t) * 100}%`;
    tick.title = e.label;
    tick.setAttribute("aria-label", `Ir a ${e.label}`);
    tick.addEventListener("click", () => seek(e.t));
    dom.track.appendChild(tick);
  }

  dom.slider.addEventListener("input", () => seek(scale.toTime(Number(dom.slider.value) / 1000), false));
  dom.play.addEventListener("click", togglePlay);
  dom.speed.innerHTML = SPEEDS.map((s, i) => `<option value="${i}">×${s.toLocaleString("es")}</option>`).join("");
  dom.speed.value = String(state.speedIndex);
  dom.speed.addEventListener("change", () => (state.speedIndex = Number(dom.speed.value)));

  function seek(t, moveSlider = true) {
    state.t = Math.min(Math.max(t, 0), tEnd);
    if (moveSlider) syncSlider();
  }

  function syncSlider() {
    dom.slider.value = String(Math.round(scale.toFraction(state.t) * 1000));
  }

  function togglePlay() {
    if (state.t >= tEnd) state.t = 0;
    state.playing = !state.playing;
    dom.play.textContent = state.playing ? "❚❚" : "▶";
    dom.play.setAttribute("aria-label", state.playing ? "Pausa" : "Reproducir");
  }

  function setSpeed(delta) {
    state.speedIndex = Math.min(Math.max(state.speedIndex + delta, 0), SPEEDS.length - 1);
    dom.speed.value = String(state.speedIndex);
  }

  /** Salta al evento anterior/siguiente (dir = ±1). */
  function jumpEvent(dir) {
    const eps = 1e-3;
    const list = dir > 0 ? events.filter((e) => e.t > state.t + eps) : events.filter((e) => e.t < state.t - eps).reverse();
    if (list.length) seek(list[0].t);
  }

  /** Avanza el reloj dt_real segundos de pared. */
  function tick(dtReal) {
    if (!state.playing) return;
    const t0 = state.t;
    const t1 = Math.min(t0 + dtReal * SPEEDS[state.speedIndex], tEnd);
    for (const e of events) if (e.t > t0 && e.t <= t1) onEvent(e.label);
    state.t = t1;
    if (t1 >= tEnd && state.playing) togglePlay();
    syncSlider();
  }

  syncSlider();
  return { tick, seek, togglePlay, setSpeed, jumpEvent, tEnd };
}
