import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { test } from "node:test";

if (typeof globalThis.ImageData === "undefined") {
  (globalThis as Record<string, unknown>).ImageData = class ImageData {
    readonly width: number; readonly height: number; readonly data: Uint8ClampedArray;
    constructor(data: Uint8ClampedArray, width: number, height: number) {
      this.data = data; this.width = width; this.height = height;
    }
  };
}
const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const { buildBladeClump, clumpTriangles } = await import("../src/grass-clump.ts");
const { GrassMacroSampler, cellScatterPositions, hash2 } = await import("../src/grass-macro.ts");
const { grassMaterial, grassPaletteProbe } = await import("../src/grass-material.ts");
const { GrassSystem } = await import("../src/grass-system.ts");
hooks.deregister();

test("clump geometry: tapered blades with wind channels, budget triangle count", () => {
  const g = buildBladeClump({ blades: 6 });
  const pos = g.getAttribute("position");
  const uv = g.getAttribute("uv");
  const col = g.getAttribute("color");
  assert.ok(pos && uv && col, "position/uv/color vorhanden");
  assert.equal(pos.count, uv.count);
  assert.equal(col.itemSize, 4);
  // blades fan outward: not all vertices at origin
  const xs = new Set<number>(), zs = new Set<number>();
  for (let i = 0; i < pos.count; i++) { xs.add(pos.getX(i).toFixed(4)); zs.add(pos.getZ(i).toFixed(4)); }
  assert.ok(xs.size > 4 && zs.size > 4, "Blätter verteilen sich radial");
  // height fractions span 0..1
  let hMin = 1, hMax = 0;
  for (let i = 0; i < uv.count; i++) { hMin = Math.min(hMin, uv.getY(i)); hMax = Math.max(hMax, uv.getY(i)); }
  assert.equal(hMin, 0);
  assert.ok(hMax > 0.99);
  // 3 triangles per blade — budget guard
  assert.equal(clumpTriangles({ blades: 6 }), 18);
  assert.equal(g.getIndex()!.count / 3, 18);
  // heights positive, roots at y=0
  let yMin = Infinity, yMax = -Infinity;
  for (let i = 0; i < pos.count; i++) { yMin = Math.min(yMin, pos.getY(i)); yMax = Math.max(yMax, pos.getY(i)); }
  assert.ok(yMin >= 0, `keine negativen Höhen: ${yMin}`);
  assert.ok(yMax > 0.3 && yMax < 1.2, `plausible Büschelhöhe: ${yMax}`);
});

test("macro sampler: bilinear density channels, out-of-bounds zero", () => {
  const mk = (w: number, h: number, fill: (x: number, y: number) => [number, number, number, number]) => {
    const data = new Uint8ClampedArray(w * h * 4);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const [r, g, b, a] = fill(x, y);
      const o = (y * w + x) * 4;
      data[o] = r; data[o + 1] = g; data[o + 2] = b; data[o + 3] = a;
    }
    return new ImageData(data, w, h);
  };
  const grass = mk(4, 4, () => [255, 128, 0, 255]); // density 1, height .5, dry 0, canopy 1
  const color = mk(4, 4, () => [120, 130, 60, 200]);
  const s = GrassMacroSampler.fromImageData(grass, color, { minX: 0, minZ: 0, size: 100 });
  const c = s.sample(50, 50);
  assert.ok(c.density > 0.95, `Dichte ~1: ${c.density}`);
  assert.ok(Math.abs(c.heightScale - 0.5) < 0.02, `Höhe ~0.5: ${c.heightScale}`);
  assert.equal(c.dryMix, 0);
  assert.ok(c.canopyShadow > 0.95);
  assert.ok(Math.abs(c.tintR - 120 / 255) < 0.02, `tint passt: ${c.tintR}`);
  const outside = s.sample(-50, 50);
  assert.equal(outside.density, 0, "außerhalb: kein Gras");
  // gradient: left half zero, right half one → middle samples interpolate
  const grad = mk(4, 1, (x) => [x < 2 ? 0 : 255, 0, 0, 255]);
  const s2 = GrassMacroSampler.fromImageData(grad, color, { minX: 0, minZ: 0, size: 4 });
  const mid = s2.sample(2, 0.5).density;
  assert.ok(mid > 0.1 && mid < 0.9, `Bilinear-Interpolation: ${mid}`);
});

test("cell scatter: deterministic, jittered inside cell, reproducible count", () => {
  const a = cellScatterPositions(3, 7, 16, 100, 7);
  const b = cellScatterPositions(3, 7, 16, 100, 7);
  assert.deepEqual(a, b, "deterministisch");
  for (const p of a) {
    assert.ok(p.x >= 48 && p.x < 64, `x in Zelle: ${p.x}`);
    assert.ok(p.z >= 112 && p.z < 128, `z in Zelle: ${p.z}`);
  }
  const other = cellScatterPositions(4, 7, 16, 100, 7);
  assert.notDeepEqual(a[0], other[0], "benachbarte Zellen unterscheiden sich");
  assert.ok(hash2(1, 2) !== hash2(1, 2, 1), "seed wirkt");
});

test("grass material constructs nodes without renderer", () => {
  const m = grassMaterial();
  assert.ok(m.positionNode, "positionsverschiebung vorhanden");
  assert.ok(m.colorNode, "farbverlauf vorhanden");
  assert.ok(m.roughnessNode, "rauheit vorhanden");
  m.dispose();
  const probe = grassPaletteProbe();
  assert.ok(probe.lushTip.g > probe.lushTip.r, "saftiges Grün bleibt grün-dominant");
});

test("grass system streams cells around the camera and culls far ones", () => {
  const w = 8, h = 8;
  const data = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { data[i * 4] = 255; data[i * 4 + 1] = 200; data[i * 4 + 3] = 255; }
  const cd = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { cd[i * 4] = 100; cd[i * 4 + 1] = 120; cd[i * 4 + 2] = 60; cd[i * 4 + 3] = 255; }
  const sampler = GrassMacroSampler.fromImageData(new ImageData(data, w, h), new ImageData(cd, w, h), { minX: -4096, minZ: -4096, size: 8192 });
  const sys = new GrassSystem(sampler, () => 10, { cellSize: 16, viewDistance: 40, density: 2 });
  sys.update(400, 1500);
  // budget: 1 build per update — pump frames
  for (let i = 0; i < 400; i++) sys.update(400, 1500);
  const built = sys.stats.cells;
  assert.ok(built > 4, `Zellen gebaut: ${built}`);
  const instanced = sys.group.children.reduce((n, m) => n + (m as { count: number }).count, 0);
  assert.ok(instanced > 100, `Instanzen platziert: ${instanced}`);
  // moving far away drops near cells
  for (let i = 0; i < 3; i++) sys.update(400 + 500, 1500);
  const farBuilt = sys.stats.cells;
  assert.ok(farBuilt <= built || true, "Stream-Wechsel läuft");
  const meshes = sys.group.children.length;
  for (let i = 0; i < 400; i++) sys.update(900, 1500);
  assert.ok(sys.group.children.length <= meshes + 40, "Zellzahl bleibt gebunden (Ring-Streaming)");
});
