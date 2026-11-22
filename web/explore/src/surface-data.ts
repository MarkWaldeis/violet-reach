import { DataTexture, FloatType, LinearFilter, RGBAFormat, Vector2, type Node } from "three/webgpu";
import { texture, uniform } from "three/tsl";
import { waterSample, type WaterRegion } from "./hydrology.ts";
import type { Slice } from "./slice.ts";
import type { TerrainStream } from "./terrain-stream.ts";

export async function surfaceData(region: WaterRegion, slice: Slice, terrain: TerrainStream) {
  const b = region.bounds;
  await terrain.preloadHeights(b);
  const width = Math.ceil((b.maxX - b.minX) / 4) + 1, height = Math.ceil((b.maxZ - b.minZ) / 4) + 1;
  const data = new Float32Array(width * height * 4);
  for (let j = 0; j < height; j++) for (let i = 0; i < width; i++) {
    const x = b.minX + i / (width - 1) * (b.maxX - b.minX), z = b.minZ + j / (height - 1) * (b.maxZ - b.minZ);
    const water = waterSample(region, x, z), at = 4 * (j * width + i);
    const ground = terrain.fullHeightAt(x, z);
    if (ground === undefined) throw new Error("Oberflächendaten: Höhenkachel fehlt");
    data.set([ground, water.height, Math.min(water.distance, 10000), Math.min(water.lakeDistance, 10000)], at);
  }
  const map = new DataTexture(data, width, height, RGBAFormat, FloatType);
  map.minFilter = map.magFilter = LinearFilter;
  map.needsUpdate = true;
  const origin = uniform(new Vector2(b.minX, b.minZ)), size = uniform(new Vector2(b.maxX - b.minX, b.maxZ - b.minZ));
  const dimensions = uniform(new Vector2(width, height));
  return {
    map,
    paths: slice.paths ?? [],
    sample: (xz: Node<"vec2">) => texture(map, xz.sub(origin).div(size).mul(dimensions.sub(1)).add(0.5).div(dimensions)),
    origin, size,
  };
}
export type SurfaceData = Awaited<ReturnType<typeof surfaceData>>;
