import {
  ACESFilmicToneMapping, AgXToneMapping, NeutralToneMapping, RenderPipeline,
  Vector2, Vector3, type Camera, type Node, type Scene, type ToneMapping, type WebGPURenderer,
} from "three/webgpu";
import {
  Fn, If, color, dot, float, interleavedGradientNoise, mix, pass, screenCoordinate,
  screenUV, smoothstep, uniform, vec2, vec3, vec4,
} from "three/tsl";
import { ao } from "three/addons/tsl/display/GTAONode.js";
import { bloom } from "three/addons/tsl/display/BloomNode.js";
import { sunDirection } from "./atmosphere.ts";
import { swatch } from "./palette.ts";
import type { QualityLevel } from "./quality.ts";

export type ToneMappingName = "aces" | "neutral" | "agx";

export interface ToneMappingConfig {
  name: ToneMappingName;
  toneMapping: ToneMapping;
  exposure: number;
}

export interface PostProcessingConfig {
  enabled: boolean;
  ao: boolean;
  aoResolutionScale: number;
  bloom: boolean;
  godrays: boolean;
  grade: boolean;
  vignette: boolean;
}

const TONE_MAPPINGS: Record<ToneMappingName, ToneMapping> = {
  aces: ACESFilmicToneMapping,
  neutral: NeutralToneMapping,
  agx: AgXToneMapping,
};

export const DEFAULT_TONE_MAPPING: ToneMappingName = "aces";
export const DEFAULT_EXPOSURE = 0.90;

function parseBoolFlag(params: URLSearchParams, key: string, fallback: boolean): boolean {
  if (!params.has(key)) return fallback;
  const raw = (params.get(key) ?? "").trim().toLowerCase();
  if (["0", "false", "no", "off"].includes(raw)) return false;
  if (["", "1", "true", "yes", "on"].includes(raw)) return true;
  throw new Error(`${key}: 0|1|true|false erwartet`);
}

export function resolveToneMapping(params: URLSearchParams): ToneMappingConfig {
  const rawName = (params.get("tonemapping") ?? DEFAULT_TONE_MAPPING).trim().toLowerCase() || DEFAULT_TONE_MAPPING;
  if (!(rawName in TONE_MAPPINGS)) {
    throw new Error("tonemapping: aces|neutral|agx erwartet");
  }
  const name = rawName as ToneMappingName;
  const exposure = params.has("exposure") ? Number(params.get("exposure")) : DEFAULT_EXPOSURE;
  if (!Number.isFinite(exposure) || exposure < 0.1 || exposure > 5) {
    throw new Error("exposure: Zahl zwischen 0.1 und 5 erwartet");
  }
  return { name, toneMapping: TONE_MAPPINGS[name], exposure };
}

export function resolvePostConfig(quality: QualityLevel, params: URLSearchParams): PostProcessingConfig {
  const tier = quality.name;
  const tierPost = tier !== "low";
  const postMaster = parseBoolFlag(params, "post", tierPost);
  if (!postMaster) {
    return {
      enabled: false,
      ao: false,
      aoResolutionScale: tier === "ultra" ? 0.75 : 0.5,
      bloom: false,
      godrays: false,
      grade: false,
      vignette: false,
    };
  }
  const aoEnabled = parseBoolFlag(params, "ao", tier === "high" || tier === "ultra");
  const bloomEnabled = parseBoolFlag(params, "bloom", tier !== "low");
  const godraysEnabled = parseBoolFlag(params, "godrays", tier === "high" || tier === "ultra");
  const gradeEnabled = parseBoolFlag(params, "grade", tier !== "low");
  const vignetteEnabled = parseBoolFlag(params, "vignette", tier !== "low");
  const anyActive = aoEnabled || bloomEnabled || godraysEnabled || gradeEnabled || vignetteEnabled;

  return {
    enabled: anyActive,
    ao: aoEnabled,
    aoResolutionScale: tier === "ultra" ? 0.75 : 0.5,
    bloom: bloomEnabled,
    godrays: godraysEnabled,
    grade: gradeEnabled,
    vignette: vignetteEnabled,
  };
}

export function createPostProcessing(
  renderer: WebGPURenderer,
  scene: Scene,
  camera: Camera,
  quality: QualityLevel,
  params: URLSearchParams,
) {
  const config = resolvePostConfig(quality, params);
  if (!config.enabled) {
    return {
      config,
      enabled: false,
      render: () => { renderer.render(scene, camera); },
      dispose: () => {},
    };
  }

  // Single geometry pass (no separate normal/depth pre-pass so draw calls are never doubled).
  // Force samples = 1 on the pass renderTarget so depthTexture is single-sampled (texture_depth_2d),
  // which WGSL requires for GTAO's depth gather / textureLoad normal reconstruction.
  const scenePass = pass(scene, camera, { samples: 1 } as never);
  (scenePass as unknown as { options: { samples?: number }; renderTarget: { samples: number } }).options.samples = 1;
  (scenePass as unknown as { renderTarget: { samples: number } }).renderTarget.samples = 1;

  const scenePassColor = scenePass.getTextureNode("output");
  const scenePassDepth = scenePass.getTextureNode("depth");

  let colorOut: Node<"vec3"> = scenePassColor.rgb;

  // 1. Screen-Space Ambient Occlusion (GTAO tightened near camera so distant ridges never get dark halos)
  if (config.ao) {
    const aoPass = ao(scenePassDepth, null as unknown as Node, camera);
    aoPass.resolutionScale = config.aoResolutionScale;
    aoPass.radius.value = 1.6;
    aoPass.thickness.value = 2.6;
    aoPass.samples.value = quality.name === "ultra" ? 12 : 6;
    const aoTex = aoPass.getTextureNode();

    const o1 = vec2(0.0012, 0.0021);
    const o2 = vec2(-0.0012, 0.0021);
    const aoSmooth = aoTex.sample(screenUV).r
      .add(aoTex.sample(screenUV.add(o1)).r)
      .add(aoTex.sample(screenUV.sub(o1)).r)
      .add(aoTex.sample(screenUV.add(o2)).r)
      .mul(0.25);

    const depthCenter = scenePassDepth.sample(screenUV).r;
    const nearAO = smoothstep(0.9978, 0.9942, depthCenter);
    colorOut = colorOut.mul(mix(float(1.0), aoSmooth, nearAO.mul(0.56)));
  }

  // 2. Screen-Space Sunbeams / Godrays when looking toward the sun (e.g. G2 canopy backlight)
  const sunScreenUV = uniform(new Vector2(0.5, 0.25));
  const sunVisibility = uniform(0);
  const camForward = new Vector3();
  const sunWorldPos = new Vector3();

  if (config.godrays) {
    const computeShaft = Fn(() => {
      const shaftOut = float(0).toVar();
      If(sunVisibility.greaterThan(0.01), () => {
        const toSun = sunScreenUV.sub(screenUV);
        const distToSun = toSun.length();
        const radialFalloff = smoothstep(1.18, 0.0, distToSun);
        const clampedRay = toSun.div(distToSun.max(0.001)).mul(distToSun.min(0.68));
        const jitter = interleavedGradientNoise(screenCoordinate);

        let shaftAcc: Node<"float"> = float(0);
        const STEPS = 12;
        let weightSum = 0;
        for (let i = 1; i <= STEPS; i++) {
          const w = 0.91 ** i;
          weightSum += w;
          const t = float(i - 0.5).add(jitter.sub(0.5)).div(STEPS);
          const sampleUV = screenUV.add(clampedRay.mul(t)).clamp(vec2(0.002, 0.002), vec2(0.998, 0.998));
          const d = scenePassDepth.sample(sampleUV).r;
          const skyMask = smoothstep(0.9965, 0.9998, d);
          const sampleCol = scenePassColor.sample(sampleUV).rgb;
          const sampleLuma = dot(sampleCol, vec3(0.2126, 0.7152, 0.0722)).clamp(0.25, 2.5);
          shaftAcc = shaftAcc.add(skyMask.mul(sampleLuma).mul(w));
        }
        shaftOut.assign(shaftAcc.div(weightSum).mul(radialFalloff).mul(sunVisibility));
      });
      return shaftOut;
    });
    const rayColor = mix(color(swatch("cloud_cream")), color(swatch("accent_ochre")), 0.62);
    colorOut = colorOut.add(rayColor.mul(computeShaft().mul(0.54)));
  }

  // 3. Soft sunlit highlight halation Bloom (threshold ~0.90, strength ~0.18, radius ~0.44)
  if (config.bloom) {
    const bloomPass = bloom(scenePassColor, 0.18, 0.44, 0.90);
    bloomPass.setResolutionScale(0.2);
    colorOut = colorOut.add(bloomPass.rgb);
  }

  // 4. Color Grading: gentle shadow floor recovery + smooth highlight rolloff
  if (config.grade) {
    const luma = dot(colorOut, vec3(0.2126, 0.7152, 0.0722)).max(0.0001);
    const blackLift = smoothstep(0.04, 0.0, luma).mul(0.008);
    colorOut = colorOut.add(vec3(blackLift));
    const lumaLifted = luma.add(blackLift);
    const toe = mix(float(0.96), float(1.02), smoothstep(0.03, 0.25, lumaLifted));
    const highlightCompress = mix(float(1.0), float(0.80), smoothstep(0.55, 1.18, lumaLifted));
    colorOut = colorOut.mul(toe.mul(highlightCompress)).mul(vec3(1.015, 1.005, 0.975));

    const yGraded = dot(colorOut, vec3(0.2126, 0.7152, 0.0722));
    colorOut = mix(vec3(yGraded), colorOut, float(1.05)).max(vec3(0));
  }

  // 5. Subtle Edge Vignette
  if (config.vignette) {
    const centered = screenUV.sub(vec2(0.5, 0.5)).mul(vec2(1.15, 1.0));
    const vig = float(1.0).sub(dot(centered, centered).mul(0.24)).clamp(0.78, 1.0);
    colorOut = colorOut.mul(vig);
  }

  const pipeline = new RenderPipeline(renderer, vec4(colorOut, 1.0));

  function updateSunUniforms() {
    if (!config.godrays) return;
    camera.getWorldDirection(camForward);
    const cosAngle = camForward.dot(sunDirection);
    if (cosAngle <= 0.15) {
      sunVisibility.value = 0;
      return;
    }
    sunWorldPos.copy(camera.position).addScaledVector(sunDirection, 1000).project(camera);
    const u = sunWorldPos.x * 0.5 + 0.5;
    const v = 0.5 - sunWorldPos.y * 0.5;
    sunScreenUV.value.set(Math.max(-0.35, Math.min(1.35, u)), Math.max(-0.35, Math.min(1.35, v)));
    const angleFade = Math.min(1, Math.max(0, (cosAngle - 0.18) / 0.62));
    const edgeDist = Math.max(Math.abs(sunWorldPos.x), Math.abs(sunWorldPos.y));
    const screenFade = Math.min(1, Math.max(0, (1.45 - edgeDist) / 0.55));
    sunVisibility.value = angleFade * screenFade;
  }

  return {
    config,
    enabled: true,
    render: () => {
      updateSunUniforms();
      pipeline.render();
    },
    dispose: () => {
      pipeline.dispose();
    },
  };
}
