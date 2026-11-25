"""Bodenfarn A — übernommene AAA-Tripo-Baumvorlage aus Fantasy open world.

Deterministischer Aufbau:
1. Verifiziert ``blender_reference/tripo_trees.blend`` per SHA-256 gegen das
   Staging-Manifest unter ``VR_MESHY_DIR/fantasy_open_world_import``.
2. Appendet nur ``V3_TPL_bush_lush_fern`` (ein Mesh mit Materialslot 0 Rinde und
   Slot 1 Laubkarten) inklusive der gepackten 1024²-Albedo/Normal/ORM-Texturen.
3. Gleicht Laub und Rinde materialgetrennt an die Violet-Reach-Palette an und
   verkabelt Alpha als echten glTF-Alpha-Masken-Test.
4. Erhält den vorhandenen Eingrabe-Sockel (z_min = -0,65 m), die UVs, das
   ``blockcol``-Farbattribut und die weichen benutzerdefinierten Kronennormalen.

Die externen Originaldateien werden ausschließlich gelesen. Alle Farbänderungen
entstehen als neue gepackte Bilder in dieser Asset-.blend.
"""
import hashlib
import json
import math
import os

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

import vrlib
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = "V3_TPL_bush_lush_fern"
SLUG = "bush_lush_fern"
EXPECTED_Z_MIN = -0.35
TARGET_SIZE_M = (2.0, 1.8, 0.5)  # ungefähr, oberirdische Höhe im Quelltemplate
FOLIAGE_TARGET = "#596536"  # zwischen leaf_green #313C1D und grass_green #696F44
FOLIAGE_STRENGTH = 0.65
BARK_TARGET = "#4A3320"
BARK_STRENGTH = 0.34
ALPHA_CUTOFF = 0.28
ROUGHNESS_MIN = 0.65
ASSET_KIND = "fern"
GEOMETRY_SEED = 9606
CARD_CONFIG = dict()
BARK_TAPER_CONFIG = dict()
FILL_CONFIG = dict(attach_high=False, fraction=1.0, second_fraction=1.0, third_fraction=.70,
                   width_range=(.66, .95), length_range=(.62, 1.00),
                   yaw_deg=44, pitch_deg=32, roll_deg=22,
                   normal_offset=.024, tangent_offset=.026,
                   inward_fraction=0.0, inward_pull=0.0, z_jitter=.034, seed=GEOMETRY_SEED)
ROOT_CONFIG = None
BRANCH_COLLARS = ()
SHOOT_COLLAR_CONFIG = None
TIP_CAP_CONFIG = None
FOLIAGE_GAMMA = .58
FOLIAGE_LIFT_FLOOR = .055
FOLIAGE_TRANSLUCENCY = .190
BARK_TRANSLUCENCY = .060


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _staging_root():
    return os.path.join(vrmeshy.meshy_dir(), "fantasy_open_world_import")


def _staging_paths():
    root = _staging_root()
    return {
        "root": root,
        "blend": os.path.join(root, "blender_reference", "tripo_trees.blend"),
        "manifest": os.path.join(root, "manifest.json"),
        "template_manifest": os.path.join(root, "blender_reference", "tripo_trees_manifest.json"),
        "leaf_textures": os.path.join(root, "leaf_textures"),
    }


def _verify_library(paths):
    with open(paths["manifest"], encoding="utf-8") as f:
        entries = json.load(f)["hashed_files"]
    expected = next(
        entry["sha256"] for entry in entries
        if entry["relative_path"] == "blender_reference/tripo_trees.blend"
    )
    actual = _sha256_file(paths["blend"])
    if actual != expected:
        raise SystemExit(
            f"{paths['blend']}: sha256 {actual} does not match staging manifest ({expected})"
        )
    with open(paths["template_manifest"], encoding="utf-8") as f:
        templates = json.load(f)["assets"]
    if TEMPLATE not in templates:
        raise SystemExit(f"{TEMPLATE} is missing in tripo_trees_manifest.json")
    return templates[TEMPLATE]


def _append_template(paths):
    before = set(bpy.data.objects)
    bpy.ops.wm.append(
        filepath=os.path.join(paths["blend"], "Object", TEMPLATE),
        directory=os.path.join(paths["blend"], "Object"),
        filename=TEMPLATE,
        link=False,
    )
    new = [o for o in bpy.data.objects if o not in before]
    obj = next((o for o in new if o.type == "MESH" and o.name.split(".")[0] == TEMPLATE), None)
    if obj is None:
        raise SystemExit(f"appending {TEMPLATE} produced no matching mesh object")
    for extra in new:
        if extra is not obj:
            bpy.data.objects.remove(extra, do_unlink=True)
    obj.name = "fern_lush_a_source"
    obj.data.name = "fern_lush_a_source_mesh"
    return obj


def _verify_packed_textures(paths, template_info):
    """The .blend pins the packed PNG bytes; compare them with the read-only provenance copies."""
    problems = []
    for image_name in template_info["textures"]:
        image = bpy.data.images.get(image_name)
        png = os.path.join(paths["leaf_textures"], image_name + ".png")
        if image is None:
            problems.append(f"missing appended image {image_name}")
            continue
        if not image.packed_file:
            problems.append(f"{image_name} is not packed")
            continue
        if not os.path.isfile(png):
            problems.append(f"provenance texture missing: {png}")
            continue
        packed_hash = hashlib.sha256(bytes(image.packed_file.data)).hexdigest()
        file_hash = _sha256_file(png)
        if packed_hash != file_hash:
            problems.append(f"{image_name}: packed sha256 {packed_hash} != file {file_hash}")
    if problems:
        raise SystemExit("texture verification failed:\n  - " + "\n  - ".join(problems))


def _materials(obj):
    return [m for m in obj.data.materials if m and m.node_tree]


def _principled(mat):
    return mat.node_tree.nodes.get("Principled BSDF")


def _basecolor_texture_nodes(mat):
    bsdf = _principled(mat)
    nodes = []
    if bsdf is None:
        return nodes
    for link in bsdf.inputs["Base Color"].links:
        node = link.from_node
        if node.type == "TEX_IMAGE" and node.image and node not in nodes:
            nodes.append(node)
    return nodes


def _grade_material_basecolor(mat, target_hex, strength, suffix):
    """vrmeshy.grade_basecolor logic, scoped to one material instead of the whole object."""
    h = target_hex.lstrip("#")
    target = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)
    tgt_hsv = vrmeshy._rgb_to_hsv(target.reshape(1, 1, 3))[0, 0]
    made = {}
    for node in _basecolor_texture_nodes(mat):
        img = node.image
        if img in made:
            continue
        px = vrmeshy._image_pixels(img)
        mask = px[..., 3] > 0.5
        if not mask.any():
            mask = np.ones(px.shape[:2], dtype=bool)
        hsv = vrmeshy._rgb_to_hsv(px[..., :3])
        sample = hsv[mask]
        mean_hue = math.atan2(
            np.sin(sample[:, 0] * 2 * math.pi).mean(),
            np.cos(sample[:, 0] * 2 * math.pi).mean(),
        ) / (2 * math.pi) % 1.0
        med_s, med_v = np.median(sample[:, 1]), np.median(sample[:, 2])
        dh = ((tgt_hsv[0] - mean_hue + 0.5) % 1.0) - 0.5
        hsv[..., 0] = (hsv[..., 0] + dh * strength) % 1.0
        hsv[..., 1] = np.clip(hsv[..., 1] + (tgt_hsv[1] - med_s) * strength, 0, 1)
        hsv[..., 2] = np.clip(hsv[..., 2] + (tgt_hsv[2] - med_v) * strength, 0, 1)
        made[img] = vrmeshy._replace_image(
            img,
            np.concatenate([vrmeshy._hsv_to_rgb(hsv), px[..., 3:]], -1),
            suffix,
        )
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image in made:
            node.image = made[node.image]
    return [img.name for img in made.values()]


def _hash01(*vals):
    x = 0.0
    for i, v in enumerate(vals):
        x += math.sin((i + 1) * 127.1 + float(v) * 311.7) * 43758.5453
    return x - math.floor(x)


def _foliage_components(mesh, material_index=1):
    """Connected foliage-card islands; the templates keep every 3x3 card separate."""
    faces = [p for p in mesh.polygons if p.material_index == material_index]
    parent = {p.index: p.index for p in faces}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_vertex = {}
    for p in faces:
        for v in p.vertices:
            by_vertex.setdefault(v, []).append(p.index)
    for ids in by_vertex.values():
        for other in ids[1:]:
            union(ids[0], other)
    comps = {}
    for p in faces:
        comps.setdefault(find(p.index), []).append(p)
    return list(comps.values())


def _component_rows(mesh, polys):
    uvlay = mesh.uv_layers.active
    raw = {}
    for p in polys:
        for li in p.loop_indices:
            v = mesh.loops[li].vertex_index
            raw.setdefault(v, []).append(uvlay.data[li].uv.copy())
    uvs = {}
    for v, vals in raw.items():
        uv = Vector((0, 0))
        for val in vals:
            uv += val
        uvs[v] = uv / len(vals)
    us = [uv.x for uv in uvs.values()]
    vs = [uv.y for uv in uvs.values()]
    umin, umax = min(us), max(us)
    vmin, vmax = min(vs), max(vs)
    rows = []
    for v, uv in uvs.items():
        u = (uv.x - umin) / max(umax - umin, 1e-8)
        w = (uv.y - vmin) / max(vmax - vmin, 1e-8)
        rows.append((v, u, w, mesh.vertices[v].co.copy()))
    return rows


def _mean_row(rows, pred):
    pts = [co for v, u, w, co in rows if pred(u, w)]
    if not pts:
        return Vector((0, 0, 0))
    acc = Vector((0, 0, 0))
    for co in pts:
        acc += co
    return acc / len(pts)


def _reshape_foliage_cards(
    mesh,
    *,
    width_scale,
    length_scale,
    cup,
    twist_deg,
    arch,
    tilt,
    tilt_threshold=0.55,
    tilt_min_deg=12.0,
    tilt_max_deg=25.0,
    upward_bias=0.70,
    radial_sway=0.0,
    seed=0,
):
    """Bend and re-pitch the template's flat 3x3 leaf cards without changing topology.

    The UV stem end is used as the approximate attachment edge.  Width cupping,
    progressive twist and a restrained anti-shelf pitch break the large planar
    shelves while keeping the crown silhouette and triangle count intact.
    """
    comps = _foliage_components(mesh, 1)
    moved = 0
    tilted = 0
    for ci, polys in enumerate(comps):
        rows = _component_rows(mesh, polys)
        if len(rows) < 4:
            continue
        center = Vector((0, 0, 0))
        for v, u, w, co in rows:
            center += co
        center /= len(rows)
        pu0 = _mean_row(rows, lambda u, w: u < .2)
        pu1 = _mean_row(rows, lambda u, w: u > .8)
        pv0 = _mean_row(rows, lambda u, w: w < .2)
        pv1 = _mean_row(rows, lambda u, w: w > .8)
        au = pu1 - pu0
        av = pv1 - pv0
        if au.length < 1e-5 or av.length < 1e-5:
            continue
        uhat = au.normalized()
        vhat = av.normalized()
        nhat = uhat.cross(vhat)
        if nhat.length < 1e-5:
            continue
        nhat.normalize()
        h1 = _hash01(ci, 3, seed)
        h2 = _hash01(ci, 7, seed)
        h3 = _hash01(ci, 13, seed)
        h4 = _hash01(ci, 17, seed)
        cup_sign = 1.0 if h1 < .62 else -1.0
        twist = math.radians((h2 * 2.0 - 1.0) * twist_deg)
        arch_sign = 1.0 if h3 < .55 else -1.0
        origin = pv1 if attach_high else pv0
        newpos = {}
        for v, u, w, co in rows:
            d = co - origin
            x = d.dot(uhat) * width_scale
            y = d.dot(vhat) * length_scale
            z = d.dot(nhat)
            z += cup_sign * cup * math.sin(math.pi * u)
            z += arch_sign * arch * math.sin(math.pi * w)
            x += (h4 - .5) * cup * .35 * math.sin(math.pi * w)
            a = twist * (w - .5)
            ca, sa = math.cos(a), math.sin(a)
            x, z = ca * x - sa * z, sa * x + ca * z
            co2 = origin + uhat * x + vhat * y + nhat * z
            if radial_sway:
                radial = Vector((center.x, center.y, 0.0))
                if radial.length > 1e-5:
                    radial.normalize()
                    tangent = Vector((-radial.y, radial.x, 0.0))
                    direction = -radial if h2 < .58 else radial
                    offset = direction * (radial_sway * (.35 + .65 * w) * (.45 + h3))
                    offset += tangent * (h4 - .5) * radial_sway * .55 * math.sin(math.pi * w)
                    co2 += offset
            newpos[v] = co2
        rotation = None
        pivot = origin * .78 + center * .22
        if tilt and abs(nhat.z) > tilt_threshold:
            alpha = math.radians(tilt_min_deg + (tilt_max_deg - tilt_min_deg) * h2)
            plus = (Matrix.Rotation(alpha, 4, uhat) @ vhat).z
            minus = (Matrix.Rotation(-alpha, 4, uhat) @ vhat).z
            want_up = h3 < upward_bias
            sign = 1.0 if ((plus >= minus) == want_up) else -1.0
            rotation = Matrix.Rotation(sign * alpha, 4, uhat)
            tilted += 1
        for v, co2 in newpos.items():
            if rotation is not None:
                co2 = pivot + rotation @ (co2 - pivot)
            mesh.vertices[v].co = co2
            moved += 1
    mesh.update()
    return {"cards": len(comps), "vertices": moved, "tilted_cards": tilted}


def _recalc_foliage_normals(mesh, *, geom_weight=.56, up_weight=.68, radial_weight=.72):
    """Re-author canopy split normals after card deformation, retaining soft volume shading."""
    old = [x.vector.copy() for x in mesh.corner_normals]
    acc = [Vector((0, 0, 0)) for _ in mesh.vertices]
    for p in mesh.polygons:
        if p.material_index != 1:
            continue
        n = p.normal * p.area
        for v in p.vertices:
            acc[v] += n
    loop_poly = {}
    for p in mesh.polygons:
        for li in p.loop_indices:
            loop_poly[li] = p
    out = list(old)
    for li, loop in enumerate(mesh.loops):
        p = loop_poly[li]
        if p.material_index != 1:
            continue
        v = loop.vertex_index
        geom = acc[v].normalized() if acc[v].length > 1e-6 else Vector((0, 0, 1))
        co = mesh.vertices[v].co
        radial = Vector((co.x, co.y, 0.0))
        if radial.length > .15:
            canopy = (radial.normalized() * radial_weight + Vector((0, 0, up_weight))).normalized()
        else:
            canopy = Vector((0, 0, 1))
        if geom.dot(canopy) < 0:
            geom = -geom
        out[li] = (geom * geom_weight + canopy * (1.0 - geom_weight)).normalized()
    mesh.normals_split_custom_set(out)
    mesh.update()
    return len(out)


def _taper_small_bark_tips(
    mesh,
    *,
    max_faces=48,
    min_faces=32,
    taper_start=.80,
    end_radius=.12,
    length_scale=1.0,
    bend=0.0,
    seed=0,
):
    """Orient, bend and close small loose shoot tubes at their real free ends."""
    comps = _material_components(mesh, 0)
    small_ids = {id(c) for c in comps if min_faces <= len(c["polys"]) <= max_faces}
    small = [c for c in comps if id(c) in small_ids]
    large_verts = sorted({v for c in comps if id(c) not in small_ids for v in c["verts"]})
    if not large_verts:
        large_verts = sorted({v for c in comps for v in c["verts"]})
    ref = np.array([mesh.vertices[v].co[:] for v in large_verts], dtype=float)
    changed = 0
    pieces = 0
    for ci, comp in enumerate(small):
        verts = comp["verts"]
        pts, centre, axis0, e0, e1, length0 = _component_pca(mesh, verts)
        if len(ref):
            d0 = float(((ref - np.array(e0)) ** 2).sum(axis=1).min())
            d1 = float(((ref - np.array(e1)) ** 2).sum(axis=1).min())
        else:
            d0, d1 = (0.0, 1.0) if e0.z < e1.z else (1.0, 0.0)
        if abs(d0 - d1) < 1e-5:
            score0 = e0.z + math.hypot(e0.x, e0.y) * .18
            score1 = e1.z + math.hypot(e1.x, e1.y) * .18
            base, tip = (e0, e1) if score1 >= score0 else (e1, e0)
        elif d0 <= d1:
            base, tip = e0, e1
        else:
            base, tip = e1, e0
        axis = tip - base
        if axis.length < 1e-5:
            continue
        axis.normalize()
        length = max((tip - base).length, 1e-6)
        h = _hash01(ci, seed, 29)
        this_end_radius = end_radius * (.70 + .55 * h)
        this_start = taper_start - .045 * h
        this_length_scale = length_scale * (.92 + .16 * h) if length_scale < .999 else 1.0
        side = axis.cross(Vector((0, 0, 1)))
        if side.length < 1e-5:
            side = Vector((1, 0, 0))
        side.normalize()
        if h < .5:
            side = -side
        upbend = axis.cross(side).normalized()
        bend_amount = bend * length * (.65 + .70 * h)
        pieces += 1
        for v in verts:
            original = mesh.vertices[v].co
            tt = max(0.0, (original - base).dot(axis))
            q = min(max(tt / length, 0.0), 1.0)
            axial = tt * this_length_scale
            centreline = base + axis * axial
            radial = original - (base + axis * tt)
            if q > this_start:
                s = (q - this_start) / max(1.0 - this_start, 1e-6)
                s = min(max(s, 0.0), 1.0)
                s = s * s * (3.0 - 2.0 * s)
                radial *= 1.0 + (this_end_radius - 1.0) * s
            curve = q * q * (3.0 - 2.0 * q)
            displacement = side * (bend_amount * curve)
            displacement += upbend * (bend_amount * .28 * math.sin(math.pi * q) * (h - .5) * 2.0)
            mesh.vertices[v].co = centreline + radial + displacement
            changed += 1
    mesh.update()
    return {"pieces": pieces, "vertices": changed}


def _material_components(mesh, material_index):
    """Connected polygon islands of one material, with vertex ids cached."""
    faces = [p for p in mesh.polygons if p.material_index == material_index]
    parent = {p.index: p.index for p in faces}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_vertex = {}
    for p in faces:
        for v in p.vertices:
            by_vertex.setdefault(v, []).append(p.index)
    for ids in by_vertex.values():
        for other in ids[1:]:
            union(ids[0], other)
    comps = {}
    for p in faces:
        comps.setdefault(find(p.index), []).append(p)
    out = []
    for polys in comps.values():
        out.append({
            "polys": polys,
            "poly_indices": [p.index for p in polys],
            "verts": sorted({v for p in polys for v in p.vertices}),
        })
    return out


def _component_pca(mesh, verts):
    pts = np.array([mesh.vertices[v].co[:] for v in verts], dtype=float)
    centre = pts.mean(axis=0)
    cov = (pts - centre).T @ (pts - centre)
    vals, vecs = np.linalg.eigh(cov)
    axis = Vector(vecs[:, int(np.argmax(vals))])
    if axis.length < 1e-6:
        axis = Vector((0, 0, 1))
    axis.normalize()
    rel = pts - centre
    t = rel @ np.array(axis)
    tmin, tmax = float(t.min()), float(t.max())
    length = max(tmax - tmin, 1e-6)
    end_band = length * .16
    e0 = pts[t <= tmin + end_band].mean(axis=0)
    e1 = pts[t >= tmax - end_band].mean(axis=0)
    return pts, Vector(centre), axis, Vector(e0), Vector(e1), length


def _leaf_card_features(mesh, *, material_index=1, attach_high=False):
    """Frames and attachment points of the separate foliage-card islands."""
    features = []
    for ci, comp in enumerate(_material_components(mesh, material_index)):
        rows = _component_rows(mesh, comp["polys"])
        if len(rows) < 4:
            continue
        pu0 = _mean_row(rows, lambda u, w: u < .2)
        pu1 = _mean_row(rows, lambda u, w: u > .8)
        pv0 = _mean_row(rows, lambda u, w: w < .18)
        pv1 = _mean_row(rows, lambda u, w: w > .82)
        au = pu1 - pu0
        av = pv1 - pv0
        if au.length < 1e-5 or av.length < 1e-5:
            continue
        uhat = au.normalized()
        vhat = av.normalized()
        nhat = uhat.cross(vhat)
        if nhat.length < 1e-5:
            continue
        nhat.normalize()
        center = Vector((0, 0, 0))
        for v, u, w, co in rows:
            center += co
        center /= len(rows)
        pts = np.array([co[:] for v, u, w, co in rows], dtype=float)
        span = float((pts.max(axis=0) - pts.min(axis=0)).max())
        base = pv1.copy() if attach_high else pv0.copy()
        far = pv0.copy() if attach_high else pv1.copy()
        features.append({
            "ci": ci, "rows": rows, "poly_indices": comp["poly_indices"], "verts": comp["verts"],
            "center": center, "base": base, "far": far,
            "uhat": uhat, "vhat": vhat, "nhat": nhat, "span": span,
        })
    return features


def _duplicate_foliage_clusters(
    mesh,
    *,
    attach_high=False,
    fraction=.55,
    second_fraction=0.0,
    third_fraction=0.0,
    width_range=(.55, .75),
    length_range=(.58, .80),
    yaw_deg=35,
    pitch_deg=25,
    roll_deg=20,
    normal_offset=.04,
    tangent_offset=.08,
    inward_fraction=0.0,
    inward_pull=0.0,
    z_jitter=0.0,
    seed=0,
):
    """Add smaller duplicated foliage-card geometry as anchored fans/inner-canopy fill."""
    features = _leaf_card_features(mesh, material_index=1, attach_high=attach_high)
    if not features:
        return {"copies": 0, "vertices": 0, "source_cards": 0}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm_faces = list(bm.faces)
    copies = 0
    copied_vertices = 0
    zup = Vector((0, 0, 1))
    for feat in features:
        ci = feat["ci"]
        count = (1 if _hash01(ci, 101, seed) < fraction else 0)
        count += (1 if _hash01(ci, 103, seed) < second_fraction else 0)
        count += (1 if _hash01(ci, 105, seed) < third_fraction else 0)
        if not count:
            continue
        faces = [bm_faces[i] for i in feat["poly_indices"] if i < len(bm_faces)]
        if not faces:
            continue
        geom = []
        seen = set()
        for f in faces:
            for item in [f] + list(f.edges) + list(f.verts):
                if item not in seen:
                    seen.add(item)
                    geom.append(item)
        pivot = feat["base"]
        uhat, vhat, nhat = feat["uhat"], feat["vhat"], feat["nhat"]
        for copy_no in range(count):
            res = bmesh.ops.duplicate(bm, geom=geom)
            newverts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
            newfaces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
            h1 = _hash01(ci, copy_no, 3, seed)
            h2 = _hash01(ci, copy_no, 7, seed)
            h3 = _hash01(ci, copy_no, 13, seed)
            h4 = _hash01(ci, copy_no, 17, seed)
            h5 = _hash01(ci, copy_no, 23, seed)
            h6 = _hash01(ci, copy_no, 29, seed)
            h7 = _hash01(ci, copy_no, 31, seed)
            ws = width_range[0] + (width_range[1] - width_range[0]) * h1
            ls = length_range[0] + (length_range[1] - length_range[0]) * h2
            if copy_no:
                ws *= .86 + .12 * h3
                ls *= .86 + .12 * h4
            yaw = math.radians((h3 * 2.0 - 1.0) * yaw_deg)
            pitch = math.radians((h4 * 2.0 - 1.0) * pitch_deg)
            roll = math.radians((h5 * 2.0 - 1.0) * roll_deg)
            rot = Matrix.Rotation(yaw, 3, zup)
            rot = rot @ Matrix.Rotation(pitch, 3, uhat)
            rot = rot @ Matrix.Rotation(roll, 3, vhat)
            radial = Vector((-pivot.x, -pivot.y, 0.0))
            if radial.length > 1e-5:
                radial.normalize()
            tangent = Vector((-radial.y, radial.x, 0.0)) if radial.length > 1e-5 else Vector((1, 0, 0))
            offset = nhat * ((h6 * 2.0 - 1.0) * normal_offset)
            offset += tangent * ((h7 * 2.0 - 1.0) * tangent_offset)
            if inward_pull and h5 < inward_fraction and radial.length > 1e-5:
                offset += radial * (inward_pull * (.55 + .75 * h1))
                offset += zup * ((h2 - .5) * z_jitter)
            elif z_jitter:
                offset += zup * ((h2 - .5) * z_jitter * .45)
            zscale = .82 + .30 * h6
            for v in newverts:
                d = v.co - pivot
                x = d.dot(uhat) * ws
                y = d.dot(vhat) * ls
                z = d.dot(nhat) * zscale
                v.co = pivot + rot @ (uhat * x + vhat * y + nhat * z) + offset
            for f in newfaces:
                f.material_index = 1
            copies += 1
            copied_vertices += len(newverts)
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"copies": copies, "vertices": copied_vertices, "source_cards": len(features)}


def _orthogonal_frame(axis):
    axis = axis.normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < .88 else Vector((0, 1, 0))
    e1 = axis.cross(ref)
    if e1.length < 1e-6:
        e1 = Vector((1, 0, 0))
    e1.normalize()
    e2 = axis.cross(e1).normalized()
    return e1, e2


def _set_bark_uvs(bm, faces, centre):
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return
    for f in faces:
        for lp in f.loops:
            co = lp.vert.co - centre
            ang = math.atan2(co.y, co.x) / (2.0 * math.pi) % 1.0
            lp[uv_layer].uv = (.06 + .88 * ang, .06 + .88 * ((co.z * .173) % 1.0))


def _finish_bm_faces(bm, faces, material_index, centre):
    for f in faces:
        f.material_index = material_index
    _set_bark_uvs(bm, faces, centre)


def _append_collar(bm, centre, axis, *, length, radius, sides=10, rings=5, seed=0,
                   material_index=0, oval=.88):
    """Append an irregular closed sleeve used as a branch/stem junction collar."""
    axis = axis.normalized()
    e1, e2 = _orthogonal_frame(axis)
    ring_verts = []
    phase1 = _hash01(seed, 3) * 2.0 * math.pi
    phase2 = _hash01(seed, 7) * 2.0 * math.pi
    for j in range(rings):
        t = j / max(rings - 1, 1)
        axial = (t - .5) * length
        profile = .36 + .64 * math.sin(math.pi * t)
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            organic = 1.0 + .075 * math.sin(3.0 * a + phase1 + j * .53) + .045 * math.sin(5.0 * a + phase2)
            rr = radius * profile * organic
            radial = e1 * (math.cos(a) * rr) + e2 * (math.sin(a) * rr * oval)
            ring.append(bm.verts.new(centre + axis * axial + radial))
        ring_verts.append(ring)
    faces = []
    for j in range(rings - 1):
        for i in range(sides):
            ni = (i + 1) % sides
            faces.append(bm.faces.new((ring_verts[j][i], ring_verts[j][ni],
                                       ring_verts[j + 1][ni], ring_verts[j + 1][i])))
    faces.append(bm.faces.new(tuple(reversed(ring_verts[0]))))
    faces.append(bm.faces.new(tuple(ring_verts[-1])))
    _finish_bm_faces(bm, faces, material_index, centre)
    return faces


def _append_tapered_tip(bm, base_centre, axis, *, length, radius, sides=8, seed=0,
                        material_index=0):
    """Append a closed, sharply tapered continuation over a blunt branch end."""
    axis = axis.normalized()
    e1, e2 = _orthogonal_frame(axis)
    profile = (1.0, .90, .66, .38, .12, .012)
    ring_verts = []
    phase = _hash01(seed, 11) * 2.0 * math.pi
    for j, pf in enumerate(profile):
        t = j / (len(profile) - 1)
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            organic = 1.0 + .045 * math.sin(3.0 * a + phase + j * .71)
            rr = max(radius * pf * organic, .0015 if j == len(profile) - 1 else 0.0)
            ring.append(bm.verts.new(base_centre + axis * (length * t) +
                                     (e1 * math.cos(a) + e2 * math.sin(a)) * rr))
        ring_verts.append(ring)
    faces = []
    for j in range(len(profile) - 1):
        for i in range(sides):
            ni = (i + 1) % sides
            faces.append(bm.faces.new((ring_verts[j][i], ring_verts[j][ni],
                                       ring_verts[j + 1][ni], ring_verts[j + 1][i])))
    faces.append(bm.faces.new(tuple(reversed(ring_verts[0]))))
    faces.append(bm.faces.new(tuple(ring_verts[-1])))
    _finish_bm_faces(bm, faces, material_index, base_centre)
    return faces


def _append_mound(bm, centre, *, radius, height, sides=18, rings=3, seed=0,
                  material_index=0):
    """Append a low irregular soil/root mound, open only at the buried underside."""
    centre = Vector(centre)
    phase1 = _hash01(seed, 5) * 2.0 * math.pi
    phase2 = _hash01(seed, 9) * 2.0 * math.pi
    ring_verts = []
    for j in range(1, rings + 1):
        rf = j / rings
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            organic = 1.0 + .20 * math.sin(3.0 * a + phase1) + .10 * math.sin(5.0 * a + phase2 + j)
            organic += .07 * math.sin(9.0 * a + phase1 * 1.7 + rf * 3.1)
            rr = radius * rf * organic
            dome = max(0.0, 1.0 - rf * rf) ** .68
            znoise = height * .30 * math.sin(4.0 * a + phase2 + rf * 2.1) * rf
            ring.append(bm.verts.new(centre + Vector((math.cos(a) * rr, math.sin(a) * rr,
                                                       height * dome + znoise))))
        ring_verts.append(ring)
    top = bm.verts.new(centre + Vector((0, 0, height * 1.03)))
    faces = []
    first = ring_verts[0]
    for i in range(sides):
        faces.append(bm.faces.new((top, first[i], first[(i + 1) % sides])))
    for j in range(len(ring_verts) - 1):
        inner = ring_verts[j]
        outer = ring_verts[j + 1]
        for i in range(sides):
            ni = (i + 1) % sides
            faces.append(bm.faces.new((inner[i], outer[i], outer[ni], inner[ni])))
    _finish_bm_faces(bm, faces, material_index, centre)
    return faces


def _estimate_trunk_center(mesh):
    ids = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    pts = np.array([mesh.vertices[v].co[:] for v in ids], dtype=float)
    if not len(pts):
        return Vector((0, 0, 0))
    cand = pts[(pts[:, 2] > .15) & (pts[:, 2] < 1.35)]
    if len(cand) < 8:
        cand = pts[pts[:, 2] < 2.0]
    centre = np.median(cand[:, :2], axis=0)
    for iteration in range(2):
        near = cand[np.hypot(cand[:, 0] - centre[0], cand[:, 1] - centre[1]) < 1.15]
        if len(near) >= 5:
            centre = np.median(near[:, :2], axis=0)
    return Vector((float(centre[0]), float(centre[1]), 0.0))


def _root_radius_bins(mesh, centre, sides):
    ids = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    pts = np.array([mesh.vertices[v].co[:] for v in ids], dtype=float)
    vals = [[] for _ in range(sides)]
    for p in pts:
        if not (-.06 <= p[2] <= .68):
            continue
        dx, dy = p[0] - centre.x, p[1] - centre.y
        r = math.hypot(dx, dy)
        if r < .05 or r > 3.2:
            continue
        k = int((math.atan2(dy, dx) + 2.0 * math.pi) % (2.0 * math.pi) / (2.0 * math.pi) * sides) % sides
        vals[k].append(r)
    populated = [max(v) if v else 0.0 for v in vals]
    fallback = float(np.median([r for r in populated if r > 0.0])) if any(r > 0.0 for r in populated) else .8
    for i in range(sides):
        if populated[i] <= 0.0:
            left = right = 0.0
            for step in range(1, sides):
                if populated[(i - step) % sides] > 0.0:
                    left = populated[(i - step) % sides]
                    break
            for step in range(1, sides):
                if populated[(i + step) % sides] > 0.0:
                    right = populated[(i + step) % sides]
                    break
            populated[i] = (left + right) * .5 if left and right else fallback
    for smooth_pass in range(2):
        populated = [(populated[(i - 1) % sides] + 2.0 * populated[i] + populated[(i + 1) % sides]) * .25
                     for i in range(sides)]
    return populated


def _append_root_flare(bm, mesh, centre, *, height, trunk_radius, min_flare, max_flare,
                       sides=24, seed=0):
    """Append a many-sided organic root collar that envelops the faceted root teeth."""
    bins = _root_radius_bins(mesh, centre, sides)
    ring_verts = []
    ring_count = 6
    for j in range(ring_count):
        t = j / (ring_count - 1)
        z = -.035 + t * height
        fall = (1.0 - t) ** 1.72
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            sampled = bins[i]
            base_r = min(max(sampled + .025, trunk_radius + min_flare), trunk_radius + max_flare)
            trunk_part = trunk_radius * (.91 + .12 * math.sin(math.pi * t))
            rr = trunk_part + max(0.0, base_r - trunk_radius * .94) * fall
            rr *= 1.0 + .035 * math.sin(5.0 * a + seed * .013 + j * .47)
            ring.append(bm.verts.new(Vector((centre.x + math.cos(a) * rr,
                                             centre.y + math.sin(a) * rr, z))))
        ring_verts.append(ring)
    faces = []
    for j in range(ring_count - 1):
        for i in range(sides):
            ni = (i + 1) % sides
            faces.append(bm.faces.new((ring_verts[j][i], ring_verts[j][ni],
                                       ring_verts[j + 1][ni], ring_verts[j + 1][i])))
    faces.append(bm.faces.new(tuple(reversed(ring_verts[0]))))
    _finish_bm_faces(bm, faces, 0, centre)
    return faces


def _small_shoot_data(mesh, min_faces=32, max_faces=48):
    comps = _material_components(mesh, 0)
    small_ids = {id(c) for c in comps if min_faces <= len(c["polys"]) <= max_faces}
    small = [c for c in comps if id(c) in small_ids]
    large_verts = sorted({v for c in comps if id(c) not in small_ids for v in c["verts"]})
    if not large_verts:
        large_verts = sorted({v for c in comps for v in c["verts"]})
    ref = np.array([mesh.vertices[v].co[:] for v in large_verts], dtype=float)
    data = []
    for ci, comp in enumerate(small):
        pts, centre, axis0, e0, e1, length = _component_pca(mesh, comp["verts"])
        if len(ref):
            d0 = float(((ref - np.array(e0)) ** 2).sum(axis=1).min())
            d1 = float(((ref - np.array(e1)) ** 2).sum(axis=1).min())
        else:
            d0, d1 = 0.0, 1.0
        base, tip = (e0, e1) if d0 <= d1 else (e1, e0)
        axis = tip - base
        if axis.length < 1e-5:
            continue
        axis.normalize()
        rel = pts - np.array(base)
        t = rel @ np.array(axis)
        perp = pts - (np.array(base) + t[:, None] * np.array(axis))
        radius = float(np.percentile(np.linalg.norm(perp, axis=1), 72))
        data.append({"ci": ci, "base": base, "axis": axis, "length": length, "radius": radius})
    return data


def _tip_cap_candidates(mesh, *, zmin, min_radius, cluster_radius, min_points, seed):
    ids = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    pts = np.array([mesh.vertices[v].co[:] for v in ids], dtype=float)
    if not len(pts):
        return []
    sel = pts[(pts[:, 2] > zmin) & (np.hypot(pts[:, 0], pts[:, 1]) > min_radius)]
    clusters = []
    for p in sel[np.argsort(-sel[:, 2])]:
        for c in clusters:
            if np.linalg.norm(p - c["centre"]) < cluster_radius:
                c["pts"].append(p)
                c["centre"] = np.mean(c["pts"], axis=0)
                break
        else:
            clusters.append({"pts": [p], "centre": p.copy()})
    out = []
    for ci, c in enumerate(clusters):
        pts_c = np.array(c["pts"], dtype=float)
        if len(pts_c) < min_points:
            continue
        centre = pts_c.mean(axis=0)
        cov = (pts_c - centre).T @ (pts_c - centre)
        vals, vecs = np.linalg.eigh(cov)
        axis0 = Vector(vecs[:, int(np.argmax(vals))])
        if axis0.length < 1e-6:
            continue
        axis0.normalize()
        t = (pts_c - centre) @ np.array(axis0)
        length = float(t.max() - t.min())
        if length < .16:
            continue
        band = length * .20
        e0 = Vector(pts_c[t <= t.min() + band].mean(axis=0))
        e1 = Vector(pts_c[t >= t.max() - band].mean(axis=0))
        score0 = e0.z + math.hypot(e0.x, e0.y) * .30
        score1 = e1.z + math.hypot(e1.x, e1.y) * .30
        base, tip = (e0, e1) if score1 >= score0 else (e1, e0)
        axis = tip - base
        if axis.length < 1e-5:
            continue
        axis.normalize()
        rel = pts_c - np.array(base)
        tt = rel @ np.array(axis)
        perp = pts_c - (np.array(base) + tt[:, None] * np.array(axis))
        radius = float(np.percentile(np.linalg.norm(perp, axis=1), 76))
        radius = min(max(radius * .82, .045), .15)
        out.append({"ci": ci, "tip": tip, "axis": axis, "radius": radius,
                    "hash": _hash01(ci, 47, seed)})
    return out


def _add_procedural_bark_geometry(mesh, *, seed=0, root=None, collars=(), shoot_collars=None,
                                  tip_caps=None):
    """Attach new bark geometry: root flare, joint collars and closed tapered tips."""
    centre = _estimate_trunk_center(mesh)
    shoot_data = _small_shoot_data(mesh) if shoot_collars else []
    cap_data = []
    if tip_caps:
        cap_args = {k: v for k, v in tip_caps.items()
                    if k in {"zmin", "min_radius", "cluster_radius", "min_points", "seed"}}
        cap_data = _tip_cap_candidates(mesh, **cap_args)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    made = {"root_flare": 0, "branch_collars": 0, "shoot_collars": 0, "tip_caps": 0}
    if root:
        made["root_flare"] = len(_append_root_flare(bm, mesh, centre, seed=seed, **root))
    for ci, cfg in enumerate(collars or ()):
        angle = math.radians(cfg["angle_deg"])
        radial = Vector((math.cos(angle), math.sin(angle), 0.0))
        axis = (radial + Vector((0, 0, cfg.get("up", .35)))).normalized()
        surface = cfg.get("surface_radius", .5) * cfg.get("surface_fraction", .72)
        base = Vector((centre.x + radial.x * surface, centre.y + radial.y * surface, cfg["z"]))
        ccentre = base + axis * (cfg["length"] * cfg.get("forward", .20))
        made["branch_collars"] += len(_append_collar(
            bm, ccentre, axis, length=cfg["length"], radius=cfg["radius"],
            sides=cfg.get("sides", 12), rings=6, seed=seed + ci * 17, oval=cfg.get("oval", .86)))
    if shoot_collars:
        for si, data in enumerate(shoot_data):
            if _hash01(data["ci"], 71, seed) > shoot_collars.get("fraction", 1.0):
                continue
            length = min(data["length"] * .48, max(data["radius"] * 5.2, .12))
            radius = max(data["radius"] * 1.55, .018)
            ccentre = data["base"] + data["axis"] * (length * .18)
            made["shoot_collars"] += len(_append_collar(
                bm, ccentre, data["axis"], length=length, radius=radius,
                sides=8, rings=5, seed=seed + 200 + si, oval=.82))
    if tip_caps:
        lo, hi = tip_caps.get("length_range", (.34, .54))
        for ci, data in enumerate(cap_data):
            length = lo + (hi - lo) * data["hash"]
            base = data["tip"] - data["axis"] * tip_caps.get("inset", .10)
            made["tip_caps"] += len(_append_tapered_tip(
                bm, base, data["axis"], length=length, radius=data["radius"],
                sides=8, seed=seed + 400 + ci))
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return made


def _scatter_fern_hearts(mesh, *, seed=0):
    """Move frond bases into three offset, imperfect heart clusters plus a few centre shoots."""
    features = _leaf_card_features(mesh, material_index=1, attach_high=False)
    if not features:
        return {"fronds": 0, "centres": []}
    base_mean = Vector((0, 0, 0))
    for f in features:
        base_mean += f["base"]
    base_mean /= len(features)
    heart_angles = (math.radians(18), math.radians(143), math.radians(266))
    heart_radii = (.270, .225, .300)
    heart_z = (.000, .038, -.018)
    hearts = []
    for a, r, hz in zip(heart_angles, heart_radii, heart_z):
        hearts.append(Vector((base_mean.x + math.cos(a) * r,
                              base_mean.y + math.sin(a) * r, base_mean.z + hz)))
    moved = 0
    used = []
    for feat in features:
        vec = feat["far"] - feat["base"]
        direction = Vector((vec.x, vec.y, 0.0))
        if direction.length < 1e-5:
            direction = Vector((1, 0, 0))
        direction.normalize()
        h1 = _hash01(feat["ci"], 101, seed)
        h2 = _hash01(feat["ci"], 107, seed)
        if h1 < .22:
            heart = base_mean + Vector(((h1 - .11) * .35, (h2 - .5) * .055, .012 + .020 * h2))
        else:
            ang = math.atan2(direction.y, direction.x)
            diffs = [abs((ang - a + math.pi) % (2.0 * math.pi) - math.pi) for a in heart_angles]
            hi = diffs.index(min(diffs))
            jitter_r = (h2 - .5) * .070
            jitter_a = (h1 - .5) * .26
            heart = hearts[hi] + Vector((math.cos(ang + jitter_a) * jitter_r,
                                         math.sin(ang + jitter_a) * jitter_r, 0.0))
        used.append(heart.copy())
        shift = heart - feat["base"]
        shift.z = heart.z - base_mean.z
        for v in feat["verts"]:
            mesh.vertices[v].co += shift
            moved += 1
    mesh.update()
    centres = []
    for co in sorted({(round(c.x, 3), round(c.y, 3), round(c.z, 3)) for c in used}):
        centres.append(co)
    return {"fronds": moved, "centres": centres, "base": tuple(round(x, 3) for x in base_mean)}


def _bury_fern_crown(mesh):
    """Remove the template's wooden above-ground crown plates outright.

    R3 only squashed the cylinder; the reviewer still read the flattened shell as
    faceted brown plates with a black core, and no amount of additional shrinking
    keeps the wide plates from peeking out beside the soil mound. The below-ground
    burial socket stays untouched; above ground the fern now consists of fronds,
    soil mound, heart nubs and rootlets only.
    """
    kill = [p.index for p in mesh.polygons
            if p.material_index == 0 and p.center.z > .002]
    if not kill:
        return {"vertices": 0, "faces_removed": 0}
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    doomed = [bm.faces[i] for i in kill if i < len(bm.faces)]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    # verwaiste Punkte der geloeschten Platten mit entfernen, aber nur solche ohne
    # verbleibende Flaeche (die Erdverankerung unter z=0 muss intakt bleiben)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"vertices": len(loose), "faces_removed": len(doomed)}


def _replace_fern_rootstock(mesh):
    """Remove all spike-like template bark and replace it by a low hidden rhizome."""
    bm=bmesh.new(); bm.from_mesh(mesh)
    doomed=[f for f in bm.faces if f.material_index==0]
    if doomed: bmesh.ops.delete(bm,geom=doomed,context="FACES")
    loose=[v for v in bm.verts if not v.link_faces]
    if loose: bmesh.ops.delete(bm,geom=loose,context="VERTS")
    uv=bm.loops.layers.uv.active
    zs=(-.350,-.240,-.100,-.006)
    rs=(.045,.055,.050,.035)
    sides=12; rings=[]; faces=[]
    for j,(z,r) in enumerate(zip(zs,rs)):
        ring=[]
        for i in range(sides):
            a=2*math.pi*i/sides
            rr=r*(1+.10*math.sin(3*a+j*.9)+.045*math.sin(7*a-j*.4))
            ring.append(bm.verts.new((math.cos(a)*rr,math.sin(a)*rr,z)))
        rings.append(ring)
    for j in range(len(zs)-1):
        for i in range(sides):
            ni=(i+1)%sides
            f=bm.faces.new((rings[j][i],rings[j][ni],rings[j+1][ni],rings[j+1][i])); f.material_index=0; faces.append(f)
            if uv:
                u0=i/sides; u1=(i+1)/sides
                for loop,co in zip(f.loops,((u0,j/3),(u1,j/3),(u1,(j+1)/3),(u0,(j+1)/3))): loop[uv].uv=co
    cap=bm.faces.new(tuple(reversed(rings[0]))); cap.material_index=0; faces.append(cap)
    cap=bm.faces.new(tuple(rings[-1])); cap.material_index=0; faces.append(cap)
    bm.to_mesh(mesh); mesh.update(); bm.free()
    return {"template_bark_faces":len(doomed),"rootstock_faces":len(faces)}


def _bezier_point(p0,p1,p2,p3,t):
    u=1.0-t
    return p0*(u**3)+p1*(3*u*u*t)+p2*(3*u*t*t)+p3*(t**3)


def _write_face_uvs(face,uv_layer,uvs):
    if uv_layer is not None:
        for loop,uv in zip(face.loops,uvs):
            loop[uv_layer].uv=uv


def _clear_template_foliage(mesh):
    """Remove the spider-like template ribbons before rebuilding the fern procedurally."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    doomed = [f for f in bm.faces if f.material_index == 1]
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"faces_removed": len(doomed), "loose_vertices": len(loose)}


def _append_fern_frond(bm, yaw, *, reach, base_z, arch, tip_z, width, seed,
                       atlas_half=0, segments=11):
    """Append one softly arching fern frond as a segmented tapered ribbon.

    UVs use one complete authored fern frond half-atlas, so the alpha texture stays
    leafy through the tip.  The centreline is a vertical-to-arching cubic Bezier and the
    three-vertex-wide ribbon is gently cambered rather than a flat angular strip.
    """
    radial = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    side = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    h1 = _hash01(seed, 601)
    h2 = _hash01(seed, 607)
    h3 = _hash01(seed, 613)
    p0 = radial * .018 + Vector((0, 0, base_z))
    p1 = radial * (reach * (.025 + .025 * h1)) + Vector((0, 0, base_z + arch * (.78 + .12 * h2)))
    p2 = radial * (reach * (.58 + .08 * h2)) + side * ((h3 - .5) * reach * .08) + Vector((0, 0, base_z + arch))
    p3 = radial * reach + side * ((h3 - .5) * reach * .16) + Vector((0, 0, tip_z))
    uv_layer = bm.loops.layers.uv.active
    if atlas_half:
        u0, u1 = .580, .820
    else:
        u0, u1 = .090, .320
    lattice = {}
    centres = []
    for j in range(segments):
        t = j / (segments - 1)
        centre = _bezier_point(p0, p1, p2, p3, t)
        # A small sideways oscillation breaks the comb-straight ribbon rhythm without
        # disturbing the overall drooping/arching habitus.
        centre += side * (math.sin(math.pi * t) * (h2 - .5) * reach * .055)
        centres.append(centre)
        width_here = width * (.82 + .18 * math.sin(math.pi * min(t * 1.35, 1.0))) * (1.0 - .30 * t)
        for iu in range(3):
            u = iu / 2.0
            centred = u - .5
            camber = (1.0 - centred * centred * 4.0) * (.018 + .018 * h1) * math.sin(math.pi * t)
            twist = (h3 - .5) * .045 * math.sin(math.pi * t)
            pos = centre + side * (centred * width_here + twist * math.sin(math.pi * t))
            pos += radial * camber + Vector((0, 0, camber * .35))
            lattice[(iu, j)] = bm.verts.new(pos)
    faces = []
    for j in range(segments - 1):
        t0 = j / (segments - 1)
        t1 = (j + 1) / (segments - 1)
        for iu in range(2):
            keys = ((iu, j), (iu + 1, j), (iu + 1, j + 1), (iu, j + 1))
            face = bm.faces.new(tuple(lattice[k] for k in keys))
            face.material_index = 1
            uvs = []
            for ku, kj in keys:
                uu = u0 + (ku / 2.0) * (u1 - u0)
                vv = .095 + (kj / (segments - 1)) * .890
                uvs.append((uu, vv))
            _write_face_uvs(face, uv_layer, uvs)
            faces.append(face)
    return faces


def _build_procedural_fern_rosette(mesh, *, seed=0):
    """Build the R5 fern from overlapping green fronds; no brown root spikes/core slab."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    layers = (
        # count, reach range, base z, arch range, tip z range, width range
        (16, (.86, 1.00), .014, (.27, .37), (.025, .105), (.300, .390)),
        (11, (.50, .73), .032, (.33, .45), (.095, .225), (.260, .340)),
        (8, (.28, .49), .052, (.38, .50), (.285, .455), (.210, .285)),
        (9, (.08, .22), .058, (.25, .36), (.155, .295), (.170, .240)),
    )
    made = 0
    fronds = 0
    index = 0
    for layer_no, (count, reaches, base_z, arches, tips, widths) in enumerate(layers):
        for k in range(count):
            h1 = _hash01(layer_no, k, 617, seed)
            h2 = _hash01(layer_no, k, 619, seed)
            h3 = _hash01(layer_no, k, 623, seed)
            h4 = _hash01(layer_no, k, 631, seed)
            # Even coverage with deterministic gaps/clumps; layers are phase-shifted so
            # their bases overlap into a green fibrous crown rather than a black cavity.
            yaw = 2.0 * math.pi * ((k + .18 * layer_no + (h1 - .5) * .42) / count)
            yaw += (h2 - .5) * .10
            reach = reaches[0] + (reaches[1] - reaches[0]) * h2
            arch = arches[0] + (arches[1] - arches[0]) * h3
            tip = tips[0] + (tips[1] - tips[0]) * h4
            width = widths[0] + (widths[1] - widths[0]) * h1
            faces = _append_fern_frond(bm, yaw, reach=reach, base_z=base_z + (h3 - .5) * .012,
                                       arch=arch, tip_z=tip, width=width,
                                       seed=seed + layer_no * 100 + k, atlas_half=(index + layer_no) % 2)
            made += len(faces)
            fronds += 1
            index += 1
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"fronds": fronds, "faces": made, "layers": len(layers)}


def _add_fern_root_mound(mesh, centre_data, *, seed=0):
    """Cover the buried core with a low soil/root mound, heart nubs and tapered surface roots."""
    if centre_data.get("base"):
        base = Vector(centre_data["base"])
    else:
        base = Vector((0, 0, .005))
    base.z = -.010
    centres = [Vector(c) for c in centre_data.get("centres", [])]
    bm = bmesh.new()
    bm.from_mesh(mesh)
    made = 0
    # Kein Erdkuppel-Plug und keine Herd-Nubs mehr: selbst flache, erodierte
    # braune Kuppeln lasen sich im Nahbereich weiterhin als schwebende braune
    # Scheiben/Pilze. Der Farn waechst jetzt schlicht aus dem Boden; die Wedel-
    # basis verdunkelt das Zentrum natuerlich. Nur die Oberflaechenwurzeln
    # bleiben als organische Verankerung.
    centres = centres[:0]
    for ri in range(7):
        a = 2.0 * math.pi * ri / 7.0 + (_hash01(ri, 83, seed) - .5) * .30
        radial = Vector((math.cos(a), math.sin(a), .05 + .06 * _hash01(ri, 89, seed))).normalized()
        start = base + Vector((math.cos(a) * .055, math.sin(a) * .055, .014))
        made += len(_append_tapered_tip(bm, start, radial, length=.16 + .06 * _hash01(ri, 97, seed),
                                        radius=.012 + .004 * _hash01(ri, 101, seed), sides=6,
                                        seed=seed + 120 + ri))
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"faces": made, "heart_nubs": min(len(centres), 8), "rootlets": 7}


def _reshape_fern_fronds(mesh, *, seed=0):
    """Make the fern rosette irregular while preserving its authored arching strips."""
    comps = _foliage_components(mesh, 1)
    data = []
    max_reach = 0.0
    for ci, polys in enumerate(comps):
        rows = _component_rows(mesh, polys)
        if len(rows) < 8:
            continue
        base = _mean_row(rows, lambda u, w: w < .15)
        tip = _mean_row(rows, lambda u, w: w > .85)
        vec = tip - base
        horiz = Vector((vec.x, vec.y, 0.0))
        if horiz.length < 1e-5:
            continue
        reach = horiz.length
        max_reach = max(max_reach, reach)
        data.append((ci, rows, base, horiz.normalized(), reach))
    moved = 0
    for ci, rows, base, dirh, reach in data:
        side = Vector((-dirh.y, dirh.x, 0.0))
        h1 = _hash01(ci, 3, seed)
        h2 = _hash01(ci, 7, seed)
        h3 = _hash01(ci, 13, seed)
        h4 = _hash01(ci, 17, seed)
        longest = reach > max_reach * .94
        if (longest and h3 < .38) or h3 < .06:
            length_scale = .86 + .15 * h1
            tip_delta = -.095 + .070 * h2
            arch_z = .100 + .050 * h4
            width_scale = .78 + .08 * h2
        elif h3 < .66:
            length_scale = .71 + .16 * h1
            tip_delta = -.045 + .045 * h2
            arch_z = .100 + .050 * h4
            width_scale = .82 + .08 * h2
        else:
            length_scale = .54 + .15 * h1
            tip_delta = -.010 + .040 * h2
            arch_z = .115 + .050 * h4
            width_scale = .84 + .08 * h2
        yaw = math.radians((h4 - .5) * 38.0)
        ca, sa = math.cos(yaw), math.sin(yaw)
        sway = (h2 - .5) * .16
        cup = .045 + .030 * h1
        pinch = .38 + .30 * h3
        zlift = (h1 - .5) * .045
        for v, u, w, co in rows:
            d = co - base
            y = d.dot(dirh) * length_scale
            x = d.dot(side) * width_scale
            taper_t = max(0.0, (w - .45) / .55)
            x *= 1.0 - pinch * taper_t * taper_t
            x += sway * math.sin(math.pi * w)
            z = co.z + tip_delta * w + arch_z * math.sin(math.pi * w)
            z += cup * .35 * math.sin(math.pi * u) * (0.5 + 0.5 * math.sin(math.pi * w))
            z += zlift * math.sin(math.pi * w)
            z = min(max(z, .004), .53)
            xr = x * ca - y * sa
            yr = x * sa + y * ca
            mesh.vertices[v].co = base + side * xr + dirh * yr + Vector((0, 0, z - base.z))
            moved += 1
    mesh.update()
    return {"fronds": len(data), "vertices": moved, "max_reach": round(max_reach, 3)}


def _compress_fern_frond_uvs(mesh, *, factor=.70):
    """Map frond tips back into the leafy part of the atlas instead of its bare stem end."""
    uvlay = mesh.uv_layers.active
    comps = _foliage_components(mesh, 1)
    changed = 0
    for polys in comps:
        loops = sorted({li for p in polys for li in p.loop_indices})
        if not loops:
            continue
        vmin = min(uvlay.data[li].uv.y for li in loops)
        for li in loops:
            uv = uvlay.data[li].uv
            uv.y = vmin + (uv.y - vmin) * factor
            changed += 1
    mesh.update()
    return {"loops": changed, "factor": factor}


def _shrink_fern_crown(mesh, *, z0=.018, height_scale=.24, radial_pull=.68):
    """Reduce the fern's cylindrical wooden centre to a low dark root crown."""
    verts = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    if not verts:
        return {"vertices": 0}
    pts = np.array([mesh.vertices[v].co[:] for v in verts], dtype=float)
    above = pts[pts[:, 2] > z0]
    if not len(above):
        return {"vertices": 0}
    centre = Vector((float(above[:, 0].mean()), float(above[:, 1].mean()), z0))
    zmax = float(above[:, 2].max())
    changed = 0
    for v in verts:
        co = mesh.vertices[v].co
        if co.z <= z0:
            continue
        q = (co.z - z0) / max(zmax - z0, 1e-6)
        horiz = Vector((co.x - centre.x, co.y - centre.y, 0.0))
        scale = 1.0 - radial_pull * q
        newz = z0 + (co.z - z0) * height_scale
        mesh.vertices[v].co = Vector((centre.x + horiz.x * scale, centre.y + horiz.y * scale, newz))
        changed += 1
    mesh.update()
    return {"vertices": changed}


def _smooth_bark_normals(mesh):
    """Use area-weighted smooth split normals on wood while leaving foliage loops untouched."""
    old = [x.vector.copy() for x in mesh.corner_normals]
    acc = [Vector((0, 0, 0)) for _ in mesh.vertices]
    for p in mesh.polygons:
        if p.material_index != 0:
            continue
        n = p.normal * p.area
        for v in p.vertices:
            acc[v] += n
    loop_poly = {}
    for p in mesh.polygons:
        for li in p.loop_indices:
            loop_poly[li] = p
    changed = 0
    for li, loop in enumerate(mesh.loops):
        p = loop_poly[li]
        if p.material_index != 0:
            continue
        v = loop.vertex_index
        if acc[v].length > 1e-6:
            old[li] = acc[v].normalized()
            changed += 1
    mesh.normals_split_custom_set(old)
    mesh.update()
    return changed


def _lift_foliage_albedo(mat, *, gamma, floor):
    """Lift linear-space dark leaf texels without flattening hue or leaf detail."""
    lifted = []
    for node in _basecolor_texture_nodes(mat):
        img = node.image
        px = vrmeshy._image_pixels(img)
        rgb = px[..., :3]
        lum = rgb @ np.array([.2126, .7152, .0722], dtype=np.float32)
        safe = np.maximum(lum, 1e-5)
        target = np.maximum(np.power(np.clip(safe, 0.0, 1.0), gamma), floor)
        rgb = np.clip(rgb * (target / safe)[..., None], 0.0, 1.0)
        out = np.concatenate([rgb, px[..., 3:]], -1)
        img.pixels.foreach_set(out.astype(np.float32).ravel())
        lifted.append(img.name)
    return lifted


def _wire_foliage_translucency(mat, strength):
    """Very weak exportable emission lift, standing in for leaf translucency.

    The value is deliberately far below bloom/glow intensity; it only keeps deep
    leaf shade olive and readable in the neutral review light.
    """
    if strength <= 0.0:
        return
    bsdf = _principled(mat)
    base_nodes = _basecolor_texture_nodes(mat)
    if bsdf is None or not base_nodes:
        return
    emission_color = bsdf.inputs["Emission Color"]
    for link in list(emission_color.links):
        mat.node_tree.links.remove(link)
    mat.node_tree.links.new(base_nodes[0].outputs["Color"], emission_color)
    bsdf.inputs["Emission Strength"].default_value = strength


def _apply_asset_geometry(obj):
    mesh = obj.data
    if ASSET_KIND == "fern":
        cleared = _clear_template_foliage(mesh)
        crown = _bury_fern_crown(mesh)
        rootstock = _replace_fern_rootstock(mesh)
        rosette = _build_procedural_fern_rosette(mesh, seed=GEOMETRY_SEED)
        bark_normals = _smooth_bark_normals(mesh)
        foliage_normals = _recalc_foliage_normals(mesh, geom_weight=.42, up_weight=.82, radial_weight=.24)
        return {"template_foliage_cleared": cleared, "root_crown": crown, "rootstock": rootstock,
                "procedural_rosette": rosette, "bark_normals": bark_normals,
                "foliage_normals": foliage_normals}
    cards = _reshape_foliage_cards(mesh, **CARD_CONFIG)
    fill = _duplicate_foliage_clusters(mesh, **FILL_CONFIG)
    tips = _taper_small_bark_tips(mesh, **BARK_TAPER_CONFIG)
    bark_geometry = _add_procedural_bark_geometry(
        mesh, seed=GEOMETRY_SEED, root=ROOT_CONFIG, collars=BRANCH_COLLARS,
        shoot_collars=SHOOT_COLLAR_CONFIG, tip_caps=TIP_CAP_CONFIG)
    bark_normals = _smooth_bark_normals(mesh)
    normals = 0
    return {"cards": cards, "cluster_fill": fill, "tapered_tips": tips,
            "procedural_bark": bark_geometry, "bark_normals": bark_normals,
            "foliage_normals": normals}


def _occlusion_group():
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
    if not any(socket.name == "Occlusion" for socket in group.interface.items_tree):
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return group


def _wire_orm_occlusion(mat):
    """Use the red ORM channel as glTF occlusion, avoiding a lossy self-AO rebake later."""
    sep = next((n for n in mat.node_tree.nodes if n.type == "SEPARATE_COLOR"), None)
    if sep is None:
        raise SystemExit(f"{mat.name}: no Separate Color ORM node found")
    group = _occlusion_group()
    existing = [n for n in mat.node_tree.nodes if n.type == "GROUP" and n.node_tree == group]
    occ = existing[0] if existing else mat.node_tree.nodes.new("ShaderNodeGroup")
    occ.node_tree = group
    for link in list(occ.inputs["Occlusion"].links):
        mat.node_tree.links.remove(link)
    mat.node_tree.links.new(sep.outputs["Red"], occ.inputs["Occlusion"])


def _configure_foliage_alpha(mat):
    bsdf = _principled(mat)
    base_nodes = _basecolor_texture_nodes(mat)
    if bsdf is None or not base_nodes:
        raise SystemExit(f"{mat.name}: foliage base colour texture not found")
    image_node = base_nodes[0]
    alpha_socket = bsdf.inputs["Alpha"]
    for link in list(alpha_socket.links):
        mat.node_tree.links.remove(link)
    clip = next((n for n in mat.node_tree.nodes if n.type == "MATH" and n.name.startswith("VR Alpha")), None)
    if clip is None:
        clip = mat.node_tree.nodes.new("ShaderNodeMath")
        clip.name = "VR Alpha Cutout"
    clip.operation = "GREATER_THAN"
    clip.inputs[1].default_value = ALPHA_CUTOFF
    for link in list(clip.inputs[0].links):
        mat.node_tree.links.remove(link)
    mat.node_tree.links.new(image_node.outputs["Alpha"], clip.inputs[0])
    mat.node_tree.links.new(clip.outputs[0], alpha_socket)
    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "HASHED"
    if hasattr(mat, "alpha_threshold"):
        mat.alpha_threshold = ALPHA_CUTOFF


def _configure_materials(obj, template_info):
    mats = {m.name.split(".")[0]: m for m in _materials(obj)}
    bark = mats.get(template_info["bark_material"])
    foliage = mats.get(template_info["foliage_material"])
    if bark is None or foliage is None:
        raise SystemExit(
            f"{TEMPLATE}: expected materials {template_info['materials']}, "
            f"got {[m.name for m in _materials(obj)]}"
        )
    vrmeshy.clamp_material([obj], roughness_min=ROUGHNESS_MIN, metallic=0.0)
    graded = {
        "bark": _grade_material_basecolor(bark, BARK_TARGET, BARK_STRENGTH, "_vr_bark"),
        "foliage": _grade_material_basecolor(foliage, FOLIAGE_TARGET, FOLIAGE_STRENGTH, "_vr_olive"),
    }
    lifted = _lift_foliage_albedo(foliage, gamma=FOLIAGE_GAMMA, floor=FOLIAGE_LIFT_FLOOR)
    if lifted:
        graded["foliage_lifted"] = lifted
    _wire_foliage_translucency(foliage, FOLIAGE_TRANSLUCENCY)
    # A much weaker floor on wood keeps shadowed twigs brown instead of colourless black.
    _wire_foliage_translucency(bark, BARK_TRANSLUCENCY)
    for mat in (bark, foliage):
        bsdf = _principled(mat)
        bsdf.inputs["Metallic"].default_value = 0.0
        _wire_orm_occlusion(mat)
    bark.use_backface_culling = True
    _configure_foliage_alpha(foliage)
    return graded


def _centre_footprint(obj):
    lo, hi = vrlib.world_bounds([obj])
    dx = -(lo.x + hi.x) * 0.5
    dy = -(lo.y + hi.y) * 0.5
    if abs(dx) > 1e-7 or abs(dy) > 1e-7:
        obj.matrix_world = Matrix.Translation((dx, dy, 0.0)) @ obj.matrix_world
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


def _validate_source(obj, template_info):
    me = obj.data
    tris = vrlib.triangle_count([obj])
    base_tris = int(template_info["tris"])
    if tris < base_tris:
        raise SystemExit(f"{TEMPLATE}: {tris} triangles, below verified template floor {base_tris}")
    if me.color_attributes.get(template_info["color_attribute"]) is None:
        raise SystemExit(f"{TEMPLATE}: color attribute {template_info['color_attribute']} is missing")
    if not getattr(me, "has_custom_normals", False) and me.attributes.get("custom_normal") is None:
        raise SystemExit(f"{TEMPLATE}: custom smooth canopy normals are missing")
    lo, hi = vrlib.world_bounds([obj])
    if abs(lo.z - EXPECTED_Z_MIN) > 0.025:
        raise SystemExit(f"{TEMPLATE}: z_min {lo.z:.3f}, expected about {EXPECTED_Z_MIN:.2f}; do not bury twice")
    size = hi - lo
    # The templates were already authored in the target corridor. Do not rescale them:
    # uniform rescaling would also shrink the existing underground burial socket.
    # TARGET_SIZE_M.z means the above-ground crown height (manifest z_max), while
    # the exported bounds necessarily include the negative burial socket too.
    actuals = (size.x, size.y, hi.z)
    for axis, actual, target in zip("XYZ", actuals, TARGET_SIZE_M):
        if abs(actual - target) / target > 0.12:
            raise SystemExit(f"{TEMPLATE}: {axis} size {actual:.3f} m outside ca. target {target:.3f} m")
    return tris


def build():
    paths = _staging_paths()
    template_info = _verify_library(paths)
    obj = _append_template(paths)
    _verify_packed_textures(paths, template_info)
    _centre_footprint(obj)
    geometry_info = _apply_asset_geometry(obj)
    graded = _configure_materials(obj, template_info)
    tris = _validate_source(obj, template_info)
    obj["fantasy_open_world_template"] = TEMPLATE
    obj["palette_grade"] = (
        f"foliage {FOLIAGE_TARGET}@{FOLIAGE_STRENGTH:.2f}, "
        f"bark {BARK_TARGET}@{BARK_STRENGTH:.2f}"
    )
    obj["graded_images"] = ",".join(graded["bark"] + graded["foliage"])
    obj["geometry_revision"] = json.dumps(geometry_info, sort_keys=True)
    # vrmeshy.fix_normals is deliberately not called: the hashed template already has
    # outward wood normals, and a blanket recalculation must not endanger the custom
    # smooth canopy split normals on the foliage cards.
    vrlib.link_to_source(obj)
    print(
        "VR_TREE_IMPORT",
        {"template": TEMPLATE, "triangles": tris, "graded": graded, "geometry": geometry_info},
        flush=True,
    )
