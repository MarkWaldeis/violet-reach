import type { Slice } from "./slice.ts";
import type { ScatterPlacement } from "./placements.ts";

const smooth = (lo: number, hi: number, value: number) => {
  const t = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};
const rotate = (n: number, bits: number) => (n << bits) | (n >>> (32 - bits));
function hash(x: number, y: number) {
  const seed = 0xdeadbeef + 21;
  let a = (seed + x) >>> 0, b = (seed + y) >>> 0, c = seed >>> 0;
  c = ((c ^ b) - rotate(b, 14)) >>> 0;
  a = ((a ^ c) - rotate(c, 11)) >>> 0;
  b = ((b ^ a) - rotate(a, 25)) >>> 0;
  c = ((c ^ b) - rotate(b, 16)) >>> 0;
  a = ((a ^ c) - rotate(c, 4)) >>> 0;
  b = ((b ^ a) - rotate(a, 14)) >>> 0;
  return ((c ^ b) - rotate(b, 24)) >>> 0;
}

/** MaterialX's two-dimensional gradient noise, also used by the ground shader. */
export function groundNoise(x: number, z: number) {
  const ix = Math.floor(x), iz = Math.floor(z), fx = x - ix, fz = z - iz;
  const fade = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
  const gradient = (dx: number, dz: number) => {
    const h = hash(ix + dx, iz + dz) & 7, a = fx - dx, b = fz - dz;
    const u = h < 4 ? a : b, v = 2 * (h < 4 ? b : a);
    return (h & 1 ? -u : u) + (h & 2 ? -v : v);
  };
  const mix = (a: number, b: number, t: number) => a * (1 - t) + b * t;
  return 0.6616 * mix(mix(gradient(0, 0), gradient(1, 0), fade(fx)), mix(gradient(0, 1), gradient(1, 1), fade(fx)), fade(fz));
}

export function scatterSurface(
  surface: NonNullable<ScatterPlacement["scatter"]["surface"]>, x: number, z: number,
  normal: [number, number, number], aboveWater: number, paths: NonNullable<Slice["paths"]>,
  clearance = 0.5, hollow = 0,
) {
  for (const path of paths) for (let i = 1; i < path.polyline.length; i++) {
    const a = path.polyline[i - 1], b = path.polyline[i], dx = b[0] - a[0], dz = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / Math.max(0.0001, dx * dx + dz * dz)));
    if (Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz) < path.width / 2 + 2.5 + clearance) return false;
  }
  if (surface === "shore") return aboveWater >= -0.3 && aboveWater <= 0.03 && normal[1] > Math.cos(28 * Math.PI / 180);
  if (aboveWater < 6 || normal[1] < Math.cos(28 * Math.PI / 180)) return false;
  if (surface === "land") return true;
  const patches = groundNoise(x * 0.046 + 71, z * 0.046 - 39) * 1.3 + 0.5;
  const small = groundNoise(x * 0.16 - 19, z * 0.16 + 58) * 1.2 + 0.5;
  const bare = smooth(0.68, 0.94, patches + (small - 0.5) * 0.3) * 0.55 + smooth(0.07, 0.17, 1 - normal[1]) * 0.15;
  const clumps = groundNoise(x * 0.17 + 13.7, z * 0.17 - 6.3) + groundNoise(x * 0.43 - 31.2, z * 0.43 + 14.9) * 0.35;
  return bare < 0.12 && hollow < 0.6 && clumps > 0.13;
}
