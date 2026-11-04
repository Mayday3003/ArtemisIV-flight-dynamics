// Trayectoria coloreada por fase, con "origen flotante": las coordenadas del marco se
// guardan en Float64 y en cada cuadro se resta el cuerpo enfocado antes de pasarlas a Float32.
import * as THREE from "three";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";

import { findSegment } from "./interpolate.js";
import { PHASE_COLORS } from "./palette.js";
import { KM_PER_UNIT } from "./scene.js";
const FALLBACK = "#cccccc";
const FUTURE_DIM = 0.28; // brillo del tramo aún no volado

const materials = new Set();

/** LineMaterial mide el grosor en píxeles: necesita el tamaño del lienzo. */
export function setLineResolution(width, height) {
  for (const m of materials) m.resolution.set(width, height);
  setLineResolution.size = [width, height];
}

/** Polilínea gruesa de `count` puntos con búfer dinámico. */
function fatPath(scene, count, { width, color, opacity = 1, vertexColors = false }) {
  const geo = new LineSegmentsGeometry();
  geo.setPositions(new Float32Array(6 * (count - 1)));
  if (vertexColors) geo.setColors(new Float32Array(6 * (count - 1)));
  const material = new LineMaterial({ linewidth: width, vertexColors, transparent: opacity < 1, opacity });
  if (color !== undefined) material.color.set(color);
  materials.add(material);
  if (setLineResolution.size) material.resolution.set(...setLineResolution.size);
  const line = new LineSegments2(geo, material);
  line.frustumCulled = false;
  scene.add(line);

  const pos = geo.attributes.instanceStart.data;
  pos.setUsage(THREE.DynamicDrawUsage);
  const array = pos.array;

  /** Escribe el punto i: es el final del tramo i−1 y el inicio del tramo i. */
  function setPoint(i, x, y, z) {
    if (i > 0) {
      const a = 6 * i - 3;
      array[a] = x;
      array[a + 1] = y;
      array[a + 2] = z;
    }
    if (i < count - 1) {
      const b = 6 * i;
      array[b] = x;
      array[b + 1] = y;
      array[b + 2] = z;
    }
  }
  return { line, geo, setPoint, commit: () => (pos.needsUpdate = true) };
}

/** `path`: puntos de densify() para dibujar. */
export function createTrajectory(scene, path, phases, frames) {
  const n = path.n;
  const frameCoords = new Float64Array(3 * n);
  let cachedFrame = null;
  let drawnSegment = -1;

  const fat = fatPath(scene, n, { width: 2, vertexColors: true });
  const colorBuffer = fat.geo.attributes.instanceColorStart.data;
  colorBuffer.setUsage(THREE.DynamicDrawUsage);
  const base = new Float32Array(3 * n);
  const c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    c.set(PHASE_COLORS[phases[path.phase[i]]?.id] ?? FALLBACK);
    base.set([c.r, c.g, c.b], 3 * i);
  }

  function paint(from, to, flown) {
    const f = flown ? 1 : FUTURE_DIM;
    for (let i = from; i < to; i++) {
      for (let k = 0; k < 3; k++) {
        colorBuffer.array[6 * i + k] = base[3 * i + k] * f;
        colorBuffer.array[6 * i + 3 + k] = base[3 * (i + 1) + k] * f;
      }
    }
    colorBuffer.needsUpdate = true;
  }
  paint(0, n - 1, false);

  /** Cada punto se transforma con SU instante: así se ve la trayectoria en el marco rotante. */
  function computeFrame(frame) {
    for (let i = 0; i < n; i++) {
      const r = frames.toFrame(frame, [path.x[i], path.y[i], path.z[i]], path.t[i]);
      frameCoords.set(r, 3 * i);
    }
    cachedFrame = frame;
  }

  /** focus: posición (km, en el marco) que queda en el origen de la escena. */
  function update(frame, focus, t, shipPos) {
    if (frame !== cachedFrame) computeFrame(frame);
    for (let i = 0; i < n; i++) {
      fat.setPoint(
        i,
        (frameCoords[3 * i] - focus[0]) / KM_PER_UNIT,
        (frameCoords[3 * i + 1] - focus[1]) / KM_PER_UNIT,
        (frameCoords[3 * i + 2] - focus[2]) / KM_PER_UNIT
      );
    }
    // La nave reemplaza a la muestra k+1: el tramo volado termina justo en ella
    const k = findSegment(path.t, t);
    fat.setPoint(
      k + 1,
      (shipPos[0] - focus[0]) / KM_PER_UNIT,
      (shipPos[1] - focus[1]) / KM_PER_UNIT,
      (shipPos[2] - focus[2]) / KM_PER_UNIT
    );
    fat.commit();
    if (k > drawnSegment) paint(Math.max(drawnSegment, 0), k + 1, true);
    else if (k < drawnSegment) paint(k + 1, drawnSegment + 1, false);
    drawnSegment = k;
  }

  return { update, setVisible: (v) => (fat.line.visible = v) };
}

/** Círculo de la órbita lunar (se transforma al marco con el instante actual). */
export function createMoonOrbit(scene, frames, segments = 256) {
  const eci = [];
  for (let i = 0; i <= segments; i++) {
    const t = (i / segments) * (2 * Math.PI) / frames.meanMotion;
    eci.push(frames.moonPosition(t));
  }
  const fat = fatPath(scene, eci.length, { width: 1, color: 0x8892a6, opacity: 0.4 });

  function update(frame, t, focus) {
    for (let i = 0; i < eci.length; i++) {
      const r = frames.toFrame(frame, eci[i], t);
      fat.setPoint(i, (r[0] - focus[0]) / KM_PER_UNIT, (r[1] - focus[1]) / KM_PER_UNIT, (r[2] - focus[2]) / KM_PER_UNIT);
    }
    fat.commit();
  }
  return { line: fat.line, update };
}

/** NRHO de Gateway: dada en el marco rotante, se lleva a ECI con el instante actual. */
export function createNrho(scene, frames, nrho) {
  const points = nrho.x.map((x, i) => new THREE.Vector3(x, nrho.y[i], nrho.z[i]));
  // Las muestras son uniformes en tiempo y quedan muy separadas en el perilunio: se suaviza
  const smooth = new THREE.CatmullRomCurve3(points, true, "centripetal").getPoints(4 * points.length);
  const fat = fatPath(scene, smooth.length, { width: 1.5, color: 0x7cf29a, opacity: 0.5 });

  function update(frame, t, focus) {
    smooth.forEach((p, i) => {
      const r = frames.toFrame(frame, frames.fromRotating([p.x, p.y, p.z], t), t);
      fat.setPoint(i, (r[0] - focus[0]) / KM_PER_UNIT, (r[1] - focus[1]) / KM_PER_UNIT, (r[2] - focus[2]) / KM_PER_UNIT);
    });
    fat.commit();
  }
  return { line: fat.line, update };
}
