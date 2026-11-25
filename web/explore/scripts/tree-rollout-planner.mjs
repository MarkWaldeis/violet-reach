#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { decodeTile, parseManifest, sampleTile, tileKey, worldTile } from "../src/heightfield.ts";
import { planTreeRollout, sampleTreeRolloutPositions } from "../src/tree-rollout-planner.ts";

export function createOfflineTerrain(runtimeDir) {
  const manifest = parseManifest(JSON.parse(readFileSync(resolve(runtimeDir, "manifest.json"), "utf8")));
  const tiles = new Map();
  const fullHeightAt = (x, z) => {
    const coords = worldTile(manifest, x, z);
    const key = tileKey(coords);
    let data = tiles.get(key);
    if (!data) {
      const buffer = readFileSync(resolve(runtimeDir, `${key}.r16`));
      const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
      data = decodeTile(arrayBuffer, manifest);
      tiles.set(key, data);
    }
    return sampleTile(
      data,
      manifest.samples,
      1,
      (x - manifest.originX) / manifest.tileSize - coords.x,
      (z - manifest.originZ) / manifest.tileSize - coords.z,
    );
  };
  return {
    manifest,
    fullHeightAt,
    loadedTileCount: () => tiles.size,
    loadedTiles: () => [...tiles.keys()].sort(),
  };
}

export function loadRolloutWorld(repoRoot) {
  const readJson = (path) => JSON.parse(readFileSync(resolve(repoRoot, path), "utf8"));
  const placementsDocument = readJson("world/placements.json");
  const hydrology = readJson("world/hydrology.json");
  const slice = readJson("world/slice.json");
  const terrain = createOfflineTerrain(resolve(repoRoot, "world/terrain/runtime"));
  return { placementsDocument, hydrology, slice, terrain };
}

export function buildDryRunReport(repoRoot, options = {}) {
  const { placementsDocument, hydrology, slice, terrain } = loadRolloutWorld(repoRoot);
  const positions = sampleTreeRolloutPositions(
    placementsDocument.placements,
    hydrology,
    terrain.fullHeightAt,
    slice.paths ?? [],
    slice.bounds,
  );
  const report = planTreeRollout(positions, options.planner ?? {});
  return {
    ...report,
    offlineInput: {
      placements: "world/placements.json",
      hydrology: "world/hydrology.json",
      slice: "world/slice.json",
      terrain: "world/terrain/runtime/*.r16",
      terrainTilesLoaded: terrain.loadedTileCount(),
      expandedTreePositions: positions.length,
    },
  };
}

function usage() {
  return [
    "Usage: node scripts/tree-rollout-planner.mjs [--repo <path>] [--output <path>] [--compact] [--no-positions]",
    "",
    "Offline deterministic broadleaf-to-fantasy-tree rollout planner.",
    "Default output is the full dry-run JSON report on stdout.  The tool never writes world/placements.json.",
  ].join("\n");
}

export function parseCliArgs(argv) {
  const result = { repo: undefined, output: undefined, compact: false, positions: true, help: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") result.help = true;
    else if (arg === "--compact") result.compact = true;
    else if (arg === "--no-positions") result.positions = false;
    else if (arg === "--repo") result.repo = argv[++i];
    else if (arg === "--output") result.output = argv[++i];
    else throw new Error(`unknown argument: ${arg}`);
  }
  return result;
}

export function runCli(argv, stdout = process.stdout, stderr = process.stderr) {
  const args = parseCliArgs(argv);
  if (args.help) {
    stdout.write(`${usage()}\n`);
    return 0;
  }
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const repoRoot = resolve(args.repo ?? resolve(scriptDir, "../../.."));
  const report = buildDryRunReport(repoRoot);
  if (!args.positions) {
    delete report.positions;
    delete report.changes;
  }
  const json = `${JSON.stringify(report, null, args.compact ? 0 : 2)}\n`;
  if (args.output) writeFileSync(resolve(process.cwd(), args.output), json);
  else stdout.write(json);
  if (args.output) stderr.write(`${args.output}\n`);
  return 0;
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath && invokedPath === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = runCli(process.argv.slice(2));
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
