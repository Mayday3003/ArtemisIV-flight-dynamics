// Genera la presentación Artemis_IV_UdeM.pptx a partir de las figuras y resultados del proyecto.
// Uso:
//   cd docs/presentation && npm install          (una sola vez; instala pptxgenjs)
//   npm run build
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const imageSize = require("image-size");

const ROOT = path.resolve(__dirname, "..", "..");
const A = (p) => path.join(ROOT, p);
const R = JSON.parse(fs.readFileSync(A("docs/figures/results.json"), "utf8"));
const OUT = A("docs/presentation/Artemis_IV_UdeM.pptx");

const THEME = {
  name: "Artemis UdeM",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1B1F", lt1: "FFFFFF", dk2: "0B1D3A", lt2: "EEF2F7",
    accent1: "E8702A", accent2: "2A78D6", accent3: "1BAF7A",
    accent4: "EDA100", accent5: "6250D6", accent6: "52514E",
    hlink: "2A78D6", folHlink: "6250D6",
  },
};
const NAVY = THEME.colors.dk2, ORANGE = THEME.colors.accent1, BLUE = THEME.colors.accent2;
const INK = "1B1B1F", MUTED = "52514E", TINT = "EEF2F7", CODEBG = "F1F3F6";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
pres.title = "Simulación dinámica multifase de la misión Artemis IV";
pres.author = "Mariana Lopera Correa, Juan José Becerra Bedoya, Daniel Santiago Machado";
pres.company = "Universidad de Medellín";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const W = 13.333, H = 7.5, MX = 0.6;
const LOGO = A("docs/paper/final/logo.png");

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "DARK",
  background: { color: NAVY },
  objects: [],
});
pres.defineSlideMaster({
  title: "SECTION",
  background: { color: NAVY },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 3.0, w: 8.2, h: 1.2, fontFace: THEME.headFontFace, fontSize: 40, bold: true, color: "FFFFFF", valign: "middle", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: MX, y: 4.2, w: 8.2, h: 1.2, fontFace: THEME.bodyFontFace, fontSize: 18, color: "CADCFC", valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: W - 1.0, y: H - 0.5, w: 0.6, h: 0.3, fontSize: 10, color: "CADCFC", align: "right" },
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    { image: { path: LOGO, x: W - 1.35, y: H - 0.62, w: 0.78, h: 0.48 } },
    { placeholder: { options: { name: "title", type: "title", x: MX, y: 0.35, w: W - 2 * MX, h: 0.8, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: NAVY, valign: "middle", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: MX, y: H - 0.5, w: 0.6, h: 0.3, fontSize: 10, color: MUTED, align: "left" },
});

// ---------------------------------------------------------------- helpers
function dims(p) {
  const { width, height } = imageSize(fs.readFileSync(p));
  return [width, height];
}
// Coloca una imagen ajustada (contain) dentro de la caja, centrada.
function fit(slide, p, x, y, w, h, extra = {}) {
  const [iw, ih] = dims(p);
  const s = Math.min(w / iw, h / ih);
  const ww = iw * s, hh = ih * s;
  slide.addImage({ path: p, x: x + (w - ww) / 2, y: y + (h - hh) / 2, w: ww, h: hh, ...extra });
  return { x: x + (w - ww) / 2, y: y + (h - hh) / 2, w: ww, h: hh };
}
const FIG = (n) => A(`docs/figures/${n}.png`);
const EQ = (n) => A(`docs/presentation/assets/${n}.png`);
const NASA = (n) => A(`docs/presentation/assets/${n}.jpg`);

// Ecuación: altura en pulgadas proporcional al render (fontsize 26 @220 dpi -> escala)
function eq(slide, name, x, y, maxW, scale = 1.0) {
  const [iw, ih] = dims(EQ(name));
  let w = (iw / 220) * 0.9 * scale, h = (ih / 220) * 0.9 * scale;
  if (w > maxW) { h *= maxW / w; w = maxW; }
  slide.addImage({ path: EQ(name), x, y, w, h });
  return h;
}

// Etiqueta de código: dónde vive la implementación
function codeTag(slide, lines, x, y, w) {
  const h = 0.22 + 0.27 * lines.length;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: CODEBG }, line: { color: "D5DAE1", width: 0.75 }, rectRadius: 0.08 });
  slide.addText(
    lines.map((l, i) => ({
      text: l,
      options: { fontFace: "Courier New", fontSize: 11.5, color: i === 0 ? MUTED : NAVY, bold: i !== 0, breakLine: i < lines.length - 1 },
    })),
    { x: x + 0.12, y, w: w - 0.24, h, valign: "middle", margin: 0, isTextBox: true },
  );
  return h;
}

function bullets(slide, items, x, y, w, h, size = 16) {
  slide.addText(
    items.map((it, i) => {
      const runs = Array.isArray(it) ? it : [{ text: it }];
      return runs.map((r, j) => ({
        text: r.text,
        options: {
          fontSize: size, color: INK, bold: !!r.bold,
          bullet: j === 0 ? true : undefined,
          paraSpaceAfter: 8,
          breakLine: j === runs.length - 1 && i < items.length - 1,
        },
      }));
    }).flat(),
    { x, y, w, h, valign: "top", margin: 0, isTextBox: true },
  );
}

function stat(slide, value, label, x, y, w, color = ORANGE) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.25, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.1 });
  slide.addText(value, { x, y: y + 0.08, w, h: 0.7, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color, align: "center", margin: 0, isTextBox: true });
  slide.addText(label, { x: x + 0.1, y: y + 0.76, w: w - 0.2, h: 0.45, fontSize: 15, color: MUTED, align: "center", fit: "shrink", margin: 0, isTextBox: true });
}

function credit(slide, text, x, y, w, color = MUTED) {
  slide.addText(text, { x, y, w, h: 0.25, fontSize: 10, italic: true, color, margin: 0, isTextBox: true });
}

function content(title) {
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText(title, { placeholder: "title" });
  return s;
}
function divider(num, title, sub, section) {
  pres.addSection({ title: section });
  const s = pres.addSlide({ masterName: "SECTION", sectionTitle: section });
  s.addText(num, { x: MX, y: 1.6, w: 3, h: 1.3, fontFace: THEME.headFontFace, fontSize: 80, bold: true, color: ORANGE, margin: 0, isTextBox: true });
  s.addText(title, { placeholder: "title" });
  s.addText(sub, { placeholder: "body" });
  return s;
}
const f1 = (x, d = 1) => Number(x).toFixed(d);
const fmtInt = (x) => String(Math.round(x)).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");

// ---------------------------------------------------------------- diapositivas
// Regla del curso: imagen grande y palabras clave. Sin fórmulas; lo técnico va en las notas
// del orador y en el informe.
const M = R.mission;
const es = (x, d = 1) => Number(x).toFixed(d).replace(".", ",");
const VIZ = (n) => A(`docs/figures/viz_${n}.png`);

/** Imagen a sangre sobre fondo oscuro, con título y palabras clave en una franja. */
function hero(img, title, keywords, notes) {
  const s = pres.addSlide({ masterName: "DARK" });
  s.addImage({ path: img, x: 0, y: 0, w: W, h: H, sizing: { type: "cover", w: W, h: H } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - 1.5, w: W, h: 1.5, fill: { color: NAVY, transparency: 15 }, line: { color: NAVY, transparency: 100 } });
  s.addText(title, { x: MX, y: H - 1.42, w: W - 2 * MX, h: 0.75, fontFace: THEME.headFontFace, fontSize: 32, bold: true, color: "FFFFFF", margin: 0, isTextBox: true });
  s.addText(keywords, { x: MX, y: H - 0.68, w: W - 2 * MX, h: 0.45, fontSize: 18, color: "CADCFC", margin: 0, isTextBox: true });
  s.addNotes(notes);
  return s;
}

/** Figura a la izquierda y hasta tres datos a la derecha. */
function figureSlide(title, img, stats, notes, formula) {
  const s = content(title);
  fit(s, img, MX, 1.25, 8.6, formula ? 4.3 : 5.4);
  if (formula) {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 5.62, w: 8.6, h: 1.05, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.08 });
    s.addText(formula.label, { x: MX + 0.2, y: 5.66, w: 8.2, h: 0.28, fontSize: 13, bold: true, color: ORANGE, margin: 0, isTextBox: true });
    fit(s, EQ(formula.eq), MX + 0.2, 5.95, 8.2, 0.66);
    notes += ` Fórmula: ${formula.note}`;
  }
  stats.forEach(([value, label], i) => stat(s, value, label, 9.55, 1.45 + i * 1.7, 3.2, i === 0 ? ORANGE : BLUE));
  s.addNotes(notes);
  return s;
}

// 1. Portada
let s = pres.addSlide({ masterName: "DARK" });
s.addImage({ path: NASA("nasa_sls_launch"), x: 8.4, y: 0, w: 4.93, h: H, sizing: { type: "cover", w: 4.93, h: H } });
s.addImage({ path: LOGO, x: MX, y: 0.5, w: 1.3, h: 0.8 });
s.addText("Artemis IV", { x: MX, y: 2.1, w: 7.4, h: 1.2, fontFace: THEME.headFontFace, fontSize: 60, bold: true, color: "FFFFFF", margin: 0, isTextBox: true });
s.addText("Simulación dinámica multifase: del ascenso del SLS Block 1B al alunizaje en el polo sur", { x: MX, y: 3.35, w: 7.2, h: 1, fontSize: 24, color: "CADCFC", margin: 0, isTextBox: true });
s.addText("Mariana Lopera Correa · Juan José Becerra Bedoya · Daniel Santiago Machado", { x: MX, y: 5.6, w: 7.4, h: 0.4, fontSize: 15, color: "FFFFFF", margin: 0, isTextBox: true });
s.addText("Computación Científica · Universidad de Medellín", { x: MX, y: 6.0, w: 7.4, h: 0.4, fontSize: 15, color: "CADCFC", margin: 0, isTextBox: true });
credit(s, "Imagen: NASA", 8.55, H - 0.35, 3, "FFFFFF");
s.addNotes("Se presenta un simulador numérico del perfil completo de Artemis IV y su visualizador 3D. El desarrollo matemático está en el informe.");

// 2. La misión en una imagen
hero(VIZ("mision"), "Perfil de misión simulado", `Marco rotante Tierra–Luna · ${es(M.mission_days, 1)} días · 5 fases · trayectoria continua`,
  "Trayectoria obtenida por el simulador en el marco rotante Tierra–Luna. El estado final de cada fase es el estado inicial de la siguiente.");

// 3. Las cinco fases
s = content("Cinco regímenes dinámicos");
const PHASES = [
  ["1", "Ascenso", "ascenso", "Masa variable y arrastre"],
  ["2", "Tránsito", "aparcamiento", "Problema de tres cuerpos"],
  ["3", "TLI", "sobrevuelo", "Valores en la frontera"],
  ["4", "NRHO", "nrho", "Órbita periódica"],
  ["5", "Descenso", "doi", "Guiado en lazo cerrado"],
];
PHASES.forEach(([n, name, img, key], i) => {
  const w = 2.3, x = MX + i * (w + 0.16);
  s.addImage({ path: VIZ(img), x, y: 1.6, w, h: 2.6, sizing: { type: "cover", w, h: 2.6 } });
  s.addText(`${n}. ${name}`, { x, y: 4.35, w, h: 0.5, fontFace: THEME.headFontFace, fontSize: 21, bold: true, color: NAVY, margin: 0, isTextBox: true });
  s.addText(key, { x, y: 4.85, w, h: 0.6, fontSize: 16, color: MUTED, margin: 0, isTextBox: true });
});
s.addText("Cada régimen requiere un método numérico específico", { x: MX, y: 5.75, w: W - 2 * MX, h: 0.5, fontSize: 20, bold: true, color: ORANGE, margin: 0, isTextBox: true });
s.addNotes("El ascenso es no conservativo y usa paso adaptativo con eventos. El tránsito es casi hamiltoniano y usa un integrador simpléctico. La TLI y la transferencia son problemas de valores en la frontera. El descenso combina integración de alto orden y guiado.");

// 4. El vehículo
s = content("Vehículo de lanzamiento: SLS Block 1B");
fit(s, NASA("nasa_sls_family"), MX, 1.25, 8.6, 5.4);
stat(s, `${fmtInt(R.liftoff_mass_t)} t`, "masa al despegue", 9.55, 1.45, 3.2);
stat(s, "4 + 2", "RS-25 + SRB de 5 segmentos", 9.55, 3.15, 3.2, BLUE);
stat(s, "EUS", "Etapa Superior de Exploración", 9.55, 4.85, 3.2, BLUE);
credit(s, "Imagen: NASA", MX, 6.65, 4);
s.addNotes("Artemis IV es la primera misión prevista con el Block 1B. La EUS permite co-manifestar el módulo I-Hab de Gateway con Orion. Los parámetros del HLS son supuestos del trabajo, porque SpaceX no los publica.");

// 5. Fase 1
figureSlide("Fase 1 · Ascenso atmosférico", FIG("fig01_ascenso_perfil"), [
  [`${es(R.maxq_kpa)} kPa`, "Max-Q: presión dinámica máxima"],
  [`${fmtInt(R.h_meco_km)} km`, "altitud de MECO"],
  ["RK45", "Dormand–Prince con eventos"],
], `Sistema de siete EDO en ECI con masa variable, arrastre Cd(Mach) y atmósfera US76. El paso es adaptativo y los eventos detectan la separación de SRB y el MECO. Max-Q ocurre a los ${es(R.t_maxq_s, 0)} s. En MECO la velocidad es ${es(R.v_meco_kms, 2)} km/s, suborbital; la EUS completa la inserción.`, { eq: "eq_asc_v", label: "Ecuación de movimiento (ECI)", note: "empuje sobre masa, más arrastre sobre masa, menos gravedad. Se integra junto con la posición y la masa." });

// 6. Fase 2
figureSlide("Fase 2 · Tránsito cislunar: conservación numérica", FIG("fig03_conservacion_integradores"), [
  ["Verlet", "simpléctico: error ≤ 1,5e-4"],
  ["RK4", "deriva secular: 3,4e-3"],
  ["200", "órbitas, 40 pasos por órbita"],
], "Verlet, de orden 2, conserva un hamiltoniano modificado: su error de energía oscila sin deriva. RK4, de orden 4, presenta deriva secular y un decaimiento orbital artificial. Con la Luna activa, la energía geocéntrica no es un invariante; el diagnóstico correcto es la integral de Jacobi, conservada a 1e-5.", { eq: "eq_verlet", label: "Velocity Verlet (kick–drift–kick)", note: "medio paso de velocidad, paso completo de posición y otro medio paso de velocidad. Usa una evaluación de fuerzas por paso." });

// 7. Fase 3
figureSlide("Fase 3 · Inyección translunar (TLI)", FIG("fig05_trayectoria_tli"), [
  [`${R.tli_iterations}`, "iteraciones de Newton–Raphson"],
  ["≈ 3,2 km/s", "Δv de la TLI"],
  ["Disparo", "valores en la frontera"],
], `Se busca el Δv que lleva del estado de aparcamiento al objetivo lunar en un tiempo de vuelo dado. Newton–Raphson amortiguado converge con una estimación inicial obtenida de la ecuación de Kepler; con la estimación vis-viva no convergía. El Δv es ${fmtInt(R.tli_dv_ms)} m/s en el problema aislado y ${fmtInt(M.dv_tli_ms)} m/s en la misión integrada, cuyo objetivo es distinto.`, { eq: "eq_shoot", label: "Condición del disparo", note: "F es la distancia entre el punto de llegada y el objetivo; Newton–Raphson busca el Δv que la anula." });

// 8. Fase 4: NRHO
figureSlide("Fase 4 · NRHO 9:2 de Gateway", FIG("fig09_familia_halo"), [
  [`${es(M.nrho_period_d, 2)} d`, "periodo de la órbita"],
  [es(M.nrho_stability, 2), "índice de estabilidad"],
  ["L2 sur", "familia de halos por continuación"],
], "La NRHO es una órbita periódica del CR3BP. Se obtiene por corrección diferencial con la matriz de transición de estados y continuación de la familia de halos L2 sur hasta el periodo 9:2. Su inestabilidad débil reduce el costo de mantenimiento.");

// 9. Transferencia
figureSlide("Fase 4 · Transferencia de la TLI a la NRHO", FIG("fig10_transferencia_nrho"), [
  [`${fmtInt(M.dv_opf_ms)} m/s`, "sobrevuelo propulsado (OPF)"],
  [`${fmtInt(M.dv_nri_ms)} m/s`, "inserción en la NRHO (NRI)"],
  [`${fmtInt(M.orion_dv_used_pct)} %`, "del Δv disponible de Orion"],
], `La inserción directa en el perilunio tiene un Δv elevado. Como en Artemis I, se emplea un sobrevuelo propulsado a ${fmtInt(M.opf_alt_km)} km. La trayectoria se optimiza con disparo múltiple y SLSQP; el resultado es un mínimo local, no necesariamente global.`);

// 10. Descenso
hero(VIZ("descenso"), "Fase 5 · Descenso propulsado al polo sur", `Velocidad de contacto ${es(M.touchdown_speed_ms, 1)} m/s · Error de posición ${es(M.landing_error_m * 100, 1)} cm · Latitud ${es(Math.abs(M.site_lat_deg), 1)}° S`,
  "Tras la DOI, el HLS sigue una elipse con periapsis a 15 km y ejecuta 700 s de descenso propulsado. El E-guidance recalcula el empuje en lazo cerrado. En la imagen, el vehículo no está a escala y el relieve fino lunar es decorativo.");

// 11. Perfil de descenso
figureSlide("Fase 5 · Perfil del descenso propulsado", FIG("fig11_descenso"), [
  [`${fmtInt(M.powered_s)} s`, "de descenso propulsado"],
  ["1,9 km/s", "velocidad horizontal en el PDI"],
  [`${fmtInt(M.hls_mass_landed_t)} t`, `masa final (inicial: ${fmtInt(M.hls_mass_initial_t)} t)`],
], "Tres tramos con objetivo propio: frenado, aproximación y descenso vertical, separados por la high gate y la low gate. Las masas del HLS parten de parámetros supuestos.", { eq: "eq_eguidance", label: "E-guidance (energía mínima)", note: "aceleración ordenada a partir del error de posición y velocidad respecto al objetivo, con t_go el tiempo restante. Se recalcula en lazo cerrado." });

// 12. Mascons
figureSlide("Campo gravitatorio lunar: efecto de los mascons", FIG("fig12_mascons"), [
  [`${fmtInt(M.mascon_anomaly_max_mgal)} mGal`, "anomalía máxima"],
  [`${es(M.mascon_dev_jtwo_km, 1)} km`, "desviación frente a J₂ en una órbita"],
  ["GRGM1200A", "campo GRAIL, grado 100"],
], "El potencial se evalúa con armónicos esféricos hasta grado 100. La formulación de Pines elimina la singularidad polar. En una órbita polar de 100 km, los mascons producen desviaciones de kilómetros por revolución; el guiado en lazo cerrado las corrige.");

// 13. Presupuesto
s = content("Presupuesto de Δv de la misión");
const DV = [
  ["Inserción", M.dv_insertion_ms, "EUS"], ["TLI", M.dv_tli_ms, "EUS"], ["OPF", M.dv_opf_ms, "Orion"],
  ["NRI", M.dv_nri_ms, "Orion"], ["DOI", M.dv_doi_ms, "HLS"], ["Descenso", M.dv_powered_ms, "HLS"],
];
DV.forEach(([name, dv, who], i) => {
  stat(s, fmtInt(dv), `${name} · ${who} (m/s)`, MX + (i % 3) * 4.1, 1.5 + Math.floor(i / 3) * 1.6, 3.85, i % 3 === 0 ? ORANGE : BLUE);
});
const totalDv = DV.reduce((a, [, dv]) => a + dv, 0);
s.addText(`Total desde la inserción: ${es(totalDv / 1000, 2)} km/s`, { x: MX, y: 4.95, w: W - 2 * MX, h: 0.7, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: NAVY, margin: 0, isTextBox: true });
s.addText(`El descenso propulsado representa el ${fmtInt(100 * M.dv_powered_ms / totalDv)} % del total`, { x: MX, y: 5.65, w: W - 2 * MX, h: 0.5, fontSize: 20, color: MUTED, margin: 0, isTextBox: true });
s.addNotes("El presupuesto incluye las maniobras desde la inserción en órbita de aparcamiento; no incluye el ascenso hasta el MECO. TLI, OPF, NRI y DOI se modelan como impulsivas.");

// 14. Visualizador
s = content("Visualizador 3D interactivo");
fit(s, VIZ("interfaz"), MX, 1.2, W - 2 * MX, 4.95);
s.addText("Reproducción de la misión en 2,5 min · Tres marcos de referencia · Datos exportados del simulador", { x: MX, y: 6.2, w: W - 2 * MX - 1, h: 0.45, fontSize: 18, color: MUTED, align: "center", margin: 0, isTextBox: true });
s.addNotes("Demostración en vivo: python -m http.server 8000 -d frontend. La telemetría se calcula de la trayectoria exportada, con la velocidad relativa a la superficie lunar cerca de la Luna.");

// 15. Confianza
s = content("Verificación y validación");
stat(s, "151", "pruebas automáticas", MX, 1.5, 3.85);
stat(s, "≈ 1e-5", "error relativo de la integral de Jacobi", MX + 4.1, 1.5, 3.85, BLUE);
stat(s, "8", "problemas corregidos en la revisión", MX + 8.2, 1.5, 3.85, BLUE);
bullets(s, [
  "Max-Q y Δv de TLI consistentes con valores publicados",
  "Órdenes de convergencia medidos: Verlet 2,00 y RK4 4,14",
  "Trazabilidad: los valores del informe se generan desde el código",
], MX, 3.4, W - 2 * MX, 2.2, 22);
s.addNotes("133 pruebas en Python y 18 en el visualizador. La revisión crítica corrigió, entre otros, el balance de masa de los SRB, la mezcla de marcos ECI y ECEF y la interpolación de discontinuidades en la exportación.");

// 16. Conclusiones
s = content("Conclusiones");
const KEYS = [
  ["Simulación integrada", `Trayectoria continua de ${es(M.mission_days, 1)} días en 5 fases, con Δv de ${es(totalDv / 1000, 2)} km/s desde la inserción`],
  ["Integración simpléctica", "Error de energía acotado en 1,5e-4, frente a deriva secular de 3,4e-3 con RK4 en 200 órbitas"],
  ["Métodos de disparo", "La convergencia depende de la estimación inicial: kepleriana en la TLI, retropropagada en la NRHO"],
  ["Guiado en lazo cerrado", `Contacto a ${es(M.touchdown_speed_ms, 1)} m/s y ${es(M.landing_error_m * 100, 1)} cm del sitio, con campo GRAIL de grado 100`],
];
KEYS.forEach(([k, d], i) => {
  const x = MX + (i % 2) * 6.15, y = 1.4 + Math.floor(i / 2) * 2.05;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 5.95, h: 1.85, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.1 });
  s.addText(k, { x: x + 0.3, y: y + 0.18, w: 5.4, h: 0.55, fontFace: THEME.headFontFace, fontSize: 23, bold: true, color: NAVY, margin: 0, isTextBox: true });
  s.addText(d, { x: x + 0.3, y: y + 0.76, w: 5.4, h: 0.95, fontSize: 17, color: INK, valign: "top", margin: 0, isTextBox: true });
});
s.addText("Limitaciones: maniobras impulsivas · modelo CR3BP sin efemérides · parámetros del HLS supuestos", { x: MX, y: 5.6, w: W - 2 * MX - 1, h: 0.45, fontSize: 16, color: MUTED, margin: 0, isTextBox: true });
s.addText("Trabajo futuro: efemérides DE440 · combustiones finitas · topografía lunar", { x: MX, y: 6.05, w: W - 2 * MX - 1, h: 0.45, fontSize: 16, color: MUTED, margin: 0, isTextBox: true });
s.addNotes("Cada conclusión se apoya en un resultado medido. El modelo no incluye perturbación solar ni combustiones finitas en órbita; el trabajo futuro apunta a esas limitaciones.");

// 17. Cierre
s = pres.addSlide({ masterName: "DARK" });
s.addImage({ path: NASA("nasa_artemis_moon"), x: 8.4, y: 0, w: 4.93, h: H, sizing: { type: "cover", w: 4.93, h: H } });
s.addText("Gracias", { x: MX, y: 2.4, w: 7.4, h: 1.2, fontFace: THEME.headFontFace, fontSize: 60, bold: true, color: "FFFFFF", margin: 0, isTextBox: true });
s.addText("¿Preguntas?", { x: MX, y: 3.6, w: 7.4, h: 0.7, fontSize: 28, color: "CADCFC", margin: 0, isTextBox: true });
credit(s, "Imagen: NASA", 8.55, H - 0.35, 3, "FFFFFF");
s.addNotes("El desarrollo matemático, los métodos y la verificación se encuentran en el informe.");

// ---------------------------------------------------------------- write + theme
(async () => {
  await pres.writeFile({ fileName: OUT });
  // Opcional: escribe los colores de THEME en el tema del .pptx (solo cambia la paleta que
  // PowerPoint ofrece al editar; las diapositivas ya usan colores explícitos).
  if (process.env.PPTX_SKILL) {
    const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");
    await applyTheme(OUT, THEME);
  }
  console.log("OK ->", OUT);
})();
