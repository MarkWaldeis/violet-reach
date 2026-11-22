import assert from "node:assert/strict";
import { test } from "node:test";
import { expandPlacements, type ScatterPlacement } from "../src/placements.ts";
import { placementWaterAt, waterSample } from "../src/hydrology.ts";

const entry: ScatterPlacement = { asset: "crystal", scatter: {
  seed: 42, count: 100, rect: { minX: 0, minZ: 0, maxX: 100, maxZ: 100 },
  min_spacing: 2, max_slope: 30, min_height_above_water: 1, max_height_above_water: 20,
  scale: [0.8, 1.2], align_to_slope: true,
} };
const ground = () => ({ height: 185, slope: 10, normal: [0, 1, 0] as [number, number, number] });
const water = () => 180;

test("scatter water reference matches interpolated segment level and width, not the nearest endpoint", () => {
  const polyline: [number, number, number, number][] = [[0, 0, 20, 4], [100, 0, 10, 20]];
  const sample = placementWaterAt({ lakes: [], rivers: [{ name: "Slope", polyline }] });
  assert.equal(sample(75, 2), 12.5);
  assert.equal(waterSample({ lakes: [], segments: [{ a: polyline[0], b: polyline[1] }] }, 75, 2).distance, -6);
  const scatter: ScatterPlacement = { asset: "crystal", scatter: { ...entry.scatter, count: 1, rect: { minX: 74, maxX: 76, minZ: 0, maxZ: 1 } } };
  assert.throws(() => expandPlacements([scatter], () => ({ ...ground(), height: 11 }), sample), /constraints exhausted/);
  const accepted = expandPlacements([scatter], () => ({ ...ground(), height: 15 }), sample);
  assert.ok(accepted.every((p) => p.y - sample(p.x, p.z) >= 1));
  assert.equal(placementWaterAt({ lakes: [], rivers: [] })(0, 0), 0);
});

test("single placement follows terrain plus offset; empty documents produce no instances", () => {
  assert.deepEqual(expandPlacements([], ground, water), []);
  const single = { asset: "crystal", x: 1, z: 2, yaw: 3, pitch: .1, roll: -.2, scale: 1, y_offset: -0.2 };
  assert.deepEqual(expandPlacements([single], ground, water), [{ ...single, y: 184.8 }]);
  assert.throws(() => expandPlacements([single], () => undefined, water), /Missing/);
  assert.deepEqual(expandPlacements([single], () => undefined, water, () => false), []);
});
test("large scatter expansion does not exceed the engine's argument limit", () => {
  const large: ScatterPlacement = { asset: "crystal", scatter: { ...entry.scatter, count: 150000, min_spacing: 0,
    rect: { minX: 0, minZ: 0, maxX: 100000, maxZ: 100000 } } };
  assert.equal(expandPlacements([large], ground, water).length, 150000);
});
test("scatter is seeded, spaced, scaled and optionally slope aligned", () => {
  const a = expandPlacements([entry], ground, water);
  assert.equal(a.length, 100);
  assert.deepEqual(a, expandPlacements([entry], ground, water));
  assert.notDeepEqual(a, expandPlacements([{ ...entry, scatter: { ...entry.scatter, seed: 43 } }], ground, water));
  for (const p of a) {
    assert.ok(p.scale >= 0.8 && p.scale <= 1.2);
    assert.deepEqual(p.normal, [0, 1, 0]);
    for (const q of a) if (p !== q) assert.ok(Math.hypot(p.x - q.x, p.z - q.z) >= 2);
  }
});
test("polygon clipping and rejection constraints are respected", () => {
  const { rect: _, ...s } = entry.scatter;
  const polygon: ScatterPlacement = { asset: "crystal", scatter: { ...s, polygon: [[0, 0], [100, 0], [0, 100]], align_to_slope: false } };
  for (const p of expandPlacements([polygon], ground, water)) { assert.ok(p.x + p.z < 100); assert.equal(p.normal, undefined); }
  assert.throws(() => expandPlacements([entry], () => undefined, water), /Missing/);
  for (const sample of [{ ...ground(), slope: 40 }, { ...ground(), height: 180 }, { ...ground(), height: 210 }]) {
    assert.throws(() => expandPlacements([entry], () => sample, water), /constraints exhausted/);
  }
  assert.throws(() => expandPlacements([{ ...entry, scatter: { ...entry.scatter, min_spacing: 1000 } }], ground, water), /constraints exhausted/);
  assert.deepEqual(expandPlacements([{ ...entry, scatter: { ...entry.scatter, count: 0 } }], ground, water), []);
  assert.throws(() => expandPlacements([entry], ground, water, () => false), /constraints exhausted/);
  for (const p of expandPlacements([entry], ground, water, (x) => x < 50)) assert.ok(p.x < 50);
});

test("surface rejection applies only to scatter and preserves deterministic counts, spacing and slope alignment", () => {
  const accept = (_entry: ScatterPlacement, _ground: ReturnType<typeof ground>, x: number) => x > 60;
  const a = expandPlacements([entry], ground, water, undefined, accept);
  assert.equal(a.length, 100);
  assert.ok(a.every((p) => p.x > 60));
  assert.deepEqual(a, expandPlacements([entry], ground, water, undefined, accept));
  assert.throws(() => expandPlacements([entry], ground, water, undefined, () => false), /constraints exhausted/);
  assert.deepEqual(expandPlacements([], ground, water, undefined, accept), []);
  const single = { asset: "crystal", x: 1, z: 2, yaw: 0, scale: 1 };
  assert.equal(expandPlacements([single], ground, water, undefined, () => false).length, 1);
});
