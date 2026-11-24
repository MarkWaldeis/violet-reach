"""Wiesen-Buche A — übernommene AAA-Tripo-Baumvorlage aus Fantasy open world.

Deterministischer Aufbau:
1. Verifiziert ``blender_reference/tripo_trees.blend`` per SHA-256 gegen das
   Staging-Manifest unter ``VR_MESHY_DIR/fantasy_open_world_import``.
2. Appendet nur ``V3_TPL_tree_meadow_beech`` (ein Mesh mit Materialslot 0 Rinde und
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
import numpy as np
from mathutils import Matrix, Vector

import vrlib
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = "V3_TPL_tree_meadow_beech"
SLUG = "tree_meadow_beech"
EXPECTED_Z_MIN = -0.65
TARGET_SIZE_M = (11.0, 12.0, 11.0)  # ungefähr, oberirdische Höhe im Quelltemplate
FOLIAGE_TARGET = "#4A5426"  # zwischen leaf_green #313C1D und grass_green #696F44
FOLIAGE_STRENGTH = 0.60
BARK_TARGET = "#41321D"
BARK_STRENGTH = 0.62
ALPHA_CUTOFF = 0.34
ROUGHNESS_MIN = 0.65
ASSET_KIND = "tree"
GEOMETRY_SEED = 9202
CARD_CONFIG = dict(width_scale=1.04, length_scale=1.01, cup=.32, twist_deg=28, arch=.16,
                   tilt=True, tilt_threshold=.46, tilt_min_deg=16, tilt_max_deg=32,
                   upward_bias=.72, radial_sway=0.0, scale_jitter=.07, seed=GEOMETRY_SEED)
BARK_TAPER_CONFIG = dict(max_faces=48, min_faces=32, taper_start=.80, end_radius=.12,
                         length_scale=1.0, seed=GEOMETRY_SEED)
FOLIAGE_GAMMA = .80
FOLIAGE_LIFT_FLOOR = .035
FOLIAGE_TRANSLUCENCY = .15
BARK_TRANSLUCENCY = .070


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
    obj.name = "tree_beech_a_source"
    obj.data.name = "tree_beech_a_source_mesh"
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
    scale_jitter=0.0,
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
        origin = pv0
        newpos = {}
        wscale = width_scale * (1.0 - scale_jitter + 2.0 * scale_jitter * h3) if scale_jitter else width_scale
        lscale = length_scale * (1.0 - scale_jitter + 2.0 * scale_jitter * h1) if scale_jitter else length_scale
        for v, u, w, co in rows:
            d = co - origin
            x = d.dot(uhat) * wscale
            y = d.dot(vhat) * lscale
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
            axis = uhat * (.75 + .5 * h4) + vhat * ((h1 - .5) * 1.2)
            if axis.length < 1e-5:
                axis = uhat.copy()
            axis.normalize()
            plus = (Matrix.Rotation(alpha, 4, axis) @ nhat).z
            minus = (Matrix.Rotation(-alpha, 4, axis) @ nhat).z
            want_up = h3 < upward_bias
            sign = 1.0 if ((plus >= minus) == want_up) else -1.0
            rotation = Matrix.Rotation(sign * alpha, 4, axis)
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
    seed=0,
):
    """Turn the detached 8-sided branchlet tubes' flat caps into tapered tips.

    The source templates close those tube pieces with a planar ring.  This pulls
    the last section radially toward the branch axis; optionally the whole small
    shoot is shortened first (used for the exposed bush sticks).  No vertices or
    triangles are added or removed.
    """
    faces = [p for p in mesh.polygons if p.material_index == 0]
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
    changed = 0
    pieces = 0
    for ci, polys in enumerate(comps.values()):
        if not (min_faces <= len(polys) <= max_faces):
            continue
        verts = sorted({v for p in polys for v in p.vertices})
        pts = np.array([mesh.vertices[v].co[:] for v in verts], dtype=float)
        if len(pts) < 8:
            continue
        centre = pts.mean(axis=0)
        cov = (pts - centre).T @ (pts - centre)
        vals, vecs = np.linalg.eigh(cov)
        axis = Vector(vecs[:, int(np.argmax(vals))])
        if axis.length < 1e-6:
            continue
        axis.normalize()
        if axis.z < 0:
            axis = -axis
        rel = pts - centre
        t = rel @ np.array(axis)
        tmin, tmax = float(t.min()), float(t.max())
        length = max(tmax - tmin, 1e-6)
        base_c = Vector(centre) + axis * tmin
        h = _hash01(ci, seed, 29)
        this_end_radius = end_radius * (.75 + .5 * h)
        this_start = taper_start - .04 * h
        this_length_scale = length_scale * (.92 + .16 * h) if length_scale < .999 else 1.0
        pieces += 1
        for v in verts:
            co = mesh.vertices[v].co
            tt = (co - base_c).dot(axis)
            q = tt / length
            if this_length_scale < .999:
                radial0 = co - (base_c + axis * tt)
                tt *= this_length_scale
                q *= this_length_scale
                co = base_c + axis * tt + radial0
                mesh.vertices[v].co = co
            if q <= this_start:
                continue
            centreline = base_c + axis * tt
            radial = co - centreline
            s = (q - this_start) / max(1.0 - this_start, 1e-6)
            s = min(max(s, 0.0), 1.0)
            s = s * s * (3.0 - 2.0 * s)
            factor = 1.0 + (this_end_radius - 1.0) * s
            mesh.vertices[v].co = centreline + radial * factor
            changed += 1
    mesh.update()
    return {"pieces": pieces, "vertices": changed}


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
        if longest or h3 < .18:
            length_scale = .985 + .030 * h1
            tip_delta = -.025 + .035 * h2
            arch_z = .008 + .018 * h4
            width_scale = 1.00 + .025 * h2
        elif h3 < .58:
            length_scale = .90 + .08 * h1
            tip_delta = .015 + .045 * h2
            arch_z = .015 + .020 * h4
            width_scale = 1.01 + .035 * h2
        else:
            length_scale = .80 + .09 * h1
            tip_delta = .050 + .045 * h2
            arch_z = .012 + .018 * h4
            width_scale = 1.02 + .04 * h2
        yaw = math.radians((h4 - .5) * 9.0)
        ca, sa = math.cos(yaw), math.sin(yaw)
        sway = (h2 - .5) * .07
        cup = .018 + .018 * h1
        for v, u, w, co in rows:
            d = co - base
            y = d.dot(dirh) * length_scale
            x = d.dot(side) * width_scale
            x += sway * math.sin(math.pi * w)
            z = co.z + tip_delta * w + arch_z * math.sin(math.pi * w)
            z += cup * .35 * math.sin(math.pi * u) * (0.5 + 0.5 * math.sin(math.pi * w))
            z = min(z, .525)
            xr = x * ca - y * sa
            yr = x * sa + y * ca
            mesh.vertices[v].co = base + side * xr + dirh * yr + Vector((0, 0, z - base.z))
            moved += 1
    mesh.update()
    return {"fronds": len(data), "vertices": moved, "max_reach": round(max_reach, 3)}


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
        fronds = _reshape_fern_fronds(mesh, seed=GEOMETRY_SEED)
        crown = _shrink_fern_crown(mesh)
        return {"fern_fronds": fronds, "root_crown": crown}
    cards = _reshape_foliage_cards(mesh, **CARD_CONFIG)
    tips = _taper_small_bark_tips(mesh, **BARK_TAPER_CONFIG)
    bark_normals = _smooth_bark_normals(mesh)
    normals = 0
    if ASSET_KIND == "tree":
        if "willow" in SLUG:
            normals = _recalc_foliage_normals(mesh, geom_weight=.58, up_weight=.32, radial_weight=.86)
        else:
            normals = _recalc_foliage_normals(mesh, geom_weight=.56, up_weight=.68, radial_weight=.72)
    # bush_lush_a keeps its authored canopy normals: they are already strongly
    # volume-biased and recalculation darkened the dense interior in diagnostics.
    return {"cards": cards, "tapered_tips": tips, "bark_normals": bark_normals, "foliage_normals": normals}


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
    if tris != int(template_info["tris"]):
        raise SystemExit(f"{TEMPLATE}: {tris} triangles, expected {template_info['tris']}")
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
        if abs(actual - target) / target > 0.06:
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
