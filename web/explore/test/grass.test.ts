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
const { GrassSystem, grassSectorSlotUpperBound } = await import("../src/grass-system.ts");
hooks.deregister();

function uniformGrassSampler(densityByte = 255) {
  const w = 8, h = 8;
  const data = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { data[i * 4] = densityByte; data[i * 4 + 1] = 200; data[i * 4 + 3] = 255; }
  const cd = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { cd[i * 4] = 100; cd[i * 4 + 1] = 120; cd[i * 4 + 2] = 60; cd[i * 4 + 3] = 255; }
  return GrassMacroSampler.fromImageData(new ImageData(data, w, h), new ImageData(cd, w, h), { minX: -4096, minZ: -4096, size: 8192 });
}

/** Pump frame slices until the streaming working set is complete, then settle the readiness counters. */
function pumpGrass(sys, x: number, z: number, py?: number, maxFrames = 120) {
  for (let i = 0; i < maxFrames; i++) {
    sys.update(x, z, py);
    if (i > 0 && sys.stats.pending === 0 && sys.stats.building === 0) {
      sys.update(x, z, py); // pendingVisible is sampled before the build slice; settle it one frame later
      return;
    }
  }
  throw new Error(`grass streaming did not finish within ${maxFrames} frames`);
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

test("cell scatter helpers: deterministic, jittered inside cell, reproducible count", () => {
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
});

test("32 m sector scatter: capacity, deterministic positions and spatially uniform prefixes", () => {
  const target = Math.round(32 * 32 * 5.5);
  assert.equal(target, 5632, "Zielinstanzen eines vollen Hochqualitäts-Sektors");
  const total = cellScatterCapacity(target);
  assert.equal(total, 5625, "75×75-Kandidatenraster im 32-m-Sektor");
  const a = cellScatterPositions(3, 7, 32, target, 7);
  const b = cellScatterPositions(3, 7, 32, target, 7);
  assert.equal(a.length, total);
  assert.deepEqual(a.slice(0, 32), b.slice(0, 32), "Sektor-Scatter ist deterministisch");
  for (const p of a) {
    assert.ok(p.x >= 96 && p.x < 128, `x im 32-m-Sektor: ${p.x}`);
    assert.ok(p.z >= 224 && p.z < 256, `z im 32-m-Sektor: ${p.z}`);
  }

  const order = cellScatterOrder(total, 113.17);
  assert.equal(new Set(order).size, total, "Permutation ohne Duplikate");
  // Distance LOD renders count prefixes: the first half must already cover all quadrants instead
  // of filling the large sector row-by-row. Bounds are deliberately loose; exact counts are seed-dependent.
  const half = Math.floor(total / 2), quadrants = [0, 0, 0, 0], n = Math.sqrt(total);
  assert.equal(n, 75);
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

test("grass system uses 32 m sectors: ~28 streaming slots at 72 m and 5625-instance capacity", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { viewDistance: 72, density: 5.5, buildBudgetMs: 0 });
  sys.update(16, 16);
  assert.ok(sys.stats.wanted >= 24 && sys.stats.wanted <= 33, `grober Sektorring statt ~87 Zellen: ${sys.stats.wanted}`);
  assert.equal(sys.stats.pending, sys.stats.wanted);
  assert.equal(sys.stats.building, 1, "nächster Sektor wird inkrementell gebaut");
  assert.equal(sys.group.children.length, 1, "Baustellen-Mesh ist für progressive Uploads in der Szene");
  const buildMesh = sys.group.children[0] as unknown as { count: number; frustumCulled: boolean; geometry: { getAttribute(name: string): { count: number } } };
  assert.equal(buildMesh.count, 0, "noch keine sichtbaren Instanzen im ersten Frame");
  assert.equal(buildMesh.frustumCulled, false, "count-0-Baustelle bleibt für Teiluploads im Rendertraversal");
  assert.equal(buildMesh.geometry.getAttribute("aInfo").count, 5625, "Sektorkapazität aus 32×32×5.5 mit n²-Rundung");
  sys.dispose();
});

test("grass system streams sectors around the camera and reuses bounded slots", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { sectorSize: 32, viewDistance: 40, density: 2, buildBudgetMs: 8, maxBuildPerFrame: 8 });
  pumpGrass(sys, 400, 1500);
  const built = sys.stats.cells;
  assert.ok(built > 4, `Sektoren gebaut: ${built}`);
  assert.equal(sys.stats.sectors, sys.stats.cells, "Bench-Alias grassCells bleibt sinnvoll gemappt");
  assert.ok(sys.stats.wanted <= 20, `32-m-Arbeitsmenge bleibt klein: ${sys.stats.wanted}`);
  const instanced = sys.group.children.reduce((n, m) => n + (m as { count: number }).count, 0);
  assert.ok(instanced > 1000, `Instanzen platziert: ${instanced}`);
  const slots = sys.stats.slots;
  const meshes = sys.group.children.length;

  pumpGrass(sys, 900, 1500, undefined, 160);
  assert.ok(sys.group.children.length <= meshes + 8, "Sektorzahl bleibt durch Ring-Streaming gebunden");
  assert.ok(sys.stats.slots <= slots + 2, `Render-Slots werden wieder verwendet: ${slots} → ${sys.stats.slots}`);
  sys.dispose();
});

test("grass sector streaming follows rectangle distance with a small exit hysteresis", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, {
    sectorSize: 32, viewDistance: 20, density: 0.01, buildBudgetMs: 8, maxBuildPerFrame: 8,
  });
  const hasEastSector = () => sys.group.children.some((m) => (m as { name?: string }).name === "grass_sector_1_0");
  pumpGrass(sys, 0, 16, undefined, 40);
  assert.equal(hasEastSector(), false, "Ostsektor ist vor der 22-m-Eintrittskante noch nicht gestreamt");
  pumpGrass(sys, 10.5, 16, undefined, 40);
  assert.equal(hasEastSector(), true, "Sektorfläche innerhalb viewDistance+Prefetch wird gestreamt");
  pumpGrass(sys, 9.5, 16, undefined, 40);
  assert.equal(hasEastSector(), true, "innerhalb der Austritts-Hysterese bleibt der Sektor erhalten");
  pumpGrass(sys, 7.5, 16, undefined, 40);
  assert.equal(hasEastSector(), false, "jenseits der Austritts-Hysterese wird der Sektor freigegeben");
  sys.dispose();
});

test("grass sector build is frame-sliced and uploads a contiguous prefix in bounded chunks", () => {
  const options = { sectorSize: 32, viewDistance: 0, density: 1, buildBudgetMs: 0, distanceDensityStart: 1000, distanceDensityEnd: 1001 };
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, options);
  sys.update(8, 8);
  assert.equal(sys.stats.building, 1, "Sektor ist nach der ersten Zeitscheibe noch im Bau");
  assert.equal(sys.stats.cells, 0, "kein synchroner Komplettbau im ersten Frame");
  assert.equal(sys.group.children.length, 1, "unsichtbare Baustelle ist bereits im Rendertraversal");
  assert.equal((sys.group.children[0] as unknown as { count: number }).count, 0, "Baustelle zeigt noch keine Instanzen");
  for (let i = 0; i < 80 && sys.stats.builds === 0; i++) sys.update(8, 8);
  assert.equal(sys.stats.builds, 1, "inkrementeller Bau wird später fertig");
  assert.equal(sys.stats.cells, 1);
  const mesh = sys.group.children[0] as unknown as { count: number; frustumCulled: boolean; geometry: { getAttribute(name: string): { count: number; itemSize: number; updateRanges: Array<{ start: number; count: number }>; array: ArrayLike<number> } } };
  assert.equal(mesh.count, 1024, "32×32×1 Instanzen im vollen Sektor");
  assert.equal(mesh.frustumCulled, true, "fertige Sektoren nutzen wieder analytisches Frustum-Culling");

  for (const name of ["aInfo", "aShade", "aTint"]) {
    const attr = mesh.geometry.getAttribute(name);
    assert.deepEqual(attr.updateRanges, [
      { start: 0, count: 2048 },
      { start: 2048, count: 2048 },
    ], `${name}: zwei contiguous 512-Instanz-Chunks statt eines Completion-Bursts`);
    assert.ok(attr.updateRanges.every((r) => r.count < attr.count * attr.itemSize), `${name}: kein Full-Buffer-Range`);
  }

  // The first visible prefix is already spatially uniform inside the 32 m sector.
  const info = mesh.geometry.getAttribute("aInfo").array;
  const quadrants = [0, 0, 0, 0];
  for (let i = 0; i < 512; i++) {
    quadrants[(info[i * 4] >= 16 ? 1 : 0) + (info[i * 4 + 2] >= 16 ? 2 : 0)]++;
  }
  for (const q of quadrants) assert.ok(q >= 96, `erster Präfix uniform im Sektor: ${quadrants.join("/")}`);

  // Same world inputs reproduce the same bytes/prefix order exactly.
  const repeat = new GrassSystem(uniformGrassSampler(), () => 10, { ...options, buildBudgetMs: 8 });
  pumpGrass(repeat, 8, 8, undefined, 20);
  const repeatInfo = (repeat.group.children[0] as unknown as typeof mesh).geometry.getAttribute("aInfo").array;
  assert.deepEqual(Array.from(repeatInfo.slice(0, 64)), Array.from(info.slice(0, 64)), "Sektor-Instanzpräfix ist deterministisch");
  repeat.dispose();
  sys.dispose();
});

test("grass density importance scan keeps the mean placement rate in sparse sectors", () => {
  const densityByte = 128;
  const sampler = uniformGrassSampler(densityByte);
  const target = 400;
  const sys = new GrassSystem(sampler, () => 10, { sectorSize: 32, viewDistance: 0, density: target / (32 * 32), buildBudgetMs: 20 });
  sys.update(8, 8);
  assert.equal(sys.stats.pending, 0);
  const expected = Math.ceil(cellScatterCapacity(target) * (densityByte / 255));
  assert.equal(sys.stats.instances, expected, "halb dichte Makrozelle scannt nur den statistisch nötigen Kandidatenanteil");
  assert.equal(sys.stats.skipDensity, 0, "innerhalb des Maximums ist die skalierte Akzeptanz exakt kompensiert");
  sys.dispose();
});

test("grass distance LOD uses uniform count prefixes, sector far geometry and bounded reusable slots", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { sectorSize: 32, viewDistance: 40, density: 0.5, buildBudgetMs: 8, maxBuildPerFrame: 8 });
  pumpGrass(sys, 400, 1500);
  assert.equal(sys.stats.pending, 0, "Ring vollständig gebaut");
  assert.equal(sys.stats.pendingVisible, 0, "Readiness-Zähler wird nach dem letzten Build wieder null");
  assert.ok(sys.stats.instances > 1000, `Vollzählige Instanzen: ${sys.stats.instances}`);
  assert.ok(sys.stats.visibleInstances < sys.stats.instances, `Fernsektoren reduziert: ${sys.stats.visibleInstances}/${sys.stats.instances}`);
  const meshes = sys.group.children as unknown as Array<{ name: string; count: number; material: unknown; geometry: { getAttribute(name: string): { count: number } } }>;
  const vertexCounts = new Set(meshes.map((m) => m.geometry.getAttribute("position").count));
  assert.ok(vertexCounts.has(30), "Nahe Sektoren nutzen gekrümmte 5-Vertexpaare/18-Dreiecks-Büschel");
  assert.ok(vertexCounts.has(18), "Ferne Sektoren nutzen vereinfachte 3-Vertexpaare/6-Dreiecks-Büschel");
  for (const mesh of meshes) {
    const count = mesh.geometry.getAttribute("position").count;
    assert.ok(count === 30 || count === 18, `pro Sektor genau eine einheitliche near/far-Geometrie: ${count}`);
  }
  assert.equal(new Set(meshes.map((m) => m.material)).size, 1, "alle Sektoren teilen eine Grass-Materialinstanz");
  assert.ok(sys.stats.triangles < sys.stats.instances * 18, "Dreiecksschätzung berücksichtigt LOD");
  const first = meshes[0] as unknown as {
    name: string;
    boundingSphere?: { center: { x: number; y: number; z: number }; radius: number };
    instanceMatrix: { array: ArrayLike<number>; count: number; updateRanges: Array<{ start: number; count: number }> };
  };
  assert.ok(first.boundingSphere, "analytische Sektorbounds vorhanden");
  assert.ok(first.boundingSphere!.radius > 22, "Sektorbounds decken die 32-m-Halbdiagonale");
  const parts = first.name.split("_").map(Number);
  assert.ok(Math.abs(first.boundingSphere!.center.x - (parts[2] + 0.5) * 32) < 1e-4, "Bounds sind x-sektorzentriert");
  assert.ok(Math.abs(first.boundingSphere!.center.z - (parts[3] + 0.5) * 32) < 1e-4, "Bounds sind z-sektorzentriert");
  assert.equal(first.instanceMatrix.count, 1, "instanceMatrix ist nur der eine Dummy-Eintrag");
  assert.equal(first.instanceMatrix.array.length, 16, "keine full-capacity Matrixliste pro Sektor");
  assert.equal(first.instanceMatrix.updateRanges.length, 0, "instanceMatrix wird nie partiell oder vollständig hochgeladen");
  assert.ok([...first.instanceMatrix.array].every((v) => v === 0), "Grass-Shader braucht keine Instanzmatrizen");
  const slots = sys.stats.slots;
  pumpGrass(sys, 900, 1500, undefined, 120);
  assert.ok(sys.stats.slots <= slots + 2, `Render-Slots werden wieder verwendet: ${slots} → ${sys.stats.slots}`);
  for (const mesh of sys.group.children as unknown as Array<{ geometry: { getAttribute(name: string): { count: number; itemSize: number; updateRanges: Array<{ count: number }> } } }>) {
    for (const name of ["aInfo", "aShade", "aTint"]) {
      const attr = mesh.geometry.getAttribute(name);
      assert.ok(attr.updateRanges.every((r) => r.count <= 512 * attr.itemSize), `${name}: auch Slot-Reuse bleibt in Upload-Chunks`);
      assert.ok(attr.updateRanges.every((r) => r.count < attr.count * attr.itemSize), `${name}: kein Full-Buffer-Upload bei Slot-Reuse`);
    }
  }
  sys.dispose();
});

test("grass sector geometry LOD is conservative, hysteretic and shares instance attributes", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, {
    sectorSize: 32, viewDistance: 40, density: 0.2, buildBudgetMs: 8, maxBuildPerFrame: 8,
    geometryLodDistance: 8, geometryLodHysteresis: 4,
  });
  pumpGrass(sys, 16, 16);
  const sectorMesh = () => sys.group.children.find((m) => (m as { name?: string }).name === "grass_sector_0_0") as unknown as {
    count: number; geometry: { getAttribute(name: string): { count: number } & object };
  } | undefined;
  assert.ok(sectorMesh(), "Zielsektor gebaut");
  const nearGeometry = sectorMesh()!.geometry;
  assert.equal(nearGeometry.getAttribute("position").count, 30, "Kamera im Sektor: konservativ nahe Geometrie");

  for (let i = 0; i < 3; i++) sys.update(39, 16); // 7 m: Hysterese-Totzone, near bleibt stabil
  assert.equal(sectorMesh()!.geometry, nearGeometry, "Hysterese verhindert Flackern Richtung far");
  for (let i = 0; i < 3; i++) sys.update(45, 16); // 13 m von der Sektorfläche: jenseits 8+4 m
  const farGeometry = sectorMesh()!.geometry;
  assert.notEqual(farGeometry, nearGeometry);
  assert.equal(farGeometry.getAttribute("position").count, 18, "eindeutig ferner Sektor nutzt 6-Dreiecks-Büschel");
  assert.equal(farGeometry.getAttribute("aInfo"), nearGeometry.getAttribute("aInfo"), "near/far teilen aInfo");
  assert.equal(farGeometry.getAttribute("aShade"), nearGeometry.getAttribute("aShade"), "near/far teilen aShade");
  assert.equal(farGeometry.getAttribute("aTint"), nearGeometry.getAttribute("aTint"), "near/far teilen aTint");

  for (let i = 0; i < 3; i++) sys.update(41, 16); // 9 m: in der Hysterese bleibt der Sektor stabil fern
  assert.equal(sectorMesh()!.geometry, farGeometry, "Hysterese verhindert Flackern Richtung near");
  for (let i = 0; i < 3; i++) sys.update(35, 16); // 3 m: eindeutig innerhalb 8−4 m
  assert.equal(sectorMesh()!.geometry, nearGeometry, "nahe Sektorfläche stellt die volle Geometrie wieder her");
  sys.dispose();
});

test("grass system suspends streaming when vertical camera distance exceeds the fade range", () => {
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, { sectorSize: 32, viewDistance: 20, density: 0.2, buildBudgetMs: 8 }, () => 45);
  pumpGrass(sys, 400, 1500, 11.7);
  assert.ok(sys.stats.cells > 0, "Bodenkamera streamt Gras");
  sys.update(400, 1500, 60);
  assert.equal(sys.stats.suspended, 0, "nahe höhere Grassflächen verhindern das Abschalten");
  assert.ok(sys.stats.cells > 0);
  sys.update(400, 1500, 131);
  assert.equal(sys.stats.suspended, 1);
  assert.equal(sys.stats.cells, 0);
  assert.equal(sys.stats.instances, 0);
  assert.equal(sys.group.children.length, 0, "unsichtbare Fernsektoren werden aus dem Streaming entfernt");
  pumpGrass(sys, 400, 1500, 11.7);
  assert.equal(sys.stats.suspended, 0);
  assert.ok(sys.stats.cells > 0, "beim Abstieg wird der Ring erneut aufgebaut");
  sys.dispose();
});

test("macro no-grass sectors complete empty without allocating a render slot", () => {
  const sys = new GrassSystem(uniformGrassSampler(0), () => 10, { sectorSize: 32, viewDistance: 0, density: 1, buildBudgetMs: 8 });
  sys.update(8, 8);
  assert.equal(sys.stats.wanted, 1);
  assert.equal(sys.stats.builds, 1);
  assert.equal(sys.stats.pending, 0);
  assert.equal(sys.stats.cells, 0);
  assert.equal(sys.stats.instances, 0);
  assert.equal(sys.stats.slots, 0, "Wasser/Pfad/Fels erzeugt keinen GPU-Slot");
  assert.equal(sys.group.children.length, 0);
  sys.dispose();
});


test("preallocated grass slots stay hidden in the scene as warm-up targets and prevent pool growth", () => {
  const preallocated = grassSectorSlotUpperBound(20, 32);
  assert.ok(preallocated >= 10, `konservative Obergrenze für den kleinen Testring: ${preallocated}`);
  const sys = new GrassSystem(uniformGrassSampler(), () => 10, {
    sectorSize: 32, viewDistance: 20, density: 0.01, buildBudgetMs: 8, maxBuildPerFrame: 8, preallocateSlots: preallocated,
  });
  assert.equal(sys.group.children.length, preallocated, "vorab allokierte Slots sind bereits Warm-up-Kandidaten im Szenengraph");
  for (const child of sys.group.children as unknown as Array<{ name: string; visible: boolean; count: number }>) {
    assert.equal(child.name, "grass_sector_slot");
    assert.equal(child.visible, false, "freie Slots kosten im Normalrender keinen Render-Object-Pass");
    assert.equal(child.count, 0);
  }

  pumpGrass(sys, 400, 1500, undefined, 40);
  assert.equal(sys.stats.slots, preallocated, "der Streaming-Ring wächst nicht über die vorab erwärmten Slots hinaus");
  assert.equal(sys.group.children.length, preallocated, "persistent slots werden beim Streaming nicht erneut hinzugefügt");
  assert.ok(sys.stats.cells > 0, "Testring wurde trotzdem gebaut");
  pumpGrass(sys, 900, 1500, undefined, 60);
  assert.equal(sys.stats.slots, preallocated, "auch spätere Ringverschiebungen erzeugen keine neuen first-use GPU-Slots");
  assert.equal(sys.group.children.length, preallocated, "freigegebene persistente Slots bleiben versteckt im Warm-up-Pool");
  sys.dispose();
});

test("main keeps nograss mode and optional grass update wiring intact", () => {
  const main = readFileSync(new URL("../src/main.ts", import.meta.url), "utf8");
  assert.ok(main.includes('!params.has("nograss")'), "?nograss verhindert weiterhin die GrassSystem-Erzeugung");
  assert.ok(main.includes("grass?.update("), "bestehendes Gras bleibt optional/flight-suspension-fähig");
  assert.ok(main.includes("preallocateSlots: grassSectorSlotUpperBound"), "Produktionsgras allokiert seine Streaming-Slots vor dem Warm-up");
});
