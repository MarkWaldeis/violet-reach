import assert from "node:assert/strict";
import { test } from "node:test";
import { LinearMipmapLinearFilter, RepeatWrapping } from "three/webgpu";
import { groundDetailPixels, groundDetails, type GroundDetail } from "../src/ground-detail.ts";

test("ground detail is reproducible, distinct per material and packs albedo plus normal relief", () => {
  const variance: number[] = [];
  for (const kind of ["grass", "soil", "sand"] as GroundDetail[]) {
    const data = groundDetailPixels(kind, 128);
    assert.deepEqual(data, groundDetailPixels(kind, 128));
    assert.equal(data.length, 128 * 128 * 4);
    const shades = new Set<number>();
    let relief = 0;
    for (let i = 0; i < data.length; i += 4) {
      shades.add(data[i]);
      assert.equal(data[i + 3], 255);
      relief += Math.abs(data[i + 1] - 128) + Math.abs(data[i + 2] - 128);
    }
    assert.ok(shades.size > 20);
    assert.ok(relief > 0);
    variance.push(relief);
  }
  assert.ok(variance[0] > variance[2] * 3);
  assert.ok(variance[1] > variance[2] * 3);
  assert.notDeepEqual(groundDetailPixels("grass", 32), groundDetailPixels("soil", 32));
});

test("detail textures are generated once with repeating, anisotropic mipmapped filtering", () => {
  const maps = groundDetails();
  assert.equal(maps, groundDetails());
  for (const map of Object.values(maps)) {
    assert.equal(map.image.width, 256);
    assert.equal(map.wrapS, RepeatWrapping);
    assert.equal(map.wrapT, RepeatWrapping);
    assert.equal(map.minFilter, LinearMipmapLinearFilter);
    assert.equal(map.generateMipmaps, true);
    assert.equal(map.anisotropy, 16);
  }
});

test("empty, oversized and invalid detail resolutions are rejected", () => {
  for (const size of [0, -1, 15, 2048, 16.5, NaN, Infinity]) {
    assert.throws(() => groundDetailPixels("grass", size), /Invalid ground detail size/);
  }
});
