import { qualityLevel, type QualityLevel } from "./quality.ts";

/** Camera pose; yaw/pitch in radians with the Navigation convention (see README). */
export interface CameraPose { x: number; y: number; z: number; yaw: number; pitch: number }
export interface QAParams {
  /** Fixed start pose from ?cam=x,y,z,yaw,pitch. */
  cam?: CameraPose;
  /** ?agl=1: cam.y is metres above full-resolution ground instead of absolute. */
  agl: boolean;
  /** Vertical field of view in degrees. */
  fov: number;
  hud: boolean;
  quality: Readonly<QualityLevel>;
  freeze: boolean;
}

export const DEFAULT_FOV = 57;
export const PITCH_LIMIT = 1.42;
const flag = (value: string | null) => value !== null && !["0", "false", "no", "off"].includes(value.trim().toLowerCase());

export function parseCamera(value: string): CameraPose {
  const parts = value.split(",").map((s) => s.trim());
  const numbers = parts.map(Number);
  if (parts.length !== 5 || parts.some((s) => s === "") || !numbers.every(Number.isFinite)) {
    throw new Error("cam: x,y,z,yaw,pitch als fünf Zahlen erwartet");
  }
  const [x, y, z, yaw, pitch] = numbers;
  if (Math.abs(pitch) > PITCH_LIMIT) throw new Error(`cam: pitch muss zwischen −${PITCH_LIMIT} und ${PITCH_LIMIT} rad liegen`);
  return { x, y, z, yaw, pitch };
}

export function parseQAParams(params: URLSearchParams): QAParams {
  const cam = params.has("cam") ? parseCamera(params.get("cam")!) : undefined;
  const fov = params.has("fov") ? Number(params.get("fov")) : DEFAULT_FOV;
  if (!Number.isFinite(fov) || fov < 10 || fov > 120) throw new Error("fov: 10–120 Grad erwartet");
  return {
    cam,
    agl: flag(params.get("agl")),
    fov,
    hud: params.get("hud") === null || flag(params.get("hud")),
    quality: qualityLevel(params.get("quality")),
    freeze: flag(params.get("freeze")),
  };
}

/** Unit forward vector of the camera for a yaw/pitch pair (yaw 0 = north/−Z, positive yaw turns west). */
export function viewDirection(yaw: number, pitch: number): [number, number, number] {
  return [-Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch)];
}
