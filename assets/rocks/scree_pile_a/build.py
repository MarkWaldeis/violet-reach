"""Kalkstein-Geröllhaufen A (scree_pile_a) — Meshy Klasse B.

Bereitet das Meshy-Rohmodell (scree_pile_a/model/B-v1/model.glb) deterministisch
mit tools/blender/vrmeshy.py auf: Alle 419 verzahnten Steinschalen BEHALTEN (kein
drop_loose!), auf Zielhöhe 1,20 m (yaw -55,4°) normalisieren, einen wasserdichten,
~5,5 cm zurückgesetzten Geröll-/Erdkern (gleiches Material + 35 cm Eingrabe-Rand
unter z = 0) einfügen, damit LOD1–3 massiv bleiben, Farbton Richtung canyon_chalk
(#BCB296, 0,45) angleichen, Rauheit ≥ 0,65 / Metall 0,0 klemmen und Normalen richten.
"""
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))


def _pick_crevice_uv(obj):
    """Find a verified opaque, dark-dusty stone UV point inside an existing mesh triangle."""
    mat = obj.data.materials[0] if obj.data.materials else None
    img = None
    if mat and mat.node_tree:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and bsdf.inputs["Base Color"].is_linked:
            node = bsdf.inputs["Base Color"].links[0].from_node
            if node.type == "TEX_IMAGE":
                img = node.image
    if img is None or obj.data.uv_layers.active is None:
        return Vector((0.5, 0.5))

    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    arr = px.reshape(h, w, 4)

    uv_layer = obj.data.uv_layers.active.data
    best_uv = Vector((0.5, 0.5))
    best_score = 1e9
    for poly in obj.data.polygons:
        if poly.loop_total < 3:
            continue
        uvs = [uv_layer[li].uv for li in poly.loop_indices]
        c = sum(uvs, Vector((0.0, 0.0))) / len(uvs)
        ix = min(max(int((c.x % 1.0) * w), 0), w - 1)
        iy = min(max(int((c.y % 1.0) * h), 0), h - 1)
        if arr[iy, ix, 3] < 0.99:
            continue
        # Ensure a small neighborhood stays inside opaque texture island
        if ix < 16 or ix >= w - 16 or iy < 16 or iy >= h - 16:
            continue
        patch = arr[iy - 12:iy + 13, ix - 12:ix + 13]
        if (patch[..., 3] < 0.99).any():
            continue
        lum = float((patch[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)).mean())
        # Target darker dusty crevice stone (~0.25-0.38 linear/sRGB mean)
        score = abs(lum - 0.34)
        if score < best_score:
            best_score = score
            best_uv = Vector((c.x % 1.0, c.y % 1.0))
    return best_uv


def _add_inner_core_dome(objs, inset=0.055, skirt_depth=0.35):
    """Build a watertight opaque inner dirt/chalk core dome ~5.5 cm inside the stone hull
    with an integrated vertical burial skirt extending down to z = -skirt_depth.
    """
    src = objs[0]
    bm_src = bmesh.new()
    bm_src.from_mesh(src.data)
    bvh = BVHTree.FromBMesh(bm_src)

    coords = np.array([v.co[:] for v in bm_src.verts], dtype=np.float64)
    bm_src.free()

    n_ang = 40
    n_rings = 9
    ang_step = 2.0 * math.pi / n_ang
    angles = np.arctan2(coords[:, 1], coords[:, 0])
    radii = np.hypot(coords[:, 0], coords[:, 1])
    low_mask = coords[:, 2] < 0.45

    r_edge = np.zeros(n_ang, dtype=np.float64)
    for k in range(n_ang):
        a0 = -math.pi + (k + 0.5) * ang_step
        da = np.abs((angles - a0 + math.pi) % (2.0 * math.pi) - math.pi)
        sel = low_mask & (da <= ang_step * 0.9)
        if not sel.any():
            sel = da <= ang_step * 1.5
        r_edge[k] = float(np.percentile(radii[sel], 92)) if sel.any() else 1.2

    # Smooth contour radially and tuck inside the outer perimeter rocks
    for _ in range(2):
        r_edge = 0.25 * np.roll(r_edge, -1) + 0.5 * r_edge + 0.25 * np.roll(r_edge, 1)
    r_outer = np.maximum(0.25, r_edge - inset)

    def sample_recessed_z(x, y):
        hits = []
        for dx, dy in ((0.0, 0.0), (0.045, 0.0), (-0.045, 0.0), (0.0, 0.045), (0.0, -0.045)):
            loc, _, _, _ = bvh.ray_cast(Vector((x + dx, y + dy, 2.5)), Vector((0.0, 0.0, -1.0)), 4.0)
            if loc is not None:
                hits.append(loc.z)
        if not hits:
            return 0.02
        return max(0.02, min(hits) - inset)

    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    uv_center = _pick_crevice_uv(src)

    center_z = sample_recessed_z(0.0, 0.0)
    v_top_center = bm.verts.new((0.0, 0.0, center_z))

    rings = []
    ring_fracs = [float(i) / n_rings for i in range(1, n_rings + 1)]
    for ri, frac in enumerate(ring_fracs):
        ring_verts = []
        is_rim = ri == n_rings - 1
        for k in range(n_ang):
            a = -math.pi + (k + 0.5) * ang_step
            r = r_outer[k] * frac
            x, y = r * math.cos(a), r * math.sin(a)
            z = 0.0 if is_rim else sample_recessed_z(x, y)
            ring_verts.append(bm.verts.new((x, y, z)))
        rings.append(ring_verts)

    # Gentle downward-safe smoothing on interior rings so dome stays smooth & never pokes out
    for ri in range(n_rings - 1):
        z_cur = [v.co.z for v in rings[ri]]
        for k in range(n_ang):
            avg = 0.25 * z_cur[(k - 1) % n_ang] + 0.5 * z_cur[k] + 0.25 * z_cur[(k + 1) % n_ang]
            rings[ri][k].co.z = min(z_cur[k], avg)

    # Outer burial skirt ring at z = -skirt_depth and bottom cap
    skirt_ring = [bm.verts.new((v.co.x, v.co.y, -skirt_depth)) for v in rings[-1]]
    v_bot_center = bm.verts.new((0.0, 0.0, -skirt_depth))

    # Build dome faces (outward normals)
    for k in range(n_ang):
        k1 = (k + 1) % n_ang
        bm.faces.new((v_top_center, rings[0][k], rings[0][k1]))
    for ri in range(n_rings - 1):
        for k in range(n_ang):
            k1 = (k + 1) % n_ang
            bm.faces.new((rings[ri][k], rings[ri + 1][k], rings[ri + 1][k1], rings[ri][k1]))
    # Burial skirt wall
    for k in range(n_ang):
        k1 = (k + 1) % n_ang
        bm.faces.new((rings[-1][k], skirt_ring[k], skirt_ring[k1], rings[-1][k1]))
    # Bottom cap (facing -Z)
    for k in range(n_ang):
        k1 = (k + 1) % n_ang
        bm.faces.new((v_bot_center, skirt_ring[k1], skirt_ring[k]))

    # Assign compact crevice UVs inside verified opaque patch
    uv_scale = 0.004
    for f in bm.faces:
        for lp in f.loops:
            u = uv_center.x + (lp.vert.co.x * uv_scale)
            v = uv_center.y + (lp.vert.co.y * uv_scale)
            lp[uv_layer].uv = (min(max(u, 0.002), 0.998), min(max(v, 0.002), 0.998))

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))

    me = bpy.data.meshes.new("scree_core_dome")
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    if src.data.materials:
        me.materials.append(src.data.materials[0])

    core_obj = bpy.data.objects.new("scree_core_dome", me)
    bpy.context.scene.collection.objects.link(core_obj)
    objs.append(core_obj)


def build():
    objs = vrmeshy.load_raw(ASSET_DIR)
    # DO NOT call drop_loose — keep all 419 interlocked rock chunks!
    vrmeshy.normalize(objs, height=1.20, yaw_deg=-55.4)
    vrmeshy.grade_basecolor(objs, "#BCB296", strength=0.45)
    vrmeshy.clamp_material(objs, roughness_min=0.65, metallic=0.0)
    _add_inner_core_dome(objs, inset=0.055, skirt_depth=0.35)
    vrmeshy.fix_normals(objs)
    vrmeshy.link_source(objs)
