import assert from "node:assert/strict";
import test from "node:test";
import { MeshStandardMaterial } from "three/webgpu";
import { applyAssetDetailMap, detailClassForMaterial, prepareDetailMapsForAssets } from "../src/detail-maps.ts";

test("detail-maps resolves safely in Node without browser fetch and preserves base material", async () => {
  await prepareDetailMapsForAssets(["boulder_chalk_a", "ruin_wall_a", "trunk_acacia_a"]);
  const base = new MeshStandardMaterial({ alphaTest: 0.5, roughness: 0.85 });
  const result = applyAssetDetailMap(base, "boulder_chalk_a");
  assert.equal(result, base);
  assert.equal(result.alphaTest, 0.5);
});

test("mixed foliage assets keep leaf detail but exclude woody material primitives", () => {
  assert.equal(detailClassForMaterial("foliage", "V3_mat_foliage_tree_meadow_oak"), "foliage");
  assert.equal(detailClassForMaterial("foliage", "tree_oak_a_LOD1_foliage"), "foliage");
  assert.equal(detailClassForMaterial("foliage", "V3_mat_bark_tree_meadow_oak"), undefined);
  assert.equal(detailClassForMaterial("foliage", "trunk_acacia_wood"), undefined);
  assert.equal(detailClassForMaterial("bark", "Material_0"), "bark");
  assert.equal(detailClassForMaterial(undefined, "V3_mat_bark_tree_meadow_oak"), undefined);
});
