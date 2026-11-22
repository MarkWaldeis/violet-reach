import assert from "node:assert/strict";
import { test } from "node:test";
import { Quaternion, Vector3 } from "three";
import { placementRotation } from "../src/placement-rotation.ts";

test("optional rotations preserve yaw-only placements and terrain alignment", () => {
  assert.deepEqual(placementRotation({ yaw: 0 }), new Quaternion());
  const expected = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), 1.2);
  assert.ok(placementRotation({ yaw: 1.2 }).angleTo(expected) < 1e-7);
  const normal: [number, number, number] = [0, 1, 1];
  assert.ok(new Vector3(0, 1, 0).applyQuaternion(placementRotation({ yaw: 0, normal })).distanceTo(new Vector3(...normal).normalize()) < 1e-7);
});

test("pitch and roll compose locally before yaw, including a fallen column", () => {
  const p = { yaw: .35, pitch: .1, roll: -.15 };
  const up = new Vector3(0, 1, 0).applyAxisAngle(new Vector3(0, 0, 1), p.roll)
    .applyAxisAngle(new Vector3(1, 0, 0), p.pitch).applyAxisAngle(new Vector3(0, 1, 0), p.yaw);
  assert.ok(new Vector3(0, 1, 0).applyQuaternion(placementRotation(p)).distanceTo(up) < 1e-7);
  assert.ok(Math.abs(new Vector3(0, 1, 0).applyQuaternion(placementRotation({ yaw: 1.7, roll: Math.PI/2 })).y) < 1e-7);
});

test("nonfinite rotations fail instead of writing invalid instance matrices", () => {
  for (const key of ["yaw", "pitch", "roll"]) for (const value of [NaN, Infinity, -Infinity]) {
    assert.throws(() => placementRotation({ yaw: 0, [key]: value }), /Invalid placement rotation/);
  }
});
