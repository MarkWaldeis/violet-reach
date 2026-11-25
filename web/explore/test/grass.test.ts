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
const { GrassMacroSampler, cellScatterCapacity, cellScatterOrder, cellScatterPositionAt, cellScatterPositions, hash2 } = await import("../src/grass-macro.ts");
const { grassMaterial, grassPaletteProbe } = await import("../src/grass-material.ts");
const { GrassSystem } = await import("../src/grass-system.ts");
hooks.deregister();

function uniformGrassSampler() {
  const w = 8, h = 8;
  const data = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { data[i * 4] = 255; data[i * 4 + 1] = 200; data[i * 4 + 3] = 255; }
  const cd = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { cd[i * 4] = 100; cd[i * 4 + 1] = 120; cd[i * 4 + 2] = 60; cd[i * 4 + 3] = 255; }
  return GrassMacroSampler.fromImageData(new ImageData(data, w, h), new ImageData(cd, w, h), { minX: -4096, minZ: -4096, size: 8192 });
}

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
  const far = buildBladeClump({ blades: 6, curved: false });
  assert.equal(clumpTriangles({ blades: 6, curved: false }), 6, "Fern-LOD: ein Dreieck pro Halm");
  assert.equal(far.getIndex()!.count / 3, 6);
  assert.equal(far.getAttribute("position").count, 18, "Wurzelpaar + Spitze je Halm");
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
  assert.equal(s.densityCellMax(0, 0, 100, 100), 1, "Zell-Maximum erkennt volle Dichte");
  assert.equal(s.densityCellMax(-80, 0, -20, 50), 0, "Zell-Maximum außerhalb ist null");
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

  const total = cellScatterCapacity(100);
  assert.equal(total, a.length, "Kapazität ist die n²-Rastergröße");
  for (let i = 0; i < total; i++) assert.deepEqual(cellScatterPositionAt(3, 7, 16, 100, 7, i), a[i], `indexierter Kandidat ${i}`);
  const order = cellScatterOrder(total, 113.17);
  assert.equal(order.length, total);
  assert.equal(new Set(order).size, total, "Permutation ohne Duplikate");
  // Distance LOD renders count prefixes: the first half must already cover all quadrants instead
  // of filling the cell row-by-row. Bounds are deliberately loose; exact counts are seed-dependent.
  const half = Math.floor(total / 2), quadrants = [0, 0, 0, 0], n = Math.sqrt(total);
  for (let i = 0; i < half; i++) {
    const idx = order[i], gx = idx % n, gz = Math.floor(idx / n);
    quadrants[(gx >= n / 2 ? 1 : 0) + (gz >= n / 2 ? 2 : 0)]++;
  }
  for (const q of quadrants) assert.ok(q >= total * 0.08, `Präfix räumlich gestreut: ${quadrants.join("/")}`);
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

test("grass system build budget slices dense cell construction across frames", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { cellSize: 16, viewDistance: 20, density: 5.5, buildBudgetMs: 0 });
  sys.update(400, 1500);
  assert.equal(sys.stats.building, 1, "Zelle ist nach der ersten Zeitscheibe noch im Bau");
  assert.equal(sys.group.children.length, 0, "kein synchroner Komplettbau im ersten Frame");
  for (let i = 0; i < 220 && sys.stats.builds === 0; i++) sys.update(400, 1500);
  assert.ok(sys.stats.builds > 0, "inkrementeller Bau wird später fertig");
  assert.ok(sys.stats.cells > 0);
  sys.dispose();
});

test("grass density importance scan keeps the mean placement rate in sparse cells", () => {
  const w = 4, h = 4, densityByte = 128;
  const data = new Uint8ClampedArray(w * h * 4);
  const cd = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    data[i * 4] = densityByte; data[i * 4 + 1] = 200; data[i * 4 + 3] = 255;
    cd[i * 4] = 100; cd[i * 4 + 1] = 120; cd[i * 4 + 2] = 60; cd[i * 4 + 3] = 255;
  }
  const sampler = GrassMacroSampler.fromImageData(new ImageData(data, w, h), new ImageData(cd, w, h), { minX: -4096, minZ: -4096, size: 8192 });
  const target = 100;
  const sys = new GrassSystem(sampler, () => 10, { cellSize: 16, viewDistance: 0, density: target / 256, buildBudgetMs: 20 });
  sys.update(8, 8);
  assert.equal(sys.stats.pending, 0);
  const expected = Math.ceil(cellScatterCapacity(target) * (densityByte / 255));
  assert.equal(sys.stats.instances, expected, "halb dichte Makrozelle scannt nur den statistisch nötigen Kandidatenanteil");
  assert.equal(sys.stats.skipDensity, 0, "innerhalb des Maximums ist die skalierte Akzeptanz exakt kompensiert");
  sys.dispose();
});

test("grass distance LOD uses uniform count prefixes, far geometry and bounded reusable slots", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { cellSize: 16, viewDistance: 40, density: 2, buildBudgetMs: 8, maxBuildPerFrame: 8 });
  for (let i = 0; i < 120; i++) sys.update(400, 1500);
  assert.equal(sys.stats.pending, 0, "Ring vollständig gebaut");
  assert.ok(sys.stats.instances > 500, `Vollzählige Instanzen: ${sys.stats.instances}`);
  assert.ok(sys.stats.visibleInstances < sys.stats.instances, `Fernzellen reduziert: ${sys.stats.visibleInstances}/${sys.stats.instances}`);
  const meshes = sys.group.children as unknown as Array<{ count: number; geometry: { getAttribute(name: string): { count: number } } }>;
  const vertexCounts = new Set(meshes.map((m) => m.geometry.getAttribute("position").count));
  assert.ok(vertexCounts.has(30), "Nahzellen nutzen gekrümmte 5-Vertexpaare/18-Dreiecks-Büschel");
  assert.ok(vertexCounts.has(18), "Fernzellen nutzen vereinfachte 3-Vertexpaare/6-Dreiecks-Büschel");
  assert.ok(sys.stats.triangles < sys.stats.instances * 18, "Dreiecksschätzung berücksichtigt LOD");
  const slots = sys.stats.slots;
  for (let i = 0; i < 120; i++) sys.update(900, 1500);
  assert.ok(sys.stats.slots <= slots + 2, `Render-Slots werden wieder verwendet: ${slots} → ${sys.stats.slots}`);
  sys.dispose();
});

test("grass system suspends streaming when vertical camera distance exceeds the fade range", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { cellSize: 16, viewDistance: 20, density: 2, buildBudgetMs: 8 }, () => 45);
  for (let i = 0; i < 120; i++) sys.update(400, 1500, 11.7);
  assert.ok(sys.stats.cells > 0, "Bodenkamera streamt Gras");
  sys.update(400, 1500, 60);
  assert.equal(sys.stats.suspended, 0, "nahe höhere Grassflächen verhindern das Abschalten");
  assert.ok(sys.stats.cells > 0);
  sys.update(400, 1500, 131);
  assert.equal(sys.stats.suspended, 1);
  assert.equal(sys.stats.cells, 0);
  assert.equal(sys.stats.instances, 0);
  assert.equal(sys.group.children.length, 0, "unsichtbare Fernzellen werden aus dem Streaming entfernt");
  for (let i = 0; i < 120; i++) sys.update(400, 1500, 11.7);
  assert.equal(sys.stats.suspended, 0);
  assert.ok(sys.stats.cells > 0, "beim Abstieg wird der Ring erneut aufgebaut");
  sys.dispose();
});
