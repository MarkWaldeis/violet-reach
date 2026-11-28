import {
  Color, DirectionalLight, HemisphereLight, MathUtils, Scene, Vector3,
} from "three/webgpu";
import { CSMShadowNode } from "three/addons/csm/CSMShadowNode.js";
import {
  cameraPosition, cameraProjectionMatrixInverse, cameraWorldMatrix, color, fog, mix,
  mx_noise_float, positionWorld, screenUV, smoothstep, vec2, vec3, vec4,
} from "three/tsl";
import { worldTime as time } from "./world-time.ts";
import { swatch } from "./palette.ts";
import {
  buildCelestialBodiesNode, createCloudBillboards, createSkyEnvironmentTexture,
} from "./sky-bodies.ts";
import { REFLECTION_LAYER, SHADOW_PROXY_LAYER } from "./quality.ts";

export const sunDirection = new Vector3(-0.56, 0.52, -0.62).normalize();

export interface ShadowSettings { shadows: boolean; shadowMapSize: number; shadowCascades: number }
export const DEFAULT_SHADOWS: ShadowSettings = { shadows: true, shadowMapSize: 2048, shadowCascades: 4 };

export function setupAtmosphere(scene: Scene, quality: ShadowSettings = DEFAULT_SHADOWS) {
  const clip = vec4(screenUV.mul(vec2(2, -2)).add(vec2(-1, 1)), 1, 1);
  const direction = cameraWorldMatrix.mul(vec4(cameraProjectionMatrixInverse.mul(clip).xyz.normalize(), 0)).xyz.normalize();

  // 1. Deep azure upper sky + airy mid-sky + crisp warm golden-cream horizon band
  const zenithColor = color(swatch("sky_blue").clone().multiply(new Color(0.42, 0.62, 0.96)));
  const midSkyColor = color(swatch("sky_blue").clone().multiply(new Color(0.76, 0.87, 1.00)));
  const horizonBase = color(swatch("cloud_cream").clone().lerp(swatch("haze"), 0.22).lerp(new Color("#F2E1C0"), 0.24)).mul(1.02);
  const zenithT = smoothstep(0.08, 0.68, direction.y);
  const horizon = smoothstep(-0.02, 0.24, direction.y).oneMinus().pow(1.75);
  const sunDot = direction.dot(vec3(sunDirection)).max(0);
  const horizonGlow = horizon.mul(sunDot.pow(3).mul(0.28).add(0.96));
  const skyGradient = mix(midSkyColor, zenithColor, zenithT);
  const skyColor = mix(skyGradient, horizonBase.mul(horizonGlow), horizon.mul(0.82));

  // 2. Celestial bodies (monumental banded giant + angular shattered moons)
  const skyWithBodies = buildCelestialBodiesNode(direction, skyColor, sunDirection);

  // 3. Delicate patchy multi-octave feathery high-altitude cirrus wisps (zero thick diagonal bars)
  const drift2 = vec2(time.mul(0.0020), time.mul(0.0007));
  const shellDenom = direction.y.max(0.04).add(0.16);
  const shellUV = direction.xz.div(shellDenom);
  const cirrusPatch = smoothstep(0.05, 0.65, mx_noise_float(vec3(shellUV.mul(0.85).add(drift2), 0.7)));
  const cirrusCoord = vec2(shellUV.x.mul(1.65), shellUV.y.mul(2.95));
  const c1 = mx_noise_float(vec3(cirrusCoord.add(drift2), 2.3));
  const c2 = mx_noise_float(vec3(cirrusCoord.mul(2.4).add(drift2.mul(1.3)), 5.1)).mul(0.55);
  const cirrus = smoothstep(0.32, 0.88, c1.add(c2))
    .mul(cirrusPatch)
    .mul(smoothstep(0.10, 0.34, direction.y))
    .mul(0.24);
  const cream = color(swatch("cloud_cream")).mul(1.24);
  const clouds = mix(skyWithBodies, cream, cirrus);

  // Sun disk + warm sunlit atmospheric aureole
  const glow = sunDot.pow(36).mul(0.34).add(sunDot.pow(10).mul(0.28)).add(sunDot.pow(3).mul(0.14)).add(smoothstep(0.99976, 0.99992, sunDot).mul(5.5));
  const sunHalo = sunDot.pow(6).mul(horizon).mul(0.34);
  scene.backgroundNode = clouds.add(color(swatch("accent_ochre")).mul(glow.add(sunHalo)));

  // 3b. 3D Instanced Six-Way lightmap cloud billboards from 2048x1024 Cycles atlas (zero seams)
  const cloudBillboards = createCloudBillboards(sunDirection);
  scene.add(cloudBillboards);

  // 4. Balanced aerial perspective starting beyond 300 m (softens far ridges while keeping foreground/H1 crisp)
  const viewVec = positionWorld.sub(cameraPosition);
  const distance = viewVec.length();
  const viewDir = viewVec.div(distance.max(0.001));
  const clearDist = distance.sub(300).max(0);
  const aerial = clearDist.mul(0.00022).negate().exp().oneMinus();
  const valleyMist = smoothstep(182, 212, positionWorld.y).oneMinus()
    .mul(smoothstep(500, 2200, distance))
    .mul(0.16);
  const forward = viewDir.dot(vec3(sunDirection)).max(0).pow(4);
  const coolAerial = mix(
    color(swatch("sky_blue")).mul(0.88),
    color(swatch("haze")),
    smoothstep(900, 5200, distance).mul(0.45).add(0.20),
  );
  const warmAerial = color(new Color("#E8DFCC"));
  const hazeColor = mix(coolAerial, warmAerial, forward.mul(0.58).add(valleyMist.mul(0.55)).clamp(0, 1));
  scene.fogNode = fog(hazeColor, aerial.add(valleyMist).clamp(0, 0.50));

  // 5. Environment map from our own sky + luminous HemisphereLight (lifts canopy/trunk shadows cleanly)
  scene.environment = createSkyEnvironmentTexture(sunDirection);
  scene.environmentIntensity = 0.68;

  // 6. Warm crisp sun + 4 CSM cascades
  const sunColor = new Color("#FFF4E0");
  const sun = new DirectionalLight(sunColor, 4.2);
  sun.position.copy(sunDirection).multiplyScalar(1000);
  sun.layers.enable(REFLECTION_LAYER);
  const shadows = quality.shadows && quality.shadowCascades > 0;
  sun.castShadow = shadows;
  sun.shadow.mapSize.set(quality.shadowMapSize, quality.shadowMapSize);
  sun.shadow.bias = -0.00012;
  sun.shadow.normalBias = 0.45;
  sun.shadow.camera.layers.enable(SHADOW_PROXY_LAYER);
  const csm = shadows
    ? new CSMShadowNode(sun, {
      cascades: quality.shadowCascades,
      maxFar: 950,
      mode: "practical",
      lightMargin: 120,
    })
    : undefined;
  if (csm) {
    csm.fade = true;
    // Practical split with higher logarithmic weight (lambda = 0.85) for a tight first cascade (~30 m)
    const csmInternal = csm as unknown as {
      cascades: number;
      maxFar: number;
      camera: { near: number; far: number } | null;
      breaks: number[];
      _getBreaks?: () => void;
    };
    csmInternal._getBreaks = () => {
      if (!csmInternal.camera) return;
      const near = Math.max(0.1, csmInternal.camera.near);
      const far = Math.min(csmInternal.camera.far, csmInternal.maxFar);
      const amount = csmInternal.cascades;
      csmInternal.breaks.length = 0;
      const lambda = 0.85;
      for (let i = 1; i < amount; i++) {
        const u = (near + (far - near) * (i / amount)) / far;
        const l = (near * (far / near) ** (i / amount)) / far;
        csmInternal.breaks.push(MathUtils.lerp(u, l, lambda));
      }
      csmInternal.breaks.push(1);
    };
    sun.shadow.shadowNode = csm;
  }

  const skyFill = new Color(swatch("sky_blue")).lerp(new Color(swatch("cloud_cream")), 0.65);
  const groundFill = new Color(swatch("stone_weathered")).lerp(new Color(swatch("monument_shadow")), 0.35);
  const hemi = new HemisphereLight(skyFill, groundFill, 0.48);
  hemi.layers.enable(REFLECTION_LAYER);
  scene.add(sun, sun.target, hemi);
  return {
    sun,
    update: (camera: { position: { x: number; y: number; z: number } }) => {
      cloudBillboards.position.set(camera.position.x, camera.position.y * 0.15, camera.position.z);
    },
    resize: () => { if (csm?.camera) csm.updateFrustums(); },
  };
}
