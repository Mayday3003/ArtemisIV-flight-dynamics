import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_SHOT, TOUR_SHOTS, createTour, phaseIndexAt, shotAt } from "../js/tour.js";

const phases = [
  { id: "ascent", name: "Ascenso", t_start: 0, t_end: 480 },
  { id: "parking", name: "Aparcamiento", t_start: 480, t_end: 8000 },
  { id: "mystery", name: "Sin toma", t_start: 8000, t_end: 9000 },
];

test("phaseIndexAt localiza la fase y satura al final", () => {
  assert.equal(phaseIndexAt(phases, 0), 0);
  assert.equal(phaseIndexAt(phases, 479.9), 0);
  assert.equal(phaseIndexAt(phases, 480), 1);
  assert.equal(phaseIndexAt(phases, 1e9), 2);
});

test("shotAt usa la toma de la fase o la de respaldo", () => {
  assert.deepEqual(shotAt(phases, 10), TOUR_SHOTS.ascent);
  assert.deepEqual(shotAt(phases, 8500), DEFAULT_SHOT);
});

test("el recorrido aplica una toma solo al cambiar de fase y no actúa detenido", () => {
  const applied = [];
  const tour = createTour(phases, (shot, phase) => applied.push(phase.id));
  assert.equal(tour.update(0), false);
  tour.start();
  assert.equal(tour.update(0), true);
  assert.equal(tour.update(100), false);
  assert.equal(tour.update(600), true);
  tour.stop();
  assert.equal(tour.update(8500), false);
  assert.deepEqual(applied, ["ascent", "parking"]);
});

test("todas las fases de la misión real tienen toma", () => {
  for (const id of ["ascent", "parking", "transit", "nrho", "descent", "landing"]) assert.ok(TOUR_SHOTS[id], id);
});
