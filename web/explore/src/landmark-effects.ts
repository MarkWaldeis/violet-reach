import {
  AdditiveBlending, CylinderGeometry, DoubleSide, Group, InstancedBufferAttribute, InstancedMesh,
  Matrix4, MeshBasicNodeMaterial, PlaneGeometry, PointLight, Quaternion, Vector3, type Node,
} from "three/webgpu";
import {
  abs, attribute, cameraPosition, cameraWorldMatrix, color, dot, float,
  mix, mx_noise_float, normalWorldGeometry, positionGeometry, positionWorld, sin, smoothstep,
  uv as tslUV, vec2, vec3, vec4,
} from "three/tsl";
import { swatch } from "./palette.ts";
import { QUALITY_NAMES, type QualityName } from "./quality.ts";
import { worldTime } from "./world-time.ts";

/**
 * Optional slice-local landmark effects. `y` is an exact world-space anchor; without it the
 * runtime samples the full-resolution terrain and then applies `y_offset`. Light-column anchors
 * are column feet, crystal-glow anchors are glow centres.
 */
export interface LightColumnEffect {
  id?: string;
  x: number;
  z: number;
  y?: number;
  y_offset?: number;
  height: number;
  radius: number;
  intensity?: number;
  /** 0 = ivory/monument white, 1 = palette violet glow. */
  violet?: number;
  /** Deterministic animation phase in turns (0..1); missing values are hashed from x/z. */
  phase?: number;
}

export interface CrystalGlowEffect {
  id?: string;
  x: number;
  z: number;
  y?: number;
  y_offset?: number;
  /** Radius of the additive camera-facing halo in metres. */
  radius: number;
  intensity?: number;
  /** 0 = warm ivory, 1 = palette violet glow. */
  violet?: number;
  phase?: number;
  /** Sparse local point light; quality tiers may reduce or disable it. */
  light?: boolean;
  light_radius?: number;
  light_intensity?: number;
}

export interface SliceEffects {
  light_columns?: LightColumnEffect[];
  crystal_glows?: CrystalGlowEffect[];
}

export interface ResolvedLightColumnEffect extends Omit<LightColumnEffect, "intensity" | "violet" | "phase" | "y_offset"> {
  y_offset: number;
  intensity: number;
  violet: number;
  phase: number;
}

export interface ResolvedCrystalGlowEffect extends Omit<CrystalGlowEffect, "intensity" | "violet" | "phase" | "y_offset" | "light" | "light_radius" | "light_intensity"> {
  y_offset: number;
  intensity: number;
  violet: number;
  phase: number;
  light: boolean;
  light_radius: number;
  light_intensity: number;
}

export interface ResolvedSliceEffects {
  light_columns: ResolvedLightColumnEffect[];
  crystal_glows: ResolvedCrystalGlowEffect[];
}

export interface EffectBounds { minX: number; minZ: number; maxX: number; maxZ: number }

export const MAX_LIGHT_COLUMNS = 32;
export const MAX_CRYSTAL_GLOWS = 64;
const TWO_PI = Math.PI * 2;

function effectError(path: string, message: string): Error {
  return new Error(`${path}: ${message}`);
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw effectError(path, "object expected");
  return value as Record<string, unknown>;
}

function rejectUnknownFields(obj: Record<string, unknown>, allowed: readonly string[], path: string) {
  const known = new Set(allowed);
  for (const key of Object.keys(obj)) {
    if (!known.has(key)) throw effectError(path, `unknown field "${key}"`);
  }
}

function numberField(obj: Record<string, unknown>, key: string, path: string, min: number, max: number, required = false): number | undefined {
  const value = obj[key];
  if (value === undefined) {
    if (required) throw effectError(path, `"${key}" missing`);
    return undefined;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) throw effectError(path, `"${key}" must be a finite number`);
  if (value < min || value > max) throw effectError(path, `"${key}" must be in [${min}, ${max}]`);
  return value;
}

function booleanField(obj: Record<string, unknown>, key: string, path: string): boolean | undefined {
  const value = obj[key];
  if (value === undefined) return undefined;
  if (typeof value !== "boolean") throw effectError(path, `"${key}" must be boolean`);
  return value;
}

function idField(obj: Record<string, unknown>, path: string): string | undefined {
  const value = obj.id;
  if (value === undefined) return undefined;
  if (typeof value !== "string" || value.trim().length === 0 || value.length > 80) {
    throw effectError(path, '"id" must be a non-empty string of at most 80 characters');
  }
  return value;
}

/** Integer-noise phase hash, stable across runs and independent of floating-point trig noise. */
export function deterministicEffectPhase(x: number, z: number): number {
  const ix = Math.round(x * 1000) | 0;
  const iz = Math.round(z * 1000) | 0;
  let h = Math.imul(ix, 0x27D4EB2D) ^ Math.imul(iz, 0x165667B1) ^ 0x9E3779B9;
  h ^= h >>> 15;
  h = Math.imul(h, 0x85EBCA6B);
  h ^= h >>> 13;
  h = Math.imul(h, 0xC2B2AE35);
  h ^= h >>> 16;
  return (h >>> 0) / 0x100000000;
}

function checkBounds(x: number, z: number, bounds: EffectBounds | undefined, path: string) {
  if (!bounds) return;
  if (x < bounds.minX || x > bounds.maxX || z < bounds.minZ || z > bounds.maxZ) {
    throw effectError(path, `position outside slice bounds [${bounds.minX}..${bounds.maxX}] × [${bounds.minZ}..${bounds.maxZ}]`);
  }
}

function parseLightColumn(value: unknown, index: number, bounds: EffectBounds | undefined): ResolvedLightColumnEffect {
  const path = `effects.light_columns[${index}]`;
  const obj = record(value, path);
  rejectUnknownFields(obj, ["id", "x", "z", "y", "y_offset", "height", "radius", "intensity", "violet", "phase"], path);
  const x = numberField(obj, "x", path, -100000, 100000, true)!;
  const z = numberField(obj, "z", path, -100000, 100000, true)!;
  checkBounds(x, z, bounds, path);
  const y = numberField(obj, "y", path, -1000, 2000);
  const yOffset = numberField(obj, "y_offset", path, -100, 100) ?? 0;
  const height = numberField(obj, "height", path, 3, 240, true)!;
  const radius = numberField(obj, "radius", path, 0.25, 40, true)!;
  const intensity = numberField(obj, "intensity", path, 0, 4) ?? 1;
  const violet = numberField(obj, "violet", path, 0, 1) ?? 0.35;
  const phase = numberField(obj, "phase", path, 0, 1) ?? deterministicEffectPhase(x, z);
  const id = idField(obj, path);
  return { ...(id !== undefined ? { id } : {}), x, z, ...(y !== undefined ? { y } : {}), y_offset: yOffset, height, radius, intensity, violet, phase };
}

function parseCrystalGlow(value: unknown, index: number, bounds: EffectBounds | undefined): ResolvedCrystalGlowEffect {
  const path = `effects.crystal_glows[${index}]`;
  const obj = record(value, path);
  rejectUnknownFields(obj, ["id", "x", "z", "y", "y_offset", "radius", "intensity", "violet", "phase", "light", "light_radius", "light_intensity"], path);
  const x = numberField(obj, "x", path, -100000, 100000, true)!;
  const z = numberField(obj, "z", path, -100000, 100000, true)!;
  checkBounds(x, z, bounds, path);
  const y = numberField(obj, "y", path, -1000, 2000);
  const yOffset = numberField(obj, "y_offset", path, -100, 100) ?? 0;
  const radius = numberField(obj, "radius", path, 0.2, 12, true)!;
  const intensity = numberField(obj, "intensity", path, 0, 4) ?? 1;
  const violet = numberField(obj, "violet", path, 0, 1) ?? 0.85;
  const phase = numberField(obj, "phase", path, 0, 1) ?? deterministicEffectPhase(x, z);
  const light = booleanField(obj, "light", path) ?? true;
  const lightRadius = numberField(obj, "light_radius", path, 0, 80) ?? Math.min(80, Math.max(3, radius * 5));
  const lightIntensity = numberField(obj, "light_intensity", path, 0, 12) ?? intensity * 1.8;
  const id = idField(obj, path);
  return {
    ...(id !== undefined ? { id } : {}), x, z, ...(y !== undefined ? { y } : {}), y_offset: yOffset,
    radius, intensity, violet, phase, light, light_radius: lightRadius, light_intensity: lightIntensity,
  };
}

/**
 * Strictly parses the optional slice.effects section. Unknown entry fields and non-finite values
 * are rejected so placement typos fail at load time rather than becoming invisible landmarks.
 */
export function parseSliceEffects(input: unknown, bounds?: EffectBounds): ResolvedSliceEffects {
  if (input === undefined) return { light_columns: [], crystal_glows: [] };
  const root = record(input, "effects");
  rejectUnknownFields(root, ["light_columns", "crystal_glows"], "effects");
  const columnsRaw = root.light_columns ?? [];
  const glowsRaw = root.crystal_glows ?? [];
  if (!Array.isArray(columnsRaw)) throw effectError("effects.light_columns", "array expected");
  if (!Array.isArray(glowsRaw)) throw effectError("effects.crystal_glows", "array expected");
  if (columnsRaw.length > MAX_LIGHT_COLUMNS) throw effectError("effects.light_columns", `at most ${MAX_LIGHT_COLUMNS} entries allowed`);
  if (glowsRaw.length > MAX_CRYSTAL_GLOWS) throw effectError("effects.crystal_glows", `at most ${MAX_CRYSTAL_GLOWS} entries allowed`);
  return {
    light_columns: columnsRaw.map((entry, index) => parseLightColumn(entry, index, bounds)),
    crystal_glows: glowsRaw.map((entry, index) => parseCrystalGlow(entry, index, bounds)),
  };
}

export function validateSliceEffects(input: unknown, bounds?: EffectBounds): ResolvedSliceEffects {
  return parseSliceEffects(input, bounds);
}

export const hasLandmarkEffects = (effects: SliceEffects | ResolvedSliceEffects | undefined) =>
  !!effects && ((effects.light_columns?.length ?? 0) > 0 || (effects.crystal_glows?.length ?? 0) > 0);

export interface CrystalGlowQualitySettings {
  /** Multiplier for the additive halo alpha/intensity. */
  haloIntensity: number;
  /** Multiplier for the halo radius. */
  haloRadius: number;
  /** Multiplier for point-light intensity; zero disables lights. */
  pointLightIntensity: number;
  /** Multiplier for point-light distance. */
  pointLightDistance: number;
  /** Hard cap; lights are selected by intensity × distance, stable for ties. */
  maxPointLights: number;
}

/** Sparse glow/light ladder: low is strongly reduced, medium reduced, high/ultra full. */
export const CRYSTAL_GLOW_QUALITY: Readonly<Record<QualityName, Readonly<CrystalGlowQualitySettings>>> = {
  low: { haloIntensity: 0.25, haloRadius: 0.75, pointLightIntensity: 0, pointLightDistance: 0, maxPointLights: 0 },
  medium: { haloIntensity: 0.65, haloRadius: 0.88, pointLightIntensity: 0.5, pointLightDistance: 0.8, maxPointLights: 2 },
  high: { haloIntensity: 1, haloRadius: 1, pointLightIntensity: 1, pointLightDistance: 1, maxPointLights: 4 },
  ultra: { haloIntensity: 1, haloRadius: 1, pointLightIntensity: 1, pointLightDistance: 1, maxPointLights: 8 },
};

export function crystalGlowQuality(quality: QualityName | { name: QualityName } = "high"): Readonly<CrystalGlowQualitySettings> {
  const name = typeof quality === "string" ? quality : quality.name;
  if (!QUALITY_NAMES.includes(name)) throw new Error(`quality: ${QUALITY_NAMES.join("|")} erwartet`);
  return CRYSTAL_GLOW_QUALITY[name];
}

/** Selects the strongest sparse point lights deterministically; order in the slice breaks ties. */
export function selectCrystalPointLights(entries: readonly ResolvedCrystalGlowEffect[], maxPointLights: number): ResolvedCrystalGlowEffect[] {
  if (maxPointLights <= 0) return [];
  return entries
    .map((entry, index) => ({ entry, index, score: entry.light_intensity * entry.light_radius }))
    .filter(({ entry }) => entry.light && entry.light_intensity > 0 && entry.light_radius > 0)
    .sort((a, b) => (b.score - a.score) || (a.index - b.index))
    .slice(0, maxPointLights)
    .map(({ entry }) => entry);
}

function lightColumnMaterial(layer: "veil" | "core"): MeshBasicNodeMaterial {
  const material = new MeshBasicNodeMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: DoubleSide,
    blending: AdditiveBlending,
    fog: false,
  });
  // Additive blending is order-independent, so the correct two-sided cylinder volume does not
  // need three.js' double-sided transparent two-pass path; one draw per layer is enough.
  material.forceSinglePass = true;
  const data = attribute("aColumn", "vec4") as Node<"vec4">;
  const vertical = tslUV().y;
  const toCamera = cameraPosition.sub(positionWorld).normalize();
  const facing = abs(dot(normalWorldGeometry.normalize(), toCamera)).clamp(0, 1);

  // Fresnel-like radial extinction hides the cylindrical silhouette; end fades hide both caps.
  const radialFade = smoothstep(0.02, 0.58, facing);
  const endFade = smoothstep(0.0, 0.11, vertical).mul(smoothstep(0.78, 1.0, vertical).oneMinus());

  // One coherent world-space noise octave is enough for slow internal filaments. It is driven by
  // worldTime only, so ?freeze=1 is bit-stable and never depends on CPU frame timing.
  const noiseCoord = vec3(
    positionWorld.x.mul(0.071),
    positionWorld.z.mul(0.071),
    vertical.mul(data.w).mul(0.052).sub(worldTime.mul(0.11)).add(data.z.mul(19.0)),
  );
  const noise = mx_noise_float(noiseCoord).mul(0.5).add(0.5);
  const noiseAlpha = mix(float(0.84), float(1.12), noise);
  const pulse = sin(worldTime.mul(0.42).add(data.z.mul(TWO_PI))).mul(0.045).add(0.955);

  const ivory = color(swatch("monument_white"));
  const violetGlow = color(swatch("violet_glow"));
  const base = mix(ivory, violetGlow, data.y);
  const topViolet = smoothstep(0.35, 1.0, vertical).mul(0.20);
  const columnColor = mix(base, violetGlow, topViolet);

  const alphaScale = layer === "veil" ? 0.095 : 0.30;
  const brightness = layer === "veil" ? 0.78 : 1.22;
  material.colorNode = columnColor.mul(float(brightness));
  material.opacityNode = endFade
    .mul(radialFade)
    .mul(noiseAlpha)
    .mul(pulse)
    .mul(data.x)
    .mul(float(alphaScale))
    .clamp(0, 0.85);
  return material;
}

function crystalGlowMaterial(): MeshBasicNodeMaterial {
  const material = new MeshBasicNodeMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    blending: AdditiveBlending,
    fog: false,
  });
  material.forceSinglePass = true;
  const centre = attribute("aGlowCentre", "vec4") as Node<"vec4">;
  const style = attribute("aGlowStyle", "vec4") as Node<"vec4">;

  // Camera-facing instanced quads in world space. positionNode deliberately replaces the unused
  // instance-matrix path (the mesh itself stays at identity), keeping billboard orientation exact
  // and the CPU-side per-frame cost at zero.
  const right = cameraWorldMatrix.mul(vec4(1, 0, 0, 0)).xyz.normalize();
  const up = cameraWorldMatrix.mul(vec4(0, 1, 0, 0)).xyz.normalize();
  const corner = positionGeometry.xy.mul(centre.w.mul(2));
  material.positionNode = centre.xyz.add(right.mul(corner.x)).add(up.mul(corner.y));

  const centred = tslUV().sub(vec2(0.5)).mul(2);
  const radius = centred.length();
  const halo = radius.oneMinus().max(0).pow(2.0);
  const core = smoothstep(0.0, 0.36, radius).oneMinus().pow(1.35);
  const noise = mx_noise_float(vec3(centred.mul(1.7), worldTime.mul(0.18).add(style.z.mul(13.0))));
  const shimmer = noise.mul(0.035).add(1.0);
  const pulse = sin(worldTime.mul(0.70).add(style.z.mul(TWO_PI))).mul(0.07).add(0.93);
  const shape = halo.mul(0.55).add(core.mul(0.45)).clamp(0, 1);

  const warmCentre = color(swatch("cloud_cream"));
  const violetCentre = color(swatch("violet_glow"));
  const violetRim = color(swatch("violet_body"));
  const centreColor = mix(warmCentre, violetCentre, style.y);
  const rimColor = mix(warmCentre, violetRim, style.y);
  material.colorNode = mix(centreColor, rimColor, smoothstep(0.15, 1.0, radius).mul(0.75)).mul(1.15);
  material.opacityNode = shape
    .mul(style.x)
    .mul(pulse)
    .mul(shimmer)
    .mul(0.65)
    .clamp(0, 0.8);
  return material;
}

function lightColumnGeometry(radiusTop: number, radiusBottom: number, radialSegments: number) {
  return new CylinderGeometry(radiusTop, radiusBottom, 1, radialSegments, 1, true);
}

function geometryTriangles(geometry: { index: { count: number } | null; getAttribute(name: "position"): { count: number } | undefined }) {
  return Math.round((geometry.index ? geometry.index.count : (geometry.getAttribute("position")?.count ?? 0)) / 3);
}

export interface LandmarkEffectsOptions {
  quality?: QualityName | { name: QualityName };
  /** Full-resolution terrain sampler used when an entry omits y. */
  heightAt?: (x: number, z: number) => number | undefined;
  bounds?: EffectBounds;
}

export interface LandmarkEffectsStats {
  lightColumns: number;
  crystalGlows: number;
  crystalPointLights: number;
  /** Maximum effect geometry draws when everything is visible: two column layers + one halo instanced draw. */
  drawCalls: number;
  triangles: number;
  quality: QualityName;
}

export interface LandmarkEffects {
  group: Group;
  stats: LandmarkEffectsStats;
  dispose(): void;
}

function anchorY(entry: { x: number; z: number; y?: number; y_offset: number }, heightAt: ((x: number, z: number) => number | undefined) | undefined, path: string): number {
  const base = entry.y ?? heightAt?.(entry.x, entry.z);
  if (base === undefined || !Number.isFinite(base)) {
    throw effectError(path, "y missing and no finite full-resolution terrain height is available");
  }
  return base + entry.y_offset;
}

/**
 * Builds static effect geometry. There is no per-frame CPU update: visibility-independent animation
 * is shader-local and uses the shared world-time uniform, while point lights remain constant.
 */
export function createLandmarkEffects(input: unknown, options: LandmarkEffectsOptions = {}): LandmarkEffects {
  const effects = parseSliceEffects(input, options.bounds);
  const qualityName = (typeof options.quality === "string" ? options.quality : options.quality?.name) ?? "high";
  const glowQuality = crystalGlowQuality(qualityName);
  const group = new Group();
  group.name = "landmark_effects";
  group.matrixAutoUpdate = false;
  let drawCalls = 0;
  let triangles = 0;

  const resolvedColumns = effects.light_columns.map((entry, index) => ({
    entry,
    y: anchorY(entry, options.heightAt, `effects.light_columns[${index}]`),
  }));
  if (resolvedColumns.length) {
    const data = new InstancedBufferAttribute(new Float32Array(resolvedColumns.length * 4), 4);
    const outerGeometry = lightColumnGeometry(0.62, 1.0, 20);
    const coreGeometry = lightColumnGeometry(0.27, 0.46, 16);
    outerGeometry.setAttribute("aColumn", data);
    coreGeometry.setAttribute("aColumn", data);
    const outer = new InstancedMesh(outerGeometry, lightColumnMaterial("veil"), resolvedColumns.length);
    const core = new InstancedMesh(coreGeometry, lightColumnMaterial("core"), resolvedColumns.length);
    const matrix = new Matrix4();
    const position = new Vector3();
    const scale = new Vector3();
    const identity = new Quaternion();
    resolvedColumns.forEach(({ entry, y }, index) => {
      matrix.compose(
        position.set(entry.x, y + entry.height * 0.5, entry.z),
        identity,
        scale.set(entry.radius, entry.height, entry.radius),
      );
      outer.setMatrixAt(index, matrix);
      core.setMatrixAt(index, matrix);
      data.setXYZW(index, entry.intensity, entry.violet, entry.phase, entry.height);
    });
    data.needsUpdate = true;
    outer.instanceMatrix.needsUpdate = true;
    core.instanceMatrix.needsUpdate = true;
    for (const [mesh, name, order] of [[outer, "light_columns_veil", 30], [core, "light_columns_core", 31]] as const) {
      mesh.name = name;
      mesh.renderOrder = order;
      mesh.castShadow = false;
      mesh.receiveShadow = false;
      mesh.matrixAutoUpdate = false;
      mesh.computeBoundingSphere();
      group.add(mesh);
    }
    drawCalls += 2;
    triangles += resolvedColumns.length * (geometryTriangles(outerGeometry) + geometryTriangles(coreGeometry));
  }

  const resolvedGlows = effects.crystal_glows.map((entry, index) => ({
    entry,
    y: anchorY(entry, options.heightAt, `effects.crystal_glows[${index}]`),
  }));
  let pointLightCount = 0;
  if (resolvedGlows.length) {
    const centres = new InstancedBufferAttribute(new Float32Array(resolvedGlows.length * 4), 4);
    const styles = new InstancedBufferAttribute(new Float32Array(resolvedGlows.length * 4), 4);
    const geometry = new PlaneGeometry(1, 1);
    geometry.setAttribute("aGlowCentre", centres);
    geometry.setAttribute("aGlowStyle", styles);
    // Constructing with count 0 avoids the otherwise mandatory identity-matrix initialisation.
    // The custom billboard vertex shader uses aGlowCentre instead of instanceMatrix; keep only the
    // one-instance dummy expected by three.js instead of a dead full-size matrix stream.
    const mesh = new InstancedMesh(geometry, crystalGlowMaterial(), 0);
    mesh.instanceMatrix = new InstancedBufferAttribute(new Float32Array(16), 16);
    mesh.count = resolvedGlows.length;
    resolvedGlows.forEach(({ entry, y }, index) => {
      centres.setXYZW(index, entry.x, y, entry.z, entry.radius * glowQuality.haloRadius);
      styles.setXYZW(index, entry.intensity * glowQuality.haloIntensity, entry.violet, entry.phase, 0);
    });
    centres.needsUpdate = true;
    styles.needsUpdate = true;
    mesh.name = "crystal_glow_halos";
    mesh.renderOrder = 32;
    mesh.castShadow = false;
    mesh.receiveShadow = false;
    mesh.matrixAutoUpdate = false;
    mesh.frustumCulled = false; // positions live in the custom shader, not in instanceMatrix bounds
    group.add(mesh);
    drawCalls += 1;
    triangles += resolvedGlows.length * geometryTriangles(geometry);

    const lightEntries = new Set(selectCrystalPointLights(effects.crystal_glows, glowQuality.maxPointLights));
    for (const { entry, y } of resolvedGlows) {
      if (!lightEntries.has(entry)) continue;
      const lightColour = swatch("cloud_cream").lerp(swatch("violet_glow"), entry.violet);
      const light = new PointLight(
        lightColour,
        entry.light_intensity * glowQuality.pointLightIntensity,
        entry.light_radius * glowQuality.pointLightDistance,
        2,
      );
      light.name = `crystal_glow_light${entry.id ? `_${entry.id}` : ""}`;
      light.position.set(entry.x, y, entry.z);
      light.castShadow = false;
      light.matrixAutoUpdate = false;
      light.updateMatrix();
      group.add(light);
      pointLightCount++;
    }
  }

  const stats: LandmarkEffectsStats = {
    lightColumns: effects.light_columns.length,
    crystalGlows: effects.crystal_glows.length,
    crystalPointLights: pointLightCount,
    drawCalls,
    triangles,
    quality: qualityName,
  };
  return {
    group,
    stats,
    dispose() {
      for (const child of [...group.children]) {
        if (child instanceof InstancedMesh) {
          child.geometry.dispose();
          const materials = Array.isArray(child.material) ? child.material : [child.material];
          for (const material of materials) material.dispose();
        }
        group.remove(child);
      }
    },
  };
}
