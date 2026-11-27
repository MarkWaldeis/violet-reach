import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { AdditiveBlending, DoubleSide, InstancedMesh, Matrix4, PointLight } from "three/webgpu";

const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const {
  MAX_CRYSTAL_GLOWS,
  MAX_LIGHT_COLUMNS,
  createLandmarkEffects,
  crystalGlowQuality,
  deterministicEffectPhase,
  parseSliceEffects,
  selectCrystalPointLights,
  validateSliceEffects,
} = await import("../src/landmark-effects.ts");
hooks.deregister();

const bounds = { minX: 0, minZ: 0, maxX: 100, maxZ: 100 };
const closeTo = (actual: number, expected: number, epsilon = 1e-5) => assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} ≈ ${expected}`);

test("slice.effects parsing normalizes defaults deterministically and keeps the section optional", () => {
  assert.deepEqual(parseSliceEffects(undefined), { light_columns: [], crystal_glows: [] });
  const input = {
    light_columns: [{ x: 1, z: 2, height: 42, radius: 2.5 }],
    crystal_glows: [{ x: 3, z: 4, radius: 1.2, y_offset: 0.7 }],
  };
  const parsed = parseSliceEffects(input, bounds);
  assert.deepEqual(parsed, parseSliceEffects(input, bounds));
  const column = parsed.light_columns[0];
  assert.equal(column.intensity, 1);
  assert.equal(column.violet, 0.35);
  assert.equal(column.y_offset, 0);
  assert.ok(column.phase >= 0 && column.phase <= 1);
  assert.equal(column.phase, deterministicEffectPhase(1, 2));

  const glow = parsed.crystal_glows[0];
  assert.equal(glow.intensity, 1);
  assert.equal(glow.violet, 0.85);
  assert.equal(glow.y_offset, 0.7);
  assert.equal(glow.light, true);
  assert.equal(glow.light_radius, 6);
  assert.equal(glow.light_intensity, 1.8);
  assert.equal(glow.phase, deterministicEffectPhase(3, 4));
  assert.deepEqual(validateSliceEffects(input, bounds), parsed);
});

test("explicit effect fields are preserved, including intentional zero light values", () => {
  const parsed = parseSliceEffects({
    light_columns: [{ id: "gate", x: 10, z: 20, y: 180, y_offset: 0.5, height: 90, radius: 4, intensity: 1.4, violet: 0.2, phase: 0.25 }],
    crystal_glows: [{ id: "shard", x: 30, z: 40, y: 190, y_offset: -0.5, radius: 2, intensity: 0.5, violet: 0.2, phase: 0.75, light: false, light_radius: 0, light_intensity: 0 }],
  }, bounds);
  assert.equal(parsed.light_columns[0].id, "gate");
  assert.equal(parsed.light_columns[0].y, 180);
  assert.equal(parsed.light_columns[0].phase, 0.25);
  assert.equal(parsed.crystal_glows[0].light, false);
  assert.equal(parsed.crystal_glows[0].light_radius, 0);
  assert.equal(parsed.crystal_glows[0].light_intensity, 0);
});

test("malformed, nonfinite, unknown, out-of-range and out-of-bounds entries fail validation", () => {
  const column = { x: 1, z: 2, height: 40, radius: 2 };
  const invalidInputs = [
    null,
    { light_columns: {} },
    { crystal_glows: {} },
    { beams: [] },
    { light_columns: [{ ...column, typo: true }] },
    { light_columns: [{ ...column, height: undefined }] },
    { light_columns: [{ ...column, height: 2 }] },
    { light_columns: [{ ...column, radius: Number.NaN }] },
    { light_columns: [{ ...column, violet: 1.01 }] },
    { light_columns: [{ ...column, phase: -0.01 }] },
    { light_columns: [{ ...column, id: "" }] },
    { light_columns: [{ ...column, x: 101 }] },
    { crystal_glows: [{ x: 1, z: 2, radius: 1, light_radius: -1 }] },
    { crystal_glows: [{ x: 1, z: 2, radius: 1, light: 1 }] },
  ];
  for (const input of invalidInputs) assert.throws(() => parseSliceEffects(input, bounds), /effects/);
  assert.throws(
    () => parseSliceEffects({ light_columns: Array.from({ length: MAX_LIGHT_COLUMNS + 1 }, () => ({ ...column })) }, bounds),
    new RegExp(`at most ${MAX_LIGHT_COLUMNS}`),
  );
  assert.throws(
    () => parseSliceEffects({ crystal_glows: Array.from({ length: MAX_CRYSTAL_GLOWS + 1 }, () => ({ x: 1, z: 2, radius: 1 })) }, bounds),
    new RegExp(`at most ${MAX_CRYSTAL_GLOWS}`),
  );
});

test("crystal quality ladder: low strongly reduced without lights, medium reduced, high/ultra full", () => {
  const low = crystalGlowQuality("low");
  const medium = crystalGlowQuality("medium");
  const high = crystalGlowQuality("high");
  const ultra = crystalGlowQuality("ultra");
  assert.ok(low.haloIntensity > 0 && low.haloIntensity < 0.5);
  assert.equal(low.maxPointLights, 0);
  assert.equal(low.pointLightIntensity, 0);
  assert.ok(medium.haloIntensity < high.haloIntensity);
  assert.ok(medium.haloRadius < high.haloRadius);
  assert.ok(medium.maxPointLights < high.maxPointLights);
  assert.equal(high.haloIntensity, 1);
  assert.equal(high.haloRadius, 1);
  assert.equal(high.pointLightIntensity, 1);
  assert.equal(ultra.haloIntensity, 1);
  assert.ok(ultra.maxPointLights > high.maxPointLights);
  assert.throws(() => crystalGlowQuality("extreme" as never), /quality/);
});

test("point-light selection is sparse, deterministic, strongest-first and stable for ties", () => {
  const { crystal_glows: entries } = parseSliceEffects({
    crystal_glows: [
      { id: "weak", x: 1, z: 1, radius: 1, light_radius: 4, light_intensity: 1 },
      { id: "strong", x: 2, z: 1, radius: 1, light_radius: 5, light_intensity: 2 },
      { id: "middle", x: 3, z: 1, radius: 1, light_radius: 5, light_intensity: 1.5 },
      { id: "disabled", x: 4, z: 1, radius: 1, light: false, light_radius: 80, light_intensity: 10 },
    ],
  }, bounds);
  const selected = selectCrystalPointLights(entries, 2);
  assert.deepEqual(selected.map((entry) => entry.id), ["strong", "middle"]);
  assert.deepEqual(selectCrystalPointLights(entries, 2), selected);
  assert.deepEqual(selectCrystalPointLights(entries, 0), []);
});

test("constructed columns and crystal halos are additive, transparent, depth-write-free and shadowless", () => {
  const input = {
    light_columns: [{ x: 1, z: 2, height: 40, radius: 2, y_offset: 1 }],
    crystal_glows: [{ x: 3, z: 4, radius: 1.5, y_offset: 2, light_radius: 8, light_intensity: 2 }],
  };
  const effects = createLandmarkEffects(input, { quality: "high", bounds, heightAt: () => 100 });
  assert.equal(effects.stats.lightColumns, 1);
  assert.equal(effects.stats.crystalGlows, 1);
  assert.equal(effects.stats.crystalPointLights, 1);
  assert.equal(effects.stats.drawCalls, 3);
  assert.equal(effects.stats.quality, "high");
  assert.ok(effects.stats.triangles > 0 && effects.stats.triangles < 100);

  const meshes = effects.group.children.filter((child) => child instanceof InstancedMesh) as InstancedMesh[];
  assert.equal(meshes.length, 3);
  const veil = meshes.find((mesh) => mesh.name === "light_columns_veil")!;
  const core = meshes.find((mesh) => mesh.name === "light_columns_core")!;
  const halo = meshes.find((mesh) => mesh.name === "crystal_glow_halos")!;
  for (const mesh of [veil, core, halo]) {
    const material = mesh.material as import("three/webgpu").MeshBasicNodeMaterial;
    assert.equal(material.transparent, true);
    assert.equal(material.depthWrite, false);
    assert.equal(material.blending, AdditiveBlending);
    assert.equal(material.forceSinglePass, true);
    assert.ok(material.colorNode);
    assert.ok(material.opacityNode);
    assert.equal(mesh.castShadow, false);
    assert.equal(mesh.receiveShadow, false);
  }
  assert.equal((veil.material as import("three/webgpu").MeshBasicNodeMaterial).side, DoubleSide);
  assert.ok((halo.material as import("three/webgpu").MeshBasicNodeMaterial).positionNode);

  const matrix = new Matrix4();
  veil.getMatrixAt(0, matrix);
  assert.equal(matrix.elements[12], 1);
  assert.equal(matrix.elements[13], 121);
  assert.equal(matrix.elements[14], 2);

  const centres = halo.geometry.getAttribute("aGlowCentre");
  assert.equal(centres.getX(0), 3);
  assert.equal(centres.getY(0), 102);
  assert.equal(centres.getZ(0), 4);
  assert.equal(centres.getW(0), 1.5);

  const lights = effects.group.children.filter((child) => child instanceof PointLight) as PointLight[];
  assert.equal(lights.length, 1);
  assert.equal(lights[0].intensity, 2);
  assert.equal(lights[0].distance, 8);
  assert.equal(lights[0].decay, 2);
  assert.equal(lights[0].castShadow, false);
  assert.equal(lights[0].position.y, 102);
  effects.dispose();
});

test("quality scaling is baked into halos and point-light count/intensity without CPU updates", () => {
  const input = { crystal_glows: [{ x: 3, z: 4, radius: 2, intensity: 1, light_radius: 10, light_intensity: 2 }] };
  const medium = createLandmarkEffects(input, { quality: "medium", bounds, heightAt: () => 100 });
  const mediumHalo = medium.group.children.find((child) => child instanceof InstancedMesh) as InstancedMesh;
  const mediumStyles = mediumHalo.geometry.getAttribute("aGlowStyle");
  const mediumCentres = mediumHalo.geometry.getAttribute("aGlowCentre");
  closeTo(mediumStyles.getX(0), 0.65);
  closeTo(mediumCentres.getW(0), 1.76);
  const mediumLight = medium.group.children.find((child) => child instanceof PointLight) as PointLight;
  assert.equal(mediumLight.intensity, 1);
  assert.equal(mediumLight.distance, 8);
  medium.dispose();

  const low = createLandmarkEffects(input, { quality: "low", bounds, heightAt: () => 100 });
  const lowHalo = low.group.children.find((child) => child instanceof InstancedMesh) as InstancedMesh;
  assert.equal(lowHalo.geometry.getAttribute("aGlowStyle").getX(0), 0.25);
  assert.equal(lowHalo.geometry.getAttribute("aGlowCentre").getW(0), 1.5);
  assert.equal(low.stats.crystalPointLights, 0);
  assert.equal(low.group.children.some((child) => child instanceof PointLight), false);
  low.dispose();

  const many = {
    crystal_glows: Array.from({ length: 10 }, (_, index) => ({ x: index + 1, z: 4, radius: 1, light_radius: 5, light_intensity: 1 })),
  };
  const ultra = createLandmarkEffects(many, { quality: "ultra", bounds, heightAt: () => 100 });
  assert.equal(ultra.stats.crystalPointLights, crystalGlowQuality("ultra").maxPointLights);
  ultra.dispose();
});

test("terrain anchoring is explicit and missing heights fail loudly instead of floating silently", () => {
  const missing = { light_columns: [{ x: 1, z: 2, height: 20, radius: 2 }] };
  assert.throws(
    () => createLandmarkEffects(missing, { quality: "high", bounds, heightAt: () => undefined }),
    /terrain height/,
  );
  const explicit = createLandmarkEffects({
    light_columns: [{ x: 1, z: 2, y: 77, height: 20, radius: 2 }],
  }, { quality: "high", bounds });
  assert.equal(explicit.stats.lightColumns, 1);
  explicit.dispose();
});

test("effect animation is world-time driven and main integrates effects after slice terrain preload", () => {
  const source = readFileSync(new URL("../src/landmark-effects.ts", import.meta.url), "utf8");
  assert.match(source, /worldTime/);
  assert.doesNotMatch(source, /performance\.now|Date\.now|Math\.random/);
  const main = readFileSync(new URL("../src/main.ts", import.meta.url), "utf8");
  assert.match(main, /validateSliceEffects\(slice\.effects, slice\.bounds\)/);
  assert.match(main, /createLandmarkEffects\(effectConfig/);
  assert.match(main, /heightAt: \(x, z\) => terrain\.fullHeightAt\(x, z\)/);
});
