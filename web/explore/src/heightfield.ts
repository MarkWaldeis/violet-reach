export interface TerrainManifest {
  version: 1;
  tilesX: number;
  tilesZ: number;
  tileSize: number;
  samples: number;
  originX: number;
  originZ: number;
  minHeight: number;
  maxHeight: number;
  spawn?: { x: number; z: number; yaw: number };
}

export interface TileCoords { x: number; z: number }
export type HeightTile = Float32Array;
export const tileKey = ({ x, z }: TileCoords) => `${x}_${z}`;
export const MAX_TILE_DISTANCE = 3600;
export const LOD_DISTANCES = [750, 1450, 2350];

export function parseManifest(value: unknown): TerrainManifest {
  const m = value as TerrainManifest | null;
  const positiveInt = (n: number) => Number.isSafeInteger(n) && n > 0;
  if (
    !m || m.version !== 1 || !positiveInt(m.tilesX) || !positiveInt(m.tilesZ) ||
    !Number.isFinite(m.tileSize) || m.tileSize < 1 || m.tileSize > 8000 ||
    ![17, 33, 65, 129, 257].includes(m.samples) ||
    ![m.originX, m.originZ, m.minHeight, m.maxHeight].every(Number.isFinite) ||
    !(m.maxHeight > m.minHeight) ||
    (m.spawn && ![m.spawn.x, m.spawn.z, m.spawn.yaw].every(Number.isFinite))
  ) throw new Error("Ungültiges Gelände-Manifest (Version 1 erwartet).");
  return m;
}

export function decodeTile(buffer: ArrayBuffer, m: TerrainManifest): HeightTile {
  const count = m.samples ** 2;
  if (buffer.byteLength !== count * 2) throw new Error("Falsche Dateigröße der Höhenkachel.");
  const view = new DataView(buffer);
  const heights = new Float32Array(count);
  const scale = (m.maxHeight - m.minHeight) / 65535;
  for (let i = 0; i < count; i++) heights[i] = m.minHeight + view.getUint16(i * 2, true) * scale;
  return heights;
}

export function worldTile(m: TerrainManifest, x: number, z: number): TileCoords {
  return {
    x: Math.min(m.tilesX - 1, Math.max(0, Math.floor((x - m.originX) / m.tileSize))),
    z: Math.min(m.tilesZ - 1, Math.max(0, Math.floor((z - m.originZ) / m.tileSize))),
  };
}

export function distanceToTile(m: TerrainManifest, tile: TileCoords, x: number, z: number): number {
  const dx = x - m.originX - tile.x * m.tileSize;
  const dz = z - m.originZ - tile.z * m.tileSize;
  return Math.hypot(Math.max(0, -dx, dx - m.tileSize), Math.max(0, -dz, dz - m.tileSize));
}

export function selectTiles(m: TerrainManifest, x: number, z: number, radius = Math.min(MAX_TILE_DISTANCE, 10 * m.tileSize)) {
  const from = worldTile(m, x - radius, z - radius);
  const to = worldTile(m, x + radius, z + radius);
  const result: { coords: TileCoords; distance: number }[] = [];
  for (let tz = from.z; tz <= to.z; tz++) {
    for (let tx = from.x; tx <= to.x; tx++) {
      const coords = { x: tx, z: tz };
      const distance = distanceToTile(m, coords, x, z);
      if (distance < radius) result.push({ coords, distance });
    }
  }
  return result.sort((a, b) => a.distance - b.distance);
}

export function chooseLOD(distance: number, current?: number): number {
  const hysteresis = 90;
  let lod = current ?? 0;
  while (lod < LOD_DISTANCES.length && distance > LOD_DISTANCES[lod] + (current === undefined ? 0 : hysteresis)) lod++;
  while (lod > 0 && distance < LOD_DISTANCES[lod - 1] - hysteresis) lod--;
  return lod;
}

// Use the same diagonal and decimation as the mesh so walk height agrees with the visible ground.
export function sampleTile(heights: HeightTile, n: number, stride: number, u: number, v: number): number {
  const quads = (n - 1) / stride;
  const sx = Math.max(0, Math.min(quads, u * quads));
  const sz = Math.max(0, Math.min(quads, v * quads));
  const qx = Math.min(quads - 1, Math.floor(sx)), qz = Math.min(quads - 1, Math.floor(sz));
  const i = (qz * n + qx) * stride;
  const tx = sx - qx, tz = sz - qz;
  const a = heights[i], b = heights[i + stride];
  const c = heights[i + stride * n], d = heights[i + stride * (n + 1)];
  return tx + tz <= 1
    ? a + (b - a) * tx + (c - a) * tz
    : d + (c - d) * (1 - tx) + (b - d) * (1 - tz);
}
