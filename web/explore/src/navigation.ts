import { MathUtils, PerspectiveCamera } from "three/webgpu";
import type { TerrainManifest } from "./heightfield.ts";

export const EYE_HEIGHT = 1.8;
export const FLY_CLEARANCE = 2.6;
type Mode = "fly" | "walk";
type GroundHeight = (x: number, z: number) => number | undefined;

export class Navigation {
  mode: Mode = "fly";
  landing = false;
  readonly keys = new Set<string>();
  #manifest: TerrainManifest;
  #camera: PerspectiveCamera;
  #ground: GroundHeight;
  #yaw = 0;
  #pitch = 0;
  /** A pose set via setPose stays exactly in place (no ground clamp) until a movement key is held. */
  #pinned = false;

  constructor(camera: PerspectiveCamera, manifest: TerrainManifest, ground: GroundHeight) {
    this.#camera = camera;
    this.#manifest = manifest;
    this.#ground = ground;
    camera.rotation.order = "YXZ";
    this.reset();
  }

  reset() {
    const m = this.#manifest;
    const x = m.spawn?.x ?? m.originX + m.tileSize * m.tilesX / 2;
    const z = m.spawn?.z ?? m.originZ + m.tileSize * m.tilesZ / 2;
    this.#camera.position.set(this.#clampX(x), m.maxHeight + 150, this.#clampZ(z));
    this.#yaw = m.spawn?.yaw ?? 0;
    const availableGround = m.tileSize * Math.min(m.tilesX / 2, m.tilesZ / 2, 10);
    this.#pitch = Math.min(-0.13, 0.23 - Math.atan2(this.#spawnClearance(), availableGround));
    this.mode = "fly";
    this.landing = false;
    this.#pinned = false;
    this.#applyLook();
  }

  get yaw() { return this.#yaw; }
  get pitch() { return this.#pitch; }

  /** Fixed pose for QA (?cam / __vr.setCamera); y is absolute. Yaw 0 looks north (−Z), positive yaw turns west, positive pitch looks up. */
  setPose(x: number, y: number, z: number, yaw: number, pitch: number, mode: Mode = "fly") {
    this.#camera.position.set(this.#clampX(x), y, this.#clampZ(z));
    this.#yaw = yaw;
    this.#pitch = MathUtils.clamp(pitch, -1.42, 1.42);
    this.mode = mode;
    this.landing = false;
    this.#pinned = true;
    this.#applyLook();
  }

  liftToSpawnHeight(walk = false) {
    const p = this.#camera.position;
    const ground = this.#ground(p.x, p.z);
    if (ground === undefined) return false;
    p.y = ground + (walk ? EYE_HEIGHT : this.#spawnClearance());
    this.mode = walk ? "walk" : "fly";
    if (walk) { this.#pitch = -0.03; this.#applyLook(); }
    return true;
  }

  toggle() {
    const p = this.#camera.position;
    if (this.#ground(p.x, p.z) === undefined) return;
    this.mode = this.mode === "fly" ? "walk" : "fly";
    this.#pinned = false;
    this.landing = this.mode === "walk";
    if (this.landing && this.#pitch < -0.18) {
      this.#pitch = -0.18;
      this.#applyLook();
    }
  }

  look(dx: number, dy: number) {
    this.#yaw -= dx;
    this.#pitch = MathUtils.clamp(this.#pitch - dy, -1.42, 1.42);
    this.#applyLook();
  }

  update(dt: number) {
    const held = (code: string) => Number(this.keys.has(code));
    const p = this.#camera.position;
    this.look((held("ArrowRight") - held("ArrowLeft")) * dt * 1.4, (held("ArrowDown") - held("ArrowUp")) * dt * 1.2);

    if (this.#pinned) {
      if (!["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE"].some((code) => this.keys.has(code))) return;
      this.#pinned = false;
    }
    const forward = held("KeyW") - held("KeyS");
    const right = held("KeyD") - held("KeyA");
    const up = held("KeyE") - held("KeyQ");
    const sprint = held("ShiftLeft") || held("ShiftRight");
    const flying = this.mode === "fly";
    const directionLength = Math.max(1, Math.hypot(right, forward, flying ? up : 0));
    const speed = flying
      ? (sprint ? 193 : 68) * Math.min(1, this.#manifest.tileSize * 10 / 193)
      : (sprint ? 8 : 4.5);
    const dtSpeed = dt * speed / directionLength;
    const cp = flying ? Math.cos(this.#pitch) : 1;
    const x = this.#clampX(p.x + (right * Math.cos(this.#yaw) - forward * Math.sin(this.#yaw) * cp) * dtSpeed);
    const z = this.#clampZ(p.z + (-right * Math.sin(this.#yaw) - forward * Math.cos(this.#yaw) * cp) * dtSpeed);
    const nextGround = this.#ground(x, z);
    if (nextGround === undefined) return;

    if (flying) {
      const y = p.y + (up + forward * Math.sin(this.#pitch)) * dtSpeed;
      p.set(x, MathUtils.clamp(y, nextGround + FLY_CLEARANCE, this.#manifest.maxHeight + 950), z);
    } else if (this.landing) {
      const ground = this.#ground(p.x, p.z)! + EYE_HEIGHT;
      p.y = Math.max(ground, MathUtils.damp(p.y, ground, 5.2, dt));
      if (p.y - ground < 0.12) {
        p.y = ground;
        this.landing = false;
      }
    } else {
      p.set(x, nextGround + EYE_HEIGHT, z);
    }
  }

  #applyLook() {
    this.#camera.rotation.set(this.#pitch, this.#yaw, 0, "YXZ");
  }

  #spawnClearance() {
    return MathUtils.clamp(this.#manifest.tileSize * 3, FLY_CLEARANCE, 160);
  }

  #clampX(x: number) {
    const { originX, tileSize, tilesX } = this.#manifest;
    return MathUtils.clamp(x, originX + 0.1, originX + tileSize * tilesX - 0.1);
  }

  #clampZ(z: number) {
    const { originZ, tileSize, tilesZ } = this.#manifest;
    return MathUtils.clamp(z, originZ + 0.1, originZ + tileSize * tilesZ - 0.1);
  }
}
