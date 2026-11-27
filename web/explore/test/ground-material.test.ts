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
const {
  evaluateDistantCliffCalm,
  evaluateFarRockMask,
  evaluateMacroGroundBlend,
  evaluateWallStrataWarp,
  terrainMaterial,
  terrainReflectionMaterial,
  waitForGroundTextures,
} = await import("../src/ground-material.ts");
const { waitForWaterTextures, waterMaterial } = await import("../src/water.ts");
hooks.deregister();

test("ground and water preloading resolve cleanly in Node without browser DOM/fetch", async () => {
  await Promise.all([waitForGroundTextures(50), waitForWaterTextures(50)]);
  const terrainMat = terrainMaterial();
  assert.ok(terrainMat.colorNode);
  assert.ok(terrainMat.normalNode);
  assert.ok(terrainMat.roughnessNode);
  terrainMat.dispose();
  const reflMat = terrainReflectionMaterial();
  assert.ok(reflMat.colorNode);
  reflMat.dispose();
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

test("Phase 6 distant rock exposure is slope/height-led and macro weights only modulate it", () => {
  const slopeDeg = (degrees: number) => 1 - Math.cos(degrees * Math.PI / 180);

  for (const macroHint of [0, 0.5, 1]) {
    assert.equal(evaluateFarRockMask(220, slopeDeg(8), macroHint), 0);
    assert.equal(evaluateFarRockMask(220, slopeDeg(30), macroHint), 0);
  }

  const low45MacroLow = evaluateFarRockMask(220, slopeDeg(45), 0);
  const low45MacroHigh = evaluateFarRockMask(220, slopeDeg(45), 1);
  assert.ok(low45MacroHigh > low45MacroLow);
  assert.ok(low45MacroHigh - low45MacroLow <= 0.30);
  assert.ok(evaluateFarRockMask(220, slopeDeg(40), 0.5) < 0.12);
  assert.ok(evaluateFarRockMask(220, slopeDeg(45), 0.5) > 0.55);
  assert.ok(evaluateFarRockMask(220, slopeDeg(50), 0.5) > 0.95);

  assert.equal(evaluateFarRockMask(240, slopeDeg(20), 0.5), 0);
  assert.ok(evaluateFarRockMask(390, slopeDeg(20), 0.5) > 0.24);
  const highCap = evaluateFarRockMask(460, slopeDeg(8), 0.5);
  assert.ok(highCap > 0.35);
  assert.ok(highCap < 0.75);
  assert.ok(evaluateFarRockMask(415, slopeDeg(8), 0.5, 1) > evaluateFarRockMask(415, slopeDeg(8), 0.5, 0));
});

test("Phase 6 strata warp follows signed terrain relief and stays bounded relative to tile scale", () => {
  assert.equal(evaluateWallStrataWarp(64, 1, 0, 0, 0.5), 0);
  assert.ok(evaluateWallStrataWarp(64, 1, 2, 0, 0.5) > 0);
  assert.ok(evaluateWallStrataWarp(64, 1, -2, 0, 0.5) < 0);

  const steepNeutral = evaluateWallStrataWarp(64, 1, 0, 0.3, 0.5);
  assert.ok(Math.abs(steepNeutral - 2.304) < 1e-9);
  const foldedHigh = evaluateWallStrataWarp(64, 1, 0, 0.3, 1);
  assert.ok(Math.abs((foldedHigh - steepNeutral) - 5.12) < 1e-9);

  const maxMacroWarp = Math.abs(evaluateWallStrataWarp(64, 1, 3.5, 1, 1));
  const maxFineWarp = Math.abs(evaluateWallStrataWarp(9.5, 0.45, 3.5, 1, 1));
  assert.ok(maxMacroWarp < 16.0);
  assert.ok(maxFineWarp < 2.25);
});

test("Phase 6 distant stripe calming leaves G7/F4 untouched and reaches full strength only in far views", () => {
  assert.equal(evaluateDistantCliffCalm(80), 0);
  assert.equal(evaluateDistantCliffCalm(220), 0);
  const mid = evaluateDistantCliffCalm(600);
  assert.ok(mid > 0.25);
  assert.ok(mid < 0.75);
  assert.equal(evaluateDistantCliffCalm(950), 1);
  assert.equal(evaluateDistantCliffCalm(1400), 1);
});

test("Phase 6 macro ground colour stays out of close views and carries distant lowland vegetation", () => {
  assert.equal(evaluateMacroGroundBlend(80, 220), 0);
  assert.equal(evaluateMacroGroundBlend(260, 220), 0);
  const mid = evaluateMacroGroundBlend(700, 220);
  assert.ok(mid > 0.18);
  assert.ok(mid < 0.55);
  assert.equal(evaluateMacroGroundBlend(1050, 220), 0.82);
  assert.ok(evaluateMacroGroundBlend(1250, 420) > evaluateMacroGroundBlend(1250, 220));
  assert.ok(evaluateMacroGroundBlend(2400, 700) <= 0.9);
});
