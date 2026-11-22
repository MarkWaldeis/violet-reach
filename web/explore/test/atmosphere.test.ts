import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import test from "node:test";
import { HemisphereLight, Scene } from "three/webgpu";

const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const { setupAtmosphere } = await import("../src/atmosphere.ts");
hooks.deregister();

test("cream cloud fill keeps limestone warm in shade without changing its albedo", () => {
  const scene = new Scene();
  setupAtmosphere(scene);
  const fills = scene.children.filter((light): light is HemisphereLight => light instanceof HemisphereLight);
  assert.equal(fills.length, 1);
  const fill = fills[0];
  assert.ok(fill.color.r > fill.color.b);
  assert.ok(fill.groundColor.r > fill.groundColor.b);
  assert.ok(fill.color.b > 0.4);
  assert.ok(fill.intensity > 0);
});
