import { expandPlacements, type Placement } from "./placements.ts";
import { inBounds, readJSON, type Slice } from "./slice.ts";
import type { TerrainStream } from "./terrain-stream.ts";
import { InstanceAssets } from "./instance-assets.ts";
import { placementWaterAt, type Hydrology } from "./hydrology.ts";

export async function sliceAssets(slice: Slice, terrain: TerrainStream, params: URLSearchParams) {
  const [document, hydrology] = await Promise.all([
    readJSON<{ placements: Placement[] }>("./placements.json"), readJSON<Hydrology>("./hydrology.json"),
  ]);
  const entries = [...document.placements];
  const stress = Number(params.get("stress") ?? 0);
  if (!Number.isSafeInteger(stress) || stress < 0 || stress > 100000) throw new Error("stress: 0–100000 erwartet");
  if (stress && entries.length) entries.push({ asset: entries[0].asset, scatter: {
    seed: 73129, count: stress, rect: slice.bounds, min_spacing: 1, max_slope: 60,
    min_height_above_water: 0.5, max_height_above_water: 10000, scale: [0.8, 1.2],
  } });
  const waterAt = placementWaterAt(hydrology);
  const groundAt = (x: number, z: number) => {
    const height = terrain.fullHeightAt(x, z);
    if (height === undefined) return undefined;
    const dx = ((terrain.fullHeightAt(x + 2, z) ?? height) - (terrain.fullHeightAt(x - 2, z) ?? height)) / 4;
    const dz = ((terrain.fullHeightAt(x, z + 2) ?? height) - (terrain.fullHeightAt(x, z - 2) ?? height)) / 4;
    const length = Math.hypot(dx, 1, dz);
    return { height, slope: Math.atan(Math.hypot(dx, dz)) * 180 / Math.PI, normal: [-dx / length, 1 / length, -dz / length] as [number, number, number] };
  };
  const instances = expandPlacements(entries, groundAt, waterAt, (x, z) => inBounds(slice.bounds, x, z));
  const maxDistance = params.has("assetDistance") ? Number(params.get("assetDistance")) : undefined;
  if (maxDistance !== undefined && (!Number.isFinite(maxDistance) || maxDistance <= 0)) throw new Error("assetDistance muss positiv sein");
  return InstanceAssets.load(instances, { maxDistance });
}
