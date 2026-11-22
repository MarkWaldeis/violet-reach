"""Ruinenmauer Kalkstein A (ruin_wall_a) — Meshy-Pilot Klasse A.

Bereitet das Meshy-Rohmodell (ruin_wall_a/model/A-v2/model.glb) deterministisch
mit tools/blender/vrmeshy.py auf: Lose Teile entfernen, auf Zielhöhe 4,5 m
(ca. 6,23 × 1,11 × 4,50 m) normalisieren, eingebackenes Licht herausrechnen,
Farbton Richtung stone_weathered (#DCCDB1) angleichen, Rauheit ≥ 0,55 / Metall 0,0
klemmen, 35 cm Eingrabe-Rand am Mauerfuß extrudieren (Schnittkante bündig auf z = 0)
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
    vrmeshy.normalize(objs, size_m=(8.0, 1.4, 4.5), yaw_deg=0.0)
    vrmeshy.delight_basecolor(objs, radius_frac=0.25)
    vrmeshy.grade_basecolor(objs, "#DCCDB1", strength=0.65)
    vrmeshy.clamp_material(objs, roughness_min=0.55, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=0.35)
    _bury_skirt_below_ground(objs, depth=0.35)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)
