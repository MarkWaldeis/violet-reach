import {
  ByteType, DepthFormat, DepthStencilFormat, FloatType, HalfFloatType, IntType, LinearMipmapLinearFilter,
  LinearMipmapNearestFilter, NearestMipmapLinearFilter, NearestMipmapNearestFilter, RedFormat, RedIntegerFormat,
  RGBFormat, RGFormat, RGIntegerFormat, ShortType, UnsignedInt248Type, UnsignedIntType, UnsignedShortType,
  type Texture,
} from "three/webgpu";
import type { CameraPose } from "./qa-params.ts";

/** Frames without any load/LOD/pose change before __vr.ready turns true. */
export const STABLE_FRAMES = 30;
export const FRAME_HISTORY = 240;

export interface FrameRecord { now: number; frameMs: number; cpuMs: number; triangles: number; drawCalls: number }
export interface AdapterInfo { vendor: string; architecture: string; device: string; description: string }
export interface TerrainStatus { lods: number[]; total: number; loaded: number; failed: number; pending: number; complete: boolean }
export interface VRStats {
  backend: "WebGPU" | "WebGL2";
  adapter: AdapterInfo | null;
  quality: Record<string, unknown>;
  ready: boolean;
  stableFrames: number;
  frame: number;
  fps: number;
  frameTimes: number[];
  cpuTimes: number[];
  triangles: number;
  drawCalls: number;
  geometries: number;
  textures: number;
  /** Own estimate: Σ width × height × layers × bytes/pixel × mip factor (see README). */
  textureBytes: number;
  /** three.js Info.memory.texturesSize (ignores GPU-generated mip levels). */
  textureBytesThree: number;
  textureSizes: Record<string, { count: number; bytes: number }>;
  camera: CameraPose & { agl: number | null; fov: number; mode: string };
  terrain: TerrainStatus;
  assets: { assets: number; total: number; lods: number[]; visibleChunks: number; chunks: number } | null;
  frozen: boolean;
}
export interface VRProbe {
  readonly ready: boolean;
  stats(): VRStats;
  setCamera(x: number, y: number, z: number, yaw: number, pitch: number, options?: { agl?: boolean }): CameraPose;
  /** Resolves after the next rendered frame. */
  frame(): Promise<FrameRecord>;
  /** Callback run at the start of every animation frame (before update/render) with the rAF time and the previous frame. */
  drive(callback?: ((now: number, last: FrameRecord | undefined) => void) | null): void;
}
declare global { interface Window { __vr?: VRProbe } }

/** Counts consecutive frames with an identical state signature. */
export class FrameStability {
  #signature = "";
  frames = 0;
  observe(signature: string) {
    this.frames = signature === this.#signature ? this.frames + 1 : 0;
    this.#signature = signature;
    return this.frames;
  }
  reset() { this.#signature = ""; this.frames = 0; }
}

export class FrameHistory {
  readonly records: FrameRecord[] = [];
  readonly size: number;
  constructor(size = FRAME_HISTORY) { this.size = size; }
  push(record: FrameRecord) {
    this.records.push(record);
    if (this.records.length > this.size) this.records.shift();
  }
  get last() { return this.records.at(-1); }
  fps() {
    const times = this.records.slice(1).map((r) => r.frameMs);
    const total = times.reduce((a, b) => a + b, 0);
    return total > 0 ? times.length * 1000 / total : 0;
  }
}

const MIPMAP_FILTERS = new Set<number>([NearestMipmapNearestFilter, NearestMipmapLinearFilter, LinearMipmapNearestFilter, LinearMipmapLinearFilter]);

export function textureBytesPerPixel(texture: Pick<Texture, "format" | "type">) {
  const { format, type } = texture;
  if (type === UnsignedInt248Type) return 4;
  const channel = type === ByteType ? 1
    : type === ShortType || type === UnsignedShortType || type === HalfFloatType ? 2
    : type === IntType || type === UnsignedIntType || type === FloatType ? 4 : 1;
  const channels = format === RedFormat || format === RedIntegerFormat || format === DepthFormat || format === DepthStencilFormat ? 1
    : format === RGFormat || format === RGIntegerFormat ? 2 : format === RGBFormat ? 4 : 4; // RGB is padded to RGBA on the GPU
  return channel * channels;
}

/** GPU bytes of one texture: width × height × layers × bytes/pixel × mip factor (4/3 with a mip chain); compressed = sum of mip data. */
export function estimateTextureBytes(texture: Texture) {
  const t = texture as Texture & { isCompressedTexture?: boolean; isCubeTexture?: boolean; isDataArrayTexture?: boolean; isData3DTexture?: boolean };
  const layers = t.isCubeTexture ? 6 : Math.max(1, t.depth || 1);
  if (t.isCompressedTexture) {
    const mips = (t.mipmaps ?? []) as { data?: ArrayBufferView }[];
    return mips.reduce((sum, m) => sum + (m.data?.byteLength ?? 0), 0) * (t.isCubeTexture ? 6 : 1);
  }
  const base = Math.max(1, t.width || 1) * Math.max(1, t.height || 1) * layers * textureBytesPerPixel(t);
  const mipped = (t.mipmaps?.length ?? 0) > 1 || (t.generateMipmaps && MIPMAP_FILTERS.has(t.minFilter));
  return Math.round(base * (mipped ? 4 / 3 : 1));
}

/** Keeps the set of textures the renderer has actually uploaded, by wrapping Info.createTexture/destroyTexture. */
export function trackTextures(info: { createTexture(t: Texture): void; destroyTexture(t: Texture): void }) {
  const live = new Set<Texture>();
  const create = info.createTexture.bind(info), destroy = info.destroyTexture.bind(info);
  info.createTexture = (texture) => { live.add(texture); create(texture); };
  info.destroyTexture = (texture) => { live.delete(texture); destroy(texture); };
  return {
    live,
    bytes: () => [...live].reduce((sum, t) => sum + estimateTextureBytes(t), 0),
    /** Count and bytes per "<width>x<height>" for budget work. */
    summary: () => {
      const out: Record<string, { count: number; bytes: number }> = {};
      for (const t of live) {
        const key = `${t.width || 1}x${t.height || 1}`;
        out[key] ??= { count: 0, bytes: 0 };
        out[key].count++;
        out[key].bytes += estimateTextureBytes(t);
      }
      return out;
    },
  };
}

export async function adapterInfo(backend: unknown): Promise<AdapterInfo | null> {
  const pick = (info: Partial<AdapterInfo> | undefined) => info && {
    vendor: info.vendor ?? "", architecture: info.architecture ?? "", device: info.device ?? "", description: info.description ?? "",
  };
  const device = (backend as { device?: { adapterInfo?: AdapterInfo } } | undefined)?.device;
  if (device?.adapterInfo) return pick(device.adapterInfo)!;
  const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<{ info?: AdapterInfo } | null> } }).gpu;
  if (!device || !gpu) return null;
  return pick((await gpu.requestAdapter())?.info) ?? null;
}
