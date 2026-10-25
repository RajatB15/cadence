// Renders the algorithm explainers (explainers/explainers.html) to lossless PNG frames, deterministically.
//   node render-explainers.mjs <out-dir> [fps=12] [seconds=10] [scene,scene,...|still:<t>]
// Frames land in <out-dir>/<scene>/f0000.png. Synthetic data only; no server needed.
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = process.argv[2];
const FPS = Number(process.argv[3] ?? 12);
const SECONDS = Number(process.argv[4] ?? 10);
const ONLY = process.argv[5];
if (!OUT) { console.error("usage: node render-explainers.mjs <out-dir> [fps] [seconds] [scenes|still:<t>]"); process.exit(2); }

// Fonts come from the web app's own dependencies, so the clips match the product typography.
const NM = path.resolve(HERE, "../../app/web/node_modules");
const fonts = path.join(HERE, "explainers/fonts");
fs.mkdirSync(fonts, { recursive: true });
for (const [src, dst] of [
  ["@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2", "manrope.woff2"],
  ["@fontsource/instrument-serif/files/instrument-serif-latin-400-normal.woff2", "serif.woff2"],
  ["@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2", "mono.woff2"],
]) fs.copyFileSync(path.join(NM, src), path.join(fonts, dst));

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await (await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 })).newPage();
await page.goto("file://" + path.join(HERE, "explainers/explainers.html"));
await page.evaluate(() => document.fonts.ready);
const names = await page.evaluate(() => window.sceneNames);
const still = ONLY?.startsWith("still:") ? Number(ONLY.slice(6)) : null;
const pick = still === null && ONLY ? ONLY.split(",") : names;

for (const name of pick) {
  const dir = path.join(OUT, name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  if (still !== null) {
    await page.evaluate(([n, t]) => window.draw(n, t), [name, still]);
    await page.waitForTimeout(100);
    await page.screenshot({ path: path.join(dir, "still.png") });
    continue;
  }
  const body = Math.round(FPS * SECONDS), hold = Math.round(FPS * 2);   // animate, then hold the finished state
  for (let i = 0; i < body + hold; i++) {
    await page.evaluate(([n, t]) => window.draw(n, t), [name, Math.min(1, i / body)]);
    await page.screenshot({ path: path.join(dir, `f${String(i).padStart(4, "0")}.png`) });
  }
  console.log(`${name}: ${body + hold} frames`);
}
await browser.close();
