import {
  ClampToEdgeWrapping, DataArrayTexture, DataTexture, LinearFilter, LinearMipmapLinearFilter,
  LinearSRGBColorSpace, MeshPhysicalNodeMaterial, RepeatWrapping, RGBAFormat, SRGBColorSpace,
  Texture, UnsignedByteType, type Node,
} from "three/webgpu";
import {
  abs, cameraPosition, cos, float, int, max, mix, mx_noise_float, normalWorldGeometry,
  positionWorld, sin, smoothstep, texture, transformNormalToView, vec2, vec3,
} from "three/tsl";
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
  let damp: Node<"float"> = float(0);
  let shoreDampMul: Node<"float"> = float(1);

  if (surface && field) {
    const dx = surface.sample(planar.add(vec2(3, 0))).r.sub(surface.sample(planar.sub(vec2(3, 0))).r).div(6);
    const dz = surface.sample(planar.add(vec2(0, 3))).r.sub(surface.sample(planar.sub(vec2(0, 3))).r).div(6);
    const uv = planar.sub(surface.origin).div(surface.size);
    const border = smoothstep(0, 0.02, uv.x)
      .mul(smoothstep(0, 0.02, uv.y))
      .mul(smoothstep(0, 0.02, uv.x.oneMinus()))
      .mul(smoothstep(0, 0.02, uv.y.oneMinus()));
    smoothNormal = mix(geomNormal, vec3(dx.negate(), 1, dz.negate()).normalize(), smoothstep(40, 100, field.b).oneMinus().mul(border));
    const neighbours = surface.sample(planar.add(vec2(14, 0))).r
      .add(surface.sample(planar.sub(vec2(14, 0))).r)
      .add(surface.sample(planar.add(vec2(0, 14))).r)
      .add(surface.sample(planar.sub(vec2(0, 14))).r)
      .mul(0.25);
    hollow = smoothstep(0.15, 1.7, neighbours.sub(field.r)).mul(border);
    damp = smoothstep(2, 26, p.y.sub(field.g)).oneMinus().mul(smoothstep(15, 100, field.b).oneMinus()).mul(border);
  }

  const macroUv = planar.sub(vec2(MACRO_MIN, MACRO_MIN)).div(MACRO_SIZE).clamp(0, 1);
  const macroColorAo = texture(macroColorAoTex, macroUv);
  const macroWA = texture(macroWeightsATex, macroUv);
  const macroWB = texture(macroWeightsBTex, macroUv);

  const dist = p.sub(cameraPosition).length();
  const microAoFade = smoothstep(25, 140, dist).oneMinus();
  const microNormalFade = smoothstep(15, 105, dist).oneMinus();
  const midNormalFade = smoothstep(45, 160, dist).mul(smoothstep(280, 980, dist).oneMinus().mul(0.80).add(0.20));
  const cliffNormalFade = smoothstep(60, 1200, dist).oneMinus().mul(0.50).add(0.50);

  // Lean 3-noise planar basis + analytic cove envelope (zero crosshatch, zero extra texture taps)
  const savannaPatch = mx_noise_float(planar.mul(0.0085).add(vec2(71, -39))).mul(0.5).add(0.5);
  const turfPatch = mx_noise_float(planar.mul(0.052).add(vec2(-29, 83))).mul(0.5).add(0.5);
  const smallNoise = mx_noise_float(planar.mul(0.18).add(vec2(-19, 58))).mul(0.5).add(0.5);
  const antiMix = savannaPatch.mul(0.45);
  const coveV1 = sin(planar.x.sub(560).mul(0.009).add(planar.y.sub(1520).mul(0.005)).add(1.57)).mul(0.5).add(0.5);
  const coveV2 = cos(planar.x.sub(560).mul(0.007).sub(planar.y.sub(1520).mul(0.008))).mul(0.5).add(0.5);
  const coveShape = coveV1.mul(0.55).add(coveV2.mul(0.45));

  const uvBBase = vec2(
    planar.x.mul(0.8).add(planar.y.mul(0.6)),
    planar.y.mul(0.8).sub(planar.x.mul(0.6)),
  ).add(vec2(17.3, 9.2));

  const samplePlanar = (layerIndex: number, mode: "single" | "dual" | "aerial") => {
    const idx = int(layerIndex);
    const invTile = 1 / layerTileM[layerIndex];
    const uvA = planar.mul(invTile);
    const aAlb = texture(albedoArray, uvA).depth(idx).rgb;
    const aNrm = texture(normalArray, uvA).depth(idx).xy.mul(2).sub(1);
    const aOrh = texture(orhArray, uvA).depth(idx).rgb;
    if (mode === "single") return { albedo: aAlb, reliefXZ: aNrm, midReliefXZ: aNrm.mul(0), orh: aOrh, macroGrain: float(0.5) };

    const uvB = uvBBase.mul(invTile / 2.31);
    const bAlb = texture(albedoArray, uvB).depth(idx).rgb;
    const closeAlb = mix(aAlb, bAlb, antiMix);
    if (mode === "dual") return { albedo: closeAlb, reliefXZ: aNrm, midReliefXZ: aNrm.mul(0), orh: aOrh, macroGrain: float(0.5) };

    // Macro 36m organic soil clump grain for dappled ref_09 hills across mid/aerial distances
    const uvM = planar.mul(1 / 36.0);
    const mSoilAlb = texture(albedoArray, uvM).depth(int(2)).rgb;
    const mLuma = mSoilAlb.r.mul(0.40).add(mSoilAlb.g.mul(0.40)).add(mSoilAlb.b.mul(0.20));
    const mContrast = smoothstep(0.16, 0.72, mLuma);
    const mNrm = texture(normalArray, uvM).depth(int(2)).xy.mul(2).sub(1);
    return {
      albedo: closeAlb,
      reliefXZ: aNrm,
      midReliefXZ: mNrm,
      orh: aOrh,
      macroGrain: mContrast,
    };
  };

  // Rich ref_09 sunlit savanna meadow + dappled soil/clump macro texture + pebbled coastal sand
  const clumpDetail = smoothstep(0.16, 0.84, turfPatch.mul(0.45).add(smallNoise.mul(0.55)));
  const turfShade = clumpDetail.mul(0.20).add(savannaPatch.mul(0.10)).add(0.84);
  const lGrassRaw = samplePlanar(0, "aerial");
  const macroGrainField = mix(float(0.5), lGrassRaw.macroGrain, smoothstep(14, 75, dist));
  const meadowMottle = mix(vec3(0.75, 0.83, 0.55), vec3(1.13, 1.11, 0.78), macroGrainField);
  const lGrass = { ...lGrassRaw, albedo: lGrassRaw.albedo.mul(vec3(0.84, 1.04, 0.50)).mul(turfShade).mul(meadowMottle) };
  const lDryRaw = samplePlanar(1, "dual");
  const lDry = { ...lDryRaw, albedo: lDryRaw.albedo.mul(vec3(1.02, 1.05, 0.56)).mul(turfShade).mul(meadowMottle) };
  const lSoilRaw = samplePlanar(2, "single");
  const lSoil = { ...lSoilRaw, albedo: lSoilRaw.albedo.mul(vec3(0.82, 0.74, 0.58)) };
  const lSandRaw = samplePlanar(3, "dual");
  const lGravelRaw = samplePlanar(5, "single");
  const lGravel = { ...lGravelRaw, albedo: lGravelRaw.albedo.mul(vec3(0.80, 0.74, 0.60)) };
  const sandPebble = smoothstep(0.24, 0.82, smallNoise.mul(0.55).add(turfPatch.mul(0.45))).mul(0.52).add(0.14);
  const sandDrift = smoothstep(0.30, 0.78, savannaPatch.mul(0.6).add(turfPatch.mul(0.4))).mul(0.22);
  const sandTone = turfPatch.mul(0.20).add(smallNoise.mul(0.14)).add(0.82);
  const sandBase = mix(lSandRaw.albedo.mul(vec3(0.88, 0.81, 0.65)), lGravelRaw.albedo.mul(vec3(0.76, 0.70, 0.56)), sandPebble);
  const lSand = {
    ...lSandRaw,
    albedo: mix(sandBase, lSoil.albedo.mul(vec3(1.05, 1.00, 0.90)), sandDrift).mul(sandTone),
    reliefXZ: mix(lSandRaw.reliefXZ, lGravelRaw.reliefXZ, sandPebble.mul(0.65)),
  };
  const lSandWetRaw = samplePlanar(4, "single");
  const lSandWet = { ...lSandWetRaw, albedo: lSandWetRaw.albedo.mul(vec3(0.54, 0.48, 0.37)) };
  const lMossRaw = samplePlanar(8, "single");
  const lMoss = { ...lMossRaw, albedo: lMossRaw.albedo.mul(vec3(0.56, 0.78, 0.38)).mul(meadowMottle) };

  // Noise-warped dominant horizontal axis selection (zero 50/50 45-deg crosshatch overlap)
  const geomSlope = geomNormal.y.abs().oneMinus();
  const hAx = abs(geomNormal.x);
  const hAz = abs(geomNormal.z);
  const axisBias = hAx.sub(hAz).add(turfPatch.sub(0.5).mul(0.045));
  const wx = smoothstep(-0.045, 0.045, axisBias);
  const wz = wx.oneMinus();

  const sampleWallCliff = (layerIndex: number, scaleM: number, includeOrh: boolean) => {
    const idx = int(layerIndex);
    const inv = 1 / scaleM;
    const uvX = vec2(p.z.mul(inv), p.y.negate().mul(inv));
    const uvZ = vec2(p.x.mul(inv), p.y.negate().mul(inv));

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

  const cChalkFine = sampleWallCliff(6, 9.5, true);
  const cStrataMacro = sampleWallCliff(6, 64.0, false);

  // Genuine steep cliffs (>= 39 deg near, >= 41 deg + alpine macroWB far) with rocky scree skirt
  const farLod = smoothstep(70, 220, dist);
  const nearRockBreakup = cChalkFine.orh.b.sub(0.5).mul(0.085).add(smallNoise.sub(0.5).mul(0.048)).add(turfPatch.sub(0.5).mul(0.032));
  const nearCliff = smoothstep(0.220, 0.285, geomSlope.add(nearRockBreakup));
  const screeBand = smoothstep(0.185, 0.245, geomSlope.add(smallNoise.sub(0.5).mul(0.04))).mul(nearCliff.oneMinus()).mul(farLod.oneMinus());
  const farRockSignal = macroWB.b.add(macroWB.a).clamp(0, 1);
  const farRockBreakup = turfPatch.sub(0.5).mul(0.18).add(cChalkFine.orh.b.sub(0.5).mul(0.14));
  const farCliff = smoothstep(0.34, 0.68, farRockSignal.add(farRockBreakup));
  const cliffMask = mix(nearCliff, farCliff, farLod);
  const normal = mix(smoothNormal, geomNormal, cliffMask.mul(farLod.oneMinus())).normalize();
  const slope = normal.y.abs().oneMinus();
  const north = normal.z.negate().max(0);

  const dryBias = smoothstep(0.20, 0.80, savannaPatch.mul(0.55).add(turfPatch.mul(0.25)).add(smallNoise.mul(0.20))).mul(0.58)
    .add(smoothstep(0.04, 0.16, slope).mul(0.26))
    .sub(hollow.mul(0.44))
    .sub(damp.mul(0.24));
  let wGrass: Node<"float"> = macroWA.r.max(0.52).mul(dryBias.mul(0.48).clamp(0, 0.62).oneMinus()).max(0.20);
  let wDry: Node<"float"> = macroWA.g.mul(0.55).add(dryBias.max(0).mul(0.82));
  let wSoil: Node<"float"> = macroWA.b.mul(0.20).add(smoothstep(0.175, 0.26, geomSlope).mul(0.45)).add(screeBand.mul(0.42));
  let wMoss: Node<"float"> = macroWA.a.mul(0.42).add(
    smoothstep(0.32, 0.78, damp.mul(0.45).add(hollow.mul(0.72)).add(north.mul(0.45)).add(savannaPatch.oneMinus().mul(0.25))).mul(0.58),
  );
  let wSand: Node<"float"> = float(0);
  let wWet: Node<"float"> = float(0);
  let wPath: Node<"float"> = screeBand.mul(0.24);

  if (surface && field) {
    const uv = planar.sub(surface.origin).div(surface.size);
    const inside = float(uv.x.greaterThanEqual(0).and(uv.y.greaterThanEqual(0)).and(uv.x.lessThanEqual(1)).and(uv.y.lessThanEqual(1)));
    const aboveWater = p.y.sub(field.g);

    const isLakeShore = smoothstep(14.0, 48.0, field.a).oneMinus();
    const wetEdge = smoothstep(-0.10, 0.34, aboveWater.add(smallNoise.sub(0.5).mul(0.07))).oneMinus();
    const liveWet = wetEdge.mul(isLakeShore).mul(smoothstep(2.0, 12.0, field.b).oneMinus()).mul(inside);

    // Continuous varying-width lake beaches around Spiegelsee, wider in coves & cleanly separated from riverbanks
    const flatBeachMask = smoothstep(0.012, 0.080, slope).oneMinus();
    const coveWidth = mix(float(0.36), float(1.0), smoothstep(0.28, 0.82, coveShape.mul(0.70).add(savannaPatch.mul(0.30))));
    const maxBeachHeight = isLakeShore.mul(flatBeachMask).mul(coveWidth).mul(1.55);
    const beachEdgeJitter = savannaPatch.sub(0.5).mul(0.75).add(turfPatch.sub(0.5).mul(0.68)).add(smallNoise.sub(0.5).mul(0.45));
    const beachTop = maxBeachHeight.max(0.18);
    const shoreAbove = smoothstep(beachTop.mul(0.12), beachTop, aboveWater.max(0).add(beachEdgeJitter)).oneMinus();
    const shore = shoreAbove.mul(isLakeShore.mul(flatBeachMask)).mul(smoothstep(2.0, 22.0, field.b).oneMinus()).mul(inside);
    const liveSand = shore.mul(wetEdge.oneMinus());

    // Gentle capillary damp darkening on sandy beaches (natural wet rim, zero charcoal puddle halo)
    const dampZone = smoothstep(0.0, 0.55, aboveWater.add(smallNoise.sub(0.5).mul(0.08))).oneMinus()
      .mul(shore.max(liveWet))
      .mul(smoothstep(2.0, 12.0, field.b).oneMinus())
      .mul(inside);
    const submergedDark = smoothstep(-1.10, 0.05, aboveWater).mul(0.24).add(0.76);
    shoreDampMul = mix(float(1), float(0.84), dampZone.mul(0.85)).mul(mix(float(1), submergedDark, inside));

    const upperBeachFringe = smoothstep(0.18, 1.25, aboveWater).mul(smoothstep(0.38, 0.78, turfPatch.mul(0.55).add(smallNoise.mul(0.45))));
    const sandClean = liveSand.mul(upperBeachFringe.mul(0.55).oneMinus());
    wSand = sandClean;
    wWet = liveWet;
    const clearVeg = sandClean.max(liveWet).oneMinus();
    wGrass = wGrass.mul(clearVeg);
    wDry = wDry.mul(clearVeg).add(shore.mul(0.46).mul(upperBeachFringe));
    wSoil = wSoil.add(shore.mul(0.26).mul(clearVeg.max(upperBeachFringe.mul(0.5))));
    wMoss = wMoss.mul(clearVeg);

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
    const pathJitter = smallNoise.sub(0.5).mul(1.95).add(turfPatch.sub(0.5).mul(1.55));
    const noisyPathDist = pathDistance.add(pathJitter);
    const dryPath = smoothstep(0.08, 0.25, aboveWater);
    const pathTuft = smoothstep(0.52, 0.88, smallNoise.mul(0.6).add(turfPatch.mul(0.4))).mul(0.32);
    const pathWorn = smoothstep(0.20, 0.85, turfPatch.mul(0.55).add(smallNoise.mul(0.45))).mul(0.24).add(0.46).mul(pathTuft.oneMinus());
    const pathEdge = smoothstep(-0.1, 3.0, noisyPathDist).oneMinus().mul(dryPath).mul(0.52);
    const pathFill = smoothstep(-0.30, 1.25, noisyPathDist).oneMinus().mul(dryPath).mul(pathWorn);
    wSoil = wSoil.add(pathEdge.mul(0.35)).add(pathFill.mul(0.28));
    wDry = wDry.add(pathEdge.mul(0.45));
    wPath = wPath.add(pathFill.mul(0.62));
    const trailSuppress = pathFill.mul(0.78).max(pathEdge.mul(0.45)).oneMinus();
    wGrass = wGrass.mul(trailSuppress);
    wMoss = wMoss.mul(trailSuppress);
  }

  // Soft height-interlocked ORH blending across all 7 planar surface layers
  const rawSum = wGrass.add(wDry).add(wSoil).add(wSand).add(wWet).add(wPath).add(wMoss).max(0.0001);
  const nw0 = wGrass.div(rawSum);
  const nw1 = wDry.div(rawSum);
  const nw2 = wSoil.div(rawSum);
  const nw3 = wSand.div(rawSum);
  const nw4 = wWet.div(rawSum);
  const nw5 = wPath.div(rawSum);
  const nw6 = wMoss.div(rawSum);

  const s0 = nw0.mul(lGrass.orh.b.add(0.30));
  const s1 = nw1.mul(lDry.orh.b.add(0.30));
  const s2 = nw2.mul(lSoil.orh.b.add(0.30));
  const s3 = nw3.mul(lSand.orh.b.add(0.30));
  const s4 = nw4.mul(lSandWet.orh.b.add(0.30));
  const s5 = nw5.mul(lGravel.orh.b.add(0.30));
  const s6 = nw6.mul(lMoss.orh.b.add(0.30));

  const maxS = max(max(max(s0, s1), max(s2, s3)), max(max(s4, s5), s6)).sub(0.24);
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

  const planarMidReliefXZ = lGrass.midReliefXZ.mul(bw0.add(bw1).add(bw6).clamp(0, 1));

  const planarOrh = lGrass.orh.mul(bw0)
    .add(lDry.orh.mul(bw1))
    .add(lSoil.orh.mul(bw2))
    .add(lSand.orh.mul(bw3))
    .add(lSandWet.orh.mul(bw4))
    .add(lGravel.orh.mul(bw5))
    .add(lMoss.orh.mul(bw6));

  // Distance-scaled fractured limestone strata for both near hero cliffs (G7) and far mountains
  const strataY = p.y.add(savannaPatch.sub(0.5).mul(26.0)).add(turfPatch.sub(0.5).mul(5.0));
  const bandBroad = mx_noise_float(vec3(p.x.mul(0.008), strataY.mul(0.11), p.z.mul(0.008))).mul(0.5).add(0.5);
  const ledgeStep = smoothstep(0.28, 0.72, bandBroad);
  const bandShift = ledgeStep.mul(0.68).add(cChalkFine.orh.b.mul(0.32));

  const chalkCol = cChalkFine.albedo.mul(vec3(1.07, 1.03, 0.95));
  const strataCol = cStrataMacro.albedo.mul(vec3(0.84, 0.80, 0.72));
  const strataMix = smoothstep(0.10, 0.82, bandShift).mul(0.52).add(0.36).add(macroWB.a.mul(0.10)).clamp(0, 0.94);
  const cliffFarMix = smoothstep(35, 320, dist).mul(0.62).add(strataMix.mul(0.38)).clamp(0, 1);
  const strataTone = mix(float(0.72), float(1.14), ledgeStep);
  const cliffAlbedo = mix(chalkCol, strataCol, cliffFarMix).mul(strataTone);
  const cliffDeltaWorld = mix(cChalkFine.deltaWorld.mul(0.85), cStrataMacro.deltaWorld.mul(1.30), cliffFarMix);
  const cliffOrh = cChalkFine.orh;

  const alpineFarFade = smoothstep(380, 1400, dist).mul(smoothstep(260, 420, p.y));
  const nearAlbedo = mix(planarAlbedo, cliffAlbedo, cliffMask);
  const farAlpine = mix(nearAlbedo, macroColorAo.rgb, float(0.18));
  const combinedOrh = mix(planarOrh, cliffOrh, cliffMask);
  const microAO = mix(float(1), combinedOrh.r, microAoFade);
  const macroAO = mix(float(0.68), float(1.04), macroColorAo.a);
  const finalColor = mix(nearAlbedo, farAlpine, alpineFarFade).mul(microAO).mul(macroAO).mul(shoreDampMul);

  const dryRough = mix(planarOrh.g.max(0.90), cliffOrh.g.max(0.95), cliffMask);
  const wetGlossRough = mix(dryRough, float(0.18), bw4.mul(cliffMask.oneMinus()));
  material.roughnessNode = mix(wetGlossRough, float(0.96), alpineFarFade.mul(0.5)).clamp(0.16, 0.99);
  material.specularIntensityNode = mix(float(0.14), float(0.88), bw4.mul(cliffMask.oneMinus()));

  const planarDeltaWorld = vec3(planarReliefXZ.x, 0, planarReliefXZ.y).mul(microNormalFade.mul(0.85))
    .add(vec3(planarMidReliefXZ.x, 0, planarMidReliefXZ.y).mul(midNormalFade.mul(1.25)));
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
