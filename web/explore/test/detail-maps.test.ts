import assert from "node:assert/strict";
import test from "node:test";
import { MeshStandardMaterial } from "three/webgpu";
import { applyAssetDetailMap, prepareDetailMapsForAssets } from "../src/detail-maps.ts";

test("detail-maps resolves safely in Node without browser fetch and preserves base material", async () => {
  await prepareDetailMapsForAssets(["boulder_chalk_a", "ruin_wall_a", "trunk_acacia_a"]);
  const base = new MeshStandardMaterial({ alphaTest: 0.5, roughness: 0.85 });
  const result = applyAssetDetailMap(base, "boulder_chalk_a");
  assert.equal(result, base);
  assert.equal(result.alphaTest, 0.5);
});
