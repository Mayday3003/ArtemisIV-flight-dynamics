import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { createFrames } from "../js/frames.js";
import { densify, hermiteState, toTypedSamples } from "../js/interpolate.js";
import { AUTO_RATE, PHASE_INFO, RESULTS, dvBudget, dvSpent, eventInfo, vehicleAt } from "../js/story.js";
import { telemetry } from "../js/telemetry.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const mission = read("../data/mission.json");
const results = read("../../docs/figures/results.json").mission;

test("RESULTS coincide con docs/figures/results.json", () => {
  for (const [k, v] of Object.entries(RESULTS)) assert.equal(v, results[k], k);
});

test("cada fase tiene ciencia y velocidad automática, y cada evento su tarjeta", () => {
  for (const p of mission.phases) {
    assert.ok(PHASE_INFO[p.id], p.id);
    assert.ok(AUTO_RATE[p.id], p.id);
  }
  for (const e of mission.events) assert.ok(eventInfo(e.label).text, e.label);
});

test("el vehículo cambia en las separaciones", () => {
  assert.equal(vehicleAt(0, mission.events).id, "sls");
  assert.equal(vehicleAt(1000, mission.events).id, "eus");
  assert.equal(vehicleAt(500000, mission.events).id, "orion");
  assert.equal(vehicleAt(1402000, mission.events).id, "hls");
});

test("el Δv acumulado llega al total al alunizar", () => {
  const budget = dvBudget(mission.events);
  const total = budget.reduce((s, b) => s + b.dv, 0);
  assert.equal(dvSpent(budget, 0), 0);
  assert.ok(Math.abs(dvSpent(budget, 1e9) - total) < 1e-9);
});

test("la telemetría al alunizar reproduce el contacto a ~1 m/s", () => {
  const s = toTypedSamples(mission.samples);
  const frames = createFrames(mission.bodies.moon);
  const t = s.t[s.n - 1];
  const tm = telemetry(hermiteState(s, t), frames.moonPosition(t), frames, mission.bodies);
  assert.ok(tm.nearMoon);
  assert.ok(Math.abs(tm.speed * 1000 - RESULTS.touchdown_speed_ms) < 0.2, `${tm.speed * 1000} m/s`);
  assert.ok(tm.alt < 0.01);
});

test("densify conserva extremos y orden temporal", () => {
  const s = toTypedSamples(mission.samples);
  const d = densify(s);
  assert.ok(d.n >= s.n);
  assert.equal(d.t[0], s.t[0]);
  assert.equal(d.t[d.n - 1], s.t[s.n - 1]);
  for (let i = 1; i < d.n; i++) assert.ok(d.t[i] >= d.t[i - 1]);
});

test("al terminar la reproducción el reloj se queda en el alunizaje", async () => {
  const { createTimeline } = await import("../js/timeline.js");
  const el = () => ({
    style: {}, dataset: {}, appendChild() {}, addEventListener() {}, setAttribute() {}, offsetWidth: 10, clientWidth: 100,
  });
  globalThis.document = { createElement: el };
  globalThis.window = { addEventListener() {} };
  const dom = { track: el(), tags: el(), names: el(), curtain: el(), slider: el(), play: el() };
  const state = { t: 0, playing: false, speedIndex: 0 };
  const timeline = createTimeline(dom, mission, state, { cross() {}, jump() {} });
  timeline.seek(timeline.tEnd - 1);
  timeline.togglePlay();
  timeline.tick(1);
  assert.equal(state.t, timeline.tEnd);
  assert.equal(state.playing, false);
});
