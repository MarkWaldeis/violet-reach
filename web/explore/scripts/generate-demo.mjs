import { mkdir, readFile, writeFile } from "node:fs/promises";

// Synthetic developer fixture only; production terrain is exported from Blender.
const target = new URL("../public/demo-terrain/", import.meta.url);
const m = {
  version: 1, tilesX: 16, tilesZ: 16, tileSize: 500, samples: 129,
  originX: -4000, originZ: -4000, minHeight: -25, maxHeight: 1150,
  spawn: { x: -940, z: 1210, yaw: -0.82 },
};
const marker = new URL(".fixture-version", target);
const fixtureVersion = await readFile(new URL(import.meta.url));
if ((await readFile(marker).catch(() => null))?.equals(fixtureVersion)) process.exit(0);

const mix = (a, b, t) => a + (b - a) * t;
const smooth = (t) => t * t * (3 - 2 * t);
function hash(x, z) {
  let n = Math.imul(x, 374761393) + Math.imul(z, 668265263) | 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
}
function noise(x, z) {
  const i = Math.floor(x), j = Math.floor(z);
  const u = smooth(x - i), v = smooth(z - j);
  return mix(mix(hash(i, j), hash(i + 1, j), u), mix(hash(i, j + 1), hash(i + 1, j + 1), u), v);
}
function fbm(x, z) {
  return (noise(x, z) + 0.48 * noise(x * 2.08, z * 2.08) + 0.22 * noise(x * 4.21, z * 4.21)
    + 0.09 * noise(x * 8.4, z * 8.4)) / 1.79;
}
function ridge(x, z, cx, cz, sx, sz, tilt) {
  const a = x - cx, b = z - cz;
  return Math.exp(-(((a + b * tilt) / sx) ** 2 + ((b - a * tilt * 0.42) / sz) ** 2));
}
function height(x, z) {
  const warpedX = x + 430 * (noise(x / 1120 + 9, z / 1120 + 13) - 0.5);
  const warpedZ = z + 430 * (noise(x / 1120 + 2, z / 1120 + 7) - 0.5);
  const n = fbm(warpedX / 530, warpedZ / 530);
  const rock = 1 - Math.abs(2 * n - 1);
  const hills = 48 + 138 * fbm(x / 710 + 5, z / 710 + 5);
  const highlands = (470 * ridge(warpedX, warpedZ, -400, -1460, 1950, 925, 0.48)
    + 535 * ridge(warpedX, warpedZ, 1680, -2180, 1130, 980, -0.62)
    + 320 * ridge(warpedX, warpedZ, 1700, 570, 1100, 1030, 0.55)
    + 260 * ridge(warpedX, warpedZ, -2080, 590, 980, 1540, -0.45)) * (0.33 + rock * rock * 0.85);
  const riverX = 260 * Math.sin(z / 565 + 0.5) + 460 * Math.sin(z / 1770) + 210;
  const across = Math.abs(x - riverX);
  const width = 260 + 98 * noise(z / 420, 12);
  const gorge = Math.max(0, Math.min(1, (across - 31) / width));
  const bank = 11 + 13 * noise(x / 147, z / 335) + 0.004 * (4000 - z);
  const nearDetail = 0.95 * (noise(x / 15, z / 15) - 0.5);
  return mix(bank, hills + highlands + 7 * noise(x / 73, z / 73), smooth(gorge)) + nearDetail;
}

await mkdir(target, { recursive: true });
await writeFile(new URL("manifest.json", target), JSON.stringify(m, null, 2) + "\n");
const stride = m.samples - 1;
const side = m.tilesX * stride + 1;
const heights = new Uint16Array(side * (m.tilesZ * stride + 1));
for (let j = 0; j <= m.tilesZ * stride; j++) {
  for (let i = 0; i <= m.tilesX * stride; i++) {
    const h = height(m.originX + i * m.tileSize / stride, m.originZ + j * m.tileSize / stride);
    heights[j * side + i] = Math.round(65535 * Math.max(0, Math.min(1, (h - m.minHeight) / (m.maxHeight - m.minHeight))));
  }
}
for (let z = 0; z < m.tilesZ; z++) {
  for (let x = 0; x < m.tilesX; x++) {
    const buffer = Buffer.alloc(m.samples * m.samples * 2);
    for (let j = 0; j < m.samples; j++) {
      for (let i = 0; i < m.samples; i++) {
        buffer.writeUInt16LE(heights[(z * stride + j) * side + x * stride + i], 2 * (j * m.samples + i));
      }
    }
    await writeFile(new URL(`${x}_${z}.r16`, target), buffer);
  }
}
await writeFile(marker, fixtureVersion);
