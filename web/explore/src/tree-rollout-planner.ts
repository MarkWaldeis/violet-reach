import { expandPlacements, type GroundSample, type Placement, type ScatterPlacement } from "./placements.ts";
import { placementWaterAt, segmentSample, type Hydrology } from "./hydrology.ts";
import { scatterSurface } from "./scatter-surface.ts";
import type { Bounds, Slice } from "./slice.ts";

export type TreeSpecies = "oak" | "beech" | "ancient" | "willow";

export const TREE_ASSETS: Readonly<Record<TreeSpecies, string>> = {
  oak: "tree_oak_a",
  beech: "tree_beech_a",
  ancient: "tree_ancient_a",
  willow: "tree_willow_a",
};

export const TREE_SCALE_RANGES: Readonly<Record<TreeSpecies, readonly [number, number]>> = {
  oak: [0.95, 1.25],
  beech: [0.95, 1.25],
  ancient: [1.0, 1.1],
  willow: [0.9, 1.15],
};

export const BROADLEAF_ASSETS = new Set(["tree_broadleaf_a", "tree_broadleaf_b", "tree_broadleaf_c"]);
export const FANTASY_TREE_ASSETS = new Set(Object.values(TREE_ASSETS));
export const ROLLOUT_TREE_ASSETS = new Set([...BROADLEAF_ASSETS, ...FANTASY_TREE_ASSETS]);

export const DEFAULT_TARGET_COUNTS: Readonly<Record<TreeSpecies, number>> = {
  oak: 144,
  beech: 108,
  ancient: 54,
  willow: 54,
};

// The pilot positions stay fixed, but the species assignment is the rollout assignment.
// In particular 24157 and 24158 are intentionally swapped relative to the first pilot,
// and the two unsuitable pilot willows 24145/24146 are deliberately not fixed.
export const DEFAULT_FIXED_PILOT: Readonly<Record<number, TreeSpecies>> = {
  24144: "oak",
  24148: "oak",
  24149: "oak",
  24157: "ancient",
  24147: "beech",
  24154: "beech",
  24158: "oak",
};

export const WILLOW_RULE = "waterDistance <= 30 || (waterDistance <= 55 && heightAboveWater <= 20)";
export const DEFAULT_CLUSTER_LINK_DISTANCE = 15;
export const DEFAULT_CORRIDOR_BIN_SIZE = 160;
export const DEFAULT_ANCIENT_SPACING_STEPS = [45, 40, 35, 30] as const;
export const DEFAULT_MINIMUM_ANCIENT_SPACING = 30;

const CARDINAL_WEIGHT = 1_000_000;
const ANCIENT_HASH_TIE_RANGE = 300;
const EPSILON = 1e-9;

export function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function stableHash(seed: number | string, purpose: string): number {
  const seedHash = typeof seed === "number" ? seed >>> 0 : hashString(seed);
  let x = (seedHash ^ hashString(purpose) ^ 0x9e3779b9) >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x21f0aaad) >>> 0;
  x = Math.imul(x ^ (x >>> 15), 0x735a2d97) >>> 0;
  return (x ^ (x >>> 15)) >>> 0;
}

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const distance2d = (a: { x: number; z: number }, b: { x: number; z: number }) => Math.hypot(a.x - b.x, a.z - b.z);
const compareNumbers = (a: number, b: number) => a < b ? -1 : a > b ? 1 : 0;
const compareStrings = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

export interface SightAxis {
  id: string;
  x: number;
  z: number;
  yaw: number;
  length: number;
  width: number;
}

/** Horizontal distance to a finite forward view ray using the navigation yaw convention. */
export function sightAxisDistance(axis: SightAxis, x: number, z: number) {
  const forwardX = -Math.sin(axis.yaw), forwardZ = -Math.cos(axis.yaw);
  const dx = x - axis.x, dz = z - axis.z;
  const along = clamp(dx * forwardX + dz * forwardZ, 0, axis.length);
  return { distance: Math.hypot(dx - along * forwardX, dz - along * forwardZ), along };
}

/** Adds deterministic central-view-axis flags without mutating the input samples. */
export function withSightAxisFlags<T extends { x: number; z: number; nearCentralAxis?: boolean }>(positions: readonly T[], axes: readonly SightAxis[]): T[] {
  return positions.map((position) => {
    if (position.nearCentralAxis) return position;
    const hit = axes.some((axis) => sightAxisDistance(axis, position.x, position.z).distance <= axis.width);
    return hit ? { ...position, nearCentralAxis: true } as T : position;
  });
}

export interface DetailedWaterSample {
  distance: number;
  height: number;
  lakeDistance: number;
  kind: "lake" | "river" | "none";
  feature: string;
  segmentIndex: number;
  segmentT: number;
  chainage: number;
  corridorId: string;
}

interface RiverGeometry {
  name: string;
  cumulative: number[];
  lengths: number[];
  polyline: [number, number, number, number][];
}

interface LakeGeometry {
  name: string;
  water_y: number;
  outline: [number, number][];
  cumulative: number[];
  lengths: number[];
  perimeter: number;
}

/**
 * Exact placement-hydrology sample plus deterministic provenance metadata.
 * The distance/height calculation deliberately mirrors waterSample()/polygonDistance()
 * operation for operation; the metadata only identifies which water feature won.
 */
export function createDetailedWaterSampler(hydrology: Hydrology, corridorBinSize = DEFAULT_CORRIDOR_BIN_SIZE) {
  if (!Number.isFinite(corridorBinSize) || corridorBinSize <= 0) throw new Error("corridorBinSize muss positiv sein");
  const lakes: LakeGeometry[] = hydrology.lakes.map((lake) => {
    const cumulative: number[] = [];
    const lengths: number[] = [];
    let perimeter = 0;
    for (let i = 0; i < lake.outline.length; i++) {
      const a = lake.outline[i], b = lake.outline[(i + 1) % lake.outline.length];
      const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      cumulative.push(perimeter);
      lengths.push(length);
      perimeter += length;
    }
    return { ...lake, cumulative, lengths, perimeter };
  });
  const rivers: RiverGeometry[] = hydrology.rivers.map((river) => {
    const cumulative = [0];
    const lengths: number[] = [];
    for (let i = 1; i < river.polyline.length; i++) {
      const a = river.polyline[i - 1], b = river.polyline[i];
      const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      lengths.push(length);
      cumulative.push(cumulative[cumulative.length - 1] + length);
    }
    return { ...river, cumulative, lengths };
  });

  return (x: number, z: number): DetailedWaterSample => {
    let distance = Infinity, height = 0, lakeDistance = Infinity;
    let kind: DetailedWaterSample["kind"] = "none";
    let feature = "none", segmentIndex = -1, segmentT = 0, chainage = 0;

    for (const lake of lakes) {
      // Same signed-distance traversal as polygonDistance(): edge a is vertex i,
      // edge b is the previous vertex.  For chainage we convert back to the
      // conventional previous -> current orientation.
      let inside = false, shoreDistance = Infinity;
      let bestEdge = -1, bestT = 0;
      for (let i = 0, j = lake.outline.length - 1; i < lake.outline.length; j = i++) {
        const a = lake.outline[i], b = lake.outline[j];
        if ((a[1] > z) !== (b[1] > z) && x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
        const sample = segmentSample(x, z, a, b);
        if (sample.distance < shoreDistance) {
          shoreDistance = sample.distance;
          bestEdge = i;
          bestT = sample.t;
        }
      }
      const signed = inside ? -shoreDistance : shoreDistance;
      lakeDistance = Math.min(lakeDistance, signed);
      const d = signed + 3;
      if (d < distance) {
        distance = d;
        height = lake.water_y;
        kind = "lake";
        feature = lake.name;
        segmentIndex = bestEdge;
        segmentT = bestT;
        if (bestEdge >= 0) {
          const previous = (bestEdge + lake.outline.length - 1) % lake.outline.length;
          const edgeLength = lake.lengths[previous];
          const alongForwardEdge = (1 - bestT) * edgeLength;
          chainage = (lake.cumulative[previous] + alongForwardEdge) % Math.max(lake.perimeter, EPSILON);
        }
      }
    }

    for (const river of rivers) {
      for (let i = 1; i < river.polyline.length; i++) {
        const a = river.polyline[i - 1], b = river.polyline[i];
        const sample = segmentSample(x, z, a, b);
        const d = sample.distance - (a[3] + sample.t * (b[3] - a[3])) / 2;
        if (d < distance) {
          distance = d;
          height = a[2] + sample.t * (b[2] - a[2]);
          kind = "river";
          feature = river.name;
          segmentIndex = i - 1;
          segmentT = sample.t;
          chainage = river.cumulative[i - 1] + sample.t * river.lengths[i - 1];
        }
      }
    }

    const corridorId = kind === "none" ? "none" : `${kind}:${feature}:${Math.max(0, Math.floor(chainage / corridorBinSize))}`;
    return { distance, height, lakeDistance, kind, feature, segmentIndex, segmentT, chainage, corridorId };
  };
}

export interface TreeRolloutPositionInput {
  seed: number;
  x: number;
  z: number;
  waterDistance: number;
  heightAboveWater: number;
  placementIndex?: number;
  asset?: string;
  yaw?: number;
  y?: number;
  waterHeight?: number;
  waterFeature?: string;
  waterKind?: "lake" | "river" | "none";
  corridorId?: string;
  clusterId?: string;
  landmarkDistance?: number;
  inMonumentCore?: boolean;
  nearCentralAxis?: boolean;
  currentScaleRange?: readonly [number, number];
}

export interface TreePositionSample extends TreeRolloutPositionInput {
  placementIndex: number;
  asset: string;
  yaw: number;
  y: number;
  waterHeight: number;
  waterFeature: string;
  waterKind: "lake" | "river" | "none";
  corridorId: string;
  waterChainage: number;
  waterSegmentIndex: number;
  groundHeight: number;
  slope: number;
  landmarkDistance: number;
  inMonumentCore: boolean;
  nearCentralAxis: boolean;
}

export const MONUMENT_CORE_RADII: Readonly<Record<string, number>> = {
  gate_white_a: 24,
  column_white_a: 18,
  crystal_spire_a: 22,
  bridge_arch_a: 24,
  stair_terrace_a: 26,
  arch_sandstone_a: 20,
};

function pathClearanceDistance(paths: NonNullable<Slice["paths"]>, x: number, z: number) {
  let distance = Infinity;
  for (const path of paths) {
    for (let i = 1; i < path.polyline.length; i++) {
      const sample = segmentSample(x, z, path.polyline[i - 1], path.polyline[i]);
      distance = Math.min(distance, sample.distance - path.width / 2);
    }
  }
  return distance;
}

/** Exact offline equivalent of the ground sampler in slice-content.ts. */
export function createPlacementGroundAt(fullHeightAt: (x: number, z: number) => number | undefined) {
  return (x: number, z: number): GroundSample | undefined => {
    const height = fullHeightAt(x, z);
    if (height === undefined) return undefined;
    const dx = ((fullHeightAt(x + 2, z) ?? height) - (fullHeightAt(x - 2, z) ?? height)) / 4;
    const dz = ((fullHeightAt(x, z + 2) ?? height) - (fullHeightAt(x, z - 2) ?? height)) / 4;
    const length = Math.hypot(dx, 1, dz);
    return { height, slope: Math.atan(Math.hypot(dx, dz)) * 180 / Math.PI, normal: [-dx / length, 1 / length, -dz / length] };
  };
}

/** Exact offline equivalent of the runtime scatter-surface acceptance callback. */
export function createRuntimeScatterAcceptance(
  fullHeightAt: (x: number, z: number) => number | undefined,
  paths: Slice["paths"] = [],
) {
  return (entry: ScatterPlacement, ground: GroundSample, x: number, z: number, aboveWater: number) => {
    if (!entry.scatter.surface) return true;
    const height = (dx: number, dz: number) => fullHeightAt(x + dx, z + dz) ?? ground.height;
    const dx = (height(8, 0) - height(-8, 0)) / 16, dz = (height(0, 8) - height(0, -8)) / 16;
    const length = Math.hypot(dx, 1, dz), hollow = (height(16, 0) + height(-16, 0) + height(0, 16) + height(0, -16)) / 4 - ground.height;
    return scatterSurface(entry.scatter.surface, x, z, [-dx / length, 1 / length, -dz / length], aboveWater, paths ?? [], entry.scatter.path_clearance, hollow);
  };
}

/**
 * Expands the current one-instance tree placements with the same deterministic RNG,
 * terrain interpolation, water reference, surface filter and path clearance as the game.
 * The planner never writes these positions back; they are only the read-only rollout basis.
 */
export function sampleTreeRolloutPositions(
  placements: Placement[],
  hydrology: Hydrology,
  fullHeightAt: (x: number, z: number) => number | undefined,
  paths: Slice["paths"] = [],
  bounds?: Bounds,
  corridorBinSize = DEFAULT_CORRIDOR_BIN_SIZE,
): TreePositionSample[] {
  const waterAt = placementWaterAt(hydrology);
  const detailedWaterAt = createDetailedWaterSampler(hydrology, corridorBinSize);
  const groundAt = createPlacementGroundAt(fullHeightAt);
  const acceptScatter = createRuntimeScatterAcceptance(fullHeightAt, paths);
  const acceptPosition = (x: number, z: number) => !bounds || (x >= bounds.minX && x <= bounds.maxX && z >= bounds.minZ && z <= bounds.maxZ);
  const monuments = placements.flatMap((entry) => {
    if ("scatter" in entry) return [];
    const radius = MONUMENT_CORE_RADII[entry.asset];
    return radius === undefined ? [] : [{ x: entry.x, z: entry.z, radius, asset: entry.asset }];
  });
  const samples: TreePositionSample[] = [];

  placements.forEach((entry, placementIndex) => {
    if (!("scatter" in entry) || !ROLLOUT_TREE_ASSETS.has(entry.asset)) return;
    if (entry.scatter.count !== 1) throw new Error(`Tree rollout expects count=1 per tree seed; seed ${entry.scatter.seed} has count ${entry.scatter.count}`);
    const instances = expandPlacements([entry], groundAt, waterAt, acceptPosition, acceptScatter);
    if (instances.length !== 1) throw new Error(`Tree seed ${entry.scatter.seed}: expected one expanded position, got ${instances.length}`);
    const instance = instances[0];
    const ground = groundAt(instance.x, instance.z);
    if (!ground) throw new Error(`Tree seed ${entry.scatter.seed}: missing expanded ground sample`);
    const water = detailedWaterAt(instance.x, instance.z);
    let landmarkDistance = Infinity;
    let inMonumentCore = false;
    for (const monument of monuments) {
      const d = Math.hypot(instance.x - monument.x, instance.z - monument.z);
      landmarkDistance = Math.min(landmarkDistance, d);
      if (d <= monument.radius) inMonumentCore = true;
    }
    samples.push({
      seed: entry.scatter.seed,
      placementIndex,
      asset: entry.asset,
      x: instance.x,
      z: instance.z,
      yaw: instance.yaw,
      y: instance.y,
      groundHeight: ground.height,
      slope: ground.slope,
      waterDistance: water.distance,
      waterHeight: water.height,
      heightAboveWater: ground.height - water.height,
      waterFeature: water.feature,
      waterKind: water.kind,
      waterChainage: water.chainage,
      waterSegmentIndex: water.segmentIndex,
      corridorId: water.corridorId,
      landmarkDistance,
      inMonumentCore,
      nearCentralAxis: pathClearanceDistance(paths ?? [], instance.x, instance.z) <= 10,
      currentScaleRange: [entry.scatter.scale[0], entry.scatter.scale[1]],
    });
  });
  return samples.sort((a, b) => a.seed - b.seed);
}

interface PreparedPosition {
  input: TreeRolloutPositionInput;
  seed: number;
  x: number;
  z: number;
  placementIndex: number;
  asset: string;
  waterDistance: number;
  heightAboveWater: number;
  waterHeight: number;
  corridorId: string;
  waterFeature: string;
  clusterId: string;
  clusterSize: number;
  clusterEdgeRatio: number;
  nearestTreeDistance: number;
  localDensity: number;
  landmarkDistance: number;
  inMonumentCore: boolean;
  nearCentralAxis: boolean;
  ancientPreference: number;
  ancientStructuralScore: number;
}

interface AssignmentInfo {
  species: TreeSpecies;
  stage: "fixed" | "willow" | "ancient" | "oak-beech";
  fixed: boolean;
}

export interface TreeRolloutOptions {
  targetCounts?: Partial<Record<TreeSpecies, number>>;
  fixedAssignments?: Readonly<Record<number, TreeSpecies>>;
  clusterLinkDistance?: number;
  ancientSpacingSteps?: readonly number[];
  minimumAncientSpacing?: number;
}

interface AllocationItem {
  key: string;
  weight: number;
  min: number;
  max: number;
  ideal?: number;
}

function allocateProportional(items: AllocationItem[], total: number, purpose: string) {
  if (!Number.isSafeInteger(total) || total < 0) throw new Error(`allocation total for ${purpose} must be a non-negative integer`);
  const normalized = items.map((item) => ({
    ...item,
    weight: Math.max(0, item.weight),
    min: Math.max(0, Math.floor(item.min)),
    max: Math.max(0, Math.floor(item.max)),
  }));
  if (normalized.some((item) => item.min > item.max)) throw new Error(`allocation min/max conflict for ${purpose}`);
  let minimaWereDropped = false;
  let minimumSum = normalized.reduce((sum, item) => sum + item.min, 0);
  if (minimumSum > total) {
    // Hard minima cannot be represented when the total itself is smaller.  The
    // rollout treats them as a best-effort soft constraint in that degenerate case.
    for (const item of normalized) item.min = 0;
    minimumSum = 0;
    minimaWereDropped = true;
  }
  const maximumSum = normalized.reduce((sum, item) => sum + item.max, 0);
  if (total > maximumSum) throw new Error(`allocation capacity exhausted for ${purpose}: ${total} > ${maximumSum}`);
  const allocation = new Map<string, number>();
  const positiveWeightSum = normalized.reduce((sum, item) => sum + item.weight, 0);
  const weightSum = positiveWeightSum || normalized.length;
  const ideals = new Map<string, number>();
  let assigned = 0;
  for (const item of normalized) {
    allocation.set(item.key, item.min);
    assigned += item.min;
    const weight = item.weight > 0 ? item.weight : positiveWeightSum === 0 ? 1 : 0;
    ideals.set(item.key, item.ideal ?? total * weight / weightSum);
  }
  while (assigned < total) {
    let best: typeof normalized[number] | undefined;
    let bestDeficit = -Infinity;
    let bestTie = Infinity;
    for (const item of normalized) {
      const current = allocation.get(item.key)!;
      if (current >= item.max) continue;
      const deficit = (ideals.get(item.key) ?? 0) - current;
      const tie = stableHash(item.key, purpose);
      if (deficit > bestDeficit + EPSILON || (Math.abs(deficit - bestDeficit) <= EPSILON && tie < bestTie)) {
        best = item;
        bestDeficit = deficit;
        bestTie = tie;
      }
    }
    if (!best) throw new Error(`allocation stalled for ${purpose}`);
    allocation.set(best.key, allocation.get(best.key)! + 1);
    assigned++;
  }
  return { allocation, minimaWereDropped };
}

function preparePositions(positions: TreeRolloutPositionInput[], linkDistance: number): PreparedPosition[] {
  if (!Number.isFinite(linkDistance) || linkDistance <= 0) throw new Error("clusterLinkDistance muss positiv sein");
  const sorted = [...positions].sort((a, b) => a.seed - b.seed);
  const seeds = new Set<number>();
  for (const position of sorted) {
    if (!Number.isSafeInteger(position.seed)) throw new Error(`invalid tree seed ${position.seed}`);
    if (seeds.has(position.seed)) throw new Error(`duplicate tree seed ${position.seed}`);
    seeds.add(position.seed);
    for (const [name, value] of [["x", position.x], ["z", position.z], ["waterDistance", position.waterDistance], ["heightAboveWater", position.heightAboveWater]] as const) {
      if (!Number.isFinite(value)) throw new Error(`tree seed ${position.seed}: ${name} must be finite`);
    }
  }

  const parent = sorted.map((_, index) => index);
  const find = (index: number): number => {
    while (parent[index] !== index) {
      parent[index] = parent[parent[index]];
      index = parent[index];
    }
    return index;
  };
  const union = (a: number, b: number) => {
    const ra = find(a), rb = find(b);
    if (ra !== rb) parent[rb] = ra;
  };
  for (let i = 0; i < sorted.length; i++) {
    for (let j = 0; j < i; j++) {
      if (distance2d(sorted[i], sorted[j]) <= linkDistance + EPSILON) union(i, j);
    }
  }
  const components = new Map<number, number[]>();
  sorted.forEach((_, index) => {
    const root = find(index);
    if (!components.has(root)) components.set(root, []);
    components.get(root)!.push(index);
  });
  const clusterByIndex = new Map<number, { id: string; size: number; centreX: number; centreZ: number; radius: number }>();
  for (const component of components.values()) {
    const minSeed = Math.min(...component.map((index) => sorted[index].seed));
    const centreX = component.reduce((sum, index) => sum + sorted[index].x, 0) / component.length;
    const centreZ = component.reduce((sum, index) => sum + sorted[index].z, 0) / component.length;
    const radius = Math.max(...component.map((index) => Math.hypot(sorted[index].x - centreX, sorted[index].z - centreZ)), EPSILON);
    const id = `cluster-${minSeed}`;
    for (const index of component) clusterByIndex.set(index, { id, size: component.length, centreX, centreZ, radius });
  }

  return sorted.map((input, index) => {
    const cluster = clusterByIndex.get(index)!;
    let nearestTreeDistance = Infinity;
    let localDensity = 0;
    sorted.forEach((other, otherIndex) => {
      if (otherIndex === index) return;
      const d = distance2d(input, other);
      nearestTreeDistance = Math.min(nearestTreeDistance, d);
      if (d <= linkDistance + EPSILON) localDensity++;
    });
    if (!Number.isFinite(nearestTreeDistance)) nearestTreeDistance = 0;
    const centreDistance = Math.hypot(input.x - cluster.centreX, input.z - cluster.centreZ);
    const clusterEdgeRatio = cluster.size === 1 ? 1 : clamp(centreDistance / cluster.radius, 0, 1);
    const base: Omit<PreparedPosition, "ancientPreference" | "ancientStructuralScore"> = {
      input,
      seed: input.seed,
      x: input.x,
      z: input.z,
      placementIndex: input.placementIndex ?? -1,
      asset: input.asset ?? "unknown",
      waterDistance: input.waterDistance,
      heightAboveWater: input.heightAboveWater,
      waterHeight: input.waterHeight ?? NaN,
      corridorId: input.corridorId ?? "unknown",
      waterFeature: input.waterFeature ?? "unknown",
      clusterId: input.clusterId ?? cluster.id,
      clusterSize: cluster.size,
      clusterEdgeRatio,
      nearestTreeDistance,
      localDensity,
      landmarkDistance: input.landmarkDistance ?? Infinity,
      inMonumentCore: input.inMonumentCore ?? false,
      nearCentralAxis: input.nearCentralAxis ?? false,
    };
    const ancientStructuralScore = ancientStructuralScoreFor(base);
    return {
      ...base,
      ancientStructuralScore,
      ancientPreference: ancientStructuralScore + stableHash(input.seed, "ancient-tie-break") % ANCIENT_HASH_TIE_RANGE,
    };
  });
}

function ancientStructuralScoreFor(position: Omit<PreparedPosition, "ancientPreference" | "ancientStructuralScore">) {
  let score = 0;
  if (position.clusterSize === 1) score += 160;
  score += Math.round(110 * clamp(position.clusterEdgeRatio, 0, 1));
  score += Math.round(Math.min(120, position.nearestTreeDistance * 2));
  score += Math.max(0, 80 - position.localDensity * 8);
  if (Number.isFinite(position.landmarkDistance)) {
    const d = position.landmarkDistance;
    if (d >= 25 && d <= 90) score += Math.round(80 * (1 - Math.abs(d - 55) / 35));
    else if (d < 25) score += 15;
    else score += 8;
  }
  if (position.inMonumentCore) score -= 360;
  if (position.nearCentralAxis) score -= 140;
  return clamp(Math.round(score), 0, 620);
}

interface WeightedSolution {
  weight: number;
  mask: bigint;
  count: number;
}

function bit(index: number) {
  return 1n << BigInt(index);
}

function popcount(mask: bigint) {
  let count = 0;
  while (mask) {
    mask &= mask - 1n;
    count++;
  }
  return count;
}

interface AncientSpacingEvaluation {
  spacing: number;
  selected: PreparedPosition[];
  maxCount: number;
  solverStates: number;
  excludedByFixedAncient: number;
}

function solveWeightedComponent(
  nodes: PreparedPosition[],
  conflicts: (a: PreparedPosition, b: PreparedPosition) => boolean,
  weights: Map<number, number>,
) {
  const n = nodes.length;
  const adjacency = Array.from({ length: n }, () => 0n);
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < i; j++) {
      if (conflicts(nodes[i], nodes[j])) {
        adjacency[i] |= bit(j);
        adjacency[j] |= bit(i);
      }
    }
  }
  const weightAt = nodes.map((node) => weights.get(node.seed)!);
  const memo = new Map<bigint, WeightedSolution>();
  let states = 0;

  const empty = { weight: 0, mask: 0n, count: 0 };
  const solve = (mask: bigint): WeightedSolution => {
    if (mask === 0n) return empty;
    const cached = memo.get(mask);
    if (cached) return cached;
    states++;
    const count = popcount(mask);
    if (count === 1) {
      let chosen = 0;
      for (let i = 0; i < n; i++) if ((mask & bit(i)) !== 0n) chosen = i;
      const result = { weight: weightAt[chosen], mask, count: 1 };
      memo.set(mask, result);
      return result;
    }

    let chosen = -1, chosenDegree = -1, chosenWeight = -1;
    for (let i = 0; i < n; i++) {
      const currentBit = bit(i);
      if ((mask & currentBit) === 0n) continue;
      const degree = popcount(adjacency[i] & mask);
      if (degree > chosenDegree || (degree === chosenDegree && weightAt[i] > chosenWeight)) {
        chosen = i;
        chosenDegree = degree;
        chosenWeight = weightAt[i];
      }
    }
    if (chosenDegree === 0) {
      let weight = 0;
      for (let i = 0; i < n; i++) if ((mask & bit(i)) !== 0n) weight += weightAt[i];
      const result = { weight, mask, count };
      memo.set(mask, result);
      return result;
    }

    const chosenBit = bit(chosen);
    const without = solve(mask & ~chosenBit);
    const withRest = solve(mask & ~(chosenBit | adjacency[chosen]));
    const withChosen = {
      weight: withRest.weight + weightAt[chosen],
      mask: withRest.mask | chosenBit,
      count: withRest.count + 1,
    };
    let result: WeightedSolution;
    if (withChosen.weight !== without.weight) result = withChosen.weight > without.weight ? withChosen : without;
    else if (withChosen.count !== without.count) result = withChosen.count > without.count ? withChosen : without;
    else result = withChosen.mask < without.mask ? withChosen : without;
    memo.set(mask, result);
    return result;
  };

  const solution = solve((1n << BigInt(n)) - 1n);
  const selected: PreparedPosition[] = [];
  for (let i = 0; i < n; i++) if ((solution.mask & bit(i)) !== 0n) selected.push(nodes[i]);
  return { selected, maxCount: solution.count, weight: solution.weight, states };
}

function evaluateAncientSpacing(
  candidates: PreparedPosition[],
  fixedAncients: PreparedPosition[],
  spacing: number,
  weights: Map<number, number>,
): AncientSpacingEvaluation {
  const usable = candidates.filter((candidate) => fixedAncients.every((fixed) => distance2d(candidate, fixed) >= spacing - EPSILON));
  const excludedByFixedAncient = candidates.length - usable.length;
  const conflicts = (a: PreparedPosition, b: PreparedPosition) => distance2d(a, b) < spacing - EPSILON;

  const parent = usable.map((_, index) => index);
  const find = (index: number): number => {
    while (parent[index] !== index) {
      parent[index] = parent[parent[index]];
      index = parent[index];
    }
    return index;
  };
  const union = (a: number, b: number) => {
    const ra = find(a), rb = find(b);
    if (ra !== rb) parent[rb] = ra;
  };
  for (let i = 0; i < usable.length; i++) {
    for (let j = 0; j < i; j++) if (conflicts(usable[i], usable[j])) union(i, j);
  }
  const components = new Map<number, PreparedPosition[]>();
  usable.forEach((position, index) => {
    const root = find(index);
    if (!components.has(root)) components.set(root, []);
    components.get(root)!.push(position);
  });

  const selected: PreparedPosition[] = [];
  let solverStates = 0, maxCount = 0;
  for (const component of components.values()) {
    const result = solveWeightedComponent(component, conflicts, weights);
    selected.push(...result.selected);
    solverStates += result.states;
    maxCount += result.maxCount;
  }
  selected.sort((a, b) => a.seed - b.seed);
  return { spacing, selected, maxCount, solverStates, excludedByFixedAncient };
}

function speciesCounts(species: Iterable<TreeSpecies>): Record<TreeSpecies, number> {
  const counts: Record<TreeSpecies, number> = { oak: 0, beech: 0, ancient: 0, willow: 0 };
  for (const value of species) counts[value]++;
  return counts;
}

function numericStats(values: number[]) {
  if (!values.length) return { count: 0, min: null, max: null, mean: null, median: null, p10: null, p90: null };
  const sorted = [...values].sort((a, b) => a - b);
  const quantile = (q: number) => {
    const position = (sorted.length - 1) * q;
    const lo = Math.floor(position), hi = Math.ceil(position);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (position - lo);
  };
  return {
    count: values.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    mean: values.reduce((sum, value) => sum + value, 0) / values.length,
    median: quantile(0.5),
    p10: quantile(0.1),
    p90: quantile(0.9),
  };
}

function distributeShortfall(shortfall: number, oakWeight: number, beechWeight: number) {
  if (shortfall <= 0) return { oak: 0, beech: 0 };
  const totalWeight = oakWeight + beechWeight;
  if (totalWeight <= 0) return { oak: Math.ceil(shortfall / 2), beech: Math.floor(shortfall / 2) };
  const oakIdeal = shortfall * oakWeight / totalWeight;
  const beechIdeal = shortfall - oakIdeal;
  let oak = Math.floor(oakIdeal);
  let beech = Math.floor(beechIdeal);
  let remainder = shortfall - oak - beech;
  const order = [
    { species: "oak" as const, fraction: oakIdeal - oak },
    { species: "beech" as const, fraction: beechIdeal - beech },
  ].sort((a, b) => compareNumbers(b.fraction, a.fraction) || stableHash(a.species, "shortfall-order") - stableHash(b.species, "shortfall-order"));
  for (const item of order) {
    if (!remainder) break;
    if (item.species === "oak") oak++;
    else beech++;
    remainder--;
  }
  return { oak, beech };
}

function pairSpacing(positions: PreparedPosition[]) {
  let min = Infinity;
  let pair: [number, number] | null = null;
  for (let i = 0; i < positions.length; i++) {
    for (let j = 0; j < i; j++) {
      const d = distance2d(positions[i], positions[j]);
      if (d < min) {
        min = d;
        pair = [positions[i].seed, positions[j].seed];
      }
    }
  }
  return { min: Number.isFinite(min) ? min : null, pair };
}

function sortedRecord<T>(values: Map<string, T>) {
  return Object.fromEntries([...values.entries()].sort(([a], [b]) => compareStrings(a, b)));
}

export function planTreeRollout(positionsInput: TreeRolloutPositionInput[], options: TreeRolloutOptions = {}) {
  const targetCounts: Record<TreeSpecies, number> = { ...DEFAULT_TARGET_COUNTS, ...options.targetCounts };
  const fixedAssignments = options.fixedAssignments ?? DEFAULT_FIXED_PILOT;
  const spacingSteps = [...(options.ancientSpacingSteps ?? DEFAULT_ANCIENT_SPACING_STEPS)].sort((a, b) => b - a);
  const minimumSpacing = options.minimumAncientSpacing ?? DEFAULT_MINIMUM_ANCIENT_SPACING;
  if (!spacingSteps.length || spacingSteps[spacingSteps.length - 1] < minimumSpacing) {
    throw new Error(`ancient spacing steps must end at or above the hard minimum ${minimumSpacing}`);
  }
  for (const [species, count] of Object.entries(targetCounts)) {
    if (!Number.isSafeInteger(count) || count < 0) throw new Error(`target count for ${species} must be a non-negative integer`);
  }
  for (const spacing of spacingSteps) {
    if (!Number.isFinite(spacing) || spacing <= 0) throw new Error(`invalid ancient spacing step ${spacing}`);
  }
  const targetTotal = Object.values(targetCounts).reduce((sum, count) => sum + count, 0);
  if (targetTotal !== positionsInput.length) {
    throw new Error(`target counts sum ${targetTotal}, but ${positionsInput.length} tree positions were supplied`);
  }

  const warnings: string[] = [];
  const positions = preparePositions(positionsInput, options.clusterLinkDistance ?? DEFAULT_CLUSTER_LINK_DISTANCE);
  const assignments = new Map<number, AssignmentInfo>();
  const fixedPositions: PreparedPosition[] = [];
  const remainingQuotas = { ...targetCounts };

  for (const [seedText, species] of Object.entries(fixedAssignments)) {
    const seed = Number(seedText);
    const position = positions.find((candidate) => candidate.seed === seed);
    if (!position) throw new Error(`fixed pilot seed ${seed} is missing from the tree positions`);
    assignments.set(seed, { species, stage: "fixed", fixed: true });
    fixedPositions.push(position);
    remainingQuotas[species]--;
    if (remainingQuotas[species] < 0) throw new Error(`fixed pilot assignments exceed the ${species} target`);
  }

  const unassigned = () => positions.filter((position) => !assignments.has(position.seed));

  // 1. Willow: strict hydrological eligibility, no inland fill, and deterministic
  // corridor+cluster proportional stratification.
  const willowTarget = remainingQuotas.willow;
  const willowEligible = unassigned().filter((position) => position.waterDistance <= 30 || (position.waterDistance <= 55 && position.heightAboveWater <= 20));
  const willowSelectCount = Math.min(willowTarget, willowEligible.length);
  const willowGroups = new Map<string, PreparedPosition[]>();
  for (const position of willowEligible) {
    const key = `${position.corridorId}|${position.clusterId}`;
    if (!willowGroups.has(key)) willowGroups.set(key, []);
    willowGroups.get(key)!.push(position);
  }
  const groupItems = [...willowGroups.entries()].map(([key, group]) => ({
    key,
    weight: group.length,
    min: willowSelectCount >= willowGroups.size ? 1 : 0,
    max: group.length,
  }));
  const willowAllocation = allocateProportional(groupItems, willowSelectCount, "willow-corridor-cluster");
  if (willowAllocation.minimaWereDropped) warnings.push("willow minimum representation was softened because the target is smaller than the corridor/cluster group count");
  const selectedWillows: PreparedPosition[] = [];
  for (const [key, group] of willowGroups.entries()) {
    const quota = willowAllocation.allocation.get(key) ?? 0;
    const ranked = [...group].sort((a, b) =>
      compareNumbers(a.waterDistance, b.waterDistance) ||
      compareNumbers(a.heightAboveWater, b.heightAboveWater) ||
      compareNumbers(stableHash(a.seed, "willow-candidate"), stableHash(b.seed, "willow-candidate")) ||
      compareNumbers(a.seed, b.seed),
    );
    selectedWillows.push(...ranked.slice(0, quota));
  }
  selectedWillows.sort((a, b) => a.seed - b.seed);
  for (const position of selectedWillows) assignments.set(position.seed, { species: "willow", stage: "willow", fixed: false });
  const willowShortfall = willowTarget - selectedWillows.length;
  if (willowShortfall > 0) warnings.push(`willow shortfall ${willowShortfall}: no inland fill was used`);

  // 2. Ancient: exact deterministic weighted independent-set packing per spacing step.
  // Cardinality dominates preference, so a shortfall is minimized before aesthetics.
  const ancientTarget = remainingQuotas.ancient;
  const fixedAncients = fixedPositions.filter((position) => assignments.get(position.seed)?.species === "ancient");
  const ancientWeights = new Map<number, number>();
  for (const position of positions) ancientWeights.set(position.seed, CARDINAL_WEIGHT + position.ancientPreference);
  const ancientEvaluations = spacingSteps.map((spacing) => evaluateAncientSpacing(unassigned(), fixedAncients, spacing, ancientWeights));
  let ancientEvaluation = ancientEvaluations.find((evaluation) => evaluation.maxCount >= ancientTarget) ?? ancientEvaluations[ancientEvaluations.length - 1];
  let selectedAncients = [...ancientEvaluation.selected];
  if (selectedAncients.length > ancientTarget) {
    selectedAncients = selectedAncients
      .sort((a, b) => compareNumbers(b.ancientPreference, a.ancientPreference) || compareNumbers(a.seed, b.seed))
      .slice(0, ancientTarget)
      .sort((a, b) => a.seed - b.seed);
  }
  for (const position of selectedAncients) assignments.set(position.seed, { species: "ancient", stage: "ancient", fixed: false });
  const ancientShortfall = ancientTarget - selectedAncients.length;
  if (ancientShortfall > 0) {
    warnings.push(`ancient shortfall ${ancientShortfall} even at the hard minimum spacing of ${minimumSpacing} m; spacing was not relaxed below it`);
  }

  // 3. Willow/ancient shortfalls become additional oak/beech in proportion to their
  // post-pilot base quotas.  This keeps every fixed position assigned without
  // violating hydrology or ancient spacing.
  const baseOak = remainingQuotas.oak;
  const baseBeech = remainingQuotas.beech;
  const redistributed = distributeShortfall(willowShortfall + ancientShortfall, baseOak, baseBeech);
  const oakGoal = baseOak + redistributed.oak;
  const beechGoal = baseBeech + redistributed.beech;

  // 4. Oak/beech: deterministic grove-constrained proportional quota.  For groves
  // with at least two oak/beech slots the min/max constraints reserve one slot for
  // each species whenever the global quota makes that possible.
  const oakBeechPositions = unassigned();
  const fixedOakTotal = fixedPositions.filter((position) => assignments.get(position.seed)?.species === "oak").length;
  const fixedBeechTotal = fixedPositions.filter((position) => assignments.get(position.seed)?.species === "beech").length;
  const finalOakTarget = oakGoal + fixedOakTotal;
  const oakBeechSlotTotal = oakGoal + beechGoal + fixedOakTotal + fixedBeechTotal;
  const desiredFinalOakRatio = finalOakTarget / Math.max(1, oakBeechSlotTotal);
  const clusters = new Map<string, PreparedPosition[]>();
  for (const position of oakBeechPositions) {
    if (!clusters.has(position.clusterId)) clusters.set(position.clusterId, []);
    clusters.get(position.clusterId)!.push(position);
  }
  const clusterItems = [...clusters.entries()].map(([clusterId, clusterPositions]) => {
    const allClusterPositions = positions.filter((position) => position.clusterId === clusterId);
    const fixedOak = allClusterPositions.filter((position) => assignments.get(position.seed)?.species === "oak" && assignments.get(position.seed)?.fixed).length;
    const fixedBeech = allClusterPositions.filter((position) => assignments.get(position.seed)?.species === "beech" && assignments.get(position.seed)?.fixed).length;
    const slots = clusterPositions.length + fixedOak + fixedBeech;
    let minAdditionalOak = 0;
    let maxAdditionalOak = clusterPositions.length;
    if (slots >= 2) {
      minAdditionalOak = Math.max(0, 1 - fixedOak);
      maxAdditionalOak = Math.min(clusterPositions.length, clusterPositions.length - Math.max(0, 1 - fixedBeech));
    }
    if (minAdditionalOak > maxAdditionalOak) {
      // Degenerate cases (for example fixed oak only plus one remaining slot) are
      // impossible to balance exactly.  Keep the mathematical quota feasible.
      minAdditionalOak = 0;
      maxAdditionalOak = clusterPositions.length;
    }
    return {
      key: clusterId,
      weight: slots,
      min: minAdditionalOak,
      max: maxAdditionalOak,
      ideal: desiredFinalOakRatio * slots - fixedOak,
    };
  });
  const oakAllocation = allocateProportional(clusterItems, oakGoal, "oak-beech-cluster");
  if (oakAllocation.minimaWereDropped) warnings.push("oak/beech grove minimum-mix constraints were softened because the oak total was too small");

  const assignedByCluster = new Map<string, number>();
  for (const [clusterId, clusterPositions] of clusters.entries()) {
    const oakCount = oakAllocation.allocation.get(clusterId) ?? 0;
    assignedByCluster.set(clusterId, oakCount);
    const n = clusterPositions.length;
    const centreX = clusterPositions.reduce((sum, position) => sum + position.x, 0) / n;
    const centreZ = clusterPositions.reduce((sum, position) => sum + position.z, 0) / n;
    let xx = 0, xz = 0, zz = 0;
    for (const position of clusterPositions) {
      const dx = position.x - centreX, dz = position.z - centreZ;
      xx += dx * dx;
      xz += dx * dz;
      zz += dz * dz;
    }
    let axisX = xx - zz, axisZ = 2 * xz;
    const axisLength = Math.hypot(axisX, axisZ);
    if (axisLength <= EPSILON) {
      axisX = 1;
      axisZ = 0;
    } else {
      axisX /= axisLength;
      axisZ /= axisLength;
    }
    if (axisX < 0 || (Math.abs(axisX) <= EPSILON && axisZ < 0)) {
      axisX = -axisX;
      axisZ = -axisZ;
    }
    const spatiallyOrdered = [...clusterPositions].sort((a, b) => {
      const ap = (a.x - centreX) * axisX + (a.z - centreZ) * axisZ;
      const bp = (b.x - centreX) * axisX + (b.z - centreZ) * axisZ;
      return compareNumbers(ap, bp) || compareNumbers(stableHash(a.seed, "oak-beech-spatial"), stableHash(b.seed, "oak-beech-spatial")) || compareNumbers(a.seed, b.seed);
    });
    const phase = n ? stableHash(clusterId, "oak-beech-phase") % n : 0;
    const pattern: TreeSpecies[] = [];
    let error = 0;
    for (let i = 0; i < n; i++) {
      error += oakCount;
      if (error >= n) {
        pattern.push("oak");
        error -= n;
      } else pattern.push("beech");
    }
    const rotated = pattern.map((_, index) => pattern[(index + phase) % Math.max(1, n)]);
    spatiallyOrdered.forEach((position, index) => {
      assignments.set(position.seed, { species: rotated[index] ?? "beech", stage: "oak-beech", fixed: false });
    });
  }

  if (assignments.size !== positions.length) throw new Error(`planner left ${positions.length - assignments.size} positions unassigned`);

  const finalCounts = speciesCounts([...assignments.values()].map((assignment) => assignment.species));
  const fixedCounts = speciesCounts(fixedPositions.map((position) => assignments.get(position.seed)!.species));
  const additionalCounts: Record<TreeSpecies, number> = {
    oak: finalCounts.oak - fixedCounts.oak,
    beech: finalCounts.beech - fixedCounts.beech,
    ancient: finalCounts.ancient - fixedCounts.ancient,
    willow: finalCounts.willow - fixedCounts.willow,
  };
  const allAncientPositions = positions.filter((position) => assignments.get(position.seed)?.species === "ancient");
  const ancientPair = pairSpacing(allAncientPositions);
  if (ancientPair.min !== null && ancientPair.min < minimumSpacing - EPSILON) {
    throw new Error(`internal ancient spacing violation: ${ancientPair.min} m`);
  }

  const shortfallTotal = willowShortfall + ancientShortfall;
  const adjustedCounts = { oak: oakGoal, beech: beechGoal };
  if (additionalCounts.oak !== adjustedCounts.oak || additionalCounts.beech !== adjustedCounts.beech) {
    warnings.push(`additional oak/beech counts differ from adjusted quotas: planned oak ${additionalCounts.oak}/${oakGoal}, beech ${additionalCounts.beech}/${beechGoal}`);
  }
  if (shortfallTotal > 0) {
    warnings.push(`target counts are not all reachable under the hard constraints; ${shortfallTotal} positions were proportionally reassigned to oak/beech`);
  }

  const bySeed: Record<string, TreeSpecies> = {};
  const assetBySeed: Record<string, string> = {};
  const scaleRangeBySeed: Record<string, readonly [number, number]> = {};
  const assignmentDetails = positions.map((position) => {
    const assignment = assignments.get(position.seed)!;
    bySeed[String(position.seed)] = assignment.species;
    assetBySeed[String(position.seed)] = TREE_ASSETS[assignment.species];
    scaleRangeBySeed[String(position.seed)] = TREE_SCALE_RANGES[assignment.species];
    const targetScale = TREE_SCALE_RANGES[assignment.species];
    const currentScale = position.input.currentScaleRange;
    return {
      seed: position.seed,
      placementIndex: position.placementIndex,
      fromAsset: position.asset,
      species: assignment.species,
      toAsset: TREE_ASSETS[assignment.species],
      scaleRange: targetScale,
      currentScaleRange: currentScale ?? null,
      stage: assignment.stage,
      fixed: assignment.fixed,
      assetChanged: position.asset !== TREE_ASSETS[assignment.species],
      scaleChanged: !currentScale || currentScale[0] !== targetScale[0] || currentScale[1] !== targetScale[1],
    };
  });

  const statsBySpecies: Record<string, unknown> = {};
  for (const species of Object.keys(TREE_ASSETS) as TreeSpecies[]) {
    const members = positions.filter((position) => assignments.get(position.seed)?.species === species);
    statsBySpecies[species] = {
      count: members.length,
      waterDistance: numericStats(members.map((position) => position.waterDistance)),
      heightAboveWater: numericStats(members.map((position) => position.heightAboveWater)),
    };
  }

  const eligibleByCorridor = new Map<string, number>();
  const selectedWillowByCorridor = new Map<string, number>();
  const eligibleByCorridorCluster = new Map<string, number>();
  const selectedWillowByCorridorCluster = new Map<string, number>();
  for (const position of willowEligible) {
    eligibleByCorridor.set(position.corridorId, (eligibleByCorridor.get(position.corridorId) ?? 0) + 1);
    const leaf = `${position.corridorId}|${position.clusterId}`;
    eligibleByCorridorCluster.set(leaf, (eligibleByCorridorCluster.get(leaf) ?? 0) + 1);
  }
  for (const position of selectedWillows) {
    selectedWillowByCorridor.set(position.corridorId, (selectedWillowByCorridor.get(position.corridorId) ?? 0) + 1);
    const leaf = `${position.corridorId}|${position.clusterId}`;
    selectedWillowByCorridorCluster.set(leaf, (selectedWillowByCorridorCluster.get(leaf) ?? 0) + 1);
  }

  const clusterSpecies = new Map<string, Record<TreeSpecies, number> & { total: number }>();
  for (const position of positions) {
    if (!clusterSpecies.has(position.clusterId)) {
      clusterSpecies.set(position.clusterId, { oak: 0, beech: 0, ancient: 0, willow: 0, total: 0 });
    }
    const entry = clusterSpecies.get(position.clusterId)!;
    entry[assignments.get(position.seed)!.species]++;
    entry.total++;
  }

  const reportPositions = positions.map((position) => {
    const assignment = assignments.get(position.seed)!;
    return {
      seed: position.seed,
      placementIndex: position.placementIndex,
      originalAsset: position.asset,
      species: assignment.species,
      asset: TREE_ASSETS[assignment.species],
      fixed: assignment.fixed,
      stage: assignment.stage,
      x: position.x,
      z: position.z,
      y: position.input.y ?? null,
      waterDistance: position.waterDistance,
      waterHeight: position.waterHeight,
      heightAboveWater: position.heightAboveWater,
      waterFeature: position.waterFeature,
      corridorId: position.corridorId,
      clusterId: position.clusterId,
      clusterSize: position.clusterSize,
      nearestTreeDistance: position.nearestTreeDistance,
      clusterEdgeRatio: position.clusterEdgeRatio,
      localDensity: position.localDensity,
      landmarkDistance: Number.isFinite(position.landmarkDistance) ? position.landmarkDistance : null,
      inMonumentCore: position.inMonumentCore,
      nearCentralAxis: position.nearCentralAxis,
      ancientStructuralScore: position.ancientStructuralScore,
      ancientPreference: position.ancientPreference,
      currentScaleRange: position.input.currentScaleRange ?? null,
      scaleRange: TREE_SCALE_RANGES[assignment.species],
    };
  });

  const sourceCounts = {
    total: positions.length,
    broadleaf: positions.filter((position) => BROADLEAF_ASSETS.has(position.asset)).length,
    pilotFantasy: positions.filter((position) => FANTASY_TREE_ASSETS.has(position.asset)).length,
    other: positions.filter((position) => !ROLLOUT_TREE_ASSETS.has(position.asset)).length,
  };

  return {
    version: 1,
    deterministic: true,
    positionCount: positions.length,
    sourceCounts,
    config: {
      clusterLinkDistance: options.clusterLinkDistance ?? DEFAULT_CLUSTER_LINK_DISTANCE,
      ancientSpacingSteps: spacingSteps,
      minimumAncientSpacing: minimumSpacing,
    },
    targetCounts,
    fixedPilot: Object.fromEntries(Object.entries(fixedAssignments).sort(([a], [b]) => Number(a) - Number(b))),
    quotas: {
      afterFixed: remainingQuotas,
      oakBeechAfterShortfallRedistribution: adjustedCounts,
    },
    counts: finalCounts,
    fixedCounts,
    additionalCounts,
    countsByAsset: speciesCountsAsAssets(finalCounts),
    seedSpecies: bySeed,
    seedAssets: assetBySeed,
    scaleRangeBySeed,
    changes: assignmentDetails,
    willow: {
      rule: WILLOW_RULE,
      target: willowTarget,
      eligibleCount: willowEligible.length,
      selectedCount: selectedWillows.length,
      shortfall: willowShortfall,
      selectedSeeds: selectedWillows.map((position) => position.seed),
      eligibleSeeds: willowEligible.map((position) => position.seed).sort((a, b) => a - b),
      eligibleByCorridor: sortedRecord(eligibleByCorridor),
      selectedByCorridor: sortedRecord(selectedWillowByCorridor),
      eligibleByCorridorCluster: sortedRecord(eligibleByCorridorCluster),
      selectedByCorridorCluster: sortedRecord(selectedWillowByCorridorCluster),
      allocationByCorridorCluster: Object.fromEntries([...willowAllocation.allocation.entries()].sort(([a], [b]) => compareStrings(a, b))),
    },
    ancient: {
      target: ancientTarget,
      fixedSeeds: fixedAncients.map((position) => position.seed).sort((a, b) => a - b),
      selectedAdditionalSeeds: selectedAncients.map((position) => position.seed),
      selectedCount: selectedAncients.length + fixedAncients.length,
      shortfall: ancientShortfall,
      spacingUsed: ancientEvaluation.spacing,
      minimumAllowedSpacing: minimumSpacing,
      spacingSteps: ancientEvaluations.map((evaluation) => ({
        spacing: evaluation.spacing,
        maxSelectableAdditional: evaluation.maxCount,
        selectedAdditional: evaluation.selected.length,
        solverStates: evaluation.solverStates,
        excludedByFixedAncient: evaluation.excludedByFixedAncient,
      })),
      minPairSpacing: ancientPair.min,
      minPairSeeds: ancientPair.pair,
      selectedInMonumentCore: allAncientPositions.filter((position) => position.inMonumentCore).map((position) => position.seed),
      selectedNearCentralAxis: allAncientPositions.filter((position) => position.nearCentralAxis).map((position) => position.seed),
    },
    oakBeech: {
      targetAdditionalOak: oakGoal,
      targetAdditionalBeech: beechGoal,
      targetTotalOak: oakGoal + fixedCounts.oak,
      targetTotalBeech: beechGoal + fixedCounts.beech,
      clusterOakAllocation: Object.fromEntries([...assignedByCluster.entries()].sort(([a], [b]) => compareStrings(a, b))),
      redistributedShortfall: redistributed,
    },
    hydrology: {
      statsBySpecies,
      eligibleWillowCount: willowEligible.length,
    },
    clusters: Object.fromEntries([...clusterSpecies.entries()].sort(([a], [b]) => compareStrings(a, b))),
    shortfalls: {
      willow: willowShortfall,
      ancient: ancientShortfall,
      total: shortfallTotal,
      redistributedToOakBeech: redistributed,
    },
    warnings,
    positions: reportPositions,
  };
}

function speciesCountsAsAssets(counts: Record<TreeSpecies, number>) {
  return Object.fromEntries((Object.keys(TREE_ASSETS) as TreeSpecies[]).map((species) => [TREE_ASSETS[species], counts[species]]));
}
