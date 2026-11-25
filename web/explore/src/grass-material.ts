// TSL material for the GPU grass system — port of the proven Fantasy-open-world
// grass_blade.gdshader architecture (docs/grafik/FANTASY_OPEN_WORLD_REUSE.md §3):
//   · 3-component wind (main wave + cross gust + per-blade flutter) weighted by height²
//   · mid-range width boost so coverage closes before blending into the ground texture
//   · root-to-tip colour gradient, dark blade feet instead of shadow casting
//   · base colour coupled per-instance to the macro ground colour (baked at generation)
//   · warm backlight translucency toward the sun, softened up-tilted normals
// Instanced attributes per cell geometry:
//   aInfo  = vec4(worldX, worldY, worldZ, instanceHash)
//   aShade = vec4(canopyShadow, dryMix, heightScale, widthMul)
//   aTint  = vec4(macro-matched linear ground tint rgb, unused alpha)
import { Color, DoubleSide, MeshStandardNodeMaterial } from "three/webgpu";
import {
  cameraPosition, clamp, dot, float, instancedBufferAttribute, mix, normalGeometry, positionGeometry,
  sin, cos, smoothstep, transformNormalToView, uniform, vec3, abs as tslAbs, attribute,
} from "three/tsl";
import type { InstancedBufferAttribute, Node } from "three/webgpu";

export interface GrassInstanceData {
  aInfo: InstancedBufferAttribute;
  aShade: InstancedBufferAttribute;
}
import { sunDirection } from "./atmosphere.ts";
import { worldTime } from "./world-time.ts";

export interface GrassMaterialOptions {
  fadeStart?: number;
  fadeEnd?: number;
  windStrength?: number;
  windSpeed?: number;
}

// Colour tuning constants — shared between the shader pipeline and the test probe.
// Hue correction multipliers applied to the (externally auto-multiplied) linear macro tint:
// green boosted, blue compressed → the olive macro tint shifts to fresh saturated meadow green.
const LUSH_K = [0.82, 1.38, 0.60] as const;
const STRAW_K = [1.12, 1.02, 0.45] as const;
/** tip warming: red rises relative to green, blue stays compressed (sun-lit yellow-green tips). */
const TIP_WARM = [1.48, 1.30, 0.82] as const;
/** root brightness fraction of mid brightness. */
const ROOT_SHADE = 0.34;
/** representative linear-light meadow macro tint (srgb ~#686a43), for documentation/probe. */
const REFERENCE_TINT = [0.134, 0.144, 0.054] as const;

export function grassMaterial(instanceData?: GrassInstanceData, options: GrassMaterialOptions = {}) {
  const fadeStart = uniform(float(options.fadeStart ?? 70));
  const fadeEnd = uniform(float(options.fadeEnd ?? 96));
  const windStrength = uniform(float(options.windStrength ?? 0.22));
  const windSpeed = uniform(float(options.windSpeed ?? 1.55));

  const material = new MeshStandardNodeMaterial({ roughness: 0.88, metalness: 0, side: DoubleSide });

  const uv = attribute("uv", "vec2");
  const vcol = attribute("color", "vec4");
  const aInfo = (instanceData ? instancedBufferAttribute(instanceData.aInfo, "vec4") : attribute("aInfo", "vec4")) as Node<"vec4">;
  const aShade = (instanceData ? instancedBufferAttribute(instanceData.aShade, "vec4") : attribute("aShade", "vec4")) as Node<"vec4">;
  const aTint = attribute("aTint", "vec4") as Node<"vec4">;
  const hFrac = uv.y;
  const bladeHash = vcol.r;
  const flex = vcol.g;

  const instPos = aInfo.xyz;
  const camDist = cameraPosition.sub(instPos).length();

  // three.js semantics (NodeMaterial.setupPosition): a custom positionNode OVERWRITES the
  // instanced position — instanceMatrix never applies in the shader. The full instance
  // transform is therefore rebuilt manually here from the instanced attributes. The mesh
  // sits at world identity, so attribute world positions are correct output positions.
  // Per-instance yaw is derived deterministically from the instance hash (statistically
  // identical to a CPU-side random yaw, and the matrix rotation never reaches the shader).
  const distFade = smoothstep(fadeStart, fadeEnd, camDist).oneMinus();
  const widthBoost = mix(float(1.22), float(1.45), smoothstep(14, 72, camDist)).mul(aShade.w);
  const lx = positionGeometry.x.mul(widthBoost).mul(distFade);
  const ly = positionGeometry.y.mul(aShade.z).mul(distFade);
  const lz = positionGeometry.z.mul(widthBoost).mul(distFade);
  const yaw = aInfo.w.mul(6.2831);
  const cy = cos(yaw);
  const sy = sin(yaw);
  const rx = lx.mul(cy).sub(lz.mul(sy));
  const rz = lx.mul(sy).add(lz.mul(cy));

  // 3-component wind, coherent world-space phase, h² weighting, length-preserving y drop
  const hf = hFrac.mul(hFrac).mul(flex).mul(distFade);
  const tNow = worldTime.mul(windSpeed);
  const waveMain = sin(instPos.x.mul(0.10).add(instPos.z.mul(0.07)).sub(tNow));
  const waveGust = cos(instPos.x.mul(0.045).sub(instPos.z.mul(0.06)).sub(tNow.mul(0.68)).add(1.4));
  const flutter = sin(tNow.mul(2.4).add(instPos.x.mul(0.41)).add(instPos.z.mul(0.37)).add(bladeHash.mul(6.2831))).mul(0.26);
  const dx = waveMain.mul(0.72).add(waveGust.mul(0.38)).add(flutter).mul(windStrength).mul(hf);
  const dz = waveMain.mul(0.48).sub(waveGust.mul(0.32)).add(flutter.mul(0.65)).mul(windStrength).mul(hf);
  const dy = tslAbs(dx).add(tslAbs(dz)).mul(-0.22).mul(hFrac);

  material.positionNode = vec3(
    instPos.x.add(rx).add(dx),
    instPos.y.add(ly).add(dy),
    instPos.z.add(rz).add(dz),
  );

  // fragment: root-to-tip gradient shaping. The macro tint arrives as proper linear colour
  // in aTint (CPU-linearised in grass-system.ts). It is carried in a vec4 attribute instead of
  // instanceColor because WebGPU otherwise pads every vec3 colour update through a full-capacity copy.
  const dry = aShade.y;
  const hclamped = clamp(hFrac, 0, 1);

  // hue correction: the olive macro tint is shifted toward fresh saturated meadow green
  // (green boosted, blue compressed — constant multipliers commute with the external tint).
  // dry instances lean toward golden straw instead.
  const lushK = vec3(...LUSH_K);
  const strawK = vec3(...STRAW_K);
  const hueK = mix(lushK, strawK, dry);

  // two-segment brightness gradient: shaded roots, vivid mid, sun-lit yellow-green tips
  // (red rises relative to green toward the tip, blue stays compressed — fresh straw-lit tips
  // instead of washed-out pale ones)
  const rootToMid = mix(float(ROOT_SHADE), float(1.0), smoothstep(0.0, 0.45, hclamped));
  const tipWarm = mix(vec3(1, 1, 1), vec3(...TIP_WARM), smoothstep(0.42, 1.0, hclamped));

  // across-blade shading: edges clearly darker, centre catches the light (plasticity)
  const across = tslAbs(uv.x.sub(0.5)).mul(2);
  const acrossShade = across.oneMinus().mul(0.18).add(0.88);

  // per-blade variation: brightness + a subtle dry-golden lean on some blades (meadow variance)
  const hashVar = mix(float(0.86), float(1.14), bladeHash);
  const hueVarK = mix(hueK, strawK, bladeHash.mul(0.16));

  // per-instance variation + canopy shadow
  const alb = hueVarK.mul(rootToMid).mul(tipWarm).mul(acrossShade)
    .mul(hashVar).mul(aShade.x.mul(0.55).add(0.45));
  material.colorNode = aTint.rgb.mul(alb);

  // Meadow lighting normals. NOTE: normalNode is interpreted in VIEW space (three.js
  // materialNormal semantics) — a constant vec3(0,1,0) here would mean screen-space up,
  // not world up, so lighting would wrongly depend on camera orientation. World-up is
  // therefore converted properly. A modest share of the per-blade geometry normal
  // (rotated by the same instance yaw as the positions) is mixed in toward the tips:
  // keeps the coherent meadow look but gives individual blades plastic depth.
  const nx = normalGeometry.x.mul(cy).sub(normalGeometry.z.mul(sy));
  const nz = normalGeometry.x.mul(sy).add(normalGeometry.z.mul(cy));
  const bladeNrm = vec3(nx, normalGeometry.y, nz).normalize();
  const nrmMix = hFrac.mul(0.18).add(0.10);
  const worldNrm = mix(vec3(0, 1, 0), bladeNrm, nrmMix).normalize();
  material.normalNode = transformNormalToView(worldNrm);

  // warm backlight toward the sun at blade tips (translucency), strongest in contre-jour.
  // Emissive bypasses diffuse colour and therefore applies the same linear tint explicitly.
  const sunDot = clamp(dot(vec3(sunDirection), vec3(0, 1, 0)), 0, 1);
  material.emissiveNode = aTint.rgb.mul(alb).mul(vec3(1.08, 1.14, 0.70)).mul(hclamped.mul(hclamped)).mul(sunDot).mul(0.16);

  material.roughnessNode = mix(float(0.92), float(0.62), hclamped);
  return material;
}

/**
 * Palette probe used by tests: representative final blade colours (linear light) of the
 * actual shader pipeline at the reference meadow tint — confirms grass tones stay inside
 * STYLE.md hues. root = shaded blade foot, lushTip/dryTip = sun-lit blade tips.
 */
export function grassPaletteProbe() {
  const scale = (k: readonly number[], brightness: number, warm: readonly number[] = [1, 1, 1]) =>
    new Color(
      REFERENCE_TINT[0] * k[0] * warm[0] * brightness,
      REFERENCE_TINT[1] * k[1] * warm[1] * brightness,
      REFERENCE_TINT[2] * k[2] * warm[2] * brightness,
    );
  return {
    root: scale(LUSH_K, ROOT_SHADE),
    lushTip: scale(LUSH_K, 1.0, TIP_WARM),
    dryTip: scale(STRAW_K, 1.0, TIP_WARM),
  };
}
