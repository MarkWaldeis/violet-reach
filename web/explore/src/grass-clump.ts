// Procedural grass clump geometry for the Violet Reach GPU grass system.
// A clump is a small fan of tapered 3-triangle blades (5 verts each: base pair, mid pair, tip).
// Per-vertex data channels used by the TSL material:
//   uv.y          height fraction along the blade (0 = root, 1 = tip)
//   color.r       per-blade hash 0..1 (wind flutter phase / colour variation)
//   color.g       blade flexibility multiplier (outer blades bend more)
//   uv.x          horizontal position across the blade (0..1, for midrib shading)
// No textures — blades are narrow enough that shading is fully procedural (zero alpha overdraw).
import { BufferAttribute, BufferGeometry } from "three/webgpu";

export interface ClumpOptions {
  blades?: number;
  /** blade height in metres before per-instance scaling */
  height?: number;
  /** blade base width in metres */
  width?: number;
  /** outward tilt of the fan in radians (outer blades) */
  spread?: number;
  /** backward arc of blades, 0 = straight, 1 = strong */
  arc?: number;
  seed?: number;
}

function hash(n: number): number {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
  return s - Math.floor(s);
}

export function buildBladeClump(options: ClumpOptions = {}): BufferGeometry {
  const blades = options.blades ?? 6;
  const height = options.height ?? 0.55;
  const width = options.width ?? 0.055;
  const spread = options.spread ?? 0.42;
  const arc = options.arc ?? 0.55;
  const seed = options.seed ?? 1;

  const positions: number[] = [];
  const uvs: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];

  for (let b = 0; b < blades; b++) {
    const h1 = hash(seed * 31.7 + b * 7.13);
    const h2 = hash(seed * 11.3 + b * 3.77);
    const h3 = hash(seed * 5.5 + b * 13.31);
    const yaw = (b / blades) * Math.PI * 2 + h1 * 1.9;
    const tilt = spread * (0.35 + h2 * 0.9);
    const bladeHeight = height * (0.62 + h3 * 0.55);
    const bladeWidth = width * (0.8 + h1 * 0.5);
    const radius = (h2 - 0.5) * 0.09;
    const cx = Math.cos(yaw) * radius;
    const cz = Math.sin(yaw) * radius;
    // blade local frame: direction it leans toward
    const dx = Math.cos(yaw), dz = Math.sin(yaw);
    // perpendicular (width axis)
    const px = -dz, pz = dx;
    const lean = Math.sin(tilt);
    const rise = Math.cos(tilt);
    const flex = 0.65 + h2 * 0.55;

    // rows: root (h=0), mid (h=0.55), tip (h=1). The arc pushes upper rows outward.
    const rows = [
      { h: 0, halfW: bladeWidth * 0.5, out: 0 },
      { h: 0.55, halfW: bladeWidth * 0.34, out: bladeHeight * lean * 0.45 },
      { h: 1, halfW: 0, out: bladeHeight * lean * (0.45 + arc * 0.55) },
    ];
    const baseIndex = positions.length / 3;
    for (const row of rows) {
      const y = bladeHeight * rise * row.h - (row.h === 1 ? bladeHeight * arc * 0.10 : 0);
      const ox = dx * row.out, oz = dz * row.out;
      const count = row.halfW === 0 ? 1 : 2;
      for (let i = 0; i < count; i++) {
        const side = count === 1 ? 0.5 : i;
        const off = (side - 0.5) * 2 * row.halfW;
        positions.push(cx + ox + px * off, Math.max(0, y), cz + oz + pz * off);
        uvs.push(side, row.h);
        colors.push(h1, flex, 0, 1);
      }
    }
    // triangles: root->mid quad (2), mid->tip fan (1)
    // rows are indexed: root+0,root+1, mid+2,mid+3, tip+4
    indices.push(
      baseIndex + 0, baseIndex + 2, baseIndex + 1,
      baseIndex + 1, baseIndex + 2, baseIndex + 3,
      baseIndex + 2, baseIndex + 4, baseIndex + 3,
    );
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute("uv", new BufferAttribute(new Float32Array(uvs), 2));
  geometry.setAttribute("color", new BufferAttribute(new Float32Array(colors), 4));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** Count triangles of a clump built with the given options (for budget tests). */
export function clumpTriangles(options: ClumpOptions = {}): number {
  return (options.blades ?? 6) * 3;
}
