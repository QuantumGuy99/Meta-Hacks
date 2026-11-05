// Renders the motion-graphics segments of the demo video and captures the landing page.
// Usage: node docs/video/render.js [--live https://your-app.vercel.app] [--app http://localhost:3000]
// Output: docs/video/build/*.mp4 (1920x1080, 30 fps, silent). build.sh assembles the final cut.
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const DIR = __dirname;
const OUT = path.join(DIR, "build");
const FPS = 30;
const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const LIVE = arg("--live", "");
const APP = arg("--app", "http://localhost:3000");
const ONLY = arg("--only", "");

// from/seconds in video time: each scene draws itself from absolute video seconds.
const SEGMENTS = [
  { name: "00_problem", scene: "problem", from: 0, seconds: 10 },
  { name: "01_hook", scene: "hook", from: 10, seconds: 13.5 },
  { name: "08_tech", scene: "tech", from: 0, seconds: 14.5 },
  { name: "08b_impact", scene: "impact", from: 0, seconds: 9.5 },
  { name: "09_end", scene: "end", from: 0, seconds: 5 },
  { name: "slate_defense", scene: "slate:defense", seconds: 1 },
  { name: "slate_coding", scene: "slate:coding", seconds: 1 },
];

function encodeFrames(frameDir, out, fps) {
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", path.join(frameDir, "%05d.jpg"),
    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-r", String(FPS), out]);
}

async function renderScenes(browser) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  // Word timings in video seconds, so the animations follow the voiceover (see align_vo.py).
  const timingFile = path.join(DIR, "vo_lines", "timing.json");
  const vo = {};
  // Each line's start time comes from VO_LINES in build.py, so moving a line there moves its animation too.
  const starts = {};
  for (const m of fs.readFileSync(path.join(DIR, "build.py"), "utf8").matchAll(/\("(\d{4})", ([\d.]+),/g)) starts[m[1]] = +m[2];
  if (fs.existsSync(timingFile)) {
    for (const [name, t] of Object.entries(JSON.parse(fs.readFileSync(timingFile, "utf8")))) {
      const at = starts[name] ?? t.at;
      vo[name] = t.words.map(([w, a, b]) => [w, at + a - t.onset, at + b - t.onset]);
    }
  }
  await page.addInitScript((v) => { window.VO = v; }, vo);
  const q = LIVE ? "?live=" + encodeURIComponent(LIVE) : "";
  await page.goto("file://" + path.join(DIR, "scenes.html") + q);
  await page.evaluate(() => window.ready);
  await page.waitForTimeout(500);
  for (const seg of SEGMENTS) {
    if (ONLY && !seg.name.includes(ONLY)) continue;
    const frames = path.join(OUT, "frames_" + seg.name);
    fs.rmSync(frames, { recursive: true, force: true });
    fs.mkdirSync(frames, { recursive: true });
    const n = seg.scene.startsWith("slate:") ? 1 : Math.round(seg.seconds * FPS);
    for (let i = 0; i < n; i++) {
      await page.evaluate(([s, t]) => window.seek(s, t), [seg.scene, (seg.from || 0) + i / FPS]);
      await page.screenshot({ path: path.join(frames, String(i).padStart(5, "0") + ".jpg"), type: "jpeg", quality: 95 });
    }
    if (seg.scene.startsWith("slate:")) {
      fs.copyFileSync(path.join(frames, "00000.jpg"), path.join(OUT, seg.name + ".jpg"));
    } else {
      encodeFrames(frames, path.join(OUT, seg.name + ".mp4"), FPS);
    }
    fs.rmSync(frames, { recursive: true, force: true });
    console.log("rendered", seg.name);
  }
  await page.close();
}

// The real landing page, captured in real time (its code panel animates on its own) via CDP screencast.
async function captureLanding(browser, seconds = 10) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(APP + "/", { waitUntil: "networkidle" });
  await page.addStyleTag({ content: `
    nextjs-portal { display: none !important; }
    #who-for { position: fixed; left: 50%; top: 14px; transform: translateX(-50%); z-index: 9999; font: 600 22px Inter, sans-serif;
      color: #fff; background: rgba(16,16,18,.92); border: 1px solid #2f6bff; border-radius: 999px; padding: 10px 26px; white-space: nowrap; }` });
  await page.evaluate(() => {
    const d = document.createElement("div");
    d.id = "who-for";
    d.textContent = "For students and early-career engineers who prep for interviews and ship with AI agents";
    document.body.appendChild(d);
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(1500);
  const frames = path.join(OUT, "frames_landing");
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });
  const cdp = await ctx.newCDPSession(page);
  const shots = [];
  cdp.on("Page.screencastFrame", async (f) => {
    shots.push({ t: f.metadata.timestamp, data: f.data });
    await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 95, maxWidth: 1920, maxHeight: 1080 });
  // A slow drift so the frame never looks frozen; the hero and the stats row stay in view.
  const start = Date.now();
  while (Date.now() - start < seconds * 1000 + 400) {
    const p = (Date.now() - start) / (seconds * 1000);
    await page.evaluate((y) => window.scrollTo(0, y), Math.round(Math.min(1, p) * 60));
    await page.waitForTimeout(33);
  }
  await cdp.send("Page.stopScreencast");
  await ctx.close();
  // Resample the variable-rate screencast to a constant 30 fps.
  const t0 = shots[0].t;
  let j = 0;
  for (let i = 0; i < seconds * FPS; i++) {
    const want = t0 + i / FPS;
    while (j + 1 < shots.length && shots[j + 1].t <= want) j++;
    fs.writeFileSync(path.join(frames, String(i).padStart(5, "0") + ".jpg"), Buffer.from(shots[j].data, "base64"));
  }
  encodeFrames(frames, path.join(OUT, "02_whofor.mp4"), FPS);
  fs.rmSync(frames, { recursive: true, force: true });
  console.log("captured 02_whofor from", APP, `(${shots.length} screencast frames)`);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  await renderScenes(browser);
  if (!ONLY || "whofor".includes(ONLY)) await captureLanding(browser);
  await browser.close();
})();
