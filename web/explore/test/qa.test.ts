import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";
import { DataTexture, DepthTexture, FloatType, LinearFilter, LinearMipmapLinearFilter, PerspectiveCamera, RGBAFormat, UnsignedByteType, Vector3 } from "three/webgpu";
import { Navigation } from "../src/navigation.ts";
import { DEFAULT_FOV, parseCamera, parseQAParams, viewDirection } from "../src/qa-params.ts";
import { DEFAULT_QUALITY, QUALITY, QUALITY_NAMES, qualityLevel } from "../src/quality.ts";
import { estimateTextureBytes, FrameHistory, FrameStability, STABLE_FRAMES, trackTextures } from "../src/qa-probe.ts";
import { assetRenderOptions } from "../src/instance-lod.ts";
// @ts-expect-error plain ESM tooling module without types
import { camParam, interpolateKeys, validateBackend } from "../../../tools/qa/lib.mjs";

const params = (query: string) => parseQAParams(new URLSearchParams(query));

test("without QA parameters the runtime keeps its previous behaviour", () => {
  const p = params("");
  assert.equal(p.cam, undefined);
  assert.equal(p.agl, false);
  assert.equal(p.fov, DEFAULT_FOV);
  assert.equal(p.fov, 57);
  assert.equal(p.hud, true);
  assert.equal(p.freeze, false);
  assert.equal(p.quality.name, "high");
  assert.deepEqual(QUALITY.high, { name: "high", pixelRatio: 1.5, shadows: true, shadowMapSize: 2048, shadowCascades: 2, assetDistanceScale: 1 });
  assert.deepEqual(assetRenderOptions(2, { distanceScale: QUALITY.high.assetDistanceScale }), assetRenderOptions(2));
});

test("cam, agl, fov, hud, freeze and quality parse and validate", () => {
  const p = params("cam=449,1.7,1398,-2.8,-0.05&agl=1&fov=70&hud=0&freeze=1&quality=ULTRA");
  assert.deepEqual(p.cam, { x: 449, y: 1.7, z: 1398, yaw: -2.8, pitch: -0.05 });
  assert.equal(p.agl, true);
  assert.equal(p.fov, 70);
  assert.equal(p.hud, false);
  assert.equal(p.freeze, true);
  assert.equal(p.quality.name, "ultra");
  assert.equal(params("agl=0&freeze=false&hud=1").agl, false);
  assert.equal(params("freeze").freeze, true);
  assert.equal(params("hud").hud, true);
  for (const bad of ["1,2,3,4", "1,2,3,4,5,6", "1,,3,4,5", "a,2,3,4,5", "1,2,3,4,2"]) assert.throws(() => parseCamera(bad), /cam:/);
  for (const fov of ["0", "9", "121", "abc"]) assert.throws(() => params(`fov=${fov}`), /fov/);
  assert.throws(() => params("quality=extreme"), /quality/);
});


test("QA quality overrides can reduce shadow cascades without changing the base quality table", () => {
  const base = params("quality=high").quality;
  assert.equal(base.shadowCascades, 2);
  const reduced = params("quality=high&cascades=1").quality;
  assert.equal(reduced.name, "high");
  assert.equal(reduced.shadowCascades, 1);
  assert.equal(reduced.shadows, true);
  assert.equal(QUALITY.high.shadowCascades, 2);
  assert.equal(params("quality=high&cascades=0").quality.shadows, false);
  assert.equal(params("quality=high&shadows=0").quality.shadows, false);
  assert.equal(params("quality=high&shadows=0&cascades=3").quality.shadowCascades, 3);
  for (const value of ["-1", "5", "1.5", "abc"]) assert.throws(() => params(`cascades=${value}`), /cascades/);
});

test("yaw/pitch convention matches Navigation: yaw 0 looks north (−Z), positive yaw turns west, positive pitch up", () => {
  const close = (a: number[], b: number[]) => a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) < 1e-9, `${a} vs ${b}`));
  close(viewDirection(0, 0), [0, 0, -1]);
  close(viewDirection(Math.PI / 2, 0), [-1, 0, 0]);
  close(viewDirection(-Math.PI / 2, 0), [1, 0, 0]);
  close(viewDirection(0, Math.PI / 2), [0, 1, 0]);
});

test("setPose keeps a pinned pose (no ground clamp) until a movement key is held, and matches viewDirection", () => {
  const camera = new PerspectiveCamera();
  const manifest = { version: 1 as const, tilesX: 2, tilesZ: 2, tileSize: 512, samples: 17, originX: 0, originZ: 0, minHeight: 0, maxHeight: 100 };
  const nav = new Navigation(camera, manifest, () => 50);
  nav.setPose(100, 51, 200, 0.7, -0.3, "walk");
  nav.update(0.05);
  assert.deepEqual(camera.position.toArray(), [100, 51, 200]);
  const d = camera.getWorldDirection(new Vector3()).toArray();
  viewDirection(0.7, -0.3).forEach((v, i) => assert.ok(Math.abs(v - d[i]) < 1e-6));
  assert.equal(nav.yaw, 0.7);
  assert.equal(nav.pitch, -0.3);
  nav.keys.add("KeyW");
  nav.update(0.05);
  assert.equal(camera.position.y, 51.8, "walking resumes at eye height above ground");
});

test("quality table is ordered and every level is reachable", () => {
  assert.equal(DEFAULT_QUALITY, "high");
  assert.deepEqual(QUALITY_NAMES, ["low", "medium", "high", "ultra"]);
  for (let i = 1; i < QUALITY_NAMES.length; i++) {
    const a = QUALITY[QUALITY_NAMES[i - 1]], b = QUALITY[QUALITY_NAMES[i]];
    assert.ok(b.pixelRatio >= a.pixelRatio && b.shadowMapSize >= a.shadowMapSize && b.assetDistanceScale > a.assetDistanceScale && b.shadowCascades >= a.shadowCascades);
  }
  assert.equal(QUALITY.low.shadows, false);
  for (const name of QUALITY_NAMES) assert.equal(qualityLevel(` ${name.toUpperCase()} `).name, name);
  assert.equal(qualityLevel(null).name, "high");
  assert.equal(assetRenderOptions(2, { distanceScale: 0.5 }, { maxDistance: 100 }).maxDistance, 50);
  assert.equal(assetRenderOptions(2, { distanceScale: 0.5, maxDistance: 30 }, { maxDistance: 100 }).maxDistance, 30);
  assert.equal(assetRenderOptions(2, { distanceScale: 1.25 }).maxDistance, 100);
  for (const distanceScale of [0, -1, NaN, Infinity]) assert.throws(() => assetRenderOptions(2, { distanceScale }), /Invalid asset/);
});

test("readiness needs STABLE_FRAMES identical frames; any change restarts the count", () => {
  const s = new FrameStability();
  for (let i = 0; i < STABLE_FRAMES; i++) s.observe("a");
  assert.equal(s.frames, STABLE_FRAMES - 1);
  assert.equal(s.observe("a"), STABLE_FRAMES);
  assert.equal(s.observe("b"), 0);
  s.reset();
  assert.equal(s.observe("b"), 0);
  const h = new FrameHistory(3);
  for (const frameMs of [100, 20, 20, 20]) h.push({ now: 0, frameMs, cpuMs: 1, triangles: 0, drawCalls: 0 });
  assert.equal(h.records.length, 3);
  assert.equal(h.fps(), 50);
});

test("texture memory estimate: w × h × bytes/pixel × 4/3 with mips; tracker follows create/destroy", () => {
  const rgba = new DataTexture(new Uint8Array(256 * 256 * 4), 256, 256, RGBAFormat, UnsignedByteType);
  rgba.generateMipmaps = true;
  rgba.minFilter = LinearMipmapLinearFilter;
  assert.equal(estimateTextureBytes(rgba), Math.round(256 * 256 * 4 * 4 / 3));
  rgba.minFilter = LinearFilter;
  assert.equal(estimateTextureBytes(rgba), 256 * 256 * 4);
  const float = new DataTexture(new Float32Array(64 * 32 * 4), 64, 32, RGBAFormat, FloatType);
  float.minFilter = LinearFilter;
  assert.equal(estimateTextureBytes(float), 64 * 32 * 16);
  assert.equal(estimateTextureBytes(new DepthTexture(2048, 2048)), 2048 * 2048 * 4);
  const created: unknown[] = [];
  const info = { createTexture: (t: unknown) => { created.push(t); }, destroyTexture: () => {} };
  const tracker = trackTextures(info as never);
  info.createTexture(float as never);
  assert.equal(created.length, 1);
  assert.equal(tracker.bytes(), 64 * 32 * 16);
  assert.deepEqual(tracker.summary(), { "64x32": { count: 1, bytes: 64 * 32 * 16 } });
  info.destroyTexture(float as never);
  assert.equal(tracker.bytes(), 0);
});

test("QA tooling: key interpolation, cam parameter and backend validation", () => {
  const keys = [{ t: 0, x: 0, z: 0, agl: 2, yaw: 3, pitch: 0 }, { t: 2, x: 10, z: -10, agl: 4, yaw: -3, pitch: 0.2 }];
  const mid = interpolateKeys(keys, 1);
  assert.equal(mid.x, 5);
  assert.equal(mid.agl, 3);
  assert.ok(Math.abs(mid.yaw - (3 + (2 * Math.PI - 6) / 2)) < 1e-9, "yaw turns the short way across ±π");
  assert.deepEqual(interpolateKeys(keys, 5), keys[1]);
  assert.equal(camParam({ x: 1, agl: 1.7, z: 2, yaw: -0.123456, pitch: 0 }), "1,1.7,2,-0.1235,0");
  const amd = { backend: "WebGPU", adapter: { vendor: "amd", architecture: "rdna-2", device: "", description: "" } };
  assert.equal(validateBackend(amd, false).valid, true);
  assert.equal(validateBackend({ ...amd, adapter: { vendor: "intel", architecture: "gen-12lp", device: "", description: "" } }, false).valid, false);
  assert.equal(validateBackend({ backend: "WebGL2", adapter: null }, false).valid, false);
  assert.equal(validateBackend({ backend: "WebGL2", adapter: null }, true).valid, true);
});

test("bookmarks: 13 fixed views inside the slice, existing references, sequences and routes", () => {
  const doc = JSON.parse(readFileSync(new URL("../../../world/bookmarks.json", import.meta.url), "utf8"));
  const slice = JSON.parse(readFileSync(new URL("../../../world/slice.json", import.meta.url), "utf8"));
  const b = slice.bounds;
  assert.equal(doc.version, 1);
  assert.deepEqual(doc.bookmarks.map((m: { id: string }) => m.id), ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "F1", "F2", "F3", "F4", "H1", "H2"]);
  for (const m of doc.bookmarks) {
    assert.ok(m.x >= b.minX && m.x <= b.maxX && m.z >= b.minZ && m.z <= b.maxZ, m.id);
    assert.ok(["walk", "fly"].includes(m.mode) && m.agl > 0 && Math.abs(m.pitch) <= 1.42 && m.fov === 57, m.id);
    assert.ok(Array.isArray(m.references) && m.focus.length > 10, m.id);
    for (const r of m.references) assert.ok(existsSync(new URL(`../../../${r}`, import.meta.url)), r);
  }
  const views = new Map(doc.bookmarks.map((m: { id: string }) => [m.id, m]));
  assert.ok(views.get("G2").pitch >= 0.10 && views.get("G2").pitch <= 0.18);
  const g4 = views.get("G4");
  assert.ok(Math.hypot(g4.x - 240, g4.z - 1520) >= 5.5 && Math.hypot(g4.x - 240, g4.z - 1520) <= 7);
  assert.deepEqual(doc.sequences.map((s: { id: string }) => s.id), ["walk", "fly"]);
  assert.deepEqual(doc.routes.map((s: { id: string }) => s.id), ["ground", "flight"]);
  for (const s of [...doc.sequences, ...doc.routes]) {
    const ts = s.keys.map((k: { t: number }) => k.t);
    assert.ok(ts.every((t: number, i: number) => i === 0 || t > ts[i - 1]), s.id);
    for (const k of s.keys) assert.ok(k.x >= b.minX && k.x <= b.maxX && k.z >= b.minZ && k.z <= b.maxZ && k.agl > 0, s.id);
  }
  for (const s of doc.sequences) assert.equal(s.keys.at(-1).t, s.seconds);
  for (const r of doc.routes) assert.ok(r.seconds >= 30 && r.seconds <= 45 && r.speed > 0, r.id);
});
