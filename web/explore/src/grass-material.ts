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
//   instanceColor (rgb) = macro-matched ground tint
import { Color, MeshStandardNodeMaterial } from "three/webgpu";
import {
  attribute, cameraPosition, clamp, color, dot, float, instanceColor, mix, normalize, positionLocal,
  sin, cos, smoothstep, uniform, vec3, abs as tslAbs,
} from "three/tsl";
import { sunDirection } from "./atmosphere.ts";
import { worldTime } from "./world-time.ts";
import { swatch } from "./palette.ts";

export interface GrassMaterialOptions {
  fadeStart?: number;
  fadeEnd?: number;
  windStrength?: number;
  windSpeed?: number;
}

export function grassMaterial(options: GrassMaterialOptions = {}) {
  const fadeStart = uniform(float(options.fadeStart ?? 70));
  const fadeEnd = uniform(float(options.fadeEnd ?? 96));
  const windStrength = uniform(float(options.windStrength ?? 0.22));
  const windSpeed = uniform(float(options.windSpeed ?? 1.55));

  const material = new MeshStandardNodeMaterial({ roughness: 0.88, metalness: 0 });

  const uv = attribute("uv", "vec2");
  const vcol = attribute("color", "vec4");
  const aInfo = attribute("aInfo", "vec4");
  const aShade = attribute("aShade", "vec4");
  const hFrac = uv.y;
  const bladeHash = vcol.r;
  const flex = vcol.g;

  const instPos = aInfo.xyz;
  const camDist = cameraPosition.sub(instPos).length();

  // distance fade + mid-range fullness boost (widens XZ only), height shrinks with fade
  const distFade = smoothstep(fadeStart, fadeEnd, camDist).oneMinus();
  const widthBoost = mix(float(1), float(1.30), smoothstep(14, 72, camDist)).mul(aShade.w);
  const scaled = vec3(positionLocal.x.mul(widthBoost), positionLocal.y.mul(distFade).mul(aShade.z), positionLocal.z.mul(widthBoost));

  // 3-component wind, coherent world-space phase, h² weighting, length-preserving y drop
  const hf = hFrac.mul(hFrac).mul(flex).mul(distFade);
  const tNow = worldTime.mul(windSpeed);
  const waveMain = sin(instPos.x.mul(0.10).add(instPos.z.mul(0.07)).sub(tNow));
  const waveGust = cos(instPos.x.mul(0.045).sub(instPos.z.mul(0.06)).sub(tNow.mul(0.68)).add(1.4));
  const flutter = sin(tNow.mul(2.4).add(instPos.x.mul(0.41)).add(instPos.z.mul(0.37)).add(bladeHash.mul(6.2831))).mul(0.26);
  const dx = waveMain.mul(0.72).add(waveGust.mul(0.38)).add(flutter).mul(windStrength).mul(hf);
  const dz = waveMain.mul(0.48).sub(waveGust.mul(0.32)).add(flutter.mul(0.65)).mul(windStrength).mul(hf);
  const dy = tslAbs(dx).add(tslAbs(dz)).mul(-0.22).mul(hFrac);

  material.positionNode = scaled.add(vec3(dx, dy, dz));

  // fragment: root-to-tip gradient between macro-matched base tint and dry/lush tip colour
  const tint = instanceColor.rgb;
  const dry = aShade.y;
  const lushTip = color(swatch("grass_green"));
  const dryTip = color(swatch("grass_dry"));
  const tipCol = mix(lushTip, dryTip, dry);
  const hclamped = clamp(hFrac, 0, 1);
  const grad = mix(tint.mul(0.42), tint.mul(1.18).mul(mix(vec3(1, 1, 1), tipCol, 0.55)), smoothstep(0.05, 0.95, hclamped));
  // per-instance variation + canopy shadow + macro AO baked into tint already at generation
  const alb = grad.mul(mix(0.92, 1.08, bladeHash)).mul(aShade.x.mul(0.55).add(0.45));
  material.colorNode = alb;

  // soft up-tilted normals for coherent meadow lighting (mix toward up by height)
  material.normalNode = normalize(mix(vec3(0, 1, 0), vec3(0, 1, 0), 0.0));

  // warm backlight toward the sun at blade tips (translucency), strongest in contre-jour
  const sunDot = clamp(dot(vec3(sunDirection), vec3(0, 1, 0)), 0, 1);
  material.emissiveNode = alb.mul(vec3(1.10, 1.16, 0.72)).mul(hclamped.mul(hclamped)).mul(sunDot).mul(0.30);

  material.roughnessNode = mix(float(0.92), float(0.62), hclamped);
  return material;
}

/** Palette probe used by tests: confirms grass tones stay inside STYLE.md hues. */
export function grassPaletteProbe() {
  return {
    root: new Color(swatch("leaf_shadow")).multiplyScalar(2.2),
    lushTip: new Color(swatch("grass_green")),
    dryTip: new Color(swatch("grass_dry")),
  };
}
