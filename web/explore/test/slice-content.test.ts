import assert from "node:assert/strict";
import { test } from "node:test";
import { expandSlicePlacements, parseQAPlacement, slicePlacementEntries } from "../src/slice-content.ts";
import type { InstancePlacement, Placement } from "../src/placements.ts";
import type { Hydrology } from "../src/hydrology.ts";
import type { Slice } from "../src/slice.ts";

const slice: Slice = {
  bounds: { minX: 0, minZ: 0, maxX: 1000, maxZ: 1600 },
  centre: { x: 500, z: 800 },
  spawn: { fly: { x: 500, z: 800, yaw: 0 }, walk: { x: 500, z: 800, yaw: 0 } },
};
// The lake deliberately covers the example position 420,1220: single placements are
// explicit and must still expand there, because water only constrains scatter entries.
const hydrology: Hydrology = {
  lakes: [{ name: "Spiegelsee", water_y: 95, outline: [[300, 1100], [700, 1100], [700, 1500], [300, 1500]] }],
  rivers: [{ name: "Testfluss", polyline: [[0, 100, 98, 20], [1000, 100, 96, 20]] }],
};
const heightAt = (x: number, z: number) => 100 + x * 0.02 + z * 0.01;
const terrain = { fullHeightAt: heightAt };
const documentPlacements: Placement[] = [
  { asset: "crystal_spire_a", x: 500, z: 700, yaw: 1, scale: 1, y_offset: -0.2 },
  { asset: "tree_oak_a", scatter: {
    seed: 42, count: 2, rect: { minX: 200, minZ: 300, maxX: 210, maxZ: 310 },
    min_spacing: 1, max_slope: 60, min_height_above_water: 0.5, max_height_above_water: 10000, scale: [1, 1],
  } },
];
const qaParams = (...values: string[]) => {
  const params = new URLSearchParams();
  for (const value of values) params.append("qaPlacement", value);
  return params;
};
const willows = (instances: InstancePlacement[]) => instances.filter((p) => p.asset === "tree_willow_a");

test("without qaPlacement the entries and the expansion stay exactly unchanged", () => {
  const entries = slicePlacementEntries(documentPlacements, slice.bounds, new URLSearchParams(""));
  assert.deepEqual(entries, documentPlacements);
  assert.deepEqual(slicePlacementEntries(documentPlacements, slice.bounds, new URLSearchParams("cam=1,2,3,4,0&assetDistance=100&stress=0")), documentPlacements);
  assert.deepEqual(
    expandSlicePlacements(entries, slice, terrain, hydrology),
    expandSlicePlacements(documentPlacements, slice, terrain, hydrology),
  );
  // The stress harness sharing the extraction keeps its previous validation and shape.
  assert.throws(() => slicePlacementEntries(documentPlacements, slice.bounds, new URLSearchParams("stress=-1")), /stress/);
  assert.throws(() => slicePlacementEntries(documentPlacements, slice.bounds, new URLSearchParams("stress=100001")), /stress/);
  const stressed = slicePlacementEntries(documentPlacements, slice.bounds, new URLSearchParams("stress=5"));
  assert.equal(stressed.length, documentPlacements.length + 1);
  assert.equal((stressed.at(-1) as { scatter?: { count?: number } }).scatter?.count, 5);
});

test("repeated qaPlacement params append expandable singles in order, y_offset optional", () => {
  const entries = slicePlacementEntries(documentPlacements, slice.bounds,
    qaParams("tree_willow_a,420,1220,0.4,1.2,-0.35", "tree_oak_a, 430 , 1230 , -0.2 , 0.9"));
  assert.equal(entries.length, documentPlacements.length + 2);
  assert.deepEqual(entries.slice(0, documentPlacements.length), documentPlacements);
  assert.deepEqual(entries[documentPlacements.length], { asset: "tree_willow_a", x: 420, z: 1220, yaw: 0.4, scale: 1.2, y_offset: -0.35 });
  assert.deepEqual(entries[documentPlacements.length + 1], { asset: "tree_oak_a", x: 430, z: 1230, yaw: -0.2, scale: 0.9 });
  assert.equal("y_offset" in entries[documentPlacements.length + 1], false, "y_offset key stays absent when omitted");
  const instances = expandSlicePlacements(entries, slice, terrain, hydrology);
  assert.equal(willows(instances).length, 1);
  const [willow] = willows(instances);
  assert.equal(willow.x, 420);
  assert.equal(willow.z, 1220);
  assert.equal(willow.yaw, 0.4);
  assert.equal(willow.scale, 1.2);
  assert.equal(willow.y, heightAt(420, 1220) - 0.35, "terrain height plus exact y_offset, no scatter reseeding");
  const oak = instances.find((p) => p.asset === "tree_oak_a" && p.x === 430)!;
  assert.equal(oak.y, heightAt(430, 1230), "omitted y_offset lands exactly on the terrain");
});

test("malformed field counts, empty fields and invalid asset ids are rejected", () => {
  for (const value of [
    "tree_willow_a,420,1220,0.4",
    "tree_willow_a,420,1220,0.4,1.2,-0.35,9",
    "tree_willow_a,420,1220,0.4,",
    "tree_willow_a,,1220,0.4,1.2",
    ",420,1220,0.4,1.2",
    "tree_willow_a",
    "",
  ]) assert.throws(() => parseQAPlacement(value), /qaPlacement.*asset,x,z,yaw,scale\[,y_offset\] erwartet/, value);
  for (const asset of ["420", "Tree_willow_a", "tree-willow-a", "tree willow", "../tree_willow_a", "tree_willow_a!"]) {
    assert.throws(() => parseQAPlacement(`${asset},420,1220,0.4,1.2`), /qaPlacement.*ungültige Asset-ID/, asset);
  }
  assert.throws(() => slicePlacementEntries(documentPlacements, slice.bounds,
    qaParams("tree_willow_a,420,1220,0.4,1.2,-0.35", "broken")), /qaPlacement "broken"/, "a later broken occurrence fails the whole load");
});

test("nonfinite numerics, non-positive scale and invalid y_offset are rejected", () => {
  for (const value of [
    "tree_willow_a,abc,1220,0.4,1.2",
    "tree_willow_a,NaN,1220,0.4,1.2",
    "tree_willow_a,Infinity,1220,0.4,1.2",
    "tree_willow_a,420,-Infinity,0.4,1.2",
    "tree_willow_a,420,1220,abc,1.2",
    "tree_willow_a,420,1220,NaN,1.2",
  ]) assert.throws(() => parseQAPlacement(value), /qaPlacement.*endliche Zahlen/, value);
  for (const scale of ["0", "-0", "-1", "-0.5", "abc", "NaN", "Infinity", "-Infinity"]) {
    assert.throws(() => parseQAPlacement(`tree_willow_a,420,1220,0.4,${scale}`), /qaPlacement.*scale muss eine positive endliche Zahl sein/, scale);
  }
  for (const offset of ["abc", "NaN", "Infinity", "-Infinity"]) {
    assert.throws(() => parseQAPlacement(`tree_willow_a,420,1220,0.4,1.2,${offset}`), /qaPlacement.*y_offset muss eine endliche Zahl sein/, offset);
  }
  // boundary sanity: tiny positive scales, negative yaw and zero offsets are legitimate
  assert.deepEqual(parseQAPlacement("tree_willow_a,420,1220,-3.1,0.01,0"), { asset: "tree_willow_a", x: 420, z: 1220, yaw: -3.1, scale: 0.01, y_offset: 0 });
  assert.deepEqual(parseQAPlacement("reed_cluster_a,1e2,2.5e2,3.141,2"), { asset: "reed_cluster_a", x: 100, z: 250, yaw: 3.141, scale: 2 });
});

test("QA singles pass through the normal terrain/water/single-placement pipeline", () => {
  const params = qaParams("tree_willow_a,420,1220,0.4,1.2,-0.35");
  const qaInstances = expandSlicePlacements(slicePlacementEntries(documentPlacements, slice.bounds, params), slice, terrain, hydrology);
  // twin proof: the identical pose as a document single expands to the identical instance
  const twin: Placement = { asset: "tree_willow_a", x: 420, z: 1220, yaw: 0.4, scale: 1.2, y_offset: -0.35 };
  const documentInstances = expandSlicePlacements([...documentPlacements, twin], slice, terrain, hydrology);
  assert.deepEqual(willows(qaInstances), willows(documentInstances));
  // the position sits inside the test lake, yet expands: water never gates explicit singles
  assert.equal(willows(qaInstances).length, 1);
  assert.equal(willows(qaInstances)[0].y, heightAt(420, 1220) - 0.35);
  // scatter entries keep their deterministic expansion alongside the QA single
  assert.equal(qaInstances.filter((p) => p.asset === "tree_oak_a").length, 2);
  assert.deepEqual(qaInstances.filter((p) => p.asset === "tree_oak_a"), expandSlicePlacements(documentPlacements, slice, terrain, hydrology).filter((p) => p.asset === "tree_oak_a"));
});

test("slice bounds are not relaxed: out-of-bounds QA singles drop like document singles", () => {
  for (const value of ["tree_willow_a,-0.5,1220,0.4,1.2", "tree_willow_a,420,1600.5,0.4,1.2", "tree_willow_a,1000.5,1220,0.4,1.2"]) {
    assert.deepEqual(expandSlicePlacements(slicePlacementEntries([], slice.bounds, qaParams(value)), slice, terrain, hydrology), [], value);
  }
  for (const value of ["tree_willow_a,0,1220,0.4,1.2", "tree_willow_a,1000,1600,0.4,1.2"]) {
    assert.equal(willows(expandSlicePlacements(slicePlacementEntries([], slice.bounds, qaParams(value)), slice, terrain, hydrology)).length, 1, `${value} on the inclusive boundary`);
  }
  // missing terrain is the same hard error as for document singles
  const missing = { fullHeightAt: () => undefined };
  const instances = slicePlacementEntries([], slice.bounds, qaParams("tree_willow_a,420,1220,0.4,1.2,-0.35"));
  assert.throws(() => expandSlicePlacements(instances, slice, missing, hydrology), /Missing placement terrain: tree_willow_a/);
});
