"""Kalkstein-Klippen-Ecke A (cliff_chalk_corner_a) — 0-Credit Kitbash aus freigegebenen Kreideklippen.

Kombiniert die verifizierten Meshy-Rohmodelle cliff_chalk_wall_a (Ost-Flügel, 25 m) und
cliff_chalk_wall_b (Süd-Flügel, 22 m, um -88° um Z gedreht) mit großzügigem ~10-m-Ecküberlapp
zu einer zusammenhängenden L-förmigen Canyon-Felsnase (~44 × 36 × 25 m, min_z = -2,5 m).
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix
import numpy as np

import vrlib
import vrmeshy
import vrmeshfix
import vrcliffs

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_ROCKS_DIR = os.path.dirname(ASSET_DIR)


def _heal_cavity_sculpted(objs):
    """Feathered Gaussian repair of the lower-front scar on cliff_chalk_wall_b."""
    for obj in [o for o in objs if o and o.type == "MESH"]:
        me = obj.data
        pos = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", pos)
        pos = pos.reshape(-1, 3)

        in_y = pos[:, 1] > 4.6
        in_x = (pos[:, 0] >= -1.5) & (pos[:, 0] <= 14.5)
        in_z = (pos[:, 2] >= 7.6) & (pos[:, 2] <= 12.4)
        core_mask = in_y & in_x & in_z
        if not core_mask.any():
            continue

        pts = pos[core_mask]
        target_y = float(np.quantile(pts[:, 1], 0.80))

        wx = np.clip((pos[:, 0] - (-3.5)) / 2.0, 0.0, 1.0) * np.clip((16.5 - pos[:, 0]) / 2.0, 0.0, 1.0)
        wz = np.clip((pos[:, 2] - 6.2) / 1.4, 0.0, 1.0) * np.clip((13.8 - pos[:, 2]) / 1.4, 0.0, 1.0)
        wy = np.clip((pos[:, 1] - 4.0) / 1.2, 0.0, 1.0)
        weight = (wx * wx * (3.0 - 2.0 * wx)) * (wz * wz * (3.0 - 2.0 * wz)) * (wy * wy * (3.0 - 2.0 * wy))

        fissure = 0.22 * np.sin(pos[:, 0] * 1.35 + pos[:, 2] * 0.25) + 0.18 * np.sin(pos[:, 2] * 2.1)
        sculpt_target = target_y + fissure

        recess = np.maximum(0.0, sculpt_target - pos[:, 1])
        pos[:, 1] += weight * recess * 0.85
        me.vertices.foreach_set("co", pos.astype(np.float32).ravel())
        me.update()

        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        inner_verts = [
            bm.verts[i] for i in np.flatnonzero(core_mask).tolist()
            if i < len(bm.verts)
        ]
        if inner_verts:
            for _ in range(6):
                bmesh.ops.smooth_vert(bm, verts=inner_verts, factor=0.50, use_axis_x=False, use_axis_y=True, use_axis_z=False)
        bm.to_mesh(me)
        me.update()
        bm.free()


def _apply_matrix(objs, mat):
    for o in objs:
        o.matrix_world = mat @ o.matrix_world
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def build():
    # Wing A: cliff_chalk_wall_a
    wing_a = vrmeshy.load_raw(os.path.join(ASSETS_ROCKS_DIR, "cliff_chalk_wall_a"))
    vrmeshy.drop_loose(wing_a, min_fraction=0.002)
    vrmeshy.normalize(wing_a, height=25.0, yaw_deg=4.0)
    vrcliffs.shape_cliff(
        wing_a,
        top_drop=4.6,
        top_teeth_trim=3.4,
        top_taper_xy=0.22,
        back_sign=-1.0,
        back_slope_out=2.6,
        back_shelf_amp=1.35,
        edge_chamfer_amp=0.16,
        seed=4201,
    )
    vrmeshy.grade_basecolor(wing_a, "#BCB296", strength=0.39)
    vrcliffs.clean_chalk_surface(
        wing_a,
        target_hex="#BCB296",
        dark_floor=0.22,
        dark_lift=0.36,
        deweave_rad=2,
        deweave_keep=0.48,
        normal_strength=0.42,
        bump_strength=0.38,
    )
    vrmeshy.clamp_material(wing_a, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(wing_a, depth=2.5)
    vrmeshfix.bury_skirt_below_ground(wing_a, depth=2.5)
    _apply_matrix(wing_a, Matrix.Translation((6.0, 7.0, 0.0)))

    # Wing B: cliff_chalk_wall_b rotated -88 deg around Z into L-corner bastion
    wing_b = vrmeshy.load_raw(os.path.join(ASSETS_ROCKS_DIR, "cliff_chalk_wall_b"))
    vrmeshy.drop_loose(wing_b, min_fraction=0.002)
    vrmeshy.normalize(wing_b, height=22.0, yaw_deg=1.6)
    _heal_cavity_sculpted(wing_b)
    vrcliffs.shape_cliff(
        wing_b,
        top_drop=4.2,
        top_taper_xy=0.20,
        back_sign=-1.0,
        back_slope_out=3.2,
        back_shelf_amp=1.50,
        edge_chamfer_amp=0.18,
        seed=4257,
    )
    vrmeshy.grade_basecolor(wing_b, "#BCB296", strength=0.39)
    vrcliffs.clean_chalk_surface(
        wing_b,
        target_hex="#BCB296",
        dark_floor=0.22,
        dark_lift=0.36,
        deweave_rad=2,
        deweave_keep=0.48,
        normal_strength=0.42,
        bump_strength=0.38,
    )
    vrmeshy.clamp_material(wing_b, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(wing_b, depth=2.5)
    vrmeshfix.bury_skirt_below_ground(wing_b, depth=2.5)
    _apply_matrix(
        wing_b,
        Matrix.Translation((-9.5, -5.5, 0.0)) @ Matrix.Rotation(math.radians(-88.0), 4, "Z"),
    )

    all_objs = [o for o in wing_a + wing_b if o and o.type == "MESH"]

    # Recenter combined XY footprint to (0, 0) while preserving min_z = -2.5
    lo, hi = vrlib.world_bounds(all_objs)
    _apply_matrix(all_objs, Matrix.Translation((-0.5 * (lo.x + hi.x), -0.5 * (lo.y + hi.y), 0.0)))

    # Ensure matching active UV layer name before join so all material slots retain UVs
    for o in all_objs:
        if o.data.uv_layers:
            o.data.uv_layers[0].name = "UVMap"
            o.data.uv_layers[0].active = True
            o.data.uv_layers[0].active_render = True

    bpy.ops.object.select_all(action="DESELECT")
    for o in all_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]
    if len(all_objs) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = "cliff_chalk_corner_a_source"

    vrmeshy.fix_normals([joined])
    vrmeshy.link_source([joined])
