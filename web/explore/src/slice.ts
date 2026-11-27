import type { AssetRenderOptions } from "./instance-lod.ts";
import type { SliceEffects } from "./landmark-effects.ts";

export interface Bounds { minX: number; minZ: number; maxX: number; maxZ: number }
export interface Spawn { x: number; z: number; yaw: number }
export interface Slice {
  bounds: Bounds;
  centre: { x: number; z: number };
  spawn: { fly: Spawn; walk: Spawn };
  paths?: { polyline: [number, number][]; width: number }[];
  asset_options?: Record<string, AssetRenderOptions>;
  /** Optional sparse landmark effects; validated by parseSliceEffects before use. */
  effects?: SliceEffects;
}
export const inBounds = (b: Bounds, x: number, z: number) => x >= b.minX && x <= b.maxX && z >= b.minZ && z <= b.maxZ;
export async function readJSON<T>(path: string): Promise<T> {
  const response = await fetch(new URL(path, location.href));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}
