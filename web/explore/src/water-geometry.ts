import { BufferAttribute, BufferGeometry, ShapeUtils, Vector2 } from "three/webgpu";
import type { WaterRegion } from "./hydrology.ts";

export function buildWaterGeometry(region: WaterRegion) {
  const positions: number[] = [], flows: number[] = [], lakes: number[] = [], indices: number[] = [];
  const add = (x: number, y: number, z: number, fx: number, fz: number, lake: number) => {
    const index = positions.length / 3;
    positions.push(x, y + 0.03, z); flows.push(fx, fz); lakes.push(lake);
    return index;
  };
  for (const lake of region.lakes) {
    const outline = lake.outline.map(([x, z]) => new Vector2(x, z));
    const start = positions.length / 3;
    for (const p of outline) add(p.x, lake.water_y, p.y, 0.9, 0.43589, 1);
    for (const [a, b, c] of ShapeUtils.triangulateShape(outline, [])) indices.push(start + a, start + c, start + b);
  }
  for (const [segmentIndex, { a, b }] of region.segments.entries()) {
    const dx = b[0] - a[0], dz = b[1] - a[1], length = Math.hypot(dx, dz);
    if (!length) continue;
    const fx = dx / length, fz = dz / length;
    const i = positions.length / 3;
    const before = region.segments[segmentIndex - 1], after = region.segments[segmentIndex + 1];
    for (const [end, p] of [a, b].entries()) {
      const neighbour = end === 0 && before?.b === a ? before.a : end === 1 && after?.a === b ? after.b : undefined;
      const direction = end === 0 ? -1 : 1;
      const nx = neighbour ? (neighbour[0] - p[0]) * direction : fx, nz = neighbour ? (neighbour[1] - p[1]) * direction : fz;
      const neighbourLength = Math.hypot(nx, nz) || 1;
      const tx = fx + nx / neighbourLength, tz = fz + nz / neighbourLength, tangentLength = Math.hypot(tx, tz) || 1;
      const ux = tx / tangentLength, uz = tz / tangentLength;
      const halfWidth = p[3] / 2 / Math.max(0.7, ux * fx + uz * fz);
      for (const side of [-1, 1]) add(p[0] - uz * halfWidth * side, p[2], p[1] + ux * halfWidth * side, ux, uz, 0);
    }
    indices.push(i, i + 1, i + 2, i + 2, i + 1, i + 3);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute("flow", new BufferAttribute(new Float32Array(flows), 2));
  geometry.setAttribute("lake", new BufferAttribute(new Float32Array(lakes), 1));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}
