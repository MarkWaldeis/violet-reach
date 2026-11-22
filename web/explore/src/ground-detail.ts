import { DataTexture, LinearFilter, LinearMipmapLinearFilter, RepeatWrapping, RGBAFormat } from "three/webgpu";

export type GroundDetail = "grass" | "soil" | "sand";

export function groundDetailPixels(kind: GroundDetail, size = 256) {
  if (!Number.isInteger(size) || size < 16 || size > 1024) throw new Error("Invalid ground detail size");
  const heights = new Float32Array(size * size), albedo = new Float32Array(size * size);
  let seed = { grass: 73129, soil: 89371, sand: 19733 }[kind];
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  const at = (x: number, y: number) => ((y % size + size) % size) * size + (x % size + size) % size;
  for (let i = 0; i < heights.length; i++) {
    albedo[i] = (kind === "grass" ? 0.27 : 0.5) + (random() - 0.5) * (kind === "sand" ? 0.25 : 0.28);
    heights[i] = random() * (kind === "sand" ? 0.004 : 0.008);
  }
  if (kind === "grass") {
    for (let clump = 0; clump < 170; clump++) {
      const cx = random() * size, cy = random() * size, angle = random() * Math.PI * 2;
      for (let blade = 0; blade < 9; blade++) {
        const x = cx + (random() - 0.5) * size * 0.035, y = cy + (random() - 0.5) * size * 0.035;
        const length = (0.04 + random() * 0.16) * size, direction = angle + (random() - 0.5) * 1.5;
        const shade = 0.38 + random() * 0.6, height = 0.018 + random() * 0.045;
        for (let step = 0; step <= Math.ceil(length * 2); step++) {
          const t = step / Math.ceil(length * 2), bend = t * t * length * 0.3;
          const px = Math.floor(x + Math.cos(direction) * length * t - Math.sin(direction) * bend);
          const py = Math.floor(y + Math.sin(direction) * length * t + Math.cos(direction) * bend);
          for (let edge = 0; edge < 2; edge++) {
            const index = at(px + edge, py);
            albedo[index] = shade * (edge ? 0.55 : 1) * (0.75 + 0.25 * t);
            heights[index] = height * Math.sin(Math.PI * t) * (edge ? 0.4 : 1);
          }
        }
      }
    }
  } else {
    for (let pebble = 0; pebble < (kind === "soil" ? 700 : 380); pebble++) {
      const cx = random() * size, cy = random() * size, r = size * (kind === "soil" ? 0.006 + random() * 0.02 : 0.003 + random() * 0.009);
      const shade = 0.2 + random() * 0.65;
      for (let y = Math.floor(cy - r); y <= cy + r; y++) for (let x = Math.floor(cx - r); x <= cx + r; x++) {
        const d = Math.hypot(x - cx, y - cy) / r;
        if (d > 1) continue;
        const index = at(x, y);
        heights[index] += Math.sqrt(1 - d * d) * (kind === "soil" ? 0.035 : 0.012);
        albedo[index] = shade * (1 - d * 0.2);
      }
    }
  }
  const pixels = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const index = at(x, y), offset = index * 4;
    const dx = (heights[at(x - 1, y)] - heights[at(x + 1, y)]) * size / 4;
    const dz = (heights[at(x, y - 1)] - heights[at(x, y + 1)]) * size / 4;
    // Linear R: albedo multiplier / 2; GB: signed world-XZ normal perturbation.
    pixels[offset] = Math.round(Math.min(1, Math.max(0, albedo[index])) * 255);
    pixels[offset + 1] = Math.round(127.5 + Math.max(-1, Math.min(1, dx)) * 127.5);
    pixels[offset + 2] = Math.round(127.5 + Math.max(-1, Math.min(1, dz)) * 127.5);
    pixels[offset + 3] = 255;
  }
  return pixels;
}

let cached: Record<GroundDetail, DataTexture> | undefined;
export function groundDetails() {
  if (cached) return cached;
  const create = (kind: GroundDetail) => {
    const map = new DataTexture(groundDetailPixels(kind), 256, 256, RGBAFormat);
    map.wrapS = map.wrapT = RepeatWrapping;
    map.generateMipmaps = true;
    map.minFilter = LinearMipmapLinearFilter;
    map.magFilter = LinearFilter;
    map.anisotropy = 16;
    map.needsUpdate = true;
    return map;
  };
  cached = { grass: create("grass"), soil: create("soil"), sand: create("sand") };
  return cached;
}
