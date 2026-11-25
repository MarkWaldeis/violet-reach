"""Wiesen-Eiche A — übernommene AAA-Tripo-Baumvorlage aus Fantasy open world.

Deterministischer Aufbau:
1. Verifiziert ``blender_reference/tripo_trees.blend`` per SHA-256 gegen das
   Staging-Manifest unter ``VR_MESHY_DIR/fantasy_open_world_import``.
2. Appendet nur ``V3_TPL_tree_meadow_oak`` (ein Mesh mit Materialslot 0 Rinde und
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
TEMPLATE = "V3_TPL_tree_meadow_oak"
SLUG = "tree_meadow_oak"
EXPECTED_Z_MIN = -0.65
TARGET_SIZE_M = (11.0, 12.0, 11.0)  # ungefähr, oberirdische Höhe im Quelltemplate
FOLIAGE_TARGET = "#4A5426"  # zwischen leaf_green #313C1D und grass_green #696F44
FOLIAGE_STRENGTH = 0.60
BARK_TARGET = "#41321D"
BARK_STRENGTH = 0.48
ALPHA_CUTOFF = 0.34
ROUGHNESS_MIN = 0.65
ASSET_KIND = "tree"
GEOMETRY_SEED = 9101
# Runde 4: Die 3x3-Laubkarten werden zuerst in vier unabhaengige Viertelstuecke
# zerlegt (jedes mit voller Blattcluster-Textur), dadurch halbiert sich die
# zusammenhaengende Kartenkomponente ohne zusaetzliche Dreiecke. Danach werden
# die Stuecke deutlich verkleinert, gestreut und mit vielen Tochterkartenstaffeln
# aufgefuellt, damit die Krone dicht statt hohl wirkt.
SPLIT_CONFIG = dict(enabled=True, seed=GEOMETRY_SEED)
CARD_CONFIG = dict(width_scale=.58, length_scale=.66, cup=.10, twist_deg=44, arch=.05,
                   tilt=True, tilt_threshold=.38, tilt_min_deg=20, tilt_max_deg=40,
                   upward_bias=.70, radial_sway=0.0, scale_jitter=.15, seed=GEOMETRY_SEED,
                   scatter_deg=30, scatter_offset=.12)
BARK_TAPER_CONFIG = dict(max_faces=48, min_faces=32, taper_start=.72, end_radius=.025,
                         length_scale=.78, bend=.075, seed=GEOMETRY_SEED)
FILL_CONFIG = dict(attach_high=False, fraction=1.0, second_fraction=.92, third_fraction=.55,
                   width_range=(.65, .90), length_range=(.68, .92),
                   yaw_deg=56, pitch_deg=40, roll_deg=30,
                   normal_offset=.155, tangent_offset=.26,
                   inward_fraction=.28, inward_pull=.55, z_jitter=.26, seed=GEOMETRY_SEED)
ROOT_CONFIG = dict(height=1.35, trunk_radius=.52, min_flare=.22, max_flare=1.22, sides=24,
                   margin=.045, falloff=1.50)
BRANCH_COLLARS = (
    dict(angle_deg=105, z=2.25, length=1.05, radius=.27, up=.38, surface_radius=.52),
    dict(angle_deg=165, z=2.45, length=1.15, radius=.29, up=.34, surface_radius=.52),
    dict(angle_deg=255, z=2.35, length=1.20, radius=.30, up=.32, surface_radius=.52),
    dict(angle_deg=285, z=2.90, length=1.05, radius=.26, up=.42, surface_radius=.52),
)
SHOOT_COLLAR_CONFIG = dict(min_faces=32, max_faces=48, fraction=.70, seed=GEOMETRY_SEED)
# Runde 4 aktiv: verjüngte Endkappen auf stumpfen Astenden, aber nur dort, wo
# hinter der Spitze wirklich kein Holz weiterlaeuft (Sackgassen-Test), damit
# keine Speere mitten aus Aesten wachsen.
TIP_CAP_CONFIG = dict(zmin=2.55, min_radius=.95, cluster_radius=.72, min_points=4,
                      length_range=(.26, .44), inset=.09, seed=GEOMETRY_SEED,
                      dead_end=.30, max_caps=22, length_radius_mul=2.1, min_cap_radius=.062)
FOLIAGE_GAMMA = .78
FOLIAGE_LIFT_FLOOR = .035
FOLIAGE_TRANSLUCENCY = .110
BARK_TRANSLUCENCY = .055


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
    obj.name = "tree_oak_a_source"
    obj.data.name = "tree_oak_a_source_mesh"
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


def _add_procedural_bark_geometry(mesh, *, seed=0, root=None, collars=(), shoot_collars=None,
                                  tip_caps=None):
    """Attach new bark geometry: root flare, joint collars and closed tapered tips."""
    centre = _estimate_trunk_center(mesh)
    shoot_data = _small_shoot_data(mesh) if shoot_collars else []
    cap_data = []
    if tip_caps:
        cap_args = {k: v for k, v in tip_caps.items()
                    if k in {"zmin", "min_radius", "cluster_radius", "min_points", "seed",
                             "dead_end", "max_caps", "min_cap_radius"}}
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
            length = max(length, data["radius"] * tip_caps.get("length_radius_mul", 2.1))
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
        uvs = _compress_fern_frond_uvs(mesh)
        hearts = _scatter_fern_hearts(mesh, seed=GEOMETRY_SEED)
        crown = _bury_fern_crown(mesh)
        fill = _duplicate_foliage_clusters(mesh, **FILL_CONFIG)
        soil = _add_fern_root_mound(mesh, hearts, seed=GEOMETRY_SEED)
        bark_normals = _smooth_bark_normals(mesh)
        foliage_normals = _recalc_foliage_normals(mesh, geom_weight=.72, up_weight=.38, radial_weight=.35)
        return {"fern_fronds": fronds, "frond_uvs": uvs, "wedelherzen": hearts,
                "root_crown": crown, "cluster_fill": fill, "soil_roots": soil,
                "bark_normals": bark_normals, "foliage_normals": foliage_normals}
    split = {"cards_split": 0, "pieces": 0}
    if SPLIT_CONFIG.get("enabled"):
        split = _split_foliage_cards(mesh, seed=SPLIT_CONFIG.get("seed", 0))
    cards = _reshape_foliage_cards(mesh, **CARD_CONFIG)
    fill = _duplicate_foliage_clusters(mesh, **FILL_CONFIG)
    tips = _taper_small_bark_tips(mesh, **BARK_TAPER_CONFIG)
    bark_geometry = _add_procedural_bark_geometry(
        mesh, seed=GEOMETRY_SEED, root=ROOT_CONFIG, collars=BRANCH_COLLARS,
        shoot_collars=SHOOT_COLLAR_CONFIG, tip_caps=TIP_CAP_CONFIG)
    bark_normals = _smooth_bark_normals(mesh)
    normals = 0
    if ASSET_KIND == "tree":
        if "willow" in SLUG:
            normals = _recalc_foliage_normals(mesh, geom_weight=.60, up_weight=.30, radial_weight=.82)
        else:
            normals = _recalc_foliage_normals(mesh, geom_weight=.60, up_weight=.58, radial_weight=.68)
    elif ASSET_KIND == "bush":
        normals = _recalc_foliage_normals(mesh, geom_weight=.66, up_weight=.50, radial_weight=.56)
    return {"cards": cards, "card_split": split, "cluster_fill": fill, "tapered_tips": tips,
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
    bark_lifted = _lift_foliage_albedo(bark, gamma=.86, floor=.022)
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
