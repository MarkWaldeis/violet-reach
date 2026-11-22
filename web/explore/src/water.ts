import { DoubleSide, Group, Mesh, MeshStandardNodeMaterial } from "three/webgpu";
import {
  attribute, cameraPosition, color, float, mix, positionWorld, smoothstep, time,
  transformNormalToView, vec2, vec3,
} from "three/tsl";
import { sunDirection } from "./atmosphere.ts";
import type { WaterRegion } from "./hydrology.ts";
import { swatch } from "./palette.ts";
import type { SurfaceData } from "./surface-data.ts";
import { buildWaterGeometry } from "./water-geometry.ts";

export function waterMaterial(surface: SurfaceData) {
  const material = new MeshStandardNodeMaterial({ side: DoubleSide, roughness: 0.27, metalness: 0.05 });
  const p = positionWorld, field = surface.sample(p.xz);
  const depth = p.y.sub(field.r).max(0), lake = attribute("lake", "float");
  const footprint = lake.greaterThan(0.5).and(field.a.lessThanEqual(-3)).or(lake.lessThan(0.5).and(field.a.greaterThan(-3)));
  material.maskNode = p.y.sub(field.r).greaterThan(0.02).and(field.b.lessThan(0)).and(footprint);
  const flow = mix(vec2(0.9, 0.43589), attribute("flow", "vec2"), smoothstep(-3, 18, field.a).mul(lake.oneMinus()));
  const along = p.xz.dot(flow), across = p.xz.dot(flow.yx.mul(vec2(-1, 1)));
  const phase = along.mul(1.9).sub(time.mul(1.2));
  const crossPhase = across.mul(2.6).add(time.mul(0.38));
  const ripple = smoothstep(40, 350, cameraPosition.sub(p).length()).oneMinus().mul(0.065);
  const nx = phase.sin().mul(flow.x).add(crossPhase.sin().mul(flow.y).mul(0.55)).mul(ripple).add(along.mul(0.045).sub(time.mul(0.12)).sin().mul(0.012));
  const nz = phase.sin().mul(flow.y).sub(crossPhase.sin().mul(flow.x).mul(0.55)).mul(ripple).add(across.mul(0.06).add(time.mul(0.1)).sin().mul(0.012));
  const normal = vec3(nx, 1, nz).normalize();
  material.normalNode = transformNormalToView(normal);
  const toEye = cameraPosition.sub(p).normalize();
  const fresnel = float(1).sub(normal.dot(toEye).max(0)).pow(4).mul(0.38).add(0.04);
  const tint = mix(color(swatch("water_shallow")), color(swatch("water_deep")), smoothstep(0.05, 0.5, depth));
  const reflection = mix(color(swatch("sky_blue")), color(swatch("cloud_cream")), smoothstep(0.02, 0.45, toEye.y).oneMinus().mul(0.35));
  const foam = smoothstep(0.03, 0.18, depth).oneMinus().mul(phase.mul(0.45).sin().mul(0.08).add(0.35));
  const shoreFoam = smoothstep(-0.9, -0.05, field.b).mul(0.35);
  material.colorNode = mix(mix(tint, reflection, fresnel), color(swatch("cloud_cream")), foam.add(shoreFoam).clamp());
  const half = toEye.add(vec3(sunDirection)).normalize();
  const glint = normal.dot(half).max(0).pow(350).mul(1.8);
  material.emissiveNode = reflection.mul(fresnel.mul(0.14)).add(color(swatch("accent_ochre")).mul(glint));
  return material;
}

export function waterSurface(region: WaterRegion, surface: SurfaceData) {
  const group = new Group();
  const mesh = new Mesh(buildWaterGeometry(region), waterMaterial(surface));
  mesh.receiveShadow = true;
  group.add(mesh);
  return group;
}
