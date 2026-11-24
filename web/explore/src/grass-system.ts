// Cell-streamed GPU grass for Violet Reach (GRAFIK_PLAN.md Phase 4.1).
// Blades are generated per terrain cell around the camera, instanced per cell,
// with density/height/dryness/colour taken from the same macro maps as the ground
// shader, so the grass carpet blends seamlessly into the terrain at distance.
import {
  BufferGeometry, Color, DoubleSide, Group, InstancedBufferAttribute, InstancedMesh, MeshBasicMaterial,
} from "three/webgpu";
import { buildBladeClump } from "./grass-clump.ts";
import { grassMaterial } from "./grass-material.ts";
import { cellScatterPositions, hash2, type GrassMacroSampler } from "./grass-macro.ts";

export interface GrassSystemOptions {
  cellSize?: number;
  /** metres; grass cells stream in inside this radius */
  viewDistance?: number;
  /** target clumps per m² at density 1.0, near ring */
  density?: number;
  maxBuildPerFrame?: number;
}

interface Cell {
  cx: number;
  cz: number;
  mesh?: InstancedMesh;
  count: number;
}

export class GrassSystem {
  readonly group = new Group();
  #cells = new Map<string, Cell>();
  #base: Record<"near", BufferGeometry>;
  #sampler: GrassMacroSampler;
  #heightAt: (x: number, z: number) => number | undefined;
  #opts: Required<GrassSystemOptions>;
  #lastKey = "";
  stats = { cells: 0, instances: 0, triangles: 0, skipDensity: 0, skipHeight: 0, placed: 0, builds: 0, updates: 0, wanted: 0 };

  constructor(sampler: GrassMacroSampler, heightAt: (x: number, z: number) => number | undefined, options: GrassSystemOptions = {}) {
    this.#sampler = sampler;
    this.#heightAt = heightAt;
    this.#opts = {
      cellSize: options.cellSize ?? 16,
      viewDistance: options.viewDistance ?? 96,
      density: options.density ?? 5.5,
      maxBuildPerFrame: options.maxBuildPerFrame ?? 1,
    };
    this.#base = { near: buildBladeClump({ blades: 6, height: 0.58, width: 0.055, spread: 0.42, arc: 0.55, seed: 3 }) };
  }

  update(px: number, pz: number) {
    this.stats.updates++;
    const { cellSize, viewDistance, maxBuildPerFrame } = this.#opts;
    const ccx = Math.floor(px / cellSize), ccz = Math.floor(pz / cellSize);
    const ring = Math.ceil(viewDistance / cellSize);
    const key = `${ccx},${ccz}`;
    if (key !== this.#lastKey) {
      this.#lastKey = key;
      const wanted = new Map<string, Cell>();
      for (let dz = -ring; dz <= ring; dz++) {
        for (let dx = -ring; dx <= ring; dx++) {
          const cx = ccx + dx, cz = ccz + dz;
          const mx = (cx + 0.5) * cellSize, mz = (cz + 0.5) * cellSize;
          if (Math.hypot(mx - px, mz - pz) > viewDistance + cellSize * 0.75) continue;
          const k = `${cx},${cz}`;
          wanted.set(k, this.#cells.get(k) ?? { cx, cz, count: 0 });
        }
      }
      for (const [k, cell] of this.#cells) {
        if (!wanted.has(k) && cell.mesh) {
          this.group.remove(cell.mesh);
          (cell.mesh.material as { dispose?: () => void }).dispose?.();
          cell.mesh.dispose();
        }
      }
      this.#cells = wanted;
      this.stats.wanted = wanted.size;
    }
    // build budget: nearest first
    let built = 0;
    const pending = [...this.#cells.values()].filter((c) => c.mesh === undefined)
      .sort((a, b) => (Math.hypot((a.cx + 0.5) * cellSize - px, (a.cz + 0.5) * cellSize - pz)) - (Math.hypot((b.cx + 0.5) * cellSize - px, (b.cz + 0.5) * cellSize - pz)));
    for (const cell of pending) {
      if (built >= maxBuildPerFrame) break;
      this.#build(cell);
      built++;
    }
    this.stats.cells = [...this.#cells.values()].filter((c) => c.mesh !== undefined && c.count > 0).length;
  }


  /** QA helper: swap all cells to unlit red for render-path isolation. */
  debugBasicMaterial() {
    const red = new MeshBasicMaterial({ color: new Color(1, 0.1, 0.1), side: DoubleSide });
    for (const child of this.group.children) (child as InstancedMesh).material = red;
  }
  #build(cell: Cell) {
    this.stats.builds++;
    const { cellSize, density } = this.#opts;
    const target = Math.round(cellSize * cellSize * density);
    const positions = cellScatterPositions(cell.cx, cell.cz, cellSize, target, 7);
    const info: number[] = [];
    const shade: number[] = [];
    const tint: number[] = [];
    let placed = 0;
    for (const pt of positions) {
      const s = this.#sampler.sample(pt.x, pt.z);
      // density mask: stochastic thinning, hard zero on water/paths/rock/sand
      if (s.density < 0.03 || pt.h1 > s.density) { this.stats.skipDensity++; continue; }
      const y = this.#heightAt(pt.x, pt.z);
      if (y === undefined) { this.stats.skipHeight++; continue; }
      const scale = 0.72 + pt.h2 * 0.55;
      const hs = 0.65 + s.heightScale * 0.7;
      info.push(pt.x, y - 0.02, pt.z, pt.h1);
      shade.push(
        Math.min(1, s.canopyShadow * (0.55 + s.ao * 0.45)), // canopy shadow x macro AO
        s.dryMix,
        hs * scale,
        scale,
      );
      // macro bytes are sRGB-encoded; the terrain shader samples them with an SRGBColorSpace
      // texture (auto-linearised), so the instance tint must be linearised here as well —
      // otherwise blades render raw-sRGB-as-linear (bright but badly desaturated/muddy).
      tint.push(srgbToLinear(s.tintR), srgbToLinear(s.tintG), srgbToLinear(s.tintB));
      placed++;
      this.stats.placed++;
    }
    cell.count = placed;
    if (!placed) { cell.mesh = null as never; return; }
    const geometry = new BufferGeometry();
    geometry.index = this.#base.near.index;
    for (const name of ["position", "uv", "color", "normal"] as const) {
      const attr = this.#base.near.getAttribute(name);
      if (attr) geometry.setAttribute(name, attr);
    }
    const aInfo = new InstancedBufferAttribute(new Float32Array(info), 4);
    const aShade = new InstancedBufferAttribute(new Float32Array(shade), 4);
    geometry.setAttribute("aInfo", aInfo);
    geometry.setAttribute("aShade", aShade);
    const cellMaterial = grassMaterial({ aInfo, aShade }, { fadeStart: this.#opts.viewDistance * 0.72, fadeEnd: this.#opts.viewDistance });
    const mesh = new InstancedMesh(geometry, cellMaterial, placed);
    mesh.instanceColor = new InstancedBufferAttribute(new Float32Array(tint), 3);
    mesh.count = placed;
    mesh.castShadow = false;
    mesh.receiveShadow = true;
    mesh.frustumCulled = true;
    // per-instance transforms: pure translation to the world position (rotation/scale are
    // encoded in geometry fan-out and aShade, so wind direction stays world-coherent)
    const m = mesh.instanceMatrix.array as Float32Array;
    for (let i = 0; i < placed; i++) {
      const o = i * 16;
      m[o + 0] = 1; m[o + 5] = 1; m[o + 10] = 1; m[o + 15] = 1;
      m[o + 12] = info[i * 4 + 0];
      m[o + 13] = info[i * 4 + 1];
      m[o + 14] = info[i * 4 + 2];
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.name = `grass_${cell.cx}_${cell.cz}`;
    cell.mesh = mesh;
    this.group.add(mesh);
    this.stats.instances += placed;
  }
}

/** sRGB-encoded byte fraction (0..1) → linear-light fraction, matching the GPU's SRGBColorSpace decode. */
export function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** pure helpers exposed for tests */
export { cellScatterPositions, hash2 };
export type { GrassMacroSampler };
