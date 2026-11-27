#!/usr/bin/env python3
"""Offline sparse far-vegetation candidate generator for Violet Reach.

This pilot generator reads the runtime R16 heightfield and world metadata, then
emits a deterministic, versioned JSON instance list for volumetric distant tree
crowns outside the hand-dressed 1x1 km slice.  It intentionally writes nothing
unless ``--out`` is used without ``--dry-run``.

The output is plain JSON rather than a binary sidecar for the pilot: even the
full 3k-8k instance target is only roughly half a megabyte to one megabyte, and
a flat array keeps the first runtime loader trivial to write and inspect.  The
schema is versioned so a compact binary encoding can be added later without
changing generation semantics.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

import build_macromap as macro

ROOT = macro.ROOT
WORLD_DIR = macro.WORLD_DIR
RUNTIME_DIR = macro.RUNTIME_DIR
# Writing is deliberately opt-in: pass --out explicitly (or use --dry-run).

VALID_VARIANTS = ("tree_oak_a", "tree_beech_a", "tree_willow_a", "tree_ancient_a")
VARIANT_SCALE_RANGES = {
    "tree_oak_a": (1.00, 1.38),
    "tree_beech_a": (1.05, 1.45),
    "tree_willow_a": (0.95, 1.28),
    "tree_ancient_a": (1.35, 1.85),
}
MONUMENT_ASSET_PREFIXES = (
    "monument_",
    "gate_",
    "column_",
    "ruin_",
    "stair_",
    "bridge_",
    "arch_",
)

UINT64_MASK = (1 << 64) - 1


@dataclass(frozen=True)
class Grid2D:
    """Uniform row-major grid; rows run +Z, columns run +X."""

    values: np.ndarray
    origin_x: float
    origin_z: float
    spacing: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.values.shape[:2]

    @property
    def min_x(self) -> float:
        return float(self.origin_x)

    @property
    def min_z(self) -> float:
        return float(self.origin_z)

    @property
    def max_x(self) -> float:
        return float(self.origin_x + (self.values.shape[1] - 1) * self.spacing)

    @property
    def max_z(self) -> float:
        return float(self.origin_z + (self.values.shape[0] - 1) * self.spacing)


@dataclass
class FarvegEnvironment:
    """Sampleable world inputs used by the deterministic generator."""

    heightfield: Grid2D
    water_dist: Grid2D
    water_level: Grid2D
    slice_bounds: dict[str, float]
    paths: list[dict] = field(default_factory=list)
    exclusion_circles: tuple[tuple[float, float, float], ...] = ()
    slope_override: Grid2D | None = None


@dataclass(frozen=True)
class FarvegParams:
    seed: int = macro.SEED
    candidate_cell_size_m: float = 10.0
    candidate_jitter_fraction: float = 0.42
    density_scale: float = 1.0
    savanna_floor: float = 0.022
    target_instances: int = 10000
    max_instances: int = 10000
    hard_slope_deg: float = 31.0
    tree_line_start_m: float = 430.0
    tree_line_end_m: float = 650.0
    min_above_water_m: float = 2.5
    water_edge_buffer_m: float = 1.5
    slice_transition_m: float = 120.0
    path_clearance_m: float = 5.0
    monument_clearance_m: float = 8.0
    embed_min_m: float = 1.0
    embed_max_m: float = 2.0
    gradient_step_m: float = 2.0
    core_spacing_min_m: float = 24.0
    core_spacing_max_m: float = 40.0
    edge_spacing_min_m: float = 40.0
    edge_spacing_max_m: float = 65.0
    savanna_spacing_m: float = 120.0


@dataclass
class GenerationResult:
    instances: list[dict]
    stats: dict


# ---------------------------------------------------------------------------
# Deterministic hashing and grid sampling
# ---------------------------------------------------------------------------
def hash01(ix: np.ndarray, iz: np.ndarray, seed: int, salt: int) -> np.ndarray:
    """Stable integer hash in [0, 1), independent of Python's randomized hash."""
    x = np.asarray(ix, dtype=np.uint64)
    z = np.asarray(iz, dtype=np.uint64)
    a = x * np.uint64(0x9E3779B97F4A7C15)
    a += z * np.uint64(0xC2B2AE3D27D4EB4F)
    a += np.uint64(seed & UINT64_MASK)
    a += np.uint64((int(salt) * 0x165667B19E3779F9) & UINT64_MASK)

    # MurmurHash3-style 64-bit finalizer.  NumPy uint64 arithmetic deliberately
    # wraps modulo 2^64, making this stable across platforms and processes.
    a ^= a >> np.uint64(30)
    a *= np.uint64(0xBF58476D1CE4E5B9)
    a ^= a >> np.uint64(27)
    a *= np.uint64(0x94D049BB133111EB)
    a ^= a >> np.uint64(31)
    return (a >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


def sample_grid_bilinear(grid: Grid2D, x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Bilinearly sample a Grid2D at runtime x/z coordinates, clamped at edges."""
    xa = np.asarray(x, dtype=np.float64)
    za = np.asarray(z, dtype=np.float64)
    values = grid.values
    fx = np.clip((xa - grid.origin_x) / grid.spacing, 0.0, values.shape[1] - 1)
    fz = np.clip((za - grid.origin_z) / grid.spacing, 0.0, values.shape[0] - 1)
    x0 = np.floor(fx).astype(np.int64)
    z0 = np.floor(fz).astype(np.int64)
    x1 = np.minimum(x0 + 1, values.shape[1] - 1)
    z1 = np.minimum(z0 + 1, values.shape[0] - 1)
    wx = fx - x0
    wz = fz - z0

    v00 = values[z0, x0].astype(np.float64)
    v10 = values[z0, x1].astype(np.float64)
    v01 = values[z1, x0].astype(np.float64)
    v11 = values[z1, x1].astype(np.float64)
    return (v00 * (1.0 - wx) + v10 * wx) * (1.0 - wz) + (v01 * (1.0 - wx) + v11 * wx) * wz


def finite_difference_slope_degrees(
    heightfield: Grid2D, x: np.ndarray, z: np.ndarray, step_m: float = 2.0
) -> np.ndarray:
    """Approximate terrain slope from the full-resolution R16 heightfield.

    The macro map uses cell-averaged 2 m derivatives.  For scattered continuous
    candidate positions this central-difference approximation is the closest
    point-sample analogue and uses the same underlying full R16 data.
    """
    step = max(float(step_m), 1e-3)
    hx0 = sample_grid_bilinear(heightfield, x - step, z)
    hx1 = sample_grid_bilinear(heightfield, x + step, z)
    hz0 = sample_grid_bilinear(heightfield, x, z - step)
    hz1 = sample_grid_bilinear(heightfield, x, z + step)
    dh_dx = (hx1 - hx0) / (2.0 * step)
    dh_dz = (hz1 - hz0) / (2.0 * step)
    return np.degrees(np.arctan(np.hypot(dh_dx, dh_dz))).astype(np.float32)


# ---------------------------------------------------------------------------
# Exclusion helpers
# ---------------------------------------------------------------------------
def rect_inside_mask(x: np.ndarray, z: np.ndarray, bounds: dict[str, float]) -> np.ndarray:
    return (
        (x >= float(bounds["minX"]))
        & (x <= float(bounds["maxX"]))
        & (z >= float(bounds["minZ"]))
        & (z <= float(bounds["maxZ"]))
    )


def rect_outside_distance(x: np.ndarray, z: np.ndarray, bounds: dict[str, float]) -> np.ndarray:
    dx = np.maximum(np.maximum(float(bounds["minX"]) - x, x - float(bounds["maxX"])), 0.0)
    dz = np.maximum(np.maximum(float(bounds["minZ"]) - z, z - float(bounds["maxZ"])), 0.0)
    return np.hypot(dx, dz).astype(np.float32)


def slice_density_factor(x: np.ndarray, z: np.ndarray, bounds: dict[str, float], transition_m: float) -> np.ndarray:
    if transition_m <= 0.0:
        return np.where(rect_inside_mask(x, z, bounds), 0.0, 1.0).astype(np.float32)
    return macro.smoothstep(0.0, float(transition_m), rect_outside_distance(x, z, bounds))


def path_edge_distance_points(x: np.ndarray, z: np.ndarray, paths: list[dict]) -> np.ndarray:
    """Distance to path edge in metres (negative inside the stroke), for point arrays."""
    result = np.full(np.broadcast_shapes(np.asarray(x).shape, np.asarray(z).shape), 1e6, dtype=np.float32)
    for path in paths:
        width = float(path.get("width", 2.4))
        poly = np.asarray(path.get("polyline", []), dtype=np.float32)
        if len(poly) < 2:
            continue
        for i in range(len(poly) - 1):
            a = poly[i]
            b = poly[i + 1]
            dx = float(b[0] - a[0])
            dz = float(b[1] - a[1])
            denom = max(dx * dx + dz * dz, 1e-6)
            t = np.clip(((x - float(a[0])) * dx + (z - float(a[1])) * dz) / denom, 0.0, 1.0)
            d = np.hypot(x - float(a[0]) - t * dx, z - float(a[1]) - t * dz) - 0.5 * width
            result = np.minimum(result, d.astype(np.float32))
    return result


def exclusion_circle_edge_distance(
    x: np.ndarray, z: np.ndarray, circles: tuple[tuple[float, float, float], ...]
) -> np.ndarray:
    result = np.full(np.broadcast_shapes(np.asarray(x).shape, np.asarray(z).shape), 1e6, dtype=np.float32)
    for cx, cz, radius in circles:
        d = np.hypot(x - float(cx), z - float(cz)) - float(radius)
        result = np.minimum(result, d.astype(np.float32))
    return result


def extract_exclusion_circles(placements_data: dict, base_radius_m: float = 10.0) -> tuple[tuple[float, float, float], ...]:
    """Extract coarse monument/structure circles from placements.

    This is deliberately approximate: the pilot only needs to avoid obvious
    intersections with large structures.  Scatter entries use their polygon/rect
    centroid and bounding radius; direct placements use a conservative scaled
    radius.  Most current placements are inside the slice anyway, where the
    hard slice exclusion dominates.
    """
    circles: list[tuple[float, float, float]] = []
    for entry in placements_data.get("placements", []):
        asset = str(entry.get("asset", ""))
        if not asset.startswith(MONUMENT_ASSET_PREFIXES):
            continue
        scatter = entry.get("scatter")
        if scatter:
            cx = cz = radius = None
            poly = scatter.get("polygon")
            rect = scatter.get("rect")
            if poly:
                pts = np.asarray(poly, dtype=np.float32)
                cx = float(pts[:, 0].mean())
                cz = float(pts[:, 1].mean())
                radius = float(np.hypot(pts[:, 0] - cx, pts[:, 1] - cz).max())
            elif rect:
                cx = 0.5 * (float(rect["minX"]) + float(rect["maxX"]))
                cz = 0.5 * (float(rect["minZ"]) + float(rect["maxZ"]))
                radius = 0.5 * math.hypot(float(rect["maxX"]) - float(rect["minX"]), float(rect["maxZ"]) - float(rect["minZ"]))
            if cx is not None and cz is not None and radius is not None:
                circles.append((cx, cz, max(radius, 1.0)))
        elif "x" in entry and "z" in entry:
            scale = max(float(entry.get("scale", 1.0)), 0.5)
            circles.append((float(entry["x"]), float(entry["z"]), base_radius_m * scale))
    return tuple(circles)


# ---------------------------------------------------------------------------
# Density, spacing and species
# ---------------------------------------------------------------------------
def target_spacing_for_density(density: np.ndarray, params: FarvegParams) -> np.ndarray:
    """Map forest density to local target spacing in metres.

    Dense cores end at 45-70 m, forest edges at 80-130 m, and near-zero density
    savanna receives only sparse accents.  The piecewise-linear breakpoints are
    a pilot approximation rather than a botanical model.
    """
    xp = np.array([0.0, 0.12, 0.55, 0.85, 1.0], dtype=np.float32)
    fp = np.array(
        [
            params.savanna_spacing_m,
            params.edge_spacing_max_m,
            params.edge_spacing_min_m,
            params.core_spacing_max_m,
            params.core_spacing_min_m,
        ],
        dtype=np.float32,
    )
    return np.interp(np.clip(density, 0.0, 1.0), xp, fp).astype(np.float32)


def enforce_variable_spacing(xs: np.ndarray, zs: np.ndarray, required_spacing: np.ndarray) -> list[int]:
    """Greedy deterministic variable-radius Poisson-like thinning.

    Input order defines priority during thinning.  A pair is rejected when its
    distance is below the larger of the two local target spacings; this is
    conservative at density transitions and documented as a pilot approximation.
    """
    if len(xs) == 0:
        return []
    max_spacing = float(np.max(required_spacing))
    if not math.isfinite(max_spacing) or max_spacing <= 0.0:
        return list(range(len(xs)))
    cell_size = max_spacing
    grid: dict[tuple[int, int], list[int]] = {}
    accepted: list[int] = []
    eps = 1e-5

    for i in range(len(xs)):
        cx = math.floor(float(xs[i]) / cell_size)
        cz = math.floor(float(zs[i]) / cell_size)
        ok = True
        for ox in (-1, 0, 1):
            if not ok:
                break
            for oz in (-1, 0, 1):
                for j in grid.get((cx + ox, cz + oz), []):
                    req = max(float(required_spacing[i]), float(required_spacing[j]))
                    dx = float(xs[i] - xs[j])
                    dz = float(zs[i] - zs[j])
                    if dx * dx + dz * dz < req * req - eps:
                        ok = False
                        break
                if not ok:
                    break
        if ok:
            accepted.append(i)
            grid.setdefault((cx, cz), []).append(i)
    return accepted


def choose_variant_indices(
    x: np.ndarray,
    z: np.ndarray,
    density: np.ndarray,
    above_water: np.ndarray,
    water_dist: np.ndarray,
    ix: np.ndarray,
    iz: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Choose one of the four tree variants per candidate.

    Willows are riparian accents, beech/oak form noise-clustered woodland, and
    ancient trees are rare large-crown emergents in strong forest cores.
    """
    species_noise = macro.value_noise(x, -z, 180.0, 71)
    patch_noise = 0.5 + 0.5 * macro.value_noise(x, -z, 90.0, 72)
    riparian = np.maximum(
        1.0 - macro.smoothstep(8.0, 38.0, above_water),
        0.75 * (1.0 - macro.smoothstep(10.0, 70.0, water_dist)),
    )
    riparian = np.clip(riparian, 0.0, 1.0)

    oak_w = 0.52 + 0.22 * np.clip(-species_noise, 0.0, 1.0) + 0.10 * (1.0 - density)
    beech_w = 0.42 + 0.30 * np.clip(species_noise, 0.0, 1.0) + 0.12 * density
    willow_w = 0.05 + 1.35 * riparian
    ancient_w = 0.025 + 0.11 * macro.smoothstep(0.55, 0.95, density) * np.clip(patch_noise, 0.0, 1.0)

    total = np.maximum(oak_w + beech_w + willow_w + ancient_w, 1e-6)
    r = hash01(ix, iz, seed, 41) * total
    choice = np.full(len(x), 3, dtype=np.uint8)  # ancient is the tail bin
    c0 = oak_w
    c1 = c0 + beech_w
    c2 = c1 + willow_w
    choice = np.where(r < c2, 2, choice)
    choice = np.where(r < c1, 1, choice)
    choice = np.where(r < c0, 0, choice)
    return choice.astype(np.uint8), riparian.astype(np.float32)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate_instances(
    env: FarvegEnvironment,
    params: FarvegParams = FarvegParams(),
    density_fn: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
) -> GenerationResult:
    """Generate deterministic far-vegetation instances for an environment.

    ``density_fn`` is intentionally injectable for synthetic offline tests; it
    receives continuous x/z arrays and returns a base density in [0, 1].  The
    production path uses the shared macro-map forest distribution instead.
    """
    if params.target_instances <= 0:
        raise ValueError("target_instances must be positive")
    if params.max_instances <= 0:
        raise ValueError("max_instances must be positive")
    if params.candidate_cell_size_m <= 0.0:
        raise ValueError("candidate_cell_size_m must be positive")

    hf = env.heightfield
    min_x, max_x = hf.min_x, hf.max_x
    min_z, max_z = hf.min_z, hf.max_z
    width = max_x - min_x
    depth = max_z - min_z
    if width <= 0.0 or depth <= 0.0:
        raise ValueError("heightfield world bounds must be positive")

    nominal_cell = float(params.candidate_cell_size_m)
    nx = max(1, int(math.ceil(width / nominal_cell)))
    nz = max(1, int(math.ceil(depth / nominal_cell)))
    # Shrink the last cell fractionally into the pitch so the jittered grid covers
    # the complete heightfield extent instead of leaving a half-cell strip at maxX/Z.
    cell_x = width / nx
    cell_z = depth / nz
    ix_row = np.arange(nx, dtype=np.int64)
    iz_row = np.arange(nz, dtype=np.int64)
    ix_grid, iz_grid = np.meshgrid(ix_row, iz_row)
    ix = ix_grid.ravel()
    iz = iz_grid.ravel()

    jitter_frac = float(np.clip(params.candidate_jitter_fraction, 0.0, 0.49))
    jx = (hash01(ix, iz, params.seed, 1) - 0.5) * 2.0 * jitter_frac * cell_x
    jz = (hash01(ix, iz, params.seed, 2) - 0.5) * 2.0 * jitter_frac * cell_z
    x = min_x + (ix.astype(np.float64) + 0.5) * cell_x + jx
    z = min_z + (iz.astype(np.float64) + 0.5) * cell_z + jz
    x = np.clip(x, min_x, max_x)
    z = np.clip(z, min_z, max_z)

    terrain_y = sample_grid_bilinear(hf, x, z)
    if env.slope_override is not None:
        slope_deg = sample_grid_bilinear(env.slope_override, x, z).astype(np.float32)
    else:
        slope_deg = finite_difference_slope_degrees(hf, x, z, params.gradient_step_m)
    water_dist = sample_grid_bilinear(env.water_dist, x, z).astype(np.float32)
    water_y = sample_grid_bilinear(env.water_level, x, z).astype(np.float32)
    above_water = (terrain_y - water_y).astype(np.float32)

    inside_slice = rect_inside_mask(x, z, env.slice_bounds)
    path_dist = path_edge_distance_points(x, z, env.paths)
    monument_dist = exclusion_circle_edge_distance(x, z, env.exclusion_circles)

    hard_valid = (
        (slope_deg < float(params.hard_slope_deg))
        & (above_water >= float(params.min_above_water_m))
        & (water_dist >= float(params.water_edge_buffer_m))
        & (~inside_slice)
        & (path_dist >= float(params.path_clearance_m))
        & (monument_dist >= float(params.monument_clearance_m))
    )

    if density_fn is None:
        forest_density = macro.forest_macro_density(x, z, slope_deg, above_water)
    else:
        forest_density = np.asarray(density_fn(x, z), dtype=np.float32)
    forest_density = np.clip(forest_density, 0.0, 1.0)
    # The shared macro forest noise intentionally has no altitude term: in the ground
    # bake, rock/strata weights already suppress high-alpine vegetation.  Real crown
    # geometry needs an explicit treeline, otherwise isolated instances appear on
    # bright alpine plates and rock faces where the macro colour reads as stone.
    altitude_factor = 1.0 - macro.smoothstep(
        float(params.tree_line_start_m), float(params.tree_line_end_m), terrain_y
    )
    forest_density = forest_density * altitude_factor

    # The macro value is a canopy-opacity/occupancy mask rather than a literal
    # per-tree probability.  The default density_scale of 1 nevertheless keeps it
    # exact for this pilot: the fine 10 m candidate grid plus density-dependent
    # thinning already reaches the 3k-8k target without remapping the forest.
    # The scale remains an explicit tuning knob for later runtime budgets.
    # Sparse savanna accents use a small unscaled floor; the slice ramp also
    # multiplies that floor so the hand-dressed core does not leak crowns.
    calibrated_forest = np.clip(forest_density * float(params.density_scale), 0.0, 1.0)
    density = np.maximum(calibrated_forest, float(params.savanna_floor))
    # Sparse savanna accents are still full-sized trees, not alpine shrubs: the treeline
    # must gate the floor as well as the dense-forest term.
    density = density * altitude_factor
    density = density * slice_density_factor(x, z, env.slice_bounds, params.slice_transition_m)
    density = np.clip(density, 0.0, 1.0).astype(np.float32)

    accept_probability = density
    accept_key = hash01(ix, iz, params.seed, 11)
    density_accepted = hard_valid & (accept_key < accept_probability)

    candidate_indices = np.flatnonzero(density_accepted)
    # Process stronger forest first, with only a tiny deterministic tie/noise term.
    # This matters at woodland edges: if sparse wide-spacing accents were allowed
    # to win the greedy order purely at random, they would suppress later dense-core
    # candidates through the conservative pairwise max-spacing rule and the pilot
    # would fall far below its 3k-8k instance target.
    order_noise = hash01(ix[candidate_indices], iz[candidate_indices], params.seed, 12)
    order_score = density[candidate_indices].astype(np.float64) + 0.025 * order_noise
    candidate_indices = candidate_indices[np.argsort(-order_score, kind="stable")]

    spacing = target_spacing_for_density(density, params)
    thinned_positions = enforce_variable_spacing(
        x[candidate_indices], z[candidate_indices], spacing[candidate_indices]
    )
    kept_indices = candidate_indices[np.asarray(thinned_positions, dtype=np.int64)]

    stats = {
        "candidate_cells": int(len(x)),
        "candidate_pitch_m": [round(float(cell_x), 4), round(float(cell_z), 4)],
        "hard_valid_candidates": int(np.count_nonzero(hard_valid)),
        "density_accepted_candidates": int(np.count_nonzero(density_accepted)),
        "spacing_accepted_candidates": int(len(kept_indices)),
        "rejected_inside_slice": int(np.count_nonzero(inside_slice)),
        "rejected_low_above_water": int(np.count_nonzero(above_water < float(params.min_above_water_m))),
        "rejected_steep_slope": int(np.count_nonzero(slope_deg >= float(params.hard_slope_deg))),
        "treeline_faded_candidates": int(np.count_nonzero(altitude_factor < 0.999)),
        "mean_effective_density": round(float(density[hard_valid].mean()) if np.any(hard_valid) else 0.0, 5),
    }

    if len(kept_indices) == 0:
        stats.update(
            {
                "emitted_instances": 0,
                "culled_by_target": 0,
                "variant_counts": {name: 0 for name in VALID_VARIANTS},
            }
        )
        return GenerationResult([], stats)

    kept_ix = ix[kept_indices]
    kept_iz = iz[kept_indices]
    kept_x = x[kept_indices]
    kept_z = z[kept_indices]
    kept_density = density[kept_indices]
    kept_above = above_water[kept_indices]
    kept_water_dist = water_dist[kept_indices]

    variant_indices, riparian = choose_variant_indices(
        kept_x,
        kept_z,
        kept_density,
        kept_above,
        kept_water_dist,
        kept_ix,
        kept_iz,
        params.seed,
    )
    variant_names = [VALID_VARIANTS[int(v)] for v in variant_indices]

    scale_hash = hash01(kept_ix, kept_iz, params.seed, 21)
    yaw = hash01(kept_ix, kept_iz, params.seed, 22) * (2.0 * math.pi)
    embed = float(params.embed_min_m) + hash01(kept_ix, kept_iz, params.seed, 23) * (
        float(params.embed_max_m) - float(params.embed_min_m)
    )
    scale = np.empty(len(kept_indices), dtype=np.float64)
    for local_i, variant_index in enumerate(variant_indices):
        lo, hi = VARIANT_SCALE_RANGES[VALID_VARIANTS[int(variant_index)]]
        scale[local_i] = lo + scale_hash[local_i] * (hi - lo)

    scale_norm = np.clip((scale - 0.85) / (1.75 - 0.85), 0.0, 1.0)
    ancient_bonus = (variant_indices == 3).astype(np.float64) * 0.12
    priority = np.clip(
        0.52 * kept_density
        + 0.20 * scale_norm
        + 0.12 * riparian
        + ancient_bonus
        + 0.10 * hash01(kept_ix, kept_iz, params.seed, 24),
        0.0,
        1.0,
    )

    # Priority-descending order makes the flat array directly truncatable by a
    # runtime loader.  Dropping lower-priority members can only increase spacing,
    # never violate the already enforced minimum distances.
    priority_order = np.argsort(-priority, kind="stable")
    limit = min(int(params.target_instances), int(params.max_instances), len(priority_order))
    culled = max(0, len(priority_order) - limit)
    priority_order = priority_order[:limit]

    instances: list[dict] = []
    for local_i in priority_order:
        source_i = int(kept_indices[local_i])
        variant = variant_names[local_i]
        embed_i = round(float(embed[local_i]), 3)
        terrain_y_i = float(terrain_y[source_i])
        instances.append(
            {
                "x": round(float(kept_x[local_i]), 3),
                "y": round(terrain_y_i - embed_i, 3),
                "z": round(float(kept_z[local_i]), 3),
                "variant": variant,
                "scale": round(float(scale[local_i]), 4),
                "yaw": round(float(yaw[local_i]), 5),
                "priority": round(float(priority[local_i]), 4),
                "embed": embed_i,
            }
        )

    variant_counts = {name: 0 for name in VALID_VARIANTS}
    for inst in instances:
        variant_counts[inst["variant"]] += 1
    stats.update(
        {
            "emitted_instances": int(len(instances)),
            "culled_by_target": int(culled),
            "variant_counts": variant_counts,
        }
    )
    return GenerationResult(instances, stats)


# ---------------------------------------------------------------------------
# Real-world input assembly and JSON output
# ---------------------------------------------------------------------------
def load_json_if_exists(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def build_environment(world_dir: Path = WORLD_DIR, runtime_dir: Path = RUNTIME_DIR) -> FarvegEnvironment:
    """Load real Violet Reach terrain/hydrology/slice inputs without writing anything."""
    full_h, manifest = macro.load_world_heightfield(runtime_dir)
    samples = int(manifest["samples"])
    tile_size = float(manifest.get("tileSize", 512.0))
    node_spacing = tile_size / float(samples - 1)
    origin_x = float(manifest.get("originX", -4096.0))
    origin_z = float(manifest.get("originZ", -4096.0))
    height_grid = Grid2D(full_h, origin_x, origin_z, node_spacing)

    hydrology_path = world_dir / "hydrology.json"
    if not hydrology_path.exists():
        hydrology_path = world_dir / "hydrology" / "hydrology.json"
    hydrology_data = json.loads(hydrology_path.read_text(encoding="utf-8"))

    # Match the macro map's 4 m hydrology grid: 2048 cell centres over 8192 m.
    hydro_spacing = 4.0
    hydro_count = int(round((height_grid.max_x - height_grid.min_x) / hydro_spacing))
    axis = height_grid.min_x + (np.arange(hydro_count, dtype=np.float32) + 0.5) * hydro_spacing
    x_grid, z_grid = np.meshgrid(axis, axis)
    water_dist, water_y = macro.compute_hydrology_fields(x_grid, z_grid, hydrology_data)
    hydro_origin = float(axis[0])
    water_dist_grid = Grid2D(water_dist, hydro_origin, hydro_origin, hydro_spacing)
    water_level_grid = Grid2D(water_y, hydro_origin, hydro_origin, hydro_spacing)

    slice_data = json.loads((world_dir / "slice.json").read_text(encoding="utf-8"))
    slice_bounds = {
        "minX": float(slice_data.get("bounds", {}).get("minX", -100.0)),
        "minZ": float(slice_data.get("bounds", {}).get("minZ", 1100.0)),
        "maxX": float(slice_data.get("bounds", {}).get("maxX", 900.0)),
        "maxZ": float(slice_data.get("bounds", {}).get("maxZ", 2100.0)),
    }

    paths_list = list(slice_data.get("paths", []))
    extra_paths_file = world_dir / "paths" / "paths.json"
    if extra_paths_file.exists():
        extra = json.loads(extra_paths_file.read_text(encoding="utf-8"))
        paths_list.extend(extra.get("paths", extra if isinstance(extra, list) else []))

    placements_data = load_json_if_exists(world_dir / "placements.json", {"placements": []})
    circles = extract_exclusion_circles(placements_data)

    return FarvegEnvironment(
        heightfield=height_grid,
        water_dist=water_dist_grid,
        water_level=water_level_grid,
        slice_bounds=slice_bounds,
        paths=paths_list,
        exclusion_circles=circles,
    )


def world_bounds_dict(heightfield: Grid2D) -> dict:
    return {
        "minX": round(heightfield.min_x, 3),
        "maxX": round(heightfield.max_x, 3),
        "minZ": round(heightfield.min_z, 3),
        "maxZ": round(heightfield.max_z, 3),
        "widthMetres": round(heightfield.max_x - heightfield.min_x, 3),
        "heightMetres": round(heightfield.max_z - heightfield.min_z, 3),
    }


def build_payload(result: GenerationResult, env: FarvegEnvironment, params: FarvegParams) -> dict:
    fields = ["x", "y", "z", "variant", "scale", "yaw", "priority", "embed"]
    return {
        "format": "violet-reach-farveg-json",
        "version": 1,
        "generator": "tools/world/build_farveg.py",
        "seed": int(params.seed),
        "world_noise_seed": int(macro.SEED),
        "coordinate_convention": {
            "axes": "Runtime: X east, Y up, Z south; runtime.z = -blender.y",
            "yaw": "radians around +Y",
            "y": "terrain surface height minus embed; crowns are intentionally sunk into terrain",
            "embed": "positive metres already subtracted from terrain surface height",
        },
        "bounds": world_bounds_dict(env.heightfield),
        "fields": fields,
        "field_docs": {
            "x": "runtime X position in metres",
            "y": "runtime Y position in metres, already terrain_height - embed",
            "z": "runtime Z position in metres",
            "variant": "tree asset id: tree_oak_a, tree_beech_a, tree_willow_a or tree_ancient_a",
            "scale": "dimensionless asset scale",
            "yaw": "rotation around +Y in radians",
            "priority": "0..1 deterministic streaming/culling importance; instances are sorted descending",
            "embed": "positive metres sunk below the bilinear R16 terrain surface",
        },
        "variants": list(VALID_VARIANTS),
        "slice_exclusion": {
            "bounds": env.slice_bounds,
            "hard_core": True,
            "transition_metres": float(params.slice_transition_m),
        },
        "generation": {
            "candidate_cell_size_m": float(params.candidate_cell_size_m),
            "candidate_jitter_fraction": float(params.candidate_jitter_fraction),
            "density_scale": float(params.density_scale),
            "savanna_floor": float(params.savanna_floor),
            "target_instances": int(params.target_instances),
            "max_instances": int(params.max_instances),
            "hard_slope_deg": float(params.hard_slope_deg),
            "tree_line_m": [float(params.tree_line_start_m), float(params.tree_line_end_m)],
            "min_above_water_m": float(params.min_above_water_m),
            "water_edge_buffer_m": float(params.water_edge_buffer_m),
            "path_clearance_m": float(params.path_clearance_m),
            "monument_clearance_m": float(params.monument_clearance_m),
            "embed_range_m": [float(params.embed_min_m), float(params.embed_max_m)],
            "spacing_m": {
                "forest_core": [float(params.core_spacing_min_m), float(params.core_spacing_max_m)],
                "forest_edge": [float(params.edge_spacing_min_m), float(params.edge_spacing_max_m)],
                "savanna_accent": float(params.savanna_spacing_m),
            },
            "assumptions": [
                "forest_macro is a canopy occupancy/opacity field; density_scale is an optional planting-density calibration knob (1.0 keeps the macro distribution exact)",
                "slope is sampled by central differences from the full-resolution R16 heightfield rather than from the macro map's cell-averaged 2 m slope raster",
                "hydrology distance/level are bilinearly sampled from the same 4 m analytical lake/river field used by build_macromap.py",
                "path and monument exclusions are coarse centreline/circle clearances; current monuments mostly lie inside the hard-excluded hand-dressed slice",
                "variable spacing uses the larger local spacing of each pair, so density transitions are conservative",
            ],
            "stats": result.stats,
        },
        "instance_count": len(result.instances),
        "instances": result.instances,
    }


def write_farveg_json(payload: dict, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)
    return path.stat().st_size


def main(argv: list[str] | None = None) -> None:
    t0 = time.monotonic()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None, help="JSON output path; required unless --dry-run is used")
    ap.add_argument("--world-dir", type=Path, default=WORLD_DIR, help="world metadata directory")
    ap.add_argument("--runtime-dir", type=Path, default=RUNTIME_DIR, help="R16 runtime terrain directory")
    ap.add_argument("--seed", type=int, default=macro.SEED, help="deterministic placement seed (world noise seed stays fixed)")
    ap.add_argument("--target-instances", type=int, default=FarvegParams.target_instances, help="soft priority-culling target")
    ap.add_argument("--max-instances", type=int, default=FarvegParams.max_instances, help="hard output instance cap")
    ap.add_argument("--candidate-cell-size", type=float, default=FarvegParams.candidate_cell_size_m, help="base jitter-grid cell size in metres")
    ap.add_argument("--density-scale", type=float, default=FarvegParams.density_scale, help="canopy-occupancy to planting-density calibration factor")
    ap.add_argument("--savanna-floor", type=float, default=FarvegParams.savanna_floor, help="minimum density for sparse open-country accents")
    ap.add_argument("--slice-transition", type=float, default=FarvegParams.slice_transition_m, help="density ramp outside the hard-excluded slice core, in metres")
    ap.add_argument("--hard-slope", type=float, default=FarvegParams.hard_slope_deg, help="hard slope exclusion in degrees")
    ap.add_argument("--tree-line-start", type=float, default=FarvegParams.tree_line_start_m, help="terrain height where the forest density treeline fade starts")
    ap.add_argument("--tree-line-end", type=float, default=FarvegParams.tree_line_end_m, help="terrain height where procedural forest density reaches zero")
    ap.add_argument("--min-above-water", type=float, default=FarvegParams.min_above_water_m, help="hard minimum height above local water in metres")
    ap.add_argument("--water-edge-buffer", type=float, default=FarvegParams.water_edge_buffer_m, help="hard signed distance buffer outside water edges in metres")
    ap.add_argument("--path-clearance", type=float, default=FarvegParams.path_clearance_m, help="clearance beyond path edge in metres")
    ap.add_argument("--monument-clearance", type=float, default=FarvegParams.monument_clearance_m, help="clearance beyond coarse monument circles in metres")
    ap.add_argument("--dry-run", action="store_true", help="generate and print statistics without writing output")
    args = ap.parse_args(argv)

    if args.target_instances > args.max_instances:
        ap.error("--target-instances must be <= --max-instances")
    if not args.dry_run and args.out is None:
        ap.error("--out is required unless --dry-run is used")

    params = FarvegParams(
        seed=args.seed,
        candidate_cell_size_m=args.candidate_cell_size,
        density_scale=args.density_scale,
        savanna_floor=args.savanna_floor,
        target_instances=args.target_instances,
        max_instances=args.max_instances,
        hard_slope_deg=args.hard_slope,
        tree_line_start_m=args.tree_line_start,
        tree_line_end_m=args.tree_line_end,
        min_above_water_m=args.min_above_water,
        water_edge_buffer_m=args.water_edge_buffer,
        slice_transition_m=args.slice_transition,
        path_clearance_m=args.path_clearance,
        monument_clearance_m=args.monument_clearance,
    )

    print("[1/3] Loading R16 terrain, hydrology, slice, paths and placements...", flush=True)
    env = build_environment(args.world_dir, args.runtime_dir)
    print("[2/3] Generating deterministic sparse far-vegetation candidates...", flush=True)
    result = generate_instances(env, params)
    payload = build_payload(result, env, params)

    bytes_written = 0
    if args.dry_run:
        print("[3/3] Dry run: no output file written.", flush=True)
    else:
        print(f"[3/3] Writing {args.out}...", flush=True)
        bytes_written = write_farveg_json(payload, args.out)

    dt = time.monotonic() - t0
    counts = result.stats.get("variant_counts", {})
    print(
        "FARVEG COMPLETE in "
        f"{dt:.1f}s: instances={len(result.instances)} "
        f"(target={params.target_instances}, max={params.max_instances}), "
        f"candidates={result.stats['candidate_cells']}, "
        f"hard_valid={result.stats['hard_valid_candidates']}, "
        f"variants={counts}, bytes={bytes_written}, dry_run={args.dry_run}",
        flush=True,
    )


if __name__ == "__main__":
    main()
