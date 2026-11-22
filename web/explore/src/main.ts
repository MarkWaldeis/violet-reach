import "./style.css";
import { AgXToneMapping, PCFShadowMap, PerspectiveCamera, Scene, SRGBColorSpace, WebGPUCoordinateSystem, WebGPURenderer } from "three/webgpu";
import { setupAtmosphere } from "./atmosphere.ts";
import { terrainMaterial } from "./ground-material.ts";
import { Navigation } from "./navigation.ts";
import { TerrainStream } from "./terrain-stream.ts";
import { readJSON, type Slice } from "./slice.ts";
import { sliceAssets } from "./slice-content.ts";
import { selectWater, type Hydrology } from "./hydrology.ts";
import { surfaceData } from "./surface-data.ts";
import { waterSurface } from "./water.ts";

const stage = document.querySelector<HTMLElement>("#stage")!;
const status = document.querySelector<HTMLElement>("#status")!;
const mode = document.querySelector<HTMLElement>("#mode")!;
const rendererLabel = document.querySelector<HTMLElement>("#backend")!;
const coordinates = document.querySelector<HTMLElement>("#coordinates")!;
const heading = document.querySelector<HTMLElement>("#heading")!;
const flightControls = document.querySelector<HTMLElement>("#flight-controls")!;
const terrainLabel = document.querySelector<HTMLElement>("#terrain-label")!;
const telemetry = document.querySelector<HTMLElement>("#telemetry")!;
const streamStatus = document.querySelector<HTMLElement>("#stream-status")!;
const lockLabel = document.querySelector<HTMLElement>("#look-label")!;
const toggle = document.querySelector<HTMLButtonElement>("#toggle")!;
const reset = document.querySelector<HTMLButtonElement>("#reset")!;
const params = new URLSearchParams(location.search);
const controls = new Set([
  "KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE", "KeyF", "KeyR",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "ShiftLeft", "ShiftRight",
]);

async function main() {
  const renderer = new WebGPURenderer({
    antialias: true,
    forceWebGL: params.has("webgl"),
  });
  await renderer.init();
  const backend = renderer.coordinateSystem === WebGPUCoordinateSystem ? "WebGPU" : "WebGL2";
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.toneMapping = AgXToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = PCFShadowMap;
  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  canvas.setAttribute("aria-label", "3D-Gelände, steuerbar per Tastatur und Maus");
  stage.appendChild(canvas);
  rendererLabel.textContent = backend;

  const scene = new Scene();
  const atmosphere = setupAtmosphere(scene);
  const camera = new PerspectiveCamera(57, 1, 0.25, 10000);
  let slice: Slice | undefined;
  if (!params.has("demo") && !params.has("terrain")) {
    const response = await fetch(new URL("./slice.json", location.href));
    if (response.ok) slice = await response.json() as Slice;
    else if (response.status !== 404) throw new Error(`slice.json: HTTP ${response.status}`);
  }
  const manifest = params.get("terrain") ?? (slice ? "./terrain/manifest.json" : "./demo-terrain/manifest.json");
  terrainLabel.textContent = slice ? "Spiegelsee · Phase-2-Ausschnitt" : params.has("terrain") ? "Höhenkartenvorschau" : "Testlandschaft";
  document.querySelector("#phase")!.textContent = slice ? "PHASE 2 · SPIEGELSEE-AUSSCHNITT" : params.has("terrain") ? "GELÄNDEVORSCHAU" : "DEMO · TESTLANDSCHAFT";
  const groundMaterial = terrainMaterial();
  const terrain = await TerrainStream.open(new URL(manifest, location.href), groundMaterial);
  scene.add(terrain.group);
  if (slice) {
    status.textContent = "Ausschnitt und freigegebene Objekte werden geladen …";
    terrain.manifest.spawn = slice.spawn[params.has("walk") ? "walk" : "fly"];
    await terrain.preloadSlice(slice.bounds);
    const region = selectWater(await readJSON<Hydrology>("./hydrology.json"), slice.bounds);
    status.textContent = "Gewässer und Ufermaterialien werden geladen …";
    const surface = await surfaceData(region, slice, terrain);
    groundMaterial.copy(terrainMaterial(surface));
    scene.add(waterSurface(region, surface));
  }
  const assets = slice ? await sliceAssets(slice, terrain, params) : undefined;
  if (assets) scene.add(assets.group);
  const nav = new Navigation(camera, terrain.manifest, (x, z) => terrain.heightAt(x, z));
  const { position } = camera;
  let ready = false;
  let failed = false;

  function resize() {
    const { clientWidth, clientHeight } = stage;
    renderer.setSize(clientWidth, Math.max(1, clientHeight));
    camera.aspect = clientWidth / Math.max(1, clientHeight);
    camera.updateProjectionMatrix();
    atmosphere.resize();
  }
  new ResizeObserver(resize).observe(stage);
  resize();

  function resetView() {
    nav.reset();
    ready = false;
    failed = false;
    status.hidden = false;
    status.textContent = "Startkachel wird geladen …";
    toggle.disabled = true;
    canvas.focus();
  }
  toggle.addEventListener("click", () => {
    if (ready) nav.toggle();
    canvas.focus();
  });
  reset.addEventListener("click", resetView);
  addEventListener("keydown", (e) => {
    if (!controls.has(e.code) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target instanceof HTMLButtonElement && e.code !== "KeyF" && e.code !== "KeyR") return;
    e.preventDefault();
    nav.keys.add(e.code);
    if (!e.repeat && e.code === "KeyF" && ready) nav.toggle();
    if (!e.repeat && e.code === "KeyR") resetView();
  });
  addEventListener("keyup", (e) => nav.keys.delete(e.code));
  addEventListener("blur", () => nav.keys.clear());
  document.addEventListener("visibilitychange", () => nav.keys.clear());

  let dragging = false, moved = false;
  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || document.pointerLockElement === canvas) return;
    canvas.focus();
    dragging = true;
    moved = false;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("lostpointercapture", () => { dragging = false; });
  canvas.addEventListener("click", () => {
    if (moved || document.pointerLockElement === canvas) return;
    try {
      void canvas.requestPointerLock?.()?.catch(() => {});
    } catch {
      // Drag and arrow keys still work in browsers or embeds that disallow pointer lock.
    }
  });
  document.addEventListener("pointerlockchange", () => {
    const locked = document.pointerLockElement === canvas;
    lockLabel.textContent = locked ? "Esc löst Maus" : "Klicken oder ziehen";
    if (!locked) nav.keys.clear();
  });
  addEventListener("mousemove", (e) => {
    if (document.pointerLockElement === canvas || dragging) {
      if (e.movementX || e.movementY) moved = true;
      if (ready) nav.look(e.movementX * 0.0025, e.movementY * 0.0025);
    }
  });
  document.addEventListener("pointerlockerror", () => { lockLabel.textContent = "Ziehen oder Pfeiltasten"; });

  let last = performance.now();
  let hudAt = last;
  let frames = 0;
  renderer.setAnimationLoop((now) => {
    const dt = Math.max(0, Math.min(0.05, (now - last) / 1000));
    last = now;
    terrain.update(position.x, position.z, now);
    if (!ready && !failed) {
      ready = nav.liftToSpawnHeight(params.has("walk"));
      if (ready) {
        status.hidden = true;
        reset.disabled = toggle.disabled = false;
      } else if (terrain.failedAt(position.x, position.z)) {
        failed = true;
        status.textContent = "Startkachel fehlt. Prüfe die Höhenkartendateien und lade neu.";
      }
    }
    if (ready) nav.update(dt);
    const fullHeight = terrain.fullHeightAt(position.x, position.z);
    assets?.update(camera, stage.clientHeight, now, fullHeight === undefined ? 0 : Math.max(0, position.y - fullHeight));
    renderer.render(scene, camera);
    frames++;

    if (now - hudAt < 250) return;
    const ground = terrain.heightAt(position.x, position.z);
    const fmt = (n: number) => Math.round(n).toLocaleString("de-DE");
    const azimuth = ((-camera.rotation.y * 180 / Math.PI % 360) + 360) % 360;
    const direction = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"][Math.round(azimuth / 45) % 8];
    heading.textContent = `${direction} · ${Math.round(azimuth) % 360}°`;
    coordinates.textContent = `X ${fmt(position.x)} · Z ${fmt(position.z)} · ${ground === undefined ? "—" : fmt(position.y - ground)} m über Grund`;
    mode.textContent = nav.landing ? "Landung" : nav.mode === "fly" ? "Flug" : "Zu Fuß";
    toggle.textContent = nav.mode === "fly" ? "Landen" : "Abheben";
    flightControls.hidden = nav.mode !== "fly";

    const { lods, total, failed: missing, pending } = terrain.stats;
    const loaded = lods.reduce((a, b) => a + b, 0);
    const fps = frames * 1000 / (now - hudAt);
    const info = renderer.info.render;
    telemetry.textContent = `${fmt(fps)} FPS · ${fmt(info.triangles)} Dreiecke · ${fmt(info.drawCalls)} Draws\nLOD 0–3: ${lods.join(" / ")} · ${loaded}/${total} Kacheln`;
    if (assets) {
      const stats = assets.stats;
      telemetry.textContent += `\n${stats.assets} Assets · Instanz-LOD: ${stats.lods.join(" / ")}\n${stats.lods.reduce((a, b) => a + b, 0)}/${fmt(stats.total)} Instanzen · ${stats.visibleChunks}/${stats.chunks} Chunks`;
    }
    streamStatus.textContent = missing ? `${missing} Kacheln nicht verfügbar` : loaded < total || pending ? "Kacheln werden geladen" : "Gelände geladen";
    streamStatus.dataset.state = missing ? "error" : loaded < total || pending ? "loading" : "ready";
    hudAt = now;
    frames = 0;
  });
}

main().catch((error) => {
  status.hidden = false;
  status.textContent = `Vorschau konnte nicht starten: ${error instanceof Error ? error.message : error}`;
  console.error(error);
});
