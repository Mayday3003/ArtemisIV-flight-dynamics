// Pruebas de los módulos puros del visualizador:  node --test frontend/tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { createFrames } from "../js/frames.js";
import { hermiteState, toTypedSamples } from "../js/interpolate.js";

const mission = JSON.parse(readFileSync(new URL("../data/mission.json", import.meta.url)));
const frames = createFrames(mission.bodies.moon);
const norm = (a) => Math.hypot(...a);
const sub = (a, b) => a.map((x, i) => x - b[i]);

test("en el marco rotante la Luna queda fija en (384,4 mil km; 0; 0)", () => {
  for (const t of [0, 1e5, 3.5e5, 2.4e6]) {
    const r = frames.toFrame("rot", frames.moonPosition(t), t);
    assert.ok(Math.abs(r[0] - 384400) < 1e-6, `x = ${r[0]}`);
    assert.ok(Math.abs(r[1]) < 1e-6 && Math.abs(r[2]) < 1e-6, `y, z = ${r[1]}, ${r[2]}`);
  }
});

test("el marco rotante conserva distancias (matriz ortonormal)", () => {
  const r = [12345, -67890, 4321];
  assert.ok(Math.abs(norm(frames.toFrame("rot", r, 7.7e4)) - norm(r)) < 1e-9);
});

test("en el marco selenocéntrico la Luna está en el origen", () => {
  assert.ok(norm(frames.toFrame("moon", frames.moonPosition(2e5), 2e5)) < 1e-9);
});

test("la interpolación JS coincide con Python en los puntos de control (< 1 m)", () => {
  const s = toTypedSamples(mission.samples);
  assert.ok(mission.checkpoints.length >= 5);
  for (const cp of mission.checkpoints) {
    const st = hermiteState(s, cp.t);
    const err = norm(sub(st.r, cp.r_km));
    assert.ok(err < 1e-3, `t = ${cp.t}: error ${(err * 1e3).toFixed(1)} m`);
  }
});

test("la interpolación es exacta en las muestras", () => {
  const s = toTypedSamples(mission.samples);
  for (const k of [0, 10, 500, s.n - 1]) {
    const st = hermiteState(s, s.t[k]);
    assert.ok(norm(sub(st.r, [s.x[k], s.y[k], s.z[k]])) < 1e-9);
  }
});

test("la escala de la línea de tiempo es monótona e invertible", async () => {
  const { createPhaseScale } = await import("../js/timeline.js");
  const scale = createPhaseScale(mission.phases);
  let prev = -1;
  for (const p of mission.phases) {
    for (const u of [0, 0.3, 0.7, 1]) {
      const t = p.t_start + u * (p.t_end - p.t_start);
      const f = scale.toFraction(t);
      assert.ok(f >= prev - 1e-12, `no monótona en t = ${t}`);
      prev = f;
      assert.ok(Math.abs(scale.toTime(f) - t) < 1e-6 * Math.max(1, t), `toTime(toFraction(${t}))`);
    }
  }
  assert.equal(scale.toFraction(0), 0);
  assert.ok(Math.abs(scale.toFraction(mission.phases.at(-1).t_end) - 1) < 1e-12);
});

test("fromRotating es la inversa del marco rotante y la NRHO rodea a la Luna", () => {
  const r = [380000, 12000, -50000];
  const back = frames.toFrame("rot", frames.fromRotating(r, 9.9e4), 9.9e4);
  assert.ok(norm(sub(back, r)) < 1e-6);
  const n = mission.nrho;
  const d = n.x.map((x, i) => Math.hypot(x - 384400, n.y[i], n.z[i]));
  assert.ok(Math.abs(Math.min(...d) - n.perilune_km) < 50, `perilunio ${Math.min(...d)}`);
  assert.ok(Math.abs(Math.max(...d) - n.apolune_km) < 50, `apolunio ${Math.max(...d)}`);
});
