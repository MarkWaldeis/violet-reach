// CPU-side sampling of the world macro maps for the grass system.
// Reads the SAME macro_color_ao / macro_grass textures the ground shader uses,
// so blade colour, density and dryness always match the terrain underneath.
// The textures are decoded once into ImageData and bilinearly sampled.

export interface GrassMacroSample {
  /** 0..1 — 0 means: no grass here (water, paths, steep rock, dry beach sand). */
  density: number;
  /** 0..1 — blade height multiplier. */
  heightScale: number;
  /** 0..1 — blend lush grass_green toward sun-baked grass_dry. */
  dryMix: number;
  /** 0..1 — combined sky-view & canopy shadow multiplier (1 = open sky). */
  canopyShadow: number;
  /** sRGB 0..1 macro ground/grass albedo tint, matches the terrain colour exactly at large scale. */
  tintR: number;
  tintG: number;
  tintB: number;
  /** 0..1 linear large-scale horizon AO baked into the macro colour map alpha. */
  ao: number;
}

export interface GrassMacroConfig {
  minX: number;
  minZ: number;
  size: number;
}

export const MACRO_MIN = -4096;
export const MACRO_SIZE = 8192;

interface ChannelImage {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export class GrassMacroSampler {
  #grass: ChannelImage;
  #color: ChannelImage;
  readonly config: GrassMacroConfig;

  constructor(grass: ChannelImage, color: ChannelImage, config: GrassMacroConfig = { minX: MACRO_MIN, minZ: MACRO_MIN, size: MACRO_SIZE }) {
    this.#grass = grass;
    this.#color = color;
    this.config = config;
  }

  static fromImageData(grass: ImageData, color: ImageData, config?: GrassMacroConfig) {
    return new GrassMacroSampler(
      { width: grass.width, height: grass.height, data: grass.data },
      { width: color.width, height: color.height, data: color.data },
      config,
    );
  }

  /** Decode both macro webp files through an offscreen canvas (browser only). */
  static async load(baseUrl: string, config?: GrassMacroConfig): Promise<GrassMacroSampler> {
    const decode = async (file: string): Promise<ChannelImage> => {
      const response = await fetch(new URL(file, baseUrl).href);
      if (!response.ok) throw new Error(`Makrokarte ${file}: HTTP ${response.status}`);
      const blob = await response.blob();
      const bitmap = await createImageBitmap(blob);
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      return { width: img.width, height: img.height, data: img.data };
    };
    const [grass, color] = await Promise.all([decode("macro_grass.webp"), decode("macro_color_ao.webp")]);
    return new GrassMacroSampler(grass, color, config);
  }

  #bilinear(img: ChannelImage, u: number, v: number): [number, number, number, number] {
    const x = u * img.width - 0.5, y = v * img.height - 0.5;
    const fx = x - Math.floor(x), fy = y - Math.floor(y);
    const clampi = (n: number, max: number) => Math.min(Math.max(n, 0), max - 1);
    const x0 = clampi(Math.floor(x), img.width), x1 = clampi(Math.floor(x) + 1, img.width);
    const y0 = clampi(Math.floor(y), img.height), y1 = clampi(Math.floor(y) + 1, img.height);
    const read = (xx: number, yy: number, c: number) => img.data[(yy * img.width + xx) * 4 + c] / 255;
    const out: [number, number, number, number] = [0, 0, 0, 0];
    for (let c = 0; c < 4; c++) {
      const a = read(x0, y0, c) * (1 - fx) + read(x1, y0, c) * fx;
      const b = read(x0, y1, c) * (1 - fx) + read(x1, y1, c) * fx;
      out[c] = a * (1 - fy) + b * fy;
    }
    return out;
  }

  /** Sample all grass-relevant macro channels at world position (x, z). Positions outside return zero density. */
  sample(x: number, z: number): GrassMacroSample {
    const u = (x - this.config.minX) / this.config.size;
    const v = (z - this.config.minZ) / this.config.size;
    if (u < 0 || u > 1 || v < 0 || v > 1) {
      return { density: 0, heightScale: 0, dryMix: 0, canopyShadow: 1, tintR: 0.4, tintG: 0.42, tintB: 0.26, ao: 1 };
    }
    const g = this.#bilinear(this.#grass, u, v);
    const c = this.#bilinear(this.#color, u, v);
    return {
      density: g[0],
      heightScale: g[1],
      dryMix: g[2],
      canopyShadow: g[3],
      tintR: c[0],
      tintG: c[1],
      tintB: c[2],
      ao: c[3],
    };
  }
}

/** Deterministic 2D hash → [0,1) — same family as the reference shader's Dave-Hoskins hash. */
export function hash2(x: number, z: number, seed = 0): number {
  let h = Math.sin(x * 127.1 + z * 311.7 + seed * 74.7) * 43758.5453123;
  return h - Math.floor(h);
}

/** Blue-noise-ish jittered grid positions inside a cell. count target points, deterministic by (cx, cz, seed). */
export function cellScatterPositions(
  cx: number,
  cz: number,
  cellSize: number,
  count: number,
  seed: number,
): Array<{ x: number; z: number; h1: number; h2: number }> {
  const out: Array<{ x: number; z: number; h1: number; h2: number }> = [];
  // jittered grid: resolution chosen so cells hold `count` samples on average
  const n = Math.max(1, Math.round(Math.sqrt(count)));
  const step = cellSize / n;
  for (let gz = 0; gz < n; gz++) {
    for (let gx = 0; gx < n; gx++) {
      const h1 = hash2(cx * 131 + gx * 17.13, cz * 157 + gz * 11.31, seed);
      const h2 = hash2(cx * 197 + gx * 7.77, cz * 211 + gz * 5.55, seed + 19.19);
      const h3 = hash2(cx * 89 + gx * 3.31, cz * 101 + gz * 13.77, seed + 41.41);
      out.push({
        x: cx * cellSize + (gx + 0.15 + h1 * 0.7) * step,
        z: cz * cellSize + (gz + 0.15 + h2 * 0.7) * step,
        h1: h3,
        h2: hash2(gx * 1.7 + cx, gz * 2.3 + cz, seed + 7.7),
      });
    }
  }
  return out;
}
