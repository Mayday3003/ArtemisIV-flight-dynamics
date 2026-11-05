// Captura escenas del visualizador para el informe y las diapositivas (docs/figures/viz_*.png).
// Uso, con el visualizador servido en el puerto 8000:
//   python -m http.server 8000 -d frontend
//   CHROME=/ruta/a/chrome npm run capture
import { chromium } from "playwright-core";
import path from "node:path";
import { fileURLToPath } from "node:url";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "figures");
const URL_APP = process.env.URL_APP ?? "http://localhost:8000/";
const MOVE_MS = 2500; // espera a que termine la toma de cámara

const browser = await chromium.launch({
  executablePath: process.env.CHROME,
  headless: true,
  args: ["--use-angle=gl-egl", "--use-gl=angle", "--ignore-gpu-blocklist"],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2 });
page.on("pageerror", (e) => console.error("Error en la página:", e.message));
await page.goto(URL_APP);
await page.waitForSelector("#loading", { state: "detached", timeout: 60000 });
await page.waitForTimeout(2000);

const shot = (name) => page.screenshot({ path: path.join(OUT, `viz_${name}.png`) });
await shot("inicio");

await page.click("#intro-start");
await page.waitForTimeout(500);
await page.click("#play"); // en pausa: cada captura queda en su evento

/** Salta al evento i de la línea de tiempo. */
async function goto(i) {
  const ticks = await page.$$(".event-tick");
  await ticks[i].evaluate((e) => e.click());
  await page.waitForTimeout(MOVE_MS);
}
const clean = await page.addStyleTag({ content: ".panel { visibility: hidden; }" });
const SCENES = [[0, "ascenso"], [2, "aparcamiento"], [4, "sobrevuelo"], [5, "nrho"], [6, "doi"], [8, "descenso"]];
for (const [i, name] of SCENES) {
  await goto(i);
  await shot(name);
}
await clean.evaluate((e) => e.remove());

await goto(5);
await page.click("#science-btn");
await page.waitForTimeout(600);
await shot("interfaz");
await page.click("#science-btn");

const ticks = await page.$$(".event-tick");
await goto(ticks.length - 1);
await shot("final");

// Vista general al final: toda la trayectoria queda iluminada
await page.click("#finale-close");
await page.addStyleTag({ content: ".panel { visibility: hidden; }" });
await page.keyboard.press("m");
await page.waitForTimeout(MOVE_MS);
await shot("mision");
await browser.close();
