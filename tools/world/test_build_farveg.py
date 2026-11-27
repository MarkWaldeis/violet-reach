#!/usr/bin/env python3
"""Synthetic offline regression checks for build_farveg.py.

These tests use small in-memory heightfields only.  They do not read production
world tiles, touch web/explore/public, or invoke network/browser/Blender code.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_farveg as farveg  # noqa: E402


ORIGIN = -120.0
EXTENT = 240.0
GRID_SPACING = 4.0
GRID_N = int(EXTENT / GRID_SPACING) + 1
AXIS = ORIGIN + np.arange(GRID_N, dtype=np.float32) * GRID_SPACING
XX, ZZ = np.meshgrid(AXIS, AXIS)
FAR_SLICE = {"minX": 1000.0, "minZ": 1000.0, "maxX": 1100.0, "maxZ": 1100.0}


def constant_density(value: float):
    def density(x, z):
        del z
        return np.full_like(x, value, dtype=np.float32)

    return density


def make_params(**overrides) -> farveg.FarvegParams:
    values = {
        "seed": 991,
        "candidate_cell_size_m": 8.0,
        "candidate_jitter_fraction": 0.45,
        "density_scale": 1.0,
        "savanna_floor": 0.0,
        "target_instances": 140,
        "max_instances": 140,
        "hard_slope_deg": 31.0,
        "min_above_water_m": 2.5,
        "water_edge_buffer_m": 1.5,
        "slice_transition_m": 8.0,
        "path_clearance_m": 3.0,
        "monument_clearance_m": 3.0,
        "embed_min_m": 1.0,
        "embed_max_m": 2.0,
        "gradient_step_m": GRID_SPACING,
        "core_spacing_min_m": 10.0,
        "core_spacing_max_m": 14.0,
        "edge_spacing_min_m": 16.0,
        "edge_spacing_max_m": 22.0,
        "savanna_spacing_m": 30.0,
    }
    values.update(overrides)
    return farveg.FarvegParams(**values)


def make_env(
    *,
    slice_bounds=None,
    height_values=None,
    slope_values=None,
    water_level_values=None,
    water_dist_values=None,
    paths=None,
    exclusion_circles=(),
) -> farveg.FarvegEnvironment:
    if height_values is None:
        heights = np.full((GRID_N, GRID_N), 20.0, dtype=np.float32)
    else:
        heights = height_values.astype(np.float32)
    heightfield = farveg.Grid2D(heights, ORIGIN, ORIGIN, GRID_SPACING)

    if water_level_values is None:
        water_level_values = np.full((GRID_N, GRID_N), -1000.0, dtype=np.float32)
    if water_dist_values is None:
        water_dist_values = np.full((GRID_N, GRID_N), 10000.0, dtype=np.float32)
    water_level = farveg.Grid2D(water_level_values.astype(np.float32), ORIGIN, ORIGIN, GRID_SPACING)
    water_dist = farveg.Grid2D(water_dist_values.astype(np.float32), ORIGIN, ORIGIN, GRID_SPACING)

    slope_override = None
    if slope_values is not None:
        slope_override = farveg.Grid2D(slope_values.astype(np.float32), ORIGIN, ORIGIN, GRID_SPACING)

    return farveg.FarvegEnvironment(
        heightfield=heightfield,
        water_dist=water_dist,
        water_level=water_level,
        slice_bounds=slice_bounds or FAR_SLICE,
        paths=list(paths or []),
        exclusion_circles=tuple(exclusion_circles),
        slope_override=slope_override,
    )


def dense_result(env=None, params=None) -> farveg.GenerationResult:
    return farveg.generate_instances(env or make_env(), params or make_params(), constant_density(1.0))


class FarvegGeneratorTests(unittest.TestCase):
    def test_deterministic_same_seed(self):
        env = make_env()
        params = make_params()
        first = dense_result(env, params)
        second = dense_result(env, params)
        self.assertGreater(len(first.instances), 0)
        self.assertEqual(first.instances, second.instances)
        self.assertEqual(first.stats, second.stats)
        different_seed = dense_result(env, make_params(seed=992))
        self.assertNotEqual(first.instances, different_seed.instances)

    def test_bounds_fields_and_embed(self):
        env = make_env()
        result = dense_result(env)
        self.assertEqual(len(result.instances), 140)  # deterministic target/max cap in this fixture
        min_x, max_x = env.heightfield.min_x, env.heightfield.max_x
        min_z, max_z = env.heightfield.min_z, env.heightfield.max_z
        required = {"x", "y", "z", "variant", "scale", "yaw", "priority", "embed"}
        for inst in result.instances:
            self.assertTrue(required.issubset(inst.keys()))
            self.assertGreaterEqual(inst["x"], min_x)
            self.assertLessEqual(inst["x"], max_x)
            self.assertGreaterEqual(inst["z"], min_z)
            self.assertLessEqual(inst["z"], max_z)
            self.assertGreaterEqual(inst["yaw"], 0.0)
            self.assertLess(inst["yaw"], 2.0 * math.pi + 1e-5)
            self.assertGreaterEqual(inst["priority"], 0.0)
            self.assertLessEqual(inst["priority"], 1.0)
            self.assertGreaterEqual(inst["embed"], 1.0)
            self.assertLessEqual(inst["embed"], 2.0)
            # Flat synthetic terrain is exactly y=20 before embedding.
            self.assertAlmostEqual(inst["y"] + inst["embed"], 20.0, delta=0.002)

    def test_height_sampling_and_embed_on_sloped_grid(self):
        heights = (20.0 + 0.10 * XX - 0.05 * ZZ).astype(np.float32)
        env = make_env(height_values=heights)
        result = dense_result(env)
        self.assertGreater(len(result.instances), 40)
        for inst in result.instances:
            expected_surface = 20.0 + 0.10 * inst["x"] - 0.05 * inst["z"]
            self.assertAlmostEqual(inst["y"] + inst["embed"], expected_surface, delta=0.003)

    def test_hard_water_exclusion(self):
        # Linear water plane: above_water = 20 - (20 - 10*x) = 10*x exactly
        # under bilinear interpolation.  The hard 2.5 m minimum therefore puts
        # the analytic shoreline cutoff at x=0.25 m.
        water_level = (20.0 - 10.0 * XX).astype(np.float32)
        env = make_env(water_level_values=water_level)
        result = dense_result(env)
        self.assertGreater(len(result.instances), 20)
        self.assertTrue(all(inst["x"] >= 0.25 - 0.001 for inst in result.instances))

    def test_hard_slope_exclusion(self):
        # Linear slope field crosses the hard 31 degree cutoff at x=1.8 m.
        slope = np.maximum(0.0, 40.0 - 5.0 * XX).astype(np.float32)
        env = make_env(slope_values=slope)
        result = dense_result(env)
        self.assertGreater(len(result.instances), 20)
        self.assertTrue(all(inst["x"] >= 1.8 - 0.001 for inst in result.instances))

    def test_hard_slice_exclusion(self):
        slice_bounds = {"minX": 0.0, "minZ": 0.0, "maxX": 60.0, "maxZ": 60.0}
        env = make_env(slice_bounds=slice_bounds)
        result = dense_result(env)
        self.assertGreater(len(result.instances), 20)
        for inst in result.instances:
            inside = (
                slice_bounds["minX"] <= inst["x"] <= slice_bounds["maxX"]
                and slice_bounds["minZ"] <= inst["z"] <= slice_bounds["maxZ"]
            )
            self.assertFalse(inside, f"instance inside slice core: {inst}")

    def test_slice_transition_factor_and_spacing_ranges(self):
        bounds = {"minX": 0.0, "minZ": 0.0, "maxX": 60.0, "maxZ": 60.0}
        x = np.array([30.0, 60.0, 65.0, 70.0])
        z = np.array([30.0, 30.0, 30.0, 30.0])
        factor = farveg.slice_density_factor(x, z, bounds, 10.0)
        self.assertEqual(float(factor[0]), 0.0)
        self.assertEqual(float(factor[1]), 0.0)
        self.assertGreater(float(factor[2]), 0.0)
        self.assertLess(float(factor[2]), 1.0)
        self.assertAlmostEqual(float(factor[3]), 1.0, places=5)

        params = make_params()
        spacing = farveg.target_spacing_for_density(np.array([0.0, 0.5, 1.0]), params)
        self.assertAlmostEqual(float(spacing[0]), params.savanna_spacing_m, places=5)
        self.assertGreaterEqual(float(spacing[1]), params.core_spacing_max_m)
        self.assertLessEqual(float(spacing[1]), params.edge_spacing_max_m)
        self.assertAlmostEqual(float(spacing[2]), params.core_spacing_min_m, places=5)

    def test_spacing_and_no_obvious_exact_raster(self):
        params = make_params()
        result = dense_result(make_env(), params)
        pts = np.array([[inst["x"], inst["z"]] for inst in result.instances], dtype=np.float64)
        self.assertGreater(len(pts), 60)

        nearest = []
        min_distance = float("inf")
        for i, p in enumerate(pts):
            d = np.hypot(pts[:, 0] - p[0], pts[:, 1] - p[1])
            d[i] = np.inf
            nearest.append(float(d.min()))
            min_distance = min(min_distance, nearest[-1])
        self.assertGreaterEqual(min_distance, params.core_spacing_min_m - 0.02)

        # Jitter plus greedy thinning must not collapse back to exact cell-grid
        # coordinates or a single repeated nearest-neighbour distance.
        cell = params.candidate_cell_size_m
        x_mods = {round(float(x % cell), 5) for x in pts[:, 0]}
        z_mods = {round(float(z % cell), 5) for z in pts[:, 1]}
        self.assertGreater(len(x_mods), 20)
        self.assertGreater(len(z_mods), 20)
        self.assertGreater(max(nearest) - min(nearest), 1.0)

    def test_path_and_monument_exclusions(self):
        paths = [{"width": 4.0, "polyline": [[-120.0, 0.0], [120.0, 0.0]]}]
        circles = ((-60.0, 40.0, 10.0),)
        env = make_env(paths=paths, exclusion_circles=circles)
        result = dense_result(env)
        self.assertGreater(len(result.instances), 20)
        for inst in result.instances:
            # width/2 + clearance = 2 + 3 = 5 m around the path centreline
            self.assertGreaterEqual(abs(inst["z"]), 5.0 - 1e-3)
            d_circle = math.hypot(inst["x"] + 60.0, inst["z"] - 40.0)
            self.assertGreaterEqual(d_circle, 10.0 + 3.0 - 1e-3)

    def test_monument_exclusion_extraction(self):
        placements = {
            "placements": [
                {"asset": "monument_split_disc_a", "x": 1.0, "z": 2.0, "scale": 2.0},
                {"asset": "tree_oak_a", "x": 50.0, "z": 50.0, "scale": 1.0},
            ]
        }
        circles = farveg.extract_exclusion_circles(placements, base_radius_m=10.0)
        self.assertEqual(circles, ((1.0, 2.0, 20.0),))

    def test_json_roundtrip(self):
        env = make_env()
        params = make_params()
        result = dense_result(env, params)
        payload = farveg.build_payload(result, env, params)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
            path = Path(td) / "farveg.json"
            path2 = Path(td) / "farveg-second.json"
            farveg.write_farveg_json(payload, path)
            farveg.write_farveg_json(payload, path2)
            self.assertEqual(path.read_bytes(), path2.read_bytes())
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["format"], "violet-reach-farveg-json")
        self.assertEqual(loaded["version"], 1)
        self.assertEqual(loaded["fields"], ["x", "y", "z", "variant", "scale", "yaw", "priority", "embed"])
        self.assertEqual(loaded["instance_count"], len(result.instances))
        self.assertEqual(loaded["instances"], result.instances)

    def test_variant_mapping(self):
        result = dense_result()
        variants = {inst["variant"] for inst in result.instances}
        self.assertTrue(variants)
        self.assertTrue(variants.issubset(set(farveg.VALID_VARIANTS)))
        self.assertGreaterEqual(len(variants), 2)
        for inst in result.instances:
            lo, hi = farveg.VARIANT_SCALE_RANGES[inst["variant"]]
            self.assertGreaterEqual(inst["scale"], lo - 1e-4)
            self.assertLessEqual(inst["scale"], hi + 1e-4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
