// Genera la presentación Artemis_IV_UdeM.pptx a partir de las figuras y resultados del proyecto.
// Uso (desde la raíz del repo):
//   .venv/bin/python docs/presentation/render_formulas.py
//   NODE_PATH=<dir con pptxgenjs>/node_modules node docs/presentation/build_deck.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const A = (p) => path.join(ROOT, p);
const R = JSON.parse(fs.readFileSync(A("docs/figures/results.json"), "utf8"));
const DIMS = JSON.parse(fs.readFileSync(A("docs/presentation/assets/dims.json"), "utf8"));
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
  const key = Object.keys(DIMS).find((k) => A(k) === p || k === p || p.endsWith(k));
  if (!key) throw new Error("Sin dimensiones para " + p);
  return DIMS[key];
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
  slide.addText(label, { x: x + 0.1, y: y + 0.76, w: w - 0.2, h: 0.4, fontSize: 12.5, color: MUTED, align: "center", margin: 0, isTextBox: true });
}

function credit(slide, text, x, y, w, color = MUTED) {
  slide.addText(text, { x, y, w, h: 0.25, fontSize: 10, italic: true, color, margin: 0, isTextBox: true });
}

function content(title, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
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

// ====================================================================== 1. Portada
pres.addSection({ title: "Introducción" });
let s = pres.addSlide({ masterName: "DARK", sectionTitle: "Introducción" });
fit(s, NASA("nasa_sls_launch"), 8.6, 0, 4.73, 7.5);
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 0.5, w: 1.55, h: 0.95, fill: { color: "FFFFFF" }, line: { color: "FFFFFF" }, rectRadius: 0.08 });
fit(s, LOGO, MX + 0.08, 0.55, 1.4, 0.85);
s.addText("Simulación dinámica multifase de la misión Artemis IV", { x: MX, y: 1.8, w: 7.7, h: 1.9, fontFace: THEME.headFontFace, fontSize: 38, bold: true, color: "FFFFFF", valign: "top", margin: 0, isTextBox: true });
s.addText("Ascenso del SLS Block 1B, integración simpléctica y targeting de la inyección translunar", { x: MX, y: 3.75, w: 7.5, h: 0.9, fontSize: 18, color: "CADCFC", margin: 0, isTextBox: true });
s.addText([
  { text: "Mariana Lopera Correa · Juan José Becerra Bedoya · Daniel Santiago Machado", options: { breakLine: true, bold: true } },
  { text: "Programa de Computación Científica · Universidad de Medellín", options: { breakLine: true } },
  { text: "16 de octubre de 2026" },
], { x: MX, y: 5.3, w: 7.7, h: 1.2, fontSize: 14, color: "FFFFFF", margin: 0, paraSpaceAfter: 4, isTextBox: true });
credit(s, "Imagen: NASA, lanzamiento del SLS", 8.75, 7.15, 4.4, "CADCFC");
s.addNotes("Presentamos un simulador numérico de las primeras fases de vuelo de Artemis IV: el ascenso del cohete SLS Block 1B, el viaje de la Tierra a la Luna y el cálculo de la maniobra de inyección translunar. Todo está implementado en Python, verificado con pruebas automáticas, y cada resultado que mostramos sale directamente del código.");

// ====================================================================== 2. Agenda
s = content("Agenda", "Introducción");
const agenda = [
  ["01", "Contexto", "Programa Artemis, SLS Block 1B y alcance"],
  ["02", "Fase 1 · Ascenso", "Ecuaciones en ECI, empuje, aerodinámica, guiado, RK45"],
  ["03", "Fase 2 · Tránsito", "Problema de 3 cuerpos, Verlet simpléctico, Jacobi"],
  ["04", "Fase 3 · TLI", "Método del disparo y Newton-Raphson"],
  ["05", "Cierre", "Errores corregidos, conclusiones y trabajo futuro"],
];
agenda.forEach(([n, t, d], i) => {
  const y = 1.45 + i * 1.08;
  s.addShape(pres.shapes.OVAL, { x: MX, y, w: 0.8, h: 0.8, fill: { color: i === 0 ? ORANGE : NAVY }, line: { color: i === 0 ? ORANGE : NAVY } });
  s.addText(n, { x: MX, y, w: 0.8, h: 0.8, fontSize: 18, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText(t, { x: MX + 1.05, y: y + 0.02, w: 5, h: 0.42, fontFace: THEME.headFontFace, fontSize: 20, bold: true, color: NAVY, margin: 0, isTextBox: true });
  s.addText(d, { x: MX + 1.05, y: y + 0.42, w: 6.4, h: 0.35, fontSize: 14, color: MUTED, margin: 0, isTextBox: true });
});
fit(s, NASA("nasa_sls_block1b"), 8.6, 1.3, 4.1, 5.4);
credit(s, "Imagen: NASA, SLS Block 1B (render)", 8.9, 6.75, 3.6);
s.addNotes("La charla sigue el orden de la misión: contexto, luego las tres fases que simulamos y al final la revisión crítica del código, las conclusiones y el trabajo futuro.");

// ====================================================================== 3. Artemis
s = content("El programa Artemis: regreso sostenible a la Luna", "Introducción");
fit(s, NASA("nasa_artemis_moon"), MX, 1.35, 4.2, 5.45);
credit(s, "Imagen: NASA, Artemis Plan (2020)", MX, 6.85, 4.2);
const arts = [
  ["Artemis I (2022)", "Vuelo de prueba sin tripulación de SLS + Orion alrededor de la Luna"],
  ["Artemis II", "Primer sobrevuelo lunar tripulado"],
  ["Artemis III", "Primer alunizaje tripulado en el polo sur con el HLS"],
  ["Artemis IV", "Debut del SLS Block 1B (etapa EUS) + módulo I-Hab para Gateway"],
];
arts.forEach(([t, d], i) => {
  const y = 1.45 + i * 1.2, x = 5.3;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 7.4, h: 1.0, fill: { color: i === 3 ? "FDEBDD" : TINT }, line: { color: i === 3 ? ORANGE : TINT, width: 1 }, rectRadius: 0.08 });
  s.addText(t, { x: x + 0.25, y: y + 0.08, w: 7, h: 0.4, fontFace: THEME.headFontFace, fontSize: 18, bold: true, color: i === 3 ? ORANGE : NAVY, margin: 0, isTextBox: true });
  s.addText(d, { x: x + 0.25, y: y + 0.5, w: 7, h: 0.4, fontSize: 15, color: INK, margin: 0, isTextBox: true });
});
s.addText("A diferencia de Apolo, Artemis encadena varios regímenes orbitales: LEO → TLI → NRHO (Gateway) → descenso con el HLS.", { x: 5.3, y: 6.3, w: 7.4, h: 0.6, fontSize: 14, italic: true, color: MUTED, margin: 0, isTextBox: true });
s.addNotes("Artemis es el programa de la NASA para volver a la Luna de forma sostenible. Nuestro caso es Artemis IV porque es la primera misión con el SLS Block 1B, que cambia la etapa superior por la EUS y permite llevar Orion junto con el módulo I-Hab de la estación Gateway. Eso cambia las masas y el empuje, y por eso modelamos ese vehículo concreto.");

// ====================================================================== 4. SLS Block 1B
s = content("El vehículo: SLS Block 1B", "Introducción");
fit(s, NASA("nasa_sls_exploded"), MX, 1.3, 5.6, 3.45);
credit(s, "Imagen: NASA, SLS Fact Sheet (2023)", MX, 4.8, 5.6);
const rows = [
  ["Componente", "Masa seca / prop.", "Empuje (vacío)", "Isp"],
  ["Core Stage (4× RS-25)", "85.3 / 987.5 t", "9.12 MN", "452.3 s"],
  ["2× SRB 5 segmentos", "199.6 / 1 257.4 t", "32.0 MN (pico)", "268 s"],
  ["EUS (4× RL10C-3)", "13.6 / 129.0 t", "0.43 MN", "448.5 s"],
  ["Carga útil (Orion + I-Hab)", `${f1(R.eus_payload_t)} t`, "—", "—"],
  ["Masa al despegue", `${fmtInt(R.liftoff_mass_t)} t`, "T/W ≈ 1.41", ""],
];
s.addTable(rows.map((r, i) => r.map((c) => ({
  text: c,
  options: { bold: i === 0 || i === rows.length - 1, color: i === 0 ? "FFFFFF" : INK, fill: { color: i === 0 ? NAVY : i % 2 ? "FFFFFF" : TINT }, fontSize: 13 },
}))), { x: 6.55, y: 1.4, w: 6.15, colW: [2.25, 1.55, 1.35, 1.0], rowH: 0.42, border: { type: "solid", pt: 0.5, color: "D5DAE1" }, valign: "middle", margin: 0.06 });
codeTag(s, ["src/artemis_sim/constants.py", "SLS_B1B_CORE_STAGE · SLS_B1B_SRB_PAIR · SLS_B1B_EUS · StageSpec"], 6.55, 4.25, 6.15);
bullets(s, [
  [{ text: "Etapa central + 2 SRB: ", bold: true }, { text: "llevan el vehículo fuera de la atmósfera" }],
  [{ text: "EUS: ", bold: true }, { text: "inserción en órbita de aparcamiento y maniobra TLI" }],
  [{ text: "Datos públicos NASA / fabricantes; ", bold: true }, { text: "los de la EUS siguen pendientes de confirmación" }],
], MX, 5.25, 12, 1.4, 15);
s.addNotes("Estos son los parámetros del vehículo, todos definidos en constants.py como objetos StageSpec inmutables. La masa al despegue sale de sumar etapas y carga útil: unas 2 710 toneladas. La relación empuje/peso al despegue es de 1.41, dentro del rango esperado para el SLS.");

// ====================================================================== 5. Perfil de misión
s = content("Perfil de misión y alcance del proyecto", "Introducción");
const steps = [
  ["1", "Ascenso", "Despegue LC-39B → MECO", true],
  ["2", "Órbita de aparcamiento", "Inserción con la EUS", true],
  ["3", "TLI", "Impulso hacia la Luna", true],
  ["4", "NRHO", "Acople con Gateway", false],
  ["5", "Descenso", "HLS al polo sur lunar", false],
];
const sw = 2.25, gap = 0.18;
steps.forEach(([n, t, d, done], i) => {
  const x = MX + i * (sw + gap), y = 1.8;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: sw, h: 2.1, fill: { color: done ? NAVY : "FFFFFF" }, line: { color: done ? NAVY : "B8BEC8", width: 1.25, dashType: done ? "solid" : "dash" }, rectRadius: 0.1 });
  s.addText(n, { x, y: y + 0.12, w: sw, h: 0.6, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: done ? ORANGE : "B8BEC8", align: "center", margin: 0, isTextBox: true });
  s.addText(t, { x: x + 0.1, y: y + 0.8, w: sw - 0.2, h: 0.55, fontSize: 17, bold: true, color: done ? "FFFFFF" : MUTED, align: "center", margin: 0, isTextBox: true });
  s.addText(d, { x: x + 0.1, y: y + 1.35, w: sw - 0.2, h: 0.6, fontSize: 13, color: done ? "CADCFC" : MUTED, align: "center", margin: 0, isTextBox: true });
  if (i < steps.length - 1) s.addText("›", { x: x + sw - 0.02, y: y + 0.75, w: gap + 0.04, h: 0.5, fontSize: 22, bold: true, color: ORANGE, align: "center", margin: 0, isTextBox: true });
});
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 4.35, w: 7.2, h: 0.5, fill: { color: "FDEBDD" }, line: { color: "FDEBDD" }, rectRadius: 0.08 });
s.addText("Fases 1–3: implementadas, verificadas y con resultados", { x: MX + 0.2, y: 4.35, w: 7, h: 0.5, fontSize: 15, bold: true, color: ORANGE, valign: "middle", margin: 0, isTextBox: true });
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.1, y: 4.35, w: 4.6, h: 0.5, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.08 });
s.addText("Fases 4–5: trabajo futuro", { x: 8.3, y: 4.35, w: 4.4, h: 0.5, fontSize: 15, bold: true, color: MUTED, valign: "middle", margin: 0, isTextBox: true });
bullets(s, [
  [{ text: "Problema: ", bold: true }, { text: "cada fase tiene una física distinta: disipativa en la atmósfera y casi hamiltoniana en el vacío" }],
  [{ text: "Idea central: ", bold: true }, { text: "usar el integrador adecuado para cada régimen (RK45 adaptativo frente a Verlet simpléctico)" }],
], MX, 5.25, 12.1, 1.4, 16);
s.addNotes("El perfil completo tiene cinco fases. Simulamos las tres primeras: ascenso, inserción en órbita y TLI. La NRHO y el descenso quedan como trabajo futuro. La idea que atraviesa todo el proyecto es que cada régimen físico necesita un método numérico diferente.");

// ====================================================================== 6. Arquitectura
s = content("Arquitectura del código: paquete artemis_sim", "Introducción");
const mods = [
  ["constants.py", "Tierra, Luna, etapas SLS", 0],
  ["state.py", "Vector de estado [r, v, m]", 0],
  ["physics_engine.py", "Gravedad, atmósfera, Mach, arrastre, empuje", 1],
  ["ephemeris.py", "Órbita lunar circular (n kepleriano)", 1],
  ["ascent_solver.py", "Fase 1: EDO del ascenso, guiado, eventos", 2],
  ["symplectic_solver.py", "Fase 2: CR3BP, Verlet, RK4, Jacobi", 2],
  ["shooting_method.py", "Fase 3: disparo + Newton-Raphson", 2],
];
const colX = [MX, 4.75, 8.9], colTitle = ["Datos", "Física", "Solvers"];
colTitle.forEach((t, c) => s.addText(t, { x: colX[c], y: 1.3, w: 3.8, h: 0.4, fontFace: THEME.headFontFace, fontSize: 18, bold: true, color: ORANGE, margin: 0, isTextBox: true }));
const cnt = [0, 0, 0];
mods.forEach(([m, d, c]) => {
  const y = 1.8 + cnt[c]++ * 1.12;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: colX[c], y, w: 3.8, h: 0.95, fill: { color: c === 2 ? NAVY : TINT }, line: { color: c === 2 ? NAVY : TINT }, rectRadius: 0.08 });
  s.addText(m, { x: colX[c] + 0.18, y: y + 0.08, w: 3.5, h: 0.4, fontFace: "Courier New", fontSize: 14, bold: true, color: c === 2 ? "FFFFFF" : NAVY, margin: 0, isTextBox: true });
  s.addText(d, { x: colX[c] + 0.18, y: y + 0.48, w: 3.5, h: 0.4, fontSize: 13, color: c === 2 ? "CADCFC" : INK, margin: 0, isTextBox: true });
});
[1, 2].forEach((c) => s.addText("→", { x: colX[c] - 0.37, y: 2.75, w: 0.35, h: 0.5, fontSize: 24, bold: true, color: ORANGE, align: "center", margin: 0, isTextBox: true }));
stat(s, "63", "pruebas automáticas (pytest)", MX, 4.35, 3.0, NAVY);
codeTag(s, ["Reproducir todo:", "pytest  ·  python scripts/generate_figures.py"], MX + 3.3, 4.35, 4.6);
bullets(s, [
  "Funciones físicas puras y en unidades SI",
  "Las figuras y los números del informe se generan desde el código (results.tex)",
], MX + 3.3, 5.55, 8.6, 1.0, 15);
s.addNotes("El código está en src/artemis_sim. Hay tres capas: datos (constants, state), física pura (physics_engine, ephemeris) y solvers, uno por fase. El script scripts/generate_figures.py produce todas las gráficas y los números del informe, así que lo que mostramos es reproducible. Hay 63 pruebas automáticas.");

// ====================================================================== 7. Divisor Fase 1
s = divider("01", "Fase 1 · Ascenso atmosférico", "Del LC-39B al apagado de la etapa central (MECO)", "Fase 1 · Ascenso");
fit(s, NASA("nasa_sls_block1b"), 9.4, 0.6, 3.3, 6.3);
s.addNotes("Primera fase: el ascenso por la atmósfera.");

// ====================================================================== 8. Ecuaciones ECI
s = content("Ecuaciones de movimiento en el marco inercial ECI", "Fase 1 · Ascenso");
s.addText("Estado: Y = [r, v, m] ∈ ℝ⁷", { x: MX, y: 1.35, w: 6.5, h: 0.4, fontSize: 17, bold: true, color: NAVY, margin: 0, isTextBox: true });
let yy = 1.95;
yy += eq(s, "eq_asc_r", MX + 0.2, yy, 6.5) + 0.25;
yy += eq(s, "eq_asc_v", MX + 0.2, yy, 6.5) + 0.25;
yy += eq(s, "eq_asc_m", MX + 0.2, yy, 6.5) + 0.25;
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.4, y: 1.35, w: 5.3, h: 2.6, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.1 });
s.addText("¿Por qué no hay Coriolis?", { x: 7.65, y: 1.5, w: 4.9, h: 0.4, fontFace: THEME.headFontFace, fontSize: 18, bold: true, color: ORANGE, margin: 0, isTextBox: true });
s.addText("En un marco inercial las fuerzas ficticias no existen. La rotación terrestre entra solo por:", { x: 7.65, y: 1.95, w: 4.9, h: 0.75, fontSize: 14, color: INK, margin: 0, isTextBox: true });
eq(s, "eq_vrel", 7.85, 2.8, 4.5, 0.95);
s.addText("y por la velocidad inicial ω×r₀ ≈ 408 m/s hacia el este.", { x: 7.65, y: 3.4, w: 4.9, h: 0.45, fontSize: 14, color: INK, margin: 0, isTextBox: true });
bullets(s, [
  "Tres fuerzas: empuje T·û, arrastre D y gravedad newtoniana",
  "El borrador mezclaba ECEF (Coriolis/centrífuga) con ECI: corregido",
], 7.4, 4.25, 5.3, 1.2, 14);
codeTag(s, ["src/artemis_sim/ascent_solver.py", "make_ascent_derivatives(config)  →  f(t, Y)", "physics_engine.py → compute_relative_velocity(), compute_gravity()"], MX, 5.75, 12.1);
s.addNotes("Escribimos las ecuaciones en el marco geocéntrico inercial ECI. El estado tiene siete componentes: posición, velocidad y masa. La aceleración suma empuje, arrastre y gravedad. Detalle importante: en un marco inercial no hay Coriolis; la rotación de la Tierra entra por la velocidad relativa al aire y por la velocidad inicial de 408 m/s del LC-39B. El borrador original mezclaba ambos marcos y lo corregimos. Todo esto está en make_ascent_derivatives, que devuelve la función f(t, Y) que recibe solve_ivp.");

// ====================================================================== 9. Empuje y SRB
s = content("Empuje y conservación de masa de los SRB", "Fase 1 · Ascenso");
s.addText("Empuje de tobera", { x: MX, y: 1.35, w: 6, h: 0.4, fontFace: THEME.headFontFace, fontSize: 18, bold: true, color: NAVY, margin: 0, isTextBox: true });
eq(s, "eq_thrust", MX + 0.2, 1.85, 5.5);
s.addText("El gasto másico lo fija la cámara de combustión (no depende de h); el empuje crece al bajar la presión ambiente.", { x: MX, y: 2.45, w: 6, h: 0.75, fontSize: 14, color: INK, margin: 0, isTextBox: true });
s.addText("Perfil regresivo de los SRB", { x: MX, y: 3.25, w: 6, h: 0.4, fontFace: THEME.headFontFace, fontSize: 18, bold: true, color: NAVY, margin: 0, isTextBox: true });
eq(s, "eq_srb", MX + 0.2, 3.72, 5.5);
eq(s, "eq_k", MX + 0.2, 4.25, 5.6, 0.85);
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.2, y: 1.35, w: 5.5, h: 3.7, fill: { color: "FDEBDD" }, line: { color: "FDEBDD" }, rectRadius: 0.1 });
s.addText("Error encontrado en el código original", { x: 7.45, y: 1.5, w: 5.1, h: 0.4, fontFace: THEME.headFontFace, fontSize: 17, bold: true, color: ORANGE, margin: 0, isTextBox: true });
bullets(s, [
  "Empuje constante de 16 MN por SRB con Isp de 268 s: el propelente se agota a los 103 s",
  "Pero los SRB seguían encendidos hasta los 126 s",
  "Consumían unas 280 t de masa del Core Stage",
  [{ text: "Solución: ", bold: true }, { text: "el perfil f(t) se escala con k para que ∫ṁ dt = m_p exactamente" }],
], 7.45, 2.0, 5.1, 3.0, 14);
stat(s, f1(R.srb_scale, 4), "factor k: los datos públicos son coherentes", 7.2, 5.25, 5.5);
codeTag(s, ["src/artemis_sim/ascent_solver.py", "SRB_THRUST_PROFILE · srb_thrust_fraction(t, tb) · srb_thrust_scale(spec, tb)", "physics_engine.py → compute_thrust(), compute_mass_flow()"], MX, 5.6, 6.35);
s.addNotes("El empuje real depende de la presión: T = T_vac - p_a A_e. Aquí encontramos el primer error físico: con empuje constante los SRB se quedaban sin propelente a los 103 segundos, pero el código los mantenía encendidos hasta los 126 y les restaba masa de la etapa central. Lo corregimos con un perfil de empuje regresivo, como el real, escalado con un factor k que garantiza la conservación de masa. Ese factor da 1.0033: los datos públicos son coherentes. Hay una prueba automática que integra el flujo másico y comprueba que da exactamente la masa de propelente.");

// ====================================================================== 10. Atmósfera
s = content("Atmósfera, número de Mach y arrastre", "Fase 1 · Ascenso");
const eqs10 = [["Densidad exponencial", "eq_rho"], ["Temperatura US Standard Atmosphere 1976 → sonido y Mach", "eq_sound"], ["Arrastre, opuesto a la velocidad relativa", "eq_drag"]];
yy = 1.35;
eqs10.forEach(([t, e]) => {
  s.addText(t, { x: MX, y: yy, w: 6.6, h: 0.38, fontSize: 15, bold: true, color: NAVY, margin: 0, isTextBox: true });
  yy += 0.45;
  yy += eq(s, e, MX + 0.2, yy, 6.4, 0.8) + 0.22;
});
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.6, y: 1.35, w: 5.1, h: 3.85, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.1 });
s.addText("Cd(M): tabla interpolada", { x: 7.85, y: 1.5, w: 4.6, h: 0.4, fontFace: THEME.headFontFace, fontSize: 17, bold: true, color: NAVY, margin: 0, isTextBox: true });
s.addTable([
  ["Mach", "0.6", "1.05", "2.0", "5.0"],
  ["Cd", "0.30", "0.55", "0.40", "0.26"],
].map((r, i) => r.map((c, j) => ({ text: c, options: { bold: i === 0 || j === 0, fontSize: 14, color: i === 0 ? "FFFFFF" : INK, fill: { color: i === 0 ? NAVY : "FFFFFF" }, align: "center" } }))), { x: 7.85, y: 2.05, w: 4.6, rowH: 0.42, border: { type: "solid", pt: 0.5, color: "D5DAE1" } });
bullets(s, [
  "Pico transónico por arrastre de onda (M ≈ 1)",
  "A_ref = 55.4 m² (diámetro de 8.4 m)",
  "El arrastre se anula por encima de 100 km",
], 7.85, 3.15, 4.6, 2.0, 14);
codeTag(s, ["src/artemis_sim/physics_engine.py", "compute_atmospheric_temperature() · compute_speed_of_sound() · compute_mach_number()", "compute_drag_coefficient(mach) · compute_aerodynamic_drag() · compute_dynamic_pressure()"], MX, 5.55, 12.1);
s.addNotes("La atmósfera usa densidad exponencial y la temperatura por capas de la atmósfera estándar de 1976, de donde sale la velocidad del sonido y el Mach. El coeficiente de arrastre ya no es constante: se interpola de una tabla con el pico transónico típico de los cohetes. Todas son funciones puras de physics_engine.py.");

// ====================================================================== 11. Guiado y eventos
s = content("Guiado e integración RK45 con eventos", "Fase 1 · Ascenso");
const g = [
  ["0–10 s", "Ascenso vertical", "despeje de la torre"],
  ["10–126 s", "Pitch kick + giro por gravedad", "û ∥ v_rel, ángulo de ataque nulo"],
  ["126–480 s", "Ley de tangente lineal", "óptima en el vacío (guiado PEG)"],
];
g.forEach(([t, a, b], i) => {
  const x = MX + i * 4.1;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.35, w: 3.9, h: 1.35, fill: { color: i === 2 ? NAVY : TINT }, line: { color: i === 2 ? NAVY : TINT }, rectRadius: 0.1 });
  s.addText(t, { x: x + 0.2, y: 1.42, w: 3.5, h: 0.4, fontSize: 14, bold: true, color: ORANGE, margin: 0, isTextBox: true });
  s.addText(a, { x: x + 0.2, y: 1.8, w: 3.5, h: 0.4, fontSize: 16, bold: true, color: i === 2 ? "FFFFFF" : NAVY, margin: 0, isTextBox: true });
  s.addText(b, { x: x + 0.2, y: 2.2, w: 3.5, h: 0.4, fontSize: 13, color: i === 2 ? "CADCFC" : MUTED, margin: 0, isTextBox: true });
});
eq(s, "eq_lintan", MX + 0.2, 3.0, 7.5, 0.95);
s.addText("θ₀ = 0.4915 rad y θf = 0.1548 rad se hallaron con fsolve para que el MECO quede a h = 160 km y γ = 0.", { x: MX, y: 4.05, w: 7.4, h: 0.7, fontSize: 14, color: INK, margin: 0, isTextBox: true });
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.3, y: 3.0, w: 4.4, h: 2.25, fill: { color: "FDEBDD" }, line: { color: "FDEBDD" }, rectRadius: 0.1 });
s.addText("Dormand–Prince RK45", { x: 8.5, y: 3.1, w: 4, h: 0.4, fontFace: THEME.headFontFace, fontSize: 17, bold: true, color: ORANGE, margin: 0, isTextBox: true });
bullets(s, [
  "Paso adaptativo con error local 4(5)",
  "Evento: fin de los SRB, que se descartan (salto de masa)",
  "Evento: MECO (masa de corte)",
  "Explícito: el ascenso no es rígido",
], 8.5, 3.55, 4.0, 1.7, 13.5);
codeTag(s, ["src/artemis_sim/ascent_solver.py", "linear_tangent_direction() · make_srb_burnout_event() · make_core_burnout_event()", "jettison_boosters() · simulate_full_ascent()  →  AscentResult"], MX, 5.55, 12.1);
s.addNotes("El guiado tiene tres tramos. En la atmósfera hacemos un giro por gravedad: el empuje sigue la velocidad relativa, con ángulo de ataque cero para minimizar las cargas. Fuera de la atmósfera usamos la ley de tangente lineal, que es la óptima para empuje en el vacío. Los dos parámetros se resolvieron con fsolve para llegar al MECO a 160 km con ángulo de trayectoria cero. El código original usaba solo el giro por gravedad y el cohete se estrellaba a los 388 segundos. La integración usa RK45 con eventos: al detectar el fin de los SRB se descarta su masa seca y se reinicia hasta el MECO.");

// ====================================================================== 12. Resultados ascenso
s = content("Resultados del ascenso", "Fase 1 · Ascenso");
fit(s, FIG("fig01_ascenso_perfil"), MX, 1.25, 6.4, 5.65);
stat(s, `${f1(R.maxq_kpa)} kPa`, `Max-Q a t = ${f1(R.t_maxq_s, 0)} s (Mach ${f1(R.mach_maxq, 2)})`, 7.4, 1.35, 2.55);
stat(s, `${f1(R.h_meco_km, 0)} km`, `altitud en MECO (t = ${f1(R.t_meco_s, 0)} s)`, 10.15, 1.35, 2.55);
stat(s, `${f1(R.v_meco_kms, 2)} km/s`, "velocidad inercial en MECO", 7.4, 2.8, 2.55);
stat(s, `${f1(R.max_g, 1)} g₀`, "aceleración máxima", 10.15, 2.8, 2.55);
bullets(s, [
  `Separación de los SRB a ${f1(R.t_srb_sep_s, 0)} s, h = ${f1(R.h_srb_sep_km)} km`,
  "Max-Q del orden publicado para el SLS (unos 30 kPa)",
  "Salto de masa en la separación y aceleración creciente como T/m(t)",
], 7.4, 4.35, 5.3, 2.0, 14);
s.addNotes("Resultados del ascenso completo. La presión dinámica máxima es de 27.5 kPa a los 65 segundos, ya en régimen supersónico, del mismo orden que la del SLS real. A los 126 s se separan los SRB y se ve el salto de masa. El MECO llega a los 480 s a 160 km con 6.6 km/s. La aceleración llega a 3.5 g al final; el vehículo real estrangula los motores para limitarla, algo que no modelamos.");

// ====================================================================== 13. Trayectoria y EUS
s = content("Trayectoria de ascenso y presupuesto de Δv de la EUS", "Fase 1 · Ascenso");
fit(s, FIG("fig02_ascenso_trayectoria"), MX, 1.25, 12.1, 2.55);
eq(s, "eq_tsiol", MX + 0.2, 4.15, 4.5);
s.addText("Ecuación de Tsiolkovsky", { x: MX, y: 4.95, w: 4.5, h: 0.35, fontSize: 13, color: MUTED, margin: 0, isTextBox: true });
const dvr = [
  ["Maniobra", "Δv (km/s)"],
  ["Inserción en órbita (160 km)", f1(R.dv_insertion_kms, 2)],
  ["Inyección translunar (TLI)", f1(R.tli_dv_ms / 1000, 2)],
  ["Total requerido", f1(R.dv_insertion_kms + R.tli_dv_ms / 1000, 2)],
  ["Disponible en la EUS", f1(R.dv_eus_total_kms, 2)],
];
s.addTable(dvr.map((r, i) => r.map((c, j) => ({ text: c, options: { bold: i === 0 || i >= 3, fontSize: 14, color: i === 0 ? "FFFFFF" : i === 4 ? ORANGE : INK, fill: { color: i === 0 ? NAVY : i % 2 ? "FFFFFF" : TINT }, align: j ? "right" : "left" } }))), { x: 5.4, y: 4.05, w: 4.4, colW: [3.0, 1.4], rowH: 0.4, border: { type: "solid", pt: 0.5, color: "D5DAE1" } });
stat(s, `${f1(R.eus_prop_remaining_t, 1)} t`, "propelente sobrante en la EUS", 10.15, 4.05, 2.55, BLUE);
s.addText("En el MECO, v < v_circ: la etapa central deja el vehículo en una trayectoria suborbital y la EUS completa la inserción.", { x: 10.15, y: 5.45, w: 2.55, h: 1.3, fontSize: 12.5, color: MUTED, margin: 0, isTextBox: true });
s.addNotes("Así se ve la trayectoria: 980 km de alcance hasta el MECO. Como en el MECO la velocidad (6.6 km/s) es menor que la circular (7.8 km/s), la EUS debe completar la inserción con 1.2 km/s y luego hacer la TLI de 3.15 km/s. Con Tsiolkovsky, la EUS dispone de 5.55 km/s, así que sobran unas 16 toneladas de propelente: la misión es factible dentro del modelo.");

// ====================================================================== 14. Divisor Fase 2
s = divider("02", "Fase 2 · Tránsito cislunar", "Problema restringido de tres cuerpos e integración simpléctica", "Fase 2 · Tránsito");
fit(s, NASA("nasa_artemis_moon"), 9.0, 0.6, 3.7, 6.3);
credit(s, "Imagen: NASA, Artemis Plan (2020)", 9.0, 6.95, 3.7, "CADCFC");
s.addNotes("Segunda fase: el viaje balístico de la Tierra a la Luna.");

// ====================================================================== 15. CR3BP
s = content("Modelo de 3 cuerpos: término indirecto y n kepleriano", "Fase 2 · Tránsito");
s.addText("Aceleración geocéntrica (Tierra + Luna como masas puntuales)", { x: MX, y: 1.35, w: 12, h: 0.4, fontSize: 16, bold: true, color: NAVY, margin: 0, isTextBox: true });
eq(s, "eq_cr3bp", MX + 0.2, 1.9, 9.5);
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: MX, y: 3.25, w: 5.9, h: 2.1, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.1 });
s.addText("Término indirecto", { x: MX + 0.25, y: 3.38, w: 5.4, h: 0.4, fontFace: THEME.headFontFace, fontSize: 17, bold: true, color: ORANGE, margin: 0, isTextBox: true });
s.addText("El origen (la Tierra) también cae hacia la Luna. En coordenadas geocéntricas hay que restar esa aceleración, −μ_L r_L/|r_L|³; el borrador lo omitía.", { x: MX + 0.25, y: 3.85, w: 5.4, h: 1.4, fontSize: 14, color: INK, margin: 0, isTextBox: true });
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.8, y: 3.25, w: 5.9, h: 2.1, fill: { color: "FDEBDD" }, line: { color: "FDEBDD" }, rectRadius: 0.1 });
s.addText("Movimiento medio consistente", { x: 7.05, y: 3.38, w: 5.4, h: 0.4, fontFace: THEME.headFontFace, fontSize: 17, bold: true, color: ORANGE, margin: 0, isTextBox: true });
eq(s, "eq_n", 7.15, 3.85, 5.2, 0.7);
s.addText("El valor sidéreo de 2.6617e-6 no satisface la tercera ley de Kepler con μ_E + μ_L; con ese valor, Jacobi no se conservaba.", { x: 7.05, y: 4.6, w: 5.4, h: 0.7, fontSize: 13, color: INK, margin: 0, isTextBox: true });
codeTag(s, ["src/artemis_sim/symplectic_solver.py → compute_n_body_acceleration(r, t)", "src/artemis_sim/ephemeris.py → LUNAR_MEAN_MOTION_RAD_S · get_body_position() · get_body_velocity()"], MX, 5.65, 12.1);
s.addNotes("En el vacío solo actúan la gravedad terrestre y la lunar. Como usamos coordenadas centradas en la Tierra, y la Tierra también es atraída por la Luna, aparece el término indirecto, que el documento original omitía (el código sí lo tenía). Además corregimos la velocidad angular de la Luna: para que el modelo sea un problema restringido circular de tres cuerpos auténtico, debe cumplir la tercera ley de Kepler con las masas de ambos cuerpos.");

// ====================================================================== 16. Verlet
s = content("Velocity Verlet: un integrador simpléctico", "Fase 2 · Tránsito");
s.addText("Esquema kick–drift–kick (orden 2, una evaluación de fuerza por paso)", { x: MX, y: 1.35, w: 12, h: 0.4, fontSize: 16, bold: true, color: NAVY, margin: 0, isTextBox: true });
eq(s, "eq_verlet", MX + 0.2, 1.9, 12.0, 0.9);
bullets(s, [
  [{ text: "Simpléctico: ", bold: true }, { text: "preserva la 2-forma del espacio de fases" }],
  [{ text: "Hamiltoniano modificado: ", bold: true }, { text: "el error de energía oscila acotado, sin deriva" }],
  [{ text: "Fuerza central: ", bold: true }, { text: "conserva el momento angular hasta el redondeo" }],
  [{ text: "Verificado: ", bold: true }, { text: `pendientes ${f1(R.order_verlet, 2)} (Verlet) y ${f1(R.order_rk4, 2)} (RK4)` }],
], MX, 2.75, 6.2, 2.4, 15);
eq(s, "eq_hmod", MX + 0.2, 4.95, 6.0, 0.85);
fit(s, FIG("fig04_orden_convergencia"), 7.1, 2.55, 5.6, 3.9);
codeTag(s, ["symplectic_solver.py → verlet_step() · propagate_verlet() · propagate_rk4() · propagate_reference_dop853()"], MX, 5.85, 6.3);
s.addNotes("Para el tránsito usamos Velocity Verlet. Es de orden 2 pero simpléctico: conserva la estructura geométrica del problema hamiltoniano. Por el análisis de error regresivo, conserva exactamente un hamiltoniano modificado cercano al real, así que el error de energía queda acotado para siempre. La gráfica verifica el orden: las pendientes medidas son 2.00 para Verlet y 4.14 para RK4.");

// ====================================================================== 17. Comparación
s = content("Acotado frente a deriva: Verlet, RK4 y DOP853", "Fase 2 · Tránsito");
fit(s, FIG("fig03_conservacion_integradores"), MX, 1.25, 7.8, 5.6);
stat(s, Number(R.verlet_max_dE).toExponential(1), "Verlet: error máximo de energía (acotado)", 8.75, 1.35, 3.95, BLUE);
stat(s, Number(R.rk4_final_dE).toExponential(1), "RK4: error final (deriva secular)", 8.75, 2.8, 3.95, ORANGE);
bullets(s, [
  `${R.n_orbits_cmp} órbitas a 400 km con Δt = T/${R.steps_per_orbit_cmp}`,
  "RK4 tiene mayor orden, pero disipa energía y la órbita decae artificialmente",
  "DOP853 es más preciso, pero también deriva y cuesta muchas más evaluaciones",
], 8.75, 4.3, 3.95, 2.5, 14);
s.addNotes("Esta es la gráfica clave del proyecto. Con el mismo paso, RK4, que es de mayor orden, pierde energía de forma continua: es una disipación numérica que haría decaer la órbita. Verlet tiene más error instantáneo, pero no crece: oscila acotado. El momento angular de Verlet se conserva hasta el redondeo. Por eso, para propagaciones largas, el integrador simpléctico es la elección correcta.");

// ====================================================================== 18. Jacobi
s = content("Con la Luna: el invariante correcto es la integral de Jacobi", "Fase 2 · Tránsito");
eq(s, "eq_jacobi", MX + 0.2, 1.45, 6.4, 0.9);
bullets(s, [
  "El potencial lunar depende del tiempo, así que la energía geocéntrica no se conserva",
  "En el marco baricéntrico rotante el sistema es autónomo y E_J es constante",
  `Variación de la energía geocéntrica: ${(R.geo_energy_max_rel * 100).toFixed(0)} %`,
  `Variación de Jacobi con Verlet (Δt = 1 s): ${Number(R.jacobi_max_rel).toExponential(1)}`,
], MX, 2.45, 5.8, 3.0, 15);
fit(s, FIG("fig08_jacobi"), 6.7, 1.3, 6.0, 4.3);
codeTag(s, ["src/artemis_sim/symplectic_solver.py", "compute_jacobi_constant(state) · compute_system_energy(state, t)"], MX, 5.75, 12.1);
s.addNotes("Con la Luna presente, la energía respecto a la Tierra no es constante: cambia un 77 % en el encuentro, y eso es física, no un error. El documento original afirmaba que se conservaba. El invariante correcto es la integral de Jacobi del problema restringido. Verlet la conserva con un error relativo de 1e-5, que aparece en la primera hora cerca de la Tierra y luego se mantiene plano.");

// ====================================================================== 19. Divisor Fase 3
s = divider("03", "Fase 3 · Inyección translunar", "Problema de valores en la frontera: método del disparo", "Fase 3 · TLI");
fit(s, NASA("nasa_sls_launch"), 9.0, 0.6, 3.7, 6.3);
credit(s, "Imagen: NASA, lanzamiento del SLS", 9.0, 6.95, 3.7, "CADCFC");
s.addNotes("Tercera fase: calcular la maniobra para llegar a la Luna.");

// ====================================================================== 20. Disparo
s = content("Método del disparo con Newton-Raphson", "Fase 3 · TLI");
s.addText("Buscamos Δv tal que la nave llegue al punto objetivo en t_f = 4 días", { x: MX, y: 1.3, w: 12, h: 0.4, fontSize: 16, bold: true, color: NAVY, margin: 0, isTextBox: true });
eq(s, "eq_shoot", MX + 0.2, 1.85, 7.5, 0.9);
eq(s, "eq_newton", MX + 0.2, 2.5, 7.5, 0.8);
bullets(s, [
  "Cada evaluación de F propaga la trayectoria con DOP853 (rtol = 1e-12)",
  "Diferencias centrales con h = 1 cm/s, región de confianza (500 m/s) y retroceso",
  `Objetivo: ${fmtInt(R.tli_flyby_alt_km)} km sobre la superficie lunar`,
], MX, 3.65, 7.4, 1.8, 14);
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.3, y: 1.3, w: 4.4, h: 4.1, fill: { color: "FDEBDD" }, line: { color: "FDEBDD" }, rectRadius: 0.1 });
s.addText("Semilla kepleriana", { x: 8.5, y: 1.42, w: 4, h: 0.4, fontFace: THEME.headFontFace, fontSize: 17, bold: true, color: ORANGE, margin: 0, isTextBox: true });
s.addText("Con la semilla vis-viva el residuo inicial era de 677 000 km y Newton no convergía. Resolvemos la ecuación de Kepler:", { x: 8.5, y: 1.85, w: 4.0, h: 1.1, fontSize: 13.5, color: INK, margin: 0, isTextBox: true });
eq(s, "eq_kepler", 8.6, 3.0, 3.9, 0.75);
s.addText(`Con Brent se hallan r_a y ν = ${f1(R.tli_transfer_angle_deg)}°, que fijan el punto de encendido. Residuo inicial: ${fmtInt(R.tli_initial_residual_km)} km.`, { x: 8.5, y: 3.7, w: 4.0, h: 1.4, fontSize: 13.5, color: INK, margin: 0, isTextBox: true });
codeTag(s, ["src/artemis_sim/shooting_method.py", "solve_tli_shooting() · shooting_residual() · numerical_jacobian()", "kepler_transfer_geometry() · moon_relative_target() · make_dop853_propagator()"], MX, 5.6, 12.1);
s.addNotes("La TLI es un problema de valores en la frontera: conocemos dónde empezamos y dónde queremos estar en 4 días, pero no la velocidad inicial. Lo resolvemos con el método del disparo: F(Δv) es el error de posición al llegar, y con Newton y un jacobiano por diferencias centrales iteramos hasta anularlo. Newton solo converge si arrancamos cerca, y la semilla original estaba a 677 000 km del objetivo. La mejoramos resolviendo la ecuación de Kepler, que nos dice dónde encender para que el apogeo coincida con la Luna. Así el residuo inicial cae a 24 000 km, causado solo por la gravedad lunar.");

// ====================================================================== 21. Resultado TLI
s = content("Resultado de la TLI", "Fase 3 · TLI");
fit(s, FIG("fig05_trayectoria_tli"), MX, 1.25, 7.9, 3.55);
fit(s, FIG("fig07_convergencia_disparo"), MX, 4.85, 7.9, 2.05);
stat(s, `${fmtInt(R.tli_dv_ms)} m/s`, "Δv de la TLI (clásico: 3.1–3.2 km/s)", 8.85, 1.35, 3.85);
stat(s, `${R.tli_iterations} iteraciones`, `residuo final ${Number(R.tli_final_residual_m).toExponential(1)} m`, 8.85, 2.8, 3.85, NAVY);
bullets(s, [
  "Convergencia cuadrática al final (Newton)",
  `κ(J) ≤ ${Number(R.cond_max).toExponential(1)}: problema bien condicionado`,
  `Verificación con Verlet: llega a ${fmtInt(R.verlet_arrival_alt_km)} km de altitud lunar`,
], 8.85, 4.3, 3.85, 2.5, 14);
s.addNotes("Newton converge en 5 iteraciones a un Δv de 3 150 m/s, justo el valor clásico de una TLI. En la gráfica se ve la convergencia cuadrática al final. En el marco rotante, a la derecha, la Luna queda fija y se aprecia la forma de la transferencia. Al repropagar con Verlet, la nave llega a 4 001 km de altitud, prácticamente el objetivo de 4 000 km.");

// ====================================================================== 22. Revisión crítica
pres.addSection({ title: "Cierre" });
s = content("Revisión crítica: errores encontrados y corregidos", "Cierre");
const fixes = [
  ["Masa de los SRB", "Agotados a 103 s, encendidos hasta 126 s", "Perfil f(t) con k = 1.0033"],
  ["Trayectoria de ascenso", "El cohete se estrellaba a los 388 s", "Guiado de tangente lineal → MECO a 160 km"],
  ["Eventos", "Constantes fijas (126 s, 180 t)", "Fábricas basadas en AscentConfig"],
  ["Movimiento medio lunar", "Inconsistente con μ_E + μ_L", "n = √((μ_E+μ_L)/d³)"],
  ["Diagnóstico energético", "Energía geocéntrica no conservada", "Integral de Jacobi"],
  ["Targeting TLI", "No convergía (677 000 km)", "Semilla de Kepler: 5 iteraciones"],
  ["Documento", "ECI/ECEF mezclados; RK45 'rígido'", "Formulación corregida"],
];
s.addTable([["Aspecto", "Problema", "Corrección"], ...fixes].map((r, i) => r.map((c, j) => ({ text: c, options: { bold: i === 0 || j === 0, fontSize: 13.5, color: i === 0 ? "FFFFFF" : j === 2 ? "137A55" : j === 1 ? "B54A1C" : NAVY, fill: { color: i === 0 ? NAVY : i % 2 ? "FFFFFF" : TINT } } }))), { x: MX, y: 1.35, w: 12.1, colW: [3.0, 4.6, 4.5], rowH: 0.52, border: { type: "solid", pt: 0.5, color: "D5DAE1" }, valign: "middle", margin: 0.08 });
s.addText("Cada corrección tiene una prueba automática en tests/test_physics_corrections.py", { x: MX, y: 5.75, w: 11, h: 0.4, fontSize: 14, italic: true, color: MUTED, margin: 0, isTextBox: true });
s.addNotes("Esta es la revisión crítica que hicimos antes de presentar resultados. Encontramos siete problemas: los SRB que violaban la conservación de masa, una trayectoria que se estrellaba, eventos con constantes fijas, una velocidad lunar inconsistente, un diagnóstico de energía que no era un invariante, un targeting que no convergía y errores de formulación en el documento. Cada uno tiene ahora una prueba automática que lo protege.");

// ====================================================================== 23. Conclusiones
s = content("Conclusiones y trabajo futuro", "Cierre");
s.addText("Conclusiones", { x: MX, y: 1.3, w: 6, h: 0.45, fontFace: THEME.headFontFace, fontSize: 20, bold: true, color: ORANGE, margin: 0, isTextBox: true });
bullets(s, [
  "Simulador modular y verificado de 3 fases de Artemis IV",
  "Resultados coherentes con el SLS: Max-Q de 27.5 kPa, TLI de 3.15 km/s",
  "Integrador simpléctico: error acotado frente a la deriva de RK4",
  "Con la Luna, el invariante es Jacobi y no la energía",
  "Una buena semilla (Kepler) es decisiva para Newton",
], MX, 1.9, 6.0, 4.2, 15);
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.0, y: 1.3, w: 5.7, h: 4.2, fill: { color: TINT }, line: { color: TINT }, rectRadius: 0.1 });
s.addText("Trabajo futuro", { x: 7.25, y: 1.45, w: 5.2, h: 0.45, fontFace: THEME.headFontFace, fontSize: 20, bold: true, color: NAVY, margin: 0, isTextBox: true });
bullets(s, [
  [{ text: "NRHO: ", bold: true }, { text: "órbitas de halo L2 sur por corrección diferencial" }],
  [{ text: "Descenso HLS: ", bold: true }, { text: "armónicos esféricos GRGM1200A (mascons de GRAIL)" }],
  [{ text: "Efemérides: ", bold: true }, { text: "JPL DE440, Sol, J₂ y presión de radiación" }],
  [{ text: "Combustiones finitas ", bold: true }, { text: "de la EUS y optimización del ascenso" }],
  [{ text: "Visualización 3D ", bold: true }, { text: "con Three.js (frontend del repositorio)" }],
], 7.25, 2.0, 5.2, 4.0, 14.5);
s.addNotes("En conclusión: tenemos un simulador verificado, con resultados coherentes con el vehículo real, que demuestra con datos por qué cada régimen requiere su integrador. Como trabajo futuro quedan la órbita NRHO de Gateway, el descenso con el campo gravitatorio lunar real de GRAIL y efemérides de alta fidelidad.");

// ====================================================================== 24. Cierre
s = pres.addSlide({ masterName: "DARK", sectionTitle: "Cierre" });
fit(s, NASA("nasa_sls_family"), 6.4, 0.9, 6.5, 4.4);
credit(s, "Imagen: NASA, evolución del SLS (Block 1 → Block 2)", 6.6, 5.35, 6.2, "CADCFC");
s.addText("¿Preguntas?", { x: MX, y: 2.2, w: 5.6, h: 1.2, fontFace: THEME.headFontFace, fontSize: 48, bold: true, color: "FFFFFF", margin: 0, isTextBox: true });
s.addText("Gracias", { x: MX, y: 3.4, w: 5.6, h: 0.6, fontSize: 22, color: ORANGE, bold: true, margin: 0, isTextBox: true });
s.addText([
  { text: "Referencias principales", options: { bold: true, breakLine: true, color: "FFFFFF" } },
  { text: "NASA (2020) Artemis Plan · NASA (2023) SLS Fact Sheet", options: { breakLine: true } },
  { text: "Hairer, Lubich & Wanner (2006) Geometric Numerical Integration", options: { breakLine: true } },
  { text: "Curtis (2013) Orbital Mechanics · Sutton (2017) Rocket Propulsion", options: { breakLine: true } },
  { text: "Código: src/artemis_sim · Informe: docs/paper/final/main.pdf" },
], { x: MX, y: 5.6, w: 12, h: 1.5, fontSize: 12.5, color: "CADCFC", margin: 0, paraSpaceAfter: 2, isTextBox: true });
s.addNotes("Gracias. Quedamos atentos a sus preguntas. Si quiere, podemos abrir el código y mostrar cualquiera de las funciones citadas en las diapositivas.");

// ---------------------------------------------------------------- write + theme
(async () => {
  await pres.writeFile({ fileName: OUT });
  const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");
  await applyTheme(OUT, THEME);
  console.log("OK ->", OUT);
})();
