import assert from "node:assert/strict";
import { test } from "node:test";
import { BANK_RADIUS, BANK_TALUS, relaxBankTiles } from "../src/runtime-banks.ts";
import type { TerrainManifest } from "../src/heightfield.ts";
import type { WaterRegion } from "../src/hydrology.ts";

const m: TerrainManifest = { version: 1, tilesX: 3, tilesZ: 1, tileSize: 128, samples: 65, originX: 0, originZ: 0, minHeight: 0, maxHeight: 100 };
const region: WaterRegion = { lakes: [], segments: [{ a: [128, -100, 10, 12], b: [128, 228, 10, 12] }], bounds: { minX: 0, minZ: 0, maxX: 384, maxZ: 128 } };
const tiles = () => new Map(Array.from({ length: 3 }, (_, tx) => [`${tx}_0`, Float32Array.from({ length: 65 ** 2 }, (_, i) => Math.abs(tx * 128 + i % 65 * 2 - 128) < 6 ? 4 : 30)]));

test("runtime banks are deterministic, immutable, talus-limited, wet below water and unchanged outside corridors", () => {
  const input = tiles(), output = relaxBankTiles(m, input, region);
  assert.deepEqual(output, relaxBankTiles(m, new Map([...input].reverse()), region));
  assert.equal(input.get("1_0")![32 * 65], 4);
  const sample = (x: number) => output.get(`${Math.min(2, Math.floor(x / 128))}_0`)![32 * 65 + (x === 384 ? 64 : x % 128 / 2)];
  assert.ok(sample(128) > 4 && sample(128) < 10);
  for (let x = 2; x <= 384; x += 2) {
    if (Math.abs(x - 128) - 6 < BANK_RADIUS && Math.abs(x - 130) - 6 < BANK_RADIUS) assert.ok(Math.abs(sample(x) - sample(x - 2)) <= 2 * BANK_TALUS + 0.00001);
    if (Math.abs(x - 128) - 6 >= BANK_RADIUS) assert.equal(sample(x), 30);
  }
  for (let z = 0; z < 65; z++) assert.equal(output.get("0_0")![z * 65 + 64], output.get("1_0")![z * 65]);
});

test("lake entry fills the old deep channel toward lake level without covering the bed", () => {
  const input = tiles();
  const lake = { name: "Test", water_y: 10, outline: [[80, -100], [180, -100], [180, 228], [80, 228]] as [number, number][] };
  const output = relaxBankTiles(m, input, { ...region, lakes: [lake] });
  assert.ok(output.get("1_0")![32 * 65] >= 9.25);
  assert.ok(output.get("1_0")![32 * 65] < 10);
});

test("empty corridors preserve heights and incomplete shaping mosaics fail explicitly", () => {
  const input = tiles();
  assert.deepEqual(relaxBankTiles(m, input, { ...region, lakes: [], segments: [] }), input);
  assert.equal(relaxBankTiles(m, new Map(), region).size, 0);
  input.delete("1_0");
  assert.throws(() => relaxBankTiles(m, input, region), /Höhenkachel fehlt/);
});

test("deep lake interior is outside the bank corridor and retains its original bed", () => {
  const input = tiles();
  const lake = { name: "Deep", water_y: 10, outline: [[0, -100], [384, -100], [384, 228], [0, 228]] as [number, number][] };
  const output = relaxBankTiles(m, input, { ...region, lakes: [lake], segments: [] });
  assert.equal(output.get("1_0")![32 * 65], 4);
});
