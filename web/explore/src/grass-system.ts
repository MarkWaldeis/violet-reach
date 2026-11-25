// Sector-streamed GPU grass for Violet Reach (GRAFIK_PLAN.md Phase 4.1).
// Blades are generated per 32 m terrain sector around the camera, instanced per sector,
// with density/height/dryness/colour taken from the same macro maps as the ground
// shader, so the grass carpet blends seamlessly into the terrain at distance.
//
// Performance architecture:
//   · sector construction is incremental and bounded by buildBudgetMs per frame
//   · render slots (geometries, instance buffers) are pooled and reused instead of
//     disposing a burst of streaming sectors whenever the circular working set changes
//   · candidates are scanned in a fixed shuffled order, so every mesh.count prefix is a uniform
//     sample of the full sector; distance density is then a no-rebuild prefix LOD
//   · accepted instances are written contiguously into that prefix and marked in bounded
//     update chunks while the invisible build mesh is already in the scene, spreading GPU
//     buffer uploads over the build instead of paying one large completion upload
//   · distant sectors switch the shared clump vertex data from curved 18-triangle clumps to
//     straight 6-triangle clumps while keeping the exact same instances and material inputs
//   · one sector is one mesh/render object independent of how many old 16 m cells it covers
import {
  BufferGeometry, Group, InstancedBufferAttribute, InstancedMesh, Sphere, Vector3,
} from "three/webgpu";
import { buildBladeClump, clumpTriangles } from "./grass-clump.ts";
import { grassMaterial } from "./grass-material.ts";
import {
  cellScatterCapacity, cellScatterOrder, cellScatterPositionInto, cellScatterPositions, hash2,
  type GrassMacroSample, type GrassMacroSampler, type GrassScatterPoint,
} from "./grass-macro.ts";

/** Instances per partial attribute upload. 512 instances ≈ 24 KiB across the three vec4 streams. */
const INSTANCE_UPLOAD_CHUNK = 512;

export interface GrassSystemOptions {
  /** metres; streaming/scatter sector edge length (default: 32) */
  sectorSize?: number;
  /** @deprecated backwards-compatible alias for sectorSize (new code should use sectorSize) */
  cellSize?: number;
  /** metres; grass sectors stream in inside this radius */
  viewDistance?: number;
  /** target clumps per m² at density 1.0, near ring */
  density?: number;
  /** safety cap for completed sectors per frame (the millisecond budget is the real limit) */
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
  /** metres of dead zone around geometryLodDistance; defaults to sectorSize/8 (4 m at 32 m) */
  geometryLodHysteresis?: number;
}

type ResolvedGrassSystemOptions = Required<Omit<GrassSystemOptions, "cellSize">>;

interface Sector {
  sx: number;
  sz: number;
  /** undefined = not built yet, null = built but empty, InstancedMesh = visible streamable mesh */
  mesh?: InstancedMesh | null;
  slot?: SectorSlot;
  build?: SectorBuild;
  /** full near-ring instance count independent of the currently applied distance-density count */
  count: number;
  maxY?: number | null;
  /** hysteresis state for the sector-wide geometry LOD; undefined/near is the conservative initial state */
  farLod?: boolean;
}

interface SectorBuild {
  cursor: number;
  total: number;
  orderCursor: number;
  /** conservative upper bound of macro density in this sector; also the importance-sampling scale */
  densityScale: number;
  placed: number;
  /** first instance index not yet covered by a queued partial attribute update */
  uploadCursor: number;
  minY: number;
  maxY: number;
  slot: SectorSlot;
  sample: GrassMacroSample;
  point: GrassScatterPoint;
}

interface SectorSlot {
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
  #sectors = new Map<string, Sector>();
  #base: Record<"near" | "far", BufferGeometry>;
  #sampler: GrassMacroSampler;
  #heightAt: (x: number, z: number) => number | undefined;
  #maxHeightInRect?: (minX: number, minZ: number, maxX: number, maxZ: number) => number | undefined;
  #opts: ResolvedGrassSystemOptions;
  #streamX = 0;
  #streamZ = 0;
  #streamInitialized = false;
  #scatterTarget: number;
  #scatterCapacity: number;
  #scatterOrder: Uint32Array;
  #slots: SectorSlot[] = [];
  #freeSlots: SectorSlot[] = [];
  #nearTriangles: number;
  #farTriangles: number;
  #material: ReturnType<typeof grassMaterial>;
  stats = {
    // `cells` is the stable bench/QA name; `sectors` is the precise internal streaming unit name.
    cells: 0, sectors: 0, instances: 0, visibleInstances: 0, triangles: 0,
    skipDensity: 0, skipHeight: 0, placed: 0, builds: 0, updates: 0, wanted: 0,
    pending: 0, pendingVisible: 0, building: 0, slots: 0, pooled: 0, suspended: 0,
  };

  constructor(sampler: GrassMacroSampler, heightAt: (x: number, z: number) => number | undefined, options: GrassSystemOptions = {}, maxHeightInRect?: (minX: number, minZ: number, maxX: number, maxZ: number) => number | undefined) {
    this.#sampler = sampler;
    this.#heightAt = heightAt;
    this.#maxHeightInRect = maxHeightInRect;
    const sectorSize = options.sectorSize ?? options.cellSize ?? 32;
    const viewDistance = options.viewDistance ?? 96;
    this.#opts = {
      sectorSize,
      viewDistance,
      density: options.density ?? 5.5,
      maxBuildPerFrame: options.maxBuildPerFrame ?? 2,
      buildBudgetMs: options.buildBudgetMs ?? 1.5,
      distanceDensityFactor: options.distanceDensityFactor ?? 0.5,
      // Keep full density everywhere before the material's existing fade/width compensation.
      // Thinning inside that same envelope avoids a visible sparse band at mid distance.
      distanceDensityStart: options.distanceDensityStart ?? viewDistance * 0.72,
      distanceDensityEnd: options.distanceDensityEnd ?? viewDistance,
      // Curvature is sub-pixel well before the old 0.44× fade envelope; switching to the
      // straight clump at about a quarter of the view distance removes a large share of
      // vertex/triangle load without changing the close-range silhouette.
      geometryLodDistance: options.geometryLodDistance ?? viewDistance * 0.25,
      geometryLodHysteresis: options.geometryLodHysteresis ?? Math.max(2, sectorSize * 0.125),
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
    this.#material = grassMaterial(undefined, { fadeStart: this.#opts.viewDistance * 0.72, fadeEnd: this.#opts.viewDistance });
    this.#scatterTarget = Math.round(sectorSize * sectorSize * this.#opts.density);
    this.#scatterCapacity = cellScatterCapacity(this.#scatterTarget);
    // A different seed family than the positional hashes avoids correlating the prefix order
    // with acceptance/yaw hashes. One shared permutation is enough: all sectors use the same grid.
    this.#scatterOrder = cellScatterOrder(this.#scatterCapacity, 113.17);
  }

  update(px: number, pz: number, py?: number) {
    this.stats.updates++;
    const { sectorSize, viewDistance } = this.#opts;
    const groundY = this.#heightAt(px, pz);
    let verticalDistance = 0;
    if (py !== undefined && groundY !== undefined) {
      let supportY = groundY;
      if (py - groundY > viewDistance * 0.5 && this.#maxHeightInRect) {
        const radius = viewDistance + sectorSize * 1.25;
        supportY = this.#maxHeightInRect(px - radius, pz - radius, px + radius, pz + radius) ?? groundY;
      }
      verticalDistance = py - supportY;
    }
    if (verticalDistance > viewDistance) {
      for (const sector of this.#sectors.values()) this.#releaseSector(sector);
      this.#sectors.clear();
      this.#streamInitialized = false;
      this.stats.wanted = 0;
      this.stats.suspended = 1;
      this.#refreshStats();
      return;
    }
    this.stats.suspended = 0;
    // Streaming membership follows the actual circular grass radius in world space rather than
    // the camera's current sector key. Sector rectangles enter slightly before the fade radius and
    // leave a little beyond it. This avoids the old row-of-cells churn at integer grid boundaries;
    // movement itself, not a 16/32 m key flip, is what trickles individual sectors in and out.
    if (!this.#streamInitialized || Math.hypot(px - this.#streamX, pz - this.#streamZ) >= 1) {
      this.#streamX = px;
      this.#streamZ = pz;
      this.#streamInitialized = true;
      this.#refreshStreaming(px, pz);
    }

    this.#buildBudgeted(px, pz, py);
    this.#updateDistanceLODs(px, pz, py);
    this.#refreshStats();
  }

  /**
   * Refresh the small working set of sector rectangles intersecting the circular grass radius.
   * Entry is prefetched 2 m outside the exact fade radius; exit uses an additional small hysteresis
   * so grazing the boundary does not oscillate a large sector build. Existing sectors inside the
   * exit radius are kept even when they are outside the entry radius (that gap is the hysteresis).
   */
  #refreshStreaming(px: number, pz: number) {
    const { sectorSize, viewDistance } = this.#opts;
    if (viewDistance <= 0) {
      const sx = Math.floor(px / sectorSize), sz = Math.floor(pz / sectorSize);
      const keepKey = `${sx},${sz}`;
      for (const [k, sector] of this.#sectors) {
        if (k !== keepKey) {
          this.#releaseSector(sector);
          this.#sectors.delete(k);
        }
      }
      if (!this.#sectors.has(keepKey)) this.#sectors.set(keepKey, { sx, sz, count: 0 });
      this.stats.wanted = this.#sectors.size;
      return;
    }

    const enterDistance = viewDistance + 2;
    const exitDistance = viewDistance + Math.max(2, sectorSize * 0.125);
    for (const [k, sector] of this.#sectors) {
      if (this.#sectorSurfaceDistance(sector, px, pz) > exitDistance) {
        this.#releaseSector(sector);
        this.#sectors.delete(k);
      }
    }

    // A sector rectangle can only intersect the circle when its index lies inside the circle's
    // index-space x/z extents. One index of padding keeps exact grid-line contacts conservative;
    // those few extra candidates are rejected by the exact rectangle distance below.
    const minSX = Math.floor((px - exitDistance) / sectorSize) - 1;
    const maxSX = Math.floor((px + exitDistance) / sectorSize) + 1;
    const minSZ = Math.floor((pz - exitDistance) / sectorSize) - 1;
    const maxSZ = Math.floor((pz + exitDistance) / sectorSize) + 1;
    for (let sz = minSZ; sz <= maxSZ; sz++) {
      for (let sx = minSX; sx <= maxSX; sx++) {
        const k = `${sx},${sz}`;
        if (this.#sectors.has(k)) continue;
        const sector: Sector = { sx, sz, count: 0 };
        if (this.#sectorSurfaceDistance(sector, px, pz) <= enterDistance) this.#sectors.set(k, sector);
      }
    }
    this.stats.wanted = this.#sectors.size;
  }

  /** Process the nearest incomplete sectors, but never more than buildBudgetMs in one frame. */
  #buildBudgeted(px: number, pz: number, py?: number) {
    const { maxBuildPerFrame, buildBudgetMs } = this.#opts;
    // Readiness (`pendingVisible`) remains strict: the 2 m streaming prefetch is allowed to build
    // early, but QA never has to wait for grass that is still outside the actual fade radius.
    let pendingVisible = 0;
    const pending: Sector[] = [];
    for (const sector of this.#sectors.values()) {
      if (sector.mesh !== undefined) continue;
      if (this.#sectorPotentiallyVisible(sector, px, pz, py)) pendingVisible++;
      if (this.#sectorPotentiallyVisible(sector, px, pz, py, 2)) pending.push(sector);
    }
    this.stats.pendingVisible = pendingVisible;
    if (!pending.length) return;
    const deadline = performance.now() + Math.max(0, buildBudgetMs);
    const processed = new Set<Sector>();
    let completed = 0;
    // Pick active/nearest candidates by a tiny linear selection pass instead of sorting the working
    // set every frame. maxBuildPerFrame is normally two and the sector working set is only ~28, so
    // this is both cheaper than a sort and keeps per-frame CPU work flat/simple.
    while (completed < maxBuildPerFrame) {
      if (completed > 0 && performance.now() >= deadline) break;
      let best: Sector | undefined;
      let bestActive = false;
      let bestDistance = Infinity;
      for (const sector of pending) {
        if (processed.has(sector)) continue;
        const active = !!sector.build;
        const distance = this.#sectorCenterDistance(sector, px, pz);
        if ((active && !bestActive) || (active === bestActive && distance < bestDistance)) {
          best = sector;
          bestActive = active;
          bestDistance = distance;
        }
      }
      if (!best) break;
      processed.add(best);
      if (!this.#buildSlice(best, deadline)) break; // budget exhausted inside the active sector
      completed++;
    }
  }

  /**
   * Advance one sector in small deterministic chunks. Instance data is written directly into the
   * pooled fixed-capacity GPU attributes. Accepted instances form a contiguous prefix; every
   * INSTANCE_UPLOAD_CHUNK instances (and once more for the final remainder) are queued as bounded
   * update ranges. The count-0 build mesh is already scene-visible with frustum culling disabled,
   * so the renderer can consume those chunks in the frames in which they are produced instead of
   * seeing one full-capacity upload when the sector completes.
   */
  #buildSlice(sector: Sector, deadline: number): boolean {
    let job = sector.build;
    if (!job) {
      const x0 = sector.sx * this.#opts.sectorSize, z0 = sector.sz * this.#opts.sectorSize;
      const densityScale = this.#sampler.densityCellMax(x0, z0, x0 + this.#opts.sectorSize, z0 + this.#opts.sectorSize);
      if (densityScale < 0.03) {
        // Whole-sector macro rejection: water/path/rock/sand sectors need neither height queries nor a slot.
        sector.count = 0;
        sector.mesh = null;
        this.stats.builds++;
        return true;
      }
      job = this.#startBuild(sector, densityScale);
    }
    const info = job.slot.aInfo.array as Float32Array;
    const shade = job.slot.aShade.array as Float32Array;
    const tint = job.slot.tint.array as Float32Array;
    let sinceClockCheck = 0;

    while (job.cursor < job.total) {
      if (sinceClockCheck >= 32) {
        this.#flushCompletedUploadChunks(job);
        if (performance.now() >= deadline) return false;
        sinceClockCheck = 0;
      }
      const scatterIndex = this.#scatterOrder[job.orderCursor++];
      if (job.orderCursor >= this.#scatterCapacity) job.orderCursor = 0;
      job.cursor++;
      const pt = cellScatterPositionInto(sector.sx, sector.sz, this.#opts.sectorSize, this.#scatterTarget, 7, scatterIndex, job.point);
      sinceClockCheck++;

      const density = this.#sampler.densityAt(pt.x, pt.z);
      // density mask: stochastic thinning, hard zero on water/paths/rock/sand. The scan itself is
      // importance-sampled by the sector's conservative maximum density; multiplying h1 by that upper
      // bound preserves the mean placement rate while skipping impossible trials wholesale.
      if (density < 0.03 || pt.h1 * job.densityScale > density) { this.stats.skipDensity++; continue; }
      const s = this.#sampler.sampleInto(pt.x, pt.z, job.sample);
      const y = this.#heightAt(pt.x, pt.z);
      if (y === undefined) { this.stats.skipHeight++; continue; }

      const scale = 0.72 + pt.h2 * 0.55;
      const hs = 0.65 + s.heightScale * 0.7;
      job.minY = Math.min(job.minY, y);
      job.maxY = Math.max(job.maxY, y);
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
      tint[i4] = srgbToLinear(s.tintR);
      tint[i4 + 1] = srgbToLinear(s.tintG);
      tint[i4 + 2] = srgbToLinear(s.tintB);
      tint[i4 + 3] = 1;
    }

    this.#finishBuild(sector, job);
    return true;
  }

  #startBuild(sector: Sector, densityScale: number): SectorBuild {
    const slot = this.#acquireSlot();
    // A reused slot can still carry ranges that were never consumed while its previous mesh was
    // outside the scene. The new sector overwrites the whole live prefix, and dead tail data is
    // irrelevant because mesh.count never exceeds the newly placed prefix length.
    for (const attribute of [slot.aInfo, slot.aShade, slot.tint]) attribute.clearUpdateRanges();
    slot.mesh.count = 0;
    slot.mesh.visible = true;
    slot.mesh.geometry = slot.nearGeometry;
    slot.mesh.name = `grass_sector_${sector.sx}_${sector.sz}`;
    // Keep the invisible build mesh in the render traversal. Even though no draw is emitted for
    // count 0, three.js still updates its geometry/binding data for the render object; that is
    // what lets the partial attribute ranges reach the GPU progressively during construction.
    slot.mesh.frustumCulled = false;
    if (slot.mesh.parent !== this.group) this.group.add(slot.mesh);
    const job: SectorBuild = {
      cursor: 0,
      total: Math.max(1, Math.ceil(this.#scatterCapacity * densityScale)),
      orderCursor: Math.floor(hash2(sector.sx, sector.sz, 29.71) * this.#scatterCapacity),
      densityScale,
      placed: 0,
      uploadCursor: 0,
      minY: Infinity,
      maxY: -Infinity,
      slot,
      sample: { density: 0, heightScale: 0, dryMix: 0, canopyShadow: 1, tintR: 0.4, tintG: 0.42, tintB: 0.26, ao: 1 },
      point: { x: 0, z: 0, h1: 0, h2: 0 },
    };
    sector.build = job;
    return job;
  }

  /** Queue all complete fixed-size prefix chunks that have become dirty since the last queued chunk. */
  #flushCompletedUploadChunks(job: SectorBuild) {
    while (job.placed - job.uploadCursor >= INSTANCE_UPLOAD_CHUNK) {
      this.#pushInstanceUpdate(job, INSTANCE_UPLOAD_CHUNK);
    }
  }

  /** Queue one bounded contiguous instance range on all three vec4 instance streams. */
  #pushInstanceUpdate(job: SectorBuild, count: number) {
    if (count <= 0) return;
    const start = job.uploadCursor;
    job.uploadCursor += count;
    for (const attribute of [job.slot.aInfo, job.slot.aShade, job.slot.tint]) {
      attribute.addUpdateRange(start * attribute.itemSize, count * attribute.itemSize);
      attribute.needsUpdate = true;
    }
  }

  #finishBuild(sector: Sector, job: SectorBuild) {
    this.#flushCompletedUploadChunks(job);
    this.#pushInstanceUpdate(job, job.placed - job.uploadCursor);
    sector.build = undefined;
    this.stats.builds++;
    this.stats.placed += job.placed;
    if (!job.placed) {
      sector.count = 0;
      sector.mesh = null;
      this.#releaseSlot(job.slot);
      return;
    }

    const { slot } = job;
    // Only the placed prefix changed, and that prefix was already queued in bounded chunks above.
    // Fixed-capacity slots are reused across sparse and dense sectors, so no full-capacity
    // instance-attribute upload is ever requested here or during streaming reuse.
    slot.mesh.count = job.placed;
    slot.mesh.geometry = slot.nearGeometry;
    slot.mesh.frustumCulled = true;
    // Culling must cover the full instance set, not only the currently applied distance-density
    // prefix. The custom grass shader positions blades from aInfo, so instance matrices are not
    // maintained at all; derive conservative sector bounds directly instead of paying an O(n) matrix pass.
    const y0 = job.minY - 0.1, y1 = job.maxY + 2.0;
    slot.mesh.boundingSphere = new Sphere(
      new Vector3((sector.sx + 0.5) * this.#opts.sectorSize, (y0 + y1) / 2, (sector.sz + 0.5) * this.#opts.sectorSize),
      Math.hypot(this.#opts.sectorSize * Math.SQRT1_2 + 1.5, (y1 - y0) / 2),
    );
    sector.count = job.placed;
    sector.mesh = slot.mesh;
    sector.slot = slot;
    if (slot.mesh.parent !== this.group) this.group.add(slot.mesh);
  }

  /**
   * Apply distance LODs without rebuilding: count prefixes are uniform because of the shuffled
   * scatter order, and geometry switching only selects near/far shared vertex data on the slot.
   * Distances are measured to the nearest point of the sector rectangle (not its centre), so a
   * large sector can never switch to cheap geometry while part of that sector is still close.
   */
  #updateDistanceLODs(px: number, pz: number, py?: number) {
    const threshold = this.#opts.geometryLodDistance;
    const hysteresis = Math.max(0, this.#opts.geometryLodHysteresis);
    const enterFar = threshold + hysteresis;
    const exitFar = Math.max(0, threshold - hysteresis);
    for (const sector of this.#sectors.values()) {
      if (!sector.mesh || !sector.slot || !sector.count) continue;
      if (!this.#sectorPotentiallyVisible(sector, px, pz, py)) {
        sector.mesh.count = 0;
        sector.mesh.visible = false;
        continue;
      }
      const distance = this.#sectorSurfaceDistance(sector, px, pz);
      // Conservative hysteresis: an unknown/near sector must be clearly beyond the threshold before
      // it uses the cheap geometry; once far, it must come clearly back inside before restoring curves.
      const useFar = sector.farLod ? distance >= exitFar : distance >= enterFar;
      sector.farLod = useFar;
      const geometry = useFar ? sector.slot.farGeometry : sector.slot.nearGeometry;
      if (sector.mesh.geometry !== geometry) sector.mesh.geometry = geometry;
      // Geometry quality is conservative per sector surface. The density prefix keeps the cheaper
      // centre-distance LOD for the sector interior; using the nearest surface for the whole curve
      // would pin large sectors to dense prefixes long before the fade envelope. Centres can,
      // however, lie up to 22 m outside a 32 m sector that still clips the view circle. Never cull
      // such a clipping sector completely: retain the same far prefix that the normal LOD reaches
      // at fadeEnd and let the shader fade its individual instances exactly by world position.
      const centerCount = this.#visibleCount(sector.count, this.#sectorCenterDistance(sector, px, pz));
      const edgeFactor = Math.min(1, Math.max(0, this.#opts.distanceDensityFactor));
      const visibleCount = centerCount === 0 && distance < this.#opts.distanceDensityEnd
        ? Math.max(1, Math.round(sector.count * edgeFactor))
        : centerCount;
      sector.mesh.count = visibleCount;
      // A zero-count InstancedMesh still costs a render-object/binding update in three.js even
      // though backend.draw() later skips the draw call. Sectors beyond fadeEnd cannot produce
      // a single pixel, so remove them from traversal entirely until the prefix becomes visible.
      sector.mesh.visible = visibleCount > 0;
    }
  }

  #sectorPotentiallyVisible(sector: Sector, px: number, pz: number, py?: number, rangeMargin = 0) {
    const horizontal = this.#sectorSurfaceDistance(sector, px, pz);
    const range = this.#opts.viewDistance + rangeMargin;
    if (horizontal > range) return false;
    if (py === undefined || !this.#maxHeightInRect) return true;
    if (sector.maxY === undefined) {
      const x0 = sector.sx * this.#opts.sectorSize, z0 = sector.sz * this.#opts.sectorSize;
      sector.maxY = this.#maxHeightInRect(x0, z0, x0 + this.#opts.sectorSize, z0 + this.#opts.sectorSize) ?? null;
    }
    if (sector.maxY === null) return true;
    const vertical = Math.max(0, py - (sector.maxY + 1.5));
    return Math.hypot(horizontal, vertical) <= range;
  }

  #visibleCount(count: number, distance: number): number {
    if (count <= 1) return count;
    const start = this.#opts.distanceDensityStart;
    const end = Math.max(start + 0.001, this.#opts.distanceDensityEnd);
    const factor = Math.min(1, Math.max(0, this.#opts.distanceDensityFactor));
    if (distance <= start) return count;
    // At fadeEnd the shader scales blades to exactly zero; drawing a retained far prefix beyond
    // that radius is pure vertex cost with no possible pixel output.
    if (distance >= end) return 0;
    const farCount = Math.max(1, Math.round(count * factor));
    const t = Math.min(1, Math.max(0, (distance - start) / (end - start)));
    const smooth = t * t * (3 - 2 * t);
    const fraction = 1 - (1 - factor) * smooth;
    return Math.max(farCount, Math.min(count, Math.round(count * fraction)));
  }

  #sectorCenterDistance(sector: Sector, px: number, pz: number) {
    return Math.hypot((sector.sx + 0.5) * this.#opts.sectorSize - px, (sector.sz + 0.5) * this.#opts.sectorSize - pz);
  }

  /** Exact horizontal distance to the nearest point of the sector rectangle (0 when inside). */
  #sectorSurfaceDistance(sector: Sector, px: number, pz: number) {
    const x0 = sector.sx * this.#opts.sectorSize, z0 = sector.sz * this.#opts.sectorSize;
    const x1 = x0 + this.#opts.sectorSize, z1 = z0 + this.#opts.sectorSize;
    const dx = px < x0 ? x0 - px : px > x1 ? px - x1 : 0;
    const dz = pz < z0 ? z0 - pz : pz > z1 ? pz - z1 : 0;
    return Math.hypot(dx, dz);
  }

  #acquireSlot(): SectorSlot {
    const slot = this.#freeSlots.pop() ?? this.#createSlot();
    slot.free = false;
    return slot;
  }

  #releaseSector(sector: Sector) {
    const slot = sector.build?.slot ?? sector.slot;
    if (slot) this.#releaseSlot(slot);
    sector.build = undefined;
    sector.slot = undefined;
    sector.mesh = undefined;
    sector.count = 0;
    sector.farLod = undefined;
  }

  #releaseSlot(slot: SectorSlot) {
    if (slot.free) return;
    if (slot.mesh.parent === this.group) this.group.remove(slot.mesh);
    slot.mesh.count = 0;
    slot.mesh.frustumCulled = true;
    slot.free = true;
    this.#freeSlots.push(slot);
  }

  #createSlot(): SectorSlot {
    const capacity = this.#scatterCapacity;
    const aInfo = new InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    const aShade = new InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    const tint = new InstancedBufferAttribute(new Float32Array(capacity * 4), 4);
    const nearGeometry = this.#instanceGeometry(this.#base.near, aInfo, aShade, tint);
    const farGeometry = this.#instanceGeometry(this.#base.far, aInfo, aShade, tint);
    // Resolve aInfo/aShade by geometry attribute name rather than baking the per-slot attribute
    // objects into the TSL node graph. BufferAttributeNode hashes object identity, which would give
    // every pooled slot its own shader/pipeline cache key; geometry attributes keep the same step
    // mode while allowing identical grass programs to be shared across slots.
    // Constructing with count 0 avoids InstancedMesh's otherwise mandatory identity-matrix
    // initialisation pass. The shader never consumes instanceMatrix, but three.js expects the
    // attribute object to exist on InstancedMesh; keep only a one-instance dummy rather than
    // allocating/uploading a dead full-capacity matrix buffer for every pooled slot.
    const mesh = new InstancedMesh(nearGeometry, this.#material, 0);
    mesh.instanceMatrix = new InstancedBufferAttribute(new Float32Array(16), 16);
    mesh.count = 0;
    mesh.castShadow = false;
    mesh.receiveShadow = true;
    mesh.frustumCulled = true;
    mesh.name = "grass_sector_slot";
    const slot: SectorSlot = { nearGeometry, farGeometry, mesh, aInfo, aShade, tint, free: true };
    this.#slots.push(slot);
    return slot;
  }

  #instanceGeometry(base: BufferGeometry, aInfo: InstancedBufferAttribute, aShade: InstancedBufferAttribute, tint: InstancedBufferAttribute) {
    const geometry = new BufferGeometry();
    geometry.index = base.index;
    for (const name of ["position", "uv", "color", "normal"] as const) {
      const attr = base.getAttribute(name);
      if (attr) geometry.setAttribute(name, attr);
    }
    geometry.setAttribute("aInfo", aInfo);
    geometry.setAttribute("aShade", aShade);
    geometry.setAttribute("aTint", tint);
    return geometry;
  }

  #refreshStats() {
    let sectors = 0, instances = 0, visibleInstances = 0, triangles = 0, pending = 0, building = 0;
    for (const sector of this.#sectors.values()) {
      if (sector.mesh === undefined) {
        pending++;
        if (sector.build) building++;
      } else if (sector.mesh && sector.count > 0) {
        sectors++;
        instances += sector.count;
        visibleInstances += sector.mesh.count;
        triangles += sector.mesh.count * (sector.mesh.geometry === sector.slot?.farGeometry ? this.#farTriangles : this.#nearTriangles);
      }
    }
    this.stats.cells = sectors;
    this.stats.sectors = sectors;
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
    for (const sector of this.#sectors.values()) this.#releaseSector(sector);
    this.#sectors.clear();
    for (const slot of this.#slots) {
      slot.mesh.dispose();
      slot.nearGeometry.dispose();
      slot.farGeometry.dispose();
    }
    this.#material.dispose();
    this.#slots = [];
    this.#freeSlots = [];
    this.#streamInitialized = false;
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
