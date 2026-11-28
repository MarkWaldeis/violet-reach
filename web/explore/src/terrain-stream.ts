import { Group, Material, Mesh, type BufferGeometry } from "three/webgpu";
import {
  chooseLOD, decodeTile, parseManifest, sampleTile, selectTiles, tileKey, worldTile,
  type HeightTile, type TerrainManifest, type TileCoords,
} from "./heightfield.ts";
import { buildTerrainMesh, lodStride, stitchedHeight } from "./terrain-mesh.ts";
import { REFLECTION_LAYER } from "./quality.ts";
import { type Bounds } from "./slice.ts";

const FETCH_LIMIT = 4;
const ACTIVE_LIMIT = 180;
const BUILD_LIMIT = 2;
const RETRIES = 2;

interface Tile {
  coords: TileCoords;
  wantedLOD: number;
  lod?: number;
  reflected?: boolean;
  data?: HeightTile;
  mesh?: Mesh<BufferGeometry, Material>;
  reflectionMesh?: Mesh<BufferGeometry, Material>;
  pending?: AbortController;
  attempts: number;
  retryAt: number;
}

export class TerrainStream {
  readonly group = new Group();
  readonly manifest: TerrainManifest;
  #url: URL;
  #material: Material;
  #active = new Map<string, Tile>();
  #inFlight = 0;
  #last = { x: Infinity, z: Infinity };
  #slice?: Bounds;
  #pinned = new Map<string, HeightTile>();

  constructor(manifest: TerrainManifest, url: URL, material: Material) {
    this.manifest = manifest;
    this.#url = url;
    this.#material = material;
  }

  static async open(url: URL, material: Material) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Gelände-Manifest: HTTP ${response.status}`);
    return new TerrainStream(parseManifest(await response.json()), new URL(response.url || url.href), material);
  }

  async preloadSlice(bounds: Bounds) {
    this.#slice = bounds;
    await this.preloadHeights(bounds);
  }

  async preloadHeights(bounds: Bounds) {
    const m = this.manifest;
    const from = worldTile(m, bounds.minX, bounds.minZ), to = worldTile(m, bounds.maxX, bounds.maxZ);
    const pending: TileCoords[] = [];
    for (let z = from.z; z <= to.z; z++) for (let x = from.x; x <= to.x; x++) pending.push({ x, z });
    await Promise.all(Array.from({ length: FETCH_LIMIT }, async () => {
      for (let coords = pending.shift(); coords; coords = pending.shift()) {
        const key = tileKey(coords);
        if (this.#pinned.has(key)) continue;
        const response = await fetch(new URL(`${key}.r16`, this.#url));
        if (!response.ok) throw new Error(`Slice-Kachel ${key}: HTTP ${response.status}`);
        this.#pinned.set(key, decodeTile(await response.arrayBuffer(), m));
      }
    }));
  }

  fullHeightAt(x: number, z: number): number | undefined {
    const m = this.manifest;
    const coords = worldTile(m, x, z), key = tileKey(coords);
    const data = this.#pinned.get(key) ?? this.#active.get(key)?.data;
    if (!data) return undefined;
    return sampleTile(data, m.samples, 1, (x - m.originX) / m.tileSize - coords.x, (z - m.originZ) / m.tileSize - coords.z);
  }

  maxHeightInRect(minX: number, minZ: number, maxX: number, maxZ: number): number | undefined {
    const m = this.manifest;
    const from = worldTile(m, minX, minZ), to = worldTile(m, maxX, maxZ);
    let max = -Infinity, missing = false, found = false;
    for (let tz = from.z; tz <= to.z; tz++) for (let tx = from.x; tx <= to.x; tx++) {
      const key = tileKey({ x: tx, z: tz });
      const data = this.#pinned.get(key) ?? this.#active.get(key)?.data;
      if (!data) { missing = true; continue; }
      const x0 = m.originX + tx * m.tileSize, z0 = m.originZ + tz * m.tileSize;
      const n = m.samples, last = n - 1;
      const ix0 = Math.max(0, Math.floor((minX - x0) / m.tileSize * last) - 1);
      const ix1 = Math.min(last, Math.ceil((maxX - x0) / m.tileSize * last) + 1);
      const iz0 = Math.max(0, Math.floor((minZ - z0) / m.tileSize * last) - 1);
      const iz1 = Math.min(last, Math.ceil((maxZ - z0) / m.tileSize * last) + 1);
      if (ix1 < ix0 || iz1 < iz0) continue;
      found = true;
      for (let iz = iz0; iz <= iz1; iz++) {
        const row = iz * n;
        for (let ix = ix0; ix <= ix1; ix++) {
          const h = data[row + ix];
          if (h > max) max = h;
        }
      }
    }
    return missing || !found ? undefined : max;
  }

  update(x: number, z: number, now: number) {
    if (Math.hypot(x - this.#last.x, z - this.#last.z) >= Math.min(24, this.manifest.tileSize / 2)) {
      this.#last = { x, z };
      const wanted = new Map<string, Tile>();
      const candidates = selectTiles(this.manifest, x, z, this.#slice ? 8000 : undefined);
      for (const key of this.#pinned.keys()) {
        if (!candidates.some((t) => tileKey(t.coords) === key)) {
          const [tx, tz] = key.split("_").map(Number);
          candidates.push({ coords: { x: tx, z: tz }, distance: Math.hypot(tx * this.manifest.tileSize + this.manifest.originX - x, tz * this.manifest.tileSize + this.manifest.originZ - z) });
        }
      }
      candidates.sort((a, b) => Number(this.#pinned.has(tileKey(b.coords))) - Number(this.#pinned.has(tileKey(a.coords))) || a.distance - b.distance);
      for (const { coords, distance } of candidates.slice(0, this.#slice ? 256 : ACTIVE_LIMIT)) {
        const key = tileKey(coords);
        const tile = this.#active.get(key) ?? { coords, attempts: 0, retryAt: 0, wantedLOD: 0, data: this.#pinned.get(key) };
        const inSlice = this.#slice && coords.x * this.manifest.tileSize + this.manifest.originX < this.#slice.maxX &&
          (coords.x + 1) * this.manifest.tileSize + this.manifest.originX > this.#slice.minX &&
          coords.z * this.manifest.tileSize + this.manifest.originZ < this.#slice.maxZ &&
          (coords.z + 1) * this.manifest.tileSize + this.manifest.originZ > this.#slice.minZ;
        tile.wantedLOD = this.#slice && !inSlice
          ? this.#pinned.has(key) ? Math.max(1, chooseLOD(distance, tile.lod)) : 3
          : chooseLOD(distance, tile.lod);
        wanted.set(key, tile);
      }
      for (const [key, tile] of this.#active) {
        if (!wanted.has(key)) this.#remove(tile);
      }
      this.#active = wanted;
    }

    let built = 0;
    for (const tile of this.#active.values()) {
      if (tile.data) {
        if (tile.lod !== tile.wantedLOD && built < BUILD_LIMIT) {
          this.#build(tile);
          built++;
        }
      } else if (!tile.pending && this.#inFlight < FETCH_LIMIT && tile.attempts <= RETRIES && tile.retryAt <= now) {
        void this.#load(tile);
      }
    }
  }

  heightAt(x: number, z: number): number | undefined {
    const m = this.manifest;
    const coords = worldTile(m, x, z);
    const tile = this.#active.get(tileKey(coords));
    if (!tile?.data || tile.lod === undefined) return undefined;
    const u = (x - m.originX) / m.tileSize - coords.x, v = (z - m.originZ) / m.tileSize - coords.z;
    if (tile.mesh) {
      const edge = stitchedHeight(tile.mesh.geometry, u * m.tileSize, v * m.tileSize);
      if (edge !== undefined) return edge;
    }
    return sampleTile(tile.data, m.samples, lodStride(m, tile.lod), u, v);
  }

  failedAt(x: number, z: number) {
    const tile = this.#active.get(tileKey(worldTile(this.manifest, x, z)));
    return !!tile && !tile.data && !tile.pending && tile.attempts > RETRIES;
  }

  get stats() {
    const lods = [0, 0, 0, 0];
    let failed = 0, pending = 0;
    for (const tile of this.#active.values()) {
      if (tile.lod !== undefined) lods[tile.lod]++;
      if (tile.pending || tile.lod !== tile.wantedLOD) pending++;
      if (tile.attempts > RETRIES && !tile.data && !tile.pending) failed++;
    }
    return { lods, total: this.#active.size, failed, pending };
  }

  setReflectionMaterial(material: Material | null) {
    const target = material ?? this.#material;
    for (const tile of this.#active.values()) {
      if (tile.reflectionMesh && tile.reflectionMesh.material !== target) {
        tile.reflectionMesh.material = target;
      }
    }
  }

  dispose() {
    for (const tile of this.#active.values()) this.#remove(tile);
    this.#active.clear();
    this.#pinned.clear();
    this.#last = { x: Infinity, z: Infinity };
  }

  #remove(tile: Tile) {
    tile.pending?.abort();
    if (tile.mesh) {
      this.group.remove(tile.mesh);
      tile.mesh.dispose();
      tile.mesh.geometry.dispose();
    }
    if (tile.reflectionMesh) {
      this.group.remove(tile.reflectionMesh);
      tile.reflectionMesh.geometry.dispose();
    }
  }

  #canReflect(tx: number, tz: number, data: HeightTile) {
    if (!this.#slice) return true;
    const m = this.manifest;
    const half = m.tileSize * 0.5;
    const cx = m.originX + tx * m.tileSize + half;
    const cz = m.originZ + tz * m.tileSize + half;
    if (Math.hypot(cx - 812, cz - 2025) > 2800) return false;
    for (let i = 0; i < data.length; i++) {
      if (data[i] > 178) return true;
    }
    return false;
  }

  #build(tile: Tile) {
    const m = this.manifest;
    const geometry = buildTerrainMesh(m, tile.coords, tile.data!, tile.wantedLOD);
    if (tile.mesh) {
      tile.mesh.geometry.dispose();
      tile.mesh.geometry = geometry;
    } else {
      tile.reflected = this.#canReflect(tile.coords.x, tile.coords.z, tile.data!);
      tile.mesh = new Mesh(geometry, this.#material);
      tile.mesh.receiveShadow = tile.mesh.castShadow = true;
      tile.mesh.position.set(m.originX + tile.coords.x * m.tileSize, 0, m.originZ + tile.coords.z * m.tileSize);
      this.group.add(tile.mesh);
      if (tile.reflected) {
        const reflectionGeometry = buildTerrainMesh(m, tile.coords, tile.data!, 3);
        tile.reflectionMesh = new Mesh(reflectionGeometry, this.#material);
        tile.reflectionMesh.castShadow = tile.reflectionMesh.receiveShadow = false;
        tile.reflectionMesh.layers.set(REFLECTION_LAYER);
        tile.reflectionMesh.position.copy(tile.mesh.position);
        this.group.add(tile.reflectionMesh);
      }
    }
    tile.lod = tile.wantedLOD;
  }

  async #load(tile: Tile) {
    const controller = new AbortController();
    tile.pending = controller;
    this.#inFlight++;
    tile.attempts++;
    try {
      const response = await fetch(new URL(`${tileKey(tile.coords)}.r16`, this.#url), { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const buffer = await response.arrayBuffer();
      if (!controller.signal.aborted) tile.data = decodeTile(buffer, this.manifest);
    } catch (error) {
      if (!controller.signal.aborted) {
        tile.retryAt = performance.now() + 1500 * tile.attempts;
        if (tile.attempts > RETRIES) console.warn(`Geländekachel ${tileKey(tile.coords)}:`, error);
      }
    } finally {
      tile.pending = undefined;
      this.#inFlight--;
    }
  }
}
