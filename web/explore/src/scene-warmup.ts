import type { Camera, InstancedMesh, Mesh, Object3D, Scene, WebGPURenderer } from "three/webgpu";

export async function warmScene(
  renderer: Pick<WebGPURenderer, "compileAsync" | "render">,
  scene: Scene,
  camera: Camera,
  extraPass?: () => void,
) {
  const saved: { node: Object3D; visible: boolean; culled: boolean; count?: number }[] = [];
  scene.traverse((node) => {
    const instanced = (node as InstancedMesh).isInstancedMesh;
    saved.push({ node, visible: node.visible, culled: node.frustumCulled, count: instanced ? (node as InstancedMesh).count : undefined });
    node.visible = true;
    if ((node as Mesh).isMesh) node.frustumCulled = false;
    if (instanced) (node as InstancedMesh).count = Math.max(1, (node as InstancedMesh).count);
  });
  try {
    await renderer.compileAsync(scene, camera);
    renderer.render(scene, camera);
    extraPass?.();
  } finally {
    for (const { node, visible, culled, count } of saved) {
      node.visible = visible;
      node.frustumCulled = culled;
      if (count !== undefined) (node as InstancedMesh).count = count;
    }
  }
}
