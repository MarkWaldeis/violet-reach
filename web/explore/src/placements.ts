export interface SinglePlacement {
  asset: string; x: number; z: number; yaw: number; scale: number; y_offset?: number;
}
export interface ScatterPlacement {
  asset: string;
  scatter: {
    seed: number; count: number;
    rect?: { minX: number; minZ: number; maxX: number; maxZ: number };
    polygon?: [number, number][];
    min_spacing: number;
    max_slope: number;
    min_height_above_water: number;
    max_height_above_water: number;
    scale: [number, number];
    align_to_slope?: boolean;
  };
}
export type Placement = SinglePlacement | ScatterPlacement;
export interface GroundSample { height: number; slope: number; normal: [number, number, number] }
export interface InstancePlacement extends SinglePlacement { y: number; normal?: [number, number, number] }

function inside(x: number, z: number, polygon: [number, number][]) {
  let result = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if ((a[1] > z) !== (b[1] > z) && x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]) result = !result;
  }
  return result;
}

/** Ground uses metres and slope degrees. Water height may vary along rivers.
 * Missing ground is an error: expand only after all required tiles are loaded.
 */
export function expandPlacements(
  entries: Placement[], groundAt: (x: number, z: number) => GroundSample | undefined,
  waterAt: (x: number, z: number) => number,
  acceptPosition: (x: number, z: number) => boolean = () => true,
): InstancePlacement[] {
  const result: InstancePlacement[] = [];
  for (const entry of entries) {
    if (!("scatter" in entry)) {
      if (!acceptPosition(entry.x, entry.z)) continue;
      const ground = groundAt(entry.x, entry.z);
      if (!ground) throw new Error(`Missing placement terrain: ${entry.asset}`);
      result.push({ ...entry, y: ground.height + (entry.y_offset ?? 0) });
      continue;
    }
    const s = entry.scatter;
    let state = s.seed >>> 0;
    const random = () => {
      state = (state + 0x6d2b79f5) | 0;
      let t = Math.imul(state ^ state >>> 15, 1 | state);
      t ^= t + Math.imul(t ^ t >>> 7, 61 | t);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
    const polygon = s.polygon;
    const r = s.rect ?? {
      minX: Math.min(...polygon!.map((p) => p[0])), maxX: Math.max(...polygon!.map((p) => p[0])),
      minZ: Math.min(...polygon!.map((p) => p[1])), maxZ: Math.max(...polygon!.map((p) => p[1])),
    };
    const accepted: InstancePlacement[] = [];
    const cells = new Map<string, InstancePlacement[]>();
    const cellSize = Math.max(s.min_spacing, 1);
    for (let attempt = 0; accepted.length < s.count && attempt < Math.max(100, s.count * 100); attempt++) {
      const x = r.minX + random() * (r.maxX - r.minX), z = r.minZ + random() * (r.maxZ - r.minZ);
      if (!acceptPosition(x, z)) continue;
      if (polygon && !inside(x, z, polygon)) continue;
      const ground = groundAt(x, z);
      if (!ground) throw new Error(`Missing scatter terrain: ${entry.asset}`);
      const above = ground.height - waterAt(x, z);
      if (ground.slope > s.max_slope || above < s.min_height_above_water || above > s.max_height_above_water) continue;
      const cx = Math.floor(x / cellSize), cz = Math.floor(z / cellSize);
      let crowded = false;
      for (let dx = -1; dx <= 1; dx++) for (let dz = -1; dz <= 1; dz++) {
        if (cells.get(`${cx + dx}_${cz + dz}`)?.some((p) => Math.hypot(p.x - x, p.z - z) < s.min_spacing)) crowded = true;
      }
      if (crowded) continue;
      const instance: InstancePlacement = {
        asset: entry.asset, x, z, y: ground.height, yaw: random() * 2 * Math.PI,
        scale: s.scale[0] + random() * (s.scale[1] - s.scale[0]),
        ...(s.align_to_slope ? { normal: ground.normal } : {}),
      };
      accepted.push(instance);
      const key = `${cx}_${cz}`;
      if (!cells.has(key)) cells.set(key, []);
      cells.get(key)!.push(instance);
    }
    if (accepted.length !== s.count) throw new Error(`Scatter ${entry.asset}: placed ${accepted.length}/${s.count}; constraints exhausted`);
    result.push(...accepted);
  }
  return result;
}
