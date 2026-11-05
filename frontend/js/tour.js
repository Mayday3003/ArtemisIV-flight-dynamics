// Modo presentación: recorre la misión de principio a fin con una toma de cámara por fase.
// Módulo puro (sin DOM ni Three.js) para poder probarlo con node --test.

/** Cámara del lado del Sol (+x en ECI), para no ver el lado nocturno. */
export const SUNLIT = [0.82, -0.5, 0.3];

/**
 * Toma por fase: marco, cuerpo enfocado y distancia de cámara en unidades de escena (1 000 km).
 * `view: "horizon"` pone la cámara rasante sobre el cuerpo más cercano. La velocidad la da el
 * modo Auto de la línea de tiempo. Fases sin toma usan DEFAULT_SHOT.
 */
export const TOUR_SHOTS = {
  ascent: { frame: "eci", focus: "ship", distance: 1.6, view: "horizon" },
  parking: { frame: "eci", focus: "earth", distance: 22, dir: SUNLIT },
  transit: { frame: "rot", focus: "system", distance: 620, dir: [0.1, -0.62, 0.78] },
  nrho: { frame: "rot", focus: "moon", distance: 170, dir: [0.92, -0.38, 0.08] },
  descent: { frame: "moon", focus: "moon", distance: 9, dir: [0.8, -0.45, -0.4] },
  landing: { frame: "moon", focus: "ship", distance: 0.7, view: "horizon" },
};
export const DEFAULT_SHOT = { frame: "eci", focus: "ship", distance: 3 };

/** Índice de la fase que contiene t (la última si t está más allá del final). */
export function phaseIndexAt(phases, t) {
  const i = phases.findIndex((p) => t < p.t_end);
  return i < 0 ? phases.length - 1 : i;
}

/** Toma de cámara para el instante t. */
export function shotAt(phases, t) {
  return TOUR_SHOTS[phases[phaseIndexAt(phases, t)].id] ?? DEFAULT_SHOT;
}

/**
 * Controlador del recorrido. `apply(shot)` cambia marco, foco y cámara;
 * se llama al empezar y cada vez que se entra en una fase nueva.
 */
export function createTour(phases, apply) {
  let active = false;
  let current = -1;

  return {
    get active() {
      return active;
    },
    start() {
      active = true;
      current = -1;
    },
    stop() {
      active = false;
    },
    /** Da por aplicada la toma de la fase de t, para que no pise una toma de evento. */
    sync(t) {
      current = phaseIndexAt(phases, t);
    },
    /** Llamar en cada cuadro; devuelve true si cambió de toma. */
    update(t) {
      if (!active) return false;
      const i = phaseIndexAt(phases, t);
      if (i === current) return false;
      current = i;
      apply(shotAt(phases, t), phases[i]);
      return true;
    },
  };
}
