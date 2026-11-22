import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import { test } from "node:test";
import { Mesh, MeshBasicMaterial } from "three/webgpu";
import { TerrainStream } from "../src/terrain-stream.ts";

test("tiles use the redirected manifest directory, throttle requests, and dispose on eviction", async (t) => {
  const requested: string[] = [];
  const manifestUrl = new URL("https://terrain.test/manifest.json");
  const material = new MeshBasicMaterial();
  const m = {
    version: 1, tilesX: 16, tilesZ: 8, tileSize: 512, samples: 17,
    originX: 0, originZ: 0, minHeight: 10, maxHeight: 20,
  };
  t.mock.method(globalThis, "fetch", async (url: URL) => {
    if (url.href === manifestUrl.href) {
      const response = Response.json(m);
      Object.defineProperty(response, "url", { value: "https://cdn.terrain.test/world/v1/manifest.json" });
      return response;
    }
    requested.push(url.href);
    return new Response(new ArrayBuffer(m.samples ** 2 * 2));
  });
  const terrain = await TerrainStream.open(manifestUrl, material);
  terrain.update(200, 200, performance.now());
  assert.equal(requested.length, 4);
  assert.equal(requested[0], "https://cdn.terrain.test/world/v1/0_0.r16");
  await setImmediate();
  terrain.update(200, 200, performance.now());
  assert.equal(terrain.heightAt(200, 200), 10);
  const mesh = terrain.group.children[0];
  assert.ok(mesh instanceof Mesh);
  let meshDisposed = false, geometryDisposed = false;
  mesh.addEventListener("dispose", () => { meshDisposed = true; });
  mesh.geometry.addEventListener("dispose", () => { geometryDisposed = true; });
  terrain.update(8000, 200, performance.now());
  assert.ok(!terrain.group.children.includes(mesh));
  assert.ok(meshDisposed && geometryDisposed);
  terrain.dispose();
  material.dispose();
});

test("slice tiles preload at full resolution, are prioritised and leave backdrop coarse", async (t) => {
  const m = { version: 1 as const, tilesX: 8, tilesZ: 8, tileSize: 512, samples: 257, originX: 0, originZ: 0, minHeight: 0, maxHeight: 65535 };
  const requested: string[] = [];
  t.mock.method(globalThis, "fetch", async (url: URL) => {
    requested.push(url.pathname);
    const data = new Uint16Array(m.samples ** 2);
    data[1 * m.samples + 1] = 100;
    return new Response(data.buffer);
  });
  const material = new MeshBasicMaterial();
  const terrain = new TerrainStream(m, new URL("https://terrain.test/manifest.json"), material);
  await terrain.preloadSlice({ minX: 512, minZ: 512, maxX: 600, maxZ: 600 });
  assert.deepEqual(requested, ["/1_1.r16"]);
  assert.equal(terrain.fullHeightAt(514, 514), 100);
  terrain.update(0, 0, 0);
  assert.equal(terrain.heightAt(514, 514), 0);
  assert.equal(terrain.fullHeightAt(514, 514), 100);
  const sliceMesh = terrain.group.children[0] as Mesh;
  assert.equal(sliceMesh.position.x, 512);
  assert.equal(sliceMesh.geometry.attributes.position.count, 129 ** 2 + 257 * 4);
  await setImmediate();
  terrain.update(0, 0, 1);
  const backdrop = terrain.group.children.find((mesh) => mesh.position.x === 0 && mesh.position.z === 0) as Mesh;
  assert.equal(backdrop.geometry.attributes.position.count, 17 ** 2 + 257 * 4);
  terrain.dispose(); material.dispose();
});

test("slice preload surfaces missing tiles", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 404 }));
  const material = new MeshBasicMaterial();
  const terrain = new TerrainStream({ version: 1, tilesX: 1, tilesZ: 1, tileSize: 512, samples: 17, originX: 0, originZ: 0, minHeight: 0, maxHeight: 10 }, new URL("https://terrain.test/manifest.json"), material);
  await assert.rejects(terrain.preloadSlice({ minX: 0, minZ: 0, maxX: 10, maxZ: 10 }), /HTTP 404/);
  terrain.dispose(); material.dispose();
});

test("render and full-resolution ground share unmodified exported heights", async (t) => {
  const m = { version: 1 as const, tilesX: 3, tilesZ: 1, tileSize: 128, samples: 65, originX: 0, originZ: 0, minHeight: 0, maxHeight: 100 };
  t.mock.method(globalThis, "fetch", async () => new Response(new Uint16Array(m.samples ** 2).fill(13107).buffer));
  const material = new MeshBasicMaterial(), terrain = new TerrainStream(m, new URL("https://terrain.test/manifest.json"), material);
  const bounds = { minX: 0, minZ: 0, maxX: 384, maxZ: 128 };
  await terrain.preloadSlice(bounds);
  assert.equal(terrain.fullHeightAt(128, 64), 20);
  terrain.update(128, 64, 0);
  assert.ok(Math.abs(terrain.heightAt(128, 64)! - terrain.fullHeightAt(128, 64)!) < 0.00001);
  terrain.dispose(); material.dispose();
});
