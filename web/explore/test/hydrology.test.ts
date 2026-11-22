import assert from "node:assert/strict";
import { test } from "node:test";
import { pathMask, polygonDistance, segmentSample, selectWater, waterSample, type Hydrology } from "../src/hydrology.ts";
import { surfaceData } from "../src/surface-data.ts";
import { buildWaterGeometry } from "../src/water-geometry.ts";

const bounds = { minX: 0, minZ: 0, maxX: 8, maxZ: 8 };
const outline: [number, number][] = [[0, 0], [8, 0], [8, 8], [0, 8]];
const lake = { name: "Spiegelsee", water_y: 10, outline };
const region = { lakes: [lake], segments: [{ a: [0, 12, 12, 4], b: [8, 12, 10, 6] }], bounds };

test("lake distance is signed and the visible outline is inset, rivers interpolate width and water height", () => {
  assert.equal(polygonDistance(4, 4, outline), -4);
  assert.equal(polygonDistance(-1, 4, outline), 1);
  assert.deepEqual(waterSample(region, 4, 4), { distance: -1, height: 10, lakeDistance: -4 });
  assert.ok(waterSample(region, 1, 4).distance > 0);
  assert.deepEqual(waterSample(region, 4, 12), { distance: -2.5, height: 11, lakeDistance: 4 });
  assert.deepEqual(segmentSample(2, 2, [1, 1], [1, 1]), { distance: Math.sqrt(2), t: 0 });
});

test("water selection retains the whole Spiegelsee and inflows crossing the region, but excludes distant lakes", () => {
  const hydrology: Hydrology = { lakes: [lake, { name: "Far", water_y: 0, outline: outline.map(([x, z]) => [x + 2000, z]) }], rivers: [
    { name: "Crossing", polyline: [[-200, 4, 15, 4], [200, 4, 10, 5]] },
    { name: "Distant", polyline: [[2000, 0, 15, 4], [2100, 0, 10, 4]] },
  ] };
  const selected = selectWater(hydrology, bounds);
  assert.equal(selected.lakes.length, 1);
  assert.equal(selected.segments.length, 1);
  assert.equal(selectWater(hydrology, { minX: 1000, minZ: 1000, maxX: 1010, maxZ: 1010 }).lakes[0], lake);
  assert.deepEqual(selectWater({ lakes: [], rivers: [] }, bounds).segments, []);
  assert.equal(waterSample({ ...region, lakes: [], segments: [] }, 0, 0).distance, Infinity);
});

test("paths have a full-width centre and soft edges, and omitted/empty paths paint nothing", () => {
  const paths = [{ width: 2, polyline: [[0, 0], [8, 0]] as [number, number][] }];
  assert.equal(pathMask(paths, 4, 0), 1);
  assert.ok(pathMask(paths, 4, 1.2) > 0 && pathMask(paths, 4, 1.2) < 1);
  assert.equal(pathMask(paths, 4, 4), 0);
  assert.equal(pathMask([], 0, 0), 0);
  assert.equal(pathMask(undefined, 0, 0), 0);
});

test("lake triangles and variable-width river ribbons have valid indices, water levels and flow directions", () => {
  const geometry = buildWaterGeometry(region);
  const p = geometry.getAttribute("position"), flow = geometry.getAttribute("flow");
  assert.equal(p.count, 8);
  assert.equal(geometry.index!.count, 12);
  assert.ok(geometry.index!.array.every((i) => i < p.count));
  assert.ok(Math.abs(p.getY(0) - 10.03) < 0.00001);
  assert.ok(Math.abs(p.getY(4) - 12.03) < 0.00001);
  assert.ok(Math.abs(p.getY(6) - 10.03) < 0.00001);
  assert.equal(p.getZ(5) - p.getZ(4), 4);
  assert.equal(p.getZ(7) - p.getZ(6), 6);
  assert.equal(flow.getX(4), 1); assert.equal(flow.getY(4), 0);
  assert.equal(geometry.getAttribute("lake").getX(0), 1);
  assert.equal(geometry.getAttribute("lake").getX(4), 0);
  geometry.dispose();
  const joint = [8, 12, 10, 6];
  const joined = buildWaterGeometry({ ...region, lakes: [], segments: [{ a: [0, 12, 12, 4], b: joint }, { a: joint, b: [8, 20, 8, 4] }] });
  const q = joined.getAttribute("position");
  for (let i = 0; i < 2; i++) for (let axis = 0; axis < 3; axis++) assert.equal(q.array[(2 + i) * 3 + axis], q.array[(4 + i) * 3 + axis]);
  joined.dispose();
  const empty = buildWaterGeometry({ ...region, lakes: [], segments: [{ a: [0, 0, 0, 1], b: [0, 0, 0, 2] }] });
  assert.equal(empty.getAttribute("position").count, 0);
  empty.dispose();
});

test("surface atlas encodes full-resolution ground, water plane, both shore distances, and rejects missing heights", async () => {
  const slice = { bounds, centre: { x: 4, z: 4 }, spawn: { fly: { x: 0, z: 0, yaw: 0 }, walk: { x: 0, z: 0, yaw: 0 } } };
  const terrain = { preloadHeights: async () => {}, fullHeightAt: (x: number) => x };
  const surface = await surfaceData(region, slice, terrain as never);
  const data = surface.map.image.data;
  assert.deepEqual(Array.from(data.slice(16, 20)), [4, 10, -1, -4]);
  surface.map.dispose();
  await assert.rejects(surfaceData(region, slice, { ...terrain, fullHeightAt: () => undefined } as never), /Höhenkachel fehlt/);
});
