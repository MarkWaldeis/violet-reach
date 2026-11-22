import { Color, MeshStandardNodeMaterial, type Node } from "three/webgpu";
import {
  cameraPosition, color, float, mix, mx_noise_float, normalWorldGeometry,
  positionWorld, smoothstep, transformNormalToView, vec2, vec3,
} from "three/tsl";
import { swatch } from "./palette.ts";
import type { SurfaceData } from "./surface-data.ts";
import { sunDirection } from "./atmosphere.ts";

export function terrainMaterial(surface?: SurfaceData) {
  const material = new MeshStandardNodeMaterial({ roughness: 0.92 });
  const p = positionWorld, planar = p.xz;
  const field = surface?.sample(planar);
  let normal = normalWorldGeometry;
  let hollow: Node<"float"> = float(0), damp: Node<"float"> = float(0);
  if (surface && field) {
    const dx = surface.sample(planar.add(vec2(8, 0))).r.sub(surface.sample(planar.sub(vec2(8, 0))).r).div(16);
    const dz = surface.sample(planar.add(vec2(0, 8))).r.sub(surface.sample(planar.sub(vec2(0, 8))).r).div(16);
    const uv = planar.sub(surface.origin).div(surface.size);
    const border = smoothstep(0, 0.02, uv.x).mul(smoothstep(0, 0.02, uv.y)).mul(smoothstep(0, 0.02, uv.x.oneMinus())).mul(smoothstep(0, 0.02, uv.y.oneMinus()));
    normal = mix(normal, vec3(dx.negate(), 1, dz.negate()).normalize(), smoothstep(40, 100, field.b).oneMinus().mul(border));
    const neighbours = surface.sample(planar.add(vec2(16, 0))).r.add(surface.sample(planar.sub(vec2(16, 0))).r)
      .add(surface.sample(planar.add(vec2(0, 16))).r).add(surface.sample(planar.sub(vec2(0, 16))).r).mul(0.25);
    hollow = smoothstep(0.15, 1.8, neighbours.sub(field.r)).mul(border);
    damp = smoothstep(2, 28, p.y.sub(field.g)).oneMinus().mul(smoothstep(15, 100, field.b).oneMinus()).mul(border);
  }
  const broad = mx_noise_float(planar.mul(0.0048)).mul(1.1).add(0.5);
  const patches = mx_noise_float(planar.mul(0.021).add(vec2(71, -39))).mul(1.3).add(0.5);
  const small = mx_noise_float(planar.mul(0.11).add(vec2(-19, 58))).mul(1.2).add(0.5);
  const green = color(swatch("grass_green").multiply(new Color(1.08, 1.48, 0.75)));
  const straw = color(swatch("grass_dry").lerp(swatch("path_sand"), 0.6).multiplyScalar(1.08));
  const up = normal.y.abs();
  const slope = up.oneMinus(), sunny = normal.dot(vec3(sunDirection)).max(0);
  const meadow = smoothstep(0.43, 0.64, broad.add(patches.sub(0.5).mul(0.24)))
    .mul(smoothstep(0.75, 0.95, up)).mul(sunny.mul(0.5).add(0.5));
  let ground = mix(green, straw, meadow);
  const bare = smoothstep(0.68, 0.94, patches.add(small.sub(0.5).mul(0.3))).mul(0.7)
    .add(smoothstep(0.07, 0.17, slope).mul(0.15)).clamp();
  ground = mix(ground, color(swatch("soil")), bare);
  const north = normal.z.negate().max(0);
  const moss = smoothstep(0.25, 0.75, damp.mul(0.75).add(hollow.mul(0.7)).add(north.mul(0.65)).add(patches.sub(0.5).mul(0.5)));
  ground = mix(ground, color(swatch("moss")), moss.mul(0.85));
  const strata = p.y.mul(0.16).add(broad.mul(3)).add(patches.mul(0.8)).sin().mul(0.5).add(0.5);
  const rock = mix(color(swatch("canyon_chalk")).mul(1.08), color(swatch("canyon_strata")).mul(0.9), strata.mul(0.4));
  ground = mix(ground, rock, smoothstep(0.16, 0.24, slope.add(small.sub(0.5).mul(0.02))));
  if (surface && field) {
    const uv = planar.sub(surface.origin).div(surface.size);
    const inside = uv.x.greaterThanEqual(0).and(uv.y.greaterThanEqual(0)).and(uv.x.lessThanEqual(1)).and(uv.y.lessThanEqual(1));
    const aboveWater = p.y.sub(field.g);
    const shore = smoothstep(1.6, 5.5, aboveWater.abs().add(small.sub(0.5).mul(0.6))).oneMinus()
      .mul(smoothstep(8, 28, field.b).oneMinus()).mul(float(inside));
    const wet = color(swatch("shore_wet").lerp(swatch("soil"), 0.5).multiplyScalar(0.75));
    const sand = mix(wet, color(swatch("path_sand")), smoothstep(0.15, 1.3, aboveWater));
    ground = mix(ground, sand, shore);
    let pathDistance: Node<"float"> = float(10000);
    for (const path of surface.paths) for (let i = 1; i < path.polyline.length; i++) {
      const a = vec2(...path.polyline[i - 1]), b = vec2(...path.polyline[i]);
      const delta = b.sub(a), t = planar.sub(a).dot(delta).div(delta.dot(delta).max(0.0001)).clamp();
      pathDistance = pathDistance.min(planar.sub(a.add(delta.mul(t))).length().sub(path.width / 2));
    }
    const dryPath = smoothstep(-0.1, 0.8, aboveWater);
    ground = mix(ground, color(swatch("soil")), smoothstep(0, 2.5, pathDistance).oneMinus().mul(dryPath).mul(0.8));
    ground = mix(ground, color(swatch("path_sand")), smoothstep(-0.4, 1, pathDistance).oneMinus().mul(dryPath));
    material.roughnessNode = mix(float(0.92), float(0.55), shore.mul(smoothstep(0, 2, aboveWater).oneMinus()));
  }
  const distance = p.sub(cameraPosition).length();
  const footprint = planar.fwidth().length();
  const detail = smoothstep(25, 150, distance).oneMinus().mul(smoothstep(0.1, 0.45, footprint).oneMinus());
  const midDetail = smoothstep(120, 500, distance).oneMinus().mul(smoothstep(0.8, 3, footprint).oneMinus());
  const grain = mx_noise_float(planar.mul(3.8).add(vec2(11.3, 53.7)));
  const tufts = mx_noise_float(planar.mul(vec2(0.8, 1.3))).mul(0.65).add(mx_noise_float(planar.mul(vec2(1.7, 0.95)).add(vec2(29, 83))).mul(0.35));
  material.colorNode = ground.mul(tufts.mul(0.32).mul(midDetail).add(grain.mul(0.16).mul(detail)).add(1));
  const fineNormal = vec3(grain, 0, mx_noise_float(planar.mul(3.1).add(vec2(17.5, 4.8)))).mul(detail.mul(0.17)).add(vec3(tufts, 0, mx_noise_float(planar.mul(1.1))).mul(midDetail.mul(0.08)));
  material.normalNode = transformNormalToView(normal.add(fineNormal).normalize());
  return material;
}
