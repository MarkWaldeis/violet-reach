import assert from "node:assert/strict";
import { test } from "node:test";
import { PerspectiveCamera } from "three/webgpu";
import {
  chooseLOD, decodeTile, parseManifest, sampleTile, selectTiles, worldTile,
  type TerrainManifest,
} from "../src/heightfield.ts";
import { buildTerrainMesh, lodStride, stitchedHeight } from "../src/terrain-mesh.ts";
import { Navigation } from "../src/navigation.ts";

const m: TerrainManifest = {
  version: 1, tilesX: 16, tilesZ: 16, tileSize: 512, samples: 257,
  originX: -4096, originZ: -4096, minHeight: -100, maxHeight: 900,
};

test("the Blender runtime manifest, sample layout and quantization are respected", () => {
  assert.equal(parseManifest(m), m);
  assert.throws(() => parseManifest({ ...m, samples: 256 }), /Manifest/);
  const buffer = new ArrayBuffer(m.samples ** 2 * 2);
  const view = new DataView(buffer);
  view.setUint16(2 * m.samples, 65535, true);
  view.setUint16(2, 257, true);
  const data = decodeTile(buffer, m);
  assert.equal(data[0], m.minHeight);
  assert.equal(data[m.samples], m.maxHeight);
  assert.ok(Math.abs(data[1] - (-100 + 257 * 1000 / 65535)) < 0.00001);
  assert.throws(() => decodeTile(new ArrayBuffer(10), m), /Dateigröße/);
});

test("tile selection is nearest-first, finite and moves across the map", () => {
  const first = selectTiles(m, -4000, -4000);
  const second = selectTiles(m, 4000, 4000);
  assert.deepEqual(first[0].coords, { x: 0, z: 0 });
  assert.deepEqual(second[0].coords, { x: 15, z: 15 });
  assert.ok(first.every((tile, i) => i === 0 || tile.distance >= first[i - 1].distance));
  assert.ok(first.every((tile) => tile.distance < 3600));
  assert.ok(!second.some(({ coords }) => coords.x === 0 && coords.z === 0));
  assert.deepEqual(worldTile(m, 4096, -3584), { x: 15, z: 1 });
});

test("LOD hysteresis prevents churn near the boundary", () => {
  assert.equal(chooseLOD(755), 1);
  assert.equal(chooseLOD(755, 0), 0);
  assert.equal(chooseLOD(845, 0), 1);
  assert.equal(chooseLOD(700, 1), 1);
  assert.equal(chooseLOD(650, 1), 0);
  assert.equal(chooseLOD(2600), 3);
});

test("tiny terrain tiles bound the selection and spawn clearance", () => {
  const small = { ...m, tileSize: 1, tilesX: 8192, tilesZ: 8192 };
  const selected = selectTiles(small, 0, 0);
  assert.ok(selected.length < 450);
  const camera = new PerspectiveCamera();
  const nav = new Navigation(camera, small, () => 40);
  assert.ok(nav.liftToSpawnHeight());
  assert.equal(camera.position.y, 43);
});

test("boost still increases flight speed on 1 m tiles at different frame rates", () => {
  const small = { ...m, tileSize: 1, tilesX: 8192, tilesZ: 8192 };
  const distance = (frames: number, boost: boolean) => {
    const camera = new PerspectiveCamera();
    const nav = new Navigation(camera, small, () => 40);
    nav.keys.add("KeyW");
    if (boost) nav.keys.add("ShiftLeft");
    for (let i = 0; i < frames; i++) nav.update(1 / frames);
    return -camera.position.z;
  };
  assert.ok(distance(30, true) > distance(30, false));
  assert.ok(Math.abs(distance(30, true) - distance(60, true)) < 0.001);
});

test("walking height interpolates both rendered triangles, including edge samples", () => {
  const tile = new Float32Array([0, 5, 10, 15, 20, 25, 30, 35, 100]);
  assert.equal(sampleTile(tile, 3, 2, 0.25, 0.25), 10);
  assert.equal(sampleTile(tile, 3, 2, 0.75, 0.75), 60);
  assert.equal(sampleTile(tile, 3, 2, 1, 1), 100);
});

test("every render LOD stitches to the full-resolution edge without vertical skirts or holes", () => {
  const data = Float32Array.from({ length: m.samples ** 2 }, (_, i) => 50 + i % m.samples);
  const a = buildTerrainMesh(m, { x: 0, z: 0 }, data, 0);
  const b = buildTerrainMesh(m, { x: 0, z: 1 }, data, 3);
  const fine = a.getAttribute("position");
  assert.equal(lodStride(m, 0), 2);
  assert.ok(a.index!.count > 20 * b.index!.count);
  assert.ok(a.index!.array.every((idx) => idx < fine.count));
  for (const geometry of [a, b]) {
    const p = geometry.getAttribute("position"), indices = geometry.index!;
    let area = 0;
    for (let i = 0; i < p.count; i++) assert.equal(p.getY(i), 50 + p.getX(i) / 2);
    for (let i = 0; i < indices.count; i += 3) {
      const [a, b, c] = [indices.getX(i), indices.getX(i + 1), indices.getX(i + 2)];
      const twiceArea = (p.getZ(b) - p.getZ(a)) * (p.getX(c) - p.getX(a)) - (p.getX(b) - p.getX(a)) * (p.getZ(c) - p.getZ(a));
      assert.ok(twiceArea > 0, "all triangles face up and have horizontal area");
      area += twiceArea / 2;
    }
    assert.equal(area, m.tileSize ** 2);
    for (let x = 0; x < m.tileSize; x += 0.5) {
      assert.ok(Math.abs(stitchedHeight(geometry, x, 0)! - 50 - x / 2) < 1e-6);
      assert.ok(Math.abs(stitchedHeight(geometry, x, m.tileSize)! - 50 - x / 2) < 1e-6);
    }
  }
  a.dispose();
  b.dispose();
});

test("flight has clearance, landing reaches eye height, and walk waits for terrain", () => {
  const camera = new PerspectiveCamera();
  const nav = new Navigation(camera, m, (x, z) => z < -48 ? undefined : 40 + x * 0.5);
  assert.ok(nav.liftToSpawnHeight());
  assert.equal(camera.position.y, 200);
  nav.keys.add("KeyW");
  nav.update(0.25);
  assert.ok(camera.position.z < 0);
  nav.keys.clear();
  nav.toggle();
  for (let i = 0; i < 60; i++) nav.update(0.05);
  assert.equal(nav.mode, "walk");
  assert.equal(nav.landing, false);
  assert.equal(camera.position.y, 41.8);
  nav.keys.add("KeyW");
  for (let i = 0; i < 200; i++) nav.update(0.05);
  assert.ok(camera.position.z > -48 && camera.position.z < -47);
  nav.keys.clear();
  nav.toggle();
  nav.keys.add("KeyQ");
  nav.update(0.25);
  assert.equal(camera.position.y, 42.6);
});

test("walk spawn waits for ground then starts at eye height, reset and F preserve controls", () => {
  const camera = new PerspectiveCamera();
  let height: number | undefined;
  const nav = new Navigation(camera, { ...m, spawn: { x: 350, z: 1360, yaw: -1.37 } }, () => height);
  assert.equal(nav.liftToSpawnHeight(true), false);
  height = 188;
  assert.equal(nav.liftToSpawnHeight(true), true);
  assert.equal(nav.mode, "walk");
  assert.equal(camera.position.y, 189.8);
  assert.equal(camera.position.x, 350);
  assert.equal(camera.position.z, 1360);
  assert.equal(camera.rotation.y, -1.37);
  nav.toggle();
  assert.equal(nav.mode, "fly");
  nav.reset();
  assert.equal(nav.mode, "fly");
  assert.equal(nav.liftToSpawnHeight(true), true);
  assert.equal(nav.mode, "walk");
});
