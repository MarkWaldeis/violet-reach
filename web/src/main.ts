import * as THREE from "three/webgpu";
import { pass } from "three/tsl";
import { bloom } from "three/addons/tsl/display/BloomNode.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

interface ManifestAsset {
  id: string;
  title: string;
  file: string;
  size_m: [number, number, number];
  bytes: number;
}

const hud = document.getElementById("hud")!;
const status = document.getElementById("status")!;
const params = new URLSearchParams(location.search);

/** Equirect gradient sky, used as background and as the reflection environment. */
function skyTexture(): THREE.DataTexture {
  const w = 16, h = 256;
  const data = new Float32Array(w * h * 4);
  const ground = new THREE.Color(0.10, 0.13, 0.07);
  const horizon = new THREE.Color(0.62, 0.78, 0.96);
  const zenith = new THREE.Color(0.10, 0.28, 0.80);
  const c = new THREE.Color();
  for (let y = 0; y < h; y++) {
    const up = (y / (h - 1)) * 2 - 1;
    if (up < 0) c.lerpColors(horizon, ground, Math.min(1, -up * 6));
    else c.lerpColors(horizon, zenith, Math.min(1, up * 1.4) ** 0.6);
    for (let x = 0; x < w; x++) data.set([c.r, c.g, c.b, 1], (y * w + x) * 4);
  }
  const tex = new THREE.DataTexture(data, w, h, THREE.RGBAFormat, THREE.FloatType);
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.colorSpace = THREE.LinearSRGBColorSpace;
  tex.magFilter = tex.minFilter = THREE.LinearFilter;
  tex.needsUpdate = true;
  return tex;
}

/** One exported .glb holds <id>_LOD0..n as sibling nodes; wrap them in a THREE.LOD. */
function buildLod(root: THREE.Object3D, sizeM: number): THREE.LOD {
  const lod = new THREE.LOD();
  const levels: [number, THREE.Object3D][] = [];
  root.traverse((o) => {
    const m = /_LOD(\d+)$/.exec(o.name);
    if (m) levels.push([Number(m[1]), o]);
  });
  levels.sort((a, b) => a[0] - b[0]);
  for (const [level, obj] of levels) {
    obj.traverse((o) => {
      if (o instanceof THREE.Mesh) o.castShadow = o.receiveShadow = true;
    });
    // Switch when the object is roughly 1/3 and 1/9 of the screen height.
    lod.addLevel(obj, level === 0 ? 0 : sizeM * 3 ** (level + 1));
  }
  return lod;
}

async function main() {
  const renderer = new THREE.WebGPURenderer({ antialias: true, forceWebGL: params.has("webgl") });
  await renderer.init();
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  renderer.toneMapping = THREE.AgXToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const sky = skyTexture();
  scene.background = sky;
  scene.environment = sky;
  scene.fog = new THREE.Fog(0x9fc4ee, 60, 400);

  const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 1000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.495;

  const sun = new THREE.DirectionalLight(0xfff2dc, 3.2);
  sun.position.set(12, 18, 9);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: 1, far: 60 });
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.03;
  scene.add(sun);

  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(400, 64),
    new THREE.MeshStandardMaterial({ color: 0x4a6b2a, roughness: 0.95 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);

  const manifest: { assets: ManifestAsset[] } = await (await fetch("./assets/manifest.json")).json();
  if (manifest.assets.length === 0) {
    status.textContent = "Noch kein Objekt hat das Blender-Tor passiert.";
    return;
  }
  const entry = manifest.assets.find((a) => a.id === params.get("asset")) ?? manifest.assets[0];
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  const gltf = await loader.loadAsync(`./assets/${entry.file}`);
  const size = Math.max(...entry.size_m);
  const lod = buildLod(gltf.scene, size);
  scene.add(lod);

  controls.target.set(0, entry.size_m[2] * 0.45, 0);
  camera.position.set(size * 1.5, size * 0.75, size * 1.7);
  controls.minDistance = size * 0.4;
  controls.maxDistance = size * 40;

  const post = new THREE.RenderPipeline(renderer);
  const scenePass = pass(scene, camera);
  const color = scenePass.getTextureNode("output");
  post.outputNode = color.add(bloom(color, 0.3, 0.5, 0.85));

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });

  status.remove();
  const backend = (renderer.backend as { isWebGPUBackend?: boolean }).isWebGPUBackend ? "WebGPU" : "WebGL2";
  let frames = 0, last = performance.now(), fps = 0;
  renderer.setAnimationLoop(() => {
    controls.update();
    post.render();
    frames++;
    const now = performance.now();
    if (now - last >= 500) {
      fps = (frames * 1000) / (now - last);
      frames = 0;
      last = now;
      const info = renderer.info.render;
      hud.textContent =
        `${entry.title}\n${backend} · ${fps.toFixed(0)} Bilder/s\n` +
        `LOD ${lod.getCurrentLevel()} · ${info.triangles.toLocaleString("de")} Dreiecke · ${info.drawCalls} Zeichenaufrufe\n` +
        `${(entry.bytes / 1e6).toFixed(2)} MB`;
    }
  });
}

main().catch((err) => {
  status.textContent = `Fehler: ${err instanceof Error ? err.message : err}`;
  console.error(err);
});
