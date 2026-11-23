import {
  Color, DataTexture, DoubleSide, EquirectangularReflectionMapping, FloatType,
  InstancedBufferAttribute, InstancedMesh, LinearFilter, LinearSRGBColorSpace,
  Matrix4, MeshBasicNodeMaterial, Object3D, PlaneGeometry, RGBAFormat, Vector3, type Node,
} from "three/webgpu";
import {
  abs, attribute, color, cos, cross, dot, float, max, mix, mx_noise_float, normalize,
  sin, smoothstep, sqrt, texture, uniform, uv, vec2, vec3,
} from "three/tsl";
import { swatch } from "./palette.ts";

/** Prominent SE/SSE sky direction framed cleanly across F1, F2, H2, G1, G4, G6. */
export const giantPlanetDirection = new Vector3(0.55, 0.205, 0.808).normalize();
/** Monumental shattered companion moon visible in SE/S views beside the planet (H2, F1, F2, G1, G6). */
export const shatteredMoonADirection = new Vector3(0.26, 0.285, 0.922).normalize();
/** Secondary shattered moon visible in SSW views (F3, G1). */
export const shatteredMoonBDirection = new Vector3(-0.22, 0.24, 0.94).normalize();

interface CloudCellMeta {
  name: string;
  cell_uv: [number, number, number, number];
  aspect: number;
  baseline_v: number;
}
interface CloudsManifest {
  clouds: CloudCellMeta[];
}

const ATLAS_W = 2048;
const ATLAS_H = 1024;

function makeCloudTexture() {
  const tex = new DataTexture(new Uint8Array(ATLAS_W * ATLAS_H * 4), ATLAS_W, ATLAS_H, RGBAFormat);
  tex.colorSpace = LinearSRGBColorSpace;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.flipY = false;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

let cloudAtlasPromise: Promise<void> | null = null;
const cloudLightATex = makeCloudTexture();
const cloudLightBTex = makeCloudTexture();
const cloudAtlasReady = uniform(0);

async function decodeUnpremultipliedRGBA(blob: Blob, width: number, height: number): Promise<Uint8Array | null> {
  if (typeof createImageBitmap !== "function") return null;
  const bmp = await createImageBitmap(blob, {
    resizeWidth: width,
    resizeHeight: height,
    resizeQuality: "high",
    premultiplyAlpha: "none",
    colorSpaceConversion: "none",
  });
  try {
    // WebGL2 readPixels with UNPACK_PREMULTIPLY_ALPHA_WEBGL = 0 preserves RGB and A independently
    // (critical for clouds_lightB.webp where A carries ambient occlusion rather than opacity).
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const gl = canvas.getContext("webgl2");
    if (gl) {
      const tex = gl.createTexture();
      const fbo = gl.createFramebuffer();
      if (tex && fbo) {
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, 0);
        gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, bmp);
        gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
        const out = new Uint8Array(width * height * 4);
        gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, out);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.deleteFramebuffer(fbo);
        gl.deleteTexture(tex);
        return out;
      }
    }
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(bmp, 0, 0, width, height);
    return new Uint8Array(ctx.getImageData(0, 0, width, height).data.buffer.slice(0));
  } finally {
    bmp.close?.();
  }
}

/**
 * Loads /sky/clouds.json, /sky/clouds_lightA.webp, and /sky/clouds_lightB.webp
 * into pre-allocated 1024x512 DataTextures (4 MiB total VRAM).
 * Silently keeps procedural clouds when offline or in Node unit tests.
 */
export function ensureCloudAtlasLoaded(): Promise<void> {
  if (cloudAtlasPromise) return cloudAtlasPromise;
  if (typeof window === "undefined" || typeof document === "undefined" || typeof fetch !== "function") {
    cloudAtlasPromise = Promise.resolve();
    return cloudAtlasPromise;
  }
  cloudAtlasPromise = (async () => {
    try {
      const metaRes = await fetch(new URL("./sky/clouds.json", window.location.href));
      if (!metaRes.ok) return;
      const meta = (await metaRes.json()) as CloudsManifest;
      if (!Array.isArray(meta?.clouds) || meta.clouds.length === 0) return;
      const [blobA, blobB] = await Promise.all([
        fetch(new URL("./sky/clouds_lightA.webp", window.location.href)).then((r) => (r.ok ? r.blob() : null)),
        fetch(new URL("./sky/clouds_lightB.webp", window.location.href)).then((r) => (r.ok ? r.blob() : null)),
      ]);
      if (!blobA || !blobB) return;
      const [pixelsA, pixelsB] = await Promise.all([
        decodeUnpremultipliedRGBA(blobA, ATLAS_W, ATLAS_H),
        decodeUnpremultipliedRGBA(blobB, ATLAS_W, ATLAS_H),
      ]);
      if (!pixelsA || !pixelsB) return;
      (cloudLightATex.image.data as Uint8Array).set(pixelsA);
      cloudLightATex.needsUpdate = true;
      (cloudLightBTex.image.data as Uint8Array).set(pixelsB);
      cloudLightBTex.needsUpdate = true;
      cloudAtlasReady.value = 1;
    } catch {
      // Optional asset: keep procedural volumetric cloud layer on any error.
    }
  })();
  return cloudAtlasPromise;
}

export async function waitForCloudAtlas(timeoutMs = 3000): Promise<void> {
  const p = ensureCloudAtlasLoaded();
  if (typeof window === "undefined") return p;
  await Promise.race([p, new Promise<void>((resolve) => setTimeout(resolve, timeoutMs))]);
}

const CLOUD_CELL_META: { uv: [number, number, number, number]; aspect: number; baseQ: number }[] = [
  { uv: [0.0, 0.0, 0.25, 0.5], aspect: 1.65, baseQ: 0.2136 }, // 0: cumulus_a
  { uv: [0.25, 0.0, 0.25, 0.5], aspect: 1.06, baseQ: 0.0520 }, // 1: congestus (unused cone)
  { uv: [0.5, 0.0, 0.25, 0.5], aspect: 2.13, baseQ: 0.2780 }, // 2: humilis
  { uv: [0.75, 0.0, 0.25, 0.5], aspect: 2.12, baseQ: 0.2770 }, // 3: cumulus_twin
  { uv: [0.0, 0.5, 0.25, 0.5], aspect: 1.59, baseQ: 0.2014 }, // 4: cumulus_lean
  { uv: [0.25, 0.5, 0.25, 0.5], aspect: 1.84, baseQ: 0.2434 }, // 5: cumulus_round
  { uv: [0.5, 0.5, 0.25, 0.5], aspect: 7.86, baseQ: 0.4407 }, // 6: bank_wide (unused strip)
  { uv: [0.75, 0.5, 0.25, 0.5], aspect: 4.97, baseQ: 0.4043 }, // 7: bank_domes (unused strip)
];

const HERO_CLOUDS = [0, 2, 3, 4, 5] as const;
const DECK_CLOUDS = [2, 3, 5] as const;

function seededRandom(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s * 1664525 + 1013904223) | 0;
    return (s >>> 0) / 4294967296;
  };
}

/**
 * Creates 3D Instanced Six-Way lightmap cloud billboards from the 2048x1024 Blender Cycles atlas.
 * Placed around a 6.9-8.5 km sky ring with organic base dissolution above baseline_v
 * so no hard flat bottoms or strip seams appear in any direction.
 */
export function createCloudBillboards(sunDir: Vector3): InstancedMesh {
  void ensureCloudAtlasLoaded();
  const rand = seededRandom(73129);
  const placements: { az: number; r: number; yBase: number; w: number; h: number; cell: number; tint: number; opacity: number; seed: number }[] = [];

  const planetAz = Math.atan2(giantPlanetDirection.x, giantPlanetDirection.z);
  const moonAz = Math.atan2(shatteredMoonADirection.x, shatteredMoonADirection.z);
  const angDiff = (a: number, b: number) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));

  // Layer A: 28 wide billowing horizon decks (using billowing cells [2, 3, 5], zero flat paper strips)
  for (let i = 0; i < 28; i++) {
    const az = (i / 28) * Math.PI * 2 + (rand() - 0.5) * 0.11;
    const cell = DECK_CLOUDS[i % DECK_CLOUDS.length];
    const w = 2800 + rand() * 1400;
    const h = 1250 + rand() * 500;
    const r = 7900 + rand() * 550;
    const yBase = 120 + rand() * 400;
    placements.push({ az, r, yBase, w, h, cell, tint: 0.96 + rand() * 0.08, opacity: 0.78, seed: 1.7 + i * 3.13 });
  }

  // Layer B: 56 hero sculpted volumetric cumulus clouds across 360° (lush cells [0, 2, 3, 4, 5])
  const totalHero = 56;
  for (let i = 0; i < totalHero; i++) {
    const az = (i / totalHero) * Math.PI * 2 + (rand() - 0.5) * 0.09;
    const inPlanetWindow = angDiff(az, planetAz) < 0.24 || angDiff(az, moonAz) < 0.20;
    const cell = HERO_CLOUDS[Math.floor(rand() * HERO_CLOUDS.length)];
    const meta = CLOUD_CELL_META[cell];
    const scale = inPlanetWindow ? (0.58 + rand() * 0.22) : (0.90 + rand() * 0.52);
    const w = 1400 * meta.aspect * 0.86 * scale;
    const h = 1350 * scale;
    const r = 6900 + rand() * 850;
    const yBase = inPlanetWindow ? (80 + rand() * 180) : (520 + rand() * 1100);
    placements.push({
      az,
      r,
      yBase,
      w,
      h,
      cell,
      tint: 0.96 + rand() * 0.10,
      opacity: inPlanetWindow ? 0.65 : 0.90,
      seed: 19.4 + i * 2.71,
    });
  }

  // Dedicated sunlit cumulus anchors aligned to bookmark look azimuths (no congestus cone cell 1)
  const focalAnchors: { az: number; yBase: number; cell: number }[] = [
    { az: -1.42, yBase: 1250, cell: 0 }, // G7 WSW above ridge
    { az: -1.83, yBase: 980, cell: 3 }, // G5 / F4 West
    { az: -2.02, yBase: 1320, cell: 5 }, // G5 / F4 WNW high cumulus
    { az: -2.35, yBase: 1520, cell: 2 }, // G2 NW sunlit corona
    { az: +2.46, yBase: 1020, cell: 5 }, // G3 NE billowing deck
    { az: -0.28, yBase: 1050, cell: 0 }, // F3 SSW
  ];
  for (let k = 0; k < focalAnchors.length; k++) {
    const a = focalAnchors[k];
    const meta = CLOUD_CELL_META[a.cell];
    const h = 1350;
    const w = Math.min(3100, h * meta.aspect * 0.88);
    placements.push({
      az: a.az,
      r: 6950 + k * 80,
      yBase: a.yBase,
      w,
      h,
      cell: a.cell,
      tint: 1.0,
      opacity: 0.90,
      seed: 41.2 + k * 5.17,
    });
  }

  const count = placements.length;
  const geom = new PlaneGeometry(1, 1);
  const aCellData = new Float32Array(count * 4);
  const aRightData = new Float32Array(count * 4);
  const aFrontData = new Float32Array(count * 4);
  const aMetaData = new Float32Array(count * 4);

  const mesh = new InstancedMesh(geom, new MeshBasicNodeMaterial(), count);
  mesh.name = "cloud_billboards";
  mesh.frustumCulled = false;

  const dummy = new Object3D();
  const mat4 = new Matrix4();
  for (let i = 0; i < count; i++) {
    const p = placements[i];
    const sinA = Math.sin(p.az);
    const cosA = Math.cos(p.az);
    const cx = sinA * p.r;
    const cz = cosA * p.r;
    const cy = p.yBase + p.h * 0.5;

    const rx = -cosA, rz = sinA;
    const fx = -sinA, fz = -cosA;
    dummy.position.set(cx, cy, cz);
    dummy.rotation.set(0, Math.atan2(fx, fz), 0);
    dummy.scale.set(p.w, p.h, 1);
    dummy.updateMatrix();
    mat4.copy(dummy.matrix);
    mesh.setMatrixAt(i, mat4);

    const meta = CLOUD_CELL_META[p.cell];
    const [u0, v0, du, dv] = meta.uv;
    aCellData[i * 4 + 0] = u0 + 0.004 * du;
    aCellData[i * 4 + 1] = v0 + 0.004 * dv;
    aCellData[i * 4 + 2] = du * 0.992;
    aCellData[i * 4 + 3] = dv * 0.992;

    aRightData[i * 4 + 0] = rx;
    aRightData[i * 4 + 1] = 0;
    aRightData[i * 4 + 2] = rz;
    aRightData[i * 4 + 3] = p.tint;

    aFrontData[i * 4 + 0] = fx;
    aFrontData[i * 4 + 1] = 0;
    aFrontData[i * 4 + 2] = fz;
    aFrontData[i * 4 + 3] = p.opacity;

    const elevNorm = Math.max(0, Math.min(1, (p.yBase + p.h * 0.35) / 2200));
    aMetaData[i * 4 + 0] = meta.baseQ;
    aMetaData[i * 4 + 1] = p.opacity;
    aMetaData[i * 4 + 2] = p.seed;
    aMetaData[i * 4 + 3] = elevNorm;
  }
  mesh.instanceMatrix.needsUpdate = true;
  geom.setAttribute("aCell", new InstancedBufferAttribute(aCellData, 4));
  geom.setAttribute("aRight", new InstancedBufferAttribute(aRightData, 4));
  geom.setAttribute("aFront", new InstancedBufferAttribute(aFrontData, 4));
  geom.setAttribute("aMeta", new InstancedBufferAttribute(aMetaData, 4));

  const cellAttr = attribute("aCell", "vec4");
  const rightAttr = attribute("aRight", "vec4");
  const frontAttr = attribute("aFront", "vec4");
  const metaAttr = attribute("aMeta", "vec4");
  const qUV = uv();
  const atlasUV = vec2(cellAttr.x.add(qUV.x.mul(cellAttr.z)), cellAttr.y.add(float(1).sub(qUV.y).mul(cellAttr.w)));

  const sampA = texture(cloudLightATex, atlasUV);
  const sampB = texture(cloudLightBTex, atlasUV);
  const rawAlpha = sampA.a;
  const invA = float(1.0).div(rawAlpha.max(0.02));
  const px = sampA.r.pow(2.2).mul(invA).clamp(0, 2.5);
  const py = sampA.g.pow(2.2).mul(invA).clamp(0, 2.5);
  const pz = sampA.b.pow(2.2).mul(invA).clamp(0, 2.5);
  const nx = sampB.r.pow(2.2).mul(invA).clamp(0, 2.5);
  const ny = sampB.g.pow(2.2).mul(invA).clamp(0, 2.5);
  const nz = sampB.b.pow(2.2).mul(invA).clamp(0, 2.5);
  const amb = sampB.a.mul(invA).clamp(0, 2.0);

  const sVec = vec3(sunDir);
  const lx = dot(sVec, rightAttr.xyz);
  const ly = sVec.y;
  const lz = dot(sVec, frontAttr.xyz);
  const sx = mix(nx, px, smoothstep(-0.05, 0.05, lx));
  const sy = mix(ny, py, smoothstep(-0.05, 0.05, ly));
  const sz = mix(nz, pz, smoothstep(-0.05, 0.05, lz));
  const direct = lx.mul(lx).mul(sx).add(ly.mul(ly).mul(sy)).add(lz.mul(lz).mul(sz));

  // Restore rich sculpted 6-way volumetric self-shadowing & warm belly vs sunlit cauliflower cream
  const scatteredDirect = direct.max(0).pow(1.05);
  const undersideBounce = ny.mul(0.26).add(0.14);
  const viewOut = frontAttr.xyz.negate();
  const sunForward = dot(viewOut, sVec).max(0);
  const rimGlow = sunForward.pow(6).mul(smoothstep(0.95, 0.2, rawAlpha)).mul(0.55);

  const litCream = color(new Color("#FFF6E4")).mul(1.38);
  const warmShadow = color(new Color("#8891A4")).mul(0.88);
  const coolTopTint = color(new Color("#98ACC7")).mul(0.92);
  const cloudShade = mix(warmShadow, coolTopTint, qUV.y.mul(0.35));
  const tint = rightAttr.w;

  const rawCol = litCream
    .mul(scatteredDirect.mul(1.18).add(rimGlow.mul(0.85)).add(0.08))
    .add(cloudShade.mul(amb.mul(0.46).add(undersideBounce.mul(0.12))))
    .mul(tint);

  // Subtle horizon veil integration without washing out volumetric cloud relief
  const horizonVeil = color(new Color("#E4DCCB")).mul(1.02);
  const horizonMix = metaAttr.w.oneMinus().mul(0.28).add(qUV.y.oneMinus().mul(0.08)).clamp(0, 0.34);
  const finalCol = mix(rawCol, horizonVeil, horizonMix);

  // Organic multi-frequency base dissolution above exact cell baseline_v guarantees zero horizontal card edges
  const baseWave = mx_noise_float(vec3(qUV.x.mul(9.0).add(metaAttr.z), qUV.y.mul(5.0), metaAttr.z.mul(0.37))).mul(0.075)
    .add(mx_noise_float(vec3(qUV.x.mul(23.0).sub(metaAttr.z), qUV.y.mul(11.0), 3.1)).mul(0.03));
  const aboveBase = qUV.y.sub(metaAttr.x.add(0.022)).add(baseWave);
  const hardFloor = smoothstep(metaAttr.x.add(0.006), metaAttr.x.add(0.045), qUV.y);
  const baseFade = smoothstep(0.0, 0.19, aboveBase).mul(hardFloor);

  const edgeFadeX = smoothstep(0.0, 0.06, qUV.x).mul(smoothstep(1.0, 0.94, qUV.x));
  const topFade = smoothstep(1.0, 0.93, qUV.y);
  const finalAlpha = rawAlpha.mul(baseFade).mul(edgeFadeX).mul(topFade).mul(metaAttr.y).mul(cloudAtlasReady);

  const mat = new MeshBasicNodeMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    side: DoubleSide,
    fog: false,
  });
  mat.colorNode = finalCol;
  mat.opacityNode = finalAlpha;
  mesh.material = mat;
  mesh.renderOrder = -10;
  return mesh;
}

/**
 * Renders the monumental banded gas giant and sharp angular shattered moons with daytime sky scatter.
 */
export function buildCelestialBodiesNode(direction: Node<"vec3">, skyColor: Node<"vec3">, sunDir: Vector3) {
  let result: Node<"vec3"> = skyColor;

  // 1. Monumental Striped Giant Planet (crisp atmospheric bands, opaque sunlit crescent, sky-merged terminator)
  {
    const P = vec3(giantPlanetDirection);
    const U = normalize(cross(vec3(0, 1, 0), P));
    const V = cross(P, U);
    const radius = float(0.118);
    const px = dot(direction, U).div(radius);
    const py = dot(direction, V).div(radius);
    const pzSky = dot(direction, P);
    const d2 = px.mul(px).add(py.mul(py));
    const disk = smoothstep(1.0, 0.965, d2).mul(smoothstep(0.0, 0.05, pzSky));
    const nz = sqrt(float(1.0).sub(d2.min(1.0)));

    const tilt = 0.48;
    const cosT = Math.cos(tilt), sinT = Math.sin(tilt);
    const lat = py.mul(cosT).add(px.mul(sinT)).add(float(1.0).sub(nz).mul(0.12));
    const lon = px.mul(cosT).sub(py.mul(sinT));

    const swirl = mx_noise_float(vec3(lon.mul(2.4), lat.mul(9.5), nz.mul(1.8))).mul(0.085);
    const fineWarp = mx_noise_float(vec3(lon.mul(6.0), lat.mul(22.0), nz.mul(3.5))).mul(0.035);
    const bandCoord = lat.add(swirl).add(fineWarp);

    const band1 = sin(bandCoord.mul(11.5)).mul(0.5).add(0.5);
    const band2 = cos(bandCoord.mul(23.0).add(1.1)).mul(0.5).add(0.5);
    const ivory = color(new Color("#F2EBD9")).mul(1.06);
    const sand = color(new Color("#C7B49A"));
    const violetSlate = color(new Color("#7B7E91"));

    let albedo = mix(ivory, sand, smoothstep(0.2, 0.8, band1));
    albedo = mix(albedo, violetSlate, smoothstep(0.3, 0.8, band2).mul(0.62));

    const sunProjected = normalize(vec3(sunDir).add(U.mul(-0.72)).add(V.mul(0.48)));
    const normalWorld = normalize(U.mul(px).add(V.mul(py)).sub(P.mul(nz)));
    const nDotL = dot(normalWorld, sunProjected);
    const phase = smoothstep(-0.08, 0.36, nDotL);
    const limb = nz.pow(0.28);
    const rim = smoothstep(0.38, 0.0, nz).mul(smoothstep(0.0, 0.40, nDotL)).mul(0.16);

    const litSurface = albedo.mul(limb).add(color(swatch("cloud_cream")).mul(rim));
    const sunlitPlanet = mix(litSurface, skyColor, float(0.24));
    const planetComposite = mix(skyColor, sunlitPlanet, phase);
    const aboveHorizon = smoothstep(0.02, 0.13, direction.y);
    result = mix(result, planetComposite, disk.mul(aboveHorizon));
  }

  // 2. Shattered Moons (razor-sharp angular fracture bite + 6 sharp polygonal craggy rock shards)
  const rockChunks: { cx: number; cy: number; sx: number; sy: number; rot: number; seed: number }[] = [
    { cx: 0.46, cy: 0.54, sx: 0.26, sy: 0.14, rot: 0.48, seed: 2.1 },
    { cx: 0.78, cy: 0.78, sx: 0.22, sy: 0.11, rot: -0.28, seed: 5.4 },
    { cx: 0.96, cy: 0.42, sx: 0.14, sy: 0.08, rot: 0.85, seed: 8.3 },
    { cx: 0.28, cy: 0.96, sx: 0.16, sy: 0.09, rot: -0.68, seed: 11.7 },
    { cx: 0.64, cy: 0.98, sx: 0.10, sy: 0.06, rot: 0.22, seed: 15.2 },
    { cx: 0.86, cy: 0.16, sx: 0.11, sy: 0.06, rot: -0.95, seed: 19.8 },
  ];

  const addShatteredMoon = (moonVec: Vector3, rad: number, tiltAngle: number) => {
    const P = vec3(moonVec);
    const U = normalize(cross(vec3(0, 1, 0), P));
    const V = cross(P, U);
    const radius = float(rad);
    const px = dot(direction, U).div(radius);
    const py = dot(direction, V).div(radius);
    const pzSky = dot(direction, P);
    const d2 = px.mul(px).add(py.mul(py));
    const nz = sqrt(float(1.0).sub(d2.min(1.0)));

    const cosT = Math.cos(tiltAngle), sinT = Math.sin(tiltAngle);
    const rx = px.mul(cosT).sub(py.mul(sinT));
    const ry = px.mul(sinT).add(py.mul(cosT));

    // Ridged angular fracture noise carves a razor-crisp craggy canyon bite in the upper-right quadrant
    const biteN1 = abs(mx_noise_float(vec3(rx.mul(3.8), ry.mul(3.8), 1.3))).mul(0.28);
    const biteN2 = abs(mx_noise_float(vec3(rx.mul(10.5), ry.mul(10.5), 4.7))).mul(0.10);
    const biteX = rx.sub(0.56);
    const biteY = ry.sub(0.48);
    const biteDist = sqrt(biteX.mul(biteX).add(biteY.mul(biteY))).add(biteN1).add(biteN2);
    const intactMask = smoothstep(1.0, 0.982, d2).mul(smoothstep(0.56, 0.578, biteDist));

    // Six sharp polygonal rock plates & shards (razor-crisp anti-aliased edges)
    let chunkMask: Node<"float"> = float(0);
    let chunkNxAcc: Node<"float"> = float(0);
    let chunkNyAcc: Node<"float"> = float(0);
    for (const c of rockChunks) {
      const cosC = Math.cos(c.rot), sinC = Math.sin(c.rot);
      const dx = rx.sub(c.cx), dy = ry.sub(c.cy);
      const ux = dx.mul(cosC).add(dy.mul(sinC)).div(c.sx);
      const uy = dx.mul(-sinC).add(dy.mul(cosC)).div(c.sy);
      const polyDist = max(abs(ux), abs(uy)).mul(0.65).add(abs(ux).add(abs(uy)).mul(0.35));
      const jagged = abs(mx_noise_float(vec3(rx.mul(8.5), ry.mul(8.5), c.seed))).mul(0.28);
      const m = smoothstep(1.0, 0.975, polyDist.add(jagged));
      chunkMask = max(chunkMask, m);
      chunkNxAcc = chunkNxAcc.add(ux.mul(0.6).mul(m));
      chunkNyAcc = chunkNyAcc.add(uy.mul(0.6).mul(m));
    }

    const totalMask = max(intactMask, chunkMask).mul(smoothstep(0.0, 0.05, pzSky));
    const crater = mx_noise_float(vec3(px.mul(6.5), py.mul(6.5), nz.mul(4.5))).mul(0.5).add(0.5);
    const fineCrater = mx_noise_float(vec3(px.mul(16.0), py.mul(16.0), nz.mul(10.0))).mul(0.5).add(0.5);
    const craterTex = crater.mul(0.68).add(fineCrater.mul(0.32));

    const cliffBevel = smoothstep(0.56, 0.74, biteDist).oneMinus().mul(intactMask);
    const dustLight = color(new Color("#ECE6DA"));
    const fractureShade = color(new Color("#3B4250"));
    const rockAlbedo = mix(dustLight, fractureShade, craterTex.mul(0.76).add(cliffBevel.mul(0.52)).clamp(0, 1));

    const sunProjected = normalize(vec3(sunDir).add(U.mul(-0.65)).add(V.mul(0.45)));
    const sphereNormal = normalize(U.mul(px).add(V.mul(py)).sub(P.mul(nz)));
    const chunkLocalNormal = normalize(U.mul(chunkNxAcc).add(V.mul(chunkNyAcc)).sub(P.mul(0.75)));
    const normalWorld = mix(sphereNormal, chunkLocalNormal, chunkMask.mul(intactMask.oneMinus()));
    const nDotL = dot(normalWorld, sunProjected);
    const phase = smoothstep(-0.10, 0.34, nDotL);
    const moonLit = mix(fractureShade.mul(1.05), rockAlbedo.mul(1.08), phase.mul(0.88).add(0.12));
    const sunlitMask = phase.max(chunkMask.mul(0.78));
    const veiledMoon = mix(skyColor, mix(moonLit, skyColor, float(0.18)), sunlitMask);

    const aboveHorizon = smoothstep(0.02, 0.13, direction.y);
    result = mix(result, veiledMoon, totalMask.mul(aboveHorizon));
  };

  addShatteredMoon(shatteredMoonADirection, 0.102, 0.55);
  addShatteredMoon(shatteredMoonBDirection, 0.056, -0.42);

  return result;
}

/**
 * Generates a procedural 128x64 HDR Equirectangular environment DataTexture matching the Violet Reach sky:
 * rich sky zenith, crisp cool anti-sun fill, and realistic warm limestone/grass bounce without washing out shadows.
 */
export function createSkyEnvironmentTexture(sunDir: Vector3): DataTexture {
  const width = 128, height = 64;
  const data = new Float32Array(width * height * 4);

  const zenithBlue = swatch("sky_blue").clone().multiply(new Color(0.52, 0.68, 0.96));
  const midSky = swatch("sky_blue").clone().multiply(new Color(0.88, 0.92, 0.98));
  const horizonCream = swatch("cloud_cream").clone().lerp(swatch("haze"), 0.25);
  const coolShade = new Color("#7F95B8").multiplyScalar(0.95);
  const sunTint = swatch("cloud_cream").clone().lerp(swatch("accent_ochre"), 0.30);
  const groundOlive = swatch("stone_weathered").clone().lerp(swatch("grass_green"), 0.40).multiplyScalar(0.32);
  const groundNadir = swatch("stone_weathered").clone().lerp(swatch("soil"), 0.50).multiplyScalar(0.18);
  const tmp = new Color();

  for (let iy = 0; iy < height; iy++) {
    const v = (iy + 0.5) / height;
    const lat = (v - 0.5) * Math.PI;
    const dy = Math.sin(lat);
    const cosLat = Math.cos(lat);

    for (let ix = 0; ix < width; ix++) {
      const u = (ix + 0.5) / width;
      const lon = (u - 0.5) * Math.PI * 2;
      const dx = Math.cos(lon) * cosLat;
      const dz = Math.sin(lon) * cosLat;
      const sunDot = Math.max(0, dx * sunDir.x + dy * sunDir.y + dz * sunDir.z);

      if (dy >= 0) {
        const zenithT = Math.min(1, Math.pow(dy, 0.65));
        const horizonT = Math.pow(1 - dy, 2.8);
        tmp.copy(midSky).lerp(zenithBlue, zenithT);
        const antiSun = Math.max(0, -(dx * sunDir.x + dz * sunDir.z));
        tmp.lerp(coolShade, antiSun * 0.26 * (1 - zenithT * 0.5));
        tmp.lerp(horizonCream, horizonT * 0.86);

        const mie = Math.pow(sunDot, 5) * 0.62 + Math.pow(sunDot, 24) * 1.55;
        tmp.r += sunTint.r * mie;
        tmp.g += sunTint.g * mie;
        tmp.b += sunTint.b * mie;
      } else {
        const downT = Math.min(1, Math.pow(-dy, 0.55));
        tmp.copy(horizonCream).multiplyScalar(0.58).lerp(groundOlive, Math.min(1, -dy * 3.5));
        tmp.lerp(groundNadir, downT);
      }

      const idx = (iy * width + ix) * 4;
      data[idx] = tmp.r;
      data[idx + 1] = tmp.g;
      data[idx + 2] = tmp.b;
      data[idx + 3] = 1.0;
    }
  }

  const tex = new DataTexture(data, width, height, RGBAFormat, FloatType);
  tex.mapping = EquirectangularReflectionMapping;
  tex.colorSpace = LinearSRGBColorSpace;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}
