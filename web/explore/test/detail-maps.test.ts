import assert from "node:assert/strict";
import test from "node:test";
import {
  DataTexture, DoubleSide, MeshPhysicalMaterial, MeshPhysicalNodeMaterial, MeshStandardMaterial,
  MeshStandardNodeMaterial, RGBAFormat, UnsignedByteType,
} from "three/webgpu";
import { float, vec3, vec4 } from "three/tsl";
import {
  applyAssetDetailMap, DETAIL_CLASS_TUNING, detailClassForMaterial, detailMapsTestHooks, detailTuningForAsset,
  prepareDetailMapsForAssets,
} from "../src/detail-maps.ts";

function detailTexture(rgba: [number, number, number, number]): DataTexture {
  const tex = new DataTexture(new Uint8Array(rgba), 1, 1, RGBAFormat, UnsignedByteType);
  tex.needsUpdate = true;
  return tex;
}

function makeLoadedDetail(tileM = 1, roughCenter = 0.5) {
  return {
    tileM,
    normalTex: detailTexture([128, 128, 255, 255]),
    roughTex: detailTexture([128, 128, 128, 255]),
    roughCenter,
  };
}

function registerDetailAsset(assetId: string, cls: string, tileM = 1, roughCenter = 0.5): void {
  detailMapsTestHooks.registerAssetClass(assetId, cls);
  detailMapsTestHooks.registerDetailClass(cls, makeLoadedDetail(tileM, roughCenter));
}

function nodeGraphNodes(root: unknown): object[] {
  if (!root || typeof root !== "object") return [];
  const seen = new Set<object>();
  const stack: object[] = [root];
  while (stack.length && seen.size < 1000) {
    const current = stack.pop()!;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const value of Object.values(current)) {
      if (!value || typeof value !== "object") continue;
      if (Array.isArray(value)) {
        for (const item of value) {
          if (item && typeof item === "object") stack.push(item);
        }
      } else {
        stack.push(value);
      }
    }
  }
  return [...seen];
}

function nodeGraphContains(root: unknown, needle: unknown): boolean {
  return nodeGraphNodes(root).includes(needle as object);
}

function nodeGraphHasAlphaSplit(root: unknown): boolean {
  return nodeGraphNodes(root).some((node) => {
    const split = node as { isSplitNode?: boolean; components?: string };
    return split.isSplitNode === true && (split.components === "a" || split.components === "w");
  });
}

test("detail-maps resolves safely in Node without browser fetch and preserves base material", async () => {
  await prepareDetailMapsForAssets(["boulder_chalk_a", "ruin_wall_a", "trunk_acacia_a"]);
  const base = new MeshStandardMaterial({ alphaTest: 0.5, roughness: 0.85 });
  const result = applyAssetDetailMap(base, "boulder_chalk_a");
  assert.equal(result, base);
  assert.equal(result.alphaTest, 0.5);
});

test("mixed foliage assets keep leaf detail and use bark detail on woody primitives", () => {
  assert.equal(detailClassForMaterial("foliage", "V3_mat_foliage_tree_meadow_oak"), "foliage");
  assert.equal(detailClassForMaterial("foliage", "tree_oak_a_LOD1_foliage"), "foliage");
  assert.equal(detailClassForMaterial("foliage", "V3_mat_bark_tree_meadow_oak"), "bark");
  assert.equal(detailClassForMaterial("foliage", "trunk_acacia_wood"), "bark");
  assert.equal(detailClassForMaterial("bark", "Material_0"), "bark");
  assert.equal(detailClassForMaterial(undefined, "V3_mat_bark_tree_meadow_oak"), undefined);
});

test("detail patch clones once per base material/class, preserves alpha/PBR flags and never mutates the base", () => {
  detailMapsTestHooks.reset();
  registerDetailAsset("unit_rock", "rock_chalk", 1, 0.85);

  const albedoMap = detailTexture([200, 180, 160, 128]);
  const base = new MeshStandardMaterial({ alphaTest: 0.5, roughness: 0.85, opacity: 0.72, transparent: true });
  base.map = albedoMap;
  base.depthWrite = false;
  base.depthTest = false;
  base.alphaHash = true;
  base.colorWrite = false;
  base.alphaToCoverage = true;
  base.side = DoubleSide;
  const baseColorHex = base.color.getHex();

  const detailed = applyAssetDetailMap(base, "unit_rock");
  assert.notEqual(detailed, base);
  assert.ok(detailed instanceof MeshStandardNodeMaterial);
  assert.equal(detailed.alphaTest, 0.5);
  assert.equal(detailed.depthWrite, false);
  assert.equal(detailed.depthTest, false);
  assert.equal(detailed.opacity, 0.72);
  assert.equal(detailed.alphaHash, true);
  assert.equal(detailed.colorWrite, false);
  assert.equal(detailed.alphaToCoverage, true);
  assert.equal(detailed.side, DoubleSide);
  assert.equal((detailed as MeshStandardNodeMaterial).map, albedoMap);
  assert.ok((detailed as MeshStandardNodeMaterial).colorNode, "detail patch installs a diffuse modulation node");
  assert.ok(nodeGraphHasAlphaSplit((detailed as MeshStandardNodeMaterial).colorNode), "diffuse modulation carries the original alpha channel");

  assert.equal(base.color.getHex(), baseColorHex);
  assert.equal(base.roughness, 0.85);
  assert.equal(base.opacity, 0.72);
  assert.equal(base.map, albedoMap);
  assert.equal(applyAssetDetailMap(base, "unit_rock"), detailed);

  const otherBase = new MeshStandardMaterial({ roughness: 0.85 });
  assert.notEqual(applyAssetDetailMap(otherBase, "unit_rock"), detailed);
  detailMapsTestHooks.reset();
});

test("patched-material cache is keyed by detail class as well as base material", () => {
  detailMapsTestHooks.reset();
  detailMapsTestHooks.registerAssetClass("unit_tree", "foliage");
  detailMapsTestHooks.registerDetailClass("foliage", makeLoadedDetail(0.15, 0.55));
  detailMapsTestHooks.registerDetailClass("bark", makeLoadedDetail(0.6, 0.9));

  const base = new MeshStandardMaterial({ roughness: 0.8 });
  base.name = "V3_mat_foliage_tree_meadow_oak";
  const leafDetail = applyAssetDetailMap(base, "unit_tree");
  assert.notEqual(leafDetail, base);
  assert.equal(applyAssetDetailMap(base, "unit_tree"), leafDetail);

  base.name = "V3_mat_bark_tree_meadow_oak";
  const barkDetail = applyAssetDetailMap(base, "unit_tree");
  assert.notEqual(barkDetail, base);
  assert.notEqual(barkDetail, leafDetail);
  assert.equal(applyAssetDetailMap(base, "unit_tree"), barkDetail);

  base.name = "V3_mat_foliage_tree_meadow_oak";
  assert.equal(applyAssetDetailMap(base, "unit_tree"), leafDetail);
  detailMapsTestHooks.reset();
});

test("flattened standard crystal exports become physical and keep only restrained emission", () => {
  detailMapsTestHooks.reset();
  registerDetailAsset("unit_crystal_flat", "crystal", 0.4, 0.25);

  const base = new MeshStandardMaterial({ roughness: 0.24 });
  base.emissive.setRGB(0.8, 0.4, 1.0);
  const detailed = applyAssetDetailMap(base, "unit_crystal_flat");
  assert.ok(detailed instanceof MeshPhysicalNodeMaterial);
  const physical = detailed as MeshPhysicalNodeMaterial;
  assert.equal(physical.clearcoat, 0.55);
  assert.equal(physical.clearcoatRoughness, 0.08);
  assert.equal(physical.ior, 1.6);
  for (const channel of ["r", "g", "b"] as const) {
    assert.ok(Math.abs(physical.emissive[channel] - base.emissive[channel] * 0.18) < 1e-6);
  }
  assert.equal(base.emissive.r, 0.8);
  assert.equal(base.emissive.g, 0.4);
  assert.equal(base.emissive.b, 1.0);
  detailMapsTestHooks.reset();
});

test("physical crystal materials keep transmission and clearcoat in a physical node clone", () => {
  detailMapsTestHooks.reset();
  registerDetailAsset("unit_crystal", "crystal", 0.4, 0.25);

  const base = new MeshPhysicalMaterial({ roughness: 0.24, transmission: 0.42, clearcoat: 0.35, clearcoatRoughness: 0.18, ior: 1.48 });
  const detailed = applyAssetDetailMap(base, "unit_crystal");
  assert.ok(detailed instanceof MeshPhysicalNodeMaterial);
  assert.equal((detailed as MeshPhysicalNodeMaterial).transmission, 0.42);
  assert.equal((detailed as MeshPhysicalNodeMaterial).clearcoat, 0.35);
  assert.equal((detailed as MeshPhysicalNodeMaterial).clearcoatRoughness, 0.18);
  assert.equal((detailed as MeshPhysicalNodeMaterial).ior, 1.48);
  assert.equal(base.transmission, 0.42);
  assert.equal(base.clearcoat, 0.35);
  detailMapsTestHooks.reset();
});

test("existing node material color, roughness and normal graphs are composed rather than discarded", () => {
  detailMapsTestHooks.reset();
  registerDetailAsset("unit_monument", "stone_white", 0.5, 0.78);

  const base = new MeshStandardNodeMaterial({ roughness: 0.66 });
  const originalColorNode = vec4(0.8, 0.72, 0.6, 0.64);
  const originalRoughnessNode = float(0.66);
  const originalNormalNode = vec3(0.1, 0.2, 0.9).normalize();
  base.colorNode = originalColorNode;
  base.roughnessNode = originalRoughnessNode;
  base.normalNode = originalNormalNode;

  const detailed = applyAssetDetailMap(base, "unit_monument") as MeshStandardNodeMaterial;
  assert.notEqual(detailed, base);
  assert.notEqual(detailed.colorNode, originalColorNode);
  assert.notEqual(detailed.roughnessNode, originalRoughnessNode);
  assert.notEqual(detailed.normalNode, originalNormalNode);
  assert.ok(nodeGraphHasAlphaSplit(detailed.colorNode), "detailed color keeps an explicit alpha split");
  assert.ok(nodeGraphContains(detailed.colorNode, originalColorNode), "detailed color keeps the original diffuse/alpha node");
  assert.ok(nodeGraphContains(detailed.roughnessNode, originalRoughnessNode), "detailed roughness keeps the original roughness node");
  assert.ok(nodeGraphContains(detailed.normalNode, originalNormalNode), "detailed normal keeps the original normal node");

  assert.equal(base.colorNode, originalColorNode);
  assert.equal(base.roughnessNode, originalRoughnessNode);
  assert.equal(base.normalNode, originalNormalNode);
  assert.equal(applyAssetDetailMap(base, "unit_monument"), detailed);
  detailMapsTestHooks.reset();
});

test("rib crown receives an asset-local large-scale mineral tuning without changing ordinary white stone", () => {
  const crown = detailTuningForAsset("monument_rib_crown_a", "stone_white");
  const ordinary = detailTuningForAsset("column_white_a", "stone_white");
  assert.equal(crown.noiseTileM, 8.0);
  assert.equal(crown.albedoNoise, 0.14);
  assert.equal(crown.noiseFadeEndM, 700);
  assert.equal(crown.noiseGain, 8.0);
  assert.equal(ordinary, DETAIL_CLASS_TUNING.stone_white);
  assert.ok(crown.albedoNoise <= 0.14, "even the crown exception remains a mineral tint variation, not paint");
  assert.ok(Object.isFrozen(crown));

  detailMapsTestHooks.reset();
  detailMapsTestHooks.registerAssetClass("monument_rib_crown_a", "stone_white");
  detailMapsTestHooks.registerAssetClass("column_white_a", "stone_white");
  detailMapsTestHooks.registerDetailClass("stone_white", makeLoadedDetail(0.5, 0.78));
  const base = new MeshStandardMaterial({ roughness: 0.66 });
  const crownDetail = applyAssetDetailMap(base, "monument_rib_crown_a");
  const ordinaryDetail = applyAssetDetailMap(base, "column_white_a");
  assert.notEqual(crownDetail, ordinaryDetail, "asset-specific tuning must not share the class-only cached material");
  detailMapsTestHooks.reset();
});

test("per-class detail tuning stays bounded, subtle on organic materials and strong enough on mineral focus classes", () => {
  const classes = ["stone_white", "rock_chalk", "sandstone", "crystal", "bark", "foliage"] as const;
  for (const cls of classes) {
    const tuning = DETAIL_CLASS_TUNING[cls];
    assert.ok(tuning, `${cls} has explicit tuning`);
    for (const value of Object.values(tuning)) assert.ok(Number.isFinite(value), `${cls} tuning is finite`);
    assert.ok(tuning.microNormal > 0 && tuning.microNormal <= 0.56, `${cls} micro normal remains physical`);
    assert.ok(tuning.macroNormal >= 0 && tuning.macroNormal <= 0.30, `${cls} macro normal remains bounded`);
    assert.ok(tuning.albedoMicro >= 0 && tuning.albedoMicro <= 0.04, `${cls} micro albedo stays subtle`);
    assert.ok(tuning.albedoNoise >= 0 && tuning.albedoNoise <= 0.080, `${cls} noise albedo stays bounded`);
    assert.ok(tuning.roughness > 0 && tuning.roughness <= 0.055, `${cls} roughness stays matte/bounded`);
    assert.ok(tuning.macroTileM >= 1 && tuning.macroTileM <= 6, `${cls} macro scale is a coarse world scale`);
    assert.ok(tuning.noiseTileM >= 1 && tuning.noiseTileM <= 15, `${cls} noise scale is bounded`);
    assert.ok(tuning.noiseFadeEndM >= tuning.macroTileM * 28 || tuning.albedoNoise === 0, `${cls} large albedo noise outlives the coarse normal octave`);
    assert.ok(tuning.noiseFadeEndM <= 600, `${cls} noise fade remains bounded`);
    assert.ok(Object.isFrozen(tuning), `${cls} tuning is immutable`);
  }

  assert.ok(DETAIL_CLASS_TUNING.rock_chalk.microNormal >= 0.30);
  assert.ok(DETAIL_CLASS_TUNING.stone_white.microNormal >= 0.28);
  assert.ok(DETAIL_CLASS_TUNING.sandstone.microNormal >= 0.28);
  assert.ok(DETAIL_CLASS_TUNING.rock_chalk.macroNormal > DETAIL_CLASS_TUNING.stone_white.macroNormal);
  assert.equal(DETAIL_CLASS_TUNING.foliage.macroNormal, 0);
  assert.equal(DETAIL_CLASS_TUNING.bark.macroNormal, 0);
  assert.equal(DETAIL_CLASS_TUNING.foliage.albedoNoise, 0);
  assert.equal(DETAIL_CLASS_TUNING.bark.albedoNoise, 0);
  assert.ok(DETAIL_CLASS_TUNING.foliage.albedoMicro <= 0.008);
  assert.ok(DETAIL_CLASS_TUNING.bark.albedoMicro <= 0.012);
  assert.ok(DETAIL_CLASS_TUNING.crystal.roughness <= 0.025);
});
