"""Sandstein-Canyonbogen A (arch_sandstone_a) — Meshy Klasse A-multiview.

Bereitet das Multiview-Rohmodell (arch_sandstone_a/model/A-v1/model.glb) deterministisch
mit tools/blender/vrmeshy.py auf: 2 nicht-mannigfaltige Kanten bereinigen, nach Yaw +2,4°
entlang der Schichtung horizontal strecken (scale_x=1,44, scale_y=1,18) auf ~41 × 11,3 × 27 m
normalisieren, Farbton Richtung sandstone (#D3B490, 0,40) angleichen, Rauheit ≥ 0,65 /
Metall 0,0 klemmen, 1,8 m Eingrabe-Rand an beiden Pfeilern unter z = 0 extrudieren
und Normalen richten.
"""
import os

import bmesh
import bpy
from mathutils import Vector
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _fix_non_manifold(objs):
    """Resolve isolated non-manifold edges (e.g. duplicate fin faces) and seal any tiny hole."""
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        for _ in range(8):
            nm_edges = [e for e in bm.edges if len(e.link_faces) > 2]
            if not nm_edges:
                break
            to_del = set()
            for e in nm_edges:
                faces = sorted(e.link_faces, key=lambda f: f.calc_area())
                # Drop smallest extra fin faces so each edge has at most 2 faces
                for f in faces[:len(faces) - 2]:
                    to_del.add(f)
            if not to_del:
                break
            bmesh.ops.delete(bm, geom=list(to_del), context="FACES")
        b_edges = [e for e in bm.edges if e.is_boundary]
        if b_edges:
            bmesh.ops.holes_fill(bm, edges=b_edges, sides=8)
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def _apply_stretch(objs, sx, sy, sz=1.0):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.scale = (o.scale.x * sx, o.scale.y * sy, o.scale.z * sz)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


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
    _fix_non_manifold(objs)
    vrmeshy.normalize(objs, height=27.0, yaw_deg=2.4)
    _apply_stretch(objs, sx=1.44, sy=1.18, sz=1.0)
    vrmeshy.grade_basecolor(objs, "#D3B490", strength=0.40)
    vrmeshy.clamp_material(objs, roughness_min=0.65, metallic=0.0)
    vrmeshy.burial_skirt(objs, depth=1.8)
    _bury_skirt_below_ground(objs, depth=1.8)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)
