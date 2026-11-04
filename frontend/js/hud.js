// Telemetría en vivo, gráficas por fase y panel de ciencia.
import { hermiteState } from "./interpolate.js";
import { PHASE_COLORS } from "./palette.js";
import { PHASE_INFO, dvSpent } from "./story.js";
import { formatAltitude, formatSpeed, telemetry } from "./telemetry.js";
import { formatMET } from "./timeline.js";

const fmt = (x, d = 1) => {
  const rounded = Number(x.toFixed(d)) || 0; // sin "-0,0"
  return rounded.toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: "always" });
};

const SPARK_POINTS = 90;

/** Curva de altitud y velocidad de una fase, en un <canvas>. */
function drawSpark(canvas, values, color) {
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  canvas.width = w * ratio;
  canvas.height = h * ratio;
  const g = canvas.getContext("2d");
  g.scale(ratio, ratio);
  const lo = Math.min(...values);
  const span = Math.max(...values) - lo || 1;
  g.strokeStyle = color;
  g.lineWidth = 1.5;
  g.beginPath();
  values.forEach((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - 2 - ((v - lo) / span) * (h - 4);
    if (i) g.lineTo(x, y);
    else g.moveTo(x, y);
  });
  g.stroke();
}

export function createHud(dom, mission, samples, frames, budget) {
  const { bodies } = mission;
  const total = budget.reduce((s, b) => s + b.dv, 0);
  let phaseId = null;

  // Presupuesto de Δv: un segmento por maniobra, proporcional a su Δv
  dom.dvBar.innerHTML = budget.map((b) => `<i style="flex:${b.dv}" title="${b.name}: ${fmt(b.dv, 0)} m/s"><b></b></i>`).join("");
  dom.dvList.innerHTML = budget.map((b) => `<li><span>${b.name}</span><span>${fmt(b.dv, 0)} m/s</span></li>`).join("");
  const fills = [...dom.dvBar.querySelectorAll("b")];
  const rows = [...dom.dvList.children];

  function showPhase(phase) {
    phaseId = phase.id;
    const info = PHASE_INFO[phase.id];
    const color = PHASE_COLORS[phase.id];
    dom.root.style.setProperty("--phase", color);
    dom.physics.textContent = info.physics;
    dom.method.textContent = info.method;
    dom.result.textContent = info.result;

    const alt = [];
    const speed = [];
    for (let i = 0; i < SPARK_POINTS; i++) {
      const t = phase.t_start + (i / (SPARK_POINTS - 1)) * (phase.t_end - phase.t_start);
      const tm = telemetry(hermiteState(samples, t), frames.moonPosition(t), frames, bodies);
      alt.push(tm.alt);
      speed.push(tm.speed);
    }
    drawSpark(dom.sparkAlt, alt, color);
    drawSpark(dom.sparkSpeed, speed, color);
  }

  /** st: estado ECI interpolado; moonPos: posición ECI de la Luna. */
  function update(t, st, phase, moonPos, frameName, vehicle, landed) {
    if (phase.id !== phaseId) showPhase(phase);
    const tm = telemetry(st, moonPos, frames, bodies);
    const body = tm.nearMoon ? "Luna" : "Tierra";
    dom.met.textContent = formatMET(t);
    dom.phase.textContent = landed ? "En la superficie lunar" : phase.name;
    dom.vehicle.textContent = vehicle.name;
    dom.altLabel.textContent = `Altitud (${body})`;
    dom.alt.textContent = formatAltitude(tm.alt, fmt);
    dom.speedLabel.textContent = tm.nearMoon ? "Velocidad (rel. Luna)" : "Velocidad (inercial)";
    dom.speed.textContent = formatSpeed(tm.speed, fmt);
    const descending = phase.id === "landing";
    dom.rates.hidden = !descending;
    if (descending) {
      dom.vertical.textContent = formatSpeed(tm.vertical, fmt);
      dom.horizontal.textContent = formatSpeed(tm.horizontal, fmt);
    }
    dom.mass.textContent = `${fmt(st.m, 1)} t`;
    dom.frame.textContent = frameName;

    const u = (t - phase.t_start) / (phase.t_end - phase.t_start);
    dom.cursor.forEach((c) => (c.style.left = `${Math.min(Math.max(u, 0), 1) * 100}%`));

    const spent = dvSpent(budget, t);
    dom.dvSpent.textContent = `${fmt(spent, 0)} / ${fmt(total, 0)} m/s`;
    budget.forEach((b, i) => {
      const f = t < b.t ? 0 : b.end ? Math.min((t - b.t) / (b.end - b.t), 1) : 1;
      fills[i].style.width = `${f * 100}%`;
      rows[i].classList.toggle("done", f > 0);
    });
  }

  /** Las gráficas se dibujan con el tamaño del panel: hay que repetirlas si estaba oculto. */
  const redraw = () => (phaseId = null);
  window.addEventListener("resize", redraw);

  return { update, redraw, fmt, total };
}
