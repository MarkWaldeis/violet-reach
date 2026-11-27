// Shared GLB loading for runtime asset systems.  Several render paths need different
// instancing/LOD subsets of the same approved assets; caching the parsed GLTF prevents
// duplicate KTX2 texture uploads and repeated multi-megabyte GLB decodes.
import type { WebGPURenderer } from "three/webgpu";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { KTX2Loader } from "three/addons/loaders/KTX2Loader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

const cache = new Map<string, Promise<GLTF>>();

/** Load an approved public asset once per asset id. Callers must treat the scene as read-only. */
export function loadAssetGLB(id: string, renderer?: WebGPURenderer): Promise<GLTF> {
  const existing = cache.get(id);
  if (existing) return existing;
  const promise = (async () => {
    const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    let ktx2: KTX2Loader | undefined;
    if (renderer && typeof location !== "undefined") {
      ktx2 = new KTX2Loader().setTranscoderPath(new URL("./basis/", location.href).href).detectSupport(renderer);
      loader.setKTX2Loader(ktx2);
    }
    try {
      return await loader.loadAsync(new URL(`./assets/${id}.glb`, location.href).href);
    } finally {
      ktx2?.dispose();
    }
  })();
  cache.set(id, promise);
  promise.catch(() => {
    if (cache.get(id) === promise) cache.delete(id);
  });
  return promise;
}

/** Test hook: the runtime cache is process-wide, so unit tests can clear synthetic failures. */
export function clearAssetGLBCache() {
  cache.clear();
}
