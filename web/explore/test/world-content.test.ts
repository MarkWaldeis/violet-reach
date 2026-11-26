import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { worldFiles } from "../scripts/world-content.mjs";
import { pathMask } from "../src/hydrology.ts";
import type { Slice } from "../src/slice.ts";

const vegetation = ["tree_oak_a", "tree_beech_a", "tree_ancient_a", "tree_willow_a", "bush_lush_a", "fern_cluster_a", "fern_lush_a", "reed_cluster_a", "log_fallen_a", "stump_roots_a"];
const monuments = ["gate_white_a", "column_white_a", "stair_terrace_a"];
const pilot = ["boulder_chalk_a", "ruin_wall_a", "trunk_acacia_a", "trunk_acacia_b", "trunk_baobab_a"];
const rocks = ["arch_sandstone_a", "scree_pile_a", "shore_rocks_wet_a", "boulder_chalk_c", "rock_slab_a"];

test("approved spire landmark is slightly buried and the energy core stays out", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const spires = placements.filter((p: { asset: string }) => p.asset === "crystal_spire_a");
  assert.equal(spires.length, 1);
  assert.equal(spires[0].scale, 1);
  assert.ok(spires[0].y_offset < 0 && spires[0].y_offset > -0.5);
  assert.equal(placements.some((p: { asset: string }) => p.asset === "energy_core_a"), false);
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  assert.equal(slice.asset_options?.crystal_spire_a.maxDistance, 1200);
});

test("approved violet accents replace proof placements and are partly buried", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  assert.equal(placements.filter((p: { asset: string }) => p.asset === "crystal_violet_cluster_a").length, 0);
  const crystals = placements.filter((p: { asset: string }) => p.asset === "crystal_cluster_b");
  assert.equal(crystals.length, 3);
  assert.equal(new Set(crystals.map((p: { yaw: number }) => p.yaw)).size, 3);
  for (const p of crystals) {
    assert.ok(p.y_offset < -1 && p.y_offset > -2);
    assert.ok(Math.abs(p.pitch) > 0 && Math.abs(p.roll) > 0);
    assert.ok(Math.hypot(p.x - 534, p.z - 1457) < 35);
  }
});

test("grove pilot replaces nine G2/G4 trees 1:1 with approved fantasy species", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const centre = (p: { scatter?: { polygon?: [number, number][] } }) => {
    const polygon = p.scatter?.polygon ?? [];
    return [polygon.reduce((x, pt) => x + pt[0], 0) / polygon.length, polygon.reduce((z, pt) => z + pt[1], 0) / polygon.length];
  };
  const species = ["tree_oak_a", "tree_beech_a", "tree_ancient_a", "tree_willow_a"];
  const trees = placements.filter((p: { asset: string; scatter?: { seed?: number; polygon?: [number, number][] } }) => {
    if (!species.includes(p.asset)) return false;
    const [cx, cz] = centre(p);
    return cx >= 216 - 1e-6 && cx <= 240 + 1e-6 && cz >= 1520 - 1e-6 && cz <= 1535 + 1e-6;
  });
  assert.equal(trees.length, 9);
  for (const p of trees) {
    const [cx, cz] = centre(p);
    assert.ok(cx >= 216 - 1e-6 && cx <= 240 + 1e-6 && cz >= 1520 - 1e-6 && cz <= 1535 + 1e-6, `${p.asset} at ${cx},${cz} outside the grove pilot rect`);
    assert.equal(p.scatter.count, 1);
    assert.equal(p.scatter.seed >= 24144 && p.scatter.seed <= 24159, true);
  }
  const at = (x: number, z: number) => trees.find((p: { scatter?: { polygon?: [number, number][] } }) => {
    const [cx, cz] = centre(p); return Math.abs(cx - x) < 0.5 && Math.abs(cz - z) < 0.5;
  });
  assert.equal(at(228, 1523)?.asset, "tree_oak_a");
  assert.equal(at(240, 1520)?.asset, "tree_oak_a");
  assert.equal(at(237, 1535)?.asset, "tree_ancient_a");
  assert.equal(at(237, 1526)?.asset, "tree_beech_a");
  const count = (asset: string) => trees.filter((p: { asset: string }) => p.asset === asset).length;
  assert.equal(count("tree_oak_a"), 5);
  assert.equal(count("tree_beech_a"), 3);
  assert.equal(count("tree_ancient_a"), 1);
  assert.equal(count("tree_willow_a"), 0, "the exact water-distance rule assigns no willow inside the elevated pilot rectangle");
  const ranges: Record<string, [number, number]> = { tree_oak_a: [0.95, 1.25], tree_beech_a: [0.95, 1.25], tree_ancient_a: [1.0, 1.1], tree_willow_a: [0.9, 1.15] };
  for (const p of trees) {
    assert.deepEqual(p.scatter.scale, ranges[p.asset as string], `${p.asset} uses the canonical rollout scale range`);
  }
});

test("grove pilot converts only three fern rings near G2/G4 to fern_lush_a", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const centre = (p: { scatter?: { polygon?: [number, number][] } }) => {
    const polygon = p.scatter?.polygon ?? [];
    return [polygon.reduce((x, pt) => x + pt[0], 0) / polygon.length, polygon.reduce((z, pt) => z + pt[1], 0) / polygon.length];
  };
  const ferns = placements.filter((p: { asset: string }) => p.asset === "fern_lush_a");
  assert.equal(ferns.length, 3);
  const g2 = [232.2, 1527.4], g4 = [235.9, 1515.5];
  for (const p of ferns) {
    const [cx, cz] = centre(p);
    assert.ok(Math.hypot(cx - g2[0], cz - g2[1]) < 9 || Math.hypot(cx - g4[0], cz - g4[1]) < 9, `fern_lush_a at ${cx},${cz} is not near G2/G4`);
    assert.deepEqual(p.scatter.scale, [0.85, 1.2]);
    assert.equal(p.scatter.count, 16);
  }
  assert.ok(placements.some((p: { asset: string }) => p.asset === "fern_cluster_a"));
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  for (const asset of ["tree_oak_a", "tree_beech_a", "tree_ancient_a", "tree_willow_a", "fern_lush_a"]) {
    assert.equal(slice.asset_options?.[asset]?.maxLOD, 3);
    assert.equal(slice.asset_options?.[asset]?.lodRatio, asset.startsWith("fern") ? 4 : 6);
  }
});

test("colonnade has only three standing, individually tilted columns", () => {
  const document = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const columns = document.placements.filter((p: { asset: string }) => p.asset === "column_white_a");
  assert.equal(columns.length, 3);
  for (const p of columns) {
    const tilt = Math.acos(Math.cos(p.pitch) * Math.cos(p.roll));
    assert.ok(tilt >= 6 * Math.PI / 180 && tilt <= 10 * Math.PI / 180);
  }
  const distances = columns.flatMap((a: { x: number; z: number }, i: number) => columns.slice(i + 1).map((b: { x: number; z: number }) => Math.hypot(a.x - b.x, a.z - b.z)));
  assert.ok(Math.max(...distances) > Math.min(...distances) * 1.8);
});

test("shore path frames the gate and reaches the terrace without the dead uphill spur", () => {
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  for (const [x, z] of [[494.5, 1489.5], [522, 1510], [570, 1495.8]]) assert.equal(pathMask(slice.paths, x, z), 1);
  assert.equal(pathMask(slice.paths, 550, 1460), 0);
  assert.equal(pathMask(slice.paths, 530, 1475), 0);
});

test("world content includes real terrain and only registered placed assets", () => {
  const files = worldFiles();
  assert.equal([...files.keys()].filter((p) => p.endsWith(".r16")).length, 256);
  for (const key of ["terrain/manifest.json", "slice.json", "hydrology.json", "placements.json", "assets/crystal_cluster_b.glb", "assets/crystal_spire_a.glb", "assets/bridge_arch_a.glb", "assets/lake_shore_a.glb", ...[...vegetation, ...monuments, ...pilot, ...rocks].map((asset) => `assets/${asset}.glb`)]) assert.ok(files.has(key));
  assert.equal([...files.keys()].filter((p) => p.endsWith(".glb")).length, 4 + vegetation.length + monuments.length + pilot.length + rocks.length);
});
for (const asset of ["bridge_arch_a", "lake_shore_a", "crystal_spire_a", ...vegetation, ...monuments, ...pilot, ...rocks]) test(`${asset} export contains the LODs declared in asset.json`, () => {
  const glbPath = worldFiles().get(`assets/${asset}.glb`)!;
  const glb = readFileSync(glbPath);
  assert.equal(glb.toString("ascii", 0, 4), "glTF");
  const document = JSON.parse(glb.toString("utf8", 20, 20 + glb.readUInt32LE(12)));
  const meta = JSON.parse(readFileSync(resolve(dirname(glbPath), "../asset.json"), "utf8")) as { lod_triangles: unknown[] };
  const actual = document.nodes.map((node: { name?: string }) => node.name).filter((name?: string) => name?.startsWith(`${asset}_LOD`)).sort();
  assert.deepEqual(actual, meta.lod_triangles.map((_, lod) => `${asset}_LOD${lod}`));
});
test("world content rejects non-exported and unknown assets, empty placements work, failed gate propagates", () => {
  const repo = mkdtempSync(resolve(tmpdir(), "vr-content-"));
  const write = (path: string, data: string) => writeFileSync(resolve(repo, path), data);
  try {
    for (const p of ["tools", "world/terrain/runtime", "assets/crystals/crystal"]) mkdirSync(resolve(repo, p), { recursive: true });
    write("tools/vr.py", "pass\n");
    write("world/placements.json", '{"placements":[]}');
    assert.equal(worldFiles(repo).size, 3);
    write("world/placements.json", '{"placements":[{"asset":"unknown"}]}');
    assert.throws(() => worldFiles(repo), /Unshippable/);
    write("world/placements.json", '{"placements":[{"asset":"crystal"}]}');
    write("assets/crystals/crystal/asset.json", '{"status":"approved"}');
    assert.throws(() => worldFiles(repo), /not exported/);
    write("tools/vr.py", "raise SystemExit(1)\n");
    assert.throws(() => worldFiles(repo), /Command failed/);
  } finally { rmSync(repo, { recursive: true, force: true }); }
});
