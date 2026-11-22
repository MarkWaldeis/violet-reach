import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { worldFiles } from "../scripts/world-content.mjs";
import { pathMask } from "../src/hydrology.ts";
import type { Slice } from "../src/slice.ts";

const vegetation = ["tree_broadleaf_a", "tree_broadleaf_b", "tree_broadleaf_c", "shrub_round_a", "grass_tuft_a", "fern_cluster_a", "reed_cluster_a"];
const monuments = ["gate_white_a", "column_white_a"];

test("shore path frames the gate and reaches the terrace without the dead uphill spur", () => {
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  for (const [x, z] of [[494.5, 1489.5], [522, 1510], [570, 1495.8], [593.869, 1490.652]]) assert.equal(pathMask(slice.paths, x, z), 1);
  assert.equal(pathMask(slice.paths, 550, 1460), 0);
  assert.equal(pathMask(slice.paths, 530, 1475), 0);
});

test("world content includes real terrain and only registered placed assets", () => {
  const files = worldFiles();
  assert.equal([...files.keys()].filter((p) => p.endsWith(".r16")).length, 256);
  for (const key of ["terrain/manifest.json", "slice.json", "hydrology.json", "placements.json", "assets/crystal_violet_cluster_a.glb", "assets/bridge_arch_a.glb", "assets/lake_shore_a.glb", ...[...vegetation, ...monuments].map((asset) => `assets/${asset}.glb`)]) assert.ok(files.has(key));
  assert.equal([...files.keys()].filter((p) => p.endsWith(".glb")).length, 3 + vegetation.length + monuments.length);
});
for (const asset of ["bridge_arch_a", "lake_shore_a", ...vegetation, ...monuments]) test(`${asset} export contains all three named LODs`, () => {
  const glb = readFileSync(worldFiles().get(`assets/${asset}.glb`)!);
  assert.equal(glb.toString("ascii", 0, 4), "glTF");
  const document = JSON.parse(glb.toString("utf8", 20, 20 + glb.readUInt32LE(12)));
  assert.deepEqual(document.nodes.map((node: { name?: string }) => node.name).filter((name?: string) => name?.startsWith(`${asset}_LOD`)).sort(),
    [`${asset}_LOD0`, `${asset}_LOD1`, `${asset}_LOD2`]);
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
