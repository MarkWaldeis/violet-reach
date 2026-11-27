"""Wiesen-Eiche A — subtractive-first R9 build on V3_TPL_tree_meadow_oak."""
import vrtrees

TREE_CONFIG = {
    "asset_id": "tree_oak_a",
    "template": "V3_TPL_tree_meadow_oak",
    "target_size_m": (11.0, 12.0, 11.0),
    "expected_z_min": -0.65,
    "foliage_target": "#696F44",
    "foliage_strength": 0.80,
    "bark_target": "#41321D",
    "bark_strength": 0.36,
    "foliage_gamma": 0.78,
    "foliage_lift_floor": 0.035,
    "foliage_translucency": 0.220,
    "bark_boost": 1.36,
    "bark_floor": 0.009,
    "bark_translucency": 0.088,
    "alpha_cutoff": 0.34,
    "roughness_min": 0.65,
    "card_config": {
        "width_scale": 1.0,
        "length_scale": 1.0,
        "cup": 0.035,
        "twist_deg": 8.0,
        "arch": 0.015,
        "tilt": True,
        "tilt_threshold": 0.42,
        "tilt_min_deg": 7.0,
        "tilt_max_deg": 14.0,
        "upward_bias": 0.62,
        "seed": 9101,
    },
    "shelf_fold_config": {
        "max_cards": 18,
        "min_span": 2.05,
        "min_normal_z": 0.88,
        "pitch_min_deg": 22.0,
        "pitch_max_deg": 32.0,
        "cup": 0.085,
        "arch": 0.045,
        "seed": 9101,
    },
    "tip_trim_config": {
        "min_tip_distance": 0.20,
        "zmin": 4.6,
        "max_count": 12,
        "taper_start": 0.38,
        "end_radius": 0.025,
        "length_scale": 0.28,
    },
}


def build():
    vrtrees.build_tree(TREE_CONFIG)
