import assert from "node:assert/strict";
import { test } from "node:test";
import { chunkVisible, instanceLOD, lodDistances, spatialChunks } from "../src/instance-lod.ts";

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
