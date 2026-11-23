import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { DoubleSide } from "three/webgpu";
import { selectWater, type Hydrology } from "../src/hydrology.ts";
import { surfaceData } from "../src/surface-data.ts";

const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const { terrainMaterial, waitForGroundTextures } = await import("../src/ground-material.ts");
const { waitForWaterTextures, waterMaterial } = await import("../src/water.ts");
hooks.deregister();

test("ground and water preloading resolve cleanly in Node without browser DOM/fetch", async () => {
  await Promise.all([waitForGroundTextures(50), waitForWaterTextures(50)]);
  const terrainMat = terrainMaterial();
  assert.ok(terrainMat.colorNode);
  assert.ok(terrainMat.normalNode);
  assert.ok(terrainMat.roughnessNode);
  terrainMat.dispose();
});

test("Phase 2 terrain(surface) and transparent Beer-Lambert water material construct cleanly", async () => {
  const bounds = { minX: 0, minZ: 0, maxX: 16, maxZ: 16 };
  const slice = {
    bounds,
    centre: { x: 8, z: 8 },
    paths: [{ width: 3, polyline: [[0, 8], [16, 8]] as [number, number][] }],
    spawn: { fly: { x: 8, z: 8, yaw: 0 }, walk: { x: 8, z: 8, yaw: 0 } },
  };
  const hydrology: Hydrology = {
    lakes: [{ name: "Lake", water_y: 10, outline: [[2, 2], [14, 2], [14, 14], [2, 14]] }],
    rivers: [],
  };
  const region = selectWater(hydrology, bounds);
  const terrain = { preloadHeights: async () => {}, fullHeightAt: () => 8 };
  const surface = await surfaceData(region, slice, terrain as never);

  const ground = terrainMaterial(surface);
  assert.ok(ground.colorNode);
  assert.ok(ground.normalNode);
  assert.ok(ground.roughnessNode);
  ground.dispose();

  const water = waterMaterial(surface);
  assert.equal(water.transparent, true);
  assert.equal(water.depthWrite, false);
  assert.equal(water.side, DoubleSide);
  assert.ok(water.maskNode);
  assert.ok(water.opacityNode);
  assert.ok(water.normalNode);
  assert.ok(water.colorNode);
  assert.ok(water.emissiveNode);
  water.dispose();
  surface.map.dispose();
});
