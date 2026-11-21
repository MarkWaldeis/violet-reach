import {
  DirectionalLight, DoubleSide, FogExp2, HemisphereLight, MeshLambertNodeMaterial,
  Scene, Vector3,
} from "three/webgpu";
import { SkyMesh } from "three/addons/objects/SkyMesh.js";
import { mx_noise_float, positionWorld } from "three/tsl";

export function setupAtmosphere(scene: Scene) {
  const sky = new SkyMesh();
  const light = new Vector3(-0.56, 0.45, -0.62).normalize();
  sky.scale.setScalar(14000);
  sky.frustumCulled = false;
  sky.sunPosition.value.copy(light).multiplyScalar(450000);
  sky.turbidity.value = 2.6;
  sky.rayleigh.value = 2.2;
  sky.mieCoefficient.value = 0.004;
  sky.cloudCoverage.value = 0.36;
  sky.cloudDensity.value = 0.38;
  sky.cloudElevation.value = 0.32;
  sky.cloudScale.value = 0.00026;
  sky.cloudSpeed.value = 0.00001;
  scene.add(sky);
  scene.fog = new FogExp2(0xc5d1dc, 0.00065);

  const sun = new DirectionalLight(0xffedd4, 2.3);
  sun.position.copy(light).multiplyScalar(1000);
  scene.add(sun, new HemisphereLight(0xc5dcff, 0x594835, 1.6));
  return sky;
}

export function terrainMaterial() {
  const material = new MeshLambertNodeMaterial({ vertexColors: true, side: DoubleSide });
  const planar = positionWorld.xz;
  const grain = mx_noise_float(planar.mul(1.3)).mul(0.19);
  const mottling = mx_noise_float(planar.mul(0.09)).mul(0.32);
  material.colorNode = grain.add(mottling).add(0.95);
  return material;
}
