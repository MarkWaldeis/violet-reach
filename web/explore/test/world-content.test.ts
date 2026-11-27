import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { worldFiles } from "../scripts/world-content.mjs";
import { pathMask } from "../src/hydrology.ts";
import { decodeTile, sampleTile, tileKey, worldTile, type TerrainManifest } from "../src/heightfield.ts";
import type { Slice } from "../src/slice.ts";

const vegetation = ["tree_oak_a", "tree_beech_a", "tree_ancient_a", "tree_willow_a", "bush_lush_a", "fern_cluster_a", "fern_lush_a", "reed_cluster_a", "log_fallen_a", "stump_roots_a"];
const monuments = ["gate_white_a", "column_white_a", "stair_terrace_a", "monument_split_disc_a", "monument_rib_crown_a"];
const pilot = ["boulder_chalk_a", "ruin_wall_a", "trunk_acacia_a", "trunk_acacia_b", "trunk_baobab_a"];
const rocks = ["arch_sandstone_a", "scree_pile_a", "shore_rocks_wet_a", "boulder_chalk_c", "rock_slab_a", "cliff_chalk_wall_a", "cliff_chalk_wall_b", "cliff_chalk_corner_a", "rock_pillar_chalk_a"];
const sky = ["skyship_pod_a", "skyship_pod_b"];

const distanceToSegment = (x: number, z: number, [ax, az]: [number, number], [bx, bz]: [number, number]) => {
  const dx = bx - ax, dz = bz - az;
  const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1e-9)));
  return Math.hypot(x - (ax + t * dx), z - (az + t * dz));
};
const distanceToPolyline = (x: number, z: number, polyline: readonly [number, number][]) => {
  let best = Infinity;
  for (let i = 0; i + 1 < polyline.length; i++) best = Math.min(best, distanceToSegment(x, z, polyline[i], polyline[i + 1]));
  return best;
};
const polylineSamples = (polyline: readonly [number, number][], step = 1) => {
  const points: [number, number][] = [];
  for (let i = 0; i + 1 < polyline.length; i++) {
    const [ax, az] = polyline[i], [bx, bz] = polyline[i + 1];
    const steps = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / step));
    for (let j = 0; j <= steps; j++) points.push([ax + (bx - ax) * j / steps, az + (bz - az) * j / steps]);
  }
  return points;
};
function createWorldHeightSampler(files: Map<string, string>) {
  const manifest = JSON.parse(readFileSync(files.get("terrain/manifest.json")!, "utf8")) as TerrainManifest;
  const tiles = new Map<string, Float32Array>();
  return (x: number, z: number) => {
    const coords = worldTile(manifest, x, z), key = tileKey(coords);
    if (!tiles.has(key)) {
      const bytes = readFileSync(files.get(`terrain/${key}.r16`)!);
      const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
      tiles.set(key, decodeTile(buffer, manifest));
    }
    return sampleTile(tiles.get(key)!, manifest.samples, 1, (x - manifest.originX) / manifest.tileSize - coords.x, (z - manifest.originZ) / manifest.tileSize - coords.z);
  };
}

test("western and pit spires form two distinct buried crystal landmarks", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const spires = placements.filter((p: { asset: string }) => p.asset === "crystal_spire_a");
  assert.equal(spires.length, 2, "the composition keeps the western needle and adds the eastern crystal-pit spire");
  const original = spires.find((p: { x: number; z: number }) => p.x === 424 && p.z === 1412);
  assert.ok(original, "the original western Kristallnadel must remain at (424,1412)");
  assert.equal(original.scale, 1);
  assert.ok(original.y_offset < 0 && original.y_offset > -0.5);
  const pit = spires.find((p: { x: number; z: number }) => p.x === 590 && p.z === 1464);
  assert.ok(pit, "the eastern crystal-pit spire is missing");
  assert.ok(pit.scale > 1 && pit.scale < 1.2, "pit spire should read as a large but not oversized second crystal landmark");
  assert.ok(pit.y_offset <= -0.8 && pit.y_offset >= -1.6, "pit spire must be visibly sunk into the slope");
  assert.notEqual(pit.yaw, original.yaw, "the two spires must not repeat the same silhouette orientation");
  assert.equal(placements.some((p: { asset: string }) => p.asset === "energy_core_a"), false);
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  assert.equal(slice.asset_options?.crystal_spire_a.maxDistance, 1200);
});

test("approved violet accents replace proof placements and are partly buried", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  assert.equal(placements.filter((p: { asset: string }) => p.asset === "crystal_violet_cluster_a").length, 0);
  const entries = placements.filter((p: { asset: string }) => p.asset === "crystal_cluster_b");
  const crystals = entries.filter((p: { scatter?: unknown }) => !p.scatter);
  const columnCrystals = crystals.filter((p: { x: number; z: number }) => Math.hypot(p.x - 534, p.z - 1457) < 35);
  assert.equal(columnCrystals.length, 3, "the three buried column crystals remain untouched");
  assert.equal(new Set(columnCrystals.map((p: { yaw: number }) => p.yaw)).size, 3);
  for (const p of columnCrystals) {
    assert.ok(p.y_offset < -1 && p.y_offset > -2);
    assert.ok(Math.abs(p.pitch) > 0 && Math.abs(p.roll) > 0);
  }
  assert.equal(entries.some((p: { scatter?: unknown }) => p.scatter), false, "the phase-6 crystal accents are individual singles, not uncontrolled scatter");
  const easternPit = crystals.filter((p: { x: number; z: number }) => p.x >= 565 && p.x <= 615 && p.z >= 1435 && p.z <= 1495);
  assert.ok(easternPit.length >= 5 && easternPit.length <= 8, `expected a restrained eastern crystal-pit ring, got ${easternPit.length}`);
  assert.ok(new Set(easternPit.map((p: { yaw: number }) => p.yaw)).size >= easternPit.length - 1, "pit crystals repeat their yaw too strongly");
  for (const p of easternPit) {
    assert.ok(p.scale < 0.85, `pit crystal at ${p.x},${p.z} competes with the central pit spire`);
    assert.ok(p.y_offset <= -0.4, `pit crystal at ${p.x},${p.z} is not partly sunken`);
    assert.ok(Math.abs(p.pitch) > 0 && Math.abs(p.roll) > 0, `pit crystal at ${p.x},${p.z} lacks fracture tilt`);
  }
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  const crystalOptions = slice.asset_options?.crystal_cluster_b;
  assert.ok(crystalOptions.maxDistance >= 600 && crystalOptions.maxDistance <= 800);
  assert.equal(crystalOptions.shadowLODs, 1);
});

test("western spire is ringed by a small varied mineral-fracture group", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const group = placements.filter((p: { asset: string; x: number; z: number; scatter?: unknown }) =>
    p.asset === "crystal_cluster_b" && !p.scatter && Math.hypot(p.x - 424, p.z - 1412) < 12);
  assert.ok(group.length >= 3 && group.length <= 5, `expected 3-5 fracture crystals around the western spire, got ${group.length}`);
  assert.equal(new Set(group.map((p: { yaw: number }) => p.yaw)).size, group.length, "fracture crystals use distinct yaws");
  const scales = group.map((p: { scale: number }) => p.scale);
  assert.ok(Math.max(...scales) - Math.min(...scales) >= 0.2, "fracture crystals vary visibly in scale");
  for (const p of group) {
    assert.ok(p.scale < 1, `fracture crystal at ${p.x},${p.z} must stay smaller than the hero spire`);
    assert.ok(p.y_offset <= -0.5, `fracture crystal at ${p.x},${p.z} is not partly sunken`);
    assert.ok(Math.abs(p.pitch) > 0 && Math.abs(p.roll) > 0, `fracture crystal at ${p.x},${p.z} lacks fracture tilt`);
    assert.ok(Math.abs(p.pitch) < 0.3 && Math.abs(p.roll) < 0.3, `fracture crystal at ${p.x},${p.z} tilt is implausible`);
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
  const g2 = [232.2, 1527.4], g4 = [235.9, 1515.5];
  const pilotFerns = ferns.filter((p: { scatter?: { polygon?: [number, number][] } }) => {
    const [cx, cz] = centre(p);
    return Math.hypot(cx - g2[0], cz - g2[1]) < 9 || Math.hypot(cx - g4[0], cz - g4[1]) < 9;
  });
  assert.equal(pilotFerns.length, 3, "exactly three pilot fern rings near G2/G4 convert to fern_lush_a");
  for (const p of pilotFerns) {
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

test("split-disc monument is grounded on a visible island shoal", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const island = placements.filter((p: { asset: string }) => p.asset === "island_shoal_a");
  assert.equal(island.length, 1, "exactly one exported shoal island carries the split-disc monument");
  assert.equal(island[0].x, 680);
  assert.equal(island[0].z, 1561);
  assert.ok(island[0].scale >= 2.8 && island[0].scale <= 3.2, "the shoal must be large enough to remain visible around the monument");
  assert.ok(island[0].y_offset <= -8.1 && island[0].y_offset >= -8.9, "the shoal terraces must emerge around the plinth without swallowing it");
  const monument = placements.find((p: { asset: string; x: number; z: number }) => p.asset === "monument_split_disc_a" && p.x === 680 && p.z === 1561);
  assert.ok(monument, "the split-disc monument is missing from the island centre");
  assert.equal(monument.scale, 1, "the authored 40 m monument scale is sufficient and must not cover the whole shoal");
  assert.equal(monument.yaw, 0.05, "the disc stays oblique enough to show thickness instead of a flat face-on coin");
  assert.equal(monument.y_offset, 4.6);
});

test("ruin field forms a distributed slope band with restrained debris", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const walls = placements.filter((p: { asset: string; scatter?: unknown }) => p.asset === "ruin_wall_a" && !p.scatter);
  const inCore = (p: { x: number; z: number }) => p.x >= 510 && p.x <= 565 && p.z >= 1425 && p.z <= 1475;
  const inWest = (p: { x: number; z: number }) => p.x >= 496 && p.x <= 515 && p.z >= 1478 && p.z <= 1492;
  const inEast = (p: { x: number; z: number }) => p.x >= 574 && p.x <= 606 && p.z >= 1484 && p.z <= 1488;
  const coreWalls = walls.filter((p: { x: number; z: number }) => inCore(p));
  const westWalls = walls.filter((p: { x: number; z: number }) => inWest(p));
  const eastWalls = walls.filter((p: { x: number; z: number }) => inEast(p));
  assert.equal(coreWalls.length, 5, `expected the original colonnade-core ruin walls to remain, got ${coreWalls.length}`);
  assert.equal(westWalls.length, 2, `expected two western downhill ruin-band anchors, got ${westWalls.length}`);
  assert.equal(eastWalls.length, 2, `expected two eastern ruin-band anchors near the crystal pit, got ${eastWalls.length}`);
  assert.equal(walls.length, coreWalls.length + westWalls.length + eastWalls.length, "ruin walls must stay inside the three prescribed slope-band clusters");
  for (const p of walls) {
    assert.ok(p.y_offset <= -0.6, `ruin wall at ${p.x},${p.z} is not visibly settled into the slope`);
    assert.ok(Math.abs(p.pitch ?? 0) <= 0.2 && Math.abs(p.roll ?? 0) <= 0.2, `ruin wall at ${p.x},${p.z} is rotated too strongly for a subtle accent`);
  }
  const accentAssets = ["rock_slab_a", "scree_pile_a", "boulder_chalk_a", "boulder_chalk_c"];
  const accents = placements.filter((p: { asset: string; x: number; z: number; scatter?: unknown }) =>
    accentAssets.includes(p.asset) && !p.scatter && inCore(p));
  assert.ok(accents.length >= 3 && accents.length <= 5, `expected restrained slab/rubble/boulder accents in the ruin core, got ${accents.length}`);
  for (const p of accents) {
    assert.ok(p.scale <= 0.9, `debris accent ${p.asset} at ${p.x},${p.z} is too dominant`);
    assert.ok(p.y_offset < 0, `debris accent ${p.asset} at ${p.x},${p.z} is not slightly embedded`);
    assert.ok(Math.abs(p.pitch ?? 0) <= 0.2 && Math.abs(p.roll ?? 0) <= 0.2, `debris accent ${p.asset} at ${p.x},${p.z} is rotated too strongly`);
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

test("shore path frames the gate and landmark branch paths stay in the realistic width band", () => {
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  for (const [x, z] of [[494.5, 1489.5], [522, 1510], [570, 1495.8], [437.5, 1429], [488, 1444], [240, 1655], [590, 1474]]) assert.equal(pathMask(slice.paths, x, z), 1);
  assert.equal(pathMask(slice.paths, 550, 1460), 0);
  assert.equal(pathMask(slice.paths, 530, 1475), 0);
  assert.equal(slice.paths?.length, 6, "two existing shore paths plus the crystal, ruin, crystal-pit and meadow branches");
  assert.equal(slice.effects?.light_columns?.length, 1, "the gate needs exactly one calibrated light column");
  assert.equal(slice.effects?.light_columns?.[0]?.id, "gate_beam");
  assert.equal(slice.effects?.crystal_glows?.length, 5, "crystal glows should be sparse landmark accents");
  assert.ok(slice.effects?.crystal_glows?.some((glow) => glow.id === "spire_pit"), "the crystal pit needs a calibrated glow anchor");
  assert.equal(slice.asset_options?.reed_cluster_a?.maxDistance, 45, "shore reeds must remain visible beyond the old 12 m pop-in range");
  for (const path of slice.paths ?? []) {
    assert.ok(path.width >= 1.8 && path.width <= 2.4, `path width ${path.width} outside the realistic 1.8-2.4 m band`);
  }
});

test("a narrow spur branches from the main path to the western crystal spire", () => {
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  const spur = slice.paths?.find((p) => p.polyline.length >= 2 && p.polyline[0][0] === 445 && p.polyline[0][1] === 1440 && p.width < 2);
  assert.ok(spur, "no narrow spur branches off the main path at (445,1440)");
  const end = spur.polyline[spur.polyline.length - 1];
  assert.ok(Math.hypot(end[0] - 424, end[1] - 1412) < 0.5, `spur ends at (${end[0]},${end[1]}), not at the western spire`);
  for (const [x, z] of [[437.5, 1429], [429.5, 1419]]) assert.equal(pathMask(slice.paths, x, z), 1);
});

test("ruin path links the main path through the prescribed waypoints to the colonnade", () => {
  const files = worldFiles();
  const slice: Slice = JSON.parse(readFileSync(files.get("slice.json")!, "utf8"));
  const ruin = slice.paths?.find((p) => p.polyline.length >= 6 && p.polyline[0][0] === 440 && p.polyline[0][1] === 1460);
  assert.ok(ruin, "no ruin path branches off the main path at (440,1460)");
  for (const [wx, wz] of [[462, 1452], [488, 1444], [516, 1436], [528, 1445]]) {
    const near = ruin.polyline.some(([x, z]) => Math.hypot(x - wx, z - wz) < 1.5);
    assert.ok(near, `ruin path misses the prescribed waypoint (${wx},${wz})`);
  }
  const end = ruin.polyline[ruin.polyline.length - 1];
  assert.ok(Math.hypot(end[0] - 552, end[1] - 1448) < 2, `ruin path ends at (${end[0]},${end[1]}), not at the eastern columns`);
  assert.ok(ruin.width >= 1.8 && ruin.width <= 2.4);
  for (const [x, z] of [[462, 1452], [488, 1444], [516, 1436], [528, 1445]]) assert.equal(pathMask(slice.paths, x, z), 1);
  const heightAt = createWorldHeightSampler(files);
  for (const [x, z] of polylineSamples(ruin.polyline, 0.75)) {
    assert.ok(heightAt(x, z) > 180, `ruin path enters the Spiegelsee water table at (${x.toFixed(2)},${z.toFixed(2)})`);
  }
});

test("crystal-pit path links the colonnade around the pit rim back to the shore path", () => {
  const files = worldFiles();
  const slice: Slice = JSON.parse(readFileSync(files.get("slice.json")!, "utf8"));
  const pit = slice.paths?.find((p) => p.polyline.length >= 6 && p.polyline[0][0] === 552 && p.polyline[0][1] === 1448);
  assert.ok(pit, "no crystal-pit path branches off at the eastern colonnade");
  assert.equal(pit.width, 1.8);
  for (const [x, z] of [[570, 1456], [583, 1468], [590, 1474], [598, 1484]]) {
    const near = pit.polyline.some(([px, pz]) => Math.hypot(px - x, pz - z) < 1.5);
    assert.ok(near, `crystal-pit path misses the rim waypoint (${x},${z})`);
  }
  const end = pit.polyline[pit.polyline.length - 1];
  assert.ok(Math.hypot(end[0] - 593.869, end[1] - 1490.652) < 1, `crystal-pit path ends at (${end[0]},${end[1]}), not at the shore-path junction`);
  const centreDistance = distanceToPolyline(590, 1464, pit.polyline);
  assert.ok(centreDistance > 4 && centreDistance < 12, `crystal-pit path should skirt the pit rim, not cross the centre (distance ${centreDistance.toFixed(2)})`);
  const heightAt = createWorldHeightSampler(files);
  for (const [x, z] of polylineSamples(pit.polyline, 0.75)) {
    assert.ok(heightAt(x, z) > 190, `crystal-pit path leaves the high dry ruin shelf at (${x.toFixed(2)},${z.toFixed(2)})`);
  }
});

test("meadow path leaves the G3 camera toward the rib crown without crossing water", () => {
  const files = worldFiles();
  const slice: Slice = JSON.parse(readFileSync(files.get("slice.json")!, "utf8"));
  const meadow = slice.paths?.find((p) => p.polyline.length >= 6 && p.polyline[0][0] === 360 && p.polyline[0][1] === 1680);
  assert.ok(meadow, "no meadow path starts at the G3 camera (360,1680)");
  const end = meadow.polyline[meadow.polyline.length - 1];
  const rib = [150, 1830];
  const startDist = Math.hypot(360 - rib[0], 1680 - rib[1]);
  assert.ok(Math.hypot(end[0] - rib[0], end[1] - rib[1]) < startDist * 0.75, "meadow path does not approach the rib crown");
  for (const [x, z] of [[352, 1686], [322, 1668], [240, 1655], [100, 1705]]) assert.equal(pathMask(slice.paths, x, z), 1);
  // the path bows south around the broad baobab trunk at (352,1675) instead of cutting through it
  assert.ok(distanceToPolyline(352, 1675, meadow.polyline) > 7, "meadow path cuts through the baobab trunk");
  const heightAt = createWorldHeightSampler(files);
  for (const [x, z] of polylineSamples(meadow.polyline, 0.75)) {
    assert.ok(heightAt(x, z) > 180.2, `meadow path enters the Spiegelsee water table at (${x.toFixed(2)},${z.toFixed(2)})`);
  }
});

test("no static ruin, rock or crystal singles sit on the new branch paths", () => {
  const slice: Slice = JSON.parse(readFileSync(worldFiles().get("slice.json")!, "utf8"));
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const starts = [[445, 1440], [440, 1460], [552, 1448], [360, 1680]];
  const branches = (slice.paths ?? []).filter((p) => starts.some(([x, z]) => p.polyline[0][0] === x && p.polyline[0][1] === z));
  assert.equal(branches.length, 4);
  const watched = ["ruin_wall_a", "rock_slab_a", "crystal_cluster_b", "crystal_spire_a", "boulder_chalk_a", "boulder_chalk_c", "scree_pile_a"];
  for (const p of placements) {
    if (!watched.includes(p.asset) || p.scatter) continue;
    // The pre-existing spire is the intentional endpoint landmark, not newly placed path debris.
    if (p.asset === "crystal_spire_a" && p.x === 424 && p.z === 1412) continue;
    for (const path of branches) {
      const d = distanceToPolyline(p.x, p.z, path.polyline);
      assert.ok(d > path.width / 2 + 1.2, `${p.asset} at (${p.x},${p.z}) sits on the branch path (distance ${d.toFixed(2)})`);
    }
  }
});

test("targeted lush undergrowth rings reach the acacia grove at the G3 sight axis", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const centre = (p: { scatter?: { polygon?: [number, number][] } }) => {
    const polygon = p.scatter?.polygon ?? [];
    return [polygon.reduce((x, pt) => x + pt[0], 0) / polygon.length, polygon.reduce((z, pt) => z + pt[1], 0) / polygon.length];
  };
  const g3 = [360, 1680];
  const lush = placements.filter((p: { asset: string; scatter?: { polygon?: [number, number][]; count?: number } }) => {
    if (p.asset !== "fern_lush_a" && p.asset !== "bush_lush_a") return false;
    const [cx, cz] = centre(p);
    return Math.hypot(cx - g3[0], cz - g3[1]) < 30;
  });
  assert.ok(lush.length >= 2 && lush.length <= 6, `expected a very sparse set of G3 undergrowth rings, got ${lush.length}`);
  assert.ok(lush.some((p: { asset: string }) => p.asset === "fern_lush_a"), "no fern_lush_a undergrowth near G3");
  assert.ok(lush.some((p: { asset: string }) => p.asset === "bush_lush_a"), "no bush_lush_a undergrowth near G3");
  for (const p of lush) {
    assert.ok((p.scatter?.count ?? 99) <= 8, `undergrowth ring count ${p.scatter?.count} is not restrained`);
  }
  const total = lush.reduce((n, p) => n + (p.scatter?.count ?? 99), 0);
  assert.ok(total <= 15, `G3 undergrowth expands to ${total} instances instead of staying sparse`);
});

test("shore and cliff densification stays sparse and continues existing groups without overlap", () => {
  const { placements } = JSON.parse(readFileSync(worldFiles().get("placements.json")!, "utf8"));
  const shore = placements.filter((p: { asset: string; scatter?: unknown }) => p.asset === "shore_rocks_wet_a" && !p.scatter);
  // The pre-package baseline is 7 shore rocks; the upper bound is the performance/composition guard.
  assert.ok(shore.length > 7 && shore.length <= 16, `expected a sparse continuation of the shore-rock groups, got ${shore.length}`);
  for (const p of shore) {
    const nearest = Math.min(...shore.filter((q: { x: number; z: number }) => q !== p).map((q: { x: number; z: number }) => Math.hypot(p.x - q.x, p.z - q.z)));
    assert.ok(nearest <= 12, `shore rock at ${p.x},${p.z} is isolated instead of continuing a group`);
  }
  const cliffAssets = ["scree_pile_a", "boulder_chalk_a", "boulder_chalk_c"];
  const cliff = placements.filter((p: { asset: string; x: number; z: number; scatter?: unknown }) =>
    cliffAssets.includes(p.asset) && !p.scatter && p.x >= 660 && p.x <= 735 && p.z >= 1175 && p.z <= 1300);
  // The pre-package baseline is 14 cliff-foot pieces; the upper bound prevents broad duplication.
  assert.ok(cliff.length > 14 && cliff.length <= 20, `expected a sparse cliff-foot continuation, got ${cliff.length}`);
  let nearestPair = Infinity;
  for (const [i, p] of cliff.entries()) for (const q of cliff.slice(i + 1)) nearestPair = Math.min(nearestPair, Math.hypot(p.x - q.x, p.z - q.z));
  assert.ok(nearestPair >= 4, `cliff-foot pieces overlap visually (nearest pair ${nearestPair.toFixed(2)} m)`);
});

test("world content includes real terrain and only registered placed assets", () => {
  const files = worldFiles();
  assert.equal([...files.keys()].filter((p) => p.endsWith(".r16")).length, 256);
  for (const key of ["terrain/manifest.json", "slice.json", "hydrology.json", "placements.json", "assets/crystal_cluster_b.glb", "assets/crystal_spire_a.glb", "assets/bridge_arch_a.glb", "assets/lake_shore_a.glb", ...[...vegetation, ...monuments, ...pilot, ...rocks, ...sky].map((asset) => `assets/${asset}.glb`)]) assert.ok(files.has(key));
  assert.equal([...files.keys()].filter((p) => p.endsWith(".glb")).length, 5 + vegetation.length + monuments.length + pilot.length + rocks.length + sky.length);
});
for (const asset of ["bridge_arch_a", "lake_shore_a", "island_shoal_a", "crystal_spire_a", ...vegetation, ...monuments, ...pilot, ...rocks, ...sky]) test(`${asset} export contains the LODs declared in asset.json`, () => {
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
