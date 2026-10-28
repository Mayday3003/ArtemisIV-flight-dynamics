// Trayectoria coloreada por fase, con "origen flotante": las coordenadas del marco se
// guardan en Float64 y en cada cuadro se resta el cuerpo enfocado antes de pasarlas a Float32.
import * as THREE from "three";

import { PHASE_COLORS } from "./palette.js";
import { KM_PER_UNIT } from "./scene.js";
const FALLBACK = "#cccccc";

export function createTrajectory(scene, samples, phases, frames) {
  const n = samples.n;
  const frameCoords = new Float64Array(3 * n);
  let cachedFrame = null;

  const position = new THREE.BufferAttribute(new Float32Array(3 * n), 3);
  position.setUsage(THREE.DynamicDrawUsage);

  const colors = new Float32Array(3 * n);
  const c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    c.set(PHASE_COLORS[phases[samples.phase[i]]?.id] ?? FALLBACK);
    colors.set([c.r, c.g, c.b], 3 * i);
  }
  const color = new THREE.BufferAttribute(colors, 3);

  // Dos geometrías que comparten los mismos atributos: recorrido completo tenue y tramo
  // ya volado brillante (cada una con su propio drawRange).
  const make = (opacity) => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", position);
    geo.setAttribute("color", color);
    const line = new THREE.Line(
      geo,
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: opacity < 1, opacity })
    );
    line.frustumCulled = false;
    scene.add(line);
    return line;
  };
  const future = make(0.3);
  const flown = make(1);

  /** Cada punto se transforma con SU instante: así se ve la trayectoria en el marco rotante. */
  function computeFrame(frame) {
    for (let i = 0; i < n; i++) {
      const r = frames.toFrame(frame, [samples.x[i], samples.y[i], samples.z[i]], samples.t[i]);
      frameCoords.set(r, 3 * i);
    }
    cachedFrame = frame;
  }

  /** focus: posición (km, en el marco) que queda en el origen de la escena. */
  function update(frame, focus, segment, shipPos) {
    if (frame !== cachedFrame) computeFrame(frame);
    const a = position.array;
    for (let i = 0; i < 3 * n; i += 3) {
      a[i] = (frameCoords[i] - focus[0]) / KM_PER_UNIT;
      a[i + 1] = (frameCoords[i + 1] - focus[1]) / KM_PER_UNIT;
      a[i + 2] = (frameCoords[i + 2] - focus[2]) / KM_PER_UNIT;
    }
    // La nave reemplaza a la muestra k+1: el tramo volado termina en ella y el futuro empieza ahí
    const j = Math.min(segment + 1, n - 1);
    a[3 * j] = (shipPos[0] - focus[0]) / KM_PER_UNIT;
    a[3 * j + 1] = (shipPos[1] - focus[1]) / KM_PER_UNIT;
    a[3 * j + 2] = (shipPos[2] - focus[2]) / KM_PER_UNIT;
    position.needsUpdate = true;
    flown.geometry.setDrawRange(0, j + 1);
    future.geometry.setDrawRange(j, n - j);
  }

  function setVisible(v) {
    future.visible = v;
    flown.visible = v;
  }

  return { update, setVisible };
}

/** Círculo de la órbita lunar (se transforma al marco con el instante actual). */
export function createMoonOrbit(scene, frames, segments = 256) {
  const eci = [];
  for (let i = 0; i <= segments; i++) {
    const t = (i / segments) * (2 * Math.PI) / frames.meanMotion;
    eci.push(frames.moonPosition(t));
  }
  const attr = new THREE.BufferAttribute(new Float32Array(3 * eci.length), 3);
  attr.setUsage(THREE.DynamicDrawUsage);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", attr);
  const line = new THREE.LineLoop(
    geo,
    new THREE.LineBasicMaterial({ color: 0x8892a6, transparent: true, opacity: 0.35 })
  );
  line.frustumCulled = false;
  scene.add(line);

  function update(frame, t, focus) {
    for (let i = 0; i < eci.length; i++) {
      const r = frames.toFrame(frame, eci[i], t);
      attr.array[3 * i] = (r[0] - focus[0]) / KM_PER_UNIT;
      attr.array[3 * i + 1] = (r[1] - focus[1]) / KM_PER_UNIT;
      attr.array[3 * i + 2] = (r[2] - focus[2]) / KM_PER_UNIT;
    }
    attr.needsUpdate = true;
  }
  return { line, update };
}

/** NRHO de Gateway: dada en el marco rotante, se lleva a ECI con el instante actual. */
export function createNrho(scene, frames, nrho) {
  const n = nrho.x.length;
  const attr = new THREE.BufferAttribute(new Float32Array(3 * n), 3);
  attr.setUsage(THREE.DynamicDrawUsage);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", attr);
  const line = new THREE.LineLoop(geo, new THREE.LineBasicMaterial({ color: 0x7cf29a }));
  line.frustumCulled = false;
  scene.add(line);

  function update(frame, t, focus) {
    for (let i = 0; i < n; i++) {
      const r = frames.toFrame(frame, frames.fromRotating([nrho.x[i], nrho.y[i], nrho.z[i]], t), t);
      attr.array[3 * i] = (r[0] - focus[0]) / KM_PER_UNIT;
      attr.array[3 * i + 1] = (r[1] - focus[1]) / KM_PER_UNIT;
      attr.array[3 * i + 2] = (r[2] - focus[2]) / KM_PER_UNIT;
    }
    attr.needsUpdate = true;
  }
  return { line, update };
}
