import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import test from "node:test";
import { ACESFilmicToneMapping, AgXToneMapping, EquirectangularReflectionMapping, HemisphereLight, NeutralToneMapping, Scene } from "three/webgpu";

const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const { DEFAULT_SHADOWS, setupAtmosphere } = await import("../src/atmosphere.ts");
const { DEFAULT_EXPOSURE, resolvePostConfig, resolveToneMapping } = await import("../src/post-processing.ts");
const { QUALITY } = await import("../src/quality.ts");
hooks.deregister();

test("cream cloud fill keeps limestone warm in shade without changing its albedo", () => {
  const scene = new Scene();
  const { sun } = setupAtmosphere(scene);
  const fills = scene.children.filter((light): light is HemisphereLight => light instanceof HemisphereLight);
  assert.equal(fills.length, 1);
  const fill = fills[0];
  assert.ok(fill.color.r > fill.color.b);
  assert.ok(fill.groundColor.r > fill.groundColor.b);
  assert.ok(fill.color.b > 0.4);
  assert.ok(fill.intensity > 0 && fill.intensity <= 0.6);
  assert.equal(DEFAULT_SHADOWS.shadowCascades, 4);
  assert.ok(sun.intensity >= 3.5);
  assert.ok(scene.environment);
  assert.equal(scene.environment.mapping, EquirectangularReflectionMapping);
  assert.ok(scene.environmentIntensity > 0 && scene.environmentIntensity <= 0.85);
});

test("post-processing tiers and URL switches resolve deterministically", () => {
  const q = (s: string) => new URLSearchParams(s);
  assert.equal(resolvePostConfig(QUALITY.low, q("")).enabled, false);
  const med = resolvePostConfig(QUALITY.medium, q(""));
  assert.equal(med.enabled, true);
  assert.equal(med.ao, false);
  assert.equal(med.bloom, true);
  assert.equal(med.godrays, false);
  assert.equal(med.grade, true);
  assert.equal(med.vignette, true);

  const high = resolvePostConfig(QUALITY.high, q(""));
  assert.equal(high.enabled, true);
  assert.equal(high.ao, true);
  assert.equal(high.aoResolutionScale, 0.5);
  assert.equal(high.bloom, true);
  assert.equal(high.godrays, true);
  assert.equal(high.grade, true);
  assert.equal(high.vignette, true);

  const ultra = resolvePostConfig(QUALITY.ultra, q(""));
  assert.equal(ultra.aoResolutionScale, 0.75);

  assert.equal(resolvePostConfig(QUALITY.high, q("post=0")).enabled, false);
  assert.equal(resolvePostConfig(QUALITY.high, q("ao=0&bloom=0&godrays=0&grade=0&vignette=0")).enabled, false);
  assert.equal(resolvePostConfig(QUALITY.high, q("ao=0")).ao, false);

  const tmDefault = resolveToneMapping(q(""));
  assert.equal(tmDefault.name, "aces");
  assert.equal(tmDefault.toneMapping, ACESFilmicToneMapping);
  assert.equal(tmDefault.exposure, DEFAULT_EXPOSURE);
  assert.equal(resolveToneMapping(q("tonemapping=neutral&exposure=1.15")).toneMapping, NeutralToneMapping);
  assert.equal(resolveToneMapping(q("tonemapping=AGX&exposure=1.05")).toneMapping, AgXToneMapping);
  assert.throws(() => resolveToneMapping(q("tonemapping=reinhard")), /tonemapping/);
  assert.throws(() => resolveToneMapping(q("exposure=0")), /exposure/);
});
