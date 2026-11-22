import { tileKey, type HeightTile, type TerrainManifest } from "./heightfield.ts";
import { waterSample, type WaterRegion } from "./hydrology.ts";

export const BANK_RADIUS = 50;
export const BANK_TALUS = Math.tan(32 * Math.PI / 180);
const ITERATIONS = 32;

export function relaxBankTiles(m: TerrainManifest, tiles: ReadonlyMap<string, HeightTile>, region: WaterRegion) {
  if (!tiles.size || (!region.lakes.length && !region.segments.length)) return new Map([...tiles].map(([key, data]) => [key, data.slice()]));
  const coords = [...tiles.keys()].map((key) => key.split("_").map(Number));
  const minX = Math.min(...coords.map(([x]) => x)), maxX = Math.max(...coords.map(([x]) => x));
  const minZ = Math.min(...coords.map(([, z]) => z)), maxZ = Math.max(...coords.map(([, z]) => z));
  const n = m.samples, quads = n - 1, step = m.tileSize / quads;
  const width = (maxX - minX + 1) * quads + 1, height = (maxZ - minZ + 1) * quads + 1;
  let values = new Float32Array(width * height), next = new Float32Array(values.length);
  const active: number[] = [];
  for (let z = 0; z < height; z++) for (let x = 0; x < width; x++) {
    const tx = Math.min(maxX, minX + Math.floor(x / quads)), tz = Math.min(maxZ, minZ + Math.floor(z / quads));
    const tile = tiles.get(tileKey({ x: tx, z: tz }));
    if (!tile) throw new Error("Uferformung: Höhenkachel fehlt");
    const original = tile[(z - (tz - minZ) * quads) * n + x - (tx - minX) * quads];
    const at = z * width + x;
    values[at] = original;
    if (!x || !z || x === width - 1 || z === height - 1) continue;
    const water = waterSample(region, m.originX + minX * m.tileSize + x * step, m.originZ + minZ * m.tileSize + z * step);
    if (water.distance >= BANK_RADIUS || water.distance <= -BANK_RADIUS) continue;
    const floor = water.height - 0.75;
    values[at] = water.distance <= 0
      ? Math.min(water.height - 0.35, Math.max(floor, original))
      : Math.min(original, water.height - 0.35 + BANK_TALUS * water.distance);
    active.push(at);
  }
  const neighbours = [-width - 1, -width, -width + 1, -1, 1, width - 1, width, width + 1];
  const rise = neighbours.map((_, i) => step * BANK_TALUS * ([0, 2, 5, 7].includes(i) ? Math.SQRT2 : 1));
  for (let iteration = 0; iteration < ITERATIONS; iteration++) {
    next.set(values);
    let changed = false;
    for (const at of active) {
      let limited = values[at];
      for (let i = 0; i < neighbours.length; i++) limited = Math.min(limited, values[at + neighbours[i]] + rise[i]);
      next[at] = limited;
      if (values[at] - next[at] > 0.00001) changed = true;
    }
    [values, next] = [next, values];
    if (!changed) break;
  }
  const result = new Map<string, HeightTile>();
  for (const [tx, tz] of coords) {
    const data = new Float32Array(n * n), ox = (tx - minX) * quads, oz = (tz - minZ) * quads;
    for (let z = 0; z < n; z++) data.set(values.subarray((oz + z) * width + ox, (oz + z) * width + ox + n), z * n);
    result.set(tileKey({ x: tx, z: tz }), data);
  }
  return result;
}
