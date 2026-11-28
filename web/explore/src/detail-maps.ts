import {
  Color, LinearFilter, LinearMipmapLinearFilter, LinearSRGBColorSpace, MeshPhysicalMaterial,
  MeshPhysicalNodeMaterial, MeshStandardMaterial, MeshStandardNodeMaterial, RepeatWrapping, Texture,
  TextureLoader, type Material, type Node,
} from "three/webgpu";
import {
  abs, cameraPosition, cameraViewMatrix, cos, dot, float, materialColor, materialEmissive,
  materialNormal, materialRoughness, mx_noise_float, normalViewGeometry, normalWorldGeometry,
  positionGeometry, positionWorld, sin, smoothstep, texture, vec2, vec3, vec4,
} from "three/tsl";

// Keep detail-maps importable in bare Node tests: atmosphere.ts/palette.ts use Vite-only raw JSON.
// These constants are the normalized values of atmosphere.ts sunDirection and palette violet_glow.
const DETAIL_SUN_DIRECTION = vec3(-0.5690634, 0.5284160, -0.6300345);
const CRYSTAL_GLOW_LINEAR = vec3(0.7454042, 0.5271151, 0.7454042);

interface DetailTextureEntry {
  tile_m: number;
  files: string[];
  roughness_mean?: number;
}
interface DetailManifest {
  textures: Record<string, DetailTextureEntry>;
}
interface AssetManifestEntry {
  id: string;
  material_class?: string;
}
interface AssetsManifest {
  assets: AssetManifestEntry[];
}
interface LoadedDetailClass {
  tileM: number;
  normalTex: Texture;
  roughCenter: number;
}

/**
 * Conservative per-class shader tuning. Normal values are tangent-space delta multipliers;
 * albedo values are maximum linear-luminance offsets around 1.0, and roughness values are
 * maximum additive roughness offsets after the detail signal has been normalized to [-1, 1].
 */
export interface DetailClassTuning {
  readonly microNormal: number;
  readonly macroNormal: number;
  readonly albedoMicro: number;
  readonly albedoNoise: number;
  readonly roughness: number;
  readonly macroTileM: number;
  readonly noiseTileM: number;
  /** metres; large-scale albedo variation can outlive the normal-detail octave on huge monuments. */
  readonly noiseFadeEndM: number;
  /** Optional normalization for signed low-amplitude MaterialX Perlin noise. */
  readonly noiseGain?: number;
}

function freezeTuning(tuning: DetailClassTuning): DetailClassTuning {
  return Object.freeze(tuning);
}

const DEFAULT_DETAIL_TUNING = freezeTuning({
  microNormal: 0.16,
  macroNormal: 0.06,
  albedoMicro: 0.018,
  albedoNoise: 0.018,
  roughness: 0.030,
  macroTileM: 3.5,
  noiseTileM: 8.0,
  noiseFadeEndM: 130,
});

export const DETAIL_CLASS_TUNING: Readonly<Record<string, DetailClassTuning>> = Object.freeze({
  // Chalk and sandstone need the strongest treatment: their assets span several meters and
  // otherwise read as large, soft color blotches even at walking distance.
  rock_chalk: freezeTuning({
    microNormal: 0.52,
    macroNormal: 0.27,
    albedoMicro: 0.040,
    albedoNoise: 0.072,
    roughness: 0.050,
    macroTileM: 5.0,
    noiseTileM: 12.0,
    noiseFadeEndM: 260,
  }),
  sandstone: freezeTuning({
    microNormal: 0.32,
    macroNormal: 0.14,
    albedoMicro: 0.030,
    albedoNoise: 0.040,
    roughness: 0.045,
    macroTileM: 4.5,
    noiseTileM: 10.0,
    noiseFadeEndM: 220,
  }),
  // Smooth monuments need visible pores/cracks, but not the heavy relief of natural cliff rock.
  stone_white: freezeTuning({
    microNormal: 0.40,
    macroNormal: 0.18,
    albedoMicro: 0.040,
    albedoNoise: 0.028,
    roughness: 0.052,
    macroTileM: 2.8,
    noiseTileM: 7.0,
    noiseFadeEndM: 520,
  }),
  // Crystal remains comparatively smooth and only receives a faint luminance breakup.
  crystal: freezeTuning({
    microNormal: 0.20,
    macroNormal: 0.10,
    albedoMicro: 0.022,
    albedoNoise: 0.046,
    roughness: 0.022,
    macroTileM: 2.0,
    noiseTileM: 1.8,
    noiseGain: 4.0,
    noiseFadeEndM: 300,
  }),
  // Organic classes stay deliberately restrained: no procedural color patches and no coarse octave.
  bark: freezeTuning({
    microNormal: 0.18,
    macroNormal: 0.0,
    albedoMicro: 0.010,
    albedoNoise: 0.0,
    roughness: 0.030,
    macroTileM: 2.4,
    noiseTileM: 6.0,
    noiseFadeEndM: 90,
  }),
  foliage: freezeTuning({
    microNormal: 0.07,
    macroNormal: 0.0,
    albedoMicro: 0.005,
    albedoNoise: 0.0,
    roughness: 0.014,
    macroTileM: 1.0,
    noiseTileM: 1.0,
    noiseFadeEndM: 60,
  }),
});

export function detailTuningForClass(cls: string): DetailClassTuning {
  return DETAIL_CLASS_TUNING[cls] ?? DEFAULT_DETAIL_TUNING;
}

const RIB_CROWN_DETAIL_TUNING = freezeTuning({
  ...DETAIL_CLASS_TUNING.stone_white,
  // At 250-500 m the ordinary 7 m noise is only a faint +/-2-3% signed Perlin variation.
  // The crown needs broader mineral banding within individual 6-13 m ribs, so its override
  // is deliberately stronger while remaining asset-local rather than changing all white stone.
  albedoNoise: 0.14,
  noiseTileM: 8.0,
  noiseGain: 8.0,
  noiseFadeEndM: 700,
});

/** Per-asset exceptions for structures whose scale makes class-wide detail wavelengths invisible. */
export function detailTuningForAsset(assetId: string, cls: string): DetailClassTuning {
  if (assetId === "monument_rib_crown_a" && cls === "stone_white") return RIB_CROWN_DETAIL_TUNING;
  return detailTuningForClass(cls);
}

const assetClassMap = new Map<string, string>();
const detailMetaMap = new Map<string, DetailTextureEntry>();
const loadedClasses = new Map<string, LoadedDetailClass>();
let manifestsPromise: Promise<void> | null = null;
const patchedCache = new WeakMap<Material, Map<string, Material>>();

/** Foliage-class assets may mix leaf cards with woody primitives. Leaf cards keep their authored
 * foliage textures without extra triplanar detail: their large overlapping alpha surfaces are
 * fillrate-critical, while woody primitives still receive bark detail. */
export function detailClassForMaterial(assetClass: string | undefined, materialName = "") {
  if (assetClass !== "foliage") return assetClass;
  if (/(?:^|[^a-z0-9])(?:bark|trunk|wood)(?:[^a-z0-9]|$)/i.test(materialName)) return "bark";
  return undefined;
}

function proceduralNoiseEnabled() {
  if (typeof window === "undefined") return true;
  return new URLSearchParams(window.location.search).get("procnoise") !== "0";
}

/** Narrow test seam for Node unit tests; production content should arrive via the manifests/TextureLoader path. */
export const detailMapsTestHooks = {
  registerAssetClass(assetId: string, materialClass: string): void {
    assetClassMap.set(assetId, materialClass);
  },
  registerDetailClass(cls: string, detail: LoadedDetailClass): void {
    loadedClasses.set(cls, detail);
  },
  reset(): void {
    assetClassMap.clear();
    detailMetaMap.clear();
    loadedClasses.clear();
    manifestsPromise = null;
  },
} as const;

function configureDetailTexture(tex: Texture): Texture {
  tex.colorSpace = LinearSRGBColorSpace;
  tex.wrapS = RepeatWrapping;
  tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.magFilter = LinearFilter;
  tex.flipY = false;
  tex.anisotropy = 4;
  tex.generateMipmaps = true;
  tex.needsUpdate = true;
  return tex;
}

async function ensureManifests(): Promise<void> {
  if (manifestsPromise) return manifestsPromise;
  if (typeof window === "undefined" || typeof fetch !== "function") {
    manifestsPromise = Promise.resolve();
    return manifestsPromise;
  }
  manifestsPromise = (async () => {
    try {
      const [detailRes, assetsRes] = await Promise.all([
        fetch(new URL("./detail/manifest.json", window.location.href)),
        fetch(new URL("./assets/manifest.json", window.location.href)),
      ]);
      if (detailRes.ok) {
        const dJson = (await detailRes.json()) as DetailManifest;
        for (const [key, val] of Object.entries(dJson.textures ?? {})) {
          if (val && Array.isArray(val.files) && val.files.length >= 1 && Number.isFinite(val.tile_m)) {
            detailMetaMap.set(key, val);
          }
        }
      }
      if (assetsRes.ok) {
        const aJson = (await assetsRes.json()) as AssetsManifest;
        for (const entry of aJson.assets ?? []) {
          if (entry.id && entry.material_class) {
            assetClassMap.set(entry.id, entry.material_class);
          }
        }
      }
    } catch {
      // Detail maps are optional enhancements; gracefully skip on missing manifests.
    }
  })();
  return manifestsPromise;
}

/**
 * Preloads triplanar micro-detail textures for every material_class used by `assetIds`.
 * Resolves cleanly without network calls in Node tests.
 */
export async function prepareDetailMapsForAssets(assetIds: string[]): Promise<void> {
  await ensureManifests();
  if (typeof window === "undefined") return;
  const needed = new Set<string>();
  for (const id of assetIds) {
    const cls = assetClassMap.get(id);
    if (cls && cls !== "foliage" && detailMetaMap.has(cls) && !loadedClasses.has(cls)) needed.add(cls);
    if (cls === "foliage" && detailMetaMap.has("bark") && !loadedClasses.has("bark")) needed.add("bark");
  }
  if (!needed.size) return;

  const loader = new TextureLoader();
  await Promise.all([...needed].map(async (cls) => {
    const entry = detailMetaMap.get(cls);
    if (!entry) return;
    try {
      const normalTex = await loader.loadAsync(new URL(`./detail/${entry.files[0]}`, window.location.href).href);
      const roughMean = entry.roughness_mean;
      loadedClasses.set(cls, {
        tileM: Math.max(0.05, entry.tile_m),
        normalTex: configureDetailTexture(normalTex),
        roughCenter: typeof roughMean === "number" && Number.isFinite(roughMean) ? Math.min(1, Math.max(0, roughMean)) : 0.5,
      });
    } catch {
      // Leave material_class unloaded if detail asset fails to fetch.
    }
  }));
}

/**
 * Applies camera-faded world-space triplanar detail onto PBR asset materials matching an entry's
 * `material_class` (`3..22 m`): dual-scale normal relief, normalized roughness variation and a
 * subtle hue-neutral luminance breakup. Base PBR maps, existing node graphs, alpha/cutout state
 * and LOD sharing are preserved. In mixed foliage assets, bark/trunk/wood materials use bark-scale
 * instead of leaf-scale detail.
 */
export function applyAssetDetailMap(material: Material, assetId: string): Material {
  const cls = detailClassForMaterial(assetClassMap.get(assetId), material.name);
  const detail = cls ? loadedClasses.get(cls) : undefined;
  if (!cls || !detail) return material;
  if (!(material instanceof MeshStandardMaterial) && !(material instanceof MeshStandardNodeMaterial)) {
    return material;
  }

  let byClass = patchedCache.get(material);
  const patchKey = `${assetId}:${cls}`;
  if (byClass?.has(patchKey)) return byClass.get(patchKey)!;

  let nodeMat: MeshStandardNodeMaterial;
  if (material instanceof MeshStandardNodeMaterial) {
    nodeMat = material.clone() as MeshStandardNodeMaterial;
  } else if (material instanceof MeshPhysicalMaterial || cls === "crystal") {
    // Crystal/gem assets need physical clearcoat/IOR even when the current flattened GLB export
    // only produced a standard material; copying into plain standard would discard that response.
    nodeMat = new MeshPhysicalNodeMaterial().copy(material);
  } else {
    nodeMat = new MeshStandardNodeMaterial().copy(material);
  }
  // Explicitly preserve cutout, transparency & depth flags not copied by MeshStandardNodeMaterial.copy in Three r183.
  nodeMat.alphaTest = material.alphaTest;
  nodeMat.depthWrite = material.depthWrite;
  nodeMat.depthTest = material.depthTest;
  nodeMat.opacity = material.opacity;
  nodeMat.alphaHash = material.alphaHash;
  nodeMat.colorWrite = material.colorWrite;
  nodeMat.transparent = material.transparent;
  nodeMat.side = material.side;
  nodeMat.alphaToCoverage = material.alphaToCoverage;

  const tuning = detailTuningForAsset(assetId, cls);
  const p = positionWorld;
  const nW = normalWorldGeometry.normalize();
  const blend = abs(nW).pow(4);
  const weight = blend.div(blend.x.add(blend.y).add(blend.z).max(0.0001));
  const scale = float(1 / detail.tileM);

  const uvX = p.zy.mul(scale);
  const uvY = p.xz.mul(scale);
  const uvZ = p.xy.mul(scale);

  const sampleX = texture(detail.normalTex, uvX);
  const sampleY = texture(detail.normalTex, uvY);
  const sampleZ = texture(detail.normalTex, uvZ);
  const nX = sampleX.xy.mul(2).sub(1);
  const nY = sampleY.xy.mul(2).sub(1);
  const nZ = sampleZ.xy.mul(2).sub(1);
  const microDeltaWorld = vec3(0, nX.y, nX.x).mul(weight.x)
    .add(vec3(nY.x, 0, nY.y).mul(weight.y))
    .add(vec3(nZ.x, nZ.y, 0).mul(weight.z));
  const microTangentDelta = microDeltaWorld.sub(nW.mul(microDeltaWorld.dot(nW)));
  const microTangentDetail = microTangentDelta.mul(tuning.microNormal);
  let macroTangentDetail = microTangentDelta.mul(0);
  let roughMacroSignal = float(0) as unknown as Node<"float">;

  // Reuse the same detail-normal texture at a much larger world scale for mineral surfaces.
  // The low-frequency octave survives mipmap filtering and breaks up 2..15 m walls without
  // adding textures, draw calls or another render pass. A small world-space warp hides the tiling.
  if (tuning.macroNormal > 0) {
    const warpX = sin(p.x.mul(0.53).add(p.y.mul(0.37)).add(p.z.mul(0.41))).mul(0.42);
    const warpY = cos(p.x.mul(0.29).sub(p.y.mul(0.61)).add(p.z.mul(0.47))).mul(0.42);
    const warpZ = sin(p.x.mul(-0.43).add(p.y.mul(0.31)).add(p.z.mul(0.67)).add(1.7)).mul(0.42);
    const pMacro = p.add(vec3(warpX, warpY, warpZ));
    const macroScale = float(1 / tuning.macroTileM);
    const macroOffset = vec2(0.37, 0.71);
    const uvMacroX = pMacro.zy.mul(macroScale).add(macroOffset);
    const uvMacroY = pMacro.xz.mul(macroScale).add(macroOffset);
    const uvMacroZ = pMacro.xy.mul(macroScale).add(macroOffset);

    const macroSampleX = texture(detail.normalTex, uvMacroX);
    const macroSampleY = texture(detail.normalTex, uvMacroY);
    const macroSampleZ = texture(detail.normalTex, uvMacroZ);
    const mX = macroSampleX.xy.mul(2).sub(1);
    const mY = macroSampleY.xy.mul(2).sub(1);
    const mZ = macroSampleZ.xy.mul(2).sub(1);
    const macroDeltaWorld = vec3(0, mX.y, mX.x).mul(weight.x)
      .add(vec3(mY.x, 0, mY.y).mul(weight.y))
      .add(vec3(mZ.x, mZ.y, 0).mul(weight.z));
    const macroTangentDelta = macroDeltaWorld.sub(nW.mul(macroDeltaWorld.dot(nW)));
    macroTangentDetail = macroTangentDelta.mul(tuning.macroNormal);

    if (cls === "stone_white") {
      const roughMacroTri = macroSampleX.z.mul(weight.x)
        .add(macroSampleY.z.mul(weight.y))
        .add(macroSampleZ.z.mul(weight.z));
      roughMacroSignal = roughMacroTri.sub(detail.roughCenter).div(0.055).clamp(-1, 1);
    }
  }

  // Large mineral assets are still the close focus well beyond the old 22 m micro-detail range.
  // Keep fine pores local, but let the coarse octave carry rock/stone/crystal structure into the
  // 60..140 m walking/flying band where cliff walls and monuments otherwise flatten into plastic.
  const detailDistance = p.sub(cameraPosition).length();
  const microFadeEnd = tuning.microNormal >= 0.28 ? 54 : 28;
  const microFade = smoothstep(3, microFadeEnd, detailDistance).oneMinus();
  const macroFadeEnd = Math.max(34, tuning.macroTileM * 28);
  const macroFade = smoothstep(8, macroFadeEnd, detailDistance).oneMinus();
  const noiseFade = smoothstep(8, tuning.noiseFadeEndM, detailDistance).oneMinus();
  const tangentDelta = microTangentDetail.mul(microFade).add(macroTangentDetail.mul(macroFade));
  const deltaView = cameraViewMatrix.mul(vec4(tangentDelta, 0)).xyz;
  const existingNormalNode = material instanceof MeshStandardNodeMaterial ? material.normalNode : null;
  const baseNormalView = (existingNormalNode ?? (material.normalMap || material.bumpMap ? materialNormal : normalViewGeometry)) as unknown as Node<"vec3">;
  nodeMat.normalNode = baseNormalView.add(deltaView).normalize();

  const roughTri = sampleX.z.mul(weight.x)
    .add(sampleY.z.mul(weight.y))
    .add(sampleZ.z.mul(weight.z));
  // Roughness maps are high-key; centering on the manifest mean and normalizing prevents an overall
  // roughness/albedo bias while keeping cracks and pores visible as a bounded ±1 signal.
  const roughSignal = roughTri.sub(detail.roughCenter).div(0.035).clamp(-1, 1);
  const existingRoughnessNode = material instanceof MeshStandardNodeMaterial ? material.roughnessNode : null;
  const baseRoughness = (existingRoughnessNode ?? materialRoughness) as unknown as Node<"float">;
  const roughDetail = roughSignal.mul(microFade).add(roughMacroSignal.mul(macroFade).mul(0.55));
  nodeMat.roughnessNode = baseRoughness.add(roughDetail.mul(tuning.roughness)).clamp(0.08, 1.0);

  // Hue-neutral close-detail luminance from the roughness texture, plus volumetric world noise for
  // large non-repeating patches on mineral surfaces. Alpha is carried through explicitly so cutout
  // foliage and GLB map alpha behave exactly as in the unpatched material.
  let luminanceDetail = roughSignal.mul(tuning.albedoMicro).mul(microFade)
    .add(roughMacroSignal.mul(tuning.albedoMicro).mul(0.85).mul(macroFade));
  const useProceduralNoise = proceduralNoiseEnabled() && (cls === "crystal" || assetId === "monument_rib_crown_a");
  if (useProceduralNoise && tuning.albedoNoise > 0) {
    const noisePos = p.mul(float(1 / tuning.noiseTileM)).add(vec3(17.13, 41.7, 9.31));
    luminanceDetail = luminanceDetail.add(mx_noise_float(noisePos).mul(tuning.noiseGain ?? 1).clamp(-1, 1).mul(tuning.albedoNoise).mul(noiseFade));
  }
  // The packed mineral detail already carries the broad pores/cracks used for ordinary pale stone;
  // expensive freeform procedural noise is reserved for crystal interiors and the rib crown, whose
  // monumental scale makes the baked/packaged mineral structure too repetitive without it.
  const albedoScale = float(1).add(luminanceDetail).clamp(0.90, 1.10);
  const existingColorNode = material instanceof MeshStandardNodeMaterial ? material.colorNode : null;
  const baseDiffuse = vec4((existingColorNode ?? materialColor) as unknown as Node<"vec4">);
  nodeMat.colorNode = vec4(baseDiffuse.rgb.mul(albedoScale), baseDiffuse.a);

  if (cls === "stone_white") {
    nodeMat.color = nodeMat.color.clone().multiply(new Color(0.94, 0.90, 0.82));
  } else if (cls === "bark") {
    nodeMat.color = nodeMat.color.clone().multiply(new Color(1.45, 1.38, 1.28));
  } else if (cls === "crystal") {
    // The baked emission map is mostly a flat violet body (inspected after KTX2 extraction):
    // the internal structure visible in the Cycles review did not survive the bake. Keep only a
    // restrained baked core glow, then rebuild the missing cloudy/veined mineral structure in
    // object space. MaterialX noise is low-amplitude, so it is normalized before shaping.
    nodeMat.emissive = nodeMat.emissive.clone().multiplyScalar(0.16);
    const existingEmissiveNode = material instanceof MeshStandardNodeMaterial ? material.emissiveNode : null;
    const bakedEmission = (existingEmissiveNode ?? materialEmissive) as unknown as Node<"vec3">;
    const emissionEnergy = dot(bakedEmission, vec3(1 / 3, 1 / 3, 1 / 3));
    const veinGate = smoothstep(0.06, 0.24, emissionEnergy).pow(1.25);
    const selectiveEmission = bakedEmission.mul(float(0.06).add(veinGate.mul(0.90)));

    const objectP = positionGeometry;
    let internalGlow = CRYSTAL_GLOW_LINEAR.mul(0);
    if (useProceduralNoise) {
      const cloudNoise = mx_noise_float(objectP.mul(1 / 2.2).add(vec3(4.7, 9.1, 2.3))).mul(4).clamp(-1, 1);
      const cloud = cloudNoise.mul(0.5).add(0.5);
      const veinNoiseA = abs(mx_noise_float(objectP.mul(1 / 1.15).add(vec3(8.3, 2.9, 5.7))).mul(5)).clamp(0, 1);
      const veinNoiseB = abs(mx_noise_float(objectP.mul(1 / 2.05).add(vec3(2.4, 11.7, 7.1))).mul(4)).clamp(0, 1);
      const veinA = smoothstep(0.025, 0.18, veinNoiseA).oneMinus();
      const veinB = smoothstep(0.018, 0.12, veinNoiseB).oneMinus();
      const veinMask = veinA.mul(0.72).add(veinB.mul(0.42)).clamp(0, 1);
      internalGlow = CRYSTAL_GLOW_LINEAR.mul(cloud.mul(0.030).add(veinMask.mul(0.150)));
    }

    // Cheap mineral translucency: thin silhouettes receive only a very restrained violet backlight,
    // strongest on faces turned away from the sun. No costly transmission pass is introduced.
    const viewDir = cameraPosition.sub(positionWorld).normalize();
    const rim = abs(dot(nW, viewDir)).oneMinus().clamp(0, 1).pow(2.2);
    const sunBack = dot(nW, DETAIL_SUN_DIRECTION).negate().clamp(0, 1);
    const translucency = CRYSTAL_GLOW_LINEAR.mul(rim).mul(float(0.35).add(sunBack.mul(0.65))).mul(0.015);
    nodeMat.emissiveNode = selectiveEmission.add(internalGlow).add(translucency);

    const physical = nodeMat as MeshPhysicalNodeMaterial;
    if (!physical.clearcoat) physical.clearcoat = 0.55;
    if (!physical.clearcoatRoughness) physical.clearcoatRoughness = 0.08;
    if (Math.abs((physical.ior || 1.5) - 1.5) < 1e-4) physical.ior = 1.6;
  }

  if (!byClass) {
    byClass = new Map<string, Material>();
    patchedCache.set(material, byClass);
  }
  byClass.set(patchKey, nodeMat);
  return nodeMat;
}
