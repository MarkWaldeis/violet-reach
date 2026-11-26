"""Knorriger Altbaum A — übernommene AAA-Tripo-Baumvorlage aus Fantasy open world.

Deterministischer Aufbau:
1. Verifiziert ``blender_reference/tripo_trees.blend`` per SHA-256 gegen das
   Staging-Manifest unter ``VR_MESHY_DIR/fantasy_open_world_import``.
2. Appendet nur ``V3_TPL_tree_meadow_ancient`` (ein Mesh mit Materialslot 0 Rinde und
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
from mathutils.geometry import closest_point_on_tri

import vrlib
import vrmeshy

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = "V3_TPL_tree_meadow_ancient"
SLUG = "tree_meadow_ancient"
EXPECTED_Z_MIN = -0.65
TARGET_SIZE_M = (12.0, 13.0, 11.0)  # ungefähr, oberirdische Höhe im Quelltemplate
FOLIAGE_TARGET = "#696F44"  # grass_green, evidenzbasiert aus der R9-Materialprobe
FOLIAGE_STRENGTH = 0.80
BARK_TARGET = "#41321D"
BARK_STRENGTH = 0.36
ALPHA_CUTOFF = 0.34
ROUGHNESS_MIN = 0.65
ASSET_KIND = "tree"
GEOMETRY_SEED = 9303
# R9 subtractive-first: die authored 3x3-Laubsprays des Templates bleiben ganze
# zusammenhaengende Komponenten.  Nur eine sehr milde, topologieerhaltende Krümmung
# und ein selektiver 7–14°-Anti-Regal-Pitch auf bereits horizontalen Karten bleiben
# aktiv; es gibt weder Splitting/Shattering noch Scatter- oder Fill-Re-Placement.
SPLIT_CONFIG = dict(enabled=False, seed=GEOMETRY_SEED)
CARD_CONFIG = dict(width_scale=1.0, length_scale=1.0, cup=.035, twist_deg=8, arch=.015,
                   tilt=True, tilt_threshold=.42, tilt_min_deg=7, tilt_max_deg=14,
                   upward_bias=.62, radial_sway=0.0, scale_jitter=0.0, seed=GEOMETRY_SEED,
                   attach_high=False, scatter_deg=0.0, scatter_offset=0.0)
# R9.2: only the largest near-horizontal authored sprays receive a stronger connected
# pitch/fold.  This is deliberately selective; the global mild curl above remains the
# baseline instead of a random scatter or another planar-card shatter pass.
SHELF_FOLD_CONFIG = dict(max_cards=28, min_span=2.05, min_normal_z=.88,
                         pitch_min_deg=26, pitch_max_deg=36, cup=.105, arch=.055,
                         seed=GEOMETRY_SEED)
# At most 34 extra whole 3x3 leaf cards (+14.5% versus 234 authored clusters, +272
# triangles).  They are generated only at measured wood endpoints: two per badly exposed
# loose shoot endpoint and a small number on verified exposed scaffold terminals.
ENDPOINT_FILL_CONFIG = dict(max_cards=34, scaffold_cards=6, seed=GEOMETRY_SEED)
# Runde 6: deutlich staerkere Verkuerzung (.42 statt .68), frueher einsetzende
# Verjuengung und mehr Biegung, damit die nackten Speerspitzen als kurze beblaetterte
# Zweigenden in die Krone eingegliedert werden statt als schwarze Stacheln herauszuragen.
BARK_TAPER_CONFIG = dict(max_faces=48, min_faces=32, taper_start=.60, end_radius=.022,
                         length_scale=.42, bend=.12, seed=GEOMETRY_SEED)
FILL_CONFIG = dict(attach_high=False, fraction=1.0, second_fraction=1.0, third_fraction=.85,
                   width_range=(.66, .92), length_range=(.70, .95),
                   yaw_deg=56, pitch_deg=42, roll_deg=30,
                   normal_offset=.160, tangent_offset=.27,
                   inward_fraction=.34, inward_pull=.60, z_jitter=.26, seed=GEOMETRY_SEED)
# Runde 6: nahezu runder Querschnitt (oval .92), schmaeler aber deutlich dicker,
# frueheres und tieferes Abtauchen — die Wurzeln bleiben im sichtbaren Bereich dicke
# runde Schlaengelwurzeln und verschwinden unter der Erde, bevor sie spitz werden.
ROOT_CONFIG = dict(count=10, trunk_radius=.68, base_z=.55,
                   length_range=(1.05, 1.88), radius_range=(.15, .22),
                   bury_range=(.12, .24), sides=10, rings=9, oval=.94)
BRANCH_COLLARS = (
    dict(angle_deg=15, z=2.35, length=1.25, radius=.33, up=.28, surface_radius=.68),
    dict(angle_deg=120, z=2.55, length=1.30, radius=.34, up=.24, surface_radius=.68),
    dict(angle_deg=195, z=2.30, length=1.20, radius=.31, up=.30, surface_radius=.68),
    dict(angle_deg=255, z=2.70, length=1.35, radius=.35, up=.25, surface_radius=.68),
    dict(angle_deg=300, z=3.05, length=1.15, radius=.30, up=.33, surface_radius=.68),
)
SHOOT_COLLAR_CONFIG = None
TIP_CAP_CONFIG = dict(zmin=2.45, min_radius=1.05, cluster_radius=.78, min_points=4,
                      length_range=(.26, .46), inset=.10, seed=GEOMETRY_SEED,
                      dead_end=.30, max_caps=20, length_radius_mul=2.2, min_cap_radius=.065)
FOLIAGE_GAMMA = .78
FOLIAGE_LIFT_FLOOR = .035
FOLIAGE_TRANSLUCENCY = .220
BARK_TRANSLUCENCY = .088


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
    obj.name = "tree_ancient_a_source"
    obj.data.name = "tree_ancient_a_source_mesh"
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


def _split_foliage_cards(mesh, *, material_index=1, seed=0):
    """Split every 3x3-vertex template foliage card into four independent quad pieces.

    Each piece is re-mapped onto the card's full UV rectangle, so every piece shows
    the complete leaf-cluster texture at roughly half the card size.  The connected
    component size halves without any additional triangles, and the pieces can later
    be scattered independently, which breaks the large planar shelves.
    """
    uvlay = mesh.uv_layers.active
    comps = _material_components(mesh, material_index)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.active
    delete_verts = []
    split = 0
    skipped = 0
    # BMVert references must be captured before any new geometry is created,
    # because the bmesh index table goes stale on the first insertion.
    comp_bmverts = []
    for comp in comps:
        try:
            comp_bmverts.append([bm.verts[v] for v in comp["verts"]])
        except IndexError:
            comp_bmverts.append(None)
    for comp, bmverts in zip(comps, comp_bmverts):
        if len(comp["polys"]) != 8 or len(comp["verts"]) != 9 or bmverts is None:
            skipped += 1
            continue
        # Average UV per vertex, then lattice-rank the coordinates (the mid row is
        # not necessarily at the arithmetic centre, e.g. the willow template).
        uvavg = {}
        counts = {}
        for p in comp["polys"]:
            for li in p.loop_indices:
                v = mesh.loops[li].vertex_index
                uv = uvlay.data[li].uv
                if v not in uvavg:
                    uvavg[v] = Vector((0.0, 0.0))
                    counts[v] = 0
                uvavg[v] += Vector((uv.x, uv.y))
                counts[v] += 1
        for v in uvavg:
            uvavg[v] /= counts[v]
        us = sorted({round(uvavg[v].x, 3) for v in comp["verts"]})
        vs = sorted({round(uvavg[v].y, 3) for v in comp["verts"]})
        if len(us) != 3 or len(vs) != 3:
            skipped += 1
            continue
        lattice = {}
        for v in comp["verts"]:
            iu = min(range(3), key=lambda i: abs(us[i] - round(uvavg[v].x, 3)))
            iv = min(range(3), key=lambda i: abs(vs[i] - round(uvavg[v].y, 3)))
            lattice[(iu, iv)] = mesh.vertices[v].co.copy()
        if len(lattice) != 9:
            skipped += 1
            continue
        umin, umax = us[0], us[2]
        vmin, vmax = vs[0], vs[2]
        pu0 = (lattice[(0, 0)] + lattice[(0, 1)] + lattice[(0, 2)]) / 3.0
        pu1 = (lattice[(2, 0)] + lattice[(2, 1)] + lattice[(2, 2)]) / 3.0
        pv0 = (lattice[(0, 0)] + lattice[(1, 0)] + lattice[(2, 0)]) / 3.0
        pv1 = (lattice[(0, 2)] + lattice[(1, 2)] + lattice[(2, 2)]) / 3.0
        uhat = pu1 - pu0
        vhat = pv1 - pv0
        nhat = uhat.cross(vhat)
        if nhat.length < 1e-6:
            skipped += 1
            continue
        nhat.normalize()
        uvrect = {(0, 0): (umin, vmin), (1, 0): (umax, vmin),
                  (1, 1): (umax, vmax), (0, 1): (umin, vmax)}
        ok = True
        card_faces = []
        for cell in ((0, 0), (1, 0), (0, 1), (1, 1)):
            iu, iv = cell
            corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
            pts = [lattice[(iu + du, iv + dv)] for du, dv in corners]
            forward = (pts[1] - pts[0]).cross(pts[3] - pts[0])
            order = corners if forward.dot(nhat) >= 0 else list(reversed(corners))
            newverts = []
            for du, dv in order:
                pos = lattice[(iu + du, iv + dv)]
                nv = bm.verts.new(pos)
                nv.normal_update()
                newverts.append((nv, (du, dv)))
            try:
                face = bm.faces.new([nv for nv, key in newverts])
            except ValueError:
                ok = False
                break
            face.material_index = material_index
            for loop, (nv, key) in zip(face.loops, newverts):
                loop[uv_layer].uv = uvrect[key]
            card_faces.append(face)
        if not ok or len(card_faces) != 4:
            skipped += 1
            continue
        split += 1
        delete_verts.extend(bmverts)
    if delete_verts:
        bmesh.ops.delete(bm, geom=delete_verts, context="VERTS")
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"cards_split": split, "skipped": skipped, "pieces": split * 4}


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
    attach_high=False,
    scatter_deg=0.0,
    scatter_offset=0.0,
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
        scatter = None
        scatter_shift = Vector((0.0, 0.0, 0.0))
        if scatter_deg:
            beta = math.radians((h1 * 2.0 - 1.0) * scatter_deg)
            gamma = math.radians((h4 * 2.0 - 1.0) * scatter_deg * .8)
            # rotate around the piece centre so neighbouring split pieces diverge
            axis_s = uhat * (.6 + .8 * h2) + vhat * ((h3 - .5) * 1.4) + nhat * ((h1 - .5) * .8)
            if axis_s.length < 1e-5:
                axis_s = uhat.copy()
            axis_s.normalize()
            scatter = Matrix.Rotation(beta, 4, axis_s) @ Matrix.Rotation(gamma, 4, nhat)
            if scatter_offset:
                radial = Vector((center.x, center.y, 0.0))
                if radial.length > 1e-5:
                    radial.normalize()
                    tangent = Vector((-radial.y, radial.x, 0.0))
                else:
                    tangent = Vector((1.0, 0.0, 0.0))
                scatter_shift = tangent * ((h2 - .5) * 2.0 * scatter_offset)
                scatter_shift += nhat * ((h3 - .5) * 1.2 * scatter_offset)
                scatter_shift += Vector((0.0, 0.0, (h4 - .5) * 1.1 * scatter_offset))
        for v, co2 in newpos.items():
            if rotation is not None:
                co2 = pivot + rotation @ (co2 - pivot)
            if scatter is not None:
                co2 = center + scatter @ (co2 - center) + scatter_shift
            mesh.vertices[v].co = co2
            moved += 1
    mesh.update()
    return {"cards": len(comps), "vertices": moved, "tilted_cards": tilted}


def _fold_worst_shelf_cards(
    mesh,
    *,
    max_cards=28,
    min_span=2.05,
    min_normal_z=.88,
    pitch_min_deg=20.0,
    pitch_max_deg=31.0,
    cup=.105,
    arch=.055,
    seed=0,
):
    """Selectively pitch/fold only the largest horizontal authored leaf sprays.

    The 3x3 card lattice stays exactly connected: every vertex of a selected component
    is transformed as part of the same spray, and no face is split, duplicated or
    re-anchored.  The rigid pitch is strongest on the outer/radial direction (turning
    shelf-like cards into drooping broadleaf sprays), while a modest width/length fold
    removes the remaining billboard-flat read.
    """
    features = _leaf_card_features(mesh, material_index=1, attach_high=False)
    candidates = []
    for feat in features:
        flat = abs(feat["nhat"].z)
        if feat["span"] < min_span or flat < min_normal_z:
            continue
        candidates.append((feat["span"] * flat, feat))
    candidates.sort(key=lambda item: (-item[0], item[1]["ci"]))
    selected = [feat for score, feat in candidates[:max_cards]]
    moved = 0
    details = []
    zup = Vector((0, 0, 1))
    for rank, feat in enumerate(selected):
        rows = feat["rows"]
        center = feat["center"]
        uhat = feat["uhat"].copy()
        vhat = feat["vhat"].copy()
        nhat = feat["nhat"].copy()
        radial = Vector((center.x, center.y, 0.0))
        if radial.length > 1e-5:
            radial.normalize()
            tangent = Vector((-radial.y, radial.x, 0.0))
        else:
            radial = Vector((1.0, 0.0, 0.0))
            tangent = Vector((0.0, 1.0, 0.0))
        # Rotate about the card's own width axis.  Unlike a tangential projection this
        # remains exactly in the authored (already mildly curled) secant plane, so the
        # measured 26–36° pitch really reaches the worst shelf cards.  Orient the axis
        # only for deterministic sign selection; the sign itself is chosen by whether
        # the outward length direction moves downward.
        axis = uhat.copy()
        if axis.dot(tangent) < 0.0:
            axis = -axis
        axis.normalize()
        h1 = _hash01(feat["ci"], 601, seed)
        h2 = _hash01(feat["ci"], 607, seed)
        h3 = _hash01(feat["ci"], 613, seed)
        h4 = _hash01(feat["ci"], 619, seed)
        alpha = math.radians(pitch_min_deg + (pitch_max_deg - pitch_min_deg) * h1)
        outward_len = vhat.copy() if vhat.dot(radial) >= 0.0 else -vhat
        plus_z = (Matrix.Rotation(alpha, 4, axis) @ outward_len).z
        minus_z = (Matrix.Rotation(-alpha, 4, axis) @ outward_len).z
        sign = 1.0 if plus_z <= minus_z else -1.0
        rotation = Matrix.Rotation(sign * alpha, 4, axis)
        nrot = rotation @ nhat
        pivot = feat["base"] * .35 + center * .65
        fold_sign = 1.0 if h2 < .58 else -1.0
        arch_sign = 1.0 if h3 < .52 else -1.0
        this_cup = cup * (.78 + .44 * h2)
        this_arch = arch * (.76 + .48 * h3)
        droop = .030 + .045 * h4
        for v, u, w, co in rows:
            co2 = pivot + rotation @ (co - pivot)
            fold = fold_sign * this_cup * math.sin(math.pi * u)
            fold += arch_sign * this_arch * math.sin(math.pi * w)
            co2 += nrot * fold
            # A tiny world-down outer-edge droop keeps the rotated card botanical;
            # the quadratic falloff leaves the stem end attached and continuous.
            co2.z -= droop * max(0.0, w - .42) ** 2
            mesh.vertices[v].co = co2
            moved += 1
        details.append({
            "ci": feat["ci"], "span": round(feat["span"], 3),
            "normal_z": round(feat["nhat"].z, 3),
            "pitch_deg": round(math.degrees(alpha), 2),
        })
    if moved:
        mesh.update()
    return {"cards": len(selected), "vertices": moved, "selected": details}


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


def _taper_exposed_bark_tips(
    mesh,
    *,
    max_faces=48,
    min_faces=32,
    min_tip_distance=.20,
    zmin=4.55,
    max_count=16,
    taper_start=.38,
    end_radius=.025,
    length_scale=.27,
):
    """Subtractive, non-additive trim of only the most exposed loose shoot tubes.

    The templates contain a small number of disconnected 44-face bark shoot tubes.
    Most are already covered by nearby authored foliage.  This pass measures the free
    end of each tube against the existing foliage vertices and only shortens/tapers the
    few uncovered outliers; it creates no vertices, faces, caps, twigs or leaf mass and
    leaves covered shoots untouched.
    """
    comps = _material_components(mesh, 0)
    small = [c for c in comps if min_faces <= len(c["polys"]) <= max_faces]
    small_ids = {id(c) for c in small}
    large_verts = sorted({v for c in comps if id(c) not in small_ids for v in c["verts"]})
    if not large_verts:
        large_verts = sorted({v for c in comps for v in c["verts"]})
    foliage_verts = sorted({v for p in mesh.polygons if p.material_index == 1 for v in p.vertices})
    if not small or not large_verts or not foliage_verts:
        return {"pieces": 0, "vertices": 0, "candidates": []}
    ref = np.array([mesh.vertices[v].co[:] for v in large_verts], dtype=float)
    foliage_tris = []
    for poly in mesh.polygons:
        if poly.material_index != 1:
            continue
        ids = list(poly.vertices)
        for k in range(1, len(ids) - 1):
            foliage_tris.append((
                mesh.vertices[ids[0]].co.copy(),
                mesh.vertices[ids[k]].co.copy(),
                mesh.vertices[ids[k + 1]].co.copy(),
            ))

    def foliage_surface_distance(point):
        best = 999.0
        for a, b, c in foliage_tris:
            close = closest_point_on_tri(point, a, b, c)
            best = min(best, (close - point).length)
        return best

    candidates = []
    for ci, comp in enumerate(small):
        pts, centre, axis0, e0, e1, length0 = _component_pca(mesh, comp["verts"])
        d0 = float(((ref - np.array(e0)) ** 2).sum(axis=1).min())
        d1 = float(((ref - np.array(e1)) ** 2).sum(axis=1).min())
        base, tip = (e0, e1) if d0 <= d1 else (e1, e0)
        axis = tip - base
        if axis.length < 1e-5:
            continue
        axis.normalize()
        # A tip can be geometrically near one leaf triangle yet still read as a bare
        # black needle through alpha holes.  Sample the whole outer half so sustained
        # exposure, not one lucky contact, decides whether the tube is covered.
        sample_ts = (.50, .62, .75, .88, 1.0)
        sample_dists = [
            foliage_surface_distance(base + axis * (length0 * t)) for t in sample_ts
        ]
        foliage_dist = sample_dists[-1]
        mean_outer = sum(sample_dists) / len(sample_dists)
        high_open_sky = tip.z >= 8.35 and mean_outer >= .075 and axis.z > .35
        exposed = (mean_outer >= min_tip_distance * .55 or
                   foliage_dist >= min_tip_distance or high_open_sky)
        if tip.z < zmin or not exposed:
            continue
        rel = pts - np.array(base)
        tt_all = rel @ np.array(axis)
        perp = pts - (np.array(base) + tt_all[:, None] * np.array(axis))
        radius = float(np.percentile(np.linalg.norm(perp, axis=1), 72))
        radial_tip = math.hypot(tip.x, tip.y)
        score = mean_outer * 1.45 + foliage_dist
        score += max(0.0, tip.z - 5.2) * .035 + max(axis.z, 0.0) * .09 + radial_tip * .018
        candidates.append({
            "ci": ci, "comp": comp, "base": base, "tip": tip, "axis": axis.copy(),
            "length": length0, "foliage_dist": foliage_dist, "mean_outer": mean_outer,
            "radius": radius, "score": score,
        })
    candidates.sort(key=lambda c: (-c["score"], -c["tip"].z, c["ci"]))
    selected = candidates[:max_count]
    changed = 0
    details = []
    endpoints = []
    for item in selected:
        comp = item["comp"]
        base = item["base"]
        tip = item["tip"]
        axis = item["axis"]
        length = max((tip - base).length, 1e-6)
        exposure01 = min(max((item["mean_outer"] - .10) / .32, 0.0), 1.0)
        # R9.2: exposed sky needles collapse to short brown buds rather than metre-long
        # black spikes.  Better covered tubes keep a little more length; uncovered high
        # upright tubes receive the strongest subtraction.
        this_length_scale = length_scale * (.78 + .22 * (1.0 - exposure01))
        if tip.z > 8.5 and axis.z > .55:
            this_length_scale *= .88
        this_length_scale = max(.22, this_length_scale)
        for v in comp["verts"]:
            original = mesh.vertices[v].co
            tt = min(max((original - base).dot(axis), 0.0), length)
            q = tt / length
            projection = base + axis * tt
            radial = original - projection
            if q > taper_start:
                s = (q - taper_start) / max(1.0 - taper_start, 1e-6)
                s = s * s * (3.0 - 2.0 * s)
                radial *= 1.0 + (end_radius - 1.0) * s
            mesh.vertices[v].co = base + axis * (tt * this_length_scale) + radial
            changed += 1
        final_tip = base + axis * (length * this_length_scale)
        details.append({
            "component": item["ci"],
            "length": round(item["length"], 3),
            "foliage_distance": round(item["foliage_dist"], 3),
            "mean_outer_distance": round(item["mean_outer"], 3),
            "tip_z": round(item["tip"].z, 3),
            "length_scale": round(this_length_scale, 3),
        })
        endpoints.append({
            "component": item["ci"],
            "base": tuple(round(float(x), 4) for x in base),
            "axis": tuple(round(float(x), 4) for x in axis),
            "original_tip": tuple(round(float(x), 4) for x in tip),
            "tip": tuple(round(float(x), 4) for x in final_tip),
            "radius": round(item["radius"], 4),
            "score": round(item["score"], 4),
            "mean_outer_distance": round(item["mean_outer"], 4),
        })
    if changed:
        mesh.update()
    return {"pieces": len(selected), "vertices": changed, "candidates": details,
            "endpoints": endpoints}


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
        count += (1 if _hash01(ci, 107, seed) < third_fraction else 0)
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
            if copy_no >= 2:
                ws *= .80 + .10 * h4
                ls *= .80 + .10 * h3
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
            organic = 1.0 + .11 * math.sin(3.0 * a + phase1) + .055 * math.sin(5.0 * a + phase2 + j)
            rr = radius * rf * organic
            dome = max(0.0, 1.0 - rf * rf) ** .68
            znoise = height * .10 * math.sin(4.0 * a + phase2 + rf * 2.1) * rf
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
                       sides=24, seed=0, margin=.025, falloff=1.72):
    """Append a many-sided organic root collar that envelops the faceted root teeth."""
    bins = _root_radius_bins(mesh, centre, sides)
    ring_verts = []
    ring_count = 6
    for j in range(ring_count):
        t = j / (ring_count - 1)
        z = -.035 + t * height
        fall = (1.0 - t) ** falloff
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            sampled = bins[i]
            base_r = min(max(sampled + margin, trunk_radius + min_flare), trunk_radius + max_flare)
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


def _bury_template_root_plates(mesh):
    """Push the template's separate pleated root-collar insert fully below grade."""
    changed = 0
    buried = 0
    for comp in _material_components(mesh, 0):
        if not (70 <= len(comp["polys"]) <= 240):
            continue
        pts = np.array([mesh.vertices[v].co[:] for v in comp["verts"]], dtype=float)
        if not len(pts):
            continue
        zmin, zmax = float(pts[:, 2].min()), float(pts[:, 2].max())
        if zmin > -.20 or zmax < .25 or zmax > .95:
            continue
        for v in comp["verts"]:
            co = mesh.vertices[v].co
            if co.z > -.018:
                co.z = -.022 - (co.z + .018) * .48
                changed += 1
        buried += 1
    if changed:
        mesh.update()
    return {"components": buried, "vertices": changed}


def _bezier_point(p0, p1, p2, p3, t):
    u = 1.0 - t
    return p0 * (u ** 3) + p1 * (3.0 * u * u * t) + p2 * (3.0 * u * t * t) + p3 * (t ** 3)


def _write_face_uvs(face, uv_layer, uvs):
    if uv_layer is not None:
        for loop, uv in zip(face.loops, uvs):
            loop[uv_layer].uv = uv


def _append_curved_tube(bm, points, radii, *, sides=6, seed=0, material_index=0,
                        oval=(1.0, .78), cap_start=True, cap_end=True, irregular=.04):
    """Append a tapered irregular tube along a curved point sequence."""
    if len(points) != len(radii) or len(points) < 2:
        return []
    uv_layer = bm.loops.layers.uv.active
    zup = Vector((0, 0, 1))
    rings = []
    faces = []
    phase1 = _hash01(seed, 3) * 2.0 * math.pi
    phase2 = _hash01(seed, 7) * 2.0 * math.pi
    count = len(points)
    for j, (point, radius) in enumerate(zip(points, radii)):
        if j == 0:
            tangent = points[1] - points[0]
        elif j == count - 1:
            tangent = points[-1] - points[-2]
        else:
            tangent = points[j + 1] - points[j - 1]
        if tangent.length < 1e-6:
            tangent = zup.copy()
        tangent.normalize()
        side = tangent.cross(zup)
        if side.length < 1e-5:
            side = Vector((1, 0, 0))
        side.normalize()
        upv = side.cross(tangent)
        if upv.length < 1e-5:
            upv = zup.copy()
        upv.normalize()
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            organic = 1.0 + irregular * math.sin(3.0 * a + phase1 + j * .57)
            organic += irregular * .55 * math.sin(5.0 * a + phase2 - j * .31)
            rr = max(radius * organic, .0012)
            ring.append(bm.verts.new(point + side * (math.cos(a) * rr * oval[0]) +
                                     upv * (math.sin(a) * rr * oval[1])))
        rings.append(ring)
    for j in range(count - 1):
        t0 = j / max(count - 1, 1)
        t1 = (j + 1) / max(count - 1, 1)
        for i in range(sides):
            ni = (i + 1) % sides
            face = bm.faces.new((rings[j][i], rings[j][ni], rings[j + 1][ni], rings[j + 1][i]))
            face.material_index = material_index
            u0, u1 = i / sides, (i + 1) / sides
            _write_face_uvs(face, uv_layer, ((u0, t0), (u1, t0), (u1, t1), (u0, t1)))
            faces.append(face)
    if cap_start:
        cap = bm.faces.new(tuple(reversed(rings[0])))
        cap.material_index = material_index
        faces.append(cap)
    if cap_end:
        cap = bm.faces.new(tuple(rings[-1]))
        cap.material_index = material_index
        faces.append(cap)
    return faces


def _append_surface_roots(bm, centre, *, count, trunk_radius, base_z, length_range,
                          radius_range, bury_range=(.07, .16), sides=7, rings=7,
                          seed=0, oval=.70):
    """Append separate tapering horizontal roots that dive below z=0 individually."""
    made = []
    centre = Vector((centre.x, centre.y, 0.0))
    for ri in range(count):
        h1 = _hash01(ri, 11, seed)
        h2 = _hash01(ri, 17, seed)
        h3 = _hash01(ri, 23, seed)
        h4 = _hash01(ri, 29, seed)
        h5 = _hash01(ri, 37, seed)
        angle = 2.0 * math.pi * (ri + (h1 - .5) * .82) / count + (h2 - .5) * .10
        radial = Vector((math.cos(angle), math.sin(angle), 0.0))
        tangent = Vector((-radial.y, radial.x, 0.0))
        length = length_range[0] + (length_range[1] - length_range[0]) * h2
        root_radius = radius_range[0] + (radius_range[1] - radius_range[0]) * h3
        bury = bury_range[0] + (bury_range[1] - bury_range[0]) * h4
        start_z = base_z * (.86 + .28 * h5)
        bend = (h4 - .5) * length * .34
        bend2 = bend * 1.35 + (h1 - .5) * length * .12
        p0 = centre + radial * (trunk_radius * .30) + Vector((0, 0, start_z))
        p1 = centre + radial * (trunk_radius * .90) + tangent * (bend * .12) + Vector((0, 0, start_z * .70))
        p2 = centre + radial * (trunk_radius + length * .48) + tangent * bend + Vector((0, 0, .008 + .022 * h3))
        p3 = centre + radial * (trunk_radius + length) + tangent * bend2 + Vector((0, 0, -bury))
        pts = [_bezier_point(p0, p1, p2, p3, j / max(rings - 1, 1)) for j in range(rings)]
        # Runde 6c: die wurzel LAUFT AUF dem boden statt in ihm.  der erste wurf liess
        # die mittellinie flach durch z=0 gleiten — nur eine schmale kalotte lugte ueber
        # die erde und las als flacher dreiecks-spiess (probe: sichtbare spitzen waren
        # roehren-scheitel, nicht die template-finnen).  jetzt: mittellinie steigt vom
        # stamm auf ruhehoehe (radius*.55 — mehr als die haelfte der roehre liegt frei),
        # laeuft fast eben als runde schlaengelwurzel und STUERZT erst im letzten
        # viertel steil unter die erde, wobei sie auch dort noch dick ist.
        descend_t = .40
        # eintauchen auf mehr ringe verteilt (frueher beginnend), damit der bogen unter
        # die erde weich rund statt als abgeknicktes bretter-ende liest (draft6)
        plunge_t = .62 + .06 * h4
        # radien zuerst — die ruhehoehe haengt vom lokalen radius ab
        radii = []
        for j in range(rings):
            t = j / max(rings - 1, 1)
            if t < plunge_t:
                q = t / max(plunge_t, 1e-6)
                taper = 1.0 - .26 * q
            else:
                q = (t - plunge_t) / max(1.0 - plunge_t, 1e-6)
                taper = .74 * ((1.0 - q) ** .62) + .08
            rr = .018 + (root_radius - .018) * taper
            rr *= 1.0 + .10 * math.sin(j * 2.13 + h2 * 5.1) + .05 * math.sin(j * 3.7 + h4 * 3.0)
            radii.append(max(rr, .012))
        for j, pt in enumerate(pts):
            t = j / max(rings - 1, 1)
            # ruhehoehe bei 85% des radius: die roehre liegt fast voll auf dem boden
            # auf (nur die flache unterseite versinkt) — bei 55% zeigte sich nur eine
            # flache kalotte und die wurzel las als brettesque platte (draft5)
            z_rest = radii[j] * .85 + .012
            if t < descend_t:
                q = t / descend_t
                pt.z = z_rest + (start_z - z_rest) * ((1.0 - q) ** 1.35)
                # wellen des freiliegenden wurzelkoerpers, am stamm ausklingend
                pt.z += math.sin(q * math.pi * (1.35 + .55 * h3) + h5 * 4.2) * .030 * math.sin(math.pi * q)
            elif t < plunge_t:
                q = (t - descend_t) / max(plunge_t - descend_t, 1e-6)
                # fast ebenes, leicht welliges aufliegen auf der erde
                pt.z = z_rest * (1.0 - .25 * q)
                pt.z += math.sin(t * math.pi * (2.1 + .7 * h3) + h5 * 4.2) * .022 * math.sin(math.pi * q)
            else:
                q = (t - plunge_t) / max(1.0 - plunge_t, 1e-6)
                # steiler einsturz: am ende ist die mittellinie tiefer als -radius,
                # die roehre ist komplett verschwunden, bevor sie duenn wird
                pt.z = z_rest * .75 - (bury + root_radius * 1.1) * (q ** .72)
        made.extend(_append_curved_tube(bm, pts, radii, sides=sides, seed=seed + 600 + ri * 19,
                                        material_index=0, oval=(1.0, oval), irregular=.065))
    return {"roots": count, "faces": len(made)}


def _flute_trunk_bark(mesh, *, trunk_radius, height=3.2, seed=0):
    """Subtly flute the lower trunk surface so bark catches light as structure."""
    centre = _estimate_trunk_center(mesh)
    changed = 0
    phase = _hash01(seed, 131) * 2.0 * math.pi
    for v in sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices}):
        co = mesh.vertices[v].co
        if not (.10 < co.z < height):
            continue
        dx, dy = co.x - centre.x, co.y - centre.y
        r = math.hypot(dx, dy)
        if r < trunk_radius * .42 or r > trunk_radius * 1.48:
            continue
        a = math.atan2(dy, dx)
        zfade = min(1.0, (co.z - .10) / .34)
        zfade *= 1.0 - .42 * max(0.0, co.z - height * .66) / max(height * .34, 1e-6)
        wave = .62 * math.sin(7.0 * a + co.z * 4.7 + phase)
        wave += .38 * math.sin(13.0 * a - co.z * 3.1 + phase * .37)
        amp = trunk_radius * .054 * zfade
        if r > 1e-6:
            co.x += dx / r * wave * amp
            co.y += dy / r * wave * amp
            changed += 1
    if changed:
        mesh.update()
    return {"vertices": changed}


def _smooth_lower_trunk_flare(mesh, *, trunk_radius, seed=0):
    """Collapse blade-like template buttress plates into a broad continuous trunk flare.

    Separate surface roots provide the horizontal root structure; the underlying trunk
    scaffold only needs a rounded, slightly uneven flare rather than triangular fins.
    """
    centre=_estimate_trunk_center(mesh); changed=0; phase=_hash01(seed,557)*2*math.pi
    ids=sorted({v for p in mesh.polygons if p.material_index==0 for v in p.vertices})
    for vi in ids:
        co=mesh.vertices[vi].co
        # Runde 6: auch die bodennahen finnenkanten (z bis -.02) und etwas hoeher (1.35)
        # erfassen — in R5 blieben die unteren plattenkanten unveraendert als dreieckige
        # flossen stehen, weil verts unter z=.025 komplett ausgenommen waren.
        if not (-.02<co.z<1.35): continue
        dx,dy=co.x-centre.x,co.y-centre.y; r=math.hypot(dx,dy)
        if r<.10: continue
        t=co.z/1.18
        target=trunk_radius*(1.18-.28*t)
        a=math.atan2(dy,dx)
        target*=1.0+.030*math.sin(5*a+co.z*2.1+phase)+.018*math.sin(9*a-co.z*3.0)
        if r>target:
            # staerkeres einziehen (10% statt 24% restweite): die dreieckigen template-
            # finnen werden zu vertikalen wurzelrippen am stamm statt flacher platten;
            # die horizontale wurzelstruktur uebernehmen die separaten rundwurzeln.
            newr=target+(r-target)*.10
        elif r<target*.76:
            newr=r+(target*.76-r)*.34
        else:
            continue
        scale=newr/r
        co.x=centre.x+dx*scale; co.y=centre.y+dy*scale; changed+=1
    if changed: mesh.update()
    return {"vertices":changed}


def _dive_flare_teeth(mesh, *, trunk_radius, seed=0):
    """Sink the outer skirt of the collapsed template flare progressively underground.

    The triangular template teeth are vertical webs at the trunk that flatten into
    horizontal plates exactly where they meet the soil.  Sliding their lower outer
    vertices below grade turns them into buttress ridges that dive into the ground
    instead of flat fins lying on it.  Runs before any procedural geometry is appended,
    so every bark vertex here is original template scaffold; the dive is depth-limited
    and can never reach the pinned z_min = -0.65 burial socket.
    """
    centre = _estimate_trunk_center(mesh)
    dive_start = trunk_radius * 1.02
    ids = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    changed = 0
    for vi in ids:
        co = mesh.vertices[vi].co
        # enger hoehenkorridor: unter z=.45 existieren nach dem flare-collapse nur
        # finnen-/schuerzenreste (aeste laufen erst ab z~1+ aus dem stamm); ein erster
        # wurf mit z<1.0 zog den grossen tiefen seitenast unter die erde (z_min-bruch).
        if not (-.05 < co.z < .45):
            continue
        dx, dy = co.x - centre.x, co.y - centre.y
        r = math.hypot(dx, dy)
        # kein oberer radius-schluss mehr: die sichtbaren finnen-spitzen reichen bis
        # r~1.4 und blieben durch die alte r<1.0-sperre komplett unbehandelt (woodshot
        # d4).  der harte versenkungs-deckel unten macht den z_min-sockel trotzdem
        # unerreichbar, und tief liegende schuerzenreste unterhalb z=-.05 sind ohnehin
        # unsichtbar und duerfen mit eingezogen werden.
        if r <= dive_start:
            continue
        # Runde 6b: die finnen sind flache dreiecks-platten — reines versenken liess
        # ihre spitzen als scharfe holz-spiesse ueber dem boden (woodshot-base).  jetzt
        # wird der radiale ueberstand zusaetzlich auf 38% eingezogen: die platte wird
        # zum niedrigen runden knoechel direkt am stamm, waehrend das abtauchen die
        # restspitze unter die erde zieht.  die eigentliche wurzelwirkung liegt auf den
        # separaten rund-roehrenwurzeln.
        excess = r - dive_start
        zfade = max(0.0, 1.0 - co.z / .45)
        # einzug wie versenkung zum fenster oberrand ausblenden — sonst entstuende bei
        # z=.45 eine sichtbare knickkante um den stamm
        shrink = 1.0 - .62 * zfade
        newr = dive_start + excess * shrink
        scale = newr / r
        co.x = centre.x + dx * scale
        co.y = centre.y + dy * scale
        # staerkstes abtauchen an der bodennahen unterkante, auslaufend ab z=.45;
        # hart gedeckelt, damit die versenkung niemals den eingegrabenen sockel erreicht
        sink = min(excess * 1.5 * (.35 + .65 * zfade), .34)
        co.z -= sink
        changed += 1
    if changed:
        mesh.update()
    return {"vertices": changed}


def _leaf_atlas_rect(h, *, willow=False):
    hu = _hash01(h, 401)
    hv = _hash01(h, 409)
    u0 = .008 if hu < .5 else .508
    v0 = .008 if hv < .5 else .508
    return (u0, v0, u0 + .484, v0 + .484)


def _append_leaf_card(bm, base, vhat, *, width, length, seed=0, material_index=1,
                      uv_rect=(.008, .008, .492, .492), reverse_v=False, cup=.045,
                      twist_deg=24.0, pinch=.24):
    """Append a small 2x2-quad leaf-cluster card with its stem edge at base."""
    if vhat.length < 1e-6:
        return []
    vhat = vhat.normalized()
    horizontal = Vector((vhat.x, vhat.y, 0.0))
    if horizontal.length > 1e-5:
        uhat = Vector((-horizontal.y, horizontal.x, 0.0)).normalized()
    else:
        uhat = Vector((1, 0, 0))
    nhat = uhat.cross(vhat)
    if nhat.length < 1e-6:
        nhat = Vector((0, 0, 1))
    nhat.normalize()
    uv_layer = bm.loops.layers.uv.active
    h1 = _hash01(seed, 421)
    h2 = _hash01(seed, 427)
    twist = math.radians((h1 * 2.0 - 1.0) * twist_deg)
    curl = (h2 - .5) * width * .18
    lattice = {}
    for iv in range(3):
        w = iv / 2.0
        angle = twist * (w - .5)
        ca, sa = math.cos(angle), math.sin(angle)
        u2 = uhat * ca + nhat * sa
        n2 = nhat * ca - uhat * sa
        for iu in range(3):
            u = iu / 2.0
            centred = u - .5
            x = centred * width * (1.0 - pinch * w)
            camber = (1.0 - centred * centred * 4.0) * cup * math.sin(math.pi * w)
            lattice[(iu, iv)] = bm.verts.new(base + vhat * (length * w) + u2 * x +
                                             n2 * camber + uhat * (curl * math.sin(math.pi * w)))
    faces = []
    umin, vmin, umax, vmax = uv_rect
    for iv in range(2):
        for iu in range(2):
            keys = ((iu, iv), (iu + 1, iv), (iu + 1, iv + 1), (iu, iv + 1))
            face = bm.faces.new(tuple(lattice[k] for k in keys))
            face.material_index = material_index
            uvs = []
            for ku, kv in keys:
                uu = umin + (ku / 2.0) * (umax - umin)
                vv = vmax - (kv / 2.0) * (vmax - vmin) if reverse_v else vmin + (kv / 2.0) * (vmax - vmin)
                uvs.append((uu, vv))
            _write_face_uvs(face, uv_layer, uvs)
            faces.append(face)
    return faces


def _append_terminal_growth(bm, cap_data, shoot_data, *, seed=0, willow=False):
    """Finish blunt ends as fine tapered twig whorls plus anchored leaf tufts."""
    made = {"twig_faces": 0, "twigs": 0, "leaf_cards": 0, "terminal_shoots": 0}
    zup = Vector((0, 0, 1))

    def leaf_tuft(pos, direction, size_seed, count, scale=1.0):
        if direction.length < 1e-6:
            direction = zup.copy()
        direction = direction.normalized()
        e1, e2 = _orthogonal_frame(direction)
        for k in range(count):
            h1 = _hash01(size_seed, k, 431)
            h2 = _hash01(size_seed, k, 437)
            h3 = _hash01(size_seed, k, 439)
            spin = 2.0 * math.pi * (k / max(count, 1) + h1 * .23)
            lateral = e1 * math.cos(spin) + e2 * math.sin(spin)
            if willow:
                outward = Vector((direction.x, direction.y, 0.0))
                if outward.length < 1e-5:
                    outward = lateral.copy()
                outward.normalize()
                vhat = (outward * (.25 + .20 * h2) + Vector((0, 0, -1.0))).normalized()
                length = (.42 + .18 * h2) * scale
                width = (.30 + .13 * h3) * scale
            else:
                vhat = (direction * (.72 + .16 * h2) + zup * (.24 + .22 * h3) + lateral * .16).normalized()
                length = (.48 + .22 * h2) * scale
                width = (.46 + .20 * h3) * scale
            base = pos - vhat * (.055 + .035 * h1) + lateral * (.014 + .024 * h3)
            rect = _leaf_atlas_rect(size_seed + k * 13, willow=willow)
            faces = _append_leaf_card(bm, base, vhat, width=width, length=length,
                                      seed=seed + size_seed * 17 + k, uv_rect=rect,
                                      reverse_v=willow, cup=.035 + .025 * h2,
                                      twist_deg=28, pinch=.28 if willow else .22)
            made["leaf_cards"] += len(faces) // 4

    for si, data in enumerate(shoot_data or ()):
        axis = data["axis"]
        length = data["length"]
        h = _hash01(data["ci"], si, 443)
        tip = data["base"] + axis * length
        # Runde 6: Laub entlang des ganzen verkuerzten Triebs statt nur an der Spitze —
        # der einst nackte schwarze Speer liest sich als durchgehend beblaettertes
        # Zweigende; die Karten werden nach innen kleiner und guenstiger.
        leaf_tuft(tip, axis, seed + 700 + si, 2 + (1 if h > .55 else 0), scale=.95 + .18 * h)
        if length > .30:
            mid = data["base"] + axis * (length * (.56 + .10 * h))
            leaf_tuft(mid, axis, seed + 720 + si, 1 + (1 if h > .42 else 0), scale=.68 + .14 * h)
            inner = data["base"] + axis * (length * (.24 + .08 * h))
            leaf_tuft(inner, axis, seed + 740 + si, 1, scale=.50 + .14 * h)
        made["terminal_shoots"] += 1

    for ci, data in enumerate(cap_data or ()):
        axis = data["axis"].normalized()
        tip = data["tip"]
        radius = data["radius"]
        h0 = _hash01(data["ci"], 449, seed)
        whorl = 2 + (1 if radius > .145 or h0 > .62 else 0)
        e1, e2 = _orthogonal_frame(axis)
        inset = max(.115, radius * .52)
        spread = min(radius * .30, .052)
        for k in range(whorl):
            h1 = _hash01(data["ci"], k, 451, seed)
            h2 = _hash01(data["ci"], k, 457, seed)
            h3 = _hash01(data["ci"], k, 461, seed)
            h4 = _hash01(data["ci"], k, 467, seed)
            ang = 2.0 * math.pi * (k / whorl + h1 * .19)
            lateral = e1 * math.cos(ang) + e2 * math.sin(ang)
            start = tip - axis * (inset * (.86 + .20 * h2)) + lateral * (spread * (.35 + .55 * h3))
            direction = axis * (.82 + .10 * h2) + lateral * (.28 + .18 * h3) + zup * ((h4 - .42) * .10)
            if direction.length < 1e-6:
                direction = axis.copy()
            direction.normalize()
            length = max(.24, min(.50, radius * 1.45 + .14)) * (.86 + .24 * h1)
            curl = (.025 + .045 * h2) * (1.0 if h3 > .5 else -1.0)
            lift = (.018 + .050 * h4) if not willow else (-.015 - .035 * h4)
            pts = []
            radii = []
            base_r = min(max(radius * (.22 + .08 * h2), .013), .043)
            rings = 5
            for j in range(rings):
                t = j / (rings - 1)
                pos = start + direction * (length * t)
                pos += lateral * (curl * math.sin(math.pi * t * .5))
                pos += zup * (lift * t * t)
                pts.append(pos)
                radii.append(.004 + (base_r - .004) * ((1.0 - t) ** .82))
            faces = _append_curved_tube(bm, pts, radii, sides=5, seed=seed + 900 + ci * 31 + k,
                                        material_index=0, oval=(1.0, .86), irregular=.055)
            made["twig_faces"] += len(faces)
            made["twigs"] += 1
            leaf_tuft(pts[-1], direction, seed + 1000 + ci * 17 + k, 2 if h2 > .30 else 1,
                      scale=.92 + .18 * h3)
        # Runde 6: zusaetzliche blattpolster entlang des nackten endasts hinter der
        # spitze — der lange dunkle speer des geruests liest sich so als beblaettertes
        # zweigende. kleinere, guenstigere karten weiter innen; leicht seitlich versetzt,
        # damit sie nicht exakt auf der astachse schwimmen.
        shaft_len = max(.55, min(1.15, radius * 4.2))
        for frac, sc, cnt in ((.30, .74, 2), (.62, .60, 1), (.88, .48, 1)):
            h5 = _hash01(data["ci"], int(frac * 100), 471, seed)
            h6 = _hash01(data["ci"], int(frac * 100), 479, seed)
            back = tip - axis * (shaft_len * frac)
            lateral_off = (e1 * (h5 - .5) + e2 * (h6 - .5)) * max(radius * 1.1, .06)
            pos = back + lateral_off + zup * ((h5 - .35) * .05)
            leaf_tuft(pos, axis, seed + 1100 + ci * 13 + int(frac * 100),
                      cnt + (1 if h6 > .62 else 0), scale=sc + .10 * h5)
    return made


def _foliage_distance_sampler(mesh):
    """Exact closest-distance function against the current foliage triangle surfaces."""
    foliage_tris = []
    for poly in mesh.polygons:
        if poly.material_index != 1:
            continue
        ids = list(poly.vertices)
        for k in range(1, len(ids) - 1):
            foliage_tris.append((
                mesh.vertices[ids[0]].co.copy(),
                mesh.vertices[ids[k]].co.copy(),
                mesh.vertices[ids[k + 1]].co.copy(),
            ))

    def distance(point):
        point = Vector(point)
        best = 999.0
        for a, b, c in foliage_tris:
            close = closest_point_on_tri(point, a, b, c)
            best = min(best, (close - point).length)
        return best

    return distance


def _select_scaffold_fill_anchors(mesh, shoot_endpoints, *, max_count=6, seed=0):
    """Choose a few verified exposed scaffold terminals for endpoint-attached leaf fill.

    Unlike the rejected terminal-growth pass this adds no twigs and no free-floating
    canopy cloud.  The cap detector is used only as a measurement of existing wood;
    candidates are then filtered by radius, height, upward direction, foliage exposure
    and separation from the loose shoot endpoints.  Thin 44-face shoot tubes are
    deliberately excluded here because they are handled by the subtractive trim.
    """
    if max_count <= 0:
        return []
    distance = _foliage_distance_sampler(mesh)
    shoot_tips = [Vector(e["tip"]) for e in shoot_endpoints or ()]
    candidates = _tip_cap_candidates(
        mesh, zmin=4.7, min_radius=.10, cluster_radius=.55, min_points=3,
        seed=seed, dead_end=.24, max_caps=0, min_cap_radius=0.0,
    )
    rows = []
    for cand in candidates:
        tip = Vector(cand["tip"])
        axis = Vector(cand["axis"])
        if axis.length < 1e-5:
            continue
        axis.normalize()
        radius = float(cand["radius"])
        if not (.065 <= radius <= .29):
            continue
        if not (4.8 <= tip.z <= 9.6) or axis.z < .12:
            continue
        if any((tip - shoot_tip).length < .55 for shoot_tip in shoot_tips):
            continue
        fdist = distance(tip)
        high_sky = tip.z >= 8.55
        if fdist < .24 and not high_sky:
            continue
        radial_len = math.hypot(tip.x, tip.y)
        score = min(fdist, 1.2) * 1.55
        score += max(0.0, tip.z - 5.0) * .045 + max(axis.z, 0.0) * .10
        score += max(0.0, 3.8 - radial_len) * .05
        if high_sky:
            score += .18
        rows.append({
            "tip": tip, "axis": axis, "radius": radius, "foliage_distance": fdist,
            "score": score, "ci": cand["ci"],
        })
    rows.sort(key=lambda r: (-r["score"], -r["tip"].z, r["ci"]))

    def far_enough(row, selected):
        return all((row["tip"] - other["tip"]).length >= .72 for other in selected)

    selected = []
    # Reserve up to two slots for high scaffold terminals so interior holes cannot
    # consume the whole budget before the sky-line spikes are considered.
    for row in [r for r in rows if r["tip"].z >= 7.2]:
        if len(selected) >= min(2, max_count):
            break
        if far_enough(row, selected):
            selected.append(row)
    for row in rows:
        if len(selected) >= max_count:
            break
        if row in selected or not far_enough(row, selected):
            continue
        selected.append(row)
    out = []
    for row in selected:
        out.append({
            "component": row["ci"],
            "tip": tuple(round(float(x), 4) for x in row["tip"]),
            "axis": tuple(round(float(x), 4) for x in row["axis"]),
            "radius": round(row["radius"], 4),
            "foliage_distance": round(row["foliage_distance"], 4),
            "score": round(row["score"], 4),
        })
    return out


def _retract_scaffold_terminal_spikes(mesh, scaffold_anchors, *, max_items=4):
    """Subtractive compression/taper of the worst connected scaffold terminal spikes.

    The detector measurements describe existing endpoints; this pass creates no caps,
    twigs, collars or extra bark.  It only moves vertices of the large connected wood
    scaffold inside a narrow measured end capsule.  Axial compression is smooth and
    ordering-preserving, so the branch end retreats toward the trunk instead of being
    sliced open, while the terminal radius collapses enough that it no longer reads as
    a black spear.  Interior/low endpoints are left for foliage cover rather than
    risking deformation of healthy scaffold limbs.
    """
    anchors = [dict(a) for a in (scaffold_anchors or ())]
    if not anchors:
        return {"pieces": 0, "vertices": 0, "details": [], "anchors": anchors}
    comps = _material_components(mesh, 0)
    if not comps:
        return {"pieces": 0, "vertices": 0, "details": [], "anchors": anchors}
    large = max(comps, key=lambda c: len(c["polys"]))
    large_ids = set(large["verts"])
    ranked = []
    for ai, anchor in enumerate(anchors):
        tip = Vector(anchor["tip"])
        axis = Vector(anchor["axis"])
        if axis.length < 1e-5:
            continue
        axis.normalize()
        radius = max(float(anchor.get("radius", .08)), .04)
        # The visible offender class is upright/high terminal wood.  Low horizontal
        # interior endpoints may be holes in the crown, but compressing them risks
        # collapsing healthy scaffold limbs; they are covered with foliage instead.
        if not (axis.z >= .42 or tip.z >= 7.2):
            continue
        priority = tip.z * .16 + axis.z + min(float(anchor.get("foliage_distance", 0.0)), 1.0)
        ranked.append((priority, ai, tip, axis, radius))
    ranked.sort(key=lambda item: (-item[0], -item[2].z, item[1]))
    selected = ranked[:max_items]
    changed_ids = set()
    details = []
    for priority, ai, tip, axis, radius in selected:
        retreat = min(max(radius * 3.2, .30), .62)
        influence = max(retreat * 2.15, radius * 5.0, .58)
        radial_limit = max(radius * 1.18, .105)
        affected = 0
        for vi in sorted(large_ids):
            if vi in changed_ids:
                continue
            co = mesh.vertices[vi].co
            vec = co - tip
            back = -vec.dot(axis)
            if back < -radius * .35 or back > influence:
                continue
            axial = tip - axis * back
            perp = co - axial
            if perp.length > radial_limit:
                continue
            q = min(max(back / max(influence, 1e-6), 0.0), 1.0)
            shape = (1.0 - q) ** 1.15
            shift = retreat * shape
            radial_scale = .34 + .66 * (q ** .78)
            co[:] = axial + perp * radial_scale - axis * shift
            changed_ids.add(vi)
            affected += 1
        if affected < 3:
            continue
        final_tip = tip - axis * retreat
        anchors[ai]["original_tip"] = anchors[ai]["tip"]
        anchors[ai]["tip"] = tuple(round(float(x), 4) for x in final_tip)
        anchors[ai]["retracted"] = True
        details.append({
            "component": anchors[ai].get("component"),
            "vertices": affected,
            "retreat": round(retreat, 3),
            "influence": round(influence, 3),
            "tip_z": round(tip.z, 3),
            "axis_z": round(axis.z, 3),
        })
    if changed_ids:
        mesh.update()
    return {"pieces": len(details), "vertices": len(changed_ids), "details": details,
            "anchors": anchors}


def _add_endpoint_foliage_clusters(mesh, shoot_endpoints, *, max_cards=34, scaffold_cards=6, seed=0,
                                   scaffold_anchors=None):
    """Add a tightly capped number of whole 3x3 leaf cards at real wood endpoints.

    Every added card is the same multi-face connected lattice used by the authored
    template cards (nine vertices/four quads/eight triangles, full UV sprite).  No card
    is fragmented and none is scattered freely: its stem edge is inset into a measured
    terminal wood end.  Two crossed cards are used at the worst loose-shoot endpoints;
    a few single cards close measured interior scaffold terminal holes.  The default
    maximum of 34 is 14.5% of the 234 authored clusters.
    """
    if max_cards <= 0:
        return {"cards": 0, "faces": 0, "vertices": 0, "shoot_endpoint_cards": 0,
                "scaffold_endpoint_cards": 0, "scaffold_anchors": []}
    endpoints = []
    for item in shoot_endpoints or ():
        endpoints.append(dict(item))
    endpoints.sort(key=lambda e: (-e.get("score", 0.0), -e.get("tip", (0, 0, 0))[2]))
    if scaffold_anchors is None:
        scaffold = _select_scaffold_fill_anchors(mesh, endpoints, max_count=scaffold_cards, seed=seed)
    else:
        scaffold = [dict(a) for a in scaffold_anchors[:scaffold_cards]]
    remaining = max(0, max_cards - len(scaffold))
    plan = []
    for endpoint in endpoints:
        if remaining <= 0:
            break
        # Two orientations at one endpoint are still attached whole clusters, not a
        # duplicated cloud: they share the wood end and diverge as a small leaf spray.
        for copy_no in range(2):
            if remaining <= 0:
                break
            plan.append(("shoot", endpoint, copy_no))
            remaining -= 1
    for endpoint in scaffold:
        plan.append(("scaffold", endpoint, 0))
    if not plan:
        return {"cards": 0, "faces": 0, "vertices": 0, "shoot_endpoint_cards": 0,
                "scaffold_endpoint_cards": 0, "scaffold_anchors": scaffold}

    before_vertices = len(mesh.vertices)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    zup = Vector((0, 0, 1))
    cards = 0
    faces_made = 0
    shoot_cards = 0
    scaffold_count = 0
    for pi, (kind, endpoint, copy_no) in enumerate(plan):
        tip = Vector(endpoint["tip"])
        axis = Vector(endpoint["axis"])
        if axis.length < 1e-5:
            continue
        axis.normalize()
        radius = max(float(endpoint.get("radius", .035)), .02)
        radial = Vector((tip.x, tip.y, 0.0))
        if radial.length < .12:
            radial = Vector((axis.x, axis.y, 0.0))
        if radial.length < 1e-5:
            radial = Vector((1.0, 0.0, 0.0))
        radial.normalize()
        e1, e2 = _orthogonal_frame(axis)
        h1 = _hash01(pi, copy_no, 701, seed)
        h2 = _hash01(pi, copy_no, 707, seed)
        h3 = _hash01(pi, copy_no, 709, seed)
        h4 = _hash01(pi, copy_no, 719, seed)
        h5 = _hash01(pi, copy_no, 727, seed)
        h6 = _hash01(pi, copy_no, 733, seed)
        side = e1 * (1.0 if h2 < .5 else -1.0) + e2 * ((h3 - .5) * .75)
        if side.length < 1e-5:
            side = e1.copy()
        side.normalize()
        if kind == "scaffold":
            # Interior scaffold holes are covered by a card reaching back over the
            # bare terminal wood instead of expanding the outer silhouette.
            direction = axis * .32 - radial * (.16 + .10 * h1) + zup * (.52 + .08 * h2)
            direction += side * (.18 + .14 * h3)
            width = 1.12 + .34 * h1
            length = 1.25 + .34 * h2
        elif copy_no == 0:
            direction = axis * .46 + radial * (.24 + .10 * h1) + zup * (.50 + .10 * h2)
            direction += side * ((h3 - .5) * .22)
            width = 1.02 + .32 * h1
            length = 1.14 + .34 * h2
        else:
            direction = axis * .24 - radial * (.24 + .10 * h1) + zup * (.48 + .10 * h2)
            direction += side * (.30 + .16 * h3)
            width = (1.02 + .32 * h1) * (.86 + .12 * h4)
            length = (1.14 + .34 * h2) * (.90 + .12 * h5)
        if direction.length < 1e-5:
            direction = zup.copy()
        direction.normalize()
        if direction.z < .18:
            direction = (direction + zup * (.18 - direction.z)).normalized()
        if tip.z > 9.2:
            length *= .88
        inset = .022 + min(radius * .55, .045)
        lateral_offset = side * ((h5 - .5) * min(radius * .45, .032))
        base = tip - axis * inset + lateral_offset
        rect = _leaf_atlas_rect(seed + pi * 17 + copy_no * 5)
        faces = _append_leaf_card(
            bm, base, direction, width=width, length=length,
            seed=seed + pi * 31 + copy_no, uv_rect=rect, reverse_v=False,
            cup=.040 + .025 * h4, twist_deg=24.0 + 10.0 * h5,
            pinch=.20 + .08 * h6,
        )
        if not faces:
            continue
        cards += 1
        faces_made += len(faces)
        if kind == "scaffold":
            scaffold_count += 1
        else:
            shoot_cards += 1
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {
        "cards": cards,
        "faces": faces_made,
        "vertices": len(mesh.vertices) - before_vertices,
        "shoot_endpoint_cards": shoot_cards,
        "scaffold_endpoint_cards": scaffold_count,
        "max_cards": max_cards,
        "authored_cluster_increase_pct": round(cards / 234.0 * 100.0, 2),
        "scaffold_anchors": scaffold,
    }


def _set_new_blockcol_white(mesh, first_new_vertex):
    """Keep the template blockcol contract intact for newly appended leaf vertices."""
    attr = mesh.color_attributes.get("blockcol")
    if attr is None or attr.domain != "POINT":
        return 0
    changed = 0
    for vi in range(first_new_vertex, min(len(mesh.vertices), len(attr.data))):
        attr.data[vi].color = (1.0, 1.0, 1.0, 1.0)
        changed += 1
    return changed


def _restore_template_foliage_normals(mesh, template_normals, original_loop_count):
    """Restore authored template split normals and author normals for appended cards.

    Bmesh appending can leave new loops without meaningful custom normals.  Existing
    loops are restored from the template cache unchanged; only loops belonging to the
    newly appended foliage cards receive a smooth geometric/canopy normal blend.  This
    avoids the mixed results of a blanket canopy-normal rewrite while keeping the new
    geometry exportable and correctly shaded.
    """
    if not template_normals:
        return {"template_loops": 0, "new_foliage_loops": 0}
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
    out = []
    kept = 0
    for li in range(len(mesh.loops)):
        if li < original_loop_count and li < len(template_normals):
            out.append(template_normals[li].copy())
            kept += 1
        else:
            out.append(Vector((0, 0, 1)))
    authored = 0
    for li, loop in enumerate(mesh.loops):
        if li < original_loop_count:
            continue
        p = loop_poly.get(li)
        if p is None or p.material_index != 1:
            continue
        v = loop.vertex_index
        geom = acc[v].normalized() if acc[v].length > 1e-6 else Vector((0, 0, 1))
        co = mesh.vertices[v].co
        radial = Vector((co.x, co.y, 0.0))
        if radial.length > .15:
            canopy = (radial.normalized() * .52 + Vector((0, 0, .78))).normalized()
        else:
            canopy = Vector((0, 0, 1))
        if geom.dot(canopy) < 0.0:
            geom = -geom
        out[li] = (geom * .58 + canopy * .42).normalized()
        authored += 1
    mesh.normals_split_custom_set(out)
    mesh.update()
    return {"template_loops": kept, "new_foliage_loops": authored}


def _raggedize_willow_cards(mesh, *, seed=0):
    """Skew/pinch willow cards and vary their UV windows without changing their droop."""
    uvlay = mesh.uv_layers.active
    changed = 0
    loops_changed = 0
    for ci, polys in enumerate(_foliage_components(mesh, 1)):
        rows = _component_rows(mesh, polys)
        if len(rows) != 4:
            continue
        center = Vector((0, 0, 0))
        for v, u, w, co in rows:
            center += co
        center /= len(rows)
        pu0 = _mean_row(rows, lambda u, w: u < .2)
        pu1 = _mean_row(rows, lambda u, w: u > .8)
        pv0 = _mean_row(rows, lambda u, w: w < .2)
        pv1 = _mean_row(rows, lambda u, w: w > .8)
        au, av = pu1 - pu0, pv1 - pv0
        if au.length < 1e-5 or av.length < 1e-5:
            continue
        uhat, vhat = au.normalized(), av.normalized()
        nhat = uhat.cross(vhat)
        if nhat.length < 1e-5:
            continue
        nhat.normalize()
        h1 = _hash01(ci, 501, seed)
        h2 = _hash01(ci, 503, seed)
        h3 = _hash01(ci, 509, seed)
        h4 = _hash01(ci, 521, seed)
        shear = (h2 - .5) * .22
        pinch_free = .16 + .24 * h1
        pinch_base = .05 + .12 * h4
        length_jitter = .90 + .16 * h3
        for v, u, w, co in rows:
            d = co - center
            x = d.dot(uhat)
            y = d.dot(vhat) * length_jitter
            z = d.dot(nhat)
            end = abs(w - .5) * 2.0
            pinch = pinch_free * (end ** 1.7) + pinch_base * ((1.0 - end) ** 2)
            corner_sign = 1.0 if (u > .5) == (w > .5) else -1.0
            x *= 1.0 - pinch * (1.0 + .28 * corner_sign * (h3 - .5))
            x += shear * (w - .5) * max(abs(x) * 2.0, .18)
            y += (h4 - .5) * .055 * math.sin(math.pi * u)
            mesh.vertices[v].co = center + uhat * x + vhat * y + nhat * z
            changed += 1
        loop_ids = sorted({li for p in polys for li in p.loop_indices})
        if loop_ids and uvlay:
            us = [uvlay.data[li].uv.x for li in loop_ids]
            vs = [uvlay.data[li].uv.y for li in loop_ids]
            umin, umax = min(us), max(us)
            vmin, vmax = min(vs), max(vs)
            in_u0 = .012 + .052 * h1
            in_u1 = .012 + .052 * h2
            in_v0 = .004 + .025 * h3
            in_v1 = .004 + .025 * h4
            for li in loop_ids:
                uv = uvlay.data[li].uv
                nu = (uv.x - umin) / max(umax - umin, 1e-8)
                nv = (uv.y - vmin) / max(vmax - vmin, 1e-8)
                uv.x = umin + in_u0 + nu * max((umax - umin) - in_u0 - in_u1, .01)
                uv.y = vmin + in_v0 + nv * max((vmax - vmin) - in_v0 - in_v1, .01)
                loops_changed += 1
    if changed:
        mesh.update()
    return {"cards_ragged": changed // 4, "vertices": changed, "uv_loops": loops_changed}
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


def _tip_cap_candidates(mesh, *, zmin, min_radius, cluster_radius, min_points, seed,
                        dead_end=0.0, max_caps=0, min_cap_radius=0.0):
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
        max_cap_radius = 0.35 if dead_end else .15
        radius = min(max(radius * .82, .045), max_cap_radius)
        if min_cap_radius and radius < min_cap_radius:
            # duenne freie Triebe nicht verlaengern: eine Kappe macht aus dem
            # schwarzen Spear nur einen laengeren Spear. Sie werden stattdessen
            # ueber BARK_TAPER_CONFIG verkuerzt und in die Krone gebogen.
            continue
        if dead_end > 0.0:
            # Sackgassen-Test: nur echte Enden kappen. Wenn jenseits der Spitze
            # weiteres Holz in Laufrichtung liegt, ist dies ein Ast mittendrin —
            # eine Kappe hier wuerde als Spear aus gesundem Holz herausragen.
            tip_arr = np.array(tip)
            axis_arr = np.array(axis)
            rel_all = pts - tip_arr
            along = rel_all @ axis_arr
            side = rel_all - along[:, None] * axis_arr[None, :]
            side_norm = np.linalg.norm(side, axis=1)
            forward = (along > dead_end * .30) & (side_norm < max(radius * 2.2, dead_end * .8))
            if int(forward.sum()) >= 3:
                continue
        out.append({"ci": ci, "tip": tip, "axis": axis, "radius": radius,
                    "hash": _hash01(ci, 47, seed)})
    if max_caps and len(out) > max_caps:
        # die freiesten/hoechsten Enden zuerst behalten, Ueberschuss verwerfen
        out.sort(key=lambda d: -(d["tip"].z + math.hypot(d["tip"].x, d["tip"].y) * .45))
        out = out[:max_caps]
    return out

def _shrink_blunt_terminal_mesh(mesh, cap_data):
    """Taper original scaffold geometry at detected dead ends before adding twigs.

    Without this the old flat/cylindrical end face remains visible behind the new
    terminal growth.  Vertices in a small local end zone are collapsed progressively
    toward the branch axis and pulled slightly back, producing a continuous wooden
    taper rather than a sawn disc.
    """
    ids=sorted({v for p in mesh.polygons if p.material_index==0 for v in p.vertices})
    changed=0
    for data in cap_data or ():
        axis=data["axis"].normalized(); tip=data["tip"]; radius=data["radius"]
        influence=max(radius*2.45,.24)
        for vi in ids:
            co=mesh.vertices[vi].co
            vec=co-tip; back=-vec.dot(axis)
            if back < -radius*.30 or back > influence: continue
            axial=tip-axis*back
            perp=co-axial; pr=perp.length
            if pr>max(radius*1.90,.09): continue
            q=max(0.0,min(1.0,back/influence))
            radial_scale=.20+.80*(q**.72)
            retreat=(1.0-q)**2*radius*.34
            co[:]=axial+perp*radial_scale-axis*retreat
            changed+=1
    if changed: mesh.update()
    return {"vertices":changed}


def _add_procedural_bark_geometry(mesh, *, seed=0, root=None, collars=(), shoot_collars=None,
                                  tip_caps=None):
    """Attach new bark/foliage construction: surface roots, junction collars and terminal growth."""
    root_burial = _bury_template_root_plates(mesh)
    centre = _estimate_trunk_center(mesh)
    shoot_data = _small_shoot_data(mesh) if shoot_collars or tip_caps else []
    cap_data = []
    if tip_caps:
        cap_args = {k: v for k, v in tip_caps.items()
                    if k in {"zmin", "min_radius", "cluster_radius", "min_points", "seed",
                             "dead_end", "max_caps", "min_cap_radius"}}
        cap_data = _tip_cap_candidates(mesh, **cap_args)
    blunt_terminal_mesh = _shrink_blunt_terminal_mesh(mesh, cap_data)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    made = {"root_plates_buried": root_burial, "blunt_terminal_mesh": blunt_terminal_mesh, "surface_roots": {"roots": 0, "faces": 0},
            "branch_collars": 0, "shoot_collars": 0, "terminal_growth": {}}
    if root:
        root_args = {k: v for k, v in root.items()
                     if k in {"count", "trunk_radius", "base_z", "length_range", "radius_range",
                              "bury_range", "sides", "rings", "oval"}}
        made["surface_roots"] = _append_surface_roots(bm, centre, seed=seed, **root_args)
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
        made["terminal_growth"] = _append_terminal_growth(
            bm, cap_data, shoot_data, seed=seed, willow=("willow" in SLUG))
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
    heart_radii = (.135, .115, .150)
    hearts = []
    for a, r in zip(heart_angles, heart_radii):
        hearts.append(Vector((base_mean.x + math.cos(a) * r,
                              base_mean.y + math.sin(a) * r, base_mean.z)))
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
            heart = base_mean + Vector(((h1 - .11) * .35, (h2 - .5) * .055, 0.0))
        else:
            ang = math.atan2(direction.y, direction.x)
            diffs = [abs((ang - a + math.pi) % (2.0 * math.pi) - math.pi) for a in heart_angles]
            hi = diffs.index(min(diffs))
            jitter_r = (h2 - .5) * .045
            jitter_a = (h1 - .5) * .18
            heart = hearts[hi] + Vector((math.cos(ang + jitter_a) * jitter_r,
                                         math.sin(ang + jitter_a) * jitter_r, 0.0))
        used.append(heart.copy())
        shift = heart - feat["base"]
        shift.z = 0.0
        for v in feat["verts"]:
            mesh.vertices[v].co += shift
            moved += 1
    mesh.update()
    centres = []
    for co in sorted({(round(c.x, 3), round(c.y, 3), round(c.z, 3)) for c in used}):
        centres.append(co)
    return {"fronds": moved, "centres": centres, "base": tuple(round(x, 3) for x in base_mean)}


def _bury_fern_crown(mesh):
    """Sink the cylindrical template core below the later soil mound instead of merely shrinking it."""
    verts = sorted({v for p in mesh.polygons if p.material_index == 0 for v in p.vertices})
    if not verts:
        return {"vertices": 0}
    pts = np.array([mesh.vertices[v].co[:] for v in verts], dtype=float)
    above = pts[pts[:, 2] > 0.0]
    if not len(above):
        return {"vertices": 0}
    centre = Vector((float(above[:, 0].mean()), float(above[:, 1].mean()), 0.0))
    changed = 0
    for v in verts:
        co = mesh.vertices[v].co
        if co.z <= 0.0:
            continue
        horiz = Vector((co.x - centre.x, co.y - centre.y, 0.0))
        mesh.vertices[v].co = Vector((centre.x + horiz.x * .72,
                                      centre.y + horiz.y * .72, co.z * .10))
        changed += 1
    mesh.update()
    return {"vertices": changed}


def _add_fern_root_mound(mesh, centre_data, *, seed=0):
    """Cover the buried core with a low soil/root mound, heart nubs and tapered surface roots."""
    if centre_data.get("base"):
        base = Vector(centre_data["base"])
    else:
        base = Vector((0, 0, .005))
    base.z = .004
    centres = [Vector(c) for c in centre_data.get("centres", [])]
    bm = bmesh.new()
    bm.from_mesh(mesh)
    made = 0
    made += len(_append_mound(bm, base, radius=.285, height=.058, sides=20, rings=3, seed=seed))
    for ci, c in enumerate(centres[:8]):
        c.z = .010
        made += len(_append_mound(bm, c, radius=.072, height=.025, sides=10, rings=2, seed=seed + 30 + ci))
    for ri in range(7):
        a = 2.0 * math.pi * ri / 7.0 + (_hash01(ri, 83, seed) - .5) * .30
        radial = Vector((math.cos(a), math.sin(a), .05 + .06 * _hash01(ri, 89, seed))).normalized()
        start = base + Vector((math.cos(a) * .055, math.sin(a) * .055, .014))
        made += len(_append_tapered_tip(bm, start, radial, length=.19 + .06 * _hash01(ri, 97, seed),
                                        radius=.020 + .006 * _hash01(ri, 101, seed), sides=7,
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


def _gnarly_bark_relief(mesh, *, seed=0):
    """Break the smooth-plastic cylinder read of the thick scaffold limbs with continuous
    multi-frequency surface noise displaced along the smooth bark normals.

    The displacement field is continuous in 3D space, so no seam can open and the UVs stay
    valid.  Amplitude is scaled per connected-component class: thick scaffold limbs gain
    visible gnarl, medium roots/collars get soft undulation, thin twigs only wobble so
    their cross-sections are never crumpled.  Runs after all bark construction and before
    the smooth-normal pass so the relief is shaded correctly.
    """
    comps = _material_components(mesh, 0)
    acc = [Vector((0, 0, 0)) for _ in mesh.vertices]
    for p in mesh.polygons:
        if p.material_index != 0:
            continue
        n = p.normal * p.area
        for v in p.vertices:
            acc[v] += n
    ph1 = _hash01(seed, 601) * 2.0 * math.pi
    ph2 = _hash01(seed, 607) * 2.0 * math.pi
    changed = 0
    for comp in comps:
        npolys = len(comp["polys"])
        if npolys > 500:
            amp_low, amp_mid = .030, .012
        elif npolys >= 45:
            amp_low, amp_mid = .016, .006
        else:
            amp_low, amp_mid = .007, .0
        for vi in comp["verts"]:
            co = mesh.vertices[vi].co
            # z < -0.3 is the pinned burial socket: leave it untouched.
            if co.z < -.30:
                continue
            n = acc[vi]
            if n.length < 1e-6:
                continue
            n = n.normalized()
            low = (math.sin(co.x * 5.1 + ph1) * math.sin(co.y * 4.63 + ph1 * 1.7)
                   * math.sin(co.z * 5.37 + ph1 * 2.3))
            mid = (math.sin(co.x * 15.3 + ph2 + co.z * 5.9) * math.sin(co.y * 14.1 + ph2 * 1.31 - co.z * 4.7)
                   * math.sin(co.z * 16.7 + ph2 * 2.07))
            d = amp_low * low + amp_mid * mid
            mesh.vertices[vi].co = Vector((co.x + n.x * d, co.y + n.y * d, co.z + n.z * d))
            changed += 1
    if changed:
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


def _lift_bark_albedo(mat, *, boost, floor, suffix):
    """Multiplicative linear-space bark lift plus a small additive floor.

    A constant gain preserves every contrast ratio of the authored bark texture, so the
    grain reads clearer rather than flatter — unlike another gamma pass, which compresses
    exactly the shadow contrast the reviewer asked to keep.  The floor only keeps true
    black crevices off zero in deep shade.

    The result must be baked into a NEW packed image via vrmeshy._replace_image: editing
    ``img.pixels`` of an already packed image in place never reaches the saved .blend,
    because the file keeps the original packed PNG bytes.
    """
    lifted = []
    made = {}
    for node in _basecolor_texture_nodes(mat):
        img = node.image
        if img in made:
            continue
        px = vrmeshy._image_pixels(img)
        # Runde 6: weiche saettigungskurve statt reinem linear-gain — der erste wurf
        # (v*boost+floor, hart geclippt) trieb die hellen flechten-/lichtstellen der
        # rinde in reines weiss, der stamm las bleich.  1-exp(-v) behaelt den gain in
        # den schatten (kontrastverhaeltnisse annaehernd proportional), komprimiert
        # aber lichter weich gegen weiss statt sie abzuschneiden.
        v = px[..., :3] * boost + floor
        rgb = 1.0 - np.exp(-v)
        out = np.concatenate([rgb, px[..., 3:]], -1)
        made[img] = vrmeshy._replace_image(img, out, suffix)
        lifted.append(made[img].name)
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image in made:
            node.image = made[node.image]
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
    """R9.2 subtractive-first geometry on the original template base.

    The authored leaf sprays and wood scaffold remain the baseline.  Geometry work is
    limited to connected-card curl plus a selective stronger fold of only the worst
    horizontal shelf sprays, aggressive non-additive shortening of measured bare shoot
    spikes, and a tightly capped number of whole endpoint-attached leaf cards.  No card
    splitting/shattering, canopy re-anchoring, loose confetti, surface roots, collars,
    terminal twig whorls, loop subdivision or broad displacement is run.
    """
    mesh = obj.data
    # Cache the template split normals before any bmesh append.  They are restored for
    # all authored loops after the small endpoint-fill pass; only the new leaf loops
    # receive newly authored canopy normals.
    template_loop_normals = [x.vector.copy() for x in mesh.corner_normals]
    template_loop_count = len(mesh.loops)
    cards = _reshape_foliage_cards(mesh, **CARD_CONFIG)
    shelf_fold = _fold_worst_shelf_cards(mesh, **SHELF_FOLD_CONFIG)
    exposed_tip_trim = _taper_exposed_bark_tips(mesh)
    scaffold_anchor_measurements = _select_scaffold_fill_anchors(
        mesh, exposed_tip_trim.get("endpoints", []),
        max_count=ENDPOINT_FILL_CONFIG.get("scaffold_cards", 6), seed=GEOMETRY_SEED,
    )
    scaffold_retract = _retract_scaffold_terminal_spikes(mesh, scaffold_anchor_measurements)
    before_fill_vertices = len(mesh.vertices)
    endpoint_fill = _add_endpoint_foliage_clusters(
        mesh, exposed_tip_trim.get("endpoints", []),
        scaffold_anchors=scaffold_retract.get("anchors", scaffold_anchor_measurements),
        **ENDPOINT_FILL_CONFIG
    )
    blockcol_new = _set_new_blockcol_white(mesh, before_fill_vertices)
    foliage_normals = _restore_template_foliage_normals(
        mesh, template_loop_normals, template_loop_count
    )
    bark_normals = _smooth_bark_normals(mesh)
    return {
        "subtractive_original_base": True,
        "cards": cards,
        "shelf_fold": shelf_fold,
        "card_split": {"disabled": True, "pieces": 0},
        "cluster_fill": {"disabled": True, "copies": 0},
        "leaf_shatter": {"disabled": True},
        "canopy_anchor": {"disabled": True},
        "tapered_tips": {"disabled": True},
        "exposed_tip_trim": exposed_tip_trim,
        "scaffold_terminal_retract": scaffold_retract,
        "endpoint_fill": endpoint_fill,
        "blockcol_new_vertices": blockcol_new,
        "lower_trunk_flare": {"disabled": True},
        "flare_teeth_dive": {"disabled": True},
        "trunk_fluting": {"disabled": True},
        "procedural_bark": {"disabled": True, "surface_roots": {"roots": 0}, "branch_collars": 0, "terminal_growth": 0},
        "gnarl_relief": {"disabled": True},
        "bark_normals": bark_normals,
        "foliage_normals": foliage_normals,
    }


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
    # R9: deutlich schwächerer, kontrasttreuer Rindenlift als die additive R8/R6-Linie.
    # Ziel ist braun lesbares Schattenholz, nicht blass-orange oder plastisch wirkende Rinde.
    bark_lifted = _lift_bark_albedo(bark, boost=1.36, floor=.009, suffix="_vr_r9lift")
    if bark_lifted:
        graded["bark_lifted"] = bark_lifted
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
    hard_max = int(math.ceil(base_tris * 1.15))
    if tris > hard_max:
        raise SystemExit(
            f"{TEMPLATE}: {tris} triangles exceed the R9 subtractive hard maximum {hard_max} "
            f"(template {base_tris} +15%)"
        )
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
