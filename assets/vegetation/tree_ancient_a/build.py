"""Alter knorriger Baum A — subtractive-first R9.6 build + oak-matched bark, BFS tip retract & lush caps."""
import math

import bmesh
import numpy as np
from mathutils import Vector

import vrlib
import vrmeshy
import vrtrees
import vrtrees_polish

TREE_CONFIG = {
    "asset_id": "tree_ancient_a",
    "template": "V3_TPL_tree_meadow_ancient",
    "target_size_m": (12.0, 13.0, 11.0),
    "expected_z_min": -0.65,
    "foliage_target": "#696F44",
    "foliage_strength": 0.80,
    "bark_target": "#41321D",
    "bark_strength": 0.36,
    "foliage_gamma": 0.78,
    "foliage_lift_floor": 0.035,
    "foliage_translucency": 0.220,
    "bark_boost": 1.36,
    "bark_floor": 0.012,
    "bark_translucency": 0.10,
    "alpha_cutoff": 0.34,
    "roughness_min": 0.65,
    "card_config": {
        "width_scale": 0.88,
        "length_scale": 0.88,
        "cup": 0.065,
        "twist_deg": 14.0,
        "arch": 0.035,
        "tilt": True,
        "tilt_threshold": 0.42,
        "tilt_min_deg": 7.0,
        "tilt_max_deg": 14.0,
        "upward_bias": 0.62,
        "seed": 9303,
    },
    "shelf_fold_config": {
        "max_cards": 28,
        "min_span": 2.05,
        "min_normal_z": 0.88,
        "pitch_min_deg": 26.0,
        "pitch_max_deg": 36.0,
        "cup": 0.105,
        "arch": 0.055,
        "seed": 9303,
    },
    "tip_trim_config": {
        "min_tip_distance": 0.14,
        "zmin": 2.8,
        "max_count": 24,
        "taper_start": 0.36,
        "end_radius": 0.015,
        "length_scale": 0.25,
    },
    "scaffold_retract_max": 8,
    "endpoint_fill_config": {
        "max_cards": 52,
        "scaffold_cards": 12,
        "seed": 9303,
    },
}


def _match_oak_bark_albedo(obj):
    """Calibrate bark basecolor median & variance to match approved tree_oak_a wood grain."""
    mats = [m for m in obj.data.materials if m and m.node_tree]
    if not mats:
        return
    bark_mat = mats[0]
    base_nodes = vrtrees._basecolor_texture_nodes(bark_mat)
    if not base_nodes:
        return
    img = base_nodes[0].image
    if img is None:
        return

    arr = vrmeshy._image_pixels(img).copy()
    rgb = arr[..., :3]
    cur_med = np.median(rgb, axis=(0, 1))
    rgb = cur_med + (rgb - cur_med) * 0.52
    target_med = np.array([0.345, 0.263, 0.161], dtype=np.float32)
    rgb = rgb * (target_med / np.maximum(cur_med, 1e-4))
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    safe_l = np.maximum(lum, 1e-5)
    clamped_l = np.clip(safe_l, 0.22, 0.45)
    scale = np.where((lum < 0.22) | (lum > 0.45), clamped_l / safe_l, 1.0)
    arr[..., :3] = np.clip(rgb * scale[..., None], 0.0, 1.0)

    new_img = vrmeshy._replace_image(img, arr, "_vr_bark_oakmatch")
    for node in bark_mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image == img:
            node.image = new_img


def _remove_disconnected_bark_stubs(obj):
    """Delete small disconnected bark shoot stubs (<= 50 polys, z > 1.5 m) and return their anchors."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bark_faces = [f for f in bm.faces if f.material_index == 0]
    parent = {f.index: f.index for f in bark_faces}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_v = {}
    for f in bark_faces:
        for v in f.verts:
            by_v.setdefault(v.index, []).append(f.index)
    for fids in by_v.values():
        for other in fids[1:]:
            union(fids[0], other)

    comps = {}
    for f in bark_faces:
        comps.setdefault(find(f.index), []).append(f)

    anchors = []
    to_delete = []
    for faces in comps.values():
        if len(faces) > 50:
            continue
        verts = list({v.index: v for f in faces for v in f.verts}.values())
        if not verts or min(v.co.z for v in verts) <= 1.5:
            continue
        centroid = sum((v.co for v in verts), Vector((0.0, 0.0, 0.0))) / len(verts)
        far_v = max(verts, key=lambda v: (v.co - centroid).length)
        axis = far_v.co - centroid
        if axis.length < 1e-5:
            axis = Vector((centroid.x, centroid.y, 0.35))
        axis = axis.normalized() if axis.length > 1e-5 else Vector((0.0, 0.0, 1.0))
        anchors.append((centroid.copy(), axis))
        to_delete.extend(faces)

    if to_delete:
        bmesh.ops.delete(bm, geom=to_delete, context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(me)
        me.update()
    bm.free()
    return anchors


def _blunt_terminal_bark_tips(obj):
    """BFS tip-cluster retract on sharp cones & sawed-off branch stubs (z >= 2.6 m) without ring inversion."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    fol_pts = np.array(
        [v.co[:] for f in bm.faces if f.material_index == 1 for v in f.verts],
        dtype=float,
    )
    if not len(fol_pts):
        bm.free()
        return []

    bark_v = list({v.index: v for f in bm.faces if f.material_index == 0 for v in f.verts}.values())
    cands = []
    for v in bark_v:
        if v.co.z < 2.6:
            continue
        r_xy = math.hypot(v.co.x, v.co.y)
        if v.co.z < 4.5 and r_xy <= 0.75:
            continue
        nbrs = [e.other_vert(v) for e in v.link_edges]
        if not nbrs:
            continue
        mean_nbr = sum((nv.co for nv in nbrs), Vector((0.0, 0.0, 0.0))) / len(nbrs)
        outward = v.co - mean_nbr
        if outward.length < 0.025:
            continue
        dn = outward.normalized()
        fwd = max((nv.co - v.co).dot(dn) for nv in nbrs)
        d_fol = float(np.sqrt(((fol_pts - np.array(v.co[:])) ** 2).sum(axis=1).min()))
        is_sharp = fwd <= 0.025 and d_fol > 0.14
        is_flat_stub = fwd <= 0.08 and d_fol > 0.10
        if not (is_sharp or is_flat_stub):
            continue
        cands.append((d_fol + (v.co.z - 2.6) * 0.08, v.index, v.co.copy(), dn))

    cands.sort(key=lambda item: -item[0])
    retracted = []
    used_verts = set()
    used_cos = []
    for _score, vi, origin_co, dn in cands:
        if vi >= len(bm.verts) or vi in used_verts or any((origin_co - u).length < 0.36 for u in used_cos):
            continue
        v0 = bm.verts[vi]
        cluster = {v0}
        queue = [v0]
        while queue:
            cur = queue.pop(0)
            for e in cur.link_edges:
                ov = e.other_vert(cur)
                if ov not in cluster and ov.index not in used_verts and (ov.co - origin_co).length <= 0.24:
                    cluster.add(ov)
                    queue.append(ov)
        outer_ring = {e.other_vert(u) for u in cluster for e in u.link_edges} - cluster
        if not outer_ring:
            continue
        outer_mean = sum((rv.co for rv in outer_ring), Vector((0.0, 0.0, 0.0))) / len(outer_ring)
        cone_len = max(0.0, (v0.co - outer_mean).dot(dn))
        if cone_len > 0.03:
            step = min(0.75, 0.65 * cone_len)
            for u in cluster:
                frac = min(max((u.co - outer_mean).dot(dn) / cone_len, 0.0), 1.0)
                u.co -= dn * (step * frac)
                used_verts.add(u.index)
        else:
            min_edge = min((e.other_vert(v0).co - v0.co).length for e in v0.link_edges)
            step = min(0.32, 0.55 * min_edge)
            for u in cluster:
                w_u = 1.0 if u is v0 else 0.45
                u.co -= dn * (step * w_u)
                used_verts.add(u.index)
        used_cos.append(origin_co)
        retracted.append((v0.co.copy(), dn))

    if retracted:
        bm.to_mesh(me)
        me.update()
    bm.free()
    return retracted


def _anchor_detached_foliage(obj):
    """Translate any detached outer foliage component (> 0.45 m from bark) rigidly to 0.08 m from its nearest twig."""
    me = obj.data
    bark_pts = np.array(
        [me.vertices[v].co[:] for p in me.polygons if p.material_index == 0 for v in p.vertices],
        dtype=float,
    )
    if not len(bark_pts):
        return
    moved = False
    for polys in vrtrees._foliage_components(me, 1):
        verts = sorted({v for p in polys for v in p.vertices})
        if not verts:
            continue
        pts = np.array([me.vertices[v].co[:] for v in verts], dtype=float)
        best_d = float("inf")
        best_fpt = None
        best_bpt = None
        for pt in pts:
            d2 = ((bark_pts - pt) ** 2).sum(axis=1)
            bi = int(np.argmin(d2))
            d = float(d2[bi] ** 0.5)
            if d < best_d:
                best_d = d
                best_fpt = pt
                best_bpt = bark_pts[bi]
        if best_d > 0.45:
            vec = Vector(best_bpt) - Vector(best_fpt)
            if vec.length > 1e-5:
                shift = vec.normalized() * (best_d - 0.08)
                for v in verts:
                    me.vertices[v].co += shift
                moved = True
    if moved:
        me.update()


def _cap_bare_branch_tips(obj, *, extra_anchors=(), seed=9306, max_tips=48):
    """Cover retracted tips, deleted-stub anchors, and exposed bark (z >= 2.6 m) with 3 overlapping tucked leaf cards."""
    me = obj.data
    bm_scan = bmesh.new()
    bm_scan.from_mesh(me)
    bm_scan.verts.ensure_lookup_table()
    fol_pts = np.array(
        [v.co[:] for f in bm_scan.faces if f.material_index == 1 for v in f.verts],
        dtype=float,
    )
    if not len(fol_pts):
        bm_scan.free()
        return

    cands = []
    for co, dn in extra_anchors:
        cands.append((2.0, co.copy(), dn.normalized()))

    bark_v = list({v.index: v for f in bm_scan.faces if f.material_index == 0 for v in f.verts}.values())
    for v in bark_v:
        r_xy = math.hypot(v.co.x, v.co.y)
        if v.co.z < 2.6:
            continue
        if v.co.z < 4.8 and r_xy <= 0.70:
            continue
        nbrs = [e.other_vert(v).co for e in v.link_edges]
        if not nbrs:
            continue
        d_fol = float(np.sqrt(((fol_pts - np.array(v.co[:])) ** 2).sum(axis=1).min()))
        if d_fol <= 0.12:
            continue
        mean_nbr = sum(nbrs, Vector((0.0, 0.0, 0.0))) / len(nbrs)
        outward = v.co - mean_nbr
        if outward.length > 0.02:
            dn = outward.normalized()
        else:
            fallback = v.co - Vector((0.0, 0.0, max(1.5, v.co.z - 0.8)))
            dn = fallback.normalized() if fallback.length > 0.05 else Vector((1.0, 0.0, 0.2)).normalized()
        is_terminal = not any((nco - v.co).dot(dn) > 0.04 for nco in nbrs)
        score = d_fol + (0.25 if is_terminal else 0.0)
        cands.append((score, v.co.copy(), dn))
    bm_scan.free()

    cands.sort(key=lambda item: -item[0])
    selected = []
    for _score, co, dn in cands:
        if any((co - prev_co).length < 0.34 for prev_co, _ in selected):
            continue
        selected.append((co, dn))
        if len(selected) >= max_tips:
            break

    if not selected:
        return

    bv = len(me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    zup = Vector((0.0, 0.0, 1.0))
    for ti, (tip, axis) in enumerate(selected):
        e1, e2 = vrtrees._orthogonal_frame(axis)
        radial = Vector((tip.x, tip.y, 0.0))
        radial = radial.normalized() if radial.length > 0.08 else Vector((axis.x, axis.y, 0.0))
        radial = radial.normalized() if radial.length > 1e-5 else Vector((1.0, 0.0, 0.0))
        for copy_no in range(3):
            h1 = vrtrees._hash01(ti, copy_no, 811, seed)
            h2 = vrtrees._hash01(ti, copy_no, 823, seed)
            h3 = vrtrees._hash01(ti, copy_no, 829, seed)
            h4 = vrtrees._hash01(ti, copy_no, 839, seed)
            side_sign = (0.0 if copy_no == 0 else (1.0 if copy_no == 1 else -1.0))
            side = e1 * side_sign + e2 * ((h2 - 0.5) * 0.85)
            side = side.normalized() if side.length > 1e-5 else e1
            if copy_no == 0:
                direction = axis * 0.58 + radial * 0.24 + zup * (0.42 + 0.14 * h1) + side * 0.18
            elif copy_no == 1:
                direction = axis * 0.42 - radial * 0.14 + zup * (0.48 + 0.14 * h1) + side * (0.45 + 0.16 * h3)
            else:
                direction = axis * 0.38 + radial * 0.16 + zup * (0.28 + 0.14 * h1) + side * (0.48 + 0.16 * h3)
            direction = direction.normalized() if direction.length > 1e-5 else zup.copy()
            if direction.z < 0.12:
                direction = (direction + zup * (0.12 - direction.z)).normalized()
            base = tip - axis * 0.22 + side * ((h4 - 0.5) * 0.06)
            u0, v0, u1, v1 = vrtrees._leaf_atlas_rect(seed + ti * 17 + copy_no * 5)
            uv_rect = (u0, v0 + 0.07 * (v1 - v0), u1, v1)
            vrtrees._append_leaf_card(
                bm,
                base,
                direction,
                width=0.78 + 0.27 * h1,
                length=0.88 + 0.27 * h2,
                seed=seed + ti * 31 + copy_no,
                uv_rect=uv_rect,
                cup=0.060 + 0.025 * h3,
                twist_deg=16.0 + 8.0 * h4,
                pinch=0.22,
            )
    bm.to_mesh(me)
    me.update()
    bm.free()
    vrtrees._set_new_blockcol_white(me, bv)


def _plug_root_gap(obj, *, r_bot=0.48, r_top=0.34, z_bot=-0.65, z_top=1.0, segs=12):
    """Add a closed tapered bark cylinder core inside the flared roots to stop daylight leaks."""
    me = obj.data
    bv = len(me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    uv_layer = bm.loops.layers.uv.active

    bot = []
    top = []
    for i in range(segs):
        ang = 2.0 * math.pi * i / segs
        ca, sa = math.cos(ang), math.sin(ang)
        bot.append(bm.verts.new((r_bot * ca, r_bot * sa, z_bot)))
        top.append(bm.verts.new((r_top * ca, r_top * sa, z_top)))

    for i in range(segs):
        j = (i + 1) % segs
        f = bm.faces.new((bot[i], bot[j], top[j], top[i]))
        f.material_index = 0
        f.smooth = True
        if uv_layer is not None:
            u0 = 0.25 + 0.50 * (i / segs)
            u1 = 0.25 + 0.50 * ((i + 1) / segs)
            vrtrees._write_face_uvs(f, uv_layer, ((u0, 0.25), (u1, 0.25), (u1, 0.75), (u0, 0.75)))

    f_bot = bm.faces.new(tuple(reversed(bot)))
    f_bot.material_index = 0
    f_bot.smooth = True
    f_top = bm.faces.new(tuple(top))
    f_top.material_index = 0
    f_top.smooth = True
    if uv_layer is not None:
        for fc in (f_bot, f_top):
            for loop in fc.loops:
                loop[uv_layer].uv = (0.50, 0.50)

    bm.to_mesh(me)
    me.update()
    bm.free()
    vrtrees._set_new_blockcol_white(me, bv)


def _fix_foliage_and_bark_normals(obj):
    """Set smooth area-weighted bark normals and align all foliage split normals within >= 0.45 of face normal."""
    me = obj.data
    me.update()
    for p in me.polygons:
        if p.material_index == 0:
            p.use_smooth = True
    vrtrees._smooth_bark_normals(me)

    out = [x.vector.copy() for x in me.corner_normals]
    for p in me.polygons:
        if p.material_index != 1:
            continue
        pn = p.normal.normalized() if p.normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            rad = Vector((co.x, co.y, 0.0))
            canopy = (
                (rad.normalized() * 0.50 + Vector((0.0, 0.0, 0.78))).normalized()
                if math.hypot(co.x, co.y) > 0.15
                else Vector((0.0, 0.0, 1.0))
            )
            canopy_aligned = canopy if canopy.dot(pn) >= 0.0 else -canopy
            out[li] = (pn * 0.55 + canopy_aligned * 0.45).normalized()
    me.normals_split_custom_set(out)
    me.update()


def build():
    vrtrees.build_tree(TREE_CONFIG)
    obj = vrlib.source_objects()[0]
    vrtrees_polish.clean_degenerate_faces(obj)
    _match_oak_bark_albedo(obj)
    stub_anchors = _remove_disconnected_bark_stubs(obj)
    retracted_anchors = _blunt_terminal_bark_tips(obj)
    _anchor_detached_foliage(obj)
    _cap_bare_branch_tips(obj, extra_anchors=stub_anchors + retracted_anchors, seed=9306, max_tips=48)
    _plug_root_gap(obj, r_bot=0.48, r_top=0.34, z_bot=-0.65, z_top=1.0)
    _fix_foliage_and_bark_normals(obj)
