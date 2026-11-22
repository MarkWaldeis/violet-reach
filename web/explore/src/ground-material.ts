import { Color, MeshStandardNodeMaterial, type Node } from "three/webgpu";
import {
  cameraPosition, color, float, mix, mx_noise_float, normalWorldGeometry,
  positionWorld, smoothstep, transformNormalToView, vec2, vec3,
} from "three/tsl";
import { swatch } from "./palette.ts";
import type { SurfaceData } from "./surface-data.ts";

export function terrainMaterial(surface?: SurfaceData) {
  const material = new MeshStandardNodeMaterial({ roughness: 0.92 });
  const p = positionWorld, planar = p.xz;
  const field = surface?.sample(planar);
  let normal = normalWorldGeometry;
  if (surface && field) {
    const dx = surface.sample(planar.add(vec2(8, 0))).r.sub(surface.sample(planar.sub(vec2(8, 0))).r).div(16);
    const dz = surface.sample(planar.add(vec2(0, 8))).r.sub(surface.sample(planar.sub(vec2(0, 8))).r).div(16);
    const uv = planar.sub(surface.origin).div(surface.size);
    const border = smoothstep(0, 0.02, uv.x).mul(smoothstep(0, 0.02, uv.y)).mul(smoothstep(0, 0.02, uv.x.oneMinus())).mul(smoothstep(0, 0.02, uv.y.oneMinus()));
    normal = mix(normal, vec3(dx.negate(), 1, dz.negate()).normalize(), smoothstep(40, 100, field.b).oneMinus().mul(border));
  }
  const broad = mx_noise_float(planar.mul(0.006)).mul(0.5).add(0.5);
  const patches = mx_noise_float(planar.mul(0.019).add(vec2(71, -39))).mul(0.5).add(0.5);
  const green = color(swatch("grass_green").multiply(new Color(1.05, 1.3, 0.82)));
  const meadow = mix(green, color(swatch("path_sand").multiply(new Color(0.85, 1.05, 0.65))), smoothstep(0.48, 0.82, broad).mul(0.6));
  const grass = mix(meadow, color(swatch("grass_dry")), smoothstep(0.65, 0.95, patches).mul(0.5));
  const shaded = mix(grass, color(swatch("leaf_shadow")), smoothstep(0.5, 0.84, patches).mul(0.42));
  const up = normal.y.abs();
  const soil = mix(shaded, color(swatch("soil")), smoothstep(0.3, 0.58, up.oneMinus()));
  const strata = p.y.mul(0.1).add(broad.mul(12)).add(patches.mul(2)).sin().mul(0.22).add(0.5);
  const rock = mix(color(swatch("canyon_chalk")), color(swatch("canyon_strata")), strata);
  let ground = mix(soil, rock, smoothstep(0.58, 0.83, up.oneMinus()));
  if (surface && field) {
    const uv = planar.sub(surface.origin).div(surface.size);
    const inside = uv.x.greaterThanEqual(0).and(uv.y.greaterThanEqual(0)).and(uv.x.lessThanEqual(1)).and(uv.y.lessThanEqual(1));
    const aboveWater = p.y.sub(field.g);
    const bank = smoothstep(10, 65, aboveWater).oneMinus().mul(smoothstep(40, 100, field.b).oneMinus()).mul(float(inside));
    ground = mix(ground, soil, bank.mul(0.35));
    const shore = smoothstep(0.8, 4.5, aboveWater.abs()).oneMinus().mul(smoothstep(4, 18, field.b).oneMinus()).mul(float(inside));
    const wet = mix(color(swatch("path_sand")).mul(0.58), color(swatch("shore_wet")), 0.18);
    const sand = mix(wet, color(swatch("path_sand")), smoothstep(-0.15, 1.8, aboveWater));
    ground = mix(ground, sand, shore);
    let pathDistance: Node<"float"> = float(10000);
    for (const path of surface.paths) for (let i = 1; i < path.polyline.length; i++) {
      const a = vec2(...path.polyline[i - 1]), b = vec2(...path.polyline[i]);
      const delta = b.sub(a), t = planar.sub(a).dot(delta).div(delta.dot(delta).max(0.0001)).clamp();
      pathDistance = pathDistance.min(planar.sub(a.add(delta.mul(t))).length().sub(path.width / 2));
    }
    ground = mix(ground, color(swatch("path_sand")), smoothstep(-0.4, 1.2, pathDistance).oneMinus().mul(smoothstep(-0.1, 0.8, aboveWater)));
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
