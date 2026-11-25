// One command for the performance report (GRAFIK_PLAN.md 6, step 3 and section 11):
//   node tools/qa/bench.mjs [--run <name>] [--quality high] [--webgl] [--only ground,flight] [--timeout <s>]
// Drives the fixed routes from world/bookmarks.json in real time (pose interpolated from the rAF timestamp),
// collects per-frame times and renderer counters, writes <run>/bench.json and checks web/explore/perf-budget.json.
// Exit codes: 0 ok, 1 error, 3 invalid run (not WebGPU on the AMD GPU), 4 budget violated.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  EXPLORE, bookmarks, camParam, ensureServer, interpolateKeys, launchChrome, openApp, parseArgs, readJSON, runDir,
  timestamp, validateBackend,
} from "./lib.mjs";

const args = parseArgs(process.argv.slice(2), { run: "value", quality: "value", webgl: "flag", only: "value", timeout: "value" });
const quality = args.quality ?? "high";
const run = args.run ?? timestamp();
const timeout = Number(args.timeout ?? 180) * 1000;
const doc = bookmarks();
const routes = doc.routes.filter((r) => !args.only || args.only.split(",").includes(r.id));
const budgetFile = readJSON(join(EXPLORE, "perf-budget.json"));
const budget = budgetFile.levels[quality];
const dir = runDir(run);

const sum = (a) => a.reduce((x, y) => x + y, 0);
const mean = (a) => a.length ? sum(a) / a.length : 0;
const r2 = (n) => Math.round(n * 100) / 100;
function percentile(sorted, p) {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

function summarise(route, records, textureBytes) {
  const times = records.map((r) => r.frameMs);
  const sorted = [...times].sort((a, b) => a - b);
  const worst = sorted.slice(-Math.max(1, Math.ceil(sorted.length * 0.01)));
  const tris = records.map((r) => r.triangles), draws = records.map((r) => r.drawCalls);
  return {
    id: route.id, label: route.label, speed: route.speed, length: route.length, plannedSeconds: route.seconds,
    measuredSeconds: r2(sum(times) / 1000), frames: records.length,
    fpsMean: r2(1000 / mean(times)),
    fps1Low: r2(1000 / mean(worst)),
    longestFrameMs: r2(sorted.at(-1) ?? 0),
    frameMs: { mean: r2(mean(times)), p50: r2(percentile(sorted, 0.5)), p90: r2(percentile(sorted, 0.9)), p95: r2(percentile(sorted, 0.95)), p99: r2(percentile(sorted, 0.99)), max: r2(sorted.at(-1) ?? 0) },
    framesOver: { ">25ms": times.filter((t) => t > 25).length, ">33ms": times.filter((t) => t > 33.4).length, ">50ms": times.filter((t) => t > 50).length },
    cpuMsMean: r2(mean(records.map((r) => r.cpuMs))),
    cpuMsP95: r2(percentile(records.map((r) => r.cpuMs).sort((a, b) => a - b), 0.95)),
    triangles: { max: Math.max(...tris), mean: Math.round(mean(tris)) },
    drawCalls: { max: Math.max(...draws), mean: r2(mean(draws)) },
    textureBytes,
  };
}

function check(result) {
  const violations = [], warnings = [];
  if (!budget) return { violations, warnings: [`Kein Budget für Stufe ${quality} in perf-budget.json`] };
  const fail = (what, limit, value) => violations.push(`${result.id}: ${what} ${value} verletzt Grenze ${limit}`);
  if (budget.fpsMean && result.fpsMean < budget.fpsMean.min - (budget.fpsMean.vsyncTolerance ?? 0)) fail("fpsMean", `≥ ${budget.fpsMean.min}`, result.fpsMean);
  if (budget.fps1Low && result.fps1Low < budget.fps1Low.min) fail("fps1Low", `≥ ${budget.fps1Low.min}`, result.fps1Low);
  if (budget.longestFrameMs && result.longestFrameMs >= budget.longestFrameMs.max) fail("longestFrameMs", `< ${budget.longestFrameMs.max}`, result.longestFrameMs);
  if (budget.drawCalls && result.drawCalls.max > budget.drawCalls.max) fail("drawCalls (max)", `≤ ${budget.drawCalls.max}`, result.drawCalls.max);
  if (budget.textureBytes && result.textureBytes > budget.textureBytes.max) fail("textureBytes", `≤ ${budget.textureBytes.max}`, result.textureBytes);
  const warn = budget.triangles?.warn?.[result.id];
  if (warn && result.triangles.max > warn) warnings.push(`${result.id}: Dreiecke max ${result.triangles.max} über Richtwert ${warn}`);
  return { violations, warnings };
}

console.log(`Messlauf ${run} (${quality}${args.webgl ? ", WebGL2" : ""}) → ${dir}`);
const server = await ensureServer();
const { browser, context } = await launchChrome();
const report = { run, created: new Date().toISOString(), quality, webgl: !!args.webgl, valid: null, renderer: null, backend: null, adapter: null, viewport: "1920x1080", budget: budget ?? null, routes: [], violations: [], warnings: [] };
let exitCode = 0;
try {
  for (const route of routes) {
    const start = route.keys[0];
    const { page } = await openApp(context, { hud: 0, cam: camParam(start), agl: 1, quality, webgl: args.webgl ? 1 : undefined }, { timeout, label: `Strecke ${route.id}` });
    const stats = await page.evaluate(() => window.__vr.stats());
    const verdict = validateBackend(stats, !!args.webgl);
    Object.assign(report, { backend: stats.backend, adapter: stats.adapter, valid: verdict.valid, renderer: verdict.valid ? verdict.label : `UNGÜLTIG: ${verdict.reason}` });
    if (!verdict.valid) throw Object.assign(new Error(`Lauf UNGÜLTIG: ${verdict.reason}`), { invalid: true });
    console.log(`${route.id}: ${verdict.label}; Fahrt ${route.seconds} s …`);
    const records = await page.evaluate(({ keys, seconds, interpolate }) => new Promise((resolve, reject) => {
      const at = new Function(`return (${interpolate})`)();
      const out = [];
      let t0, pose;
      window.__vr.drive((now, last) => {
        try {
          if (t0 === undefined) t0 = now;
          else if (last) out.push({ ...last, x: pose?.x, z: pose?.z, agl: pose?.agl }); // frame just finished, rendered with the previous pose
          const t = (now - t0) / 1000;
          if (t > seconds) { window.__vr.drive(null); resolve(out); return; }
          const p = at(keys, t);
          pose = p;
          window.__vr.setCamera(p.x, p.agl, p.z, p.yaw, p.pitch, { agl: true });
        } catch (error) { window.__vr.drive(null); reject(error); }
      });
    }), { keys: route.keys, seconds: route.seconds, interpolate: interpolateKeys.toString() });
    const after = await page.evaluate(() => window.__vr.stats());
    const result = summarise(route, records, Math.max(stats.textureBytes, after.textureBytes));
    result.records = records;
    result.textureBytesThree = after.textureBytesThree;
    result.textures = after.textures;
    result.textureSizes = after.textureSizes;
    result.geometries = after.geometries;
    report.routes.push(result);
    const { violations, warnings } = check(result);
    report.violations.push(...violations);
    report.warnings.push(...warnings);
    console.log(`${route.id}: ${result.fpsMean} FPS Mittel, 1 % Low ${result.fps1Low}, längstes Bild ${result.longestFrameMs} ms, CPU ${result.cpuMsMean} ms, Dreiecke max ${result.triangles.max.toLocaleString("de-DE")}, Draws max ${result.drawCalls.max}, Textur ${(result.textureBytes / 2 ** 20).toFixed(0)} MiB`);
    await page.close();
  }
  for (const w of report.warnings) console.warn(`Warnung: ${w}`);
  if (report.violations.length) {
    exitCode = 4;
    console.error(`Budget verletzt (${quality}):\n  ${report.violations.join("\n  ")}`);
  } else console.log(`Budget ${quality} eingehalten.`);
} catch (error) {
  exitCode = error.invalid ? 3 : 1;
  report.error = String(error.message ?? error);
  console.error(error.message ?? error);
} finally {
  writeFileSync(join(dir, "bench.json"), JSON.stringify(report, null, 2) + "\n");
  await browser.close();
  await server.stop();
}
console.log(`bench.json: ${join(dir, "bench.json")}`);
process.exit(exitCode);
