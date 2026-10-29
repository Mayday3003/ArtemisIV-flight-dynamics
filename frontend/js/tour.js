// Modo presentación: recorre la misión de principio a fin con una toma de cámara por fase.
// Módulo puro (sin DOM ni Three.js) para poder probarlo con node --test.

/**
 * Toma por fase: marco, cuerpo enfocado, índice de velocidad (en SPEEDS de timeline.js) y
 * distancia de cámara en unidades de escena (1 000 km). Fases sin toma usan DEFAULT_SHOT.
 */
export const TOUR_SHOTS = {
  ascent: { frame: "eci", focus: "ship", speed: 1, distance: 0.6 },
  parking: { frame: "eci", focus: "earth", speed: 3, distance: 20 },
  transit: { frame: "rot", focus: "earth", speed: 5, distance: 260 },
  nrho: { frame: "rot", focus: "moon", speed: 5, distance: 160 },
  descent: { frame: "moon", focus: "moon", speed: 3, distance: 9 },
  landing: { frame: "moon", focus: "ship", speed: 2, distance: 0.4 },
};
export const DEFAULT_SHOT = { frame: "eci", focus: "ship", speed: 3, distance: 3 };

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
 * Controlador del recorrido. `apply(shot)` cambia marco, foco, velocidad y cámara;
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
