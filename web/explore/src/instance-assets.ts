import {
  Box3, DynamicDrawUsage, Frustum, Group, InstancedMesh, Matrix4, Mesh,
  PerspectiveCamera, Quaternion, Vector3, type BufferGeometry, type Material,
} from "three/webgpu";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import type { InstancePlacement } from "./placements.ts";
import { chunkVisible, instanceLOD, lodDistances, spatialChunks, type Chunk } from "./instance-lod.ts";

interface Instance extends InstancePlacement { matrix: Matrix4; lod: number }
interface Part { mesh: InstancedMesh; local: Matrix4 }
interface AssetBatch { parts: Part[][]; chunks: Chunk<Instance>[]; size: number; maxDistance: number }
export interface InstanceOptions { maxDistance?: number; shadowLODs?: number }

export class InstanceAssets {
  readonly group = new Group();
  #batches: AssetBatch[] = [];
  #frustum = new Frustum();
  #projection = new Matrix4();
  #matrix = new Matrix4();
  #updated = -Infinity;
  stats = { assets: 0, total: 0, lods: [] as number[], visibleChunks: 0, chunks: 0 };

  static async load(placements: InstancePlacement[], options: InstanceOptions = {}) {
    const result = new InstanceAssets();
    const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    const ids = [...new Set(placements.map((p) => p.asset))];
    for (const id of ids) {
      const gltf = await loader.loadAsync(new URL(`./assets/${id}.glb`, location.href).href);
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
      const instances: Instance[] = placements.filter((p) => p.asset === id).map((p) => {
        const rotation = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), p.yaw);
        if (p.normal) rotation.premultiply(new Quaternion().setFromUnitVectors(new Vector3(0, 1, 0), new Vector3(...p.normal).normalize()));
        return { ...p, matrix: new Matrix4().compose(new Vector3(p.x, p.y, p.z), rotation, new Vector3().setScalar(p.scale)), lod: -1 };
      });
      const parts = ordered.map((level, index) => {
        const parts: Part[] = [];
        for (const source of levels.get(level)!) {
          const materials = Array.isArray(source.material) ? source.material : [source.material];
          const groups = Array.isArray(source.material) ? source.geometry.groups : [{ start: 0, count: source.geometry.index?.count ?? source.geometry.attributes.position.count, materialIndex: 0 }];
          for (const group of groups) {
            const geometry = source.geometry.clone();
            geometry.clearGroups();
            geometry.setDrawRange(group.start, group.count);
            const mesh = new InstancedMesh(geometry, materials[group.materialIndex ?? 0], instances.length);
            mesh.name = `${id}_LOD${level}`;
            mesh.count = 0;
            mesh.instanceMatrix.setUsage(DynamicDrawUsage);
            // CPU chunk culling is based on the viewer camera, never the shadow camera.
            mesh.frustumCulled = false;
            mesh.castShadow = mesh.receiveShadow = index < (options.shadowLODs ?? 2);
            result.group.add(mesh);
            parts.push({ mesh, local: source.matrixWorld.clone() });
          }
        }
        return parts;
      });
      const chunks = spatialChunks(instances, (p) => rootRadius * p.scale);
      result.#batches.push({ parts, chunks, size, maxDistance: options.maxDistance ?? size * 40 });
    }
    result.stats.assets = result.#batches.length;
    result.stats.total = placements.length;
    return result;
  }

  update(camera: PerspectiveCamera, viewportHeight: number, now: number) {
    if (now - this.#updated < 100) return;
    this.#updated = now;
    camera.updateMatrixWorld();
    this.#projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.#frustum.setFromProjectionMatrix(this.#projection, camera.coordinateSystem);
    const planes = this.#frustum.planes.map((p) => ({ ...p.normal, constant: p.constant }));
    const counts: number[] = [];
    let visibleChunks = 0, chunks = 0;
    for (const batch of this.#batches) {
      const distances = lodDistances(batch.size, batch.parts.length, viewportHeight, camera.fov, batch.maxDistance);
      const written = batch.parts.map(() => 0);
      for (const chunk of batch.chunks) {
        chunks++;
        if (!chunkVisible(chunk, camera.position, planes, batch.maxDistance * 1.12)) continue;
        visibleChunks++;
        for (const instance of chunk.items) {
          const distance = Math.hypot(instance.x - camera.position.x, instance.y - camera.position.y, instance.z - camera.position.z);
          const scaledDistances = distances.map((d) => d === batch.maxDistance ? d : Math.min(batch.maxDistance, d * instance.scale));
          const lod = instance.lod = instanceLOD(distance, scaledDistances, instance.lod);
          if (lod === batch.parts.length) continue;
          const index = written[lod]++;
          for (const part of batch.parts[lod]) {
            this.#matrix.multiplyMatrices(instance.matrix, part.local);
            part.mesh.setMatrixAt(index, this.#matrix);
          }
        }
      }
      batch.parts.forEach((parts, lod) => {
        counts[lod] = (counts[lod] ?? 0) + written[lod];
        for (const part of parts) {
          part.mesh.count = written[lod];
          part.mesh.visible = written[lod] > 0;
          if (written[lod]) part.mesh.instanceMatrix.needsUpdate = true;
        }
      });
    }
    this.stats = { ...this.stats, lods: counts, visibleChunks, chunks };
  }
}
