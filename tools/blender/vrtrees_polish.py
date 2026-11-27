"""Targeted 0-credit post-build polish for beech, ancient, and willow R9 trees.

Kept separate from vrtrees.py so approved tree_oak_a retains its valid source_hash.
"""
import bmesh
import numpy as np
from mathutils import Vector

import vrtrees
import vrmeshy


def brighten_bark(obj, *, target_hex="#5A452C", lift_mul=1.20, floor=0.012, emission=0.10):
    """Lift dark interior bark albedo cleanly with packed images."""
    mats = [m for m in obj.data.materials if m and m.node_tree]
    if not mats:
        return
    bark = mats[0]
    bsdf = vrtrees._principled(bark)
    vrtrees._grade_material_basecolor(bark, target_hex, 0.25, "_vr_bark_warm")
    made = {}
    for node in vrtrees._basecolor_texture_nodes(bark):
        img = node.image
        if img in made:
            continue
        arr = np.empty(len(img.pixels), dtype=np.float32)
        img.pixels.foreach_get(arr)
        arr = arr.reshape(img.size[1], img.size[0], 4)
        arr[..., :3] = np.clip(arr[..., :3] * float(lift_mul) + float(floor), 0.0, 1.0)
        made[img] = vrmeshy._replace_image(img, arr, "_vr_bark_bright")
    for node in bark.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image in made:
            node.image = made[node.image]
    if bsdf is not None:
        base_nodes = vrtrees._basecolor_texture_nodes(bark)
        if base_nodes:
            ec = bsdf.inputs["Emission Color"]
            for link in list(ec.links):
                bark.node_tree.links.remove(link)
            bark.node_tree.links.new(base_nodes[0].outputs["Color"], ec)
            bsdf.inputs["Emission Strength"].default_value = float(emission)


def clean_degenerate_faces(obj):
    """Remove zero-area foliage sliver faces that cause black shadow-terminator artifacts in clay/Cycles."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    tiny = [f for f in bm.faces if f.calc_area() < 1e-6]
    if tiny:
        bmesh.ops.delete(bm, geom=tiny, context="FACES")
        bm.to_mesh(me)
        me.update()
    bm.free()


def retract_exposed_spear_tips(obj, *, zmin=2.4, min_foliage_dist=0.10, retract_dist=0.42,
                               max_tips=28, fill_cards=24, seed=901):
    """Detect protruding naked bark spear-tips (even connected to main trunk) and retract + cover them."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()

    fol_pts = np.array([v.co[:] for f in bm.faces if f.material_index == 1 for v in f.verts], dtype=float)
    if not len(fol_pts):
        bm.free()
        return

    bark_verts = sorted({v.index for f in bm.faces if f.material_index == 0 for v in f.verts})
    candidates = []
    for vi in bark_verts:
        v = bm.verts[vi]
        co = v.co
        if co.z < zmin:
            continue
        nbrs = [e.other_vert(v).co for e in v.link_edges]
        if not nbrs:
            continue
        mean_nbr = sum(nbrs, Vector((0, 0, 0))) / len(nbrs)
        outward = co - mean_nbr
        if outward.length < 0.03:
            continue
        dir_n = outward.normalized()
        if any((nco - co).dot(dir_n) > 0.025 for nco in nbrs):
            continue
        d_fol = float(np.sqrt(((fol_pts - np.array(co[:])) ** 2).sum(axis=1).min()))
        if d_fol < min_foliage_dist:
            continue
        candidates.append((d_fol + max(0.0, co.z - 4.0) * 0.15, vi, co.copy(), dir_n))

    candidates.sort(key=lambda item: -item[0])
    retracted_tips = []
    used = []
    for _score, vi, co, dir_n in candidates:
        if any((co - u).length < 0.42 for u in used):
            continue
        used.append(co)
        v0 = bm.verts[vi]
        # Clamp retraction step by adjacent edge lengths so tips never invert past 2nd ring
        ring1 = [e.other_vert(v0) for e in v0.link_edges]
        avg_edge = sum((nv.co - v0.co).length for nv in ring1) / max(len(ring1), 1)
        safe_step = min(retract_dist, max(0.18, avg_edge * 0.85))
        ring2 = {v0} | set(ring1)
        for rv in ring1:
            for e2 in rv.link_edges:
                ring2.add(e2.other_vert(rv))
        for nv in ring2:
            if nv is v0:
                step = safe_step
            elif nv in ring1:
                step = safe_step * 0.62
            else:
                step = safe_step * 0.25
            if nv.co.z >= 0.0:
                nv.co -= dir_n * step
        retracted_tips.append((v0.co.copy(), dir_n))
        if len(retracted_tips) >= max_tips:
            break

    bm.to_mesh(me)
    me.update()
    bm.free()

    if fill_cards > 0 and retracted_tips:
        endpoints = [
            {
                "tip": (t.x, t.y, t.z),
                "axis": (a.x, a.y, a.z),
                "radius": 0.035,
                "score": 1.0 - i * 0.01,
            }
            for i, (t, a) in enumerate(retracted_tips[:max(1, fill_cards // 2)])
        ]
        before_verts = len(me.vertices)
        tpl_normals = [x.vector.copy() for x in me.corner_normals]
        tpl_count = len(me.loops)
        vrtrees._add_endpoint_foliage_clusters(
            me, endpoints, max_cards=fill_cards, scaffold_cards=min(6, fill_cards // 3), seed=seed
        )
        vrtrees._set_new_blockcol_white(me, before_verts)
        vrtrees._restore_template_foliage_normals(me, tpl_normals, tpl_count)


def polish_willow_curtains(obj, *, peak_tuck_z=0.22, width_boost=1.22, max_bark_dist=0.85, floor_z=0.18):
    """Tuck upward leaf-card tips slightly into twigs, widen curtains into overlapping cascades, and anchor strays."""
    me = obj.data
    bark_pts = np.array([me.vertices[v].co[:] for p in me.polygons if p.material_index == 0 for v in p.vertices], dtype=float)
    comps = vrtrees._foliage_components(me, 1)
    moved = 0
    for polys in comps:
        rows = vrtrees._component_rows(me, polys)
        if len(rows) < 4:
            continue
        verts = [v for v, _u, _w, _co in rows]
        pts = np.array([me.vertices[v].co[:] for v in verts], dtype=float)
        centre = pts.mean(axis=0)

        # Only relocate truly stray detached cards (> 0.85 m from nearest twig)
        if len(bark_pts):
            dists = np.sqrt(((bark_pts - centre) ** 2).sum(axis=1))
            min_idx = int(np.argmin(dists))
            if dists[min_idx] > max_bark_dist:
                top_pt = pts[int(np.argmax(pts[:, 2]))]
                shift_vec = Vector(bark_pts[min_idx]) - Vector(top_pt)
                for v in verts:
                    me.vertices[v].co += shift_vec * 0.90

        pu0 = vrtrees._mean_row(rows, lambda u, w: u < 0.25)
        pu1 = vrtrees._mean_row(rows, lambda u, w: u > 0.75)
        au = pu1 - pu0
        uhat = au.normalized() if au.length > 1e-5 else Vector((1, 0, 0))
        cvec = Vector(pts.mean(axis=0))
        for v, _u, w, _co in rows:
            co = me.vertices[v].co.copy()
            u_off = (co - cvec).dot(uhat)
            co += uhat * (u_off * (width_boost - 1.0))
            if w > 0.78 and co.z > 2.0:
                t_top = (w - 0.78) / 0.22
                co.z -= peak_tuck_z * t_top
                # Also gently pull top peak tip radially inward toward center bark to hide spear tips
                co.x += (cvec.x - co.x) * 0.12 * t_top
                co.y += (cvec.y - co.y) * 0.12 * t_top
            if co.z < floor_z:
                co.z = floor_z
            me.vertices[v].co = co
            moved += 1
    if moved:
        me.update()


def smooth_root_step(obj):
    """Gently smooth the buried ground intersection ring without making sharp polygon corners."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    band = [v for v in bm.verts if -0.22 <= v.co.z <= 0.28]
    if band:
        for _ in range(3):
            bmesh.ops.smooth_vert(bm, verts=band, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=False)
        bm.to_mesh(me)
        me.update()
    bm.free()
