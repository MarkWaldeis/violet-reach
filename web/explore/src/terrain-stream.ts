import { Group, Material, Mesh, type BufferGeometry } from "three/webgpu";
import {
  chooseLOD, decodeTile, parseManifest, sampleTile, selectTiles, tileKey, worldTile,
  type HeightTile, type TerrainManifest, type TileCoords,
} from "./heightfield.ts";
import { buildTerrainMesh, lodStride } from "./terrain-mesh.ts";

const FETCH_LIMIT = 4;
const ACTIVE_LIMIT = 180;
const BUILD_LIMIT = 2;
const RETRIES = 2;

interface Tile {
  coords: TileCoords;
  wantedLOD: number;
  lod?: number;
  data?: HeightTile;
  mesh?: Mesh<BufferGeometry, Material>;
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

  constructor(manifest: TerrainManifest, url: URL, material: Material) {
    this.manifest = manifest;
    this.#url = url;
    this.#material = material;
  }

  static async open(url: URL, material: Material) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Gelände-Manifest: HTTP ${response.status}`);
    return new TerrainStream(parseManifest(await response.json()), url, material);
  }

  update(x: number, z: number, now: number) {
    if (Math.hypot(x - this.#last.x, z - this.#last.z) >= 24) {
      this.#last = { x, z };
      const wanted = new Map<string, Tile>();
      for (const { coords, distance } of selectTiles(this.manifest, x, z).slice(0, ACTIVE_LIMIT)) {
        const key = tileKey(coords);
        const tile = this.#active.get(key) ?? { coords, attempts: 0, retryAt: 0, wantedLOD: 0 };
        tile.wantedLOD = chooseLOD(distance, tile.lod);
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
    return sampleTile(tile.data, m.samples, lodStride(m, tile.lod), u, v);
  }

  failedAt(x: number, z: number) {
    const tile = this.#active.get(tileKey(worldTile(this.manifest, x, z)));
    return !!tile && !tile.data && !tile.pending && tile.attempts > RETRIES;
  }

  get stats() {
    const lods = [0, 0, 0, 0];
    let failed = 0;
    for (const tile of this.#active.values()) {
      if (tile.lod !== undefined) lods[tile.lod]++;
      if (tile.attempts > RETRIES && !tile.data && !tile.pending) failed++;
    }
    return { lods, total: this.#active.size, failed };
  }

  dispose() {
    for (const tile of this.#active.values()) this.#remove(tile);
    this.#active.clear();
    this.#last = { x: Infinity, z: Infinity };
  }

  #remove(tile: Tile) {
    tile.pending?.abort();
    if (!tile.mesh) return;
    this.group.remove(tile.mesh);
    tile.mesh.geometry.dispose();
  }

  #build(tile: Tile) {
    const m = this.manifest;
    const geometry = buildTerrainMesh(m, tile.coords, tile.data!, tile.wantedLOD);
    if (tile.mesh) {
      tile.mesh.geometry.dispose();
      tile.mesh.geometry = geometry;
    } else {
      tile.mesh = new Mesh(geometry, this.#material);
      tile.mesh.position.set(m.originX + tile.coords.x * m.tileSize, 0, m.originZ + tile.coords.z * m.tileSize);
      this.group.add(tile.mesh);
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
