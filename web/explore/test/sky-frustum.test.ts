import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import test from "node:test";

const hooks = registerHooks({
  load(url, context, nextLoad) {
    if (!url.endsWith(".json?raw")) return nextLoad(url, context);
    const raw = readFileSync(new URL(url.replace(/\?raw$/, "")), "utf8");
    return { format: "module", shortCircuit: true, source: `export default ${JSON.stringify(raw)};` };
  },
});
const {
  giantPlanetDirection,
  giantPlanetRadius,
  shatteredMoonADirection,
  shatteredMoonARadius,
  shatteredMoonBDirection,
  shatteredMoonBRadius,
  shatteredMoonCDirection,
  shatteredMoonCRadius,
} = await import("../src/sky-bodies.ts");
hooks.deregister();

const DEG = 180 / Math.PI;
/** QA captures and the documented GPU runs use 1920 × 1080. */
const CAPTURE_ASPECT = 16 / 9;
const CAPTURE_HEIGHT_PX = 1080;

type Vec3 = readonly [number, number, number];

interface Bookmark {
  id: string;
  yaw: number;
  pitch: number;
  fov: number;
}

interface SkyBody {
  name: string;
  direction: Vec3;
  /** Tangent-plane shader radius; asin(radius) is the true angular radius. */
  shaderRadius: number;
}

interface SightAngles {
  horizontal: number;
  vertical: number;
  centreAngle: number;
  angularRadius: number;
  halfHorizontal: number;
  halfVertical: number;
  cornerAngle: number;
  intersects: boolean;
  fullyInside: boolean;
  definitelyOutside: boolean;
}

const tuple = (v: { x: number; y: number; z: number }): Vec3 => [v.x, v.y, v.z];
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const length = (v: Vec3) => Math.hypot(v[0], v[1], v[2]);
const normalize = (v: Vec3): Vec3 => {
  const inv = 1 / length(v);
  return [v[0] * inv, v[1] * inv, v[2] * inv];
};
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const wrapAngle = (v: number) => Math.atan2(Math.sin(v), Math.cos(v));

/** Navigation/bookmark convention: yaw 0 looks north (−Z), positive yaw west, positive pitch up. */
function cameraBasis(yaw: number, pitch: number) {
  const cp = Math.cos(pitch);
  const forward: Vec3 = [-Math.sin(yaw) * cp, Math.sin(pitch), -Math.cos(yaw) * cp];
  const right: Vec3 = [Math.cos(yaw), 0, -Math.sin(yaw)];
  const up = cross(right, forward);
  return { forward, right, up };
}

/** Inverse of the horizontal part of cameraBasis: which camera yaw centres this world direction? */
const directionYaw = (direction: Vec3) => {
  const d = normalize(direction);
  return Math.atan2(-d[0], -d[2]);
};

/**
 * Pure pinhole/frustum arithmetic for infinitely distant background bodies.
 * Bookmark x/z/agl are deliberately irrelevant here because the shader directions do not parallax.
 */
function sightAngles(body: SkyBody, bookmark: Bookmark): SightAngles {
  const direction = normalize(body.direction);
  const { forward, right, up } = cameraBasis(bookmark.yaw, bookmark.pitch);
  const depth = dot(direction, forward);
  const horizontal = Math.atan2(dot(direction, right), depth);
  const vertical = Math.atan2(dot(direction, up), depth);
  const centreAngle = Math.acos(clamp(depth, -1, 1));
  const angularRadius = Math.asin(body.shaderRadius);
  const halfVertical = bookmark.fov * Math.PI / 360;
  const halfHorizontal = Math.atan(Math.tan(halfVertical) * CAPTURE_ASPECT);
  const cornerAngle = Math.atan(Math.hypot(Math.tan(halfHorizontal), Math.tan(halfVertical)));

  return {
    horizontal,
    vertical,
    centreAngle,
    angularRadius,
    halfHorizontal,
    halfVertical,
    cornerAngle,
    // Axis-separated rectangle test is accurate enough for these small/medium discs away from corners.
    intersects: depth > 0
      && Math.abs(horizontal) - angularRadius <= halfHorizontal
      && Math.abs(vertical) - angularRadius <= halfVertical,
    fullyInside: depth > 0
      && Math.abs(horizontal) + angularRadius < halfHorizontal
      && Math.abs(vertical) + angularRadius < halfVertical,
    // Conservative exact rejection: even the nearest point of the disc cannot reach the farthest frustum corner.
    definitelyOutside: centreAngle - angularRadius > cornerAngle,
  };
}

const bookmarkDoc = JSON.parse(readFileSync(new URL("../../../world/bookmarks.json", import.meta.url), "utf8")) as { bookmarks: Bookmark[] };
function bookmark(id: string): Bookmark {
  const result = bookmarkDoc.bookmarks.find((entry) => entry.id === id);
  assert.ok(result, `bookmark ${id} missing`);
  return result;
}

const bodies = {
  giant: { name: "giant planet", direction: tuple(giantPlanetDirection), shaderRadius: giantPlanetRadius },
  moonA: { name: "shattered moon A", direction: tuple(shatteredMoonADirection), shaderRadius: shatteredMoonARadius },
  moonB: { name: "shattered moon B", direction: tuple(shatteredMoonBDirection), shaderRadius: shatteredMoonBRadius },
  moonC: { name: "G3 moon fragment", direction: tuple(shatteredMoonCDirection), shaderRadius: shatteredMoonCRadius },
} satisfies Record<string, SkyBody>;

test("sky directions use the bookmark yaw convention; the G3 fragment is low, centred and small", () => {
  for (const body of Object.values(bodies)) {
    assert.ok(Math.abs(length(body.direction) - 1) < 1e-9, `${body.name} direction must be normalized`);
  }

  const diameterDeg = (radius: number) => 2 * Math.asin(radius) * DEG;
  const giantDiameter = diameterDeg(giantPlanetRadius);
  const moonADiameter = diameterDeg(shatteredMoonARadius);
  const moonBDiameter = diameterDeg(shatteredMoonBRadius);
  const moonCDiameter = diameterDeg(shatteredMoonCRadius);
  assert.ok(giantDiameter > moonADiameter, "gas giant remains the dominant body");
  assert.ok(moonADiameter > moonBDiameter, "moon A remains larger than moon B");
  assert.ok(moonBDiameter > moonCDiameter, "G3 fragment must stay smaller than the existing secondary moon");

  const g3 = bookmark("G3");
  const yawOffsetDeg = wrapAngle(directionYaw(bodies.moonC.direction) - g3.yaw) * DEG;
  const elevationDeg = Math.asin(normalize(bodies.moonC.direction)[1]) * DEG;
  const angularRadiusDeg = Math.asin(shatteredMoonCRadius) * DEG;
  const lowerLimbDeg = elevationDeg - angularRadiusDeg;
  const upperLimbDeg = elevationDeg + angularRadiusDeg;

  assert.ok(Math.abs(yawOffsetDeg) < 1.0, `G3 fragment horizontal axis offset ${yawOffsetDeg.toFixed(3)}°`);
  assert.ok(elevationDeg > 8.6 && elevationDeg < 9.1, `G3 fragment elevation ${elevationDeg.toFixed(3)}°`);
  assert.ok(lowerLimbDeg > 7.4, `lower limb should clear the monument skyline (${lowerLimbDeg.toFixed(3)}°)`);
  assert.ok(upperLimbDeg < 10.3, `upper limb should stay below the densest NE cloud deck (${upperLimbDeg.toFixed(3)}°)`);
  assert.ok(moonCDiameter > 2.1 && moonCDiameter < 2.7, `G3 fragment diameter ${moonCDiameter.toFixed(3)}°`);

  const moonCWidthPx = moonCDiameter / g3.fov * CAPTURE_HEIGHT_PX;
  assert.ok(moonCWidthPx > 35 && moonCWidthPx < 55, `G3 fragment should be a small but readable ~${Math.round(moonCWidthPx)} px cue at 1080p`);
});

test("F1/F2/G3/H2 bookmark frusta verify the existing planet geometry and the new G3 anchor", () => {
  for (const id of ["F1", "F2", "H2"]) {
    const view = bookmark(id);
    assert.ok(sightAngles(bodies.giant, view).intersects, `gas giant should intersect ${id}`);
    assert.ok(sightAngles(bodies.moonA, view).intersects, `shattered moon A should intersect ${id}`);

    const moonBAngles = sightAngles(bodies.moonB, view);
    const moonCAngles = sightAngles(bodies.moonC, view);
    assert.equal(moonBAngles.intersects, false, `shattered moon B must not add clutter to ${id}`);
    assert.ok(moonBAngles.definitelyOutside, `shattered moon B is outside ${id} even after angular size/corner allowance`);
    assert.equal(moonCAngles.intersects, false, `G3 fragment must not enter ${id}`);
    assert.ok(moonCAngles.definitelyOutside, `G3 fragment is outside ${id} even after angular size/corner allowance`);
  }

  const g3 = bookmark("G3");
  const g3Moon = sightAngles(bodies.moonC, g3);
  assert.ok(g3Moon.fullyInside, "G3 fragment disc should be fully inside the 16:9 G3 frustum");
  assert.ok(Math.abs(g3Moon.horizontal * DEG) < 1.0, `G3 fragment horizontal angle ${((g3Moon.horizontal * DEG).toFixed(3))}°`);
  assert.ok(g3Moon.vertical * DEG > 8.6 && g3Moon.vertical * DEG < 9.1, `G3 fragment vertical angle ${(g3Moon.vertical * DEG).toFixed(3)}°`);

  assert.equal(sightAngles(bodies.giant, g3).intersects, false, "gas giant must not intersect G3");
  assert.equal(sightAngles(bodies.moonA, g3).intersects, false, "shattered moon A must not intersect G3");
  assert.equal(sightAngles(bodies.moonB, g3).intersects, false, "shattered moon B must not intersect G3");
});

test("the existing gas giant cannot geometrically double as the G3 sight-axis body", () => {
  const angles = sightAngles(bodies.giant, bookmark("G3"));
  const clearanceDeg = (angles.centreAngle - angles.angularRadius - angles.cornerAngle) * DEG;
  assert.ok(angles.definitelyOutside, "giant disc is conservatively outside every G3 frustum corner");
  assert.ok(clearanceDeg > 40, `large geometric clearance remains (${clearanceDeg.toFixed(1)}°)`);
});
