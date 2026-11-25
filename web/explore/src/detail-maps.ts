import {
  Color, LinearFilter, LinearMipmapLinearFilter, LinearSRGBColorSpace, MeshStandardMaterial,
  MeshStandardNodeMaterial, RepeatWrapping, Texture, TextureLoader, type Material,
} from "three/webgpu";
import {
  abs, cameraPosition, cameraViewMatrix, float, materialNormal, materialRoughness,
  normalViewGeometry, normalWorldGeometry, positionWorld, smoothstep, texture, vec3, vec4,
} from "three/tsl";

interface DetailTextureEntry {
  tile_m: number;
  files: [string, string];
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
  roughTex: Texture;
}

const DETAIL_NORMAL_STRENGTH: Record<string, number> = {
  stone_white: 0.07,
  rock_chalk: 0.11,
  sandstone: 0.11,
  bark: 0.11,
  crystal: 0.08,
  foliage: 0.06,
};

const assetClassMap = new Map<string, string>();
const detailMetaMap = new Map<string, DetailTextureEntry>();
const loadedClasses = new Map<string, LoadedDetailClass>();
let manifestsPromise: Promise<void> | null = null;
const patchedCache = new WeakMap<Material, Map<string, Material>>();

/** Foliage-class assets may mix leaf cards with woody primitives; leaves receive foliage detail, woody parts bark detail. */
export function detailClassForMaterial(assetClass: string | undefined, materialName = "") {
  if (assetClass !== "foliage") return assetClass;
  return /(?:^|[^a-z0-9])(?:bark|trunk|wood)(?:[^a-z0-9]|$)/i.test(materialName) ? "bark" : assetClass;
}

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
          if (val && Array.isArray(val.files) && val.files.length >= 2 && Number.isFinite(val.tile_m)) {
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
    if (cls && detailMetaMap.has(cls) && !loadedClasses.has(cls)) needed.add(cls);
    if (cls === "foliage" && detailMetaMap.has("bark") && !loadedClasses.has("bark")) needed.add("bark");
  }
  if (!needed.size) return;

  const loader = new TextureLoader();
  await Promise.all([...needed].map(async (cls) => {
    const entry = detailMetaMap.get(cls);
    if (!entry) return;
    try {
      const [normalTex, roughTex] = await Promise.all([
        loader.loadAsync(new URL(`./detail/${entry.files[0]}`, window.location.href).href),
        loader.loadAsync(new URL(`./detail/${entry.files[1]}`, window.location.href).href),
      ]);
      loadedClasses.set(cls, {
        tileM: Math.max(0.05, entry.tile_m),
        normalTex: configureDetailTexture(normalTex),
        roughTex: configureDetailTexture(roughTex),
      });
    } catch {
      // Leave material_class unloaded if detail asset fails to fetch.
    }
  }));
}

/**
 * Applies camera-faded world-space triplanar detail normal & roughness onto PBR asset materials
 * matching an entry's `material_class` (`3..22 m`), preserving all base PBR maps & alpha cutout state.
 * In mixed foliage assets, bark/trunk/wood materials use bark-scale instead of leaf-scale detail.
 */
export function applyAssetDetailMap(material: Material, assetId: string): Material {
  const cls = detailClassForMaterial(assetClassMap.get(assetId), material.name);
  const detail = cls ? loadedClasses.get(cls) : undefined;
  if (!cls || !detail) return material;
  if (!(material instanceof MeshStandardMaterial) && !(material instanceof MeshStandardNodeMaterial)) {
    return material;
  }

  let byClass = patchedCache.get(material);
  if (byClass?.has(cls)) return byClass.get(cls)!;

  let nodeMat: MeshStandardNodeMaterial;
  if (material instanceof MeshStandardNodeMaterial) {
    nodeMat = material.clone() as MeshStandardNodeMaterial;
  } else {
    nodeMat = new MeshStandardNodeMaterial().copy(material);
  }
  // Explicitly preserve cutout & depth flags not copied by MeshStandardNodeMaterial.copy in Three r183.
  nodeMat.alphaTest = material.alphaTest;
  nodeMat.depthWrite = material.depthWrite;
  nodeMat.depthTest = material.depthTest;
  nodeMat.opacity = material.opacity;
  nodeMat.alphaHash = material.alphaHash;
  nodeMat.colorWrite = material.colorWrite;

  const p = positionWorld;
  const nW = normalWorldGeometry.normalize();
  const blend = abs(nW).pow(4);
  const weight = blend.div(blend.x.add(blend.y).add(blend.z).max(0.0001));
  const scale = float(1 / detail.tileM);

  const uvX = p.zy.mul(scale);
  const uvY = p.xz.mul(scale);
  const uvZ = p.xy.mul(scale);

  const nX = texture(detail.normalTex, uvX).xy.mul(2).sub(1);
  const nY = texture(detail.normalTex, uvY).xy.mul(2).sub(1);
  const nZ = texture(detail.normalTex, uvZ).xy.mul(2).sub(1);
  const deltaWorld = vec3(0, nX.y, nX.x).mul(weight.x)
    .add(vec3(nY.x, 0, nY.y).mul(weight.y))
    .add(vec3(nZ.x, nZ.y, 0).mul(weight.z));

  const fade = smoothstep(3, 22, p.sub(cameraPosition).length()).oneMinus();
  const tangentDelta = deltaWorld.sub(nW.mul(deltaWorld.dot(nW)));
  const normalStrength = DETAIL_NORMAL_STRENGTH[cls] ?? 0.08;
  const deltaView = cameraViewMatrix.mul(vec4(tangentDelta, 0)).xyz.mul(fade.mul(normalStrength));
  const baseNormalView = material.normalMap || material.bumpMap ? materialNormal : normalViewGeometry;
  nodeMat.normalNode = baseNormalView.add(deltaView).normalize();

  const roughTri = texture(detail.roughTex, uvX).r.mul(weight.x)
    .add(texture(detail.roughTex, uvY).r.mul(weight.y))
    .add(texture(detail.roughTex, uvZ).r.mul(weight.z));
  nodeMat.roughnessNode = materialRoughness.add(roughTri.sub(0.5).mul(fade.mul(0.08))).clamp(0.08, 1.0);

  if (cls === "stone_white") {
    nodeMat.color = nodeMat.color.clone().multiply(new Color(0.94, 0.90, 0.82));
  } else if (cls === "bark") {
    nodeMat.color = nodeMat.color.clone().multiply(new Color(1.45, 1.38, 1.28));
  }

  if (!byClass) {
    byClass = new Map<string, Material>();
    patchedCache.set(material, byClass);
  }
  byClass.set(cls, nodeMat);
  return nodeMat;
}
