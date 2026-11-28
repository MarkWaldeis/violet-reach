// Quick probe shots for arbitrary poses (bookmark tuning):
//   node tools/qa/shot.mjs --run <name> [--quality high] [--fov 57] id=x,agl,z,yaw,pitch [id2=...]
// y is metres above ground (agl). Append `,abs` to interpret y as absolute metres instead.
// One browser session, __vr.setCamera per pose.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { ensureServer, launchChrome, openApp, runDir, timestamp, validateBackend, waitReady } from "./lib.mjs";

const poses = [];
const rest = [];
for (const arg of process.argv.slice(2)) (/^[\w-]+=/.test(arg) ? poses : rest).push(arg);
const opts = {};
for (let i = 0; i < rest.length; i += 2) {
  const key = rest[i].replace(/^--/, "");
  if (opts[key] === undefined) opts[key] = rest[i + 1];
  else if (Array.isArray(opts[key])) opts[key].push(rest[i + 1]);
  else opts[key] = [opts[key], rest[i + 1]];
}
if (!poses.length) { console.error("Keine Posen angegeben (id=x,agl,z,yaw,pitch)"); process.exit(2); }
const dir = runDir(opts.run ?? `shot-${timestamp()}`);
const server = await ensureServer();
const { browser, context } = await launchChrome();
let code = 0;
try {
  const parsed = poses.map((p) => {
    const [id, v] = p.split("=");
    const parts = v.split(",");
    if (![5, 6].includes(parts.length) || (parts.length === 6 && parts[5] !== "abs")) throw new Error(`${id}: erwartet x,y,z,yaw,pitch[,abs]`);
    const numbers = parts.slice(0, 5).map(Number);
    if (numbers.some((n) => !Number.isFinite(n))) throw new Error(`${id}: Kamerapose enthält keine endlichen Zahlen`);
    return { id, v: numbers, agl: parts.length === 5 };
  });
  const [first] = parsed;
  const passthrough = Object.fromEntries(Object.entries(opts).filter(([key]) => !["run", "quality", "fov", "qaPlacement"].includes(key)));
  const { page } = await openApp(context, { ...passthrough, hud: 0, freeze: 1, agl: 1, cam: first.v.join(","), fov: opts.fov ?? 57, quality: opts.quality ?? "high", qaPlacement: opts.qaPlacement }, { label: first.id });
  const check = validateBackend(await page.evaluate(() => window.__vr.stats()), false);
  console.log(check.valid ? check.label : `UNGÜLTIG: ${check.reason}`);
  for (const { id, v, agl } of parsed) {
    await page.evaluate(([v, agl]) => window.__vr.setCamera(v[0], v[1], v[2], v[3], v[4], { agl }), [v, agl]);
    await waitReady(page, 120_000, id);
    const s = await page.evaluate(() => window.__vr.stats());
    await writeFile(join(dir, `${id}.stats.json`), JSON.stringify(s, null, 2));
    await page.screenshot({ path: join(dir, `${id}.png`) });
    const treeLods = Object.entries(s.assets?.byAsset ?? {})
      .filter(([asset]) => asset.startsWith("tree_"))
      .map(([asset, v]) => `${asset}:${v.lods.join("/")} r${v.reflections}`)
      .join(" ");
    console.log(`${id}: ${join(dir, `${id}.png`)} agl=${s.camera.agl?.toFixed(2)} y=${s.camera.y.toFixed(1)} tris=${s.triangles} draws=${s.drawCalls} grassTris=${s.grass?.triangles ?? 0} farvegTris=${s.farveg?.triangles ?? 0} farvegInst=${s.farveg?.visibleInstances ?? 0} reflTris=${s.reflection?.triangles ?? 0}${treeLods ? ` trees=${treeLods}` : ""}`);
  }
} catch (error) {
  console.error(error.message ?? error);
  code = 1;
} finally {
  await browser.close();
  await server.stop();
}
process.exit(code);
