// Reloj de misión y barra de tiempo.
// La barra no es lineal en t: cada fase ocupa un ancho proporcional a log(duración), así el
// ascenso (8 min) no queda aplastado frente al tránsito (4 días).
import { PHASE_COLORS } from "./palette.js";
import { AUTO_RATE, PHASE_INFO, eventInfo } from "./story.js";
import { phaseIndexAt } from "./tour.js";

/** El índice 0 es el modo Auto: la velocidad depende de la fase. */
export const SPEEDS = [0, 1, 10, 100, 1000, 10000, 50000];

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
 * on.cross(evento) se llama al cruzar un evento reproduciendo; on.jump(evento) al saltar a él.
 */
export function createTimeline(dom, mission, state, on) {
  const { phases, events } = mission;
  const scale = createPhaseScale(phases);
  const tEnd = phases[phases.length - 1].t_end;

  // Bandas de fase y marcas de eventos
  phases.forEach((p, i) => {
    const left = `${scale.edges[i] * 100}%`;
    const width = `${(scale.edges[i + 1] - scale.edges[i]) * 100}%`;
    const band = document.createElement("div");
    band.className = "phase-band";
    band.style.left = left;
    band.style.width = width;
    band.style.background = PHASE_COLORS[p.id] ?? "#888";
    band.title = p.name;
    dom.track.appendChild(band);
    const name = document.createElement("div");
    name.className = "phase-name";
    name.style.left = left;
    name.style.width = width;
    name.style.color = PHASE_COLORS[p.id] ?? "#888";
    name.textContent = PHASE_INFO[p.id]?.short ?? p.name;
    dom.names.appendChild(name);
  });

  // Eventos simultáneos (MECO e inserción) comparten marca
  const ticks = [];
  for (const e of events) {
    if (ticks.at(-1)?.t === e.t) {
      ticks.at(-1).el.title += ` · ${e.label}`;
      continue;
    }
    const el = document.createElement("button");
    el.className = "event-tick";
    el.style.left = `${scale.toFraction(e.t) * 100}%`;
    el.title = e.label;
    el.setAttribute("aria-label", `Ir a ${e.label}`);
    el.addEventListener("click", () => {
      seek(e.t);
      on.jump(e);
    });
    dom.track.appendChild(el);
    const tag = document.createElement("span");
    tag.className = "event-tag";
    tag.textContent = eventInfo(e.label).short;
    tag.style.left = el.style.left;
    dom.tags.appendChild(tag);
    ticks.push({ t: e.t, el, tag });
  }

  /** Reparte los nombres en tres filas para que no se pisen; si no caben, se ocultan. */
  function layoutTags() {
    const w = dom.tags.clientWidth;
    const right = [-Infinity, -Infinity, -Infinity];
    for (const { t, tag } of ticks) {
      tag.hidden = false;
      const half = tag.offsetWidth / 2;
      const x = Math.min(Math.max(scale.toFraction(t) * w, half), w - half); // sin salirse de la barra
      const row = right.findIndex((r) => x - half > r + 4);
      tag.hidden = row < 0;
      if (row >= 0) {
        tag.dataset.row = row;
        tag.style.left = `${x}px`;
        right[row] = x + half;
      }
    }
  }
  window.addEventListener("resize", layoutTags);
  layoutTags();

  dom.slider.addEventListener("input", () => seek(scale.toTime(Number(dom.slider.value) / 1000), false));
  dom.play.addEventListener("click", togglePlay);

  function seek(t, moveSlider = true) {
    state.t = Math.min(Math.max(t, 0), tEnd);
    if (moveSlider) syncSlider();
    else dom.curtain.style.left = `${scale.toFraction(state.t) * 100}%`;
  }

  function syncSlider() {
    const f = scale.toFraction(state.t);
    dom.slider.value = String(Math.round(f * 1000));
    dom.curtain.style.left = `${f * 100}%`;
  }

  function setPlaying(on) {
    state.playing = on;
    dom.play.textContent = on ? "❚❚" : "▶";
    dom.play.setAttribute("aria-label", on ? "Pausa" : "Reproducir");
  }

  function togglePlay() {
    if (state.t >= tEnd) state.t = 0;
    setPlaying(!state.playing);
  }

  function setSpeed(delta) {
    state.speedIndex = Math.min(Math.max(state.speedIndex + delta, 0), SPEEDS.length - 1);
  }

  function setSpeedIndex(i) {
    state.speedIndex = Math.min(Math.max(i, 0), SPEEDS.length - 1);
  }

  /** Salta al evento anterior/siguiente (dir = ±1). */
  function jumpEvent(dir) {
    const eps = 1e-3;
    const list = dir > 0 ? events.filter((e) => e.t > state.t + eps) : events.filter((e) => e.t < state.t - eps).reverse();
    if (list.length) {
      seek(list[0].t);
      on.jump(list[0]);
    }
  }

  /** Avanza el reloj dt_real segundos de pared. */
  function tick(dtReal) {
    if (!state.playing) return;
    const t0 = state.t;
    const rate = SPEEDS[state.speedIndex] || AUTO_RATE[phases[phaseIndexAt(phases, t0)].id] || 1000;
    const t1 = Math.min(t0 + dtReal * rate, tEnd);
    for (const e of events) if (e.t > t0 && e.t <= t1) on.cross(e);
    state.t = t1;
    if (t1 >= tEnd) setPlaying(false); // se queda en el alunizaje; togglePlay reiniciaría
    syncSlider();
  }

  syncSlider();
  return { tick, seek, togglePlay, setSpeed, setSpeedIndex, jumpEvent, layoutTags, tEnd };
}
