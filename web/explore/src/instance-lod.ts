export interface Point3 { x: number; y: number; z: number }
export interface Plane extends Point3 { constant: number }
export interface Chunk<T> { centre: Point3; radius: number; items: T[] }
export interface AssetRenderOptions { maxDistance?: number; lodScale?: number; lodRatio?: number; tintVariation?: number; shadowLODs?: number; maxLOD?: number }

export function assetRenderOptions(size: number, global: AssetRenderOptions = {}, asset: AssetRenderOptions = {}) {
  const maxDistance = global.maxDistance ?? asset.maxDistance ?? size * 40;
  const lodScale = global.lodScale ?? asset.lodScale ?? 1;
  const lodRatio = global.lodRatio ?? asset.lodRatio ?? 3;
  const tintVariation = global.tintVariation ?? asset.tintVariation ?? 0;
  const shadowLODs = global.shadowLODs ?? asset.shadowLODs ?? 2;
  const maxLOD = global.maxLOD ?? asset.maxLOD ?? Number.MAX_SAFE_INTEGER;
  if (![size, maxDistance, lodScale].every((n) => Number.isFinite(n) && n > 0) || !Number.isFinite(lodRatio) || lodRatio < 1 || !Number.isFinite(tintVariation) || tintVariation < 0 || tintVariation > 1 || !Number.isSafeInteger(shadowLODs) || shadowLODs < 0 || !Number.isSafeInteger(maxLOD) || maxLOD < 0) {
    throw new Error("Invalid asset distance, LOD or shadow settings");
  }
  return { maxDistance, lodScale, lodRatio, tintVariation, shadowLODs, maxLOD };
}

export function lodDistances(size: number, levels: number, viewportHeight: number, fov: number, maxDistance = size * 40, ratio = 3) {
  const focalLength = viewportHeight / (2 * Math.tan(fov * Math.PI / 360));
  return Array.from({ length: levels }, (_, i) => i === levels - 1 ? maxDistance : Math.min(maxDistance, size * focalLength / (180 / ratio ** i)));
}

export function instanceTint(x: number, z: number, variation = 0): [number, number, number] {
  if (![x, z, variation].every(Number.isFinite) || variation < 0 || variation > 1) throw new Error("Invalid instance tint");
  const noise = (v: number) => { const n = Math.sin(x * 12.9898 + z * 78.233 + v) * 43758.5453; return (n - Math.floor(n)) * 2 - 1; };
  const value = noise(0) * variation, hue = noise(31.7) * variation * 0.35;
  return [Math.max(0, 1 + value - hue), Math.max(0, 1 + value), Math.max(0, 1 + value + hue)];
}

/** levels.length means culled. Distances grow/shrink by 12% before switching. */
export function instanceLOD(distance: number, distances: number[], previous = -1) {
  let lod = previous < 0 ? 0 : Math.min(previous, distances.length);
  const margin = previous < 0 ? 0 : 0.12;
  while (lod < distances.length && distance > distances[lod] * (1 + margin)) lod++;
  while (lod > 0 && distance < distances[lod - 1] * (1 - margin)) lod--;
  return lod;
}

export function spatialChunks<T extends Point3>(items: T[], padding: (item: T) => number, cellSize = 64): Chunk<T>[] {
  const cells = new Map<string, T[]>();
  for (const item of items) {
    const key = `${Math.floor(item.x / cellSize)}_${Math.floor(item.z / cellSize)}`;
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key)!.push(item);
  }
  return [...cells.values()].map((items) => {
    let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (const p of items) {
      const r = padding(p);
      minX = Math.min(minX, p.x - r); maxX = Math.max(maxX, p.x + r);
      minY = Math.min(minY, p.y - r); maxY = Math.max(maxY, p.y + r);
      minZ = Math.min(minZ, p.z - r); maxZ = Math.max(maxZ, p.z + r);
    }
    return { centre: { x: (minX + maxX) / 2, y: (minY + maxY) / 2, z: (minZ + maxZ) / 2 }, radius: Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) / 2, items };
  });
}

export function chunkVisible(chunk: Pick<Chunk<unknown>, "centre" | "radius">, camera: Point3, planes: Plane[], maxDistance: number) {
  const c = chunk.centre, r = chunk.radius;
  if (Math.hypot(c.x - camera.x, c.y - camera.y, c.z - camera.z) > maxDistance + r) return false;
  return planes.every((p) => p.x * c.x + p.y * c.y + p.z * c.z + p.constant >= -r);
}
