"""Himmelskapsel B (Begleiter) (skyship_pod_b) — Meshy-Asset Klasse B.

Bereitet das schwebende Himmelskörper-Modell (skyship_pod_b/model/B-v1/model.glb) ohne
Eingrabe-Rand auf: schließt alle Smart-Topology-Lücken an Kragen/Seiten vollständig
wasserdicht (Schweißnaht + Loop-Fill + glättender Kragenanschluss), skaliert auf
24,0 m Höhe, bewahrt das violette Band (#8553C6) und klemmt Rauheit >= 0,55.
"""
import math
import os

import bmesh
import bpy
import vrmeshy
import vrmeshfix

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _seal_all_seams(objs):
    """Weld only coincident split-seam vertices and cleanly fill open boundary loops."""
    for o in [ob for ob in objs if ob and ob.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        b_verts = sorted({v for e in bm.edges if e.is_boundary for v in e.verts}, key=lambda v: v.index)
        if b_verts:
            bmesh.ops.remove_doubles(bm, verts=b_verts, dist=0.0008)
        bmesh.ops.dissolve_degenerate(bm, dist=0.0004, edges=list(bm.edges))
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()

    # Fill remaining boundary loops with UV interpolation
    vrmeshfix.fill_boundary_loops(objs, uv_step=0.002)

    # Safety pass: close any rare >64-edge loop and recompute outward winding
    for o in [ob for ob in objs if ob and ob.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bedges = [e for e in bm.edges if e.is_boundary]
        if bedges:
            bmesh.ops.holes_fill(bm, edges=bedges, sides=64)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def _polish_panel_normals(objs):
    """Split crisp panel grooves/belt seams at 26 deg and apply face-area weighted normals."""
    split_rad = math.radians(26.0)
    for o in [ob for ob in objs if ob and ob.type == "MESH"]:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        for f in bm.faces:
            f.smooth = True
        sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > split_rad]
        for e in sharp:
            e.smooth = False
        if sharp:
            bmesh.ops.split_edges(bm, edges=sharp)
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()

        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        wn = o.modifiers.new(name="WeightedPanelNormals", type="WEIGHTED_NORMAL")
        wn.mode = "FACE_AREA"
        wn.weight = 100
        wn.keep_sharp = True
        bpy.ops.object.modifier_apply(modifier=wn.name)


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    _seal_all_seams(objs)
    vrmeshy.normalize(objs, height=24.0, yaw_deg=0.0)
    vrmeshfix.adjust_basecolor_levels(objs, gain=1.08, gamma=0.96, lift=0.01)
    vrmeshy.clamp_material(objs, roughness_min=0.55, metallic=0.0)
    vrmeshy.drop_loose(objs, min_fraction=0.002)
    vrmeshy.fix_normals(objs)
    _polish_panel_normals(objs)
    vrmeshy.link_source(objs)
