import {
  ClampToEdgeWrapping, Color, DataArrayTexture, DataTexture, LinearFilter, LinearMipmapLinearFilter,
  LinearSRGBColorSpace, MeshBasicNodeMaterial, MeshPhysicalNodeMaterial, RepeatWrapping, RGBAFormat,
  SRGBColorSpace, Texture, UnsignedByteType, type Node,
} from "three/webgpu";
import {
  abs, cameraPosition, color, cos, dot, float, int, max, mix, mx_noise_float, normalWorldGeometry,
  positionWorld, sin, smoothstep, texture, transformNormalToView, vec2, vec3,
} from "three/tsl";
import { sunDirection } from "./atmosphere.ts";
import { swatch } from "./palette.ts";
import type { SurfaceData } from "./surface-data.ts";

interface GroundManifestEntry {
  tile_m: number;
  files: string[];
}
interface GroundManifest {
  textures: Record<string, GroundManifestEntry>;
}

const LAYER_NAMES = [
  "grass",
  "grass_dry",
  "soil",
  "sand",
  "sand_wet",
  "gravel_path",
  "chalk_rock",
  "strata_rock",
  "moss",
] as const;

const DEFAULT_TILE_M = [3.0, 3.0, 2.5, 3.0, 3.0, 2.0, 4.0, 4.0, 2.0];
const LAYER_COUNT = LAYER_NAMES.length;
const ARRAY_RESOLUTION = 1024;
const MACRO_MIN = -4096;
const MACRO_SIZE = 8192;

// CPU mirrors of the small geological scalars used by the TSL shader below.
// Keeping the thresholds in one place lets the Node tests verify the slope/height-led
// rock model without evaluating WebGPU nodes in a browser.
const FAR_ROCK_SLOPE_START = 0.215; // 1 - normal.y; soft onset near 38 deg terrain slope
const FAR_ROCK_SLOPE_END = 0.345; // fully exposed near 49 deg terrain slope
const FAR_ROCK_ALPINE_SLOPE_START = 0.030; // approx. 14 deg
const FAR_ROCK_ALPINE_SLOPE_END = 0.100; // approx. 26 deg
const FAR_ROCK_ALPINE_HEIGHT_START = 315;
const FAR_ROCK_ALPINE_HEIGHT_END = 400;
const FAR_ROCK_CAP_HEIGHT_START = 420;
const FAR_ROCK_CAP_HEIGHT_END = 490;
const FAR_ROCK_MACRO_BASE = 0.78;
const FAR_ROCK_MACRO_RANGE = 0.44;
const FAR_ROCK_NOISE_JITTER = 0.032;
const FAR_ROCK_GRAIN_JITTER = 0.020;
const FAR_ROCK_HEIGHT_JITTER_M = 24.0;
const STRATA_FOLD_PER_TILE = 0.16;
const STRATA_RELIEF_WEIGHT = 0.75;
const STRATA_SLOPE_PER_TILE = 0.12;
const DISTANT_CLIFF_CALM_START = 280;
const DISTANT_CLIFF_CALM_END = 950;

function clampNumber(value: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, value));
}

function smoothstepNumber(edge0: number, edge1: number, value: number): number {
  const t = clampNumber((value - edge0) / (edge1 - edge0));
  return t * t * (3 - 2 * t);
}

/**
 * Numeric mirror of the distant-rock mask. `slope01` is the shader's `1 - normal.y`
 * measure, not degrees. Macro weight only scales an existing geological exposure;
 * it can never create rock on flat lowland by itself.
 */
export function evaluateFarRockMask(
  heightM: number,
  slope01: number,
  macroHint: number,
  variation = 0.5,
  grain = 0.5,
  broadVariation = variation,
): number {
  const jitter = (variation - 0.5) * FAR_ROCK_NOISE_JITTER + (grain - 0.5) * FAR_ROCK_GRAIN_JITTER;
  const organicHeightM = heightM + (broadVariation - 0.5) * FAR_ROCK_HEIGHT_JITTER_M;
  const slopeExposure = smoothstepNumber(FAR_ROCK_SLOPE_START, FAR_ROCK_SLOPE_END, slope01 + jitter);
  const alpineSlopeExposure = smoothstepNumber(FAR_ROCK_ALPINE_HEIGHT_START, FAR_ROCK_ALPINE_HEIGHT_END, organicHeightM)
    * smoothstepNumber(FAR_ROCK_ALPINE_SLOPE_START, FAR_ROCK_ALPINE_SLOPE_END, slope01 + jitter * 0.5)
    * 0.78;
  const alpineCapExposure = smoothstepNumber(FAR_ROCK_CAP_HEIGHT_START, FAR_ROCK_CAP_HEIGHT_END, organicHeightM) * 0.92;
  const geologicalExposure = Math.max(slopeExposure, alpineSlopeExposure, alpineCapExposure);
  const macroModulation = FAR_ROCK_MACRO_BASE + FAR_ROCK_MACRO_RANGE * clampNumber(macroHint);
  return clampNumber(geologicalExposure * macroModulation);
}

/**
 * Numeric mirror of the terrain-following vertical domain warp used for cliff strata.
 * Positive terrain relief means a local hollow; negative values mean a ridge or shoulder.
 */
export function evaluateWallStrataWarp(
  scaleM: number,
  warpScale: number,
  terrainReliefM: number,
  slope01: number,
  foldNoise01: number,
): number {
  const fold = (foldNoise01 - 0.5) * scaleM * STRATA_FOLD_PER_TILE * warpScale;
  const relief = clampNumber(terrainReliefM, -3.5, 3.5) * STRATA_RELIEF_WEIGHT * warpScale;
  const slopeDrape = slope01 * scaleM * STRATA_SLOPE_PER_TILE * warpScale;
  return fold + relief + slopeDrape;
}

/** Numeric mirror of the distance ramp that calms high-frequency rock striping only in far views. */
export function evaluateDistantCliffCalm(distanceM: number): number {
  return smoothstepNumber(DISTANT_CLIFF_CALM_START, DISTANT_CLIFF_CALM_END, distanceM);
}

function configureArrayTexture(tex: DataArrayTexture, colorSpace: typeof SRGBColorSpace | typeof LinearSRGBColorSpace): DataArrayTexture {
  tex.colorSpace = colorSpace;
  tex.format = RGBAFormat;
  tex.type = UnsignedByteType;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.magFilter = LinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = 4;
  tex.flipY = false;
  tex.needsUpdate = true;
  return tex;
}

function makeFallbackArray(rgba: [number, number, number, number], colorSpace: typeof SRGBColorSpace | typeof LinearSRGBColorSpace): DataArrayTexture {
  const buf = new Uint8Array(LAYER_COUNT * 4);
  for (let i = 0; i < LAYER_COUNT; i++) buf.set(rgba, i * 4);
  return configureArrayTexture(new DataArrayTexture(buf, 1, 1, LAYER_COUNT), colorSpace);
}

function makeFallback2D(rgba: [number, number, number, number], colorSpace: typeof SRGBColorSpace | typeof LinearSRGBColorSpace): DataTexture {
  const tex = new DataTexture(new Uint8Array(rgba), 1, 1, RGBAFormat, UnsignedByteType);
  tex.colorSpace = colorSpace;
  tex.wrapS = ClampToEdgeWrapping;
  tex.wrapT = ClampToEdgeWrapping;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.flipY = false;
  tex.premultiplyAlpha = false;
  tex.needsUpdate = true;
  return tex;
}

let albedoArray = makeFallbackArray([112, 118, 72, 255], SRGBColorSpace);
let normalArray = makeFallbackArray([128, 128, 255, 255], LinearSRGBColorSpace);
let orhArray = makeFallbackArray([255, 224, 128, 255], LinearSRGBColorSpace);

let macroColorAoTex: Texture = makeFallback2D([112, 118, 72, 255], SRGBColorSpace);
let macroWeightsATex: Texture = makeFallback2D([255, 0, 0, 0], LinearSRGBColorSpace);
let macroWeightsBTex: Texture = makeFallback2D([0, 0, 0, 0], LinearSRGBColorSpace);

const layerTileM = [...DEFAULT_TILE_M];
let groundTexturesPromise: Promise<void> | null = null;

async function fetchBlobWithSignal(url: URL, signal: AbortSignal): Promise<Blob> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`${url.pathname}: HTTP ${res.status}`);
  return res.blob();
}

async function decodeLayerIntoSlice(
  url: URL,
  size: number,
  dst: Uint8Array,
  sliceIndex: number,
  gl: WebGL2RenderingContext | null,
  ctx2d: CanvasRenderingContext2D | null,
  glTex: WebGLTexture | null,
  glFbo: WebGLFramebuffer | null,
  signal: AbortSignal,
): Promise<void> {
  const blob = await fetchBlobWithSignal(url, signal);
  const bmp = await createImageBitmap(blob, {
    resizeWidth: size,
    resizeHeight: size,
    resizeQuality: "high",
    premultiplyAlpha: "none",
    colorSpaceConversion: "none",
  });
  const stride = size * size * 4;
  const view = dst.subarray(sliceIndex * stride, (sliceIndex + 1) * stride);
  try {
    if (gl && glTex && glFbo) {
      gl.bindTexture(gl.TEXTURE_2D, glTex);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, 0);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, size, size, 0, gl.RGBA, gl.UNSIGNED_BYTE, bmp);
      gl.bindFramebuffer(gl.FRAMEBUFFER, glFbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, glTex, 0);
      gl.readPixels(0, 0, size, size, gl.RGBA, gl.UNSIGNED_BYTE, view);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      return;
    }
    if (ctx2d) {
      ctx2d.clearRect(0, 0, size, size);
      ctx2d.drawImage(bmp, 0, 0, size, size);
      view.set(ctx2d.getImageData(0, 0, size, size).data);
    }
  } finally {
    bmp.close?.();
  }
}

async function loadMacroBitmapTexture(
  file: string,
  colorSpace: typeof SRGBColorSpace | typeof LinearSRGBColorSpace,
  signal: AbortSignal,
): Promise<Texture> {
  const url = new URL(`./ground/${file}`, window.location.href);
  const blob = await fetchBlobWithSignal(url, signal);
  const bmp = await createImageBitmap(blob, {
    premultiplyAlpha: "none",
    colorSpaceConversion: "none",
  });
  const tex = new Texture(bmp);
  tex.colorSpace = colorSpace;
  tex.wrapS = ClampToEdgeWrapping;
  tex.wrapT = ClampToEdgeWrapping;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.magFilter = LinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = 4;
  tex.flipY = false;
  tex.premultiplyAlpha = false;
  tex.needsUpdate = true;
  return tex;
}

/**
 * Loads the 9 1k PBR ground layers into 3 GPU DataArrayTextures plus the 3 world MacroMap textures.
 * Must be awaited before constructing `terrainMaterial()` when running in the browser; resolves immediately in Node tests.
 */
export function waitForGroundTextures(timeoutMs = 8000): Promise<void> {
  if (groundTexturesPromise) return groundTexturesPromise;
  if (typeof window === "undefined" || typeof document === "undefined" || typeof fetch !== "function" || typeof createImageBitmap !== "function") {
    groundTexturesPromise = Promise.resolve();
    return groundTexturesPromise;
  }

  groundTexturesPromise = (async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const canvas = document.createElement("canvas");
    canvas.width = ARRAY_RESOLUTION;
    canvas.height = ARRAY_RESOLUTION;
    const gl = canvas.getContext("webgl2");
    const glTex = gl?.createTexture() ?? null;
    const glFbo = gl?.createFramebuffer() ?? null;
    const ctx2d = gl ? null : canvas.getContext("2d", { willReadFrequently: true });

    try {
      const manifestRes = await fetch(new URL("./ground/manifest.json", window.location.href), { signal: controller.signal });
      if (manifestRes.ok) {
        const manifest = (await manifestRes.json()) as GroundManifest;
        for (let i = 0; i < LAYER_COUNT; i++) {
          const entry = manifest.textures?.[LAYER_NAMES[i]];
          if (entry && Number.isFinite(entry.tile_m) && entry.tile_m > 0) layerTileM[i] = entry.tile_m;
        }
      }

      const sliceBytes = ARRAY_RESOLUTION * ARRAY_RESOLUTION * 4;
      const albedoBuf = new Uint8Array(sliceBytes * LAYER_COUNT);
      const normalBuf = new Uint8Array(sliceBytes * LAYER_COUNT);
      const orhBuf = new Uint8Array(sliceBytes * LAYER_COUNT);

      await Promise.all([
        (async () => {
          for (let i = 0; i < LAYER_COUNT; i++) {
            const name = LAYER_NAMES[i];
            const aUrl = new URL(`./ground/1k/${name}_albedo.webp`, window.location.href);
            const nUrl = new URL(`./ground/1k/${name}_normal.webp`, window.location.href);
            const oUrl = new URL(`./ground/1k/${name}_orh.webp`, window.location.href);
            await Promise.all([
              decodeLayerIntoSlice(aUrl, ARRAY_RESOLUTION, albedoBuf, i, gl, ctx2d, glTex, glFbo, controller.signal),
              decodeLayerIntoSlice(nUrl, ARRAY_RESOLUTION, normalBuf, i, gl, ctx2d, glTex, glFbo, controller.signal),
              decodeLayerIntoSlice(oUrl, ARRAY_RESOLUTION, orhBuf, i, gl, ctx2d, glTex, glFbo, controller.signal),
            ]);
          }
        })(),
        (async () => {
          const [mColorAo, mWA, mWB] = await Promise.all([
            loadMacroBitmapTexture("macro_color_ao.webp", SRGBColorSpace, controller.signal),
            loadMacroBitmapTexture("macro_weights_a.webp", LinearSRGBColorSpace, controller.signal),
            loadMacroBitmapTexture("macro_weights_b.webp", LinearSRGBColorSpace, controller.signal),
          ]);
          macroColorAoTex.dispose();
          macroWeightsATex.dispose();
          macroWeightsBTex.dispose();
          macroColorAoTex = mColorAo;
          macroWeightsATex = mWA;
          macroWeightsBTex = mWB;
        })(),
      ]);

      albedoArray.dispose();
      normalArray.dispose();
      orhArray.dispose();
      albedoArray = configureArrayTexture(new DataArrayTexture(albedoBuf, ARRAY_RESOLUTION, ARRAY_RESOLUTION, LAYER_COUNT), SRGBColorSpace);
      normalArray = configureArrayTexture(new DataArrayTexture(normalBuf, ARRAY_RESOLUTION, ARRAY_RESOLUTION, LAYER_COUNT), LinearSRGBColorSpace);
      orhArray = configureArrayTexture(new DataArrayTexture(orhBuf, ARRAY_RESOLUTION, ARRAY_RESOLUTION, LAYER_COUNT), LinearSRGBColorSpace);
    } catch {
      // Fallback 1x1x9 textures stay valid if ground textures are missing or aborted.
    } finally {
      clearTimeout(timer);
      if (gl && glFbo) gl.deleteFramebuffer(glFbo);
      if (gl && glTex) gl.deleteTexture(glTex);
    }
  })();

  return groundTexturesPromise;
}

export function terrainMaterial(surface?: SurfaceData) {
  const material = new MeshPhysicalNodeMaterial({ roughness: 0.94, envMapIntensity: 0.55 });
  const p = positionWorld;
  const planar = p.xz;
  const field = surface?.sample(planar);
  const geomNormal = normalWorldGeometry.normalize();
  let smoothNormal: Node<"vec3"> = geomNormal;
  let hollow: Node<"float"> = float(0);
  let terrainRelief: Node<"float"> = float(0);
  let damp: Node<"float"> = float(0);
  let shoreDampMul: Node<"float"> = float(1);

  let surfaceBorder: Node<"float"> = float(0);

  if (surface && field) {
    const dx = surface.sample(planar.add(vec2(3, 0))).r.sub(surface.sample(planar.sub(vec2(3, 0))).r).div(6);
    const dz = surface.sample(planar.add(vec2(0, 3))).r.sub(surface.sample(planar.sub(vec2(0, 3))).r).div(6);
    const uv = planar.sub(surface.origin).div(surface.size);
    surfaceBorder = smoothstep(0, 0.02, uv.x)
      .mul(smoothstep(0, 0.02, uv.y))
      .mul(smoothstep(0, 0.02, uv.x.oneMinus()))
      .mul(smoothstep(0, 0.02, uv.y.oneMinus()));
    smoothNormal = mix(geomNormal, vec3(dx.negate(), 1, dz.negate()).normalize(), smoothstep(40, 100, field.b).oneMinus().mul(surfaceBorder));
    const neighbours = surface.sample(planar.add(vec2(14, 0))).r
      .add(surface.sample(planar.sub(vec2(14, 0))).r)
      .add(surface.sample(planar.add(vec2(0, 14))).r)
      .add(surface.sample(planar.sub(vec2(0, 14))).r)
      .mul(0.25);
    const signedRelief = neighbours.sub(field.r);
    terrainRelief = signedRelief.clamp(-3.5, 3.5).mul(surfaceBorder);
    hollow = smoothstep(0.15, 1.7, signedRelief).mul(surfaceBorder);
  }

  const macroUv = planar.sub(vec2(MACRO_MIN, MACRO_MIN)).div(MACRO_SIZE).clamp(0, 1);
  const macroColorAo = texture(macroColorAoTex, macroUv);
  const macroWA = texture(macroWeightsATex, macroUv);
  const macroWB = texture(macroWeightsBTex, macroUv);

  const dist = p.sub(cameraPosition).length();
  const microAoFade = smoothstep(18, 95, dist).oneMinus();
  const microNormalFade = smoothstep(8, 42, dist).oneMinus();
  const closeTileFade = smoothstep(12.0, 48.0, dist);
  const midNormalFade = smoothstep(22, 88, dist).mul(smoothstep(380, 1300, dist).oneMinus().mul(0.65).add(0.35));
  const cliffNormalFade = smoothstep(60, 1200, dist).oneMinus().mul(0.60).add(0.40);

  // Lean 4-noise budget (3 planar + 1 cliff strata, matching p2-r14 ALU) with pure-trig domain warp (+-48 m):
  // breaks smooth velvet hills into sweeping 140m/55m/18m islands without circular polka-dots or extra noise cost.
  const warpX = sin(planar.y.mul(0.0083).add(planar.x.mul(0.0031)).add(1.2)).mul(32.0)
    .add(cos(planar.x.mul(0.0157).sub(planar.y.mul(0.0119))).mul(16.0));
  const warpZ = cos(planar.x.mul(0.0079).sub(planar.y.mul(0.0037)).add(2.4)).mul(32.0)
    .add(sin(planar.y.mul(0.0149).add(planar.x.mul(0.0127))).mul(16.0));
  const warpedMacro = planar.add(vec2(warpX, warpZ));

  const sweepA = sin(warpedMacro.x.mul(0.0074).add(warpedMacro.y.mul(0.0049)).add(0.8)).mul(0.5).add(0.5);
  const sweepB = cos(warpedMacro.x.mul(0.0043).sub(warpedMacro.y.mul(0.0081)).add(2.1)).mul(0.5).add(0.5);
  const macro140 = sweepA.mul(0.55).add(sweepB.mul(0.45));
  const macro55 = mx_noise_float(warpedMacro.mul(0.0165).add(vec2(-41.0, 67.0))).mul(0.5).add(0.5);
  const macro18 = mx_noise_float(warpedMacro.mul(0.054).add(vec2(-29.0, 83.0))).mul(0.5).add(0.5);
  const earthWaveA = sin(warpedMacro.x.mul(0.021).sub(warpedMacro.y.mul(0.015)).add(3.7)).mul(0.5).add(0.5);
  const earthWaveB = cos(warpedMacro.x.mul(0.013).add(warpedMacro.y.mul(0.024)).add(1.1)).mul(0.5).add(0.5);
  const earthField = earthWaveA.mul(0.42).add(earthWaveB.mul(0.30)).add(macro18.mul(0.28));
  const smallNoise = mx_noise_float(planar.mul(0.14).add(vec2(-19.0, 58.0))).mul(0.5).add(0.5);
  const antiMix = macro55.mul(0.28).add(0.34);
  const coveV1 = sin(planar.x.sub(560).mul(0.009).add(planar.y.sub(1520).mul(0.005)).add(1.57)).mul(0.5).add(0.5);
  const coveV2 = cos(planar.x.sub(560).mul(0.007).sub(planar.y.sub(1520).mul(0.008))).mul(0.5).add(0.5);
  const coveShape = coveV1.mul(0.55).add(coveV2.mul(0.45));
  if (surface && field) {
    damp = smoothstep(2, 24, p.y.sub(field.g).add(macro55.sub(0.5).mul(10.0)).add(macro18.sub(0.5).mul(4.0)))
      .oneMinus()
      .mul(smoothstep(14, 95, field.b).oneMinus())
      .mul(surfaceBorder);
  }

  // Gently warped, 37-deg rotated non-integer-ratio macro UV (~11.3 m on 3 m grass) so close tiles vanish over 12..48 m
  const uvBWarp = vec2(
    sin(planar.y.mul(0.031).add(planar.x.mul(0.017)).add(0.9)),
    cos(planar.x.mul(0.029).sub(planar.y.mul(0.019)).add(2.1)),
  ).mul(3.6);
  const uvBWarped = planar.add(uvBWarp);
  const uvBBase = vec2(
    uvBWarped.x.mul(0.7986).add(uvBWarped.y.mul(0.6018)),
    uvBWarped.y.mul(0.7986).sub(uvBWarped.x.mul(0.6018)),
  ).add(vec2(17.3, 9.2));

  const samplePlanar = (layerIndex: number, mode: "single" | "dual" | "aerial") => {
    const idx = int(layerIndex);
    const invTile = 1 / layerTileM[layerIndex];
    const uvA = planar.mul(invTile);
    const aAlb = texture(albedoArray, uvA).depth(idx).rgb;
    const aNrm = texture(normalArray, uvA).depth(idx).xy.mul(2).sub(1);
    const aOrh = texture(orhArray, uvA).depth(idx).rgb;
    if (mode === "single") return { albedo: aAlb, reliefXZ: aNrm, midReliefXZ: aNrm.mul(0), orh: aOrh, macroGrain: float(0.5) };

    const uvB = uvBBase.mul(invTile / 3.77);
    const bAlb = texture(albedoArray, uvB).depth(idx).rgb;
    const bMix = mix(antiMix, float(1.0), closeTileFade);
    const closeAlb = mix(aAlb, bAlb, bMix);
    if (mode === "dual") return { albedo: closeAlb, reliefXZ: aNrm, midReliefXZ: aNrm.mul(0), orh: aOrh, macroGrain: float(0.5) };

    // Domain-warped 36m organic soil clump grain for dappled ref_09 hills across mid/aerial distances
    const uvM = warpedMacro.mul(1 / 36.0);
    const mSoilAlb = texture(albedoArray, uvM).depth(int(2)).rgb;
    const mLuma = mSoilAlb.r.mul(0.40).add(mSoilAlb.g.mul(0.40)).add(mSoilAlb.b.mul(0.20));
    const mContrast = smoothstep(0.18, 0.70, mLuma);
    const mNrm = texture(normalArray, uvM).depth(int(2)).xy.mul(2).sub(1);
    return {
      albedo: closeAlb,
      reliefXZ: aNrm,
      midReliefXZ: mNrm,
      orh: aOrh,
      macroGrain: mContrast,
    };
  };

  // Helper: calm Rec.709 desaturation in linear RGB (keeps olive greens within STYLE.md & ref_09/12/13/14)
  const lumaWeights = vec3(0.2126, 0.7152, 0.0722);
  const desatLinear = (rgb: Node<"vec3">, amount: number) => {
    const l = dot(rgb, lumaWeights);
    return mix(rgb, vec3(l, l, l), float(amount));
  };

  // Coherent organic meadow shading (softened close-up stipple, rolling ref_09 hill variation)
  const clumpDetail = smoothstep(0.20, 0.80, macro18.mul(0.74).add(smallNoise.mul(0.26)));
  const turfShade = clumpDetail.mul(0.12).add(macro55.mul(0.08)).add(0.90);
  const lGrassRaw = samplePlanar(0, "aerial");
  const macroGrainField = mix(float(0.5), lGrassRaw.macroGrain, smoothstep(14, 72, dist));
  const meadowMottle = mix(vec3(0.88, 0.90, 0.87), vec3(1.12, 1.11, 1.06), macroGrainField);

  // Warm sunlit olive grass_green (#696F44, Hue ~76-84 deg across sun & shade, calm S <= 0.40)
  const grassBalanced = desatLinear(lGrassRaw.albedo.mul(vec3(0.98, 1.08, 0.86)), 0.22);
  const lGrass = { ...lGrassRaw, albedo: grassBalanced.mul(turfShade).mul(meadowMottle) };

  // Warm sunlit golden-straw dry-grass sweeps (harmonious with olive grass, no chalky grey washout)
  const lDryRaw = samplePlanar(1, "dual");
  const dryBalanced = desatLinear(lDryRaw.albedo.mul(vec3(1.16, 1.20, 1.16)), 0.25).mul(1.28);
  const lDry = { ...lDryRaw, albedo: dryBalanced.mul(turfShade).mul(meadowMottle) };

  // Exposed warm earthy soil (#665548) connecting vegetation cushions & slope shoulders
  const lSoilRaw = samplePlanar(2, "single");
  const lSoil = { ...lSoilRaw, albedo: desatLinear(lSoilRaw.albedo.mul(vec3(0.82, 0.80, 0.82)), 0.14) };

  // Matte warm coastal sand with multi-scale pebble/drift variation and softened ripple relief
  const lSandRaw = samplePlanar(3, "dual");
  const lGravelRaw = samplePlanar(5, "single");
  const trailPebbleMix = smoothstep(0.24, 0.80, macro18.mul(0.50).add(smallNoise.mul(0.50))).mul(0.45).add(0.25);
  const lGravel = {
    ...lGravelRaw,
    albedo: mix(
      lSoilRaw.albedo.mul(vec3(0.86, 0.82, 0.78)),
      lGravelRaw.albedo.mul(vec3(0.56, 0.54, 0.50)),
      trailPebbleMix,
    ),
  };
  const sandPebble = smoothstep(0.22, 0.80, smallNoise.mul(0.52).add(macro18.mul(0.48))).mul(0.52).add(0.16);
  const sandDrift = smoothstep(0.26, 0.78, macro55.mul(0.50).add(macro18.mul(0.50))).mul(0.32);
  const sandTone = macro55.mul(0.12).add(macro18.mul(0.12)).add(smallNoise.mul(0.08)).add(0.84);
  const sandBase = mix(lSandRaw.albedo.mul(vec3(0.95, 0.89, 0.76)), lGravelRaw.albedo.mul(vec3(0.79, 0.74, 0.63)), sandPebble);
  const lSand = {
    ...lSandRaw,
    albedo: mix(sandBase, lSoil.albedo.mul(vec3(1.18, 1.12, 1.00)), sandDrift).mul(sandTone),
    reliefXZ: mix(lSandRaw.reliefXZ.mul(0.24), lGravelRaw.reliefXZ.mul(0.42), sandPebble.mul(0.70)),
  };
  const lSandWetRaw = samplePlanar(4, "single");
  const lSandWet = {
    ...lSandWetRaw,
    albedo: lSandWetRaw.albedo.mul(vec3(0.46, 0.41, 0.34)),
    reliefXZ: lSandWetRaw.reliefXZ.mul(0.32),
  };
  // Dual-tiled warm shadowed olive-moss (eliminates 2 m checkerboard grid & cold pine-green blotches)
  const lMossRaw = samplePlanar(8, "dual");
  const mossBalanced = desatLinear(lMossRaw.albedo.mul(vec3(1.18, 1.06, 0.82)), 0.20).mul(1.22);
  const lMoss = { ...lMossRaw, albedo: mossBalanced.mul(meadowMottle) };

  // Continuous dominant-axis wall projection with a noise-broken transition. The wider blend avoids
  // knife-edge axis flips on diagonal spurs, while pure X/Z faces still keep their correct projection.
  const geomSlope = geomNormal.y.abs().oneMinus();
  const hAx = abs(geomNormal.x);
  const hAz = abs(geomNormal.z);
  const axisBias = hAx.sub(hAz).add(macro18.sub(0.5).mul(0.075));
  const wx = smoothstep(-0.12, 0.12, axisBias);
  const wz = wx.oneMinus();

  // Reuse the existing organic noise fields as a domain warp: sediment bands bend around local
  // relief and changes in steepness instead of running as world-horizontal/vertical texture columns.
  const wallFoldNoise = macro55.mul(0.70).add(macro18.mul(0.30));
  const strataWarpForScale = (scaleM: number, warpScale: number) =>
    wallFoldNoise.sub(0.5).mul(scaleM * STRATA_FOLD_PER_TILE * warpScale)
      .add(terrainRelief.mul(STRATA_RELIEF_WEIGHT * warpScale))
      .add(geomSlope.mul(scaleM * STRATA_SLOPE_PER_TILE * warpScale));

  const sampleWallCliff = (layerIndex: number, scaleM: number, includeOrh: boolean, warpScale: number) => {
    const idx = int(layerIndex);
    const inv = 1 / scaleM;
    // The broad trig warp already present for the macro field supplies a very low-frequency
    // horizontal wander. A bounded height-sine adds only ~1.8% tile-scale horizontal phase shift, enough to keep
    // vertical cracks/columns from reading as perfectly straight world-axis stripes.
    const horizontalWarp = warpX.add(warpZ).mul(scaleM / 5600)
      .add(smallNoise.sub(0.5).mul(0.18 + Math.min(scaleM * 0.006, 0.30)))
      .add(sin(p.y.mul(0.31).add(macro55.mul(4.2))).mul(scaleM * 0.018));
    const verticalWarp = strataWarpForScale(scaleM, warpScale);
    const uvX = vec2(p.z.add(horizontalWarp).mul(inv), p.y.negate().add(verticalWarp).mul(inv));
    const uvZ = vec2(p.x.add(horizontalWarp).mul(inv), p.y.negate().add(verticalWarp).mul(inv));

    const alb = texture(albedoArray, uvX).depth(idx).rgb.mul(wx)
      .add(texture(albedoArray, uvZ).depth(idx).rgb.mul(wz));

    const nX = texture(normalArray, uvX).depth(idx).xy.mul(2).sub(1);
    const nZ = texture(normalArray, uvZ).depth(idx).xy.mul(2).sub(1);
    const deltaWorld = vec3(0, nX.y.negate(), nX.x).mul(wx)
      .add(vec3(nZ.x, nZ.y.negate(), 0).mul(wz));

    const orh = includeOrh
      ? texture(orhArray, uvX).depth(idx).rgb.mul(wx).add(texture(orhArray, uvZ).depth(idx).rgb.mul(wz))
      : vec3(1, 0.84, 0.5);
    return { albedo: alb, deltaWorld, orh };
  };

  const cChalkFine = sampleWallCliff(6, 9.5, true, 0.45);
  const cStrataMacro = sampleWallCliff(7, 64.0, false, 1.0);

  // Genuine steep cliffs near; distant exposure is led by terrain slope/elevation. MacroWB only
  // scales that geological exposure (0.78..1.22x), so low flatland can never turn into rock
  // merely because a blurred macro weight or strata fraction is nonzero there.
  const farLod = smoothstep(70, 220, dist);
  const nearRockBreakup = cChalkFine.orh.b.sub(0.5).mul(0.085).add(smallNoise.sub(0.5).mul(0.042)).add(macro18.sub(0.5).mul(0.038));
  const nearCliff = smoothstep(0.228, 0.278, geomSlope.add(nearRockBreakup.mul(1.35)));
  const screeJitter = smallNoise.sub(0.5).mul(0.048).add(macro18.sub(0.5).mul(0.036));
  const screeBand = smoothstep(0.135, 0.245, geomSlope.add(screeJitter)).mul(nearCliff.oneMinus()).mul(farLod.oneMinus());
  const farRockHint = macroWB.b.add(macroWB.a).clamp(0, 1);
  const farRockJitter = macro18.sub(0.5).mul(FAR_ROCK_NOISE_JITTER).add(cChalkFine.orh.b.sub(0.5).mul(FAR_ROCK_GRAIN_JITTER));
  const organicRockHeight = p.y.add(macro55.sub(0.5).mul(FAR_ROCK_HEIGHT_JITTER_M));
  const slopeExposure = smoothstep(FAR_ROCK_SLOPE_START, FAR_ROCK_SLOPE_END, geomSlope.add(farRockJitter));
  const alpineSlopeExposure = smoothstep(FAR_ROCK_ALPINE_HEIGHT_START, FAR_ROCK_ALPINE_HEIGHT_END, organicRockHeight)
    .mul(smoothstep(FAR_ROCK_ALPINE_SLOPE_START, FAR_ROCK_ALPINE_SLOPE_END, geomSlope.add(farRockJitter.mul(0.5))))
    .mul(0.78);
  const alpineCapExposure = smoothstep(FAR_ROCK_CAP_HEIGHT_START, FAR_ROCK_CAP_HEIGHT_END, organicRockHeight).mul(0.92);
  const geologicalRock = slopeExposure.max(alpineSlopeExposure).max(alpineCapExposure);
  const macroRockModulation = farRockHint.mul(FAR_ROCK_MACRO_RANGE).add(FAR_ROCK_MACRO_BASE);
  const farCliff = geologicalRock.mul(macroRockModulation).clamp(0, 1);
  const cliffMask = mix(nearCliff, farCliff, farLod);
  const normal = mix(smoothNormal, geomNormal, cliffMask.mul(farLod.oneMinus())).normalize();
  const slope = normal.y.abs().oneMinus();
  const north = normal.z.negate().max(0);

  // Rolling, sweeping multi-scale hill transitions (140m / 55m / 18m) inspired by ref_09_crescent_grass.jpg:
  // wide smoothsteps prevent sharp dark cow-spots while keeping warm sunlit olive, pale dry-grass & earthy soil reads.
  const ridgeExposure = smoothstep(0.03, 0.18, slope).mul(0.22).add(smoothstep(18, 96, p.y.sub(180)).mul(0.16));
  const drySignal = macro140.mul(0.45).add(macro55.mul(0.38)).add(macro18.mul(0.17))
    .add(ridgeExposure)
    .sub(hollow.mul(0.32))
    .sub(damp.mul(0.16));
  const dryIsland = smoothstep(0.14, 0.86, drySignal);

  const dampMod = damp.mul(macro18.mul(0.55).add(0.45));
  const mossSignal = macro140.oneMinus().mul(0.34)
    .add(earthField.oneMinus().mul(0.30))
    .add(macro18.oneMinus().mul(0.14))
    .add(hollow.mul(0.42))
    .add(north.mul(0.26))
    .add(dampMod.mul(0.22))
    .sub(dryIsland.mul(0.32));
  const mossIsland = smoothstep(0.24, 0.90, mossSignal);

  const soilPatch = smoothstep(0.38, 0.88, earthField.mul(0.50).add(macro18.mul(0.32)).add(macroGrainField.mul(0.18)));
  const slopeSoil = smoothstep(0.085, 0.22, geomSlope).mul(0.46);

  const screeVegFade = screeBand.mul(0.55).oneMinus();
  let wDry: Node<"float"> = macroWA.g.mul(0.35).add(dryIsland.mul(0.92)).mul(screeVegFade);
  let wMoss: Node<"float"> = macroWA.a.mul(0.30).add(mossIsland.mul(0.62)).mul(screeVegFade);
  let wSoil: Node<"float"> = macroWA.b.mul(0.26)
    .add(soilPatch.mul(0.48))
    .add(slopeSoil)
    .add(screeBand.mul(0.66));
  const islandSuppression = dryIsland.mul(0.52).max(mossIsland.mul(0.42)).max(soilPatch.mul(0.36)).clamp(0, 0.64).oneMinus();
  let wGrass: Node<"float"> = macroWA.r.max(0.66).mul(islandSuppression).max(0.24).mul(screeVegFade);
  let wSand: Node<"float"> = float(0);
  let wWet: Node<"float"> = float(0);
  let wPath: Node<"float"> = screeBand.mul(0.42);

  if (surface && field) {
    const uv = planar.sub(surface.origin).div(surface.size);
    const inside = float(uv.x.greaterThanEqual(0).and(uv.y.greaterThanEqual(0)).and(uv.x.lessThanEqual(1)).and(uv.y.lessThanEqual(1)));
    const aboveWater = p.y.sub(field.g);

    const isLakeShore = smoothstep(14.0, 48.0, field.a).oneMinus();

    // Tight exclusion strictly around bridge_arch_a (476, 1498, r=14..24 m) so gate_white_a (522, 1510) & G5 (556, 1536) stay 100% sandy
    const bridgeDist = planar.sub(vec2(476.0, 1498.0)).length().add(macro18.sub(0.5).mul(5.0));
    const notBridgePeninsula = smoothstep(14.0, 24.0, bridgeDist);

    // Genuine sandy coves: full north bay sunlit beach (G5/gate_white_a/F2) + ~35-45% of gentle lake bays (pocketCoves).
    // Steep banks and headlands still drop cleanly to 0 so mechanical 360-deg contour ribbons never return.
    const flatBeachMask = smoothstep(0.018, 0.088, slope).oneMinus();
    const northBayDist = planar.sub(vec2(582.0, 1532.0)).div(vec2(150.0, 110.0)).length();
    const northBayCove = smoothstep(1.20, 0.65, northBayDist.add(macro55.sub(0.5).mul(0.20)));
    const pocketCove = smoothstep(0.46, 0.78, coveShape.mul(0.55).add(macro140.mul(0.28)).add(macro55.mul(0.17)));
    const coveWidth = northBayCove.max(pocketCove.mul(0.85)).mul(notBridgePeninsula);
    const hasCove = smoothstep(0.06, 0.28, coveWidth);

    // Strict height-gated immediate waterline wetness (aboveWater < 0.105 m with subtle organic jitter).
    // Because lake_outline(inset=18) shifts field.b by -15 m on dry lake shores (gate_white_a sits at
    // aboveWater +0.147 m, field.b = -5.14 m), wetness MUST be gated on aboveWater so dry sand around
    // gate_white_a and flat +0.147 m bridge benches stay 100% dry and matte.
    const wetHeightJitter = smallNoise.sub(0.5).mul(0.032).add(macro18.sub(0.5).mul(0.022));
    const wetEdge = smoothstep(-0.02, 0.105, aboveWater.add(wetHeightJitter)).oneMinus();
    const lakeWaterGuard = smoothstep(-2.0, 8.0, field.b).oneMinus();
    const riverWaterGuard = smoothstep(0.4, 3.5, field.b).oneMinus();
    const waterGuard = mix(riverWaterGuard, lakeWaterGuard, isLakeShore);
    const shoreWetBreakup = smoothstep(0.26, 0.76, coveWidth.mul(1.15).add(macro18.mul(0.46)).add(earthField.mul(0.28)));

    const coveWetSand = wetEdge.mul(waterGuard).mul(isLakeShore).mul(hasCove).mul(inside);
    const nonCoveDampEdge = wetEdge.mul(waterGuard).mul(shoreWetBreakup).mul(coveWetSand.oneMinus()).mul(inside);

    // Organic undulating beach height inside genuine sandy coves (full sunlit dry sand across G5 up to ~1.35 m)
    const beachHeightUndulation = mix(float(1.15), float(1.70), macro55.mul(0.60).add(macro18.mul(0.40)));
    const maxBeachHeight = isLakeShore.mul(flatBeachMask).mul(coveWidth).mul(beachHeightUndulation);
    const beachEdgeJitter = macro55.sub(0.5).mul(0.30).add(macro18.sub(0.5).mul(0.28)).add(smallNoise.sub(0.5).mul(0.16));
    const shoreAbove = smoothstep(maxBeachHeight.mul(0.10), maxBeachHeight.max(0.001), aboveWater.max(0).add(beachEdgeJitter)).oneMinus();
    const inlandCoveGuard = smoothstep(8.0, 22.0, field.b).oneMinus();
    const shore = shoreAbove.mul(isLakeShore).mul(flatBeachMask).mul(hasCove).mul(inlandCoveGuard).mul(inside);
    const liveSand = shore.mul(coveWetSand.oneMinus());

    // Dark matte-damp shore rim strictly at the immediate 0..0.105 m waterline (zero gloss patch in dry sand)
    const dampZone = wetEdge.mul(waterGuard).mul(coveWetSand.max(nonCoveDampEdge.mul(0.75))).mul(inside);
    const submergedDark = smoothstep(-1.10, 0.05, aboveWater).mul(0.24).add(0.76);
    shoreDampMul = mix(float(1), float(0.62), dampZone.mul(0.90)).mul(mix(float(1), submergedDark, inside));

    // Break upper cove beach margins (> 0.72 m) naturally with coastal dry-grass & earth tufts
    const upperBeachFringe = smoothstep(0.72, 1.55, aboveWater)
      .mul(smoothstep(0.36, 0.80, macro18.mul(0.55).add(smallNoise.mul(0.45))));
    const sandClean = liveSand.mul(upperBeachFringe.mul(0.80).oneMinus());
    wSand = sandClean;
    wWet = coveWetSand;
    const clearVeg = sandClean.max(coveWetSand).oneMinus();
    wGrass = wGrass.mul(clearVeg);
    wDry = wDry.mul(clearVeg).add(shore.mul(0.44).mul(upperBeachFringe));
    wSoil = wSoil
      .add(shore.mul(0.22).mul(clearVeg.max(upperBeachFringe.mul(0.5))))
      .add(nonCoveDampEdge.mul(0.55));
    wMoss = wMoss.mul(clearVeg).add(nonCoveDampEdge.mul(0.22));

    // Organic patchy earthy/mossy riverbanks (no uniform light contour ribbons along rivers in H1/F1)
    const bankBreakup = smoothstep(0.26, 0.78, earthField.mul(0.52).add(macro18.mul(0.48)));
    const bankReach = mix(float(1.2), float(4.2), bankBreakup);
    const bankHeight = mix(float(0.18), float(0.72), bankBreakup);
    const riverBank = isLakeShore.oneMinus()
      .mul(smoothstep(0.3, bankReach, field.b).oneMinus())
      .mul(smoothstep(-0.15, bankHeight, aboveWater).oneMinus())
      .mul(smoothstep(-0.15, 0.12, aboveWater))
      .mul(bankBreakup.mul(0.75).add(0.15))
      .mul(inside);
    wSoil = wSoil.add(riverBank.mul(0.58));
    wMoss = wMoss.add(riverBank.mul(0.32));
    wGrass = wGrass.mul(riverBank.mul(0.55).oneMinus());

    let pathDistance: Node<"float"> = float(10000);
    for (const path of surface.paths) {
      for (let i = 1; i < path.polyline.length; i++) {
        const a = vec2(...path.polyline[i - 1]);
        const b = vec2(...path.polyline[i]);
        const delta = b.sub(a);
        const t = planar.sub(a).dot(delta).div(delta.dot(delta).max(0.0001)).clamp();
        pathDistance = pathDistance.min(planar.sub(a.add(delta.mul(t))).length().sub(path.width / 2));
      }
    }
    // Cohesive, continuous earthy hiking trail with soft grass-tuft shoulders (never breaks in G1, never bright cream)
    const pathJitter = macro18.sub(0.5).mul(0.70).add(smallNoise.sub(0.5).mul(0.52));
    const noisyPathDist = pathDistance.add(pathJitter);
    const dryPath = smoothstep(0.02, 0.14, aboveWater);
    const pathEdgeTuft = smoothstep(0.42, 0.84, macro18.mul(0.50).add(smallNoise.mul(0.50)));
    const pathCore = smoothstep(0.35, -0.55, noisyPathDist).mul(dryPath);
    const pathShoulder = smoothstep(2.45, -0.15, noisyPathDist).mul(dryPath).mul(pathEdgeTuft.mul(0.45).oneMinus());
    const pathCenterWear = smoothstep(0.25, 0.80, smallNoise.mul(0.55).add(macro18.mul(0.45))).mul(0.22).add(0.78);
    const pathFill = pathCore.mul(pathCenterWear);
    wSoil = wSoil.add(pathShoulder.mul(0.52)).add(pathFill.mul(0.48));
    wDry = wDry.add(pathShoulder.mul(0.46));
    wPath = wPath.add(pathFill.mul(1.05)).add(pathShoulder.mul(0.18));
    const trailSuppress = pathFill.mul(0.92).max(pathShoulder.mul(0.48)).oneMinus();
    wGrass = wGrass.mul(trailSuppress);
    wMoss = wMoss.mul(trailSuppress);
  }

  // Soft height-interlocked ORH blending across all 7 planar surface layers
  // Softened grass/dry/moss height variance prevents per-texel salt-and-pepper stippling at close range.
  const rawSum = wGrass.add(wDry).add(wSoil).add(wSand).add(wWet).add(wPath).add(wMoss).max(0.0001);
  const nw0 = wGrass.div(rawSum);
  const nw1 = wDry.div(rawSum);
  const nw2 = wSoil.div(rawSum);
  const nw3 = wSand.div(rawSum);
  const nw4 = wWet.div(rawSum);
  const nw5 = wPath.div(rawSum);
  const nw6 = wMoss.div(rawSum);

  const s0 = nw0.mul(mix(float(0.5), lGrass.orh.b, 0.35).add(0.34));
  const s1 = nw1.mul(mix(float(0.5), lDry.orh.b, 0.35).add(0.34));
  const s2 = nw2.mul(mix(float(0.5), lSoil.orh.b, 0.65).add(0.34));
  const s3 = nw3.mul(mix(float(0.5), lSand.orh.b, 0.50).add(0.34));
  const s4 = nw4.mul(mix(float(0.5), lSandWet.orh.b, 0.50).add(0.34));
  const s5 = nw5.mul(mix(float(0.5), lGravel.orh.b, 0.70).add(0.34));
  const s6 = nw6.mul(mix(float(0.5), lMoss.orh.b, 0.35).add(0.34));

  const maxS = max(max(max(s0, s1), max(s2, s3)), max(max(s4, s5), s6)).sub(0.38);
  const b0 = s0.sub(maxS).max(0);
  const b1 = s1.sub(maxS).max(0);
  const b2 = s2.sub(maxS).max(0);
  const b3 = s3.sub(maxS).max(0);
  const b4 = s4.sub(maxS).max(0);
  const b5 = s5.sub(maxS).max(0);
  const b6 = s6.sub(maxS).max(0);
  const bSum = b0.add(b1).add(b2).add(b3).add(b4).add(b5).add(b6).max(0.0001);

  const bw0 = b0.div(bSum);
  const bw1 = b1.div(bSum);
  const bw2 = b2.div(bSum);
  const bw3 = b3.div(bSum);
  const bw4 = b4.div(bSum);
  const bw5 = b5.div(bSum);
  const bw6 = b6.div(bSum);

  const planarAlbedo = lGrass.albedo.mul(bw0)
    .add(lDry.albedo.mul(bw1))
    .add(lSoil.albedo.mul(bw2))
    .add(lSand.albedo.mul(bw3))
    .add(lSandWet.albedo.mul(bw4))
    .add(lGravel.albedo.mul(bw5))
    .add(lMoss.albedo.mul(bw6));

  const planarReliefXZ = lGrass.reliefXZ.mul(bw0)
    .add(lDry.reliefXZ.mul(bw1))
    .add(lSoil.reliefXZ.mul(bw2))
    .add(lSand.reliefXZ.mul(bw3))
    .add(lSandWet.reliefXZ.mul(bw4))
    .add(lGravel.reliefXZ.mul(bw5))
    .add(lMoss.reliefXZ.mul(bw6));

  const planarMidReliefXZ = lGrass.midReliefXZ.mul(bw0.add(bw1).add(bw2).add(bw6).clamp(0, 1));

  const planarOrh = lGrass.orh.mul(bw0)
    .add(lDry.orh.mul(bw1))
    .add(lSoil.orh.mul(bw2))
    .add(lSand.orh.mul(bw3))
    .add(lSandWet.orh.mul(bw4))
    .add(lGravel.orh.mul(bw5))
    .add(lMoss.orh.mul(bw6));

  // Distance-scaled fractured limestone strata for both near hero cliffs (G7) and far mountains.
  // The vertical phase shares the wall UV terrain warp, so ledges undulate around ridges, shoulders
  // and hollows rather than locking to a single world-horizontal elevation or a directional sine axis.
  const strataY = p.y.sub(strataWarpForScale(64.0, 0.9));
  const bandBroad = mx_noise_float(vec3(p.x.mul(0.008), strataY.mul(0.11), p.z.mul(0.008))).mul(0.5).add(0.5);
  const ledgeStep = smoothstep(0.28, 0.72, bandBroad);
  const bandShift = ledgeStep.mul(0.68).add(cChalkFine.orh.b.mul(0.32));

  const chalkCol = cChalkFine.albedo.mul(vec3(1.07, 1.03, 0.95));
  const strataCol = cStrataMacro.albedo.mul(vec3(0.84, 0.80, 0.72));
  const macroRockWeight = macroWB.b.add(macroWB.a).max(0.001);
  const macroStrataRatio = macroWB.a.div(macroRockWeight).clamp(0, 1);
  const strataMix = smoothstep(0.10, 0.82, bandShift).mul(0.52).add(0.36)
    .add(macroStrataRatio.sub(0.5).mul(0.16))
    .clamp(0, 0.94);
  const cliffFarMix = smoothstep(35, 320, dist).mul(0.62).add(strataMix.mul(0.38)).clamp(0, 1);
  const distantCliffCalm = smoothstep(DISTANT_CLIFF_CALM_START, DISTANT_CLIFF_CALM_END, dist);
  const strataToneDetail = mix(float(0.72), float(1.14), ledgeStep);
  const strataTone = mix(strataToneDetail, float(1), distantCliffCalm.mul(0.55));
  const cliffAlbedoDetail = mix(chalkCol, strataCol, cliffFarMix).mul(strataTone);
  const distantRockSwatch = swatch("canyon_chalk").clone().lerp(swatch("canyon_strata"), 0.35);
  const distantRockTone = vec3(distantRockSwatch.r, distantRockSwatch.g, distantRockSwatch.b);
  const cliffAlbedo = mix(cliffAlbedoDetail, distantRockTone, distantCliffCalm.mul(0.48));
  const cliffDeltaWorld = mix(cChalkFine.deltaWorld.mul(0.85), cStrataMacro.deltaWorld.mul(1.30), cliffFarMix);
  const cliffOrh = cChalkFine.orh;

  const alpineFarFade = smoothstep(380, 1400, dist).mul(smoothstep(260, 420, p.y));
  const nearAlbedo = mix(planarAlbedo, cliffAlbedo, cliffMask);
  const farAlpine = mix(nearAlbedo, macroColorAo.rgb, float(0.18));
  const combinedOrh = mix(planarOrh, cliffOrh, cliffMask);
  const softOrhAo = mix(float(0.66), float(1.0), combinedOrh.r);
  const microAO = mix(float(1), mix(softOrhAo, combinedOrh.r, cliffMask), microAoFade);
  const macroAO = mix(float(0.76), float(1.14), macroColorAo.a);
  const meadowLift = float(1.0).add(bw0.mul(0.06).add(bw1.mul(0.10)).mul(cliffMask.oneMinus()));
  const finalColor = mix(nearAlbedo, farAlpine, alpineFarFade).mul(microAO).mul(macroAO).mul(shoreDampMul).mul(meadowLift);

  const dryRough = mix(planarOrh.g.max(0.91), cliffOrh.g.max(0.95), cliffMask);
  const wetGlossRough = mix(dryRough, float(0.42), bw4.mul(cliffMask.oneMinus()));
  material.roughnessNode = mix(wetGlossRough, float(0.96), alpineFarFade.mul(0.5)).clamp(0.32, 0.99);
  material.specularIntensityNode = mix(float(0.10), float(0.22), bw4.mul(cliffMask.oneMinus()));

  // Per-surface micro-normal weight: calm organic meadow (0.32), soft matte sand (0.32), tactile soil/gravel (0.65)
  const microNormalStrength = bw0.add(bw1).add(bw6).mul(0.32)
    .add(bw3.add(bw4).mul(0.32))
    .add(bw2.add(bw5).mul(0.65));
  const planarDeltaWorld = vec3(planarReliefXZ.x, 0, planarReliefXZ.y).mul(microNormalFade.mul(microNormalStrength))
    .add(vec3(planarMidReliefXZ.x, 0, planarMidReliefXZ.y).mul(midNormalFade.mul(0.85)));
  const fineDelta = mix(planarDeltaWorld, cliffDeltaWorld.mul(cliffNormalFade.mul(1.15)), cliffMask);
  const tangentFine = fineDelta.sub(normal.mul(fineDelta.dot(normal)));
  const finalNormal = normal.add(tangentFine).normalize();
  material.normalNode = transformNormalToView(finalNormal);

  const debugDetail = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("groundDetail");
  material.colorNode = debugDetail === "albedo"
    ? nearAlbedo
    : debugDetail === "normal"
      ? finalNormal.mul(0.5).add(0.5)
      : finalColor;
  if (debugDetail === "albedo" || debugDetail === "normal") material.emissiveNode = material.colorNode;

  return material;
}

/** Lightweight macro-lit terrain material used strictly during planar water reflection passes. */
export function terrainReflectionMaterial() {
  const material = new MeshBasicNodeMaterial();
  const macroUv = positionWorld.xz.sub(vec2(MACRO_MIN, MACRO_MIN)).div(MACRO_SIZE).clamp(0, 1);
  const macro = texture(macroColorAoTex, macroUv);
  const n = normalWorldGeometry.normalize();
  const ndotl = dot(n, vec3(sunDirection)).max(0);
  const hemiT = n.y.mul(0.5).add(0.5);
  const skyFill = swatch("sky_blue").clone().lerp(swatch("cloud_cream"), 0.65);
  const groundFill = swatch("stone_weathered").clone().lerp(swatch("monument_shadow"), 0.35);
  const sunLit = color(new Color("#FFF4E0")).mul(ndotl.mul(1.15));
  const ambient = mix(color(groundFill), color(skyFill), hemiT).mul(0.74);
  const macroAO = mix(float(0.76), float(1.10), macro.a);
  material.colorNode = macro.rgb.mul(sunLit.add(ambient)).mul(macroAO);
  return material;
}
