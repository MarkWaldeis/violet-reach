import { BufferAttribute, BufferGeometry } from "three/webgpu";
import type { HeightTile, TerrainManifest, TileCoords } from "./heightfield.ts";

export function lodStride(m: TerrainManifest, lod: number) {
  return Math.max(1, (m.samples - 1) / 128) * 2 ** lod;
}

export function buildTerrainMesh(m: TerrainManifest, tile: TileCoords, heights: HeightTile, lod: number) {
  const stride = lodStride(m, lod), n = m.samples;
  const width = (n - 1) / stride + 1;
  const positions: number[] = [], normals: number[] = [], indices: number[] = [];
  const step = m.tileSize / (n - 1);
  const add = (sx: number, sz: number) => {
    const i = positions.length / 3;
    positions.push(sx * step, heights[sz * n + sx], sz * step);
    const lx = Math.max(0, sx - 1), hx = Math.min(n - 1, sx + 1);
    const lz = Math.max(0, sz - 1), hz = Math.min(n - 1, sz + 1);
    const dx = (heights[sz * n + hx] - heights[sz * n + lx]) / ((hx - lx) * step);
    const dz = (heights[hz * n + sx] - heights[lz * n + sx]) / ((hz - lz) * step);
    const length = Math.hypot(dx, 1, dz);
    normals.push(-dx / length, 1 / length, -dz / length);
    return i;
  };
  for (let z = 0; z < width; z++) for (let x = 0; x < width; x++) add(x * stride, z * stride);
  for (let z = 1; z < width - 2; z++) for (let x = 1; x < width - 2; x++) {
    const a = z * width + x, b = a + 1, c = a + width;
    indices.push(a, c, b, b, c, c + 1);
  }
  const coreIndices = indices.length;
  // Every LOD shares the full-resolution boundary. Zipper strips replace skirts.
  const edges = [
    (v: number, inset: number) => [v, inset],
    (v: number, inset: number) => [n - 1 - inset, v],
    (v: number, inset: number) => [n - 1 - v, n - 1 - inset],
    (v: number, inset: number) => [inset, n - 1 - v],
  ];
  for (const edge of edges) {
    const outer = Array.from({ length: n }, (_, i) => { const [x, z] = edge(i, 0); return add(x, z); });
    const inner = Array.from({ length: width - 2 }, (_, i) => {
      const [x, z] = edge((i + 1) * stride, stride);
      return z / stride * width + x / stride;
    });
    let a = 0, b = 0;
    while (a < outer.length - 1 || b < inner.length - 1) {
      if (b === inner.length - 1 || (a < outer.length - 1 && (a + 1) / (outer.length - 1) <= (b + 1) / (inner.length - 1))) {
        indices.push(outer[a], inner[b], outer[a + 1]); a++;
      } else {
        indices.push(outer[a], inner[b], inner[b + 1]); b++;
      }
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute("normal", new BufferAttribute(new Float32Array(normals), 3));
  geometry.setIndex(indices);
  geometry.userData.coreIndices = coreIndices;
  geometry.userData.strideMetres = stride * step;
  geometry.userData.tileSize = m.tileSize;
  geometry.computeBoundingSphere();
  geometry.name = `terrain_${tile.x}_${tile.z}_LOD${lod}`;
  return geometry;
}

export function stitchedHeight(geometry: BufferGeometry, x: number, z: number): number | undefined {
  const { tileSize, strideMetres, coreIndices } = geometry.userData;
  if (x >= strideMetres && z >= strideMetres && x <= tileSize - strideMetres && z <= tileSize - strideMetres) return undefined;
  const index = geometry.index!, p = geometry.attributes.position;
  for (let i = coreIndices; i < index.count; i += 3) {
    const a = index.getX(i), b = index.getX(i + 1), c = index.getX(i + 2);
    const ax = p.getX(a), az = p.getZ(a), bx = p.getX(b), bz = p.getZ(b), cx = p.getX(c), cz = p.getZ(c);
    const d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz);
    if (Math.abs(d) < 1e-8) continue;
    const u = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d;
    const v = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d;
    if (u >= -1e-6 && v >= -1e-6 && u + v <= 1 + 1e-6) return u * p.getY(a) + v * p.getY(b) + (1 - u - v) * p.getY(c);
  }
  return undefined;
}
