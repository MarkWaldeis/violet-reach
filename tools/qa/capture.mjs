// One command for all comparison images (GRAFIK_PLAN.md 6, step 2):
//   node tools/qa/capture.mjs [--run <name>] [--only G1,F2] [--quality high] [--seq] [--webgl] [--timeout <s>]
// Output: C:\Users\<you>\devin-screenshots\violet-reach\<run>\ — <id>.png, <id>_compare.jpg, metrics.json, index.json,
// with --seq also seq_<id>/NNN.png + <id>.mp4 for the walk/fly frame sequences.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  REPO, appURL, bookmarks, camParam, ensureServer, interpolateKeys, launchChrome, openApp, parseArgs, runDir, runPython,
  timestamp, validateBackend, waitReady,
} from "./lib.mjs";

const args = parseArgs(process.argv.slice(2), { run: "value", only: "value", quality: "value", seq: "flag", webgl: "flag", timeout: "value" });
const quality = args.quality ?? "high";
const run = args.run ?? timestamp();
const timeout = Number(args.timeout ?? 180) * 1000;
const doc = bookmarks();
const only = args.only ? new Set(args.only.split(",").map((s) => s.trim()).filter(Boolean)) : undefined;
const selected = doc.bookmarks.filter((b) => !only || only.has(b.id));
if (only) for (const id of only) if (!doc.bookmarks.some((b) => b.id === id)) { console.error(`Unbekanntes Lesezeichen: ${id}`); process.exit(2); }
const dir = runDir(run);
const index = { run, created: new Date().toISOString(), quality, webgl: !!args.webgl, valid: null, backend: null, adapter: null, bookmarks: [], sequences: [], errors: [] };
const writeIndex = () => writeFileSync(join(dir, "index.json"), JSON.stringify(index, null, 2) + "\n");
const query = (pose, fov) => ({ hud: 0, freeze: 1, cam: camParam(pose), agl: 1, fov, quality, webgl: args.webgl ? 1 : undefined });
const pick = (s) => ({ quality: s.quality, frozen: s.frozen, triangles: s.triangles, drawCalls: s.drawCalls, textureBytes: s.textureBytes, terrain: s.terrain, assets: s.assets, camera: s.camera });

console.log(`Lauf ${run} → ${dir}`);
const server = await ensureServer();
const { browser, context } = await launchChrome();
let exitCode = 0;

async function checkBackend(page) {
  const stats = await page.evaluate(() => window.__vr.stats());
  const check = validateBackend(stats, !!args.webgl);
  index.backend = stats.backend;
  index.adapter = stats.adapter;
  index.valid = check.valid;
  index.renderer = check.valid ? check.label : `UNGÜLTIG: ${check.reason}`;
  if (!check.valid) throw Object.assign(new Error(`Lauf UNGÜLTIG: ${check.reason}`), { invalid: true });
  return check;
}

try {
  const jobs = [];
  for (const b of selected) {
    const t0 = Date.now();
    const q = query(b, b.fov ?? 57);
    let page;
    try {
      ({ page } = await openApp(context, q, { timeout, label: b.id }));
      if (index.valid === null) console.log((await checkBackend(page)).label);
      await page.evaluate(() => window.__vr.frame());
      const file = join(dir, `${b.id}.png`);
      await page.screenshot({ path: file, type: "png" });
      const stats = await page.evaluate(() => window.__vr.stats());
      const ref = (b.references ?? []).map((r) => join(REPO, r)).find((p) => existsSync(p));
      jobs.push({ id: b.id, reference: ref ?? null, game: file, compare: join(dir, `${b.id}_compare.jpg`), label: `${b.id} · ${b.label} · ${quality} · ${stats.backend}` });
      index.bookmarks.push({ id: b.id, label: b.label, url: appURL(q), requested: { x: b.x, z: b.z, agl: b.agl, yaw: b.yaw, pitch: b.pitch, fov: b.fov ?? 57 }, references: b.references ?? [], image: `${b.id}.png`, compare: `${b.id}_compare.jpg`, stats: pick(stats), seconds: (Date.now() - t0) / 1000 });
      console.log(`${b.id}: ${b.id}.png (${((Date.now() - t0) / 1000).toFixed(1)} s, ${stats.triangles.toLocaleString("de-DE")} Dreiecke, ${stats.drawCalls} Draws)`);
    } catch (error) {
      if (error.invalid) throw error;
      exitCode = 1;
      index.errors.push({ id: b.id, error: String(error.message ?? error) });
      console.error(`${b.id}: FEHLER ${error.message ?? error}`);
    } finally {
      await page?.close();
    }
  }

  if (args.seq) {
    for (const seq of doc.sequences) {
      const t0 = Date.now();
      const sub = join(dir, `seq_${seq.id}`);
      mkdirSync(sub, { recursive: true });
      const frames = Math.round(seq.seconds * seq.fps);
      let page;
      try {
        ({ page } = await openApp(context, query(seq.keys[0], seq.fov ?? 57), { timeout, label: `seq ${seq.id}` }));
        if (index.valid === null) console.log((await checkBackend(page)).label);
        const perStep = Math.max(1, Math.round(60 / seq.fps)); // render as many frames per step as a 60-Hz display would
        const poses = [];
        for (let i = 0; i < frames; i++) {
          const p = interpolateKeys(seq.keys, i / seq.fps);
          await page.evaluate((p) => window.__vr.setCamera(p.x, p.agl, p.z, p.yaw, p.pitch, { agl: true }), p);
          for (let k = 0; k < perStep; k++) await page.evaluate(() => window.__vr.frame());
          await page.screenshot({ path: join(sub, `${String(i).padStart(3, "0")}.png`), type: "png" });
          poses.push(p);
        }
        const mp4 = join(dir, `${seq.id}.mp4`);
        const ff = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(seq.fps), "-i", join(sub, "%03d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", mp4], { encoding: "utf8" });
        if (ff.status !== 0) throw new Error(`ffmpeg: ${ff.stderr || ff.error}`);
        index.sequences.push({ id: seq.id, label: seq.label, frames, fps: seq.fps, folder: `seq_${seq.id}`, video: `${seq.id}.mp4`, framesPerStep: perStep, poses });
        console.log(`Folge ${seq.id}: ${frames} Bilder + ${seq.id}.mp4 (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
      } catch (error) {
        if (error.invalid) throw error;
        exitCode = 1;
        index.errors.push({ id: `seq_${seq.id}`, error: String(error.message ?? error) });
        console.error(`Folge ${seq.id}: FEHLER ${error.message ?? error}`);
      } finally {
        await page?.close();
      }
    }
  }

  if (jobs.length) {
    const spec = join(dir, "compare_jobs.json");
    writeFileSync(spec, JSON.stringify({ metrics: join(dir, "metrics.json"), jobs }, null, 2));
    await runPython([join(REPO, "tools/qa/compare.py"), spec]);
  }
} catch (error) {
  exitCode = error.invalid ? 3 : 1;
  index.errors.push({ id: "run", error: String(error.message ?? error) });
  console.error(error.message ?? error);
} finally {
  writeIndex();
  await browser.close();
  await server.stop();
}
console.log(exitCode === 0 ? `Fertig: ${dir}` : `Mit Fehlern beendet (Exit ${exitCode}): ${dir}`);
process.exit(exitCode);
