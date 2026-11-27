import assert from "node:assert/strict";
import { test } from "node:test";
import { farvegPriorityVisible, parseFarvegPayload, resolveFarvegOptions } from "../src/far-vegetation.ts";

const validInstance = {
  x: 10.5, y: 200.25, z: -30.5, variant: "tree_oak_a", scale: 1.1, yaw: 0.25, priority: 0.8, embed: 1.2,
};

function payload(instances = [validInstance]) {
  return { format: "violet-reach-farveg-json", version: 1, instance_count: instances.length, instances };
}

test("far vegetation payload validates format, ordering, finite fields and variants", () => {
  const parsed = parseFarvegPayload(payload());
  assert.equal(parsed.instances.length, 1);
  assert.equal(parsed.instances[0].variant, "tree_oak_a");
  assert.throws(() => parseFarvegPayload(null), /Objekt/);
  assert.throws(() => parseFarvegPayload({ ...payload(), format: "wrong" }), /format/);
  assert.throws(() => parseFarvegPayload({ ...payload(), version: 2 }), /version/);
  assert.throws(() => parseFarvegPayload({ ...payload(), instance_count: 2 }), /instance_count/);
  for (const patch of [
    { x: NaN }, { y: Infinity }, { z: "0" }, { scale: 0 }, { yaw: NaN }, { priority: 1.1 }, { embed: -0.1 }, { variant: "tree_unknown" },
  ]) assert.throws(() => parseFarvegPayload(payload([{ ...validInstance, ...patch }])), /Instanz 0/);
  assert.throws(() => parseFarvegPayload(payload([
    { ...validInstance, priority: 0.2 }, { ...validInstance, priority: 0.8 },
  ])), /absteigend/);
});

test("far vegetation quality distances and validation are conservative", () => {
  assert.deepEqual(resolveFarvegOptions(1), {
    maxDistance: 3800,
    trunkDistance: 1400,
    distantPriorityCut: 0,
    cellSize: 256,
    tintVariation: 0.09,
  });
  assert.equal(resolveFarvegOptions(0.5).maxDistance, 1900);
  assert.equal(resolveFarvegOptions(1.25).maxDistance, 4750);
  assert.equal(resolveFarvegOptions(1, { maxDistance: 2200 }).maxDistance, 2200);
  for (const scale of [0, -1, NaN, Infinity]) assert.throws(() => resolveFarvegOptions(scale), /Invalid far vegetation/);
  for (const options of [
    { maxDistance: 0 }, { maxDistance: NaN }, { trunkDistance: 0 }, { distantPriorityCut: -0.1 }, { distantPriorityCut: 1.1 }, { tintVariation: 1.1 }, { cellSize: 0 },
  ]) assert.throws(() => resolveFarvegOptions(1, options), /Invalid far vegetation/);
  assert.throws(() => resolveFarvegOptions(1, { maxDistance: 1000, trunkDistance: 1001 }), /Invalid far vegetation/);
});

test("far priority thinning is distance-ramped, deterministic and disabled by default", () => {
  assert.equal(farvegPriorityVisible(0, 5000, 3800, 0), true);
  assert.equal(farvegPriorityVisible(0, 2000, 3800, 0.4), true);
  assert.equal(farvegPriorityVisible(0, 2090, 3800, 0.4), true);
  const halfway = 3800 * 0.55 + 0.5 * 3800 * 0.45;
  assert.equal(farvegPriorityVisible(0.19, halfway, 3800, 0.4), false);
  assert.equal(farvegPriorityVisible(0.21, halfway, 3800, 0.4), true);
  assert.equal(farvegPriorityVisible(0.39, 3800, 3800, 0.4), false);
  assert.equal(farvegPriorityVisible(0.4, 3800, 3800, 0.4), true);
  for (const args of [[NaN, 1, 1, 0], [0, NaN, 1, 0], [0, 1, 0, 0], [0, 1, 1, NaN]]) {
    assert.throws(() => farvegPriorityVisible(...args), /Invalid far vegetation/);
  }
});
