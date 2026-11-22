import {
  DirectionalLight, HemisphereLight, Scene, Vector3,
} from "three/webgpu";
import { CSMShadowNode } from "three/addons/csm/CSMShadowNode.js";
import { cameraPosition, cameraProjectionMatrixInverse, cameraWorldMatrix, color, fog, mix, mx_noise_float, positionWorld, screenUV, smoothstep, time, vec2, vec3, vec4 } from "three/tsl";
import { swatch } from "./palette.ts";

export const sunDirection = new Vector3(-0.56, 0.52, -0.62).normalize();

export function setupAtmosphere(scene: Scene) {
  const clip = vec4(screenUV.mul(vec2(2, -2)).add(vec2(-1, 1)), 1, 1);
  const direction = cameraWorldMatrix.mul(vec4(cameraProjectionMatrixInverse.mul(clip).xyz.normalize(), 0)).xyz.normalize();
  const horizon = smoothstep(-0.04, 0.38, direction.y).oneMinus();
  const skyColor = mix(color(swatch("sky_blue")), color(swatch("haze")), horizon);
  const drift = vec3(time.mul(0.003), 0, time.mul(0.001));
  const broad = mx_noise_float(direction.mul(vec3(3.2, 7, 3.2)).add(drift));
  const wisps = mx_noise_float(direction.mul(vec3(16, 38, 16)).add(drift)).mul(0.23);
  const field = broad.add(wisps);
  const overhead = smoothstep(0.02, 0.42, field).mul(0.38);
  const bank = smoothstep(-0.18, 0.3, field)
    .mul(smoothstep(-0.07, 0.015, direction.y))
    .mul(smoothstep(0.045, 0.24, direction.y).oneMinus());
  const cloud = overhead.add(bank.mul(0.75)).clamp();
  const cream = color(swatch("cloud_cream")).mul(1.35);
  const clouds = mix(skyColor, cream, cloud.mul(0.85));
  const sunDot = direction.dot(vec3(sunDirection)).max(0);
  const glow = sunDot.pow(48).mul(0.35).add(smoothstep(0.99978, 0.9999, sunDot).mul(5));
  scene.backgroundNode = clouds.add(color(swatch("accent_ochre")).mul(glow));

  const distance = positionWorld.sub(cameraPosition).length();
  const valley = positionWorld.y.add(cameraPosition.y).mul(0.5).sub(180).max(0).mul(-0.0015).exp();
  const density = valley.mul(0.000065).add(0.000035);
  const haze = distance.sub(180).max(0).mul(density).negate().exp().oneMinus();
  const veil = bank.mul(smoothstep(1800, 6500, distance)).mul(0.48);
  const hazeColor = mix(mix(color(swatch("haze")), color(swatch("cloud_cream")), 0.18), cream, veil);
  scene.fogNode = fog(hazeColor, haze.add(veil).clamp(0, 0.82));

  const sun = new DirectionalLight(swatch("monument_white"), 3);
  sun.position.copy(sunDirection).multiplyScalar(1000);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.00015;
  sun.shadow.normalBias = 0.7;
  const csm = new CSMShadowNode(sun, { cascades: 3, maxFar: 1100, mode: "practical", lightMargin: 350 });
  csm.fade = true;
  sun.shadow.shadowNode = csm;
  scene.add(sun, sun.target, new HemisphereLight(swatch("sky_blue"), swatch("monument_shadow"), 1.9));
  return { resize: () => { if (csm.camera) csm.updateFrustums(); } };
}
