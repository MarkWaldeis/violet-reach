import {
  Color, DirectionalLight, HemisphereLight, Scene, Vector3,
} from "three/webgpu";
import { CSMShadowNode } from "three/addons/csm/CSMShadowNode.js";
import { cameraPosition, cameraProjectionMatrixInverse, cameraWorldMatrix, color, fog, mix, mx_noise_float, positionWorld, screenUV, smoothstep, vec2, vec3, vec4 } from "three/tsl";
import { worldTime as time } from "./world-time.ts";
import { swatch } from "./palette.ts";

export const sunDirection = new Vector3(-0.56, 0.52, -0.62).normalize();

export interface ShadowSettings { shadows: boolean; shadowMapSize: number; shadowCascades: number }
const DEFAULT_SHADOWS: ShadowSettings = { shadows: true, shadowMapSize: 2048, shadowCascades: 3 };

export function setupAtmosphere(scene: Scene, quality: ShadowSettings = DEFAULT_SHADOWS) {
  const clip = vec4(screenUV.mul(vec2(2, -2)).add(vec2(-1, 1)), 1, 1);
  const direction = cameraWorldMatrix.mul(vec4(cameraProjectionMatrixInverse.mul(clip).xyz.normalize(), 0)).xyz.normalize();
  const horizon = smoothstep(-0.04, 0.38, direction.y).oneMinus();
  const skyColor = mix(color(swatch("sky_blue")), color(swatch("haze")).mul(1.3), horizon);
  const drift = vec3(time.mul(0.003), 0, time.mul(0.001));
  const broad = mx_noise_float(direction.mul(vec3(3.2, 7, 3.2)).add(drift));
  const wisps = mx_noise_float(direction.mul(vec3(16, 38, 16)).add(drift)).mul(0.23);
  const field = broad.add(wisps);
  const overhead = smoothstep(0.02, 0.42, field).mul(0.38);
  const bank = smoothstep(-0.18, 0.3, field)
    .mul(smoothstep(-0.07, 0.015, direction.y))
    .mul(smoothstep(0.045, 0.24, direction.y).oneMinus());
  const cloud = overhead.add(bank.mul(0.75)).clamp();
  const sunDot = direction.dot(vec3(sunDirection)).max(0);
  const cream = color(swatch("cloud_cream")).mul(1.5);
  const cloudLight = mx_noise_float(direction.mul(vec3(6, 14, 6)).add(drift).add(vec3(0.6, 1.2, 0.4)));
  const litCloud = mix(color(swatch("haze")).mul(0.95), cream,
    smoothstep(-0.35, 0.4, cloudLight.add(sunDot.mul(0.3))));
  const clouds = mix(skyColor, litCloud, cloud.mul(0.9));
  const glow = sunDot.pow(48).mul(0.35).add(smoothstep(0.99978, 0.9999, sunDot).mul(5));
  scene.backgroundNode = clouds.add(color(swatch("accent_ochre")).mul(glow.add(sunDot.pow(12).mul(horizon).mul(0.45))));

  const distance = positionWorld.sub(cameraPosition).length();
  const valley = positionWorld.y.add(cameraPosition.y).mul(0.5).sub(180).max(0).mul(-0.0015).exp();
  const density = valley.mul(0.000065).add(0.000035);
  const haze = distance.sub(300).max(0).mul(density).negate().exp().oneMinus();
  const veil = bank.mul(smoothstep(1800, 6500, distance)).mul(0.48);
  const forward = positionWorld.sub(cameraPosition).normalize().dot(vec3(sunDirection)).max(0).pow(8);
  const brightening = smoothstep(800, 6500, distance).mul(0.5).add(forward.mul(0.35)).add(veil).clamp();
  const hazeColor = mix(color(swatch("haze")).mul(1.25), cream.mul(1.15), brightening);
  scene.fogNode = fog(hazeColor, haze.add(veil).clamp(0, 0.82));

  const sun = new DirectionalLight(swatch("monument_white"), 3);
  sun.position.copy(sunDirection).multiplyScalar(1000);
  const shadows = quality.shadows && quality.shadowCascades > 0;
  sun.castShadow = shadows;
  sun.shadow.mapSize.set(quality.shadowMapSize, quality.shadowMapSize);
  sun.shadow.bias = -0.00015;
  sun.shadow.normalBias = 0.7;
  const csm = shadows ? new CSMShadowNode(sun, { cascades: quality.shadowCascades, maxFar: 1100, mode: "practical", lightMargin: 350 }) : undefined;
  if (csm) {
    csm.fade = true;
    sun.shadow.shadowNode = csm;
  }
  const skyFill = new Color(swatch("sky_blue")).lerp(new Color(swatch("cloud_cream")), 0.65);
  const groundFill = new Color(swatch("monument_shadow")).lerp(new Color(swatch("stone_weathered")), 0.35);
  scene.add(sun, sun.target, new HemisphereLight(skyFill, groundFill, 1.9));
  return { sun, resize: () => { if (csm?.camera) csm.updateFrustums(); } };
}
