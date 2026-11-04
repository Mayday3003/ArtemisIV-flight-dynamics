// Contenido narrativo de la misión: vehículos, ciencia por fase, tarjetas de evento y
// presupuesto de Δv. Módulo puro. RESULTS copia docs/figures/results.json; tests/story.test.mjs
// falla si las dos fuentes se separan.

import { SUNLIT } from "./tour.js";

export const RESULTS = {
  dv_insertion_ms: 1200.4742863813735,
  dv_tli_ms: 3246.700784983657,
  dv_opf_ms: 291.3410215896104,
  dv_nri_ms: 172.34603111055455,
  dv_doi_ms: 701.6533740151943,
  dv_powered_ms: 2297.21691785107,
  touchdown_speed_ms: 1.0030018378838763,
  landing_error_m: 0.013516691062196726,
  hls_mass_landed_t: 154.4375295363584,
  mission_days: 16.231407385648602,
  site_lat_deg: -86.8,
};

/** Multiplicador del modo Auto: cada fase dura unos 20–35 s de reproducción. */
export const AUTO_RATE = { ascent: 20, parking: 300, transit: 15000, nrho: 40000, descent: 300, landing: 20 };

export const PHASE_INFO = {
  ascent: {
    short: "Ascenso",
    physics: "Empuje, arrastre con Cd(Mach) y masa variable sobre una Tierra en rotación.",
    method: "Dormand–Prince RK45 con eventos",
    result: "Max-Q 27,5 kPa · MECO a 160 km",
  },
  parking: {
    short: "Aparcamiento",
    physics: "Órbita baja mientras llega la ventana de inyección hacia la Luna.",
    method: "Velocity Verlet (simpléctico)",
    result: "Inclinación 29,8° · TLI a las 2,33 h",
  },
  transit: {
    short: "Tránsito",
    physics: "Problema restringido de tres cuerpos, con sobrevuelo lunar propulsado.",
    method: "Disparo múltiple + SLSQP",
    result: "Sobrevuelo a 1 340 km · 55,7 % del Δv de Orion",
  },
  nrho: {
    short: "NRHO",
    physics: "Órbita periódica de halo cerca de L2 en el CR3BP, usando la matriz de transición de estados.",
    method: "Corrección diferencial + continuación",
    result: "NRHO 9:2 · periodo 6,56 d · perilunio 3 248 km",
  },
  descent: {
    short: "Órbita HLS",
    physics: "Elipse hasta 15 km de altitud bajo la gravedad GRGM1200A de grado 100 (mascons).",
    method: "DOP853 con eventos",
    result: "DOI 702 m/s · 1,59 h de planeo",
  },
  landing: {
    short: "Descenso",
    physics: "Descenso propulsado con masa variable en el marco fijo a la Luna.",
    method: "DOP853 + E-guidance",
    result: "Contacto a 1,0 m/s y a 1,4 cm del sitio",
  },
};

/** Vehículo activo, por hora de misión. `until` usa los eventos reales de separación. */
export function vehicleAt(t, events) {
  const at = (re) => events.find((e) => re.test(e.label))?.t ?? Infinity;
  if (t < at(/SRB/)) return { id: "sls", name: "SLS Block 1B + Orion" };
  if (t < at(/MECO/)) return { id: "core", name: "Etapa central + EUS + Orion" };
  if (t < at(/TLI/)) return { id: "eus", name: "EUS + Orion" };
  if (t < at(/DOI/)) return { id: "orion", name: "Orion" };
  return { id: "hls", name: "HLS (módulo lunar)" };
}

const SHIP = { frame: "eci", focus: "ship" };
const LANDING = { frame: "moon", focus: "ship", view: "horizon" };

const EVENT_INFO = [
  [/Max-Q/, { short: "Max-Q", text: "Máxima presión dinámica: 27,5 kPa. Es el momento de mayor carga aerodinámica sobre el cohete.", shot: { ...SHIP, distance: 0.6, view: "horizon" } }],
  [/SRB/, { short: "SRB", text: "Los dos propulsores sólidos agotan su combustible y se separan. El vehículo pierde masa de golpe.", shot: { ...SHIP, distance: 0.6, view: "horizon" } }],
  [/MECO|Inserción en órbita/, { short: "MECO", text: "Se apaga la etapa central y la EUS inserta a Orion en la órbita de aparcamiento.", dv: "dv_insertion_ms", shot: { frame: "eci", focus: "earth", distance: 22, dir: SUNLIT } }],
  [/TLI/, { short: "TLI", text: "La EUS impulsa a Orion hacia la Luna y se separa. A partir de aquí, Orion vuela solo.", dv: "dv_tli_ms", shot: { frame: "eci", focus: "earth", distance: 60, dir: SUNLIT } }],
  [/OPF/, { short: "OPF", text: "Orion enciende su motor a 1 340 km sobre la Luna y aprovecha su gravedad para llegar a la NRHO.", dv: "dv_opf_ms", shot: { frame: "rot", focus: "moon", distance: 30 } }],
  [/NRI/, { short: "NRI", text: "Orion frena y queda en la órbita de Gateway, una NRHO 9:2 sincronizada con la Luna.", dv: "dv_nri_ms", shot: { frame: "rot", focus: "moon", distance: 170, dir: [0.92, -0.38, 0.08] } }],
  [/DOI/, { short: "DOI", text: "El HLS deja la NRHO, poco antes del perilunio, hacia una elipse que baja a 15 km. La masa mostrada pasa a ser la del HLS.", dv: "dv_doi_ms", shot: { frame: "moon", focus: "moon", distance: 9, dir: [0.8, -0.45, -0.4] } }],
  [/PDI/, { short: "PDI", text: "Empieza el descenso propulsado con E-guidance: 700 s de motor, con un máximo de 87 % de empuje.", dv: "dv_powered_ms", shot: { ...LANDING, distance: 0.8 } }],
  [/High gate/, { short: "High gate", text: "Termina el frenado y empieza la aproximación al sitio.", shot: { ...LANDING, distance: 0.3 } }],
  [/Low gate/, { short: "Low gate", text: "A 100 m sobre el sitio comienza el descenso vertical, que termina a 1 m/s.", shot: { ...LANDING, distance: 0.3 } }],
  [/Alunizaje/, { short: "Contacto", text: "Contacto con la superficie en la región polar sur.", shot: { ...LANDING, distance: 0.3 } }],
];

export function eventInfo(label) {
  return EVENT_INFO.find(([re]) => re.test(label))?.[1] ?? { short: label, text: "", shot: null };
}

/** Maniobras del presupuesto de Δv, en orden; `end` indica un encendido largo. */
export function dvBudget(events) {
  const at = (re) => events.find((e) => re.test(e.label))?.t ?? Infinity;
  return [
    { name: "Inserción", dv: RESULTS.dv_insertion_ms, t: at(/Inserción en órbita/) },
    { name: "TLI", dv: RESULTS.dv_tli_ms, t: at(/TLI/) },
    { name: "OPF", dv: RESULTS.dv_opf_ms, t: at(/OPF/) },
    { name: "NRI", dv: RESULTS.dv_nri_ms, t: at(/NRI/) },
    { name: "DOI", dv: RESULTS.dv_doi_ms, t: at(/DOI/) },
    { name: "Descenso", dv: RESULTS.dv_powered_ms, t: at(/PDI/), end: at(/Alunizaje/) },
  ];
}

/** Δv gastado hasta t (m/s): los impulsos cuentan enteros y el descenso crece linealmente. */
export function dvSpent(budget, t) {
  return budget.reduce((sum, b) => {
    if (t < b.t) return sum;
    return sum + (b.end ? b.dv * Math.min((t - b.t) / (b.end - b.t), 1) : b.dv);
  }, 0);
}
