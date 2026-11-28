import {
  Box3, Color, DoubleSide, FrontSide, Frustum, Group, InstancedMesh, Matrix4, Mesh,
  PerspectiveCamera, Sphere, Vector3, type BufferGeometry, type Material, type WebGPURenderer,
} from "three/webgpu";
import { loadAssetGLB } from "./asset-gltf.ts";
import type { InstancePlacement } from "./placements.ts";
import { placementRotation } from "./placement-rotation.ts";
import { aerialLODDistances, assetRenderOptions, chunkVisible, instanceLOD, instanceTint, lodDistances, spatialChunks, type AssetRenderOptions, type Chunk } from "./instance-lod.ts";
import { applyAssetDetailMap, prepareDetailMapsForAssets } from "./detail-maps.ts";
import { REFLECTION_LAYER, SHADOW_PROXY_LAYER } from "./quality.ts";

const REFLECTED_HERO_ASSETS = new Set(["gate_white_a", "bridge_arch_a", "column_white_a", "stair_terrace_a", "trunk_acacia_a", "trunk_acacia_b", "trunk_baobab_a", "monument_split_disc_a", "monument_rib_crown_a"]);
const REFLECTED_CANOPY_ASSETS = new Set(["tree_oak_a", "tree_beech_a", "tree_ancient_a", "tree_willow_a"]);

/** First simplified LOD usable as the reflection proxy for canopy assets, or -1 when capped to LOD0. */
export function simplifiedReflectionLOD(levels: number[]) {
  return levels.find((level) => level > 0) ?? -1;
}

/** Coarse LOD used for hero reflections; planar water reflections are low-resolution and distorted. */
export function heroReflectionLOD(levels: number[]) {
  return levels.find((level) => level >= 2) ?? (levels.length ? levels[levels.length - 1] : -1);
}

/** Coarse LOD used as a shadow-only proxy for high-poly assets, or -1 when the visible mesh is already cheap. */
export function shadowProxyLOD(levels: number[], lod0Triangles: number) {
  if (lod0Triangles < 5000 || levels.length < 2) return -1;
  return levels.find((level) => level >= 2) ?? levels[levels.length - 1];
}

interface Instance extends InstancePlacement { order: number; matrix: Matrix4; tint: Color; sphere: { centre: Vector3; radius: number }; lod: number }
interface Part { mesh: InstancedMesh; local: Matrix4; reflection?: InstancedMesh; shadow?: InstancedMesh }
interface AssetBatch { id: string; parts: Part[][]; chunks: Chunk<Instance>[]; size: number; maxDistance: number; lodScale: number; lodRatio: number; aerialLODScale: number; reflectionIndex: number; reflectionMode: "lod0" | "all" | "none"; shadowIndex: number; shadowLODs: number; partSignatures?: number[]; reflectionSignature?: number; shadowSignature?: number }

export class InstanceAssets {
  readonly group = new Group();
  #batches: AssetBatch[] = [];
  #frustum = new Frustum();
  #projection = new Matrix4();
  #matrix = new Matrix4();
  #updated = -Infinity;
  stats = { assets: 0, total: 0, lods: [] as number[], visibleChunks: 0, chunks: 0, byAsset: {} as Record<string, { lods: number[]; reflections: number; shadows: number }> };

  static async load(
    placements: InstancePlacement[],
    options: AssetRenderOptions = {},
    byAsset: Record<string, AssetRenderOptions> = {},
    renderer?: WebGPURenderer,
    detailMaps = true,
  ) {
    const result = new InstanceAssets();
    const ids = [...new Set(placements.map((p) => p.asset))];
    if (detailMaps) await prepareDetailMapsForAssets(ids);
      for (const id of ids) {
        const gltf = await loadAssetGLB(id, renderer);
        gltf.scene.updateMatrixWorld(true);
        const levels = new Map<number, Mesh<BufferGeometry, Material | Material[]>[]>();
        gltf.scene.traverse((node) => {
          if (!(node as Mesh).isMesh) return;
          let owner = node;
          while (!/_LOD\d+$/.test(owner.name) && owner.parent && owner.parent !== gltf.scene) owner = owner.parent;
          const suffix = /_LOD(\d+)$/.exec(owner.name);
          if (!suffix) throw new Error(`${id}: mesh without _LOD<n> node`);
          const lod = Number(suffix[1]);
          if (!levels.has(lod)) levels.set(lod, []);
          levels.get(lod)!.push(node as Mesh<BufferGeometry, Material | Material[]>);
        });
        const ordered = [...levels.keys()].sort((a, b) => a - b);
        if (!ordered.length) throw new Error(`${id}: no LOD meshes`);
        const bounds = new Box3();
        for (const node of levels.get(ordered[0])!) bounds.expandByObject(node);
        const size = bounds.getSize(new Vector3()).length();
        const rootRadius = bounds.getCenter(new Vector3()).length() + size / 2;
        const localSphere = bounds.getBoundingSphere(new Sphere());
        const settings = assetRenderOptions(size, options, byAsset[id]);
        const instances: Instance[] = placements.filter((p) => p.asset === id).map((p, order) => {
          const rotation = placementRotation(p);
          const matrix = new Matrix4().compose(new Vector3(p.x, p.y, p.z), rotation, new Vector3().setScalar(p.scale));
          const sphere = localSphere.clone().applyMatrix4(matrix);
          return { ...p, order, matrix, sphere: { centre: sphere.center, radius: sphere.radius }, tint: new Color(...instanceTint(p.x, p.z, settings.tintVariation)), lod: -1 };
        });
        const renderLevels = ordered.filter((level) => level <= settings.maxLOD);
        const canopyReflection = REFLECTED_CANOPY_ASSETS.has(id) ? simplifiedReflectionLOD(renderLevels) : -1;
        const heroReflection = REFLECTED_HERO_ASSETS.has(id) ? heroReflectionLOD(renderLevels) : -1;
        const reflectionLOD = heroReflection >= 0 ? heroReflection : canopyReflection;
        const reflectionIndex = reflectionLOD >= 0 ? renderLevels.indexOf(reflectionLOD) : -1;
        const reflectionMode = heroReflection >= 0 ? "all" as const : reflectionIndex >= 0 ? "lod0" as const : "none" as const;
        const lod0Triangles = levels.get(ordered[0])!.reduce((sum, node) => sum + (node.geometry.index?.count ?? node.geometry.attributes.position.count) / 3, 0);
        const shadowLOD = settings.shadowLODs > 0
          ? (REFLECTED_CANOPY_ASSETS.has(id) ? simplifiedReflectionLOD(renderLevels) : shadowProxyLOD(renderLevels, lod0Triangles))
          : -1;
        const shadowIndex = shadowLOD >= 0 ? renderLevels.indexOf(shadowLOD) : -1;
        const parts = renderLevels.map((level, index) => {
          const parts: Part[] = [];
          for (const source of levels.get(level)!) {
            const materials = Array.isArray(source.material) ? source.material : [source.material];
            const groups = Array.isArray(source.material) ? source.geometry.groups : [{ start: 0, count: source.geometry.index?.count ?? source.geometry.attributes.position.count, materialIndex: 0 }];
            for (const group of groups) {
              const geometry = source.geometry.clone();
              geometry.clearGroups();
              geometry.setDrawRange(group.start, group.count);
              const baseMat = materials[group.materialIndex ?? 0];
              // Most GLB mineral exports are double-sided even when they are closed opaque solids.
              // Culling their backfaces nearly halves the fill cost of bridge/gate/cliff interiors;
              // alpha-tested leaf cards and translucent materials deliberately keep DoubleSide.
              if (baseMat?.side === DoubleSide && baseMat.alphaTest === 0 && !baseMat.transparent) baseMat.side = FrontSide;
              const mat = detailMaps && baseMat ? applyAssetDetailMap(baseMat, id) : baseMat;
              const mesh = new InstancedMesh(geometry, mat, instances.length);
              mesh.name = `${id}_LOD${level}`;
              mesh.count = 0;
              mesh.setColorAt(0, new Color(1, 1, 1));
              // CPU chunk culling is based on the viewer camera, never the shadow camera.
              mesh.frustumCulled = false;
              mesh.receiveShadow = index < settings.shadowLODs;
              mesh.castShadow = shadowIndex < 0 && index < settings.shadowLODs;
              if (REFLECTED_CANOPY_ASSETS.has(id) && level >= 1) {
                mesh.layers.enable(REFLECTION_LAYER);
              }
              result.group.add(mesh);
              const part: Part = { mesh, local: source.matrixWorld.clone() };
              if (index === reflectionIndex) {
                // Trees closest to the viewer use LOD0 in the main pass. Reflecting only their
                // assigned LOD mesh would therefore omit exactly the nearest shoreline crowns.
                // This reflection-only simplified-LOD proxy keeps the main pass cheap while giving
                // those trees a simplified water reflection.
                const reflection = new InstancedMesh(geometry, baseMat ?? mat, instances.length);
                reflection.name = `${id}_REFLECT_LOD${level}`;
                reflection.count = 0;
                reflection.setColorAt(0, new Color(1, 1, 1));
                reflection.frustumCulled = false;
                reflection.castShadow = reflection.receiveShadow = false;
                reflection.layers.set(REFLECTION_LAYER);
                result.group.add(reflection);
                part.reflection = reflection;
              }
              if (index === shadowIndex) {
                const shadow = new InstancedMesh(geometry, baseMat ?? mat, instances.length);
                shadow.name = `${id}_SHADOW_LOD${level}`;
                shadow.count = 0;
                shadow.setColorAt(0, new Color(1, 1, 1));
                shadow.frustumCulled = false;
                shadow.castShadow = true;
                shadow.receiveShadow = false;
                shadow.layers.set(SHADOW_PROXY_LAYER);
                result.group.add(shadow);
                part.shadow = shadow;
              }
              parts.push(part);
            }
          }
          return parts;
        });
        const chunks = spatialChunks(instances, (p) => rootRadius * p.scale);
        result.#batches.push({ id, parts, chunks, size, maxDistance: settings.maxDistance, lodScale: settings.lodScale, lodRatio: settings.lodRatio, aerialLODScale: settings.aerialLODScale, reflectionIndex, reflectionMode, shadowIndex, shadowLODs: settings.shadowLODs });
      }
    result.stats.assets = result.#batches.length;
    result.stats.total = placements.length;
    return result;
  }

  update(camera: PerspectiveCamera, viewportHeight: number, now: number, heightAboveGround = 0) {
    if (now - this.#updated < 100) return;
    this.#updated = now;
    camera.updateMatrixWorld();
    this.#projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.#frustum.setFromProjectionMatrix(this.#projection, camera.coordinateSystem);
    const planes = this.#frustum.planes.map((p) => ({ ...p.normal, constant: p.constant }));
    const counts: number[] = [];
    const byAsset: Record<string, { lods: number[]; reflections: number; shadows: number }> = {};
    let visibleChunks = 0, chunks = 0;
    for (const batch of this.#batches) {
      const distances = aerialLODDistances(lodDistances(batch.size * batch.lodScale, batch.parts.length, viewportHeight, camera.fov, batch.maxDistance, batch.lodRatio), heightAboveGround, batch.aerialLODScale);
      const written = batch.parts.map(() => 0);
      const batchCounts = batch.parts.map(() => 0);
      const partSignatures = batch.parts.map(() => 0);
      let reflectionWritten = 0;
      let reflectionSignature = 0;
      let shadowWritten = 0;
      let shadowSignature = 0;
      for (const chunk of batch.chunks) {
        chunks++;
        if (!chunkVisible(chunk, camera.position, planes, batch.maxDistance * 1.12)) continue;
        visibleChunks++;
        for (const instance of chunk.items) {
          const distance = Math.hypot(instance.x - camera.position.x, instance.y - camera.position.y, instance.z - camera.position.z);
          const scaledDistances = distances.map((d) => d === batch.maxDistance ? d : Math.min(batch.maxDistance, d * instance.scale));
          const lod = instance.lod = instanceLOD(distance, scaledDistances, instance.lod);
          if (lod === batch.parts.length) continue;
          const castsShadow = batch.shadowIndex >= 0 ? lod < batch.shadowLODs : batch.parts[lod].some((part) => part.mesh.castShadow);
          const inCamera = chunkVisible(instance.sphere, camera.position, planes, Infinity);
          if (!castsShadow && !inCamera) continue;
          if (batch.shadowIndex >= 0 && castsShadow) {
            shadowSignature = Math.imul(shadowSignature ^ (instance.order + 1), 16777619);
            const proxyIndex = shadowWritten++;
            for (const part of batch.parts[batch.shadowIndex]) {
              if (!part.shadow) continue;
              this.#matrix.multiplyMatrices(instance.matrix, part.local);
              part.shadow.setMatrixAt(proxyIndex, this.#matrix);
              part.shadow.setColorAt(proxyIndex, instance.tint);
            }
          }
          if ((batch.reflectionMode === "all" || lod === 0) && batch.reflectionIndex >= 0) {
            reflectionSignature = Math.imul(reflectionSignature ^ (instance.order + 1), 16777619);
            const proxyIndex = reflectionWritten++;
            for (const part of batch.parts[batch.reflectionIndex]) {
              if (!part.reflection) continue;
              this.#matrix.multiplyMatrices(instance.matrix, part.local);
              part.reflection.setMatrixAt(proxyIndex, this.#matrix);
              part.reflection.setColorAt(proxyIndex, instance.tint);
            }
          }
          if (batch.shadowIndex >= 0 && !inCamera) continue;
          partSignatures[lod] = Math.imul(partSignatures[lod] ^ (instance.order + 1), 16777619);
          const index = written[lod]++;
          batchCounts[lod]++;
          for (const part of batch.parts[lod]) {
            this.#matrix.multiplyMatrices(instance.matrix, part.local);
            part.mesh.setMatrixAt(index, this.#matrix);
            part.mesh.setColorAt(index, instance.tint);
          }
        }
      }
      written.forEach((count, lod) => {
        partSignatures[lod] = Math.imul(partSignatures[lod] ^ (count + 1), 16777619);
      });
      reflectionSignature = Math.imul(reflectionSignature ^ (reflectionWritten + 1), 16777619);
      shadowSignature = Math.imul(shadowSignature ^ (shadowWritten + 1), 16777619);
      const partUnchanged = partSignatures.map((signature, lod) => batch.partSignatures?.[lod] === signature);
      const reflectionUnchanged = batch.reflectionSignature === reflectionSignature;
      const shadowUnchanged = batch.shadowSignature === shadowSignature;
      batch.partSignatures = partSignatures;
      batch.reflectionSignature = reflectionSignature;
      batch.shadowSignature = shadowSignature;
      batch.parts.forEach((parts, lod) => {
        counts[lod] = (counts[lod] ?? 0) + written[lod];
        for (const part of parts) {
          part.mesh.count = written[lod];
          part.mesh.visible = written[lod] > 0;
          if (written[lod] && !partUnchanged[lod]) {
            const matrix = part.mesh.instanceMatrix, tint = part.mesh.instanceColor!;
            matrix.clearUpdateRanges();
            matrix.addUpdateRange(0, written[lod] * matrix.itemSize);
            matrix.needsUpdate = true;
            tint.clearUpdateRanges();
            tint.addUpdateRange(0, written[lod] * tint.itemSize);
            tint.needsUpdate = true;
          }
          if (part.reflection) {
            part.reflection.count = reflectionWritten;
            part.reflection.visible = reflectionWritten > 0;
            if (reflectionWritten && !reflectionUnchanged) {
              const matrix = part.reflection.instanceMatrix, tint = part.reflection.instanceColor!;
              matrix.clearUpdateRanges();
              matrix.addUpdateRange(0, reflectionWritten * matrix.itemSize);
              matrix.needsUpdate = true;
              tint.clearUpdateRanges();
              tint.addUpdateRange(0, reflectionWritten * tint.itemSize);
              tint.needsUpdate = true;
            }
          }
          if (part.shadow) {
            part.shadow.count = shadowWritten;
            part.shadow.visible = shadowWritten > 0;
            if (shadowWritten && !shadowUnchanged) {
              const matrix = part.shadow.instanceMatrix, tint = part.shadow.instanceColor!;
              matrix.clearUpdateRanges();
              matrix.addUpdateRange(0, shadowWritten * matrix.itemSize);
              matrix.needsUpdate = true;
              tint.clearUpdateRanges();
              tint.addUpdateRange(0, shadowWritten * tint.itemSize);
              tint.needsUpdate = true;
            }
          }
        }
      });
      byAsset[batch.id] = { lods: batchCounts, reflections: reflectionWritten, shadows: shadowWritten };
    }
    this.stats = { ...this.stats, lods: counts, visibleChunks, chunks, byAsset };
  }
}
