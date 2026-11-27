"""Ufer-Weide A — subtractive-first R9.6 build + oak-matched bark, feathered curtains & crown-bridge ribbons."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import vrlib
import vrmeshy
import vrtrees
import vrtrees_polish

TREE_CONFIG = {
    "asset_id": "tree_willow_a",
    "template": "V3_TPL_tree_meadow_willow",
    "target_size_m": (9.2, 9.2, 8.3),
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
    "max_triangle_factor": 1.30,
    "card_config": {
        "width_scale": 1.18,
        "length_scale": 1.02,
        "cup": 0.045,
        "twist_deg": 12.0,
        "arch": 0.045,
        "tilt": False,
        "radial_sway": 0.08,
        "scale_jitter": 0.14,
        "attach_high": True,
        "taper_bottom": 0.45,
        "length_jitter": 0.14,
        "seed": 9404,
    },
    "tip_trim_config": {
        "min_tip_distance": 0.10,
        "zmin": 2.00,
        "max_count": 32,
        "taper_start": 0.32,
        "end_radius": 0.018,
        "length_scale": 0.24,
    },
    "scaffold_retract_max": 8,
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


def _feather_willow_foliage_top(obj):
    """Smoothly fade alpha across top brown-stem margin (v=0.88..0.96) to remove stem tips and straight quad edges."""
    mats = [m for m in obj.data.materials if m and m.node_tree]
    if len(mats) < 2:
        return
    fol_mat = mats[1]
    base_nodes = vrtrees._basecolor_texture_nodes(fol_mat)
    if not base_nodes:
        return
    img = base_nodes[0].image
    if img is None:
        return

    arr = vrmeshy._image_pixels(img).copy()
    h, w, _ = arr.shape
    vs = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    us = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    v_edge = 0.86 + 0.02 * np.sin(us * 18.0 * math.pi)
    fade_top = np.clip((0.91 - vs) / np.maximum(0.91 - v_edge, 1e-4), 0.0, 1.0)
    arr[..., 3] *= fade_top
    arr[vs[:, 0] > 0.91, :, 3] = 0.0
    u_margin = (us < 0.02) | (us > 0.98) | ((us > 0.49) & (us < 0.51))
    arr[:, u_margin[0, :], 3] = 0.0
    stem_mask = (vs >= 0.82) & (arr[..., 0] > arr[..., 1] * 0.95) & (arr[..., 1] < 0.38)
    arr[..., 3] = np.where(stem_mask, 0.0, arr[..., 3])

    new_img = vrmeshy._replace_image(img, arr, "_vr_willow_topfade")
    for node in fol_mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image == img:
            node.image = new_img


def _anchor_willow_curtains(obj):
    """Pull stray outer curtains (> 1.35 m from upper bark) rigidly inward onto branches."""
    me = obj.data
    bark_pts = np.array(
        [
            me.vertices[v].co[:]
            for p in me.polygons
            if p.material_index == 0
            for v in p.vertices
            if me.vertices[v].co.z > 2.2
        ],
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
        zmax = float(pts[:, 2].max())
        top_pts = pts[pts[:, 2] >= zmax - 0.35]
        top_c = top_pts.mean(axis=0)
        d2 = ((bark_pts - top_c) ** 2).sum(axis=1)
        bi = int(np.argmin(d2))
        d_bark = float(d2[bi] ** 0.5)
        if d_bark > 1.35:
            vec = Vector(bark_pts[bi]) - Vector(top_c)
            if vec.length > 1e-5:
                shift = vec.normalized() * (d_bark - 0.95)
                for v in verts:
                    me.vertices[v].co += shift
                moved = True
    if moved:
        me.update()


def _polish_willow_curtains(obj):
    """Bow curtains gently, curve upper roots inward, and preserve strict z(w) monotonicity with full native UVs."""
    me = obj.data
    for polys in vrtrees._foliage_components(me, 1):
        rows = vrtrees._component_rows(me, polys)
        if len(rows) < 4:
            continue

        verts = [v for v, _u, _w, _co in rows]
        pts = np.array([me.vertices[v].co[:] for v in verts], dtype=float)
        centre = Vector(pts.mean(axis=0))
        radial = Vector((centre.x, centre.y, 0.0))
        radial = radial.normalized() if radial.length > 1e-4 else Vector((1.0, 0.0, 0.0))

        pv0 = vrtrees._mean_row(rows, lambda u, w: w < 0.2)
        pv1 = vrtrees._mean_row(rows, lambda u, w: w > 0.8)
        increasing_z = pv1.z > pv0.z + 0.05

        for v, _u, w, _co in rows:
            co = me.vertices[v].co.copy()
            co += radial * (math.sin(w * math.pi) * 0.08)
            if w > 0.65:
                co -= radial * (0.16 * (((w - 0.65) / 0.35) ** 1.5))
            if co.z < 0.16:
                co.z = 0.16
            me.vertices[v].co = co

        if increasing_z:
            bands = {}
            for v, _u, w, _co in rows:
                bands.setdefault(round(w, 2), []).append(v)
            keys = sorted(bands.keys())
            if len(keys) >= 2:
                prev_max_z = max(me.vertices[v].co.z for v in bands[keys[0]])
                for k in keys[1:]:
                    for v in bands[k]:
                        if me.vertices[v].co.z < prev_max_z + 0.025:
                            me.vertices[v].co.z = prev_max_z + 0.025
                    prev_max_z = max(me.vertices[v].co.z for v in bands[k])

    me.update()


def _blunt_willow_fork_thorns(obj):
    """BFS tip-cluster blunt on exposed upper Y-branch bark thorns (z > 4.4 m)."""
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
        return

    bark_v = list({v.index: v for f in bm.faces if f.material_index == 0 for v in f.verts}.values())
    cands = []
    for v in bark_v:
        if v.co.z <= 3.0:
            continue
        nbrs = [e.other_vert(v) for e in v.link_edges]
        if not nbrs:
            continue
        mean_nbr = sum((nv.co for nv in nbrs), Vector((0.0, 0.0, 0.0))) / len(nbrs)
        outward = v.co - mean_nbr
        if outward.length < 0.025:
            continue
        dn = outward.normalized()
        if any((nv.co - v.co).dot(dn) > 0.03 for nv in nbrs):
            continue
        d_fol = float(np.sqrt(((fol_pts - np.array(v.co[:])) ** 2).sum(axis=1).min()))
        if d_fol <= 0.05:
            continue
        cands.append((d_fol, v.index, v.co.copy(), dn))

    cands.sort(key=lambda item: -item[0])
    used = set()
    moved = False
    for _d, vi, origin_co, dn in cands:
        if vi >= len(bm.verts) or vi in used:
            continue
        v0 = bm.verts[vi]
        cluster = {v0}
        queue = [v0]
        while queue:
            cur = queue.pop(0)
            for e in cur.link_edges:
                ov = e.other_vert(cur)
                if ov not in cluster and ov.index not in used and (ov.co - origin_co).length <= 0.24:
                    cluster.add(ov)
                    queue.append(ov)
        outer_ring = {e.other_vert(u) for u in cluster for e in u.link_edges} - cluster
        if not outer_ring:
            continue
        outer_mean = sum((rv.co for rv in outer_ring), Vector((0.0, 0.0, 0.0))) / len(outer_ring)
        cone_len = max(0.0, (v0.co - outer_mean).dot(dn))
        if cone_len < 0.02:
            continue
        step = min(0.65, 0.70 * cone_len)
        for u in cluster:
            frac = min(max((u.co - outer_mean).dot(dn) / cone_len, 0.0), 1.0)
            u.co -= dn * (step * frac)
            used.add(u.index)
        moved = True

    if moved:
        bm.to_mesh(me)
        me.update()
    bm.free()


def _cap_willow_crown(obj, *, seed=9406, max_forks=20):
    """Add full-strip strictly-monotonic weeping frond ribbons over exposed Y-forks and a raised crown dome."""
    me = obj.data
    fol_pts = np.array(
        [me.vertices[v].co[:] for p in me.polygons if p.material_index == 1 for v in p.vertices],
        dtype=float,
    )
    if not len(fol_pts):
        return

    bark_vids = sorted({v for p in me.polygons if p.material_index == 0 for v in p.vertices})
    cands = []
    for vi in bark_vids:
        co = me.vertices[vi].co
        if co.z <= 3.2:
            continue
        d_fol = float(np.sqrt(((fol_pts - np.array(co[:])) ** 2).sum(axis=1).min()))
        if d_fol <= 0.10:
            continue
        score = d_fol + max(0.0, co.z - 3.2) * 0.15
        cands.append((score, co.copy()))

    cands.sort(key=lambda item: -item[0])
    ribbons = []
    for _score, co in cands:
        if any((co - prev[0]).length < 0.36 for prev in ribbons):
            continue
        ribbons.append((co, False))
        if len(ribbons) >= max_forks:
            break

    # Explicitly crest the upper crown V-notch with 14 dome bridge ribbons above the z=7.37m arch
    for i in range(14):
        h1 = vrtrees._hash01(i, 311, seed)
        h2 = vrtrees._hash01(i, 317, seed)
        h3 = vrtrees._hash01(i, 331, seed)
        ang = i * (2.0 * math.pi / 14.0) + 0.25 * h1
        x_c = -0.35 + (0.35 + 1.15 * h2) * math.cos(ang)
        y_c = -0.25 + (0.30 + 0.90 * h2) * math.sin(ang)
        anchor = Vector((x_c, y_c, 7.35 + 0.50 * h3))
        ribbons.append((anchor, True))

    # Targeted drapes over remaining raycasted bare tips (mid/lower-left stubs & upper-right fork)
    ribbons.extend([
        (Vector((2.55, 0.75, 4.22)), False),
        (Vector((2.25, 0.65, 3.76)), False),
        (Vector((-1.85, -0.45, 7.45)), True),
        (Vector((-2.20, -0.40, 7.42)), True),
        (Vector((-1.50, -0.15, 7.32)), True),
    ])

    if not ribbons:
        return

    bv = len(me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    uv_layer = bm.loops.layers.uv.active
    width_profile = (0.45, 1.00, 0.92, 0.82, 0.72)

    for fi, (fork_co, is_bridge) in enumerate(ribbons):
        h1 = vrtrees._hash01(fi, 101, seed)
        h2 = vrtrees._hash01(fi, 103, seed)
        h3 = vrtrees._hash01(fi, 107, seed)
        h4 = vrtrees._hash01(fi, 109, seed)

        rad = Vector((fork_co.x, fork_co.y, 0.0))
        if rad.length > 0.12:
            radial = rad.normalized()
        else:
            ang = 2.0 * math.pi * h1
            radial = Vector((math.cos(ang), math.sin(ang), 0.0))
        tangent = Vector((-radial.y, radial.x, 0.0)).normalized()

        width = (0.72 + 0.24 * h2) if is_bridge else (0.65 + 0.25 * h2)
        drape_len = (2.8 + 0.9 * h1) if is_bridge else (2.0 + 0.8 * h3)
        out_reach = (0.42 + 0.20 * h4) if is_bridge else (0.34 + 0.20 * h4)
        cup = 0.040 + 0.020 * h1
        u0, u1 = (0.008, 0.492) if (fi % 2 == 0) else (0.508, 0.992)

        origin = fork_co + Vector((0.0, 0.0, 0.14))
        lattice = {}
        for iv in range(5):
            t = iv / 4.0
            dz = -drape_len * (t ** 1.55)
            out_r = out_reach * math.sin(min(t * 1.45, 1.0) * math.pi * 0.5) + 0.10 * t
            row_w = width * width_profile[iv]
            row_center = origin + radial * out_r + Vector((0.0, 0.0, dz))
            if row_center.z < 0.18:
                row_center.z = 0.18
            for iu in range(3):
                u = iu / 2.0
                centred = u - 0.5
                camber = (1.0 - centred * centred * 4.0) * cup * math.sin(math.pi * t)
                pos = row_center + tangent * (centred * row_w) + radial * camber
                lattice[(iu, iv)] = bm.verts.new(pos)

        for iv in range(4):
            for iu in range(2):
                keys = ((iu, iv), (iu + 1, iv), (iu + 1, iv + 1), (iu, iv + 1))
                face = bm.faces.new(tuple(lattice[k] for k in keys))
                face.material_index = 1
                if uv_layer is not None:
                    uvs = [
                        (
                            u0 + (ku / 2.0) * (u1 - u0),
                            0.92 - 0.912 * (kv / 4.0),
                        )
                        for ku, kv in keys
                    ]
                    vrtrees._write_face_uvs(face, uv_layer, uvs)

    bm.to_mesh(me)
    me.update()
    bm.free()
    vrtrees._set_new_blockcol_white(me, bv)


def _fix_foliage_and_bark_normals(obj):
    """Set smooth area-weighted bark normals and smooth per-component foliage normals (no quad seams)."""
    me = obj.data
    me.update()
    for p in me.polygons:
        if p.material_index == 0:
            p.use_smooth = True
    vrtrees._smooth_bark_normals(me)

    out = [x.vector.copy() for x in me.corner_normals]
    for polys in vrtrees._foliage_components(me, 1):
        if not polys:
            continue
        ref_n = polys[0].normal.normalized() if polys[0].normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
        v_acc = {}
        for p in polys:
            pn = p.normal.normalized() if p.normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
            aligned = pn if pn.dot(ref_n) >= 0.0 else -pn
            w_area = max(p.area, 1e-6)
            for vi in p.vertices:
                v_acc[vi] = v_acc.get(vi, Vector((0.0, 0.0, 0.0))) + aligned * w_area
        for p in polys:
            pn = p.normal.normalized() if p.normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
            for li in p.loop_indices:
                vi = me.loops[li].vertex_index
                vn = v_acc[vi].normalized() if v_acc[vi].length > 1e-6 else pn
                if vn.dot(pn) < 0.0:
                    vn = -vn
                co = me.vertices[vi].co
                rad = Vector((co.x, co.y, 0.0))
                canopy = (
                    (rad.normalized() * 0.50 + Vector((0.0, 0.0, 0.78))).normalized()
                    if math.hypot(co.x, co.y) > 0.15
                    else Vector((0.0, 0.0, 1.0))
                )
                canopy_aligned = canopy if canopy.dot(vn) >= 0.0 else -canopy
                n = (vn * 0.55 + canopy_aligned * 0.45).normalized()
                if n.dot(pn) < 0.30:
                    n = (n * 0.75 + pn * 0.25).normalized()
                out[li] = n
    me.normals_split_custom_set(out)
    me.update()


def _separate_coplanar_foliage(obj, min_dist=0.14):
    """Push apart near-coplanar overlapping foliage cards along face normal to stop raytraced Z-fighting."""
    me = obj.data
    info = []
    for polys in vrtrees._foliage_components(me, 1):
        verts = sorted({v for p in polys for v in p.vertices})
        if not verts:
            continue
        pts = np.array([me.vertices[v].co[:] for v in verts], dtype=float)
        ns = np.array([p.normal[:] for p in polys], dtype=float).mean(axis=0)
        n = Vector(ns).normalized() if np.linalg.norm(ns) > 1e-5 else Vector((1.0, 0.0, 0.0))
        info.append([verts, pts.mean(axis=0), n])
    moved = False
    for i in range(len(info)):
        for j in range(i + 1, len(info)):
            if np.linalg.norm(info[i][1] - info[j][1]) < min_dist and abs(info[i][2].dot(info[j][2])) > 0.75:
                shift = info[j][2] * 0.14
                for v in info[j][0]:
                    me.vertices[v].co += shift
                info[j][1] = info[j][1] + np.array(shift[:])
                moved = True
    if moved:
        me.update()


def build():
    vrtrees.build_tree(TREE_CONFIG)
    obj = vrlib.source_objects()[0]
    vrtrees_polish.clean_degenerate_faces(obj)
    _match_oak_bark_albedo(obj)
    _feather_willow_foliage_top(obj)
    _anchor_willow_curtains(obj)
    _polish_willow_curtains(obj)
    _blunt_willow_fork_thorns(obj)
    _cap_willow_crown(obj, seed=9406, max_forks=20)
    _separate_coplanar_foliage(obj)
    _fix_foliage_and_bark_normals(obj)
    bpy.context.scene.cycles.transparent_max_bounces = 32
