import {
  Color, DataTexture, DoubleSide, Group, LinearFilter, LinearMipmapLinearFilter,
  LinearSRGBColorSpace, Mesh, MeshPhysicalNodeMaterial, RepeatWrapping, RGBAFormat, Texture,
  TextureLoader, UnsignedByteType, type Node,
} from "three/webgpu";
import {
  attribute, cameraPosition, color, float, mix, mx_noise_float, positionWorld, reflect,
  reflector, screenUV, sin, smoothstep, texture, transformNormalToView, vec2, vec3,
} from "three/tsl";
import { sunDirection } from "./atmosphere.ts";
import { REFLECTION_LAYER } from "./quality.ts";
import { worldTime as time } from "./world-time.ts";
import type { WaterRegion } from "./hydrology.ts";
import { swatch } from "./palette.ts";
import type { SurfaceData } from "./surface-data.ts";
import { buildWaterGeometry } from "./water-geometry.ts";

function configureWaterTexture(tex: Texture): Texture {
  tex.colorSpace = LinearSRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.magFilter = LinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = 4;
  tex.flipY = false;
  tex.needsUpdate = true;
  return tex;
}

function makeWaterFallback(rgba: [number, number, number, number]): DataTexture {
  const tex = new DataTexture(new Uint8Array(rgba), 1, 1, RGBAFormat, UnsignedByteType);
  tex.colorSpace = LinearSRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.flipY = false;
  tex.needsUpdate = true;
  return tex;
}

let waterNormalATex: Texture = makeWaterFallback([128, 128, 255, 255]);
let waterNormalBTex: Texture = makeWaterFallback([128, 128, 255, 255]);
let waterFoamTex: Texture = makeWaterFallback([0, 0, 0, 255]);
let waterTexturesPromise: Promise<void> | null = null;

/**
 * Preloads the tiled normal and foam maps for water rendering.
 * Resolves immediately in Node unit tests without network calls.
 */
export function waitForWaterTextures(timeoutMs = 5000): Promise<void> {
  if (waterTexturesPromise) return waterTexturesPromise;
  if (typeof window === "undefined" || typeof fetch !== "function" || typeof createImageBitmap !== "function") {
    waterTexturesPromise = Promise.resolve();
    return waterTexturesPromise;
  }

  waterTexturesPromise = (async () => {
    const loader = new TextureLoader();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const work = Promise.all([
        loader.loadAsync(new URL("./water/water_normal_a.webp", window.location.href).href),
        loader.loadAsync(new URL("./water/water_normal_b.webp", window.location.href).href),
        loader.loadAsync(new URL("./water/water_foam.webp", window.location.href).href),
      ]);
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("water textures timeout")), timeoutMs);
      });
      const [nA, nB, foam] = await Promise.race([work, timeout]);
      waterNormalATex.dispose();
      waterNormalBTex.dispose();
      waterFoamTex.dispose();
      waterNormalATex = configureWaterTexture(nA);
      waterNormalBTex = configureWaterTexture(nB);
      waterFoamTex = configureWaterTexture(foam);
    } catch {
      // Keep neutral fallback textures if water maps are unavailable.
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  })();

  return waterTexturesPromise;
}

export function waterMaterial(surface: SurfaceData, reflection?: ReturnType<typeof reflector>, lakeY = 180.03) {
  const material = new MeshPhysicalNodeMaterial({
    side: DoubleSide,
    transparent: true,
    depthWrite: false,
    roughness: 0.09,
    metalness: 0.0,
    ior: 1.333,
  });

  const p = positionWorld;
  const field = surface.sample(p.xz);
  const surfUv = p.xz.sub(surface.origin).div(surface.size);
  const surfEdgeFade = smoothstep(0.0, 0.025, surfUv.x)
    .mul(smoothstep(0.0, 0.025, surfUv.y))
    .mul(smoothstep(0.0, 0.025, surfUv.x.oneMinus()))
    .mul(smoothstep(0.0, 0.025, surfUv.y.oneMinus()));
  const depth = p.y.sub(field.r).max(0);
  const lake = attribute("lake", "float");
  const footprint = lake.greaterThan(0.5).and(field.a.lessThanEqual(-3)).or(lake.lessThan(0.5).and(field.a.greaterThan(-3)));
  material.maskNode = p.y.sub(field.r).greaterThan(0.002).and(field.b.lessThan(0.30)).and(footprint);

  const flow = mix(vec2(0.9, 0.43589), attribute("flow", "vec2"), smoothstep(-3, 18, field.a).mul(lake.oneMinus()));
  const along = p.xz.dot(flow);
  const across = p.xz.dot(flow.yx.mul(vec2(-1, 1)));
  const dist = cameraPosition.sub(p).length();

  // Organic isotropic domain-bent wind gust mask (zero horizontal directional bands)
  const gustWarp = vec2(sin(p.z.mul(0.009).add(p.x.mul(0.005))), sin(p.x.mul(0.008).sub(p.z.mul(0.006)))).mul(0.45);
  const windUv = p.xz.mul(0.0065).add(gustWarp);
  const windPatch = mx_noise_float(windUv.add(vec2(time.mul(-0.005), time.mul(0.004)))).mul(0.5).add(0.5);
  const breeze = smoothstep(0.28, 0.74, windPatch);

  // Close procedural wind wavelets faded cleanly before Nyquist (< 85 m, zero aerial sandpaper stipple)
  const eps = 0.30;
  const hWave = (xz: typeof p.xz) => {
    const bend = sin(xz.x.mul(0.11).sub(xz.y.mul(0.14))).mul(0.75);
    const u1 = vec2(
      xz.x.mul(0.9205).sub(xz.y.mul(0.3907)).add(bend),
      xz.x.mul(0.3907).add(xz.y.mul(0.9205)).sub(bend.mul(0.7)),
    ).mul(0.32);
    const w1 = mx_noise_float(u1.add(vec2(time.mul(-0.15), time.mul(0.08))));
    const u2 = vec2(
      xz.x.mul(-0.4540).sub(xz.y.mul(0.8910)),
      xz.x.mul(0.8910).sub(xz.y.mul(0.4540)),
    ).mul(0.56).add(vec2(w1.mul(1.6), w1.mul(-1.4)));
    const w2 = mx_noise_float(u2.add(vec2(time.mul(0.12), time.mul(-0.14))).add(vec2(19.3, 41.7))).mul(0.60);
    return w1.add(w2);
  };
  const h0 = hWave(p.xz);
  const hx = hWave(p.xz.add(vec2(eps, 0)));
  const hz = hWave(p.xz.add(vec2(0, eps)));
  const h0Norm = h0.mul(0.35).add(0.5).clamp(0, 1);

  // Mipmapped, anisotropy-4 Ocean Modifier normal maps carry silky ripples across all distances
  const closeFade = smoothstep(35, 340, dist).oneMinus().mul(0.75).add(0.25);
  const c1 = 0.9563, s1 = 0.2924; // 17 deg
  const c2 = 0.1219, s2 = 0.9925; // 83 deg
  const warpClose = vec2(h0.mul(0.28), h0.mul(-0.22));
  const uvA1 = vec2(p.x.mul(c1).sub(p.z.mul(s1)), p.x.mul(s1).add(p.z.mul(c1))).div(3.6).add(warpClose).add(vec2(time.mul(-0.16), time.mul(0.08)));
  const uvA2 = vec2(p.x.mul(c2).sub(p.z.mul(s2)), p.x.mul(s2).add(p.z.mul(c2))).div(5.8).sub(warpClose).add(vec2(time.mul(0.12), time.mul(-0.10)));
  const r1 = texture(waterNormalATex, uvA1).xy.mul(2).sub(1);
  const r2 = texture(waterNormalATex, uvA2).xy.mul(2).sub(1);
  const nClose = vec2(
    r1.x.mul(c1).add(r1.y.mul(s1)).add(r2.x.mul(c2).add(r2.y.mul(s2))),
    r1.x.mul(-s1).add(r1.y.mul(c1)).add(r2.x.mul(-s2).add(r2.y.mul(c2))),
  ).mul(0.5).mul(closeFade.mul(0.042)).mul(mix(float(0.50), float(1.20), breeze));

  const nearWaveFade = smoothstep(14, 85, dist).oneMinus();
  const waveAmp = mix(float(0.015), float(0.048), breeze);
  const nWaveXZ = vec2(h0.sub(hx), h0.sub(hz)).div(eps).mul(nearWaveFade.mul(waveAmp));

  // Gentle silky broad swell from `water_normal_b` across 46 m
  const uvB = vec2(p.x.mul(0.6).sub(p.z.mul(0.8)), p.x.mul(0.8).add(p.z.mul(0.6))).div(46).add(vec2(time.mul(0.015), time.mul(-0.012)));
  const nBRaw = texture(waterNormalBTex, uvB).xy.mul(2).sub(1).mul(0.016);
  const normalXZ = nClose.add(nWaveXZ).add(vec2(nBRaw.x.mul(0.6).add(nBRaw.y.mul(0.8)), nBRaw.x.mul(-0.8).add(nBRaw.y.mul(0.6))));
  const normal = vec3(normalXZ.x, 1, normalXZ.y).normalize();
  material.normalNode = transformNormalToView(normal);

  material.roughnessNode = mix(float(0.02), float(0.09), breeze.mul(0.70).add(h0Norm.mul(0.30))).clamp(0.02, 0.12);

  const toEye = cameraPosition.sub(p).normalize();
  const ndotv = normal.dot(toEye).clamp(0.001, 1);
  const fresnel = float(0.02).add(float(0.98).mul(float(1).sub(ndotv).max(0.0001).pow(5))).clamp(0.02, 0.88);

  // Coastal ref_10/ref_11 Beer-Lambert turquoise-to-petrol underwater scattering
  const shallowClear = smoothstep(0.05, 0.65, depth);
  const depthMod = depth.add(h0.mul(0.06)).max(0);
  const absorb = float(1).sub(depthMod.mul(0.82).negate().exp());
  const shallowCol = color(new Color("#3CB2A8"));
  const midCol = color(new Color("#1B6E78"));
  const deepCol = color(new Color("#0F4254"));
  const waterBodyBase = mix(mix(shallowCol, midCol, smoothstep(0.04, 0.48, absorb)), deepCol, smoothstep(0.35, 0.94, absorb));
  const waterBody = waterBodyBase.mul(mix(float(1.03), float(0.95), breeze.mul(absorb)));

  // Delicate, patchy, open-lake-beach-only surf lace (zero unbroken perimeter halo)
  const isOpenLake = smoothstep(-2.0, 26.0, field.a).oneMinus().mul(lake);
  const foamUv = vec2(along.div(7.5).sub(time.mul(0.07)), across.div(7.5).add(time.mul(0.02))).mul(0.7).add(0.15);
  const foamTex = texture(waterFoamTex, foamUv).r;
  const foamZone = smoothstep(0.008, 0.17, depth).oneMinus().mul(smoothstep(0.0, 0.022, depth));
  const foamGust = smoothstep(0.34, 0.78, windPatch);
  const foamBreakup = foamTex.mul(0.68).add(h0Norm.mul(0.32));
  const foamFactor = smoothstep(0.42, 0.72, foamBreakup)
    .mul(foamZone)
    .mul(foamGust.mul(0.85).add(0.15))
    .mul(isOpenLake)
    .mul(smoothstep(-0.25, 0.18, field.b).oneMinus())
    .mul(0.84)
    .clamp(0, 0.84);

  // Physical Schlick Fresnel + Real-Time Planar Reflection (`reflector()`) blended smoothly with analytic sky
  const reflectDir = reflect(toEye.negate(), normal);
  const reflY = reflectDir.y.clamp(0, 1);
  const reflHorizon = color(new Color("#C4D9E6"));
  const reflMid = color(new Color("#5B98C8"));
  const reflZenith = color(new Color("#255B96"));
  const analyticSky = mix(mix(reflHorizon, reflMid, smoothstep(0.01, 0.22, reflY)), reflZenith, smoothstep(0.18, 0.65, reflY));

  let finalRefl: Node<"vec3"> = analyticSky;
  if (reflection) {
    reflection.uvNode = screenUV.flipX().add(normalXZ.mul(vec2(0.036, 0.062))).clamp(vec2(0.002), vec2(0.998));
    const flatLake = smoothstep(0.25, 2.2, p.y.sub(lakeY).abs()).oneMinus();
    finalRefl = mix(analyticSky, reflection.rgb, flatLake);
  }

  const shoreAlpha = smoothstep(0.0, 0.24, depth).mul(smoothstep(-0.65, 0.22, field.b).oneMinus()).mul(surfEdgeFade);
  const reflMix = fresnel.mul(0.68).add(0.07).mul(shallowClear.mul(0.78).add(0.22)).mul(foamFactor.oneMinus()).clamp(0.05, 0.64);

  // Energy-conserving split: underwater diffuse scaled by (1 - reflMix), HDR planar reflection + sun glint in emissiveNode
  const bodyDiffuse = waterBody.mul(reflMix.mul(0.82).oneMinus());
  material.colorNode = mix(bodyDiffuse, color(swatch("cloud_cream")), foamFactor);

  const depthAlpha = mix(float(0.06), float(0.95), absorb).max(fresnel.mul(0.32).mul(shallowClear));
  const foamOpacity = foamFactor.mul(smoothstep(0.0, 0.018, depth)).mul(surfEdgeFade);
  material.opacityNode = shoreAlpha.mul(depthAlpha).max(foamOpacity).clamp(0, 0.98);
  material.specularIntensityNode = mix(float(0.10), float(0.22), breeze.oneMinus()).mul(shallowClear).mul(shoreAlpha);

  // Crisp ref_10 directional golden sun-glint shimmer (NO static stipple sparkles!)
  const glintNormal = vec3(normalXZ.x.mul(2.6), 1, normalXZ.y.mul(2.6)).normalize();
  const half = toEye.add(vec3(sunDirection)).normalize();
  const ndoth = glintNormal.dot(half).max(0.0001);
  const sunGlint = ndoth.pow(18).mul(0.24).add(ndoth.pow(95).mul(1.85)).add(ndoth.pow(420).mul(5.2));
  const sparkle = sunGlint.mul(mix(float(0.85), float(1.25), breeze)).mul(shoreAlpha);
  material.emissiveNode = finalRefl.mul(reflMix).mul(shoreAlpha).add(color(new Color("#FFF6DC")).mul(sparkle));

  return material;
}

export function waterSurface(region: WaterRegion, surface: SurfaceData) {
  const group = new Group();
  const lakeY = (region.lakes[0]?.water_y ?? 180) + 0.03;
  let reflection: ReturnType<typeof reflector> | undefined;
  if (typeof window !== "undefined") {
    reflection = reflector({ resolutionScale: 0.25, bounces: false });
    reflection.target.position.set(900, lakeY, 1900);
    reflection.target.rotation.x = -Math.PI / 2;
    group.add(reflection.target);

    // Filter reflection pass to REFLECTION_LAYER and reuse main-pass CSM shadow maps (zero extra shadow renders)
    const baseReflector = reflection.reflector as unknown as {
      getVirtualCamera: (cam: unknown) => { layers: { set: (l: number) => void } };
      updateBefore: (frame: {
        frameId: number;
        camera: unknown;
        scene: { children: Array<{ isDirectionalLight?: boolean; layers: { enable: (l: number) => void }; shadow?: { autoUpdate: boolean; needsUpdate: boolean } }> };
      }) => unknown;
    };
    const origUpdateBefore = baseReflector.updateBefore.bind(baseReflector);
    let warmed = false;
    baseReflector.updateBefore = (frame) => {
      const vCam = baseReflector.getVirtualCamera(frame.camera);
      vCam.layers.set(REFLECTION_LAYER);
      const paused: Array<{ shadow: { autoUpdate: boolean; needsUpdate: boolean }; auto: boolean; needs: boolean }> = [];
      for (const child of frame.scene.children) {
        if (child.isDirectionalLight) {
          child.layers.enable(REFLECTION_LAYER);
          if (warmed && child.shadow) {
            paused.push({ shadow: child.shadow, auto: child.shadow.autoUpdate, needs: child.shadow.needsUpdate });
            child.shadow.autoUpdate = false;
            child.shadow.needsUpdate = false;
          }
        }
      }
      try {
        return origUpdateBefore(frame);
      } finally {
        for (const p of paused) {
          p.shadow.autoUpdate = p.auto;
          p.shadow.needsUpdate = p.needs;
        }
        if (frame.frameId > 1) warmed = true;
      }
    };
  }
  const mesh = new Mesh(buildWaterGeometry(region), waterMaterial(surface, reflection, lakeY));
  mesh.receiveShadow = true;
  group.add(mesh);
  return group;
}
