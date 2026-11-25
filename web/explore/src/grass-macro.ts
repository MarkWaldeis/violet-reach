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
  #g: [number, number, number, number] = [0, 0, 0, 0];
  #c: [number, number, number, number] = [0, 0, 0, 0];
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

  #bilinearInto(img: ChannelImage, u: number, v: number, out: [number, number, number, number]) {
    const x = u * img.width - 0.5, y = v * img.height - 0.5;
    const fx = x - Math.floor(x), fy = y - Math.floor(y);
    const x0 = Math.min(Math.max(Math.floor(x), 0), img.width - 1), x1 = Math.min(Math.max(Math.floor(x) + 1, 0), img.width - 1);
    const y0 = Math.min(Math.max(Math.floor(y), 0), img.height - 1), y1 = Math.min(Math.max(Math.floor(y) + 1, 0), img.height - 1);
    const stride = img.width * 4;
    const i00 = y0 * stride + x0 * 4, i10 = y0 * stride + x1 * 4;
    const i01 = y1 * stride + x0 * 4, i11 = y1 * stride + x1 * 4;
    for (let c = 0; c < 4; c++) {
      const a = (img.data[i00 + c] / 255) * (1 - fx) + (img.data[i10 + c] / 255) * fx;
      const b = (img.data[i01 + c] / 255) * (1 - fx) + (img.data[i11 + c] / 255) * fx;
      out[c] = a * (1 - fy) + b * fy;
    }
  }

  /**
   * Density-only prefilter. The scatter loop rejects most candidates from this channel alone;
   * reading it separately avoids the much costlier two-texture/8-channel sample for rejects.
   */
  densityAt(x: number, z: number): number {
    const u = (x - this.config.minX) / this.config.size;
    const v = (z - this.config.minZ) / this.config.size;
    if (u < 0 || u > 1 || v < 0 || v > 1) return 0;
    return this.#bilinearChannel(this.#grass, u, v, 0);
  }

  /**
   * Conservative maximum density texel overlapping a world-space rectangle. Grass cells are small
   * (only a handful of macro texels), so scanning the footprint once per cell is much cheaper than
   * blindly thinning hundreds of candidates that can never survive in water/path/rock cells.
   * Bilinear interpolation cannot exceed the maximum source texel, making this a safe upper bound.
   */
  densityCellMax(minX: number, minZ: number, maxX: number, maxZ: number): number {
    const worldMinX = this.config.minX, worldMinZ = this.config.minZ;
    const worldMaxX = worldMinX + this.config.size, worldMaxZ = worldMinZ + this.config.size;
    const x0w = Math.max(minX, worldMinX), x1w = Math.min(maxX, worldMaxX);
    const z0w = Math.max(minZ, worldMinZ), z1w = Math.min(maxZ, worldMaxZ);
    if (x0w >= x1w || z0w >= z1w) return 0;
    const img = this.#grass;
    const x0f = ((x0w - worldMinX) / this.config.size) * img.width - 0.5;
    const x1f = ((x1w - worldMinX) / this.config.size) * img.width - 0.5;
    const y0f = ((z0w - worldMinZ) / this.config.size) * img.height - 0.5;
    const y1f = ((z1w - worldMinZ) / this.config.size) * img.height - 0.5;
    // Expand by one texel: samples near the rectangle edge also read the bilinear support outside it.
    const x0 = Math.max(0, Math.floor(x0f) - 1), x1 = Math.min(img.width - 1, Math.ceil(x1f) + 1);
    const y0 = Math.max(0, Math.floor(y0f) - 1), y1 = Math.min(img.height - 1, Math.ceil(y1f) + 1);
    let max = 0;
    for (let y = y0; y <= y1; y++) {
      const row = y * img.width * 4;
      for (let x = x0; x <= x1; x++) {
        const v = img.data[row + x * 4];
        if (v > max) max = v;
      }
    }
    return max / 255;
  }

  /** Sample all grass-relevant macro channels at world position (x, z). Positions outside return zero density. */
  sample(x: number, z: number): GrassMacroSample {
    return this.sampleInto(x, z, { density: 0, heightScale: 0, dryMix: 0, canopyShadow: 1, tintR: 0.4, tintG: 0.42, tintB: 0.26, ao: 1 });
  }

  /** Allocation-free variant of sample() for hot scatter loops; out is overwritten and returned. */
  sampleInto(x: number, z: number, out: GrassMacroSample): GrassMacroSample {
    const u = (x - this.config.minX) / this.config.size;
    const v = (z - this.config.minZ) / this.config.size;
    if (u < 0 || u > 1 || v < 0 || v > 1) {
      out.density = 0; out.heightScale = 0; out.dryMix = 0; out.canopyShadow = 1;
      out.tintR = 0.4; out.tintG = 0.42; out.tintB = 0.26; out.ao = 1;
      return out;
    }
    this.#bilinearInto(this.#grass, u, v, this.#g);
    this.#bilinearInto(this.#color, u, v, this.#c);
    const g = this.#g;
    const c = this.#c;
    out.density = g[0];
    out.heightScale = g[1];
    out.dryMix = g[2];
    out.canopyShadow = g[3];
    out.tintR = c[0];
    out.tintG = c[1];
    out.tintB = c[2];
    out.ao = c[3];
    return out;
  }

  #bilinearChannel(img: ChannelImage, u: number, v: number, channel: number): number {
    const x = u * img.width - 0.5, y = v * img.height - 0.5;
    const fx = x - Math.floor(x), fy = y - Math.floor(y);
    const x0 = Math.min(Math.max(Math.floor(x), 0), img.width - 1), x1 = Math.min(Math.max(Math.floor(x) + 1, 0), img.width - 1);
    const y0 = Math.min(Math.max(Math.floor(y), 0), img.height - 1), y1 = Math.min(Math.max(Math.floor(y) + 1, 0), img.height - 1);
    const stride = img.width * 4;
    const i00 = y0 * stride + x0 * 4 + channel, i10 = y0 * stride + x1 * 4 + channel;
    const i01 = y1 * stride + x0 * 4 + channel, i11 = y1 * stride + x1 * 4 + channel;
    const a = (img.data[i00] / 255) * (1 - fx) + (img.data[i10] / 255) * fx;
    const b = (img.data[i01] / 255) * (1 - fx) + (img.data[i11] / 255) * fx;
    return a * (1 - fy) + b * fy;
  }
}

/** Deterministic 2D hash → [0,1) — same family as the reference shader's Dave-Hoskins hash. */
export function hash2(x: number, z: number, seed = 0): number {
  let h = Math.sin(x * 127.1 + z * 311.7 + seed * 74.7) * 43758.5453123;
  return h - Math.floor(h);
}

/** Number of jittered-grid candidates produced for a target count (the grid is square, so n²). */
export function cellScatterCapacity(count: number): number {
  const n = Math.max(1, Math.round(Math.sqrt(count)));
  return n * n;
}

/**
 * One deterministic scatter candidate by row-major grid index. This is the indexable form of
 * cellScatterPositions(); incremental cell builders use it to avoid allocating the whole array up-front.
 */
export interface GrassScatterPoint {
  x: number;
  z: number;
  h1: number;
  h2: number;
}

/** Allocation-free variant of cellScatterPositionAt() for hot incremental builders. */
export function cellScatterPositionInto(
  cx: number,
  cz: number,
  cellSize: number,
  count: number,
  seed: number,
  index: number,
  out: GrassScatterPoint,
): GrassScatterPoint {
  const n = Math.max(1, Math.round(Math.sqrt(count)));
  const step = cellSize / n;
  const gz = Math.floor(index / n), gx = index % n;
  const h1 = hash2(cx * 131 + gx * 17.13, cz * 157 + gz * 11.31, seed);
  const h2 = hash2(cx * 197 + gx * 7.77, cz * 211 + gz * 5.55, seed + 19.19);
  const h3 = hash2(cx * 89 + gx * 3.31, cz * 101 + gz * 13.77, seed + 41.41);
  out.x = cx * cellSize + (gx + 0.15 + h1 * 0.7) * step;
  out.z = cz * cellSize + (gz + 0.15 + h2 * 0.7) * step;
  out.h1 = h3;
  out.h2 = hash2(gx * 1.7 + cx, gz * 2.3 + cz, seed + 7.7);
  return out;
}

export function cellScatterPositionAt(
  cx: number,
  cz: number,
  cellSize: number,
  count: number,
  seed: number,
  index: number,
): GrassScatterPoint {
  return cellScatterPositionInto(cx, cz, cellSize, count, seed, index, { x: 0, z: 0, h1: 0, h2: 0 });
}

/**
 * Fixed deterministic permutation of candidate indices. Scanning candidates in this order keeps every
 * prefix spatially uniform inside the cell, so mesh.count can act as a distance-density LOD without
 * rebuilding or re-sorting instances. The full set — and therefore the final full-density meadow — is
 * exactly the same as row-major scanning; only the instance order in the buffers differs.
 */
export function cellScatterOrder(count: number, seed: number): Uint32Array {
  const out = new Uint32Array(count);
  for (let i = 0; i < count; i++) out[i] = i;
  for (let i = count - 1; i > 0; i--) {
    const j = Math.floor(hash2(i, count, seed) * (i + 1));
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
  return out;
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
  const total = cellScatterCapacity(count);
  for (let i = 0; i < total; i++) out.push(cellScatterPositionAt(cx, cz, cellSize, count, seed, i));
  return out;
}
