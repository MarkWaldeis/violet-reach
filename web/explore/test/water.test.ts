import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { reflector } from "three/tsl";
import { selectWater } from "../src/hydrology.ts";
import { surfaceData } from "../src/surface-data.ts";

const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const {
  WATER_REFLECTION_DISTORTION,
  WATER_REFLECTION_PASS,
  WATER_SHORE_TUNING,
  waterDepthFade,
  waterEdgeFade,
  waterFoamBreakupGate,
  waterFoamPatchGate,
  waterMaterial,
  waterReflectionDistanceScale,
  waterReflectionDistortionScale,
  waterReflectionNormalScale,
  waterReflectionViewScale,
  waterReflectionWaveZone,
} = await import("../src/water.ts");
hooks.deregister();

function shaderScalarConstants(root: unknown) {
  const seen = new Set<object>();
  const walk = (value: unknown) => {
    if (!value || typeof value !== "object" || seen.has(value)) return;
    seen.add(value);
    for (const [key, child] of Object.entries(value)) {
      if (key === "parents") continue;
      if (Array.isArray(child)) for (const entry of child) walk(entry);
      else if (child && typeof child === "object" && (child as { isNode?: boolean }).isNode) walk(child);
    }
  };
  walk(root);
  return new Set([...seen]
    .filter((node) => node.constructor?.name === "ConstNode" && typeof (node as { value?: unknown }).value === "number")
    .map((node) => (node as { value: number }).value));
}

async function testSurface() {
  const bounds = { minX: 0, minZ: 0, maxX: 16, maxZ: 16 };
  const region = selectWater({
    lakes: [{ name: "Lake", water_y: 10, outline: [[2, 2], [14, 2], [14, 14], [2, 14]] }],
    rivers: [],
  }, bounds);
  const surface = await surfaceData(region, {
    bounds,
    centre: { x: 8, z: 8 },
    paths: [],
    spawn: { fly: { x: 8, z: 8, yaw: 0 }, walk: { x: 8, z: 8, yaw: 0 } },
  }, { preloadHeights: async () => {}, fullHeightAt: () => 8 } as never);
  return surface;
}

test("planar reflection pass stays single, bounded and mipmapped; tuning ranges are valid", () => {
  assert.deepEqual(WATER_REFLECTION_PASS, { resolutionScale: 0.15, bounces: false, generateMipmaps: true });
  assert.ok(WATER_REFLECTION_DISTORTION.distanceFarM > WATER_REFLECTION_DISTORTION.distanceNearM);
  assert.ok(WATER_REFLECTION_DISTORTION.steepViewEnd > WATER_REFLECTION_DISTORTION.steepViewStart);
  assert.ok(WATER_REFLECTION_DISTORTION.shoreFadeDepthM > WATER_REFLECTION_DISTORTION.shoreFullDepthM);
  assert.ok(WATER_REFLECTION_DISTORTION.distanceFloor > 0 && WATER_REFLECTION_DISTORTION.distanceFloor < 0.5);
  assert.ok(WATER_REFLECTION_DISTORTION.calmNormalScale < WATER_REFLECTION_DISTORTION.roughNormalScale);
  assert.ok(WATER_REFLECTION_DISTORTION.uvScaleX < 0.18 && WATER_REFLECTION_DISTORTION.uvScaleY < 0.30);
});

test("reflection distortion is distance/view filtered but keeps shallow and ruffled water livelier", () => {
  for (const [d, viewElevation, depth, breeze] of [
    [20, 0.10, 4, 0],
    [180, 0.35, 4, 0.5],
    [500, 0.75, 0.4, 1],
  ]) {
    const scale = waterReflectionDistortionScale(d, viewElevation, depth, breeze);
    assert.ok(scale > 0 && scale <= WATER_REFLECTION_DISTORTION.roughNormalScale + 1e-9, `Scale bounded: ${scale}`);
  }

  assert.equal(waterReflectionDistanceScale(0), 1);
  assert.equal(waterReflectionDistanceScale(WATER_REFLECTION_DISTORTION.distanceFarM), WATER_REFLECTION_DISTORTION.distanceFloor);
  assert.ok(waterReflectionDistanceScale(80) > waterReflectionDistanceScale(220));
  assert.ok(waterReflectionDistanceScale(220) > waterReflectionDistanceScale(500));

  assert.equal(waterReflectionViewScale(0), 1);
  assert.ok(waterReflectionViewScale(0.15) > waterReflectionViewScale(0.65));
  assert.equal(waterReflectionViewScale(WATER_REFLECTION_DISTORTION.steepViewEnd), WATER_REFLECTION_DISTORTION.steepViewFloor);

  const calmDeep = waterReflectionNormalScale(4, 0);
  const breezyDeep = waterReflectionNormalScale(4, 1);
  const shallowCalm = waterReflectionNormalScale(0.1, 0);
  assert.equal(calmDeep, WATER_REFLECTION_DISTORTION.calmNormalScale);
  assert.ok(breezyDeep > calmDeep, "Windrausche bricht stärker als eine ruhige Seemitte");
  assert.ok(shallowCalm > calmDeep, "Flache Uferzone bricht stärker als tiefe Seemitte");
  assert.equal(waterReflectionWaveZone(0, 0), 1);
  assert.equal(waterReflectionWaveZone(WATER_REFLECTION_DISTORTION.shoreFadeDepthM, 0), 0);

  const calmLegacyRatio = WATER_REFLECTION_DISTORTION.uvScaleY * calmDeep / 0.30;
  const roughLegacyRatio = WATER_REFLECTION_DISTORTION.uvScaleY * WATER_REFLECTION_DISTORTION.roughNormalScale / 0.30;
  assert.ok(calmLegacyRatio < 0.32, `ruhige Seemitte <= ca. ein Drittel der alten Y-Verzerrung: ${calmLegacyRatio}`);
  assert.ok(roughLegacyRatio < 0.58, `selbst Ufer/Wellenzone bleibt deutlich unter der alten ungefilterten Verzerrung: ${roughLegacyRatio}`);

  // Lead-Audit-Szenarien: F2 bleibt sichtbar bewegt, H1/F1-Fernsicht wird dagegen kohärent;
  // bei gleichem Abstand bleibt die flache Uferzone spürbar unruhiger als die tiefe Seemitte.
  const nearCalm = waterReflectionDistortionScale(20, 0.15, 4, 0);
  const f2Mid = waterReflectionDistortionScale(180, 0.25, 4, 0.5);
  const h1Far = waterReflectionDistortionScale(600, 0.55, 4, 0.5);
  const f2Shore = waterReflectionDistortionScale(180, 0.25, 0.3, 0.5);
  assert.ok(f2Mid < nearCalm * 0.85, `F2-Distanz muss gedämpft sein: ${f2Mid} vs ${nearCalm}`);
  assert.ok(h1Far < 0.15, `H1-Fernsicht muss kohärent bleiben: ${h1Far}`);
  assert.ok(f2Shore > f2Mid * 1.25, `Uferzone muss stärker brechen als Seemitte: ${f2Shore} vs ${f2Mid}`);
});

test("shore edge and foam gates are soft, bounded and no longer continuous by construction", () => {
  assert.equal(waterEdgeFade(0), 0);
  assert.equal(waterEdgeFade(WATER_SHORE_TUNING.edgeFadeWidthM), 1);
  assert.ok(waterEdgeFade(0.35) > 0 && waterEdgeFade(0.35) < 1);
  assert.ok(waterEdgeFade(0.35) < waterEdgeFade(0.9));
  assert.ok(WATER_SHORE_TUNING.edgeFadeWidthM >= 0.6 && WATER_SHORE_TUNING.edgeFadeWidthM <= 2.0);
  assert.equal(waterDepthFade(0), 0);
  assert.equal(waterDepthFade(WATER_SHORE_TUNING.depthFadeWidthM), 1);
  assert.ok(waterDepthFade(0.5) < 1, "Flachwasser bleibt sichtbar transparent statt einer harten Türkiskante");
  assert.ok(WATER_SHORE_TUNING.depthFadeWidthM > 0.5 && WATER_SHORE_TUNING.depthFadeWidthM <= 1.0);

  assert.equal(waterFoamBreakupGate(WATER_SHORE_TUNING.foamBreakupLow), 0);
  assert.equal(waterFoamBreakupGate(WATER_SHORE_TUNING.foamBreakupHigh), 1);
  assert.equal(waterFoamPatchGate(WATER_SHORE_TUNING.foamPatchLow), 0);
  assert.equal(waterFoamPatchGate(WATER_SHORE_TUNING.foamPatchHigh), 1);
  assert.ok(waterFoamBreakupGate(0.60) > 0 && waterFoamBreakupGate(0.60) < 1);
  assert.ok(waterFoamPatchGate(0.55) > 0 && waterFoamPatchGate(0.55) < 1);
  assert.ok(WATER_SHORE_TUNING.foamContactPeak < 0.78, "Kontaktsaum bleibt unter der früheren Durchgangskontur");
  assert.ok(WATER_SHORE_TUNING.foamMax < 0.88, "Schaumspitzen bleiben unter dem alten harten Maximum");
  assert.ok(WATER_SHORE_TUNING.foamSwashBase < 0.38, "Swash-Taler dürfen wirklich auslaufen");
});

test("water material with planar reflection constructs a clamped distortion UV node without a browser", async () => {
  const surface = await testSurface();
  const reflection = reflector(WATER_REFLECTION_PASS);
  const water = waterMaterial(surface, reflection, 10.03);

  assert.ok(water.maskNode);
  assert.ok(water.opacityNode);
  assert.ok(water.normalNode);
  assert.ok(water.emissiveNode);
  assert.ok(reflection.uvNode, "Planarreflexion behält eine explizite UV");
  assert.equal((reflection.uvNode as { constructor?: { name?: string } }).constructor?.name, "MathNode");
  assert.equal((reflection.uvNode as { method?: string }).method, "clamp");
  assert.ok((reflection.uvNode as { aNode?: unknown }).aNode, "geclamppte UV enthält den verzerrten Sample-Ausdruck");

  // Guard against regressions to the old unfiltered constant multiplier: the exact exported
  // attenuation coefficients must be baked into the reflection-UV graph itself.
  const constants = shaderScalarConstants(reflection.uvNode);
  for (const expected of [
    WATER_REFLECTION_DISTORTION.uvScaleX,
    WATER_REFLECTION_DISTORTION.uvScaleY,
    WATER_REFLECTION_DISTORTION.distanceNearM,
    WATER_REFLECTION_DISTORTION.distanceFarM,
    WATER_REFLECTION_DISTORTION.distanceFloor,
    WATER_REFLECTION_DISTORTION.steepViewFloor,
    WATER_REFLECTION_DISTORTION.calmNormalScale,
    WATER_REFLECTION_DISTORTION.roughNormalScale,
    WATER_REFLECTION_DISTORTION.breezeAgitation,
  ]) assert.ok(constants.has(expected), `Reflexions-UV-Graph enthält Tuningkonstante ${expected}`);

  water.dispose();
  surface.map.dispose();
});
