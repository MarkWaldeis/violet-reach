import {
  Box3, Color, DataTexture, DoubleSide, Frustum, LinearFilter, LinearMipmapLinearFilter,
  LinearSRGBColorSpace, Matrix4, Mesh, MeshPhysicalNodeMaterial, RepeatWrapping, RGBAFormat, Texture,
  TextureLoader, UnsignedByteType, Group, Vector3, type Node, type PerspectiveCamera,
} from "three/webgpu";
import {
  abs, attribute, cameraPosition, color, cos, dot, float, floor, Fn, fract, If, mix, mx_noise_float,
  positionWorld, reflect, reflector, screenUV, sin, smoothstep, sqrt, step, texture,
  transformNormalToView, vec2, vec3,
} from "three/tsl";
import { sunDirection } from "./atmosphere.ts";
import { REFLECTION_LAYER } from "./quality.ts";
import { worldTime as time } from "./world-time.ts";
import type { WaterRegion } from "./hydrology.ts";
import { swatch } from "./palette.ts";
import type { SurfaceData } from "./surface-data.ts";
import { buildWaterGeometry } from "./water-geometry.ts";

function configureWaterTexture(tex: Texture): Texture {
  tex.colorSpace = LinearSRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.magFilter = LinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = 8;
  tex.flipY = false;
  tex.needsUpdate = true;
  return tex;
}

function makeWaterFallback(rgba: [number, number, number, number]): DataTexture {
  const tex = new DataTexture(new Uint8Array(rgba), 1, 1, RGBAFormat, UnsignedByteType);
  tex.colorSpace = LinearSRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.flipY = false;
  tex.needsUpdate = true;
  return tex;
}

let waterNormalATex: Texture = makeWaterFallback([128, 128, 255, 255]);
let waterFoamTex: Texture = makeWaterFallback([0, 0, 0, 255]);
let waterTexturesPromise: Promise<void> | null = null;

/**
 * Planar-reflection pass configuration. Kept as one exported, testable value so the
 * Spiegelsee reflection remains a single bounded-resolution pass on both backends.
 */
export const WATER_REFLECTION_PASS = Object.freeze({
  resolutionScale: 0.35,
  bounces: false,
  generateMipmaps: true,
});

/**
 * Conservative screen-space reflection-distortion tuning. The UV scales are deliberately
 * smaller than the legacy vec2(0.18, 0.30) multiplier; the additional normal/distance/view
 * attenuation below is what keeps distant aerial reflections coherent instead of striped.
 * Near-field effective Y coefficients are 0.21 × 0.42 ≈ 0.088 for a calm open lake and
 * at most 0.21 × 0.78 ≈ 0.164 in shallow/rough water (legacy: unfiltered 0.30).
 */
export const WATER_REFLECTION_DISTORTION = Object.freeze({
  uvScaleX: 0.13,
  uvScaleY: 0.21,
  distanceNearM: 30,
  distanceFarM: 320,
  distanceFloor: 0.24,
  steepViewStart: 0.24,
  steepViewEnd: 0.82,
  steepViewFloor: 0.58,
  calmNormalScale: 0.42,
  roughNormalScale: 0.78,
  breezeAgitation: 0.72,
  shoreFullDepthM: 0.22,
  shoreFadeDepthM: 1.55,
});

/** Shoreline/foam tuning shared by the shader and the pure Node test probes. */
export const WATER_SHORE_TUNING = Object.freeze({
  edgeFadeWidthM: 1.15,
  depthFadeWidthM: 0.72,
  foamBreakupLow: 0.40,
  foamBreakupHigh: 0.74,
  foamPatchLow: 0.28,
  foamPatchHigh: 0.80,
  foamContactPeak: 0.56,
  foamSwashBase: 0.28,
  foamSwashWave: 0.72,
  foamStrength: 0.90,
  foamMax: 0.76,
});

const clamp01Cpu = (v: number) => Math.min(1, Math.max(0, v));
const smoothstepCpu = (low: number, high: number, x: number) => {
  const t = clamp01Cpu((x - low) / (high - low));
  return t * t * (3 - 2 * t);
};

/** CPU mirror of the shader distance LOD for reflection distortion (1 near, floor far). */
export function waterReflectionDistanceScale(distanceM: number, tuning = WATER_REFLECTION_DISTORTION) {
  return 1 - smoothstepCpu(tuning.distanceNearM, tuning.distanceFarM, distanceM) * (1 - tuning.distanceFloor);
}

/** CPU mirror of the steep-view attenuation (grazing views keep stronger distortions). */
export function waterReflectionViewScale(viewElevation: number, tuning = WATER_REFLECTION_DISTORTION) {
  return 1 - smoothstepCpu(tuning.steepViewStart, tuning.steepViewEnd, viewElevation) * (1 - tuning.steepViewFloor);
}

/** CPU mirror of the combined shallow-shore and wind-ruffle agitation weight in [0, 1]. */
export function waterReflectionWaveZone(depthM: number, breeze: number, tuning = WATER_REFLECTION_DISTORTION) {
  const shore = 1 - smoothstepCpu(tuning.shoreFullDepthM, tuning.shoreFadeDepthM, depthM);
  return Math.max(shore, clamp01Cpu(breeze) * tuning.breezeAgitation);
}

/** CPU mirror of the normal-slope scale used only for planar-reflection UV distortion. */
export function waterReflectionNormalScale(depthM: number, breeze: number, tuning = WATER_REFLECTION_DISTORTION) {
  const zone = waterReflectionWaveZone(depthM, breeze, tuning);
  return tuning.calmNormalScale + (tuning.roughNormalScale - tuning.calmNormalScale) * zone;
}

/** Combined dimensionless reflection-distortion attenuation used by the shader configuration. */
export function waterReflectionDistortionScale(distanceM: number, viewElevation: number, depthM: number, breeze: number, tuning = WATER_REFLECTION_DISTORTION) {
  return waterReflectionNormalScale(depthM, breeze, tuning)
    * waterReflectionDistanceScale(distanceM, tuning)
    * waterReflectionViewScale(viewElevation, tuning);
}

/** Pure shoreline coverage fade: 0 exactly at the waterline, 1 after the configured width inside. */
export function waterEdgeFade(distanceInsideM: number, tuning = WATER_SHORE_TUNING) {
  return smoothstepCpu(0, tuning.edgeFadeWidthM, distanceInsideM);
}

/** Pure depth coverage fade for clear shallow water; complements the world-space waterline fade. */
export function waterDepthFade(depthM: number, tuning = WATER_SHORE_TUNING) {
  return smoothstepCpu(0, tuning.depthFadeWidthM, depthM);
}

/** Pure foam-breakup gate used to verify the shader keeps soft but real zero areas. */
export function waterFoamBreakupGate(breakup: number, tuning = WATER_SHORE_TUNING) {
  return smoothstepCpu(tuning.foamBreakupLow, tuning.foamBreakupHigh, breakup);
}

/** Pure along-shore patch gate: unlike the old constant floor, calm stretches reach exactly zero. */
export function waterFoamPatchGate(cluster: number, tuning = WATER_SHORE_TUNING) {
  return smoothstepCpu(tuning.foamPatchLow, tuning.foamPatchHigh, cluster);
}

/**
 * Preloads the tiled normal and foam maps for water rendering.
 * Resolves immediately in Node unit tests without network calls.
 */
export function waitForWaterTextures(timeoutMs = 5000): Promise<void> {
  if (waterTexturesPromise) return waterTexturesPromise;
  if (typeof window === "undefined" || typeof fetch !== "function" || typeof createImageBitmap !== "function") {
    waterTexturesPromise = Promise.resolve();
    return waterTexturesPromise;
  }

  waterTexturesPromise = (async () => {
    const loader = new TextureLoader();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const work = Promise.all([
        loader.loadAsync(new URL("./water/water_normal_a.webp", window.location.href).href),
        loader.loadAsync(new URL("./water/water_foam.webp", window.location.href).href),
      ]);
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("water textures timeout")), timeoutMs);
      });
      const [nA, foam] = await Promise.race([work, timeout]);
      waterNormalATex.dispose();
      waterFoamTex.dispose();
      waterNormalATex = configureWaterTexture(nA);
      waterFoamTex = configureWaterTexture(foam);
    } catch {
      // Keep neutral fallback textures if water maps are unavailable.
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  })();

  return waterTexturesPromise;
}

export function waterMaterial(surface: SurfaceData, reflection?: ReturnType<typeof reflector>, lakeY = 180.03) {
  const material = new MeshPhysicalNodeMaterial({
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
    roughness: 0.09,
    metalness: 0.0,
    ior: 1.333,
  });

  const p = positionWorld;
  const field = surface.sample(p.xz);
  const surfUv = p.xz.sub(surface.origin).div(surface.size);
  const surfEdgeFade = smoothstep(0.0, 0.025, surfUv.x)
    .mul(smoothstep(0.0, 0.025, surfUv.y))
    .mul(smoothstep(0.0, 0.025, surfUv.x.oneMinus()))
    .mul(smoothstep(0.0, 0.025, surfUv.y.oneMinus()));
  const depth = p.y.sub(field.r).max(0);
  // field.b is zero at the visible waterline and negative inside both lakes and rivers.
  // This narrow world-space coverage fade is shared by body alpha and foam: even where
  // the bed drops quickly, the first metre stays slightly translucent instead of drawing
  // a hard turquoise or white vector contour at aerial resolutions.
  const waterEdgeFade = smoothstep(float(-WATER_SHORE_TUNING.edgeFadeWidthM), float(0), field.b).oneMinus();
  const lake = attribute("lake", "float");
  const footprint = lake.greaterThan(0.5).and(field.a.lessThanEqual(-3)).or(lake.lessThan(0.5).and(field.a.greaterThan(-3)));
  material.maskNode = p.y.sub(field.r).greaterThan(0.002).and(field.b.lessThan(0.30)).and(footprint);

  const flow = mix(vec2(0.9, 0.43589), attribute("flow", "vec2"), smoothstep(-3, 18, field.a).mul(lake.oneMinus()));
  const along = p.xz.dot(flow);
  const across = p.xz.dot(flow.yx.mul(vec2(-1, 1)));
  const dist = cameraPosition.sub(p).length();

  // Broad isotropic domain-warped wind-slick vs wind-ruffled breeze field (70-240 m scale, zero straight stripes, 2 noise calls)
  const windWarp = vec2(
    sin(p.z.mul(0.0085).add(p.x.mul(0.0049))).add(cos(p.x.mul(0.0061).sub(p.z.mul(0.0073))).mul(0.65)),
    sin(p.x.mul(0.0079).sub(p.z.mul(0.0053))).add(cos(p.z.mul(0.0067).add(p.x.mul(0.0057))).mul(0.65)),
  ).mul(0.45);
  const windUvLarge = vec2(
    p.x.mul(0.8387).sub(p.z.mul(0.5446)),
    p.x.mul(0.5446).add(p.z.mul(0.8387)),
  ).mul(0.0046).add(windWarp).add(vec2(time.mul(-0.0028), time.mul(0.0021)));
  const windUvMed = vec2(
    p.x.mul(0.3746).add(p.z.mul(0.9272)),
    p.z.mul(0.3746).sub(p.x.mul(0.9272)),
  ).mul(0.0112).add(windWarp.mul(1.25)).add(vec2(time.mul(0.0036), time.mul(-0.0029)));
  const windLarge = mx_noise_float(windUvLarge).mul(0.5).add(0.5);
  const windMed = mx_noise_float(windUvMed).mul(0.5).add(0.5);
  const windPatch = windLarge.mul(0.62).add(windMed.mul(0.38)).clamp(0, 1);
  const breeze = smoothstep(0.24, 0.76, windPatch);
  const slick = breeze.oneMinus();

  // Cheap aperiodic close ripple helper (zero noise calls; feeds close UV warp, depth ripple & foam breakup)
  const closeRipple = sin(p.x.mul(0.37).sub(p.z.mul(0.29)).add(windMed.mul(3.1)).sub(time.mul(0.95)))
    .mul(0.58)
    .add(cos(p.x.mul(0.23).add(p.z.mul(0.41)).sub(windLarge.mul(2.7)).add(time.mul(0.72))).mul(0.42));
  const closeRippleNorm = closeRipple.mul(0.5).add(0.5).clamp(0, 1);

  // Near-field detail normal maps faded cleanly out BEFORE periodic tiling becomes visible (dist 25..165 m)
  const texFade1 = smoothstep(25, 115, dist).oneMinus();
  const texFade2 = smoothstep(45, 165, dist).oneMinus();
  const microDetail = smoothstep(5, 24, dist).oneMinus();
  const c1 = 0.9563, s1 = 0.2924; // 17 deg
  const c2 = 0.1219, s2 = 0.9925; // 83 deg
  const warpClose = vec2(
    windMed.sub(0.5).mul(1.5).add(closeRipple.mul(0.22)),
    windLarge.sub(0.5).mul(-1.4).sub(closeRipple.mul(0.18)),
  );
  const uvA1 = vec2(p.x.mul(c1).sub(p.z.mul(s1)), p.x.mul(s1).add(p.z.mul(c1))).div(4.2).add(warpClose).add(vec2(time.mul(-0.14), time.mul(0.07)));
  const uvA2 = vec2(p.x.mul(c2).sub(p.z.mul(s2)), p.x.mul(s2).add(p.z.mul(c2))).div(11.5).sub(warpClose).add(vec2(time.mul(0.09), time.mul(-0.08)));
  const uvMicro = vec2(p.x.mul(0.82).sub(p.z.mul(0.57)), p.x.mul(0.57).add(p.z.mul(0.82))).div(1.35).add(vec2(time.mul(-0.19), time.mul(0.15)));
  const r1 = texture(waterNormalATex, uvA1).xy.mul(2).sub(1);
  const r2 = texture(waterNormalATex, uvA2).xy.mul(2).sub(1);
  const rMicro = texture(waterNormalATex, uvMicro).xy.mul(2).sub(1);
  const nA1 = vec2(r1.x.mul(c1).add(r1.y.mul(s1)), r1.x.mul(-s1).add(r1.y.mul(c1))).mul(texFade1.mul(0.044));
  const nA2 = vec2(r2.x.mul(c2).add(r2.y.mul(s2)), r2.x.mul(-s2).add(r2.y.mul(c2))).mul(texFade2.mul(0.034));
  const nLakeClose = nA1.add(nA2).mul(mix(float(0.55), float(1.30), breeze))
    .add(vec2(rMicro.x.mul(0.82).add(rMicro.y.mul(0.57)), rMicro.x.mul(-0.57).add(rMicro.y.mul(0.82))).mul(microDetail.mul(0.026)));

  // Loop-free phase-shifted river flow normals (faded cleanly over dist 35..165 m to avoid aerial tiling)
  const sampleFlowNormal = (wp: typeof p.xz, fd: typeof flow, scale: number, cycleHz: number, flowDist: number) => {
    const p0 = fract(time.mul(cycleHz));
    const p1 = fract(time.mul(cycleHz).add(0.5));
    const w = abs(p0.mul(2).sub(1));
    const n0 = texture(waterNormalATex, wp.mul(scale).sub(fd.mul(p0.mul(flowDist * scale)))).xy.mul(2).sub(1);
    const n1 = texture(waterNormalATex, wp.mul(scale).sub(fd.mul(p1.mul(flowDist * scale))).add(vec2(0.31, 0.57))).xy.mul(2).sub(1);
    return mix(n0, n1, w);
  };
  const flowWeight = smoothstep(-4, 22, field.a).mul(lake.oneMinus());
  const flowTexFade = smoothstep(35, 165, dist).oneMinus();
  const nf1 = sampleFlowNormal(p.xz, flow, 0.14, 0.14, 1.85);
  const nf2 = sampleFlowNormal(p.xz, flow, 0.32, 0.20, 1.25).mul(microDetail.mul(0.75).add(0.25));
  const nFlow = nf1.mul(0.046).add(nf2.mul(0.024)).mul(flowTexFade);
  const nClose = mix(nLakeClose, nFlow, flowWeight.mul(0.75));

  // Close procedural wind wavelets strictly guarded to dist < 28 m (zero ALU cost on flight/aerial views)
  const eps = 0.30;
  const hWave = (xz: typeof p.xz) => {
    const bend = sin(xz.x.mul(0.11).sub(xz.y.mul(0.14))).mul(0.75);
    const u1 = vec2(
      xz.x.mul(0.9205).sub(xz.y.mul(0.3907)).add(bend),
      xz.x.mul(0.3907).add(xz.y.mul(0.9205)).sub(bend.mul(0.7)),
    ).mul(0.34);
    const w1 = mx_noise_float(u1.add(vec2(time.mul(-0.15), time.mul(0.08))));
    const w2 = sin(xz.x.mul(-0.49).sub(xz.y.mul(0.91)).add(w1.mul(2.4)).add(time.mul(0.85))).mul(0.42);
    return w1.add(w2);
  };
  const nearWaveFade = smoothstep(8, 28, dist).oneMinus();
  const waveAmp = mix(float(0.018), float(0.048), breeze);
  const nWaveXZ = Fn(() => {
    const out = vec2(0, 0).toVar();
    If(nearWaveFade.greaterThan(0.005), () => {
      const h0 = hWave(p.xz);
      const hx = hWave(p.xz.add(vec2(eps, 0)));
      const hz = hWave(p.xz.add(vec2(0, eps)));
      out.assign(vec2(h0.sub(hx), h0.sub(hz)).div(eps).mul(nearWaveFade.mul(waveAmp)));
    });
    return out;
  })();

  // Analytic derivatives of 5 incommensurate non-orthogonal phase-bent swells (13.9 m, 23.7 m, 39.1 m, 64.3 m, 113.7 m)
  // Zero periodic waffle/grid at any angle or altitude; breaks up glassy/oily reflections with ~12 ALU ops total
  const medSwellFade = smoothstep(60, 240, dist).oneMinus();
  const midSwellFade = smoothstep(220, 520, dist).oneMinus();
  const ph0 = p.x.mul(0.3411).add(p.z.mul(0.2966)).add(windMed.mul(3.6)).sub(windLarge.mul(2.1)).sub(time.mul(0.68));
  const ph1 = p.x.mul(0.2506).add(p.z.mul(0.0863)).add(windMed.mul(2.9)).sub(time.mul(0.52));
  const ph2 = p.x.mul(0.0628).add(p.z.mul(0.1479)).add(windLarge.mul(3.4)).add(time.mul(0.38));
  const ph3 = p.x.mul(-0.0503).add(p.z.mul(0.0838)).sub(windMed.mul(2.5)).sub(time.mul(0.29));
  const ph4 = p.x.mul(-0.0528).add(p.z.mul(0.0162)).add(windLarge.mul(2.7)).add(time.mul(0.21));
  const cS0 = cos(ph0).mul(medSwellFade.mul(0.024));
  const cS1 = cos(ph1).mul(midSwellFade.mul(0.025));
  const cS2 = cos(ph2).mul(midSwellFade.mul(0.023));
  const cS3 = cos(ph3).mul(0.022);
  const cS4 = cos(ph4).mul(0.020);
  const nBroad = vec2(
    cS0.mul(0.7547).add(cS1.mul(0.9455)).add(cS2.mul(0.3907)).add(cS3.mul(-0.5150)).add(cS4.mul(-0.9563)),
    cS0.mul(0.6561).add(cS1.mul(0.3256)).add(cS2.mul(0.9205)).add(cS3.mul(0.8572)).add(cS4.mul(0.2924)),
  ).mul(mix(float(0.60), float(1.45), breeze));

  const normalXZ = nClose.add(nWaveXZ).add(nBroad);
  const normal = vec3(normalXZ.x, 1, normalXZ.y).normalize();
  material.normalNode = transformNormalToView(normal);

  // Calm sky-reflecting slicks (0.04) vs wind-ruffled darker patches (0.24)
  material.roughnessNode = mix(float(0.04), float(0.24), breeze.mul(0.84).add(windMed.mul(0.16))).clamp(0.04, 0.25);

  const toEye = cameraPosition.sub(p).normalize();
  const ndotv = normal.dot(toEye).clamp(0.001, 1);
  const fresnel = float(0.025).add(float(0.975).mul(float(1).sub(ndotv).max(0.0001).pow(5))).clamp(0.025, 0.88);

  // Calm desaturated STYLE.md coastal slate-turquoise Beer-Lambert water body (never Caribbean neon, never murky brown-grey)
  const shallowClear = smoothstep(0.04, 0.90, depth);
  const shallowTrans = smoothstep(0.0, 0.85, depth);
  const depthMod = depth.add(closeRipple.mul(0.04)).max(0);
  const absorb = float(1).sub(depthMod.mul(0.56).negate().exp());
  const effAbsorb = absorb.max(lake.oneMinus().mul(smoothstep(0.15, 1.2, depth).mul(0.52)));
  const shallowCol = color(new Color("#6A9391"));
  const midCol = color(new Color("#356B70"));
  const deepCol = color(new Color("#204A52"));
  const waterBodyBase = mix(mix(shallowCol, midCol, smoothstep(0.05, 0.44, effAbsorb)), deepCol, smoothstep(0.36, 0.90, effAbsorb));
  // Visible +-14% wind-slick vs wind-ruffled luminance modulation for natural windswept depth from H1/H2/F1/F2
  const windLuma = mix(float(1.14), float(0.86), breeze.mul(effAbsorb.mul(0.80).add(0.20)));
  const macroTone = mix(float(0.95), float(1.05), windMed);
  const waterBody = waterBodyBase.mul(windLuma).mul(macroTone);

  // Crisp, lacy, patchy coastal seafoam breakup right at shallow 0.01..0.32 m waterline (never foggy blur or solid bank outline)
  const isOpenLake = smoothstep(2.0, 28.0, field.a).oneMinus().mul(lake);
  const foamWarp = vec2(closeRipple.mul(0.14), closeRipple.mul(-0.12));
  const foamUv1 = vec2(along.div(3.4).sub(time.mul(0.06)), across.div(3.4).add(time.mul(0.02))).add(foamWarp);
  const foamUv2 = vec2(p.x.mul(0.76).sub(p.z.mul(0.65)), p.x.mul(0.65).add(p.z.mul(0.76))).div(7.2).sub(foamWarp);
  const foamTex1 = texture(waterFoamTex, foamUv1).r;
  const foamTex2 = texture(waterFoamTex, foamUv2).r;

  const foamCluster = sin(p.x.mul(0.17).add(p.z.mul(0.11)).add(windLarge.mul(4.2)))
    .add(cos(p.x.mul(0.13).sub(p.z.mul(0.21)).sub(windMed.mul(3.8))).mul(0.75))
    .mul(0.28).add(0.5).clamp(0, 1);
  const swashWave = sin(depth.mul(25.0).sub(time.mul(1.6)).add(foamCluster.mul(5.0))).mul(0.5).add(0.5);

  const shallowFoamZone = smoothstep(0.008, 0.032, depth).mul(smoothstep(0.05, 0.32, depth).oneMinus());
  const contactLap = smoothstep(0.006, 0.022, depth).mul(smoothstep(0.022, 0.085, depth).oneMinus())
    .mul(float(WATER_SHORE_TUNING.foamContactPeak));
  const foamShape = shallowFoamZone
    .mul(swashWave.mul(float(WATER_SHORE_TUNING.foamSwashWave)).add(float(WATER_SHORE_TUNING.foamSwashBase)))
    .max(contactLap);

  const foamBreakup = foamTex1.mul(0.56).add(foamTex2.mul(0.30)).add(closeRippleNorm.mul(0.14));
  // Both gates reach exactly zero. The old additive patch floor painted a continuous bright
  // waterline everywhere; the wider smoothstep ranges keep the remaining foam lacy instead of hard.
  const foamBreakupMask = smoothstep(float(WATER_SHORE_TUNING.foamBreakupLow), float(WATER_SHORE_TUNING.foamBreakupHigh), foamBreakup);
  const foamPatchMask = smoothstep(float(WATER_SHORE_TUNING.foamPatchLow), float(WATER_SHORE_TUNING.foamPatchHigh), foamCluster);
  const foamDistFade = smoothstep(95, 210, dist).oneMinus();
  const foamFactor = foamBreakupMask
    .mul(foamShape)
    .mul(foamPatchMask)
    .mul(isOpenLake)
    .mul(waterEdgeFade)
    .mul(surfEdgeFade)
    .mul(foamDistFade)
    .mul(float(WATER_SHORE_TUNING.foamStrength))
    .clamp(0, float(WATER_SHORE_TUNING.foamMax));

  // Daylight Voronoi shallow-water caustics (ported from shader_reference/water.gdshader caustics_lod)
  const hash22 = (p2: typeof p.xz) => {
    const p3 = fract(vec3(p2.x, p2.y, p2.x).mul(vec3(0.1031, 0.1030, 0.0973)));
    const shifted = p3.add(dot(p3, vec3(p3.y, p3.z, p3.x).add(33.33)));
    return fract(vec2(shifted.x.add(shifted.y), shifted.x.add(shifted.z)).mul(vec2(shifted.z, shifted.y)));
  };
  const voronoiWeb = (p2: typeof p.xz, ct: Node<"float">) => {
    const i = floor(p2);
    const f = fract(p2);
    const baseG = mix(vec2(-1.0), vec2(0.0), step(vec2(0.5), f));
    const cellDist = (gx: number, gy: number) => {
      const g = baseG.add(vec2(gx, gy));
      const oHash = hash22(i.add(g));
      const o = vec2(0.5).add(sin(vec2(ct).add(oHash.mul(6.2831))).mul(0.40));
      const diff = g.add(o).sub(f);
      return dot(diff, diff);
    };
    const d00 = cellDist(0, 0);
    const d10 = cellDist(1, 0);
    const d01 = cellDist(0, 1);
    const d11 = cellDist(1, 1);
    const f1 = d00.min(d10).min(d01.min(d11));
    const f2 = d00.max(d10).min(d01.max(d11)).min(d00.min(d10).max(d01.min(d11)));
    const e = float(1.0).sub(sqrt(f2.max(0.0001)).sub(sqrt(f1.max(0.0001))).mul(1.48)).clamp(0, 1);
    return e.mul(e).mul(sqrt(e.max(0.0001)));
  };
  const caustVis = smoothstep(0.03, 0.24, depth).mul(depth.mul(-0.52).exp()).mul(smoothstep(45, 110, dist).oneMinus());
  const caust = Fn(() => {
    const out = float(0).toVar();
    If(caustVis.greaterThan(0.005), () => {
      const ct = time.mul(0.38);
      const caustP = p.xz.add(normalXZ.mul(0.45)).mul(0.55);
      const cp1 = vec2(caustP.x.mul(0.866).sub(caustP.y.mul(0.5)), caustP.x.mul(0.5).add(caustP.y.mul(0.866)))
        .add(vec2(ct.mul(0.08), ct.mul(0.05)));
      const cp2 = vec2(caustP.x.mul(0.707).add(caustP.y.mul(0.707)), caustP.x.mul(-0.707).add(caustP.y.mul(0.707)))
        .mul(1.32)
        .sub(vec2(ct.mul(0.07), ct.mul(-0.09)));
      const caust1 = voronoiWeb(cp1, ct);
      const caust2 = voronoiWeb(cp2, ct.mul(-0.86));
      out.assign(caust1.mul(caust2).mul(1.35).add(caust1.add(caust2).mul(0.24)).clamp(0, 1.3));
    });
    return out;
  })();

  // Physical Schlick Fresnel + Real-Time Planar Reflection (`reflector()`) blended smoothly with palette-matched analytic sky
  const reflectDir = reflect(toEye.negate(), normal);
  const reflY = reflectDir.y.clamp(0, 1);
  const reflHorizon = color(swatch("cloud_cream").clone().lerp(swatch("haze"), 0.25));
  const reflMid = color(swatch("sky_blue").clone().lerp(swatch("haze"), 0.14));
  const reflZenith = color(swatch("sky_blue").clone().multiply(new Color(0.52, 0.68, 0.86)));
  const analyticSky = mix(mix(reflHorizon, reflMid, smoothstep(0.01, 0.22, reflY)), reflZenith, smoothstep(0.18, 0.65, reflY));

  let finalRefl: Node<"vec3"> = analyticSky.mul(0.66);
  if (reflection) {
    // Distort the planar reflection with a filtered copy of the wave slope, not with the
    // full lighting normal. Close lighting ripples may stay crisp while the mirror image
    // remains coherent; shallow/wind-ruffled water still receives a stronger breakup.
    const reflectionZone = smoothstep(
      float(WATER_REFLECTION_DISTORTION.shoreFullDepthM),
      float(WATER_REFLECTION_DISTORTION.shoreFadeDepthM),
      depth,
    ).oneMinus().max(breeze.mul(float(WATER_REFLECTION_DISTORTION.breezeAgitation)));
    const reflectionDistanceScale = smoothstep(
      float(WATER_REFLECTION_DISTORTION.distanceNearM),
      float(WATER_REFLECTION_DISTORTION.distanceFarM),
      dist,
    ).oneMinus()
      .mul(float(1 - WATER_REFLECTION_DISTORTION.distanceFloor))
      .add(float(WATER_REFLECTION_DISTORTION.distanceFloor));
    // Use the macroscopic incidence of the flat water plane, not the noisy microfacet ndotv,
    // so the view-angle filter itself cannot imprint additional wave-scale brightness bands.
    const viewElevation = toEye.y.clamp(0, 1);
    const reflectionViewScale = smoothstep(
      float(WATER_REFLECTION_DISTORTION.steepViewStart),
      float(WATER_REFLECTION_DISTORTION.steepViewEnd),
      viewElevation,
    ).oneMinus()
      .mul(float(1 - WATER_REFLECTION_DISTORTION.steepViewFloor))
      .add(float(WATER_REFLECTION_DISTORTION.steepViewFloor));
    const reflectionSlopeScale = mix(
      float(WATER_REFLECTION_DISTORTION.calmNormalScale),
      float(WATER_REFLECTION_DISTORTION.roughNormalScale),
      reflectionZone,
    ).mul(reflectionDistanceScale).mul(reflectionViewScale);
    const reflectionXZ = normalXZ.mul(reflectionSlopeScale);

    // World x/z is not screen x/y. Project the slope into the camera azimuth frame:
    // slope across the view shifts horizontally, slope along the view shifts vertically.
    // This removes the artificial world-axis-aligned horizontal/rectangular banding while
    // keeping the physically important in-plane reflection perturbation.
    const viewXZ = cameraPosition.xz.sub(p.xz);
    const viewLenXZ = viewXZ.length().max(0.75);
    const viewAlong = viewXZ.div(viewLenXZ);
    const viewAcross = vec2(viewAlong.y, viewAlong.x.negate());
    const reflectionUVOffset = vec2(
      reflectionXZ.dot(viewAcross).mul(float(WATER_REFLECTION_DISTORTION.uvScaleX)),
      reflectionXZ.dot(viewAlong).mul(float(WATER_REFLECTION_DISTORTION.uvScaleY)),
    );
    reflection.uvNode = screenUV.flipX().add(reflectionUVOffset).clamp(vec2(0.002), vec2(0.998));

    const flatLake = smoothstep(0.35, 3.2, p.y.sub(lakeY).abs()).oneMinus();
    const reflTone = reflection.rgb.div(reflection.rgb.add(vec3(1.15))).mul(0.78);
    const planarBlend = mix(float(0.54), float(0.30), breeze);
    finalRefl = mix(analyticSky.mul(0.66), mix(analyticSky.mul(0.66), reflTone, planarBlend), flatLake);
  }

  const shoreAlpha = smoothstep(float(0.0), float(WATER_SHORE_TUNING.depthFadeWidthM), depth).mul(waterEdgeFade).mul(surfEdgeFade);
  const riverOrDeep = shallowClear.max(lake.oneMinus().mul(0.80));
  const reflFloor = mix(float(0.03), mix(float(0.07), float(0.18), slick), shallowClear.max(lake.oneMinus().mul(0.45)));
  const reflRaw = fresnel.mul(mix(float(0.32), float(0.42), slick)).add(mix(float(0.025), float(0.12), slick));
  const reflMix = reflRaw.mul(riverOrDeep.mul(0.82).add(0.18)).mul(foamFactor.oneMinus()).clamp(reflFloor, 0.36);

  // Energy-conserving split: desaturated coastal underwater diffuse + restrained subsurface scatter + tempered reflection
  const bodyDiffuse = waterBody.mul(reflMix.mul(0.48).oneMinus());
  material.colorNode = mix(bodyDiffuse, color(swatch("cloud_cream")), foamFactor);

  const shallowBand = smoothstep(0.05, 0.45, depth).mul(smoothstep(0.65, 2.8, depth).oneMinus());
  const waterScatter = waterBody.mul(mix(float(0.035), float(0.070), shallowBand.mul(lake))).mul(foamFactor.oneMinus());
  const depthAlpha = mix(float(0.06), float(0.94), effAbsorb.mul(shallowTrans.mul(0.55).add(0.45))).max(fresnel.mul(0.20).mul(shallowClear));
  const foamOpacity = foamFactor.mul(smoothstep(0.0, 0.015, depth)).mul(surfEdgeFade);
  material.opacityNode = shoreAlpha.mul(depthAlpha).max(foamOpacity).clamp(0, 0.98);
  material.specularIntensityNode = mix(float(0.14), float(0.34), slick).mul(shallowClear).mul(shoreAlpha);

  // Crisp ref_10 directional golden sun-glint shimmer + sunlit wavelet crest catch + warm shallow caustics (reflMix <= 0.36)
  const glintNormal = vec3(normalXZ.x.mul(4.0), 1, normalXZ.y.mul(4.0)).normalize();
  const half = toEye.add(vec3(sunDirection)).normalize();
  const ndoth = glintNormal.dot(half).max(0.0001);
  const sunGlint = ndoth.pow(10).mul(0.24).add(ndoth.pow(36).mul(1.65)).add(ndoth.pow(140).mul(4.8));
  const waveSlope = normalXZ.length();
  const sunFace = glintNormal.dot(vec3(sunDirection)).clamp(0, 1);
  const grazing = ndotv.oneMinus().clamp(0, 1);
  const crestCatch = smoothstep(0.025, 0.14, waveSlope)
    .mul(sunFace.pow(2))
    .mul(grazing.pow(1.5))
    .mul(smoothstep(20, 460, dist).oneMinus().mul(0.75).add(0.25))
    .mul(0.44);
  const sparkle = sunGlint.mul(mix(float(0.80), float(1.40), breeze)).add(crestCatch)
    .mul(foamFactor.oneMinus())
    .mul(shoreAlpha);
  const causticGlow = color(new Color("#F2EAD2")).mul(caust.mul(0.38).mul(caustVis)).mul(smoothstep(0.015, 0.12, depth)).mul(surfEdgeFade);
  const foamAmbient = color(swatch("cloud_cream")).mul(foamFactor.mul(0.18));
  material.emissiveNode = finalRefl.mul(reflMix).add(waterScatter).mul(shoreAlpha)
    .add(color(new Color("#FFF4D8")).mul(sparkle))
    .add(causticGlow)
    .add(foamAmbient);

  return material;
}

export function waterSurface(region: WaterRegion, surface: SurfaceData, onReflectionPass?: (active: boolean) => void) {
  const group = new Group();
  const lakeY = (region.lakes[0]?.water_y ?? 180) + 0.03;
  let reflection: ReturnType<typeof reflector> | undefined;
  if (typeof window !== "undefined") {
    reflection = reflector(WATER_REFLECTION_PASS);
    reflection.target.position.set(900, lakeY, 1900);
    reflection.target.rotation.x = -Math.PI / 2;
    group.add(reflection.target);

    const lakeOutline = region.lakes[0]?.outline;
    let lakeBounds: Box3 | null = null;
    if (lakeOutline?.length) {
      lakeBounds = new Box3();
      for (const [lx, lz] of lakeOutline) {
        lakeBounds.expandByPoint(new Vector3(lx, lakeY, lz));
      }
      lakeBounds.min.x -= 140;
      lakeBounds.min.z -= 140;
      lakeBounds.min.y = lakeY - 4;
      lakeBounds.max.x += 140;
      lakeBounds.max.z += 140;
      lakeBounds.max.y = lakeY + 4;
    }
    const projScreenMatrix = new Matrix4();
    const lakeFrustum = new Frustum();

    // Filter reflection pass to REFLECTION_LAYER and reuse main-pass CSM cascade shadow maps (zero extra shadow renders)
    type ShadowRef = { autoUpdate: boolean; needsUpdate: boolean; shadowNode?: { lights?: Array<{ shadow?: { autoUpdate: boolean; needsUpdate: boolean } }> } };
    const baseReflector = reflection.reflector as unknown as {
      getVirtualCamera: (cam: unknown) => { layers: { set: (l: number) => void } };
      updateBefore: (frame: {
        frameId: number;
        camera: PerspectiveCamera;
        scene: { children: Array<{ isDirectionalLight?: boolean; layers: { enable: (l: number) => void }; shadow?: ShadowRef }> };
      }) => unknown;
    };
    const origUpdateBefore = baseReflector.updateBefore.bind(baseReflector);
    let warmed = false;
    baseReflector.updateBefore = (frame) => {
      if (warmed && lakeBounds) {
        const cam = frame.camera;
        cam.updateMatrixWorld();
        projScreenMatrix.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
        lakeFrustum.setFromProjectionMatrix(projScreenMatrix, cam.coordinateSystem);
        if (!lakeFrustum.intersectsBox(lakeBounds)) return false;
      }
      const vCam = baseReflector.getVirtualCamera(frame.camera);
      vCam.layers.set(REFLECTION_LAYER);
      const paused: Array<{ shadow: { autoUpdate: boolean; needsUpdate: boolean }; auto: boolean; needs: boolean }> = [];
      const pauseShadow = (sh?: { autoUpdate: boolean; needsUpdate: boolean }) => {
        if (!sh) return;
        paused.push({ shadow: sh, auto: sh.autoUpdate, needs: sh.needsUpdate });
        sh.autoUpdate = false;
        sh.needsUpdate = false;
      };
      for (const child of frame.scene.children) {
        if (child.isDirectionalLight) {
          child.layers.enable(REFLECTION_LAYER);
          if (warmed && child.shadow) {
            pauseShadow(child.shadow);
            for (const lw of child.shadow.shadowNode?.lights ?? []) pauseShadow(lw.shadow);
          }
        }
      }
      onReflectionPass?.(true);
      try {
        return origUpdateBefore(frame);
      } finally {
        onReflectionPass?.(false);
        for (const p of paused) {
          p.shadow.autoUpdate = p.auto;
          p.shadow.needsUpdate = p.needs;
        }
        warmed = true;
      }
    };
  }
  const mesh = new Mesh(buildWaterGeometry(region), waterMaterial(surface, reflection, lakeY));
  mesh.receiveShadow = true;
  group.add(mesh);
  return group;
}
