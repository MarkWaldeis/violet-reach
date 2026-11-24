"""Gespaltenes Inselmonument A (monument_split_disc_a) — Meshy Klasse A-multiview.

Bereitet das wasserdichte Multiview-Rohmodell (monument_split_disc_a/model/A-v1/model.glb)
deterministisch mit tools/blender/vrmeshy.py auf: Auf Zielhöhe 40,0 m (yaw -2,0°)
normalisieren, Farbton Richtung stone_weathered (#DCCDB1, 0,40) angleichen,
Rauheit ≥ 0,55 / Metall 0,0 klemmen, 1,5 m Eingrabe-Rand unter z = 0 extrudieren
und Normalen richten.
"""
import os

import bmesh
from mathutils import Vector
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _bury_skirt_below_ground(objs, depth):
    """Place the burial_skirt cut seam at z = 0 so the vertical skirt stays underground."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        body = [v for v in bm.verts if v.co.z > -depth + 1e-3]
        if body:
            z0 = min(v.co.z for v in body)
            for v in body:
                v.co.z -= z0
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is not None:
            center = Vector((0.5, 0.5))
            for f in bm.faces:
                if any(v.co.z <= -depth + 1e-3 for v in f.verts) and any(v.co.z > -depth + 1e-3 for v in f.verts):
                    for loop in f.loops:
                        if loop.vert.co.z <= -depth + 1e-3:
                            uv = loop[uv_layer].uv
                            loop[uv_layer].uv = uv + (center - uv) * 0.04
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.normalize(objs, height=40.0, yaw_deg=-2.0)
    vrmeshy.grade_basecolor(objs, "#DCCDB1", strength=0.40)
    vrmeshy.clamp_material(objs, roughness_min=0.55, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.5)
    _bury_skirt_below_ground(objs, depth=1.5)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)
