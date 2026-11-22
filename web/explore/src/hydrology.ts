import type { Bounds, Slice } from "./slice.ts";

export interface Lake { name: string; water_y: number; outline: [number, number][] }
export interface River { name: string; polyline: [number, number, number, number][] }
export interface Hydrology { lakes: Lake[]; rivers: River[] }
export interface WaterSegment { a: number[]; b: number[] }
export interface WaterRegion { lakes: Lake[]; segments: WaterSegment[]; bounds: Bounds }

export function segmentSample(x: number, z: number, a: number[], b: number[]) {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz || 1)));
  return { distance: Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz), t };
}

export function polygonDistance(x: number, z: number, polygon: number[][]) {
  let inside = false, distance = Infinity;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if ((a[1] > z) !== (b[1] > z) && x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    distance = Math.min(distance, segmentSample(x, z, a, b).distance);
  }
  return inside ? -distance : distance;
}

export function boundsOf(points: number[][]): Bounds {
  return { minX: Math.min(...points.map((p) => p[0])), minZ: Math.min(...points.map((p) => p[1])), maxX: Math.max(...points.map((p) => p[0])), maxZ: Math.max(...points.map((p) => p[1])) };
}
const intersects = (a: Bounds, b: Bounds) => a.minX <= b.maxX && a.maxX >= b.minX && a.minZ <= b.maxZ && a.maxZ >= b.minZ;

export function selectWater(hydrology: Hydrology, slice: Bounds): WaterRegion {
  const lakes = hydrology.lakes.filter((lake) => lake.name === "Spiegelsee" || intersects(boundsOf(lake.outline), slice));
  const b = boundsOf([[slice.minX, slice.minZ], [slice.maxX, slice.maxZ], ...lakes.flatMap((lake) => lake.outline)]);
  const bounds = { minX: b.minX - 100, minZ: b.minZ - 100, maxX: b.maxX + 100, maxZ: b.maxZ + 100 };
  const segments: WaterSegment[] = [];
  for (const river of hydrology.rivers) for (let i = 1; i < river.polyline.length; i++) {
    const a = river.polyline[i - 1], b = river.polyline[i];
    if (intersects(boundsOf([a, b]), bounds)) segments.push({ a, b });
  }
  const full = boundsOf([[bounds.minX, bounds.minZ], [bounds.maxX, bounds.maxZ], ...segments.flatMap(({ a, b }) => [
    [a[0] - a[3] / 2, a[1] - a[3] / 2], [a[0] + a[3] / 2, a[1] + a[3] / 2],
    [b[0] - b[3] / 2, b[1] - b[3] / 2], [b[0] + b[3] / 2, b[1] + b[3] / 2],
  ])]);
  return { lakes, segments, bounds: full };
}

export function waterSample(region: Pick<WaterRegion, "lakes" | "segments">, x: number, z: number) {
  let distance = Infinity, height = 0, lakeDistance = Infinity;
  for (const lake of region.lakes) {
    const shore = polygonDistance(x, z, lake.outline);
    lakeDistance = Math.min(lakeDistance, shore);
    const d = shore + 3;
    if (d < distance) { distance = d; height = lake.water_y; }
  }
  for (const { a, b } of region.segments) {
    const sample = segmentSample(x, z, a, b);
    const d = sample.distance - (a[3] + sample.t * (b[3] - a[3])) / 2;
    if (d < distance) { distance = d; height = a[2] + sample.t * (b[2] - a[2]); }
  }
  return { distance, height, lakeDistance };
}

export function placementWaterAt(hydrology: Hydrology) {
  const lakes = hydrology.lakes.map((lake) => ({ lake, bounds: boundsOf(lake.outline) }));
  const segments = hydrology.rivers.flatMap((river) => river.polyline.slice(1).map((b, i) => {
    const a = river.polyline[i];
    return { a, b, bounds: boundsOf([a, b]), radius: Math.max(a[3], b[3]) / 2 };
  }));
  const lowerBound = (b: Bounds, x: number, z: number) => Math.max(b.minX - x, x - b.maxX, b.minZ - z, z - b.maxZ);
  return (x: number, z: number) => {
    let distance = Infinity, height = 0;
    for (const { lake, bounds } of lakes) {
      if (lowerBound(bounds, x, z) + 3 >= distance) continue;
      const d = polygonDistance(x, z, lake.outline) + 3;
      if (d < distance) { distance = d; height = lake.water_y; }
    }
    for (const { a, b, bounds, radius } of segments) {
      if (lowerBound(bounds, x, z) - radius >= distance) continue;
      const sample = segmentSample(x, z, a, b);
      const d = sample.distance - (a[3] + sample.t * (b[3] - a[3])) / 2;
      if (d < distance) { distance = d; height = a[2] + sample.t * (b[2] - a[2]); }
    }
    return height;
  };
}

export function pathMask(paths: Slice["paths"], x: number, z: number) {
  let distance = Infinity;
  for (const path of paths ?? []) for (let i = 1; i < path.polyline.length; i++) {
    distance = Math.min(distance, segmentSample(x, z, path.polyline[i - 1], path.polyline[i]).distance - path.width / 2);
  }
  const t = Math.max(0, Math.min(1, (distance + 0.4) / 1.6));
  return 1 - t * t * (3 - 2 * t);
}
