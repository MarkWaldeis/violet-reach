export type QualityName = "low" | "medium" | "high" | "ultra";

export interface QualityLevel {
  name: QualityName;
  /** Upper bound for devicePixelRatio. */
  pixelRatio: number;
  shadows: boolean;
  /** Edge length of each shadow cascade map. */
  shadowMapSize: number;
  shadowCascades: number;
  /** Multiplies every per-asset view distance (an explicit ?assetDistance wins). */
  assetDistanceScale: number;
}

export const QUALITY_NAMES: readonly QualityName[] = ["low", "medium", "high", "ultra"];
export const DEFAULT_QUALITY: QualityName = "high";
export const REFLECTION_LAYER = 1;

// "high" is the unchanged pre-quality-switch behaviour.
export const QUALITY: Readonly<Record<QualityName, Readonly<QualityLevel>>> = {
  low: { name: "low", pixelRatio: 1, shadows: false, shadowMapSize: 1024, shadowCascades: 0, assetDistanceScale: 0.5 },
  medium: { name: "medium", pixelRatio: 1, shadows: true, shadowMapSize: 1024, shadowCascades: 2, assetDistanceScale: 0.75 },
  high: { name: "high", pixelRatio: 1.5, shadows: true, shadowMapSize: 2048, shadowCascades: 4, assetDistanceScale: 1 },
  ultra: { name: "ultra", pixelRatio: 2, shadows: true, shadowMapSize: 4096, shadowCascades: 4, assetDistanceScale: 1.25 },
};

export function qualityLevel(name: string | null | undefined = DEFAULT_QUALITY): Readonly<QualityLevel> {
  const key = (name ?? DEFAULT_QUALITY).trim().toLowerCase() || DEFAULT_QUALITY;
  if (!QUALITY_NAMES.includes(key as QualityName)) throw new Error(`quality: ${QUALITY_NAMES.join("|")} erwartet`);
  return QUALITY[key as QualityName];
}
