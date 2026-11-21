import { BufferAttribute, BufferGeometry, Color, MathUtils } from "three/webgpu";
import type { HeightTile, TerrainManifest, TileCoords } from "./heightfield.ts";

export function lodStride(m: TerrainManifest, lod: number) {
  return Math.max(1, (m.samples - 1) / 128) * 2 ** lod;
}

const meadow = new Color(0x829648);
const heath = new Color(0x495e36);
const cliff = new Color(0x9c9184);
const scree = new Color(0xc6b79f);
const color = new Color();

export function buildTerrainMesh(m: TerrainManifest, tile: TileCoords, heights: HeightTile, lod: number) {
  const stride = lodStride(m, lod), topStride = lodStride(m, 3);
  const n = m.samples;
  const width = (n - 1) / stride + 1;
  const count = width ** 2 + width * 4;
  const positions = new Float32Array(count * 3);
  const normals = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const indices = new Uint16Array(6 * ((width - 1) ** 2 + 4 * (width - 1)));
  const step = m.tileSize / (n - 1);
  const ox = m.originX + tile.x * m.tileSize, oz = m.originZ + tile.z * m.tileSize;
  const h = (x: number, z: number) => heights[z * n + x];

  for (let z = 0; z < width; z++) {
    for (let x = 0; x < width; x++) {
      const sx = x * stride, sz = z * stride;
      const loX = Math.max(0, sx - 1), hiX = Math.min(n - 1, sx + 1);
      const loZ = Math.max(0, sz - 1), hiZ = Math.min(n - 1, sz + 1);
      const dx = (h(hiX, sz) - h(loX, sz)) / ((hiX - loX) * step);
      const dz = (h(sx, hiZ) - h(sx, loZ)) / ((hiZ - loZ) * step);
      const up = 1 / Math.hypot(dx, 1, dz);
      const px = sx * step, pz = sz * step, height = h(sx, sz);
      const i = z * width + x;
      positions.set([px, height, pz], 3 * i);
      normals.set([-dx * up, up, -dz * up], 3 * i);
      const wx = px + ox, wz = pz + oz;
      const variation = Math.sin(wx * 0.031 + Math.cos(wz * 0.017)) * Math.cos(wz * 0.026) * 0.15
        + Math.sin(wx * 0.005 - wz * 0.009) * 0.19 + 0.48;
      const rock = 1 - MathUtils.smoothstep(up, 0.71, 0.94);
      color.copy(meadow).lerp(heath, variation)
        .lerp(cliff, Math.max(rock, MathUtils.smoothstep(height, 445, 700) * 0.82))
        .lerp(scree, (1 - MathUtils.smoothstep(height, 32, 58)) * 0.75);
      color.toArray(colors, 3 * i);
    }
  }

  let cursor = 0;
  for (let z = 0; z < width - 1; z++) {
    for (let x = 0; x < width - 1; x++) {
      const a = z * width + x, b = a + 1, c = a + width, d = c + 1;
      indices.set([a, c, b, b, c, d], cursor);
      cursor += 6;
    }
  }

  // Drop the perimeter beneath the finest edge anywhere a coarse neighbor can interpolate.
  // Shared samples keep neighboring tiles coincident; these skirts cover T-junctions across LODs.
  const edges = [
    (i: number) => i,
    (i: number) => i * width + width - 1,
    (i: number) => width * width - 1 - i,
    (i: number) => (width - 1 - i) * width,
  ];
  let skirt = width ** 2;
  for (const edge of edges) {
    for (let j = 0; j < width; j++, skirt++) {
      const src = edge(j);
      const floor = lowerEdge(edge, j, width, stride, topStride, heights, n);
      positions.set([positions[3 * src], floor, positions[3 * src + 2]], 3 * skirt);
      normals.set(normals.subarray(3 * src, 3 * src + 3), 3 * skirt);
      colors.set(colors.subarray(3 * src, 3 * src + 3), 3 * skirt);
      if (j > 0) {
        const prev = edge(j - 1);
        indices.set([prev, src, skirt - 1, src, skirt, skirt - 1], cursor);
        cursor += 6;
      }
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new BufferAttribute(normals, 3));
  geometry.setAttribute("color", new BufferAttribute(colors, 3));
  geometry.setIndex(new BufferAttribute(indices, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

function lowerEdge(
  edge: (i: number) => number, j: number, width: number,
  stride: number, coarse: number, heights: HeightTile, n: number,
) {
  const start = edge(0), next = edge(1);
  const offset = (i: number) => (Math.floor(i / width) * n + i % width) * stride;
  const origin = offset(start), increment = (offset(next) - origin) / stride;
  let lowest = Infinity;
  for (let i = Math.max(0, j * stride - coarse); i <= Math.min(n - 1, j * stride + coarse); i++) {
    lowest = Math.min(lowest, heights[origin + increment * i]);
  }
  return lowest - 2;
}
