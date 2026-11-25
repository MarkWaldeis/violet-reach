// Cell-streamed GPU grass for Violet Reach (GRAFIK_PLAN.md Phase 4.1).
// Blades are generated per terrain cell around the camera, instanced per cell,
// with density/height/dryness/colour taken from the same macro maps as the ground
// shader, so the grass carpet blends seamlessly into the terrain at distance.
//
// Performance architecture:
//   · cell construction is incremental and bounded by buildBudgetMs per frame
//   · render slots (materials, geometries, instance buffers) are pooled and reused instead of
//     disposing a burst of streaming cells whenever the camera crosses a cell boundary
//   · candidates are scanned in a fixed shuffled order, so every mesh.count prefix is a uniform
//     sample of the full cell; distance density is then a no-rebuild prefix LOD
//   · distant cells switch the shared clump vertex data from curved 18-triangle clumps to
//     straight 6-triangle clumps while keeping the exact same instances and material inputs
import {
  BufferGeometry, DynamicDrawUsage, Group, InstancedBufferAttribute, InstancedMesh,
} from "three/webgpu";
import { buildBladeClump, clumpTriangles } from "./grass-clump.ts";
import { grassMaterial } from "./grass-material.ts";
import {
  cellScatterCapacity, cellScatterOrder, cellScatterPositionInto, cellScatterPositions, hash2,
  type GrassMacroSample, type GrassMacroSampler, type GrassScatterPoint,
} from "./grass-macro.ts";

export interface GrassSystemOptions {
  cellSize?: number;
  /** metres; grass cells stream in inside this radius */
  viewDistance?: number;
  /** target clumps per m² at density 1.0, near ring */
  density?: number;
  /** safety cap for completed cells per frame (the millisecond budget is the real limit) */
  maxBuildPerFrame?: number;
  /** milliseconds of scatter/instance construction work per animation frame */
  buildBudgetMs?: number;
  /** fraction of instances drawn at/after distanceDensityEnd (uniform prefix LOD, no rebuild) */
  distanceDensityFactor?: number;
  /** metres; full instance count inside this distance */
  distanceDensityStart?: number;
  /** metres; distanceDensityFactor reached here (same default as the material fade start) */
  distanceDensityEnd?: number;
  /** metres; beyond this distance curved clumps switch to straight one-triangle blades */
  geometryLodDistance?: number;
}

interface Cell {
  cx: number;
  cz: number;
  /** undefined = not built yet, null = built but empty, InstancedMesh = visible streamable mesh */
  mesh?: InstancedMesh | null;
  slot?: CellSlot;
  build?: CellBuild;
  /** full near-ring instance count independent of the currently applied distance-density count */
  count: number;
  maxY?: number | null;
}

interface CellBuild {
  cursor: number;
  total: number;
  orderCursor: number;
  /** conservative upper bound of macro density in this cell; also the importance-sampling scale */
  densityScale: number;
  placed: number;
  slot: CellSlot;
  sample: GrassMacroSample;
  point: GrassScatterPoint;
}

interface CellSlot {
  nearGeometry: BufferGeometry;
  farGeometry: BufferGeometry;
  mesh: InstancedMesh;
  aInfo: InstancedBufferAttribute;
  aShade: InstancedBufferAttribute;
  tint: InstancedBufferAttribute;
  free: boolean;
}

export class GrassSystem {
  readonly group = new Group();
  #cells = new Map<string, Cell>();
  #base: Record<"near" | "far", BufferGeometry>;
  #sampler: GrassMacroSampler;
  #heightAt: (x: number, z: number) => number | undefined;
  #maxHeightInRect?: (minX: number, minZ: number, maxX: number, maxZ: number) => number | undefined;
  #opts: Required<GrassSystemOptions>;
  #lastKey = "";
  #scatterTarget: number;
  #scatterCapacity: number;
  #scatterOrder: Uint32Array;
  #slots: CellSlot[] = [];
  #freeSlots: CellSlot[] = [];
  #nearTriangles: number;
  #farTriangles: number;
  stats = {
    cells: 0, instances: 0, visibleInstances: 0, triangles: 0,
    skipDensity: 0, skipHeight: 0, placed: 0, builds: 0, updates: 0, wanted: 0,
    pending: 0, building: 0, slots: 0, pooled: 0, suspended: 0,
  };

  constructor(sampler: GrassMacroSampler, heightAt: (x: number, z: number) => number | undefined, options: GrassSystemOptions = {}, maxHeightInRect?: (minX: number, minZ: number, maxX: number, maxZ: number) => number | undefined) {
    this.#sampler = sampler;
    this.#heightAt = heightAt;
    this.#maxHeightInRect = maxHeightInRect;
    const cellSize = options.cellSize ?? 16;
    const viewDistance = options.viewDistance ?? 96;
    this.#opts = {
      cellSize,
      viewDistance,
      density: options.density ?? 5.5,
      maxBuildPerFrame: options.maxBuildPerFrame ?? 8,
      buildBudgetMs: options.buildBudgetMs ?? 1.5,
      distanceDensityFactor: options.distanceDensityFactor ?? 0.5,
      // Keep full density everywhere before the material's existing fade/width compensation.
      // Thinning inside that same envelope avoids a visible sparse band at mid distance.
      distanceDensityStart: options.distanceDensityStart ?? viewDistance * 0.72,
      distanceDensityEnd: options.distanceDensityEnd ?? viewDistance,
      geometryLodDistance: options.geometryLodDistance ?? viewDistance * 0.44,
    };
    const clump = { blades: 6, height: 0.58, width: 0.055, spread: 0.42, arc: 0.55, seed: 3 };
    this.#base = {
      near: buildBladeClump({ ...clump, curved: true }),
      // Dropping the curved mid row removes ~19% of a blade's silhouette area. The straight
      // distance clump is therefore 24% wider, which keeps its coverage/brightness visually
      // anchored to the near clump without adding a single triangle.
      far: buildBladeClump({ ...clump, width: clump.width * 1.24, curved: false }),
    };
    this.#nearTriangles = clumpTriangles({ ...clump, curved: true });
    this.#farTriangles = clumpTriangles({ ...clump, curved: false });
    this.#scatterTarget = Math.round(cellSize * cellSize * this.#opts.density);
    this.#scatterCapacity = cellScatterCapacity(this.#scatterTarget);
    // A different seed family than the positional hashes avoids correlating the prefix order
    // with acceptance/yaw hashes. One shared permutation is enough: all cells use the same grid.
    this.#scatterOrder = cellScatterOrder(this.#scatterCapacity, 113.17);
  }

  update(px: number, pz: number, py?: number) {
    this.stats.updates++;
    const { cellSize, viewDistance } = this.#opts;
    const groundY = this.#heightAt(px, pz);
    let verticalDistance = 0;
    if (py !== undefined && groundY !== undefined) {
      let supportY = groundY;
      if (py - groundY > viewDistance * 0.5 && this.#maxHeightInRect) {
        const radius = viewDistance + cellSize * 1.25;
        supportY = this.#maxHeightInRect(px - radius, pz - radius, px + radius, pz + radius) ?? groundY;
      }
      verticalDistance = py - supportY;
    }
    if (verticalDistance > viewDistance) {
      for (const cell of this.#cells.values()) this.#releaseCell(cell);
      this.#cells.clear();
      this.#lastKey = "";
      this.stats.wanted = 0;
      this.stats.suspended = 1;
      this.#refreshStats();
      return;
    }
    this.stats.suspended = 0;
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
        if (!wanted.has(k)) this.#releaseCell(cell);
      }
      this.#cells = wanted;
      this.stats.wanted = wanted.size;
    }

    this.#buildBudgeted(px, pz, py);
    this.#updateDistanceLODs(px, pz, py);
    this.#refreshStats();
  }

  /** Process the nearest incomplete cells, but never more than buildBudgetMs in one frame. */
  #buildBudgeted(px: number, pz: number, py?: number) {
    const { cellSize, maxBuildPerFrame, buildBudgetMs } = this.#opts;
    const pending = [...this.#cells.values()].filter((c) => c.mesh === undefined);
    if (!pending.length) return;
    pending.sort((a, b) =>
      Number(!!b.build) - Number(!!a.build) ||
      Math.hypot((a.cx + 0.5) * cellSize - px, (a.cz + 0.5) * cellSize - pz) -
      Math.hypot((b.cx + 0.5) * cellSize - px, (b.cz + 0.5) * cellSize - pz)
    );
    const deadline = performance.now() + Math.max(0, buildBudgetMs);
    let completed = 0;
    for (const cell of pending) {
      if (!this.#cellPotentiallyVisible(cell, px, pz, py)) continue;
      if (completed >= maxBuildPerFrame) break;
      if (completed > 0 && performance.now() >= deadline) break;
      if (!this.#buildSlice(cell, deadline)) break; // budget exhausted inside the active cell
      completed++;
    }
  }

  /**
   * Advance one cell in small deterministic chunks. Instance data is written directly into the
   * pooled fixed-capacity GPU attributes, so completing a cell is only a buffer-upload mark plus
   * bounding-sphere update — no large temporary arrays, geometry allocation or material creation.
   */
  #buildSlice(cell: Cell, deadline: number): boolean {
    let job = cell.build;
    if (!job) {
      const x0 = cell.cx * this.#opts.cellSize, z0 = cell.cz * this.#opts.cellSize;
      const densityScale = this.#sampler.densityCellMax(x0, z0, x0 + this.#opts.cellSize, z0 + this.#opts.cellSize);
      if (densityScale < 0.03) {
        // Whole-cell macro rejection: water/path/rock/sand cells need neither height queries nor a slot.
        cell.count = 0;
        cell.mesh = null;
        this.stats.builds++;
        return true;
      }
      job = this.#startBuild(cell, densityScale);
    }
    const info = job.slot.aInfo.array as Float32Array;
    const shade = job.slot.aShade.array as Float32Array;
    const tint = job.slot.tint.array as Float32Array;
    const matrix = job.slot.mesh.instanceMatrix.array as Float32Array;
    let sinceClockCheck = 0;

    while (job.cursor < job.total) {
      if (sinceClockCheck >= 32) {
        if (performance.now() >= deadline) return false;
        sinceClockCheck = 0;
      }
      const scatterIndex = this.#scatterOrder[job.orderCursor++];
      if (job.orderCursor >= this.#scatterCapacity) job.orderCursor = 0;
      job.cursor++;
      const pt = cellScatterPositionInto(cell.cx, cell.cz, this.#opts.cellSize, this.#scatterTarget, 7, scatterIndex, job.point);
      sinceClockCheck++;

      const density = this.#sampler.densityAt(pt.x, pt.z);
      // density mask: stochastic thinning, hard zero on water/paths/rock/sand. The scan itself is
      // importance-sampled by the cell's conservative maximum density; multiplying h1 by that upper
      // bound preserves the mean placement rate while skipping impossible trials wholesale.
      if (density < 0.03 || pt.h1 * job.densityScale > density) { this.stats.skipDensity++; continue; }
      const s = this.#sampler.sampleInto(pt.x, pt.z, job.sample);
      const y = this.#heightAt(pt.x, pt.z);
      if (y === undefined) { this.stats.skipHeight++; continue; }

      const scale = 0.72 + pt.h2 * 0.55;
      const hs = 0.65 + s.heightScale * 0.7;
      const i = job.placed++;
      const i4 = i * 4;
      info[i4] = pt.x;
      info[i4 + 1] = y - 0.02;
      info[i4 + 2] = pt.z;
      info[i4 + 3] = pt.h1;
      shade[i4] = Math.min(1, s.canopyShadow * (0.55 + s.ao * 0.45)); // canopy shadow x macro AO
      shade[i4 + 1] = s.dryMix;
      shade[i4 + 2] = hs * scale;
      shade[i4 + 3] = scale;
      // macro bytes are sRGB-encoded; the terrain shader samples them with an SRGBColorSpace
      // texture (auto-linearised), so the instance tint must be linearised here as well —
      // otherwise blades render raw-sRGB-as-linear (bright but badly desaturated/muddy).
      const i3 = i * 3;
      tint[i3] = srgbToLinear(s.tintR);
      tint[i3 + 1] = srgbToLinear(s.tintG);
      tint[i3 + 2] = srgbToLinear(s.tintB);

      // per-instance transforms: pure translation to the world position (rotation/scale are
      // encoded in geometry fan-out and aShade, so wind direction stays world-coherent). All
      // off-diagonal entries are zero in the fixed-capacity matrix buffer and never need rewriting.
      const mo = i * 16;
      matrix[mo] = 1; matrix[mo + 5] = 1; matrix[mo + 10] = 1; matrix[mo + 15] = 1;
      matrix[mo + 12] = info[i4];
      matrix[mo + 13] = info[i4 + 1];
      matrix[mo + 14] = info[i4 + 2];
    }

    this.#finishBuild(cell, job);
    return true;
  }

  #startBuild(cell: Cell, densityScale: number): CellBuild {
    const job: CellBuild = {
      cursor: 0,
      total: Math.max(1, Math.ceil(this.#scatterCapacity * densityScale)),
      orderCursor: Math.floor(hash2(cell.cx, cell.cz, 29.71) * this.#scatterCapacity),
      densityScale,
      placed: 0,
      slot: this.#acquireSlot(),
      sample: { density: 0, heightScale: 0, dryMix: 0, canopyShadow: 1, tintR: 0.4, tintG: 0.42, tintB: 0.26, ao: 1 },
      point: { x: 0, z: 0, h1: 0, h2: 0 },
    };
    cell.build = job;
    return job;
  }

  #finishBuild(cell: Cell, job: CellBuild) {
    cell.build = undefined;
    this.stats.builds++;
    this.stats.placed += job.placed;
    if (!job.placed) {
      cell.count = 0;
      cell.mesh = null;
      this.#releaseSlot(job.slot);
      return;
    }

    const { slot } = job;
    // Only the placed prefix changed. Fixed-capacity slots are reused across sparse and dense cells,
    // so partial update ranges avoid re-uploading hundreds of unused instances on every streaming reuse.
    for (const [attribute, itemSize] of [
      [slot.aInfo, 4], [slot.aShade, 4], [slot.tint, 3], [slot.mesh.instanceMatrix, 16],
    ] as Array<[InstancedBufferAttribute, number]>) {
      attribute.clearUpdateRanges();
      attribute.addUpdateRange(0, job.placed * itemSize);
      attribute.needsUpdate = true;
    }
    slot.mesh.count = job.placed;
    slot.mesh.geometry = slot.nearGeometry;
    slot.mesh.name = `grass_${cell.cx}_${cell.cz}`;
    // Culling must cover the full instance set, not only the currently applied distance-density
    // prefix. computeBoundingSphere() intentionally uses mesh.count before the prefix is reduced.
    slot.mesh.boundingSphere = null;
    slot.mesh.computeBoundingSphere();
    cell.count = job.placed;
    cell.mesh = slot.mesh;
    cell.slot = slot;
    this.group.add(slot.mesh);
  }

  /**
   * Apply distance LODs without rebuilding: count prefixes are uniform because of the shuffled
   * scatter order, and geometry switching only selects near/far shared vertex data on the slot.
   */
  #updateDistanceLODs(px: number, pz: number, py?: number) {
    for (const cell of this.#cells.values()) {
      if (!cell.mesh || !cell.slot || !cell.count) continue;
      if (!this.#cellPotentiallyVisible(cell, px, pz, py)) {
        cell.mesh.count = 0;
        continue;
      }
      const distance = this.#cellDistance(cell, px, pz);
      const useFar = distance >= this.#opts.geometryLodDistance;
      const geometry = useFar ? cell.slot.farGeometry : cell.slot.nearGeometry;
      if (cell.mesh.geometry !== geometry) cell.mesh.geometry = geometry;
      cell.mesh.count = this.#visibleCount(cell.count, distance);
    }
  }

  #cellPotentiallyVisible(cell: Cell, px: number, pz: number, py?: number) {
    if (py === undefined || !this.#maxHeightInRect) return true;
    if (cell.maxY === undefined) {
      const x0 = cell.cx * this.#opts.cellSize, z0 = cell.cz * this.#opts.cellSize;
      cell.maxY = this.#maxHeightInRect(x0, z0, x0 + this.#opts.cellSize, z0 + this.#opts.cellSize) ?? null;
    }
    if (cell.maxY === null) return true;
    const horizontal = Math.max(0, this.#cellDistance(cell, px, pz) - this.#opts.cellSize * Math.SQRT1_2);
    const vertical = Math.max(0, py - (cell.maxY + 1.5));
    return Math.hypot(horizontal, vertical) <= this.#opts.viewDistance;
  }

  #visibleCount(count: number, distance: number): number {
    if (count <= 1) return count;
    const start = this.#opts.distanceDensityStart;
    const end = Math.max(start + 0.001, this.#opts.distanceDensityEnd);
    const factor = Math.min(1, Math.max(0, this.#opts.distanceDensityFactor));
    if (distance <= start) return count;
    const farCount = Math.max(1, Math.round(count * factor));
    if (distance >= end) return farCount;
    const t = Math.min(1, Math.max(0, (distance - start) / (end - start)));
    const smooth = t * t * (3 - 2 * t);
    const fraction = 1 - (1 - factor) * smooth;
    return Math.max(farCount, Math.min(count, Math.round(count * fraction)));
  }

  #cellDistance(cell: Cell, px: number, pz: number) {
    const { cellSize } = this.#opts;
    return Math.hypot((cell.cx + 0.5) * cellSize - px, (cell.cz + 0.5) * cellSize - pz);
  }

  #acquireSlot(): CellSlot {
    const slot = this.#freeSlots.pop() ?? this.#createSlot();
    slot.free = false;
    return slot;
  }

  #releaseCell(cell: Cell) {
    const slot = cell.build?.slot ?? cell.slot;
    if (slot) this.#releaseSlot(slot);
    cell.build = undefined;
    cell.slot = undefined;
    cell.mesh = undefined;
    cell.count = 0;
  }

  #releaseSlot(slot: CellSlot) {
    if (slot.free) return;
    if (slot.mesh.parent === this.group) this.group.remove(slot.mesh);
    slot.mesh.count = 0;
    slot.free = true;
    this.#freeSlots.push(slot);
  }

  #createSlot(): CellSlot {
    const capacity = this.#scatterCapacity;
    const aInfo = new InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    const aShade = new InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    const tint = new InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
    aInfo.setUsage(DynamicDrawUsage);
    aShade.setUsage(DynamicDrawUsage);
    tint.setUsage(DynamicDrawUsage);
    const nearGeometry = this.#instanceGeometry(this.#base.near, aInfo, aShade);
    const farGeometry = this.#instanceGeometry(this.#base.far, aInfo, aShade);
    const cellMaterial = grassMaterial({ aInfo, aShade }, { fadeStart: this.#opts.viewDistance * 0.72, fadeEnd: this.#opts.viewDistance });
    // Constructing with count 0 avoids InstancedMesh's otherwise mandatory identity-matrix
    // initialisation pass; the fixed-capacity matrix attribute below is the one really used.
    const mesh = new InstancedMesh(nearGeometry, cellMaterial, 0);
    mesh.instanceMatrix = new InstancedBufferAttribute(new Float32Array(capacity * 16), 16);
    mesh.instanceMatrix.setUsage(DynamicDrawUsage);
    mesh.instanceColor = tint;
    mesh.count = 0;
    mesh.castShadow = false;
    mesh.receiveShadow = true;
    mesh.frustumCulled = true;
    mesh.name = "grass_slot";
    const slot: CellSlot = { nearGeometry, farGeometry, mesh, aInfo, aShade, tint, free: true };
    this.#slots.push(slot);
    return slot;
  }

  #instanceGeometry(base: BufferGeometry, aInfo: InstancedBufferAttribute, aShade: InstancedBufferAttribute) {
    const geometry = new BufferGeometry();
    geometry.index = base.index;
    for (const name of ["position", "uv", "color", "normal"] as const) {
      const attr = base.getAttribute(name);
      if (attr) geometry.setAttribute(name, attr);
    }
    geometry.setAttribute("aInfo", aInfo);
    geometry.setAttribute("aShade", aShade);
    return geometry;
  }

  #refreshStats() {
    let cells = 0, instances = 0, visibleInstances = 0, triangles = 0, pending = 0, building = 0;
    for (const cell of this.#cells.values()) {
      if (cell.mesh === undefined) {
        pending++;
        if (cell.build) building++;
      } else if (cell.mesh && cell.count > 0) {
        cells++;
        instances += cell.count;
        visibleInstances += cell.mesh.count;
        triangles += cell.mesh.count * (cell.mesh.geometry === cell.slot?.farGeometry ? this.#farTriangles : this.#nearTriangles);
      }
    }
    this.stats.cells = cells;
    this.stats.instances = instances;
    this.stats.visibleInstances = visibleInstances;
    this.stats.triangles = triangles;
    this.stats.pending = pending;
    this.stats.building = building;
    this.stats.slots = this.#slots.length;
    this.stats.pooled = this.#freeSlots.length;
  }

  /** Release all pooled GPU resources. Streaming itself intentionally does not call this. */
  dispose() {
    for (const cell of this.#cells.values()) this.#releaseCell(cell);
    this.#cells.clear();
    for (const slot of this.#slots) {
      slot.mesh.dispose();
      slot.nearGeometry.dispose();
      slot.farGeometry.dispose();
      (slot.mesh.material as { dispose?: () => void }).dispose?.();
    }
    this.#slots = [];
    this.#freeSlots = [];
    this.#lastKey = "";
    this.#refreshStats();
  }
}

/** sRGB-encoded byte fraction (0..1) → linear-light fraction, matching the GPU's SRGBColorSpace decode. */
export function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** pure helpers exposed for tests */
export { cellScatterPositions, hash2 };
export type { GrassMacroSampler };
