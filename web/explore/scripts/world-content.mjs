import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const json = (path) => JSON.parse(readFileSync(path, "utf8"));

function gateCheck(repo) {
  const vr = resolve(repo, "tools/vr.py");
  let missing;
  for (const [cmd, args] of [["python3", []], ["python", []], ["py", ["-3"]]]) {
    try {
      return execFileSync(cmd, [...args, vr, "check"], { cwd: repo, stdio: "pipe" });
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      missing = error;
    }
  }
  throw missing;
}

export function worldFiles(repo = root) {
  gateCheck(repo);
  const files = new Map();
  const terrain = resolve(repo, "world/terrain/runtime");
  for (const name of readdirSync(terrain)) {
    if (name === "manifest.json" || /^\d+_\d+\.r16$/.test(name)) files.set(`terrain/${name}`, resolve(terrain, name));
  }
  for (const name of ["hydrology", "slice", "placements"]) files.set(`${name}.json`, resolve(repo, `world/${name}.json`));
  const ids = new Set(json(resolve(repo, "world/placements.json")).placements.map((p) => p.asset));
  for (const category of readdirSync(resolve(repo, "assets"), { withFileTypes: true })) {
    if (!category.isDirectory()) continue;
    const folder = resolve(repo, "assets", category.name);
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      if (!entry.isDirectory() || !ids.has(entry.name)) continue;
      const asset = resolve(folder, entry.name);
      const meta = json(resolve(asset, "asset.json"));
      if (!["exported", "in_game"].includes(meta.status)) throw new Error(`${entry.name}: not exported/in_game`);
      files.set(`assets/${entry.name}.glb`, resolve(asset, "export", `${entry.name}.glb`));
      ids.delete(entry.name);
    }
  }
  if (ids.size) throw new Error(`Unshippable placements: ${[...ids]}`);
  return files;
}

export function worldContent() {
  let building = false;
  return {
    name: "gated-world-content",
    configResolved(config) { building = config.command === "build"; },
    configureServer(server) {
      // Revalidate on each request so a changed approval never keeps shipping in dev.
      server.middlewares.use((req, res, next) => {
        const name = decodeURIComponent((req.url ?? "").split("?")[0]).replace(/^\//, "");
        if (!/^(terrain\/|assets\/|hydrology\.json$|slice\.json$|placements\.json$)/.test(name)) return next();
        try {
          const path = worldFiles().get(name);
          if (!path) { res.statusCode = 404; res.end(); return; }
          res.setHeader("Content-Type", name.endsWith(".json") ? "application/json" : "application/octet-stream");
          res.setHeader("Content-Length", statSync(path).size);
          res.end(readFileSync(path));
        } catch (error) { res.statusCode = 500; res.end(String(error)); }
      });
    },
    buildStart() {
      if (!building) return;
      for (const [fileName, path] of worldFiles()) {
        this.addWatchFile(path);
        this.emitFile({ type: "asset", fileName, source: readFileSync(path) });
      }
    },
  };
}
