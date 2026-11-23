"""Phase 2.3 & 4.1 World Macro Map Generator for Violet Reach.

Assembles the full 4097x4097 (2 m spacing) world heightfield from
`world/terrain/runtime/{tx}_{tz}.r16` across `[-4096, 4096] x [-4096, 4096]` (8x8 km),
computes slope, surface normals, multi-scale curvature, hydrology distance/depth,
path distance mask, 8-azimuth horizon/sky-view AO, and tree canopy shadows, and writes:

  - web/explore/public/ground/macro_color_ao.webp   (4096x4096 RGBA WebP)
  - web/explore/public/ground/macro_weights_a.webp  (2048x2048 RGBA WebP)
  - web/explore/public/ground/macro_weights_b.webp  (2048x2048 RGBA WebP)
  - web/explore/public/ground/macro_grass.webp      (2048x2048 RGBA WebP)
  - web/explore/public/ground/macro.json
  - C:/Users/Mark Waldeis/devin-screenshots/violet-reach/ground/macro_preview.jpg
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
WORLD_DIR = ROOT / "world"
RUNTIME_DIR = WORLD_DIR / "terrain" / "runtime"
PUBLIC_GROUND_DIR = ROOT / "web" / "explore" / "public" / "ground"
DEFAULT_PREVIEW_PATH = Path(r"C:\Users\Mark Waldeis\devin-screenshots\violet-reach\ground\macro_preview.jpg")

SEED = 73129
SUN_DIR = np.array([-0.56, 0.52, -0.62], dtype=np.float32)
SUN_DIR /= np.linalg.norm(SUN_DIR)


# ---------------------------------------------------------------------------
# Color & Math Helpers
# ---------------------------------------------------------------------------
def smoothstep(edge0: float | np.ndarray, edge1: float | np.ndarray, x: np.ndarray) -> np.ndarray:
    diff = edge1 - edge0
    denom = np.where(np.abs(diff) < 1e-6, 1e-6, diff)
    t = np.clip((x - edge0) / denom, 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def srgb_to_lin(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055).astype(np.float32)


def hex_to_lin(hex_str: str) -> np.ndarray:
    h = hex_str.lstrip("#")
    srgb = np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0
    return srgb_to_lin(srgb)


def value_noise(x: np.ndarray, z: np.ndarray, scale: float, salt: int = 0) -> np.ndarray:
    """Deterministic 2D value noise in [-1, 1] matching build_world.py."""
    xs = x / scale
    zs = z / scale
    ix = np.floor(xs)
    iz = np.floor(zs)
    u = xs - ix
    v = zs - iz
    u = u * u * (3.0 - 2.0 * u)
    v = v * v * (3.0 - 2.0 * v)

    def hashed(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        q = np.sin(a * 127.1 + b * 311.7 + SEED + salt * 19.3) * 43758.5453
        return q - np.floor(q)

    n00 = hashed(ix, iz)
    n10 = hashed(ix + 1.0, iz)
    n01 = hashed(ix, iz + 1.0)
    n11 = hashed(ix + 1.0, iz + 1.0)
    val = (n00 * (1.0 - u) + n10 * u) * (1.0 - v) + (n01 * (1.0 - u) + n11 * u) * v
    return (val * 2.0 - 1.0).astype(np.float32)


def box_blur_2d(arr: np.ndarray, radius: int, passes: int = 2) -> np.ndarray:
    """Fast separable mirror-padded box blur in pure NumPy."""
    if radius <= 0:
        return arr.copy()
    out = arr.astype(np.float32, copy=True)
    w = 2 * radius + 1
    for _ in range(passes):
        # Horizontal pass
        pad_x = np.pad(out, ((0, 0), (radius, radius)), mode="edge")
        cs_x = np.cumsum(pad_x, axis=1, dtype=np.float64)
        out = ((cs_x[:, w - 1 :] - np.pad(cs_x[:, :-w], ((0, 0), (1, 0)))) / w).astype(np.float32)
        # Vertical pass
        pad_y = np.pad(out, ((radius, radius), (0, 0)), mode="edge")
        cs_y = np.cumsum(pad_y, axis=0, dtype=np.float64)
        out = ((cs_y[w - 1 :, :] - np.pad(cs_y[:-w, :], ((1, 0), (0, 0)))) / w).astype(np.float32)
    return out


def downsample_2x(arr: np.ndarray) -> np.ndarray:
    """2x2 box downsample from (2H, 2W, ...) to (H, W, ...)."""
    return (0.25 * (arr[0::2, 0::2] + arr[1::2, 0::2] + arr[0::2, 1::2] + arr[1::2, 1::2])).astype(np.float32)


def upsample_2x_bilinear(arr: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    """Upsample 2D float32 array to target_hw using PIL bilinear interpolation."""
    im = Image.fromarray(arr.astype(np.float32), mode="F")
    return np.asarray(im.resize((target_hw[1], target_hw[0]), Image.BILINEAR), dtype=np.float32)


# ---------------------------------------------------------------------------
# 1. Assemble 4097x4097 -> 4096x4096 World Heightfield
# ---------------------------------------------------------------------------
def load_world_heightfield(runtime_dir: Path) -> tuple[np.ndarray, dict]:
    manifest_path = runtime_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tiles_x = int(manifest["tilesX"])
    tiles_z = int(manifest["tilesZ"])
    samples = int(manifest["samples"])
    step = samples - 1  # 256
    min_h = float(manifest["minHeight"])
    max_h = float(manifest["maxHeight"])
    scale = (max_h - min_h) / 65535.0

    full_n = tiles_x * step + 1  # 4097
    full_h = np.empty((full_n, full_n), dtype=np.float32)

    for tz in range(tiles_z):
        for tx in range(tiles_x):
            p = runtime_dir / f"{tx}_{tz}.r16"
            if not p.exists():
                p = runtime_dir / f"tile_x{tx}_y{tz}.r16"
            raw = np.fromfile(p, dtype="<u2").reshape((samples, samples))
            z0 = tz * step
            x0 = tx * step
            full_h[z0 : z0 + samples, x0 : x0 + samples] = min_h + raw.astype(np.float32) * scale

    return full_h, manifest


# ---------------------------------------------------------------------------
# 2. Hydrology & Path Distance Fields
# ---------------------------------------------------------------------------
def lake_radius_analytical(theta: np.ndarray, radius: float) -> np.ndarray:
    def cove(angle: float, width: float) -> np.ndarray:
        return np.exp(-((np.sin((theta - angle) / 2.0) / width) ** 2))

    return radius * (
        1.0
        + 0.09 * np.sin(3.0 * theta + 0.4)
        + 0.06 * np.sin(5.0 * theta - 1.3)
        + 0.035 * np.sin(9.0 * theta)
        + 0.025 * np.sin(13.0 * theta + 0.8)
        - 0.18 * cove(2.25, 0.15)
        - 0.12 * cove(0.4, 0.12)
        - 0.10 * cove(4.6, 0.16)
        + 0.12 * cove(3.5, 0.20)
    )


def lake_signed_distance_analytical(
    x: np.ndarray, y_b: np.ndarray, cx: float, cy_b: float, radius: float
) -> np.ndarray:
    theta = np.arctan2(y_b - cy_b, x - cx)
    r = lake_radius_analytical(theta, radius)
    deriv = (lake_radius_analytical(theta + 0.001, radius) - lake_radius_analytical(theta - 0.001, radius)) / 0.002
    return ((np.hypot(x - cx, y_b - cy_b) - r) / np.sqrt(1.0 + (deriv / r) ** 2)).astype(np.float32)


def inlet_distance_analytical(x: np.ndarray, y_b: np.ndarray) -> np.ndarray:
    dx = x - 480.0
    dz = -y_b - 1504.0
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    along = (dx + dz) * inv_sqrt2
    across = (dx - dz) * inv_sqrt2
    station = np.clip(along, -24.0, 70.0)
    radius = 7.0 + 7.0 * smoothstep(-25.0, 30.0, station)
    bend = 1.6 * np.sin(station / 22.0)
    return (np.hypot(across - bend, along - station) - radius).astype(np.float32)


def compute_hydrology_fields(
    x_grid_2k: np.ndarray, z_grid_2k: np.ndarray, hydrology_data: dict
) -> tuple[np.ndarray, np.ndarray]:
    """Compute signed distance to water edge and local reference water elevation on 2048x2048 grid."""
    H, W = x_grid_2k.shape
    water_dist = np.full((H, W), 1e4, dtype=np.float32)
    water_y = np.full((H, W), 180.0, dtype=np.float32)

    # Analytical lake signed distances (exact match with build_world.py where y_blender = -z_runtime)
    y_b = -z_grid_2k
    canyon_2900 = float(1850.0 + 450.0 * math.sin(2900.0 / 600.0) + 140.0 * math.sin(2900.0 / 265.0))
    lakes_spec = [
        ("Spiegelsee", 900.0, -1900.0, 520.0, 180.0),
        ("Hirschweiher", -600.0, -2400.0, 210.0, 200.0),
        ("Aschenauge", canyon_2900, 2900.0, 175.0, 380.0),
    ]
    for name, cx, cy_b, r, level in lakes_spec:
        d = lake_signed_distance_analytical(x_grid_2k, y_b, cx, cy_b, r)
        if name == "Spiegelsee":
            d_inlet = inlet_distance_analytical(x_grid_2k, y_b)
            blend = np.maximum(1.0 - np.abs(d - d_inlet) / 4.0, 0.0)
            d = np.minimum(d, d_inlet) - blend * blend
        closer = d < water_dist
        water_dist = np.where(closer, d, water_dist)
        water_y = np.where(closer, np.float32(level), water_y)

    # River polyline segments (runtime coordinates [x, z, water_y, width])
    min_x0 = float(x_grid_2k[0, 0])
    min_z0 = float(z_grid_2k[0, 0])
    spacing = float(x_grid_2k[0, 1] - x_grid_2k[0, 0])  # 4.0 m on 2k grid
    pad = 260.0

    for river in hydrology_data.get("rivers", []):
        pts = np.asarray(river["polyline"], dtype=np.float32)
        for i in range(len(pts) - 1):
            a = pts[i]
            b = pts[i + 1]
            half_w = 0.5 * max(float(a[3]), float(b[3]))
            x_lo = max(0, int(math.floor((min(a[0], b[0]) - half_w - pad - min_x0) / spacing)))
            x_hi = min(W, int(math.ceil((max(a[0], b[0]) + half_w + pad - min_x0) / spacing)) + 1)
            z_lo = max(0, int(math.floor((min(a[1], b[1]) - half_w - pad - min_z0) / spacing)))
            z_hi = min(H, int(math.ceil((max(a[1], b[1]) + half_w + pad - min_z0) / spacing)) + 1)
            if x_lo >= x_hi or z_lo >= z_hi:
                continue

            xx = x_grid_2k[z_lo:z_hi, x_lo:x_hi]
            zz = z_grid_2k[z_lo:z_hi, x_lo:x_hi]
            dx = float(b[0] - a[0])
            dz = float(b[1] - a[1])
            denom = max(dx * dx + dz * dz, 1e-6)
            t = np.clip(((xx - a[0]) * dx + (zz - a[1]) * dz) / denom, 0.0, 1.0)
            seg_w = a[3] + t * (b[3] - a[3])
            seg_y = a[2] + t * (b[2] - a[2])
            d = np.hypot(xx - a[0] - t * dx, zz - a[1] - t * dz) - 0.5 * seg_w

            cur_d = water_dist[z_lo:z_hi, x_lo:x_hi]
            cur_y = water_y[z_lo:z_hi, x_lo:x_hi]
            closer = d < cur_d
            water_dist[z_lo:z_hi, x_lo:x_hi] = np.where(closer, d, cur_d)
            water_y[z_lo:z_hi, x_lo:x_hi] = np.where(closer, seg_y, cur_y)

    return water_dist, water_y


def compute_path_distance(x_axis_4k: np.ndarray, z_axis_4k: np.ndarray, paths: list[dict]) -> np.ndarray:
    """Compute signed distance (m) to paths on the 4096x4096 grid (fast bbox-clipped)."""
    H = len(z_axis_4k)
    W = len(x_axis_4k)
    path_dist = np.full((H, W), 1000.0, dtype=np.float32)
    min_x0 = float(x_axis_4k[0])
    min_z0 = float(z_axis_4k[0])
    spacing = float(x_axis_4k[1] - x_axis_4k[0])  # 2.0 m
    pad = 24.0

    for path in paths:
        width = float(path.get("width", 2.4))
        poly = np.asarray(path.get("polyline", []), dtype=np.float32)
        for i in range(len(poly) - 1):
            a = poly[i]
            b = poly[i + 1]
            x_lo = max(0, int(math.floor((min(a[0], b[0]) - pad - min_x0) / spacing)))
            x_hi = min(W, int(math.ceil((max(a[0], b[0]) + pad - min_x0) / spacing)) + 1)
            z_lo = max(0, int(math.floor((min(a[1], b[1]) - pad - min_z0) / spacing)))
            z_hi = min(H, int(math.ceil((max(a[1], b[1]) + pad - min_z0) / spacing)) + 1)
            if x_lo >= x_hi or z_lo >= z_hi:
                continue
            xx = x_axis_4k[None, x_lo:x_hi]
            zz = z_axis_4k[z_lo:z_hi, None]
            dx = float(b[0] - a[0])
            dz = float(b[1] - a[1])
            denom = max(dx * dx + dz * dz, 1e-6)
            t = np.clip(((xx - a[0]) * dx + (zz - a[1]) * dz) / denom, 0.0, 1.0)
            d = np.hypot(xx - a[0] - t * dx, zz - a[1] - t * dz) - 0.5 * width
            path_dist[z_lo:z_hi, x_lo:x_hi] = np.minimum(path_dist[z_lo:z_hi, x_lo:x_hi], d.astype(np.float32))

    return path_dist


# ---------------------------------------------------------------------------
# 3. Horizon / Sky-View AO & Canopy Shadow Mask
# ---------------------------------------------------------------------------
def compute_horizon_ao(h_2k: np.ndarray, pixel_size_m: float = 4.0) -> np.ndarray:
    """March 8 azimuth directions up to ~128 m across the heightfield to compute
    large-scale terrain sky-view / horizon ambient occlusion.
    """
    H, W = h_2k.shape
    dirs = [
        (1, 0),
        (1, 1),
        (0, 1),
        (-1, 1),
        (-1, 0),
        (-1, -1),
        (0, -1),
        (1, -1),
    ]
    step_pixels = [1, 2, 3, 5, 7, 10, 14, 19, 25, 32]  # up to 32 * 4m = 128m
    sun_xz = np.array([SUN_DIR[0], SUN_DIR[2]], dtype=np.float32)
    sun_xz /= max(float(np.linalg.norm(sun_xz)), 1e-6)

    total_occ = np.zeros((H, W), dtype=np.float32)
    total_weight = 0.0

    for dx, dz in dirs:
        dir_len = math.hypot(dx, dz)
        unit_dir = np.array([dx / dir_len, dz / dir_len], dtype=np.float32)
        # Weight directions slightly toward the sun so cliff bases facing away from sun get deeper shadow
        sun_align = max(0.0, float(np.dot(unit_dir, sun_xz)))
        w_dir = 1.0 + 0.45 * sun_align

        max_tan = np.zeros((H, W), dtype=np.float32)
        for sp in step_pixels:
            dist_m = sp * pixel_size_m * dir_len
            # Sample h at (x + sp*dx, z + sp*dz) with edge clamping
            ix = np.clip(np.arange(W) + sp * dx, 0, W - 1)
            iz = np.clip(np.arange(H) + sp * dz, 0, H - 1)
            shifted = h_2k[iz[:, None], ix[None, :]]
            # Attenuate slightly at far distances (>80 m) so broad basins don't over-darken
            atten = max(0.35, 1.0 - (dist_m / 180.0) ** 2)
            tan_elev = ((shifted - h_2k) / dist_m) * atten
            max_tan = np.maximum(max_tan, tan_elev)

        sin_h = max_tan / np.sqrt(1.0 + max_tan * max_tan)
        total_occ += w_dir * np.power(np.clip(sin_h, 0.0, 1.0), 1.15)
        total_weight += w_dir

    mean_occ = total_occ / total_weight
    sky_ao = np.clip(1.0 - 0.88 * mean_occ, 0.20, 1.0).astype(np.float32)
    return sky_ao


def compute_canopy_shadow(
    x_axis_4k: np.ndarray,
    z_axis_4k: np.ndarray,
    x_grid_2k: np.ndarray,
    z_grid_2k: np.ndarray,
    slope_deg_4k: np.ndarray,
    above_water_4k: np.ndarray,
    placements_data: dict,
    slice_bounds: dict,
) -> np.ndarray:
    """Compute canopy shadow factor in [0, 1] (1 = open sky, <1 = darkened under tree crowns)."""
    H, W = len(z_axis_4k), len(x_axis_4k)
    canopy_dark = np.zeros((H, W), dtype=np.float32)
    min_x0 = float(x_axis_4k[0])
    min_z0 = float(z_axis_4k[0])
    spacing = float(x_axis_4k[1] - x_axis_4k[0])  # 2.0 m

    # Sun shadow offset on the ground for an average ~8-11m high crown
    sun_offset_x = -float(SUN_DIR[0]) / max(float(SUN_DIR[1]), 0.3) * 3.2
    sun_offset_z = -float(SUN_DIR[2]) / max(float(SUN_DIR[1]), 0.3) * 3.2

    def stamp_crown(cx: float, cz: float, radius: float, strength: float):
        for ox, oz, mult in ((0.0, 0.0, 0.65), (sun_offset_x, sun_offset_z, 0.55)):
            px = cx + ox * (radius / 7.0)
            pz = cz + oz * (radius / 7.0)
            r = radius * (1.05 if mult < 0.6 else 0.95)
            x_lo = max(0, int(math.floor((px - r - min_x0) / spacing)))
            x_hi = min(W, int(math.ceil((px + r - min_x0) / spacing)) + 1)
            z_lo = max(0, int(math.floor((pz - r - min_z0) / spacing)))
            z_hi = min(H, int(math.ceil((pz + r - min_z0) / spacing)) + 1)
            if x_lo >= x_hi or z_lo >= z_hi:
                continue
            xx = x_axis_4k[None, x_lo:x_hi]
            zz = z_axis_4k[z_lo:z_hi, None]
            d2 = ((xx - px) ** 2 + (zz - pz) ** 2) / max(r * r, 1e-4)
            falloff = np.clip(1.0 - d2, 0.0, 1.0) ** 1.6
            patch = canopy_dark[z_lo:z_hi, x_lo:x_hi]
            canopy_dark[z_lo:z_hi, x_lo:x_hi] = np.maximum(patch, (falloff * strength * mult).astype(np.float32))

    for entry in placements_data.get("placements", []):
        asset = str(entry.get("asset", ""))
        is_tree = asset.startswith("tree_") or asset.startswith("trunk_")
        is_shrub = asset.startswith("shrub_")
        if not (is_tree or is_shrub):
            continue

        if "scatter" not in entry:
            sc = float(entry.get("scale", 1.0))
            rad = (7.2 if is_tree else 2.6) * sc
            strg = 0.42 if is_tree else 0.16
            stamp_crown(float(entry["x"]), float(entry["z"]), rad, strg)
        else:
            s = entry["scatter"]
            cnt = int(s.get("count", 1))
            sc_range = s.get("scale", [1.0, 1.0])
            mean_sc = 0.5 * (float(sc_range[0]) + float(sc_range[1]))
            poly = s.get("polygon")
            rect = s.get("rect")
            if poly:
                pts = np.asarray(poly, dtype=np.float32)
                cx = float(pts[:, 0].mean())
                cz = float(pts[:, 1].mean())
                poly_rad = float(np.hypot(pts[:, 0] - cx, pts[:, 1] - cz).max())
            elif rect:
                cx = 0.5 * (float(rect["minX"]) + float(rect["maxX"]))
                cz = 0.5 * (float(rect["minZ"]) + float(rect["maxZ"]))
                poly_rad = 0.5 * math.hypot(
                    float(rect["maxX"]) - float(rect["minX"]),
                    float(rect["maxZ"]) - float(rect["minZ"]),
                )
            else:
                continue

            if is_tree and cnt == 1:
                stamp_crown(cx, cz, 7.2 * mean_sc, 0.44)
            elif is_tree:
                stamp_crown(cx, cz, max(poly_rad, 7.5 * mean_sc), 0.42)
            elif is_shrub:
                stamp_crown(cx, cz, max(poly_rad * 0.85, 2.8 * mean_sc), 0.18)

    # Also add world-wide procedural forest canopy shadow outside the 1x1 km hand-dressed slice
    # (matching build_world.py's forest distribution so distant 8x8 km woods have macro canopy shadows)
    y_b_2k = -z_grid_2k
    slope_2k = downsample_2x(slope_deg_4k)
    above_2k = downsample_2x(above_water_4k)
    forest_macro = smoothstep(
        0.0,
        1.0,
        (value_noise(x_grid_2k, y_b_2k, 400.0, 62) + 0.12) * 3.0
        + value_noise(x_grid_2k, y_b_2k, 65.0, 63) * 0.65,
    )
    forest_macro *= 1.0 - smoothstep(18.0, 31.0, slope_2k)
    forest_macro *= smoothstep(2.5, 10.0, above_2k)
    crown_clumps = smoothstep(
        0.25,
        0.78,
        0.5 + 0.35 * value_noise(x_grid_2k, y_b_2k, 22.0, 64) + 0.20 * value_noise(x_grid_2k, y_b_2k, 11.0, 68),
    )
    proc_canopy_2k = forest_macro * crown_clumps * 0.36

    # Smoothly mask out procedural canopy inside the 1x1 km Spiegelsee slice where exact placements govern
    sb_min_x = float(slice_bounds.get("minX", -100.0))
    sb_max_x = float(slice_bounds.get("maxX", 900.0))
    sb_min_z = float(slice_bounds.get("minZ", 1100.0))
    sb_max_z = float(slice_bounds.get("maxZ", 2100.0))
    in_slice_x = smoothstep(sb_min_x - 80.0, sb_min_x + 20.0, x_grid_2k) * (
        1.0 - smoothstep(sb_max_x - 20.0, sb_max_x + 80.0, x_grid_2k)
    )
    in_slice_z = smoothstep(sb_min_z - 80.0, sb_min_z + 20.0, z_grid_2k) * (
        1.0 - smoothstep(sb_max_z - 20.0, sb_max_z + 80.0, z_grid_2k)
    )
    in_slice_2k = in_slice_x * in_slice_z
    proc_canopy_2k *= 1.0 - 0.85 * in_slice_2k

    proc_canopy_4k = upsample_2x_bilinear(proc_canopy_2k, (H, W))
    canopy_dark = np.maximum(canopy_dark, proc_canopy_4k)
    canopy_ao = np.clip(1.0 - canopy_dark, 0.48, 1.0).astype(np.float32)
    return canopy_ao


# ---------------------------------------------------------------------------
# 4. Contact Sheet Preview
# ---------------------------------------------------------------------------
def build_preview_sheet(
    preview_path: Path,
    color_srgb_4k: np.ndarray,
    ao_4k: np.ndarray,
    weights_a_2k: np.ndarray,
    weights_b_2k: np.ndarray,
    grass_2k: np.ndarray,
    slice_bounds: dict,
) -> None:
    """Create a labeled 2x4 visual diagnostic contact sheet:
    Top row: Full 8x8 km World (Macro Color, Combined Sky+Canopy AO, Layer Weights RGB, Grass Density/Dryness)
    Bottom row: 1x1 km Spiegelsee Slice Zoom ([-100, 900] x [1100, 2100])
    """
    panel_size = 512
    pad = 20
    header_h = 44
    cols = 4
    rows = 2
    sheet_w = cols * panel_size + (cols + 1) * pad
    sheet_h = rows * (panel_size + header_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (20, 22, 26))
    draw = ImageDraw.Draw(sheet)

    def to_uint8_rgb(arr: np.ndarray) -> np.ndarray:
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        return np.clip(np.round(arr * 255.0), 0, 255).astype(np.uint8)

    # Visualization of layer weights:
    # Green = grass/moss, Ochre = dry grass, Brown = soil, Sand = sand/wet sand, Chalk/White = rock
    w_grass = weights_a_2k[..., 0]
    w_dry = weights_a_2k[..., 1]
    w_soil = weights_a_2k[..., 2]
    w_moss = weights_a_2k[..., 3]
    w_sand = weights_b_2k[..., 0]
    w_wet = weights_b_2k[..., 1]
    w_chalk = weights_b_2k[..., 2]
    w_strata = weights_b_2k[..., 3]

    weights_vis_2k = (
        w_grass[..., None] * np.array([0.28, 0.72, 0.25], dtype=np.float32)
        + w_dry[..., None] * np.array([0.78, 0.68, 0.22], dtype=np.float32)
        + w_soil[..., None] * np.array([0.52, 0.34, 0.20], dtype=np.float32)
        + w_moss[..., None] * np.array([0.12, 0.42, 0.22], dtype=np.float32)
        + w_sand[..., None] * np.array([0.92, 0.82, 0.52], dtype=np.float32)
        + w_wet[..., None] * np.array([0.35, 0.58, 0.68], dtype=np.float32)
        + (w_chalk + w_strata)[..., None] * np.array([0.86, 0.84, 0.82], dtype=np.float32)
    )

    # Visualization of grass map: R=density, G=height, B=dry_mix
    grass_vis_2k = np.stack(
        [
            grass_2k[..., 0] * (0.45 + 0.55 * grass_2k[..., 2]),
            grass_2k[..., 0] * (0.65 + 0.35 * grass_2k[..., 1]),
            grass_2k[..., 0] * 0.25 + (1.0 - grass_2k[..., 3]) * 0.35,
        ],
        axis=-1,
    )

    # Slice pixel coordinates in 4k (2m/px) and 2k (4m/px)
    min_x, max_x = float(slice_bounds["minX"]), float(slice_bounds["maxX"])
    min_z, max_z = float(slice_bounds["minZ"]), float(slice_bounds["maxZ"])

    def crop_world(arr: np.ndarray, x0: float, x1: float, z0: float, z1: float) -> np.ndarray:
        H, W = arr.shape[:2]
        c0 = max(0, int(round((x0 + 4096.0) / 8192.0 * W)))
        c1 = min(W, int(round((x1 + 4096.0) / 8192.0 * W)))
        r0 = max(0, int(round((z0 + 4096.0) / 8192.0 * H)))
        r1 = min(H, int(round((z1 + 4096.0) / 8192.0 * H)))
        return arr[r0:r1, c0:c1]

    panels = [
        # Row 0: Full 8x8 km World
        ("World 8x8km: Macro Color (sRGB)", to_uint8_rgb(color_srgb_4k)),
        ("World 8x8km: Sky Horizon + Canopy AO", to_uint8_rgb(ao_4k)),
        ("World 8x8km: Layer Weights (Grn/Dry/Sand/Rock)", to_uint8_rgb(weights_vis_2k)),
        ("World 8x8km: Grass Density & Height", to_uint8_rgb(grass_vis_2k)),
        # Row 1: 1x1 km Spiegelsee Slice ([-100, 900] x [1100, 2100])
        (
            "Spiegelsee 1x1km Slice: Macro Color",
            to_uint8_rgb(crop_world(color_srgb_4k, min_x, max_x, min_z, max_z)),
        ),
        (
            "Spiegelsee 1x1km Slice: Sky + Canopy AO",
            to_uint8_rgb(crop_world(ao_4k, min_x, max_x, min_z, max_z)),
        ),
        (
            "Spiegelsee 1x1km Slice: Layer Weights",
            to_uint8_rgb(crop_world(weights_vis_2k, min_x, max_x, min_z, max_z)),
        ),
        (
            "Spiegelsee 1x1km Slice: Grass Density (R) / Dry (B)",
            to_uint8_rgb(crop_world(grass_vis_2k, min_x, max_x, min_z, max_z)),
        ),
    ]

    for idx, (title, img_arr) in enumerate(panels):
        r = idx // cols
        c = idx % cols
        x0 = pad + c * (panel_size + pad)
        y0 = pad + r * (panel_size + header_h + pad)
        draw.text((x0 + 4, y0 + 12), title, fill=(235, 235, 240))
        im = Image.fromarray(img_arr, mode="RGB").resize((panel_size, panel_size), Image.LANCZOS)
        # Draw 1x1km slice box on full-world panels
        if r == 0:
            im_draw = ImageDraw.Draw(im)
            bx0 = int(round((min_x + 4096.0) / 8192.0 * panel_size))
            bx1 = int(round((max_x + 4096.0) / 8192.0 * panel_size))
            bz0 = int(round((min_z + 4096.0) / 8192.0 * panel_size))
            bz1 = int(round((max_z + 4096.0) / 8192.0 * panel_size))
            im_draw.rectangle([bx0, bz0, bx1, bz1], outline=(255, 90, 90), width=2)
        sheet.paste(im, (x0, y0 + header_h))

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(preview_path, "JPEG", quality=92)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    t0 = time.monotonic()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=PUBLIC_GROUND_DIR)
    ap.add_argument("--preview", type=Path, default=DEFAULT_PREVIEW_PATH)
    args = ap.parse_args(argv)

    print("[1/6] Loading 16x16 R16 heightfield tiles...", flush=True)
    full_h, manifest = load_world_heightfield(RUNTIME_DIR)
    # 4096x4096 cell centers (each 2x2 m pixel covers [-4096+2*i, -4096+2*(i+1)])
    h_4k = (0.25 * (full_h[:-1, :-1] + full_h[:-1, 1:] + full_h[1:, :-1] + full_h[1:, 1:])).astype(np.float32)
    dh_dx = (0.25 * ((full_h[:-1, 1:] - full_h[:-1, :-1]) + (full_h[1:, 1:] - full_h[1:, :-1]))).astype(np.float32)
    dh_dz = (0.25 * ((full_h[1:, :-1] - full_h[:-1, :-1]) + (full_h[1:, 1:] - full_h[:-1, 1:]))).astype(np.float32)

    grad_mag = np.hypot(dh_dx, dh_dz)
    slope_rad = np.arctan(grad_mag)
    slope_deg_4k = np.degrees(slope_rad).astype(np.float32)
    inv_len = 1.0 / np.sqrt(1.0 + grad_mag * grad_mag)
    nx_4k = (-dh_dx * inv_len).astype(np.float32)
    ny_4k = inv_len.astype(np.float32)
    nz_4k = (-dh_dz * inv_len).astype(np.float32)

    # Coordinate axes for 4096x4096 (2 m spacing) and 2048x2048 (4 m spacing)
    axis_4k = np.linspace(-4095.0, 4095.0, 4096, dtype=np.float32)
    axis_2k = np.linspace(-4094.0, 4094.0, 2048, dtype=np.float32)
    x_grid_2k, z_grid_2k = np.meshgrid(axis_2k, axis_2k)
    h_2k = downsample_2x(h_4k)

    print("[2/6] Computing multi-scale curvature, hydrology & path masks...", flush=True)
    # Multi-scale Laplacian curvature (hollow > 0 in concave gullies/valleys; ridge > 0 on convex crests)
    lap_fine_4k = h_4k - box_blur_2d(h_4k, radius=3, passes=2)  # ~12 m scale
    lap_meso_2k = h_2k - box_blur_2d(h_2k, radius=7, passes=2)  # ~56 m scale
    lap_macro_2k = h_2k - box_blur_2d(h_2k, radius=20, passes=2)  # ~160 m scale
    lap_meso_4k = upsample_2x_bilinear(lap_meso_2k, (4096, 4096))
    lap_macro_4k = upsample_2x_bilinear(lap_macro_2k, (4096, 4096))

    hollow_4k = np.clip(
        -(0.45 * lap_fine_4k / 1.4 + 0.35 * lap_meso_4k / 4.8 + 0.20 * lap_macro_4k / 14.0),
        0.0,
        1.0,
    ).astype(np.float32)
    ridge_4k = np.clip(
        +(0.35 * lap_fine_4k / 1.4 + 0.40 * lap_meso_4k / 4.8 + 0.25 * lap_macro_4k / 14.0),
        0.0,
        1.0,
    ).astype(np.float32)

    hydrology_path = WORLD_DIR / "hydrology.json"
    if not hydrology_path.exists():
        hydrology_path = WORLD_DIR / "hydrology" / "hydrology.json"
    hydrology_data = json.loads(hydrology_path.read_text(encoding="utf-8"))

    water_dist_2k, water_y_2k = compute_hydrology_fields(x_grid_2k, z_grid_2k, hydrology_data)
    water_dist_4k = upsample_2x_bilinear(water_dist_2k, (4096, 4096))
    water_y_4k = upsample_2x_bilinear(water_y_2k, (4096, 4096))
    above_water_4k = (h_4k - water_y_4k).astype(np.float32)

    slice_data = json.loads((WORLD_DIR / "slice.json").read_text(encoding="utf-8"))
    paths_list = list(slice_data.get("paths", []))
    extra_paths_file = WORLD_DIR / "paths" / "paths.json"
    if extra_paths_file.exists():
        extra = json.loads(extra_paths_file.read_text(encoding="utf-8"))
        paths_list.extend(extra.get("paths", extra if isinstance(extra, list) else []))

    path_dist_4k = compute_path_distance(axis_4k, axis_4k, paths_list)

    print("[3/6] Computing 8-azimuth horizon AO & tree canopy shadow mask...", flush=True)
    sky_ao_2k = compute_horizon_ao(h_2k, pixel_size_m=4.0)
    sky_ao_4k = upsample_2x_bilinear(sky_ao_2k, (4096, 4096))
    # Combine macro horizon AO with fine-scale gully cavity AO
    cavity_ao_4k = np.clip(1.0 - 0.30 * smoothstep(0.08, 0.85, hollow_4k), 0.65, 1.0)
    terrain_ao_4k = np.clip(sky_ao_4k * cavity_ao_4k, 0.18, 1.0).astype(np.float32)

    placements_data = json.loads((WORLD_DIR / "placements.json").read_text(encoding="utf-8"))
    canopy_ao_4k = compute_canopy_shadow(
        axis_4k,
        axis_4k,
        x_grid_2k,
        z_grid_2k,
        slope_deg_4k,
        above_water_4k,
        placements_data,
        slice_data.get("bounds", {"minX": -100, "minZ": 1100, "maxX": 900, "maxZ": 2100}),
    )
    combined_ao_4k = np.clip(terrain_ao_4k * canopy_ao_4k, 0.14, 1.0).astype(np.float32)

    print("[4/6] Evaluating biome moisture, layer weights & palette-aligned macro tint...", flush=True)
    # Multi-scale organic variation computed on 2k and upsampled + fine 4k detail
    y_b_2k = -z_grid_2k
    noise_macro_2k = 0.5 + 0.5 * (
        0.55 * value_noise(x_grid_2k, y_b_2k, 240.0, 101)
        + 0.30 * value_noise(x_grid_2k, y_b_2k, 85.0, 102)
        + 0.15 * value_noise(x_grid_2k, y_b_2k, 32.0, 103)
    )
    noise_patches_2k = 0.5 + 0.5 * (
        0.60 * value_noise(x_grid_2k, y_b_2k, 52.0, 104)
        + 0.40 * value_noise(x_grid_2k, y_b_2k, 18.0, 105)
    )
    noise_strata_2k = value_noise(x_grid_2k, y_b_2k, 110.0, 106)
    noise_macro_4k = upsample_2x_bilinear(noise_macro_2k, (4096, 4096))
    noise_patches_4k = upsample_2x_bilinear(noise_patches_2k, (4096, 4096))
    noise_strata_4k = upsample_2x_bilinear(noise_strata_2k, (4096, 4096))

    sunny_4k = np.clip(
        nx_4k * float(SUN_DIR[0]) + ny_4k * float(SUN_DIR[1]) + nz_4k * float(SUN_DIR[2]),
        0.0,
        1.0,
    )
    north_shade_4k = np.clip(-nz_4k, 0.0, 1.0)

    # Moisture proxy: high near water, in concave hollows, under tree canopies, and on north slopes;
    # low on high sun-baked ridges and steep south-facing shoulders.
    near_water_moist = (1.0 - smoothstep(0.0, 85.0, water_dist_4k)) * (1.0 - smoothstep(1.0, 32.0, above_water_4k))
    canopy_moist = 1.0 - canopy_ao_4k
    moisture_4k = np.clip(
        0.48
        + 0.36 * near_water_moist
        + 0.32 * hollow_4k
        + 0.42 * canopy_moist
        + 0.16 * north_shade_4k
        - 0.30 * ridge_4k
        - 0.16 * smoothstep(20.0, 180.0, above_water_4k)
        - 0.10 * sunny_4k
        + 0.24 * (noise_macro_4k - 0.5)
        + 0.16 * (noise_patches_4k - 0.5),
        0.0,
        1.0,
    ).astype(np.float32)

    # Dry grass mix factor (0 = lush grass_green, 1 = golden grass_dry)
    dry_mix_4k = np.clip(
        smoothstep(0.68, 0.22, moisture_4k) * 0.78
        + smoothstep(5.0, 26.0, slope_deg_4k) * 0.24
        + (noise_patches_4k - 0.5) * 0.28,
        0.0,
        1.0,
    ).astype(np.float32)

    # Rock mask: steep slopes >= 28..36 deg transition to chalk/strata rock
    rock_mask_4k = smoothstep(26.5, 36.5, slope_deg_4k + (noise_patches_4k - 0.5) * 3.5)
    # Stratified bands along world elevation
    layer_h = h_4k + 38.0 * noise_strata_4k
    strata_band_4k = (0.5 + 0.5 * np.sin(layer_h / 6.5 + noise_patches_4k * 1.8)).astype(np.float32)
    strata_frac_4k = np.clip(
        0.25 + 0.55 * strata_band_4k * smoothstep(28.0, 48.0, slope_deg_4k),
        0.0,
        1.0,
    ).astype(np.float32)

    # Shore & beach masks (near lakes and rivers, on gentle-to-moderate slopes)
    shore_corridor = (1.0 - smoothstep(10.0, 42.0, water_dist_4k)) * (1.0 - smoothstep(20.0, 30.0, slope_deg_4k))
    wet_shore_4k = (
        shore_corridor
        * (1.0 - smoothstep(-2.2, -0.35, above_water_4k))  # wait: below -2.2 is deep water
        * (1.0 - smoothstep(0.15, 1.15, above_water_4k))
    )
    # Explicitly cover [-1.8m, +1.0m] around waterline for wet shore/sand_wet
    wet_shore_4k = (
        (1.0 - smoothstep(14.0, 45.0, water_dist_4k))
        * smoothstep(-2.2, -0.2, above_water_4k)
        * (1.0 - smoothstep(0.25, 1.25, above_water_4k))
        * (1.0 - smoothstep(22.0, 32.0, slope_deg_4k))
    ).astype(np.float32)

    dry_beach_4k = (
        (1.0 - smoothstep(8.0, 34.0, water_dist_4k + (noise_patches_4k - 0.5) * 10.0))
        * smoothstep(0.15, 0.95, above_water_4k)
        * (1.0 - smoothstep(2.4, 5.8, above_water_4k + (noise_macro_4k - 0.5) * 1.4))
        * (1.0 - smoothstep(16.0, 25.0, slope_deg_4k))
    ).astype(np.float32)

    # Underwater lake/river bed mask
    underwater_4k = (
        smoothstep(0.25, -0.45, above_water_4k) * (1.0 - smoothstep(12.0, 35.0, water_dist_4k))
    ).astype(np.float32)

    # Footpath masks (above water)
    dry_land = smoothstep(-0.05, 0.55, above_water_4k)
    path_fill_4k = (1.0 - smoothstep(-0.35, 0.85, path_dist_4k)) * dry_land
    path_edge_4k = (1.0 - smoothstep(0.2, 2.5, path_dist_4k)) * (1.0 - path_fill_4k * 0.75) * dry_land

    # Bare soil on mid-slopes (14..28 deg) and path edges
    slope_soil_4k = (
        smoothstep(11.0, 24.0, slope_deg_4k)
        * (1.0 - rock_mask_4k)
        * (0.42 + 0.35 * (1.0 - moisture_4k))
    )
    soil_raw_4k = np.clip(np.maximum(slope_soil_4k, path_edge_4k * 0.85), 0.0, 1.0)

    # Moss in shaded hollows, north slopes, and under dense tree canopies
    moss_raw_4k = (
        smoothstep(0.54, 0.88, moisture_4k + 0.25 * hollow_4k + 0.25 * (1.0 - canopy_ao_4k))
        * (1.0 - rock_mask_4k * 0.7)
        * (1.0 - dry_beach_4k)
        * (1.0 - path_fill_4k)
        * dry_land
        * 0.62
    ).astype(np.float32)

    # Combine into 8 mutually consistent layer weights:
    # A: (R: grass, G: grass_dry, B: soil, A: moss)
    # B: (R: sand, G: sand_wet, B: chalk_rock, A: strata_rock)
    w_chalk_4k = rock_mask_4k * (1.0 - strata_frac_4k)
    w_strata_4k = rock_mask_4k * strata_frac_4k

    rem_after_rock = np.clip(1.0 - rock_mask_4k, 0.0, 1.0)
    w_sand_wet_4k = rem_after_rock * np.clip(wet_shore_4k + underwater_4k * 0.85, 0.0, 1.0)
    rem_after_wet = np.clip(rem_after_rock - w_sand_wet_4k, 0.0, 1.0)

    w_sand_4k = rem_after_wet * np.clip(np.maximum(dry_beach_4k, path_fill_4k), 0.0, 1.0)
    rem_veg_soil = np.clip(rem_after_wet - w_sand_4k, 0.0, 1.0)

    w_soil_4k = rem_veg_soil * soil_raw_4k
    rem_veg = np.clip(rem_veg_soil - w_soil_4k, 0.0, 1.0)

    w_moss_4k = rem_veg * moss_raw_4k
    rem_grass = np.clip(rem_veg - w_moss_4k, 0.0, 1.0)

    w_grass_dry_4k = rem_grass * dry_mix_4k
    w_grass_4k = rem_grass * (1.0 - dry_mix_4k)

    # Normalize weights so all 8 sum to 1.0 everywhere
    w_sum = (
        w_grass_4k
        + w_grass_dry_4k
        + w_soil_4k
        + w_moss_4k
        + w_sand_4k
        + w_sand_wet_4k
        + w_chalk_4k
        + w_strata_4k
    )
    inv_w_sum = 1.0 / np.maximum(w_sum, 1e-6)
    w_grass_4k *= inv_w_sum
    w_grass_dry_4k *= inv_w_sum
    w_soil_4k *= inv_w_sum
    w_moss_4k *= inv_w_sum
    w_sand_4k *= inv_w_sum
    w_sand_wet_4k *= inv_w_sum
    w_chalk_4k *= inv_w_sum
    w_strata_4k *= inv_w_sum

    # Palette linear RGB colors from art/palette.json
    palette = json.loads((ROOT / "art" / "palette.json").read_text(encoding="utf-8"))["colors"]
    c_grass_lit = np.array(palette["grass_green"]["linear_rgb"], dtype=np.float32)  # #696F44
    c_grass_dry = np.array(palette["grass_dry"]["linear_rgb"], dtype=np.float32)  # #635C30
    c_grass_shadow = np.array(palette["leaf_green"]["linear_rgb"], dtype=np.float32)  # #313C1D
    c_moss = np.array(palette["moss"]["linear_rgb"], dtype=np.float32)  # #3D4C2B
    c_soil = np.array(palette["soil"]["linear_rgb"], dtype=np.float32)  # #665548
    c_sand = np.array(palette["path_sand"]["linear_rgb"], dtype=np.float32)  # #B6A176
    c_shore_wet = 0.45 * np.array(palette["shore_wet"]["linear_rgb"], dtype=np.float32) + 0.55 * c_sand * 0.62
    c_chalk = np.array(palette["canyon_chalk"]["linear_rgb"], dtype=np.float32)  # #BCB296
    c_strata = np.array(palette["canyon_strata"]["linear_rgb"], dtype=np.float32)  # #9B8E7E
    c_water_deep = np.array(palette["water_deep"]["linear_rgb"], dtype=np.float32)  # #254447

    # Subtle meadow hue/value variation so grass & ground share rich organic patches
    patch_tint = (0.90 + 0.20 * noise_patches_4k)[..., None]
    canopy_shade_mix = np.clip((1.0 - canopy_ao_4k) * 1.35 + hollow_4k * 0.25, 0.0, 0.75)[..., None]
    c_grass_varied = (
        c_grass_lit[None, None, :] * (1.0 - canopy_shade_mix) + c_grass_shadow[None, None, :] * canopy_shade_mix
    ) * patch_tint
    c_dry_varied = c_grass_dry[None, None, :] * (0.92 + 0.16 * noise_macro_4k)[..., None]
    c_moss_varied = (0.65 * c_moss + 0.35 * c_grass_shadow)[None, None, :] * (0.90 + 0.18 * noise_patches_4k)[..., None]

    macro_lin_4k = (
        w_grass_4k[..., None] * c_grass_varied
        + w_grass_dry_4k[..., None] * c_dry_varied
        + w_soil_4k[..., None] * c_soil[None, None, :] * patch_tint
        + w_moss_4k[..., None] * c_moss_varied
        + w_sand_4k[..., None] * c_sand[None, None, :] * (0.95 + 0.10 * noise_patches_4k)[..., None]
        + w_sand_wet_4k[..., None] * c_shore_wet[None, None, :]
        + w_chalk_4k[..., None] * c_chalk[None, None, :] * (0.94 + 0.12 * strata_band_4k)[..., None]
        + w_strata_4k[..., None] * c_strata[None, None, :] * (0.92 + 0.14 * noise_patches_4k)[..., None]
    )

    # Deepen underwater basin color slightly for realistic depth when seen through transparent water
    deep_water_mix = (smoothstep(-0.3, -4.5, above_water_4k) * underwater_4k)[..., None]
    macro_lin_4k = macro_lin_4k * (1.0 - 0.55 * deep_water_mix) + c_water_deep[None, None, :] * (0.55 * deep_water_mix)

    macro_srgb_4k = lin_to_srgb(np.clip(macro_lin_4k, 0.0, 1.0))

    # Phase 4.1 Runtime GPU Grass Map (2048x2048):
    # R: grass_density (0..1) — zero in water, on gravel paths, on steep rock >=32 deg, and on dry beach sand
    # G: grass_height_scale (0..1)
    # B: dry_mix (0..1)
    # A: canopy_shadow (0..1, 1 = open sky, <1 = under tree canopy/gorge shadow)
    not_water = smoothstep(0.12, 0.65, above_water_4k)
    not_path = smoothstep(0.55, 2.20, path_dist_4k)
    not_steep_rock = 1.0 - smoothstep(23.5, 31.5, slope_deg_4k)
    not_beach_sand = 1.0 - smoothstep(0.25, 0.70, dry_beach_4k + wet_shore_4k)

    grass_density_4k = (
        not_water
        * not_path
        * not_steep_rock
        * not_beach_sand
        * np.clip(0.82 + 0.18 * moisture_4k + 0.12 * (noise_patches_4k - 0.5) - 0.25 * soil_raw_4k, 0.0, 1.0)
    ).astype(np.float32)

    grass_height_4k = (
        grass_density_4k
        * np.clip(
            0.52 + 0.34 * moisture_4k + 0.18 * hollow_4k - 0.20 * ridge_4k + 0.15 * (noise_macro_4k - 0.5),
            0.18,
            1.0,
        )
    ).astype(np.float32)

    # Downsample weights and grass channels to 2048x2048
    weights_a_2k = np.stack(
        [
            downsample_2x(w_grass_4k),
            downsample_2x(w_grass_dry_4k),
            downsample_2x(w_soil_4k),
            downsample_2x(w_moss_4k),
        ],
        axis=-1,
    )
    weights_b_2k = np.stack(
        [
            downsample_2x(w_sand_4k),
            downsample_2x(w_sand_wet_4k),
            downsample_2x(w_chalk_4k),
            downsample_2x(w_strata_4k),
        ],
        axis=-1,
    )
    # Re-normalize 2k weights after downsampling
    sum_2k = np.maximum(weights_a_2k.sum(axis=-1, keepdims=True) + weights_b_2k.sum(axis=-1, keepdims=True), 1e-6)
    weights_a_2k = np.clip(weights_a_2k / sum_2k, 0.0, 1.0)
    weights_b_2k = np.clip(weights_b_2k / sum_2k, 0.0, 1.0)

    grass_2k = np.stack(
        [
            np.clip(downsample_2x(grass_density_4k), 0.0, 1.0),
            np.clip(downsample_2x(grass_height_4k), 0.0, 1.0),
            np.clip(downsample_2x(dry_mix_4k), 0.0, 1.0),
            np.clip(downsample_2x(combined_ao_4k), 0.0, 1.0),
        ],
        axis=-1,
    )
    # Enforce hard zero on grass_density in water, on paths, and on steep rock >= 32 deg at 2k resolution
    above_2k = downsample_2x(above_water_4k)
    path_2k = np.minimum.reduce(
        [path_dist_4k[0::2, 0::2], path_dist_4k[1::2, 0::2], path_dist_4k[0::2, 1::2], path_dist_4k[1::2, 1::2]]
    )
    slope_2k = downsample_2x(slope_deg_4k)
    grass_2k[..., 0] = np.where((above_2k <= 0.12) | (path_2k <= 0.45) | (slope_2k >= 32.0), 0.0, grass_2k[..., 0])

    print("[5/6] Saving WebP macro textures and macro.json...", flush=True)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    def save_rgba_webp(arr_01: np.ndarray, path: Path, quality: int = 92) -> int:
        u8 = np.clip(np.round(arr_01 * 255.0), 0, 255).astype(np.uint8)
        im = Image.fromarray(u8, mode="RGBA")
        im.save(path, "WEBP", quality=quality, method=4)
        return path.stat().st_size

    color_ao_4k = np.concatenate([macro_srgb_4k, combined_ao_4k[..., None]], axis=-1)
    sz_color_ao = save_rgba_webp(color_ao_4k, out_dir / "macro_color_ao.webp", quality=92)
    sz_weights_a = save_rgba_webp(weights_a_2k, out_dir / "macro_weights_a.webp", quality=90)
    sz_weights_b = save_rgba_webp(weights_b_2k, out_dir / "macro_weights_b.webp", quality=90)
    sz_grass = save_rgba_webp(grass_2k, out_dir / "macro_grass.webp", quality=90)

    # Compute summary stats for verification
    slice_bounds = slice_data.get("bounds", {"minX": -100, "minZ": 1100, "maxX": 900, "maxZ": 2100})
    meta = {
        "version": 1,
        "bounds": {
            "minX": -4096,
            "maxX": 4096,
            "minZ": -4096,
            "maxZ": 4096,
            "widthMetres": 8192,
            "heightMetres": 8192,
        },
        "coordinate_convention": {
            "axes": "Runtime: X east (-4096..4096), Y up, Z south (-4096..4096); runtime.z = -blender.y",
            "row_direction": "+Z (north to south: row 0 = minZ = -4096, row H-1 = maxZ = +4096)",
            "col_direction": "+X (west to east: col 0 = minX = -4096, col W-1 = maxX = +4096)",
            "uv_mapping": "u = (x - minX) / (maxX - minX), v = (z - minZ) / (maxZ - minZ) with texture.flipY = false",
            "spiegelsee_region_centre_runtime": [650, 1750],
            "spiegelsee_lake_centre_runtime": [900, 1900],
            "playable_slice_bounds_runtime": slice_bounds,
        },
        "textures": {
            "macro_color_ao": {
                "file": "macro_color_ao.webp",
                "resolution": [4096, 4096],
                "metres_per_pixel": 2.0,
                "color_space": "sRGB (RGB) + linear AO (A)",
                "bytes": sz_color_ao,
                "channels": {
                    "R": "Macro ground & grass albedo tint R (sRGB, aligned with art/palette.json)",
                    "G": "Macro ground & grass albedo tint G (sRGB, aligned with art/palette.json)",
                    "B": "Macro ground & grass albedo tint B (sRGB, aligned with art/palette.json)",
                    "A": "Combined large-scale 8-azimuth horizon sky-view AO x tree canopy shadow (0..255, 255 = full open sky)",
                },
            },
            "macro_weights_a": {
                "file": "macro_weights_a.webp",
                "resolution": [2048, 2048],
                "metres_per_pixel": 4.0,
                "color_space": "linear",
                "bytes": sz_weights_a,
                "channels": {
                    "R": "grass weight (0..1)",
                    "G": "grass_dry weight (0..1)",
                    "B": "soil weight (0..1)",
                    "A": "moss weight (0..1)",
                },
            },
            "macro_weights_b": {
                "file": "macro_weights_b.webp",
                "resolution": [2048, 2048],
                "metres_per_pixel": 4.0,
                "color_space": "linear",
                "bytes": sz_weights_b,
                "channels": {
                    "R": "sand / gravel_path weight (0..1)",
                    "G": "sand_wet / wet shore weight (0..1)",
                    "B": "chalk_rock weight (0..1)",
                    "A": "strata_rock weight (0..1)",
                },
            },
            "macro_grass": {
                "file": "macro_grass.webp",
                "resolution": [2048, 2048],
                "metres_per_pixel": 4.0,
                "color_space": "linear",
                "bytes": sz_grass,
                "channels": {
                    "R": "grass_density (0..1) — zero in water, on gravel paths, on steep rock >=32 deg, and on dry beach sand",
                    "G": "grass_height_scale (0..1)",
                    "B": "dry_mix (0..1) — blend between lush grass_green (#696F44) and sun-baked grass_dry (#635C30)",
                    "A": "canopy_shadow (0..1) — combined sky-view & tree canopy shadow multiplier (1 = open sky)",
                },
            },
        },
        "stats": {
            "height_min_m": round(float(h_4k.min()), 2),
            "height_max_m": round(float(h_4k.max()), 2),
            "slope_max_deg": round(float(slope_deg_4k.max()), 2),
            "ao_min": round(float(combined_ao_4k.min()), 3),
            "ao_mean": round(float(combined_ao_4k.mean()), 3),
            "grass_coverage_fraction": round(float((grass_2k[..., 0] > 0.1).mean()), 4),
            "rock_coverage_fraction": round(float(((weights_b_2k[..., 2] + weights_b_2k[..., 3]) > 0.25).mean()), 4),
        },
    }
    (out_dir / "macro.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("[6/6] Rendering visual diagnostic contact sheet...", flush=True)
    build_preview_sheet(
        args.preview,
        macro_srgb_4k,
        combined_ao_4k,
        weights_a_2k,
        weights_b_2k,
        grass_2k,
        slice_bounds,
    )
    dt = time.monotonic() - t0
    print(
        f"MACROMAP COMPLETE in {dt:.1f}s: "
        f"color_ao={sz_color_ao // 1024}KB, weights_a={sz_weights_a // 1024}KB, "
        f"weights_b={sz_weights_b // 1024}KB, grass={sz_grass // 1024}KB",
        flush=True,
    )


if __name__ == "__main__":
    main()
