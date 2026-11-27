"""Gestufte Kalkstein-Klippenwand B (cliff_chalk_wall_b) — Meshy Klasse A + 0-Credit Klippen-Sculpt.

Heilt die dunkle Kreuz-Vertiefung auf der unteren Vorderseite (+Y), verwandelt die glatt
abgeschnittene Rückseite (-Y) in abgestufte Felsbänke, dämpft verwaschene Mittelstufen
mit organischem Objektraum-Kalksteinrelief und setzt einen 2,5-m-Eingrabe-Rand an.
"""
import math
import os

import bmesh
import numpy as np
import vrmeshy
import vrmeshfix
import vrcliffs

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _heal_cavity_sculpted(objs):
    """Feathered Gaussian repair of the lower-front scar with matching chalk fissures and strata."""
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

        # Smooth Gaussian-like bell falloff across margins (2.0m on X, 1.4m on Z) so no box ridge appears
        wx = np.clip((pos[:, 0] - (-3.5)) / 2.0, 0.0, 1.0) * np.clip((16.5 - pos[:, 0]) / 2.0, 0.0, 1.0)
        wz = np.clip((pos[:, 2] - 6.2) / 1.4, 0.0, 1.0) * np.clip((13.8 - pos[:, 2]) / 1.4, 0.0, 1.0)
        wy = np.clip((pos[:, 1] - 4.0) / 1.2, 0.0, 1.0)
        weight = (wx * wx * (3.0 - 2.0 * wx)) * (wz * wz * (3.0 - 2.0 * wz)) * (wy * wy * (3.0 - 2.0 * wy))

        # Add organic vertical chalk fissures & horizontal strata bench relief matching neighboring cliff
        fissure = 0.22 * np.sin(pos[:, 0] * 1.35 + pos[:, 2] * 0.25) + 0.18 * np.sin(pos[:, 2] * 2.1)
        sculpt_target = target_y + fissure

        # Only pull recessed cavity vertices cleanly outward toward sculpted envelope
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


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=25.0, yaw_deg=1.6)
    _heal_cavity_sculpted(objs)
    vrcliffs.shape_cliff(
        objs,
        top_drop=3.8,
        top_taper_xy=0.18,
        back_sign=-1.0,
        back_slope_out=3.8,
        back_shelf_amp=1.65,
        edge_chamfer_amp=0.18,
        seed=4157,
    )
    vrmeshy.grade_basecolor(objs, "#BCB296", strength=0.40)
    vrcliffs.clean_chalk_surface(objs, target_hex="#BCB296", dark_floor=0.26, dark_lift=0.45,
                                 deweave_rad=2, deweave_keep=0.42, normal_strength=0.40, bump_strength=0.42)
    vrmeshy.clamp_material(objs, roughness_min=0.68, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=2.5)
    vrmeshfix.bury_skirt_below_ground(objs, depth=2.5)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)
