import assert from "node:assert/strict";
import { test } from "node:test";
import { groundNoise, scatterSurface } from "../src/scatter-surface.ts";

const up: [number, number, number] = [0, 1, 0];
test("MaterialX meadow noise is deterministic, continuous, signed and zero on the integer lattice", () => {
  for (const n of [-12, -1, 0, 5, 130]) assert.equal(Math.abs(groundNoise(n, n + 3)), 0);
  const values = Array.from({ length: 200 }, (_, i) => groundNoise(i * 0.13 - 10, i * 0.31));
  assert.ok(Math.min(...values) < -0.2 && Math.max(...values) > 0.2);
  assert.ok(values.every((v) => Math.abs(v) < 1));
  assert.equal(groundNoise(-7.81, 18.32), groundNoise(-7.81, 18.32));
  assert.ok(Math.abs(groundNoise(1 - 1e-6, 0.3) - groundNoise(1 + 1e-6, 0.3)) < 1e-5);
});
test("meadow scatter follows grass patches while excluding wet shore, rock, soil, hollows and path edges", () => {
  assert.equal(scatterSurface("meadow", 0, 0, up, 1, []), false);
  assert.equal(scatterSurface("meadow", 0, 0, [0.7, Math.sqrt(0.51), 0], 20, []), false);
  assert.equal(scatterSurface("meadow", 0, 0, up, 20, [], 0.5, 2), false);
  let grass = 0, soil = 0;
  for (let x = 0; x < 1000; x += 4) {
    if (scatterSurface("meadow", x, 0, up, 20, [])) grass++; else soil++;
  }
  assert.ok(grass > 15 && soil > 100);
  const paths = [{ width: 2, polyline: [[0, 0], [10, 0]] as [number, number][] }];
  assert.equal(scatterSurface("land", 5, 3, up, 20, paths), false);
  assert.equal(scatterSurface("land", 5, 5, up, 20, paths), true);
  assert.equal(scatterSurface("land", 5, 5, up, 20, paths, 3), false);
  assert.equal(scatterSurface("land", -2, 0, up, 20, paths), false);
});
test("reed profiles allow very shallow water only; land profiles need dry banks", () => {
  assert.equal(scatterSurface("shore", 0, 0, up, -0.1, []), true);
  assert.equal(scatterSurface("shore", 0, 0, up, -0.3, []), true);
  assert.equal(scatterSurface("shore", 0, 0, up, -0.31, []), false);
  assert.equal(scatterSurface("shore", 0, 0, up, 0.15, []), false);
  assert.equal(scatterSurface("shore", 0, 0, up, 1, []), false);
  assert.equal(scatterSurface("shore", 0, 0, [0.5, Math.sqrt(0.75), 0], -0.1, []), false);
  assert.equal(scatterSurface("shore", 0, 0, [0.3, Math.sqrt(0.91), 0], -0.1, []), true);
  assert.equal(scatterSurface("land", 0, 0, up, 10, []), true);
  assert.equal(scatterSurface("land", 0, 0, up, 0, []), false);
});

test("meadow density forms reproducible metre-scale clumps with open gaps", () => {
  const accepted = (x: number, z: number) => scatterSurface("meadow", x, z, up, 20, []);
  let same = 0, transitions = 0;
  for (let x = 0; x < 200; x += 0.2) {
    if (accepted(x, 23) === accepted(x + 0.2, 23)) same++; else transitions++;
    assert.equal(accepted(x, 23), accepted(x, 23));
  }
  assert.ok(transitions > 10 && same > transitions * 4);
});
