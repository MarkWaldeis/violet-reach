// Sparse volumetric far vegetation for the 8x8 km world outside the hand-dressed slice.
// The offline generator (tools/world/build_farveg.py) provides deterministic, terrain-anchored
// instances. This runtime deliberately uses only the approved tree LOD3 meshes: no shadow
// passes, no reflection layer, no per-instance LOD switching and no placeholder billboards.
import {
  Box3, Color, Frustum, Group, InstancedMesh, Matrix4, Mesh, PerspectiveCamera, Quaternion,
  Sphere, Vector3, type BufferGeometry, type Material, type WebGPURenderer,
} from "three/webgpu";
import { loadAssetGLB } from "./asset-gltf.ts";
import { chunkVisible, instanceTint, spatialChunks, type Chunk } from "./instance-lod.ts";

export const FARVEG_FORMAT = "violet-reach-farveg-json";
export const FARVEG_VERSION = 1;
export const FARVEG_VARIANTS = ["tree_oak_a", "tree_beech_a", "tree_willow_a", "tree_ancient_a"] as const;
export type FarvegVariant = typeof FARVEG_VARIANTS[number];

export interface FarvegInstanceData {
  x: number;
  y: number;
  z: number;
  variant: FarvegVariant;
  scale: number;
  yaw: number;
  priority: number;
  embed: number;
}

export interface FarvegPayload {
  format: typeof FARVEG_FORMAT;
  version: typeof FARVEG_VERSION;
  instance_count: number;
  instances: FarvegInstanceData[];
}

export interface FarvegOptions {
  /** metres; normally scaled by the active quality level's assetDistanceScale */
  maxDistance?: number;
  /** metres; bark primitives are omitted beyond this range because trunks are subpixel accents there */
  trunkDistance?: number;
  /** 0 disables far priority thinning; 0.25 would drop priorities below 0.25 exactly at maxDistance */
  distantPriorityCut?: number;
  /** spatial CPU-culling cell size in metres */
  cellSize?: number;
  /** canopy colour variation matching the regular tree instances */
  tintVariation?: number;
  canopyBrightness?: number;
  canopyEmissionScale?: number;
}

export interface ResolvedFarvegOptions {
  maxDistance: number;
  trunkDistance: number;
  distantPriorityCut: number;
  cellSize: number;
  tintVariation: number;
  canopyBrightness: number;
  canopyEmissionScale: number;
}

const VARIANT_SET = new Set<string>(FARVEG_VARIANTS);
const Y_AXIS = new Vector3(0, 1, 0);

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Validate the versioned offline payload strictly enough to fail loudly on stale/generator mismatches. */
export function parseFarvegPayload(value: unknown): FarvegPayload {
  if (!value || typeof value !== "object") throw new Error("farveg.json: Objekt erwartet");
  const raw = value as Record<string, unknown>;
  if (raw.format !== FARVEG_FORMAT) throw new Error(`farveg.json: format ${FARVEG_FORMAT} erwartet`);
  if (raw.version !== FARVEG_VERSION) throw new Error(`farveg.json: version ${FARVEG_VERSION} erwartet`);
  if (!Number.isSafeInteger(raw.instance_count) || (raw.instance_count as number) < 0) throw new Error("farveg.json: ungültige instance_count");
  if (!Array.isArray(raw.instances)) throw new Error("farveg.json: instances muss ein Array sein");
  if (raw.instances.length !== raw.instance_count) throw new Error("farveg.json: instance_count passt nicht zu instances");
  const instances = raw.instances.map((entry, index) => {
    if (!entry || typeof entry !== "object") throw new Error(`farveg.json Instanz ${index}: Objekt erwartet`);
    const p = entry as Record<string, unknown>;
    if (!finite(p.x) || !finite(p.y) || !finite(p.z) || !finite(p.yaw) || !finite(p.priority) || !finite(p.embed)) {
      throw new Error(`farveg.json Instanz ${index}: x/y/z/yaw/priority/embed müssen endliche Zahlen sein`);
    }
    if (!finite(p.scale) || p.scale <= 0) throw new Error(`farveg.json Instanz ${index}: scale muss positiv sein`);
    if (typeof p.variant !== "string" || !VARIANT_SET.has(p.variant)) throw new Error(`farveg.json Instanz ${index}: unbekannte Variante`);
    if (p.priority < 0 || p.priority > 1) throw new Error(`farveg.json Instanz ${index}: priority ausserhalb 0..1`);
    if (p.embed < 0) throw new Error(`farveg.json Instanz ${index}: embed muss nichtnegativ sein`);
    return {
      x: p.x, y: p.y, z: p.z, variant: p.variant as FarvegVariant,
      scale: p.scale, yaw: p.yaw, priority: p.priority, embed: p.embed,
    };
  });
  for (let i = 1; i < instances.length; i++) {
    if (instances[i - 1].priority < instances[i].priority) throw new Error(`farveg.json Instanz ${i}: Prioritäten müssen absteigend sortiert sein`);
  }
  return { format: FARVEG_FORMAT, version: FARVEG_VERSION, instance_count: raw.instance_count as number, instances };
}

/** Clone a canopy material for far vegetation and reduce only its emissive translucency floor. */
export function cloneFarCanopyMaterial(source: Material, emissionScale: number): Material {
  if (!Number.isFinite(emissionScale) || emissionScale < 0 || emissionScale > 1) throw new Error("Invalid far canopy emission scale");
  const material = source.clone() as Material & { emissive?: Color; emissiveIntensity?: number };
  if (typeof material.emissiveIntensity === "number") material.emissiveIntensity *= emissionScale;
  else material.emissive?.multiplyScalar(emissionScale);
  return material;
}

/** Resolve conservative distance defaults from the active quality scale. */
export function resolveFarvegOptions(assetDistanceScale = 1, options: FarvegOptions = {}): ResolvedFarvegOptions {
  if (!Number.isFinite(assetDistanceScale) || assetDistanceScale <= 0) throw new Error("Invalid far vegetation distance settings");
  const maxDistance = options.maxDistance ?? 3800 * assetDistanceScale;
  const trunkDistance = options.trunkDistance ?? Math.min(1400, maxDistance * 0.75);
  const distantPriorityCut = options.distantPriorityCut ?? 0;
  const cellSize = options.cellSize ?? 256;
  const tintVariation = options.tintVariation ?? 0.06;
  const canopyBrightness = options.canopyBrightness ?? 0.72;
  const canopyEmissionScale = options.canopyEmissionScale ?? 0.45;
  if (![maxDistance, trunkDistance, cellSize].every((n) => Number.isFinite(n) && n > 0) || trunkDistance > maxDistance) {
    throw new Error("Invalid far vegetation distance settings");
  }
  if (!Number.isFinite(distantPriorityCut) || distantPriorityCut < 0 || distantPriorityCut > 1) throw new Error("Invalid far vegetation priority thinning");
  if (!Number.isFinite(tintVariation) || tintVariation < 0 || tintVariation > 1 || !Number.isFinite(canopyBrightness) || canopyBrightness < 0.4 || canopyBrightness > 1 || !Number.isFinite(canopyEmissionScale) || canopyEmissionScale < 0 || canopyEmissionScale > 1) throw new Error("Invalid far vegetation tint variation");
  return { maxDistance, trunkDistance, distantPriorityCut, cellSize, tintVariation, canopyBrightness, canopyEmissionScale };
}

/**
 * Optional deterministic distance thinning. It begins at 55% of maxDistance and reaches
 * ``thinning`` exactly at maxDistance. This is a pure function so the visual/performance
 * trade-off can be regression-tested without constructing WebGL resources.
 */
export function farvegPriorityVisible(priority: number, distance: number, maxDistance: number, thinning = 0): boolean {
  if (![priority, distance, maxDistance, thinning].every(Number.isFinite) || maxDistance <= 0) throw new Error("Invalid far vegetation visibility input");
  if (thinning <= 0 || distance <= maxDistance * 0.55) return true;
  const t = Math.min(1, Math.max(0, (distance - maxDistance * 0.55) / (maxDistance * 0.45)));
  return priority >= t * thinning;
}

interface RuntimeInstance extends FarvegInstanceData {
  order: number;
  matrix: Matrix4;
  tint: Color;
  sphere: { centre: Vector3; radius: number };
}

interface FarvegPart {
  mesh: InstancedMesh;
  local: Matrix4;
  triangles: number;
  bark: boolean;
}

interface VariantBatch {
  id: FarvegVariant;
  parts: FarvegPart[];
  instances: RuntimeInstance[];
  chunks: Chunk<RuntimeInstance>[];
  size: number;
  signature?: number;
}

function meshTriangles(geometry: BufferGeometry): number {
  return Math.floor((geometry.drawRange.count === Infinity
    ? geometry.index?.count ?? geometry.attributes.position.count
    : geometry.drawRange.count) / 3);
}

function isBarkMaterial(material: Material): boolean {
  return material.name.toLowerCase().includes("bark");
}

/**
 * Runtime renderer for static offline far-vegetation instances. Matrices are built once;
 * the periodic update only compacts currently visible instances into contiguous prefixes,
 * matching the upload strategy of InstanceAssets but without any shadow/reflection copies.
 */
export class FarVegetation {
  readonly group = new Group();
  #batches: VariantBatch[] = [];
  #frustum = new Frustum();
  #projection = new Matrix4();
  #matrix = new Matrix4();
  #white = new Color(1, 1, 1);
  #updated = -Infinity;
  #options: ResolvedFarvegOptions;
  stats = {
    instances: 0,
    visibleInstances: 0,
    triangles: 0,
    drawCalls: 0,
    chunks: 0,
    visibleChunks: 0,
    variants: {} as Record<string, { total: number; visible: number; triangles: number }>,
  };

  private constructor(options: ResolvedFarvegOptions) {
    this.#options = options;
    this.group.name = "far_vegetation";
  }

  static async load(
    payload: FarvegPayload,
    options: ResolvedFarvegOptions,
    renderer?: WebGPURenderer,
  ): Promise<FarVegetation> {
    const result = new FarVegetation(options);
    const byVariant = new Map<FarvegVariant, FarvegInstanceData[]>();
      for (const variant of FARVEG_VARIANTS) byVariant.set(variant, []);
      for (const instance of payload.instances) byVariant.get(instance.variant)!.push(instance);
      for (const variant of FARVEG_VARIANTS) {
        const sourceInstances = byVariant.get(variant)!;
        if (!sourceInstances.length) continue;
        const gltf = await loadAssetGLB(variant, renderer);
        gltf.scene.updateMatrixWorld(true);
        const targetLod = 3;
        const lodNodes: Mesh<BufferGeometry, Material | Material[]>[] = [];
        gltf.scene.traverse((node) => {
          if (!(node as Mesh).isMesh) return;
          let owner = node;
          while (!/_LOD\d+$/.test(owner.name) && owner.parent && owner.parent !== gltf.scene) owner = owner.parent;
          const suffix = /_LOD(\d+)$/.exec(owner.name);
          if (suffix && Number(suffix[1]) === targetLod) lodNodes.push(node as Mesh<BufferGeometry, Material | Material[]>);
        });
        if (!lodNodes.length) throw new Error(`${variant}: exakt LOD3 wird für Fernvegetation benötigt`);
        const bestLod = targetLod;

        const bounds = new Box3();
        for (const node of lodNodes) bounds.expandByObject(node);
        const size = bounds.getSize(new Vector3()).length();
        const localSphere = bounds.getBoundingSphere(new Sphere());
        const instances: RuntimeInstance[] = sourceInstances.map((p, order) => {
          const rotation = new Quaternion().setFromAxisAngle(Y_AXIS, p.yaw);
          const matrix = new Matrix4().compose(new Vector3(p.x, p.y, p.z), rotation, new Vector3().setScalar(p.scale));
          const sphere = localSphere.clone().applyMatrix4(matrix);
          return {
            ...p,
            order,
            matrix,
            sphere: { centre: sphere.center, radius: sphere.radius },
            tint: new Color(...instanceTint(p.x, p.z, options.tintVariation)).multiplyScalar(options.canopyBrightness),
          };
        });

        const parts: FarvegPart[] = [];
        const farMaterials = new Map<Material, Material>();
        for (const source of lodNodes) {
          const materials = Array.isArray(source.material) ? source.material : [source.material];
          const groups = Array.isArray(source.material)
            ? source.geometry.groups
            : [{ start: 0, count: source.geometry.index?.count ?? source.geometry.attributes.position.count, materialIndex: 0 }];
          for (const group of groups) {
            const geometry = source.geometry.clone();
            geometry.clearGroups();
            geometry.setDrawRange(group.start, group.count);
            const sourceMaterial = materials[group.materialIndex ?? 0];
            if (!sourceMaterial) continue;
            const bark = isBarkMaterial(sourceMaterial);
            let material = sourceMaterial;
            if (!bark) {
              material = farMaterials.get(sourceMaterial) ?? cloneFarCanopyMaterial(sourceMaterial, options.canopyEmissionScale);
              farMaterials.set(sourceMaterial, material);
            }
            const mesh = new InstancedMesh(geometry, material, instances.length);
            mesh.name = `${variant}_far_LOD${bestLod}${bark ? "_bark" : "_canopy"}`;
            mesh.count = 0;
            mesh.setColorAt(0, new Color(1, 1, 1));
            mesh.frustumCulled = false;
            mesh.castShadow = false;
            mesh.receiveShadow = false;
            result.group.add(mesh);
            parts.push({ mesh, local: source.matrixWorld.clone(), triangles: meshTriangles(geometry), bark });
          }
        }
        if (!parts.length) throw new Error(`${variant}: keine renderbaren LOD-Materialgruppen`);
        const conservativeRadius = localSphere.center.length() + localSphere.radius;
        const chunks = spatialChunks(instances, (p) => conservativeRadius * p.scale, options.cellSize);
        result.#batches.push({ id: variant, parts, instances, chunks, size });
      }
    result.stats.instances = payload.instance_count;
    result.stats.chunks = result.#batches.reduce((sum, batch) => sum + batch.chunks.length, 0);
    return result;
  }

  update(camera: PerspectiveCamera, now: number) {
    if (now - this.#updated < 100) return;
    this.#updated = now;
    camera.updateMatrixWorld();
    this.#projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.#frustum.setFromProjectionMatrix(this.#projection, camera.coordinateSystem);
    const planes = this.#frustum.planes.map((p) => ({ ...p.normal, constant: p.constant }));
    const options = this.#options;
    let visibleInstances = 0, triangles = 0, drawCalls = 0, visibleChunks = 0;
    const variants: Record<string, { total: number; visible: number; triangles: number }> = {};

    for (const batch of this.#batches) {
      const written = batch.parts.map(() => 0);
      let batchVisible = 0, batchTriangles = 0;
      let signature = 0;
      for (const chunk of batch.chunks) {
        if (!chunkVisible(chunk, camera.position, planes, options.maxDistance * 1.05)) continue;
        visibleChunks++;
        for (const instance of chunk.items) {
          const distance = Math.hypot(instance.x - camera.position.x, instance.y - camera.position.y, instance.z - camera.position.z);
          if (distance > options.maxDistance) continue;
          if (!farvegPriorityVisible(instance.priority, distance, options.maxDistance, options.distantPriorityCut)) continue;
          if (!chunkVisible(instance.sphere, camera.position, planes, Infinity)) continue;
          const barkVisible = distance <= options.trunkDistance;
          signature = Math.imul(signature ^ (instance.order + 1), 16777619) ^ (barkVisible ? 0x9e3779b9 : 0);
          batchVisible++;
          for (let partIndex = 0; partIndex < batch.parts.length; partIndex++) {
            const part = batch.parts[partIndex];
            if (part.bark && distance > options.trunkDistance) continue;
            const index = written[partIndex]++;
            this.#matrix.multiplyMatrices(instance.matrix, part.local);
            part.mesh.setMatrixAt(index, this.#matrix);
            part.mesh.setColorAt(index, part.bark ? this.#white : instance.tint);
          }
        }
      }
      for (const count of written) signature = Math.imul(signature ^ (count + 1), 16777619);
      const unchanged = batch.signature === signature;
      batch.signature = signature;
      batch.parts.forEach((part, partIndex) => {
        const count = written[partIndex];
        part.mesh.count = count;
        part.mesh.visible = count > 0;
        if (count) {
          drawCalls++;
          batchTriangles += part.triangles * count;
          if (!unchanged) {
            const matrix = part.mesh.instanceMatrix, tint = part.mesh.instanceColor!;
            matrix.clearUpdateRanges();
            matrix.addUpdateRange(0, count * matrix.itemSize);
            matrix.needsUpdate = true;
            tint.clearUpdateRanges();
            tint.addUpdateRange(0, count * tint.itemSize);
            tint.needsUpdate = true;
          }
        }
      });
      visibleInstances += batchVisible;
      triangles += batchTriangles;
      variants[batch.id] = { total: batch.instances.length, visible: batchVisible, triangles: batchTriangles };
    }

    this.stats = {
      ...this.stats,
      visibleInstances,
      triangles,
      drawCalls,
      visibleChunks,
      variants,
    };
  }
}
