// Quick probe shots for arbitrary poses (bookmark tuning):
//   node tools/qa/shot.mjs --run <name> [--quality high] [--fov 57] id=x,agl,z,yaw,pitch [id2=...]
// y is metres above ground (agl). One browser session, __vr.setCamera per pose.
import { join } from "node:path";
import { ensureServer, launchChrome, openApp, runDir, timestamp, validateBackend, waitReady } from "./lib.mjs";

const poses = [];
const rest = [];
for (const arg of process.argv.slice(2)) (/^[\w-]+=/.test(arg) ? poses : rest).push(arg);
const opts = {};
for (let i = 0; i < rest.length; i += 2) opts[rest[i].replace(/^--/, "")] = rest[i + 1];
if (!poses.length) { console.error("Keine Posen angegeben (id=x,agl,z,yaw,pitch)"); process.exit(2); }
const dir = runDir(opts.run ?? `shot-${timestamp()}`);
const server = await ensureServer();
const { browser, context } = await launchChrome();
let code = 0;
try {
  const parsed = poses.map((p) => { const [id, v] = p.split("="); return { id, v: v.split(",").map(Number) }; });
  const [first] = parsed;
  const { page } = await openApp(context, { hud: 0, freeze: 1, agl: 1, cam: first.v.join(","), fov: opts.fov ?? 57, quality: opts.quality ?? "high" }, { label: first.id });
  const check = validateBackend(await page.evaluate(() => window.__vr.stats()), false);
  console.log(check.valid ? check.label : `UNGÜLTIG: ${check.reason}`);
  for (const { id, v } of parsed) {
    await page.evaluate((v) => window.__vr.setCamera(v[0], v[1], v[2], v[3], v[4], { agl: true }), v);
    await waitReady(page, 120_000, id);
    const s = await page.evaluate(() => window.__vr.stats());
    await page.screenshot({ path: join(dir, `${id}.png`) });
    console.log(`${id}: ${join(dir, `${id}.png`)} agl=${s.camera.agl?.toFixed(2)} y=${s.camera.y.toFixed(1)} tris=${s.triangles} draws=${s.drawCalls}`);
  }
} catch (error) {
  console.error(error.message ?? error);
  code = 1;
} finally {
  await browser.close();
  await server.stop();
}
process.exit(code);
