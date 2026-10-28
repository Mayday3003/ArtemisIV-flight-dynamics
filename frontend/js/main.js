// Arranque del visualizador: carga mission.json, arma la escena y conecta la interfaz.
import * as THREE from "three";

import { FRAMES, createFrames } from "./frames.js";
import { createHud } from "./hud.js";
import { hermiteState, toTypedSamples } from "./interpolate.js";
import { KM_PER_UNIT, createScene, mul3, rotZ, setMatrix } from "./scene.js";
import { createTimeline } from "./timeline.js";
import { createMoonOrbit, createNrho, createTrajectory } from "./trajectory.js";

const $ = (id) => document.getElementById(id);
const SUN_DIR_ECI = [1, 0, 0]; // dirección fija del Sol (solo para iluminar)

/** Distancia de cámara al cambiar de foco (unidades de escena = 1 000 km). */
const FOCUS_DISTANCE = { earth: 30, moon: 9, ship: 3 };

async function main() {
  const res = await fetch("data/mission.json");
  if (!res.ok) throw new Error(`No se pudo cargar data/mission.json (${res.status})`);
  const mission = await res.json();
  if (mission.schema_version !== 1) throw new Error(`Versión de formato no soportada: ${mission.schema_version}`);

  const samples = toTypedSamples(mission.samples);
  const frames = createFrames(mission.bodies.moon);
  const omegaEarth = mission.bodies.earth.rotation_rate_rad_s;

  const view = createScene($("viewport"), mission.bodies);
  const { scene, camera, controls, renderer } = view;

  const trajectory = createTrajectory(scene, samples, mission.phases, frames);
  const moonOrbit = createMoonOrbit(scene, frames);
  const nrho = mission.nrho ? createNrho(scene, frames, mission.nrho) : null;

  // LC-39B: fijo a la Tierra (en t = 0 el marco terrestre coincide con ECI)
  const pad = new THREE.Mesh(new THREE.SphereGeometry(0.003, 12, 8), new THREE.MeshBasicMaterial({ color: 0xe8702a }));
  pad.position.set(samples.x[0], samples.y[0], samples.z[0]).divideScalar(KM_PER_UNIT);
  view.earth.add(pad);

  const ship = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: dotTexture(), sizeAttenuation: false, depthTest: false })
  );
  ship.scale.setScalar(0.018);
  ship.renderOrder = 10;
  scene.add(ship);

  const velocity = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 1, 0x7cf29a);
  scene.add(velocity);

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const state = { t: 0, playing: false, speedIndex: 1, frame: "eci", focus: "ship" };

  const hud = createHud(
    {
      met: $("hud-met"), phase: $("hud-phase"), alt: $("hud-alt"), altLabel: $("hud-alt-label"),
      distMoon: $("hud-dist-moon"), speed: $("hud-speed"), mass: $("hud-mass"), frame: $("hud-frame"),
      toast: $("toast"),
    },
    mission.bodies
  );
  const timeline = createTimeline(
    { track: $("track"), slider: $("slider"), play: $("play"), speed: $("speed") },
    mission,
    state,
    (label) => hud.toast(label)
  );

  // --- Controles -----------------------------------------------------------------------
  const frameSelect = $("frame");
  frameSelect.innerHTML = Object.entries(FRAMES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  frameSelect.addEventListener("change", () => (state.frame = frameSelect.value));

  const focusSelect = $("focus");
  focusSelect.addEventListener("change", () => setFocus(focusSelect.value));

  function setFocus(key) {
    state.focus = key;
    focusSelect.value = key;
    const dist = key === "ship" && state.t < mission.phases[0].t_end ? 0.6 : FOCUS_DISTANCE[key];
    const dir = camera.position.clone().sub(controls.target);
    if (dir.lengthSq() === 0) dir.set(1, -1, 0.5);
    controls.target.set(0, 0, 0);
    camera.position.copy(dir.normalize().multiplyScalar(dist));
  }

  const layers = {
    "layer-trajectory": (v) => trajectory.setVisible(v),
    "layer-moon-orbit": (v) => (moonOrbit.line.visible = v),
    "layer-nrho": (v) => nrho && (nrho.line.visible = v),
    "layer-velocity": (v) => (velocity.visible = v),
    "layer-stars": (v) => (view.stars.visible = v),
    "layer-axes": (v) => (view.axes.visible = v),
  };
  for (const [id, apply] of Object.entries(layers)) {
    const box = $(id);
    apply(box.checked);
    box.addEventListener("change", () => apply(box.checked));
  }

  const help = $("help");
  $("help-btn").addEventListener("click", () => help.showModal());
  $("help-close").addEventListener("click", () => help.close());

  const reduce = $("reduce-motion");
  reduce.checked = reducedMotion;
  const applyReduce = () => (controls.enableDamping = !reduce.checked);
  reduce.addEventListener("change", applyReduce);
  applyReduce();

  window.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    const actions = {
      " ": () => timeline.togglePlay(),
      ArrowRight: () => timeline.jumpEvent(1),
      ArrowLeft: () => timeline.jumpEvent(-1),
      ArrowUp: () => timeline.setSpeed(1),
      ArrowDown: () => timeline.setSpeed(-1),
      "+": () => timeline.setSpeed(1),
      "-": () => timeline.setSpeed(-1),
      1: () => setFrame("eci"),
      2: () => setFrame("rot"),
      3: () => setFrame("moon"),
      n: () => setFocus("ship"),
      t: () => setFocus("earth"),
      l: () => setFocus("moon"),
      h: () => (help.open ? help.close() : help.showModal()),
    };
    const fn = actions[e.key.length === 1 ? e.key.toLowerCase() : e.key];
    if (fn) {
      e.preventDefault();
      fn();
    }
  });

  function setFrame(key) {
    state.frame = key;
    frameSelect.value = key;
  }

  // --- Bucle ---------------------------------------------------------------------------
  const m4 = new THREE.Matrix4();
  const tmp = new THREE.Vector3();
  let last = performance.now();
  setFocus("ship");
  if (!reducedMotion) timeline.togglePlay();
  $("loading").remove();

  function frameLoop(now) {
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    timeline.tick(dt);

    const { t, frame } = state;
    const st = hermiteState(samples, t);
    const moonEci = frames.moonPosition(t);
    const shipF = frames.toFrame(frame, st.r, t);
    const moonF = frames.toFrame(frame, moonEci, t);
    const earthF = frames.toFrame(frame, [0, 0, 0], t);
    const focus = { ship: shipF, earth: earthF, moon: moonF }[state.focus];
    const rel = (p) => tmp.set((p[0] - focus[0]) / KM_PER_UNIT, (p[1] - focus[1]) / KM_PER_UNIT, (p[2] - focus[2]) / KM_PER_UNIT);

    const M = frames.matrix(frame, t);
    rel(earthF);
    setMatrix(view.earth.matrix, mul3(M, rotZ(omegaEarth * t)), tmp.x, tmp.y, tmp.z);
    view.earth.matrixWorldNeedsUpdate = true;
    view.moon.position.copy(rel(moonF));
    ship.position.copy(rel(shipF));
    view.axes.position.copy(rel(earthF));
    view.axes.setRotationFromMatrix(m4.set(M[0], M[1], M[2], 0, M[3], M[4], M[5], 0, M[6], M[7], M[8], 0, 0, 0, 0, 1));

    const v = frames.directionToFrame(frame, st.v, t);
    velocity.position.copy(ship.position);
    velocity.setDirection(tmp.set(v[0], v[1], v[2]).normalize());
    const camDist = camera.position.distanceTo(controls.target);
    velocity.setLength(camDist * 0.15, camDist * 0.03, camDist * 0.015);

    const sun = frames.directionToFrame(frame, SUN_DIR_ECI, t);
    view.sun.position.set(sun[0], sun[1], sun[2]).multiplyScalar(100);

    trajectory.update(frame, focus, st.k, shipF);
    moonOrbit.update(frame, t, focus);
    if (nrho?.line.visible) nrho.update(frame, t, focus);
    view.stars.position.copy(camera.position);

    const phase = mission.phases[samples.phase[st.k + 1 < samples.n && samples.t[st.k + 1] <= t ? st.k + 1 : st.k]];
    hud.update(t, st, phase.name, moonEci, FRAMES[frame]);

    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(frameLoop);
  }
  requestAnimationFrame(frameLoop);
}

function dotTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = "#ffffff";
  g.beginPath();
  g.arc(32, 32, 22, 0, 2 * Math.PI);
  g.fill();
  g.lineWidth = 6;
  g.strokeStyle = "#e8702a";
  g.stroke();
  return new THREE.CanvasTexture(c);
}

main().catch((err) => {
  console.error(err);
  const box = $("loading");
  if (box) {
    box.textContent = `Error: ${err.message}. Sirve la carpeta frontend/ con un servidor local (ver README).`;
    box.classList.add("error");
  }
});
