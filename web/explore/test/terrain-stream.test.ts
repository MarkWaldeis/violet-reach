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
