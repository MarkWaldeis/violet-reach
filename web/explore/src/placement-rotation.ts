import { Euler, Quaternion, Vector3 } from "three";
import type { InstancePlacement } from "./placements.ts";

export function placementRotation({ yaw, pitch = 0, roll = 0, normal }: Pick<InstancePlacement, "yaw" | "pitch" | "roll" | "normal">) {
  if (![yaw, pitch, roll].every(Number.isFinite)) throw new Error("Invalid placement rotation");
  const rotation = new Quaternion().setFromEuler(new Euler(pitch, yaw, roll, "YXZ"));
  if (normal) rotation.premultiply(new Quaternion().setFromUnitVectors(new Vector3(0, 1, 0), new Vector3(...normal).normalize()));
  return rotation;
}
