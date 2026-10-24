// Records a scripted tour of the running Cadence UI as lossless PNG frames at a constant frame rate.
//   node record-tour.mjs <frames-dir> desktop|phone
// The server must be running with DEMO data (build.sh sets that up). Needs Google Chrome installed.
import { chromium } from "playwright-core";
import fs from "node:fs";

const OUT = process.argv[2];
const MODE = process.argv[3] === "phone" ? "phone" : "desktop";
const BASE = process.env.CADENCE_URL ?? "http://127.0.0.1:8790";
const FPS = 12;
const phone = MODE === "phone";
if (!OUT) {
  console.error("usage: node record-tour.mjs <frames-dir> desktop|phone");
  process.exit(2);
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({
  viewport: phone ? { width: 390, height: 844 } : { width: 1180, height: 740 },
  deviceScaleFactor: phone ? 2 : 1,
  hasTouch: phone,
  isMobile: phone,
  userAgent: phone
    ? "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    : undefined,
});
const page = await ctx.newPage();

// Chrome's screencast emits a frame whenever the page repaints; we resample to a constant rate below.
const cdp = await ctx.newCDPSession(page);
const frames = [];
cdp.on("Page.screencastFrame", async (f) => {
  frames.push({ t: f.metadata.timestamp, data: Buffer.from(f.data, "base64") });
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});

const wait = (ms) => page.waitForTimeout(ms);
const scrollTo = (y, ms) =>
  page.evaluate(
    ([y, ms]) =>
      new Promise((res) => {
        const start = performance.now();
        const from = window.scrollY;
        const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
        const step = (now) => {
          const t = Math.min(1, (now - start) / ms);
          window.scrollTo(0, from + (y - from) * ease(t));
          t < 1 ? requestAnimationFrame(step) : res();
        };
        requestAnimationFrame(step);
      }),
    [y, ms],
  );
const go = async (href) => {
  await page.locator(`a[href="${href}"]:visible`).first().click();
  await wait(300);
};

await page.goto(BASE + "/", { waitUntil: "networkidle" });
await cdp.send("Page.startScreencast", { format: "png", everyNthFrame: 1 });

if (!phone) {
  await wait(3200);
  await scrollTo(520, 1600); await wait(900);
  await scrollTo(0, 900); await wait(300);
  await go("/coach"); await wait(2200); await scrollTo(480, 1600); await wait(900);
  await go("/plan"); await wait(2600); await scrollTo(380, 1300); await wait(700);
  await go("/weight"); await wait(2600);
  await scrollTo(760, 1700); await wait(2200);
  await scrollTo(0, 900); await wait(400);
  await page.getByRole("button", { name: /log weight/i }).click(); await wait(700);
  await page.locator("#log-kg").pressSequentially("77.4", { delay: 190 }); await wait(1400);
  await page.keyboard.press("Escape"); await wait(500); // never saved: the tour must not change the data
  await go("/activities"); await wait(2200);
  await go("/"); await wait(1600); // ends where it began, so the loop is seamless
} else {
  await wait(3000);
  await scrollTo(600, 1800); await wait(1000);
  await page.evaluate(() => window.scrollTo({ top: 0 })); await wait(300);
  await go("/coach"); await wait(2200); await scrollTo(500, 1700); await wait(800);
  await go("/weight"); await wait(2400); await scrollTo(900, 2000); await wait(2000);
  await go("/"); await wait(1500);
}

await cdp.send("Page.stopScreencast");
await browser.close();

const t0 = frames[0].t;
const t1 = frames[frames.length - 1].t;
const count = Math.floor((t1 - t0) * FPS);
let j = 0;
for (let i = 0; i <= count; i++) {
  const want = t0 + i / FPS;
  while (j + 1 < frames.length && frames[j + 1].t <= want) j++;
  fs.writeFileSync(`${OUT}/f${String(i).padStart(4, "0")}.png`, frames[j].data);
}
console.log(`${MODE}: ${count + 1} frames at ${FPS} fps (${(t1 - t0).toFixed(1)} s)`);
