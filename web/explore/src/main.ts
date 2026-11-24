import "./style.css";
import { PCFShadowMap, PerspectiveCamera, Scene, SRGBColorSpace, WebGPUCoordinateSystem, WebGPURenderer } from "three/webgpu";
import { setupAtmosphere } from "./atmosphere.ts";
import { waitForCloudAtlas } from "./sky-bodies.ts";
import { createPostProcessing, resolveToneMapping } from "./post-processing.ts";
import { terrainMaterial, terrainReflectionMaterial, waitForGroundTextures } from "./ground-material.ts";
import { Navigation } from "./navigation.ts";
import { TerrainStream } from "./terrain-stream.ts";
import { readJSON, type Slice } from "./slice.ts";
import { sliceAssets } from "./slice-content.ts";
import { selectWater, type Hydrology } from "./hydrology.ts";
import { surfaceData } from "./surface-data.ts";
import { waitForWaterTextures, waterSurface } from "./water.ts";
import { warmScene } from "./scene-warmup.ts";
import { parseQAParams } from "./qa-params.ts";
import { FLY_CLEARANCE } from "./navigation.ts";
import { adapterInfo, FrameHistory, FrameStability, STABLE_FRAMES, trackTextures, type FrameRecord, type VRProbe } from "./qa-probe.ts";
import { freezeWorldTime, worldTimeFrozen } from "./world-time.ts";
import { GrassMacroSampler } from "./grass-macro.ts";
import { GrassSystem } from "./grass-system.ts";

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
  const qa = parseQAParams(params);
  const { quality } = qa;
  if (!qa.hud) document.documentElement.dataset.hud = "off";
  if (qa.freeze) freezeWorldTime();
  const renderer = new WebGPURenderer({
    antialias: true,
    forceWebGL: params.has("webgl"),
  });
  const textures = trackTextures(renderer.info);
  await renderer.init();
  const backend = renderer.coordinateSystem === WebGPUCoordinateSystem ? "WebGPU" : "WebGL2";
  const adapter = backend === "WebGPU" ? await adapterInfo(renderer.backend).catch(() => null) : null;
  const tone = resolveToneMapping(params);
  renderer.setPixelRatio(Math.min(devicePixelRatio, quality.pixelRatio));
  renderer.toneMapping = tone.toneMapping;
  renderer.toneMappingExposure = tone.exposure;
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.shadowMap.enabled = quality.shadows;
  renderer.shadowMap.type = PCFShadowMap;
  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  canvas.setAttribute("aria-label", "3D-Gelände, steuerbar per Tastatur und Maus");
  stage.appendChild(canvas);
  rendererLabel.textContent = backend;

  const scene = new Scene();
  const atmosphere = setupAtmosphere(scene, quality);
  const camera = new PerspectiveCamera(qa.fov, 1, 0.25, 10000);
  let slice: Slice | undefined;
  if (!params.has("demo") && !params.has("terrain")) {
    const response = await fetch(new URL("./slice.json", location.href));
    if (response.ok) slice = await response.json() as Slice;
    else if (response.status !== 404) throw new Error(`slice.json: HTTP ${response.status}`);
  }
  const manifest = params.get("terrain") ?? (slice ? "./terrain/manifest.json" : "./demo-terrain/manifest.json");
  terrainLabel.textContent = slice ? "Spiegelsee · Phase-2-Ausschnitt" : params.has("terrain") ? "Höhenkartenvorschau" : "Testlandschaft";
  document.querySelector("#phase")!.textContent = slice ? "PHASE 2 · SPIEGELSEE-AUSSCHNITT" : params.has("terrain") ? "GELÄNDEVORSCHAU" : "DEMO · TESTLANDSCHAFT";
  status.textContent = "Boden- und Wassertexturen werden geladen …";
  await Promise.all([waitForGroundTextures(), waitForWaterTextures()]);
  const groundMaterial = terrainMaterial();
  const reflTerrainMaterial = terrainReflectionMaterial();
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
    scene.add(waterSurface(region, surface, (active) => terrain.setReflectionMaterial(active ? reflTerrainMaterial : null)));
  }
  const assets = slice ? await sliceAssets(slice, terrain, params, quality.assetDistanceScale, renderer) : undefined;
  if (assets) scene.add(assets.group);
  let grass: GrassSystem | undefined;
  if (slice && !params.has("nograss")) {
    status.textContent = "Gras-Makrokarten werden geladen …";
    const sampler = await GrassMacroSampler.load(new URL("./ground/", location.href).href);
    const grassQuality: Record<string, { viewDistance: number; density: number }> = {
      low: { viewDistance: 44, density: 2.6 },
      medium: { viewDistance: 68, density: 4.0 },
      high: { viewDistance: 96, density: 5.5 },
      ultra: { viewDistance: 128, density: 6.5 },
    };
    const gq = grassQuality[quality.name] ?? grassQuality.high;
    grass = new GrassSystem(sampler, (x, z) => terrain.fullHeightAt(x, z) ?? terrain.heightAt(x, z), gq);
    scene.add(grass.group);
  }
  const nav = new Navigation(camera, terrain.manifest, (x, z) => terrain.heightAt(x, z));
  const { position } = camera;
  let ready = false;
  let failed = false;
  let pose = qa.cam ? { ...qa.cam, agl: qa.agl } : undefined;
  const groundAt = (x: number, z: number) => terrain.fullHeightAt(x, z) ?? terrain.heightAt(x, z);
  // ?cam / __vr.setCamera: apply once the ground below the camera is known; no spawn lift.
  function applyPose() {
    if (!pose) return nav.liftToSpawnHeight(params.has("walk"));
    const ground = groundAt(pose.x, pose.z);
    if (ground === undefined) {
      camera.position.set(pose.x, camera.position.y, pose.z); // stream the tiles under the requested pose first
      return false;
    }
    const y = pose.agl ? ground + pose.y : pose.y;
    nav.setPose(pose.x, y, pose.z, pose.yaw, pose.pitch, y - ground <= FLY_CLEARANCE ? "walk" : "fly");
    return true;
  }

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
    pose = undefined;
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

  status.textContent = "Materialien werden vorbereitet …";
  terrain.update(position.x, position.z, performance.now());
  const post = createPostProcessing(renderer, scene, camera, quality, params);
  await waitForCloudAtlas();
  const warmPos = camera.position.clone();
  const warmQuat = camera.quaternion.clone();
  camera.position.set(500, 260, 1500);
  camera.lookAt(900, 180, 1900);
  camera.updateMatrixWorld(true);
  atmosphere.update(camera);
  const advanceFrame = () => (renderer as unknown as { _nodes?: { nodeFrame?: { update?: () => void } } })._nodes?.nodeFrame?.update?.();
  await warmScene(renderer, scene, camera, () => {
    post.render();
    advanceFrame();
    post.render();
  });
  camera.position.copy(warmPos);
  camera.quaternion.copy(warmQuat);
  camera.updateMatrixWorld(true);
  atmosphere.update(camera);
  let last = performance.now();
  let hudAt = last;
  let frames = 0;
  const history = new FrameHistory();
  const stability = new FrameStability();
  let probeReady = false;
  let frameId = 0;
  let driver: ((now: number, last: FrameRecord | undefined) => void) | undefined;
  let waiting: ((record: FrameRecord) => void)[] = [];
  const terrainStatus = () => {
    const { lods, total, failed: missing, pending } = terrain.stats;
    const loaded = lods.reduce((a, b) => a + b, 0);
    return { lods, total, loaded, failed: missing, pending, complete: !missing && !pending && loaded === total };
  };
  const probe: VRProbe = {
    get ready() { return probeReady; },
    stats() {
      const p = camera.position, info = renderer.info, records = history.records;
      const ground = groundAt(p.x, p.z);
      return {
        backend, adapter, quality: { ...quality }, ready: probeReady, stableFrames: stability.frames, frame: frameId,
        fps: history.fps(), frameTimes: records.map((r) => r.frameMs), cpuTimes: records.map((r) => r.cpuMs),
        triangles: info.render.triangles, drawCalls: info.render.drawCalls,
        geometries: info.memory.geometries, textures: info.memory.textures,
        textureBytes: textures.bytes(), textureBytesThree: info.memory.texturesSize, textureSizes: textures.summary(),
        camera: { x: p.x, y: p.y, z: p.z, yaw: nav.yaw, pitch: nav.pitch, agl: ground === undefined ? null : p.y - ground, fov: camera.fov, mode: nav.mode },
        terrain: terrainStatus(), assets: assets ? { ...assets.stats } : null, frozen: worldTimeFrozen(),
      };
    },
    setCamera(x, y, z, yaw, pitch, options = {}) {
      if (![x, y, z, yaw, pitch].every(Number.isFinite)) throw new Error("setCamera: endliche Zahlen erwartet");
      pose = { x, y, z, yaw, pitch, agl: !!options.agl };
      ready = applyPose();
      stability.reset();
      probeReady = false;
      if (ready) {
        status.hidden = true;
        reset.disabled = toggle.disabled = false;
      }
      const p = camera.position;
      return { x: p.x, y: p.y, z: p.z, yaw: nav.yaw, pitch: nav.pitch };
    },
    frame: () => new Promise((resolve) => { waiting.push(resolve); }),
    drive(callback) { driver = callback ?? undefined; },
  };
  window.__vr = probe;
  renderer.setAnimationLoop((now) => {
    const cpuStart = performance.now();
    const frameMs = now - last;
    driver?.(now, history.last);
    const dt = Math.max(0, Math.min(0.05, (now - last) / 1000));
    last = now;
    terrain.update(position.x, position.z, now);
    grass?.update(position.x, position.z);
    if (!ready && !failed) {
      ready = applyPose();
      if (ready) {
        status.hidden = true;
        reset.disabled = toggle.disabled = false;
      } else if (terrain.failedAt(position.x, position.z)) {
        failed = true;
        status.textContent = "Startkachel fehlt. Prüfe die Höhenkartendateien und lade neu.";
      }
    }
    if (ready) nav.update(dt);
    atmosphere.update(camera);
    const fullHeight = terrain.fullHeightAt(position.x, position.z);
    assets?.update(camera, stage.clientHeight, now, fullHeight === undefined ? 0 : Math.max(0, position.y - fullHeight));
    post.render();
    frames++;
    frameId++;
    const p = camera.position, t = terrainStatus(), a = assets?.stats;
    const signature = [ready, t.complete, t.lods, t.pending, a?.lods, a?.visibleChunks, p.x, p.y, p.z, nav.yaw, nav.pitch].join("|");
    probeReady = ready && t.complete && stability.observe(signature) >= STABLE_FRAMES;
    const record = { now, frameMs, cpuMs: performance.now() - cpuStart, triangles: renderer.info.render.triangles, drawCalls: renderer.info.render.drawCalls };
    history.push(record);
    if (waiting.length) {
      const resolved = waiting;
      waiting = [];
      for (const resolve of resolved) resolve(record);
    }

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
