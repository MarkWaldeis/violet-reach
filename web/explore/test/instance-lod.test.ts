import assert from "node:assert/strict";
import { test } from "node:test";
import { assetRenderOptions, chunkVisible, instanceLOD, instanceTint, lodDistances, spatialChunks } from "../src/instance-lod.ts";

test("asset rendering overrides preserve defaults and validate finite distance, quality and shadow limits", () => {
  assert.deepEqual(assetRenderOptions(2), { maxDistance: 80, lodScale: 1, lodRatio: 3, tintVariation: 0, shadowLODs: 2, maxLOD: Number.MAX_SAFE_INTEGER });
  assert.deepEqual(assetRenderOptions(2, { maxDistance: 100 }, { maxDistance: 30, lodScale: 0.5, shadowLODs: 1, maxLOD: 1 }), { maxDistance: 100, lodScale: 0.5, lodRatio: 3, tintVariation: 0, shadowLODs: 1, maxLOD: 1 });
  for (const options of [{ maxDistance: 0 }, { maxDistance: Infinity }, { lodScale: -1 }, { lodScale: NaN }, { shadowLODs: 1.5 }, { shadowLODs: -1 }, { maxLOD: -1 }, { maxLOD: 1.5 }, { maxLOD: Infinity }]) {
    assert.throws(() => assetRenderOptions(2, {}, options), /Invalid asset/);
  }
  assert.throws(() => assetRenderOptions(0), /Invalid asset/);
  assert.equal(assetRenderOptions(2, { maxLOD: 0 }, { maxLOD: 1 }).maxLOD, 0);
  const a = assetRenderOptions(2, {}, { maxDistance: 60, lodScale: 0.5 });
  const full = lodDistances(2, 3, 900, 57, 60), reduced = lodDistances(2 * a.lodScale, 3, 900, 57, a.maxDistance);
  assert.equal(reduced[0], full[0] / 2);
  assert.equal(reduced[2], 60);
  for (const options of [{ lodRatio: 0.5 }, { lodRatio: NaN }, { tintVariation: -0.1 }, { tintVariation: 1.1 }, { tintVariation: Infinity }]) assert.throws(() => assetRenderOptions(2, {}, options), /Invalid asset/);
  assert.equal(assetRenderOptions(2, { lodRatio: 12, tintVariation: 0.1 }, { lodRatio: 8 }).lodRatio, 12);
  const wide = lodDistances(2, 3, 900, 57, 600, 12), regular = lodDistances(2, 3, 900, 57, 600);
  assert.equal(wide[0], regular[0]);
  assert.equal(wide[1], regular[1] * 4);
  assert.equal(wide[2], 600);
});

test("instance tint is reproducible, bounded and neutral by default", () => {
  assert.deepEqual(instanceTint(1, 2), [1, 1, 1]);
  assert.deepEqual(instanceTint(14, -27, 0.12), instanceTint(14, -27, 0.12));
  assert.notDeepEqual(instanceTint(14, -27, 0.12), instanceTint(15, -27, 0.12));
  for (let x = -20; x < 20; x++) assert.ok(instanceTint(x, x * 0.37, 0.1).every(c => c >= 0.865 && c <= 1.135));
  for (const v of [-1, 2, NaN]) assert.throws(() => instanceTint(0, 0, v), /Invalid instance tint/);
  assert.throws(() => instanceTint(Infinity, 0), /Invalid instance tint/);
});

test("object size, screen resolution, FOV and cutoff determine LOD distances", () => {
  const a = lodDistances(4, 3, 900, 60, 200);
  assert.ok(a[0] < a[1] && a[1] < a[2]);
  assert.equal(a[2], 200);
  assert.equal(lodDistances(8, 3, 900, 60, 200)[0], a[0] * 2);
  assert.equal(lodDistances(4, 3, 1800, 60, 200)[0], a[0] * 2);
  assert.ok(lodDistances(4, 3, 900, 90, 200)[0] < a[0]);
  assert.deepEqual(lodDistances(1, 1, 900, 60, 100), [100]);
  assert.deepEqual(lodDistances(1, 0, 900, 60), []);
});
test("manual LOD selection has hysteresis at every boundary including culling", () => {
  const d = [20, 60, 200];
  assert.equal(instanceLOD(10, d), 0);
  assert.equal(instanceLOD(21, d), 1);
  assert.equal(instanceLOD(21, d, 0), 0);
  assert.equal(instanceLOD(23, d, 0), 1);
  assert.equal(instanceLOD(18, d, 1), 1);
  assert.equal(instanceLOD(17, d, 1), 0);
  assert.equal(instanceLOD(61, d, 1), 1);
  assert.equal(instanceLOD(68, d, 1), 2);
  assert.equal(instanceLOD(201, d), 3);
  assert.equal(instanceLOD(210, d, 2), 2);
  assert.equal(instanceLOD(225, d, 2), 3);
  assert.equal(instanceLOD(190, d, 3), 3);
  assert.equal(instanceLOD(175, d, 3), 2);
  assert.equal(instanceLOD(1000, d, 0), 3);
  assert.equal(instanceLOD(0, d, 3), 0);
  assert.equal(instanceLOD(0, []), 0);
});
test("chunk bounds include vertical relief, scale padding and negative cells", () => {
  const points = [{ x: -1, y: 0, z: 0 }, { x: 0, y: 100, z: 0 }, { x: 63, y: 0, z: 63 }, { x: 64, y: 0, z: 64 }];
  const chunks = spatialChunks(points, () => 10);
  assert.equal(chunks.length, 3);
  assert.equal(chunks.flatMap((c) => c.items).length, 4);
  for (const c of chunks) for (const p of c.items) assert.ok(Math.hypot(p.x - c.centre.x, p.y - c.centre.y, p.z - c.centre.z) + 10 <= c.radius + 1e-8);
  assert.deepEqual(spatialChunks([], () => 0), []);
});
test("chunk culling keeps intersecting spheres and rejects distance and all six frustum sides", () => {
  const planes = [
    { x: 1, y: 0, z: 0, constant: 10 }, { x: -1, y: 0, z: 0, constant: 10 },
    { x: 0, y: 1, z: 0, constant: 10 }, { x: 0, y: -1, z: 0, constant: 10 },
    { x: 0, y: 0, z: 1, constant: 10 }, { x: 0, y: 0, z: -1, constant: 10 },
  ];
  const camera = { x: 0, y: 0, z: 0 };
  const chunk = { centre: camera, radius: 2, items: [] };
  assert.ok(chunkVisible(chunk, camera, planes, 100));
  assert.ok(chunkVisible({ ...chunk, centre: { x: 12, y: 0, z: 0 } }, camera, planes, 10));
  for (const axis of ["x", "y", "z"]) for (const sign of [-1, 1]) {
    assert.equal(chunkVisible({ ...chunk, centre: { ...camera, [axis]: 13 * sign } }, camera, planes, 100), false);
  }
  assert.equal(chunkVisible({ ...chunk, centre: { x: 103, y: 0, z: 0 } }, camera, [], 100), false);
});

test("individual bounds reject offscreen instances in a visible chunk", () => {
  const camera = { x: 0, y: 0, z: 0 }, planes = [{ x: 0, y: 0, z: -1, constant: 0 }];
  const items = [{ x: 0, y: 0, z: -20 }, { x: 0, y: 0, z: 20 }];
  const [chunk] = spatialChunks(items, () => 2, 64).filter((c) => c.centre.z > 0);
  assert.ok(chunkVisible({ centre: camera, radius: 30 }, camera, planes, 100));
  assert.equal(chunkVisible({ centre: items[1], radius: 2 }, camera, planes, Infinity), false);
  assert.equal(chunkVisible({ centre: items[0], radius: 2 }, camera, planes, Infinity), true);
  assert.equal(chunkVisible({ centre: { x: 0, y: 0, z: 1 }, radius: 2 }, camera, planes, Infinity), true);
  assert.equal(chunkVisible(chunk, camera, [], Infinity), true);
});
