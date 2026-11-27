"""Shared subtractive-first Blender build helpers for Fantasy Open World tree assets.

Used by tree_oak_a, tree_beech_a, tree_ancient_a, and tree_willow_a.
Keeps authored template topology, UVs, blockcol, buried base (z_min = -0.65 m),
and custom smooth canopy split normals intact while applying palette grading,
alpha cutout wiring, mild connected card reshaping, and subtractive bare-tip trim.
"""
import hashlib
import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.geometry import closest_point_on_tri

import vrlib
import vrmeshy


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _staging_paths():
    root = os.path.join(vrmeshy.meshy_dir(), "fantasy_open_world_import")
    return {
        "root": root,
        "blend": os.path.join(root, "blender_reference", "tripo_trees.blend"),
        "manifest": os.path.join(root, "manifest.json"),
        "template_manifest": os.path.join(root, "blender_reference", "tripo_trees_manifest.json"),
        "leaf_textures": os.path.join(root, "leaf_textures"),
    }


def _verify_library(paths, template_name):
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
    if template_name not in templates:
        raise SystemExit(f"{template_name} is missing in tripo_trees_manifest.json")
    return templates[template_name]


def _append_template(paths, template_name, source_name):
    before = set(bpy.data.objects)
    bpy.ops.wm.append(
        filepath=os.path.join(paths["blend"], "Object", template_name),
        directory=os.path.join(paths["blend"], "Object"),
        filename=template_name,
        link=False,
    )
    new = [o for o in bpy.data.objects if o not in before]
    obj = next((o for o in new if o.type == "MESH" and o.name.split(".")[0] == template_name), None)
    if obj is None:
        raise SystemExit(f"appending {template_name} produced no matching mesh object")
    for extra in new:
        if extra is not obj:
            bpy.data.objects.remove(extra, do_unlink=True)
    obj.name = f"{source_name}_source"
    obj.data.name = f"{source_name}_source_mesh"
    return obj


def _verify_packed_textures(paths, template_info):
    """Compare packed PNG bytes in the .blend against read-only provenance copies."""
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


def _hash01(*vals):
    x = 0.0
    for i, v in enumerate(vals):
        x += math.sin((i + 1) * 127.1 + float(v) * 311.7) * 43758.5453
    return x - math.floor(x)


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


def _lift_foliage_albedo(mat, *, gamma, floor):
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
    """Soft shadow-preserving bark lift baked into a new packed image."""
    lifted = []
    made = {}
    for node in _basecolor_texture_nodes(mat):
        img = node.image
        if img in made:
            continue
        px = vrmeshy._image_pixels(img)
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


def _occlusion_group():
    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
    if not any(socket.name == "Occlusion" for socket in group.interface.items_tree):
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return group


def _wire_orm_occlusion(mat):
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


def _configure_foliage_alpha(mat, alpha_cutoff):
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
    clip.inputs[1].default_value = alpha_cutoff
    for link in list(clip.inputs[0].links):
        mat.node_tree.links.remove(link)
    mat.node_tree.links.new(image_node.outputs["Alpha"], clip.inputs[0])
    mat.node_tree.links.new(clip.outputs[0], alpha_socket)
    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "HASHED"
    if hasattr(mat, "alpha_threshold"):
        mat.alpha_threshold = alpha_cutoff


def _configure_materials(obj, template_info, cfg):
    mats = {m.name.split(".")[0]: m for m in _materials(obj)}
    bark = mats.get(template_info["bark_material"])
    foliage = mats.get(template_info["foliage_material"])
    if bark is None or foliage is None:
        raise SystemExit(
            f"{cfg['template']}: expected materials {template_info['materials']}, "
            f"got {[m.name for m in _materials(obj)]}"
        )
    vrmeshy.clamp_material([obj], roughness_min=cfg.get("roughness_min", 0.65), metallic=0.0)
    graded = {
        "bark": _grade_material_basecolor(bark, cfg.get("bark_target", "#41321D"), cfg.get("bark_strength", 0.36), "_vr_bark"),
        "foliage": _grade_material_basecolor(foliage, cfg.get("foliage_target", "#696F44"), cfg.get("foliage_strength", 0.80), "_vr_olive"),
    }
    lifted = _lift_foliage_albedo(
        foliage, gamma=cfg.get("foliage_gamma", 0.78), floor=cfg.get("foliage_lift_floor", 0.035)
    )
    if lifted:
        graded["foliage_lifted"] = lifted
    bark_lifted = _lift_bark_albedo(
        bark, boost=cfg.get("bark_boost", 1.36), floor=cfg.get("bark_floor", 0.009), suffix="_vr_r9lift"
    )
    if bark_lifted:
        graded["bark_lifted"] = bark_lifted
    _wire_foliage_translucency(foliage, cfg.get("foliage_translucency", 0.220))
    _wire_foliage_translucency(bark, cfg.get("bark_translucency", 0.088))
    for mat in (bark, foliage):
        bsdf = _principled(mat)
        bsdf.inputs["Metallic"].default_value = 0.0
        _wire_orm_occlusion(mat)
    bark.use_backface_culling = True
    _configure_foliage_alpha(foliage, cfg.get("alpha_cutoff", 0.34))
    return graded


def _material_components(mesh, material_index):
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
    return [
        {
            "polys": polys,
            "poly_indices": [p.index for p in polys],
            "verts": sorted({v for p in polys for v in p.vertices}),
        }
        for polys in comps.values()
    ]


def _foliage_components(mesh, material_index=1):
    return [c["polys"] for c in _material_components(mesh, material_index)]


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


def _reshape_foliage_cards(
    mesh,
    *,
    width_scale=1.0,
    length_scale=1.0,
    cup=0.035,
    twist_deg=8.0,
    arch=0.015,
    tilt=True,
    tilt_threshold=0.42,
    tilt_min_deg=7.0,
    tilt_max_deg=14.0,
    upward_bias=0.62,
    radial_sway=0.0,
    scale_jitter=0.0,
    attach_high=False,
    taper_bottom=0.0,
    length_jitter=0.0,
    seed=0,
):
    """Bend, taper, and re-pitch authored 3x3 leaf cards without breaking topology."""
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
        if length_jitter:
            lscale *= 1.0 + (h4 * 2.0 - 1.0) * length_jitter
        for v, u, w, co in rows:
            dist_frac = (1.0 - w) if attach_high else w
            # Taper hanging tips when taper_bottom > 0 (breaks rectangular willow curtains)
            tip_w = 1.0 - taper_bottom * (0.35 + 0.65 * h2) * (dist_frac ** 1.25) if taper_bottom > 0 else 1.0
            d = co - origin
            x = d.dot(uhat) * wscale * tip_w
            y = d.dot(vhat) * lscale
            z = d.dot(nhat)
            z += cup_sign * cup * math.sin(math.pi * u)
            z += arch_sign * arch * math.sin(math.pi * dist_frac)
            x += (h4 - .5) * cup * .35 * math.sin(math.pi * dist_frac)
            a = twist * (dist_frac - .5)
            ca, sa = math.cos(a), math.sin(a)
            x, z = ca * x - sa * z, sa * x + ca * z
            co2 = origin + uhat * x + vhat * y + nhat * z
            if radial_sway:
                radial = Vector((center.x, center.y, 0.0))
                if radial.length > 1e-5:
                    radial.normalize()
                    tangent = Vector((-radial.y, radial.x, 0.0))
                    direction = radial if attach_high else (-radial if h2 < .58 else radial)
                    offset = direction * (radial_sway * (.25 + .75 * dist_frac) * (.45 + h3))
                    offset += tangent * (h4 - .5) * radial_sway * .55 * math.sin(math.pi * dist_frac)
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


def _fold_worst_shelf_cards(
    mesh,
    *,
    max_cards=28,
    min_span=2.05,
    min_normal_z=.88,
    pitch_min_deg=26.0,
    pitch_max_deg=36.0,
    cup=.105,
    arch=.055,
    seed=0,
):
    """Selectively pitch/fold the largest horizontal authored leaf sprays."""
    features = _leaf_card_features(mesh, material_index=1, attach_high=False)
    candidates = []
    for feat in features:
        flat = abs(feat["nhat"].z)
        if feat["span"] < min_span or flat < min_normal_z:
            continue
        candidates.append((feat["span"] * flat, feat))
    candidates.sort(key=lambda item: (-item[0], item[1]["ci"]))
    selected = [feat for _score, feat in candidates[:max_cards]]
    moved = 0
    for feat in selected:
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
            fold = fold_sign * this_cup * math.sin(math.pi * u) + arch_sign * this_arch * math.sin(math.pi * w)
            co2 += nrot * fold
            co2.z -= droop * max(0.0, w - .42) ** 2
            mesh.vertices[v].co = co2
            moved += 1
    if moved:
        mesh.update()
    return {"cards": len(selected), "vertices": moved}


def _foliage_distance_sampler(mesh):
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
    """Subtractive trim of only the most exposed loose shoot tubes."""
    comps = _material_components(mesh, 0)
    small = [c for c in comps if min_faces <= len(c["polys"]) <= max_faces]
    small_ids = {id(c) for c in small}
    large_verts = sorted({v for c in comps if id(c) not in small_ids for v in c["verts"]})
    if not large_verts:
        large_verts = sorted({v for c in comps for v in c["verts"]})
    foliage_verts = sorted({v for p in mesh.polygons if p.material_index == 1 for v in p.vertices})
    if not small or not large_verts or not foliage_verts:
        return {"pieces": 0, "vertices": 0, "endpoints": []}
    ref = np.array([mesh.vertices[v].co[:] for v in large_verts], dtype=float)
    foliage_dist_fn = _foliage_distance_sampler(mesh)

    candidates = []
    for ci, comp in enumerate(small):
        pts, _centre, _axis0, e0, e1, length0 = _component_pca(mesh, comp["verts"])
        d0 = float(((ref - np.array(e0)) ** 2).sum(axis=1).min())
        d1 = float(((ref - np.array(e1)) ** 2).sum(axis=1).min())
        base, tip = (e0, e1) if d0 <= d1 else (e1, e0)
        axis = tip - base
        if axis.length < 1e-5:
            continue
        axis.normalize()
        sample_dists = [foliage_dist_fn(base + axis * (length0 * t)) for t in (.50, .62, .75, .88, 1.0)]
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
        score = mean_outer * 1.45 + foliage_dist + max(0.0, tip.z - 5.2) * .035 + max(axis.z, 0.0) * .09 + radial_tip * .018
        candidates.append({
            "ci": ci, "comp": comp, "base": base, "tip": tip, "axis": axis.copy(),
            "length": length0, "foliage_dist": foliage_dist, "mean_outer": mean_outer,
            "radius": radius, "score": score,
        })
    candidates.sort(key=lambda c: (-c["score"], -c["tip"].z, c["ci"]))
    selected = candidates[:max_count]
    changed = 0
    endpoints = []
    for item in selected:
        comp = item["comp"]
        base, tip, axis = item["base"], item["tip"], item["axis"]
        length = max((tip - base).length, 1e-6)
        exposure01 = min(max((item["mean_outer"] - .10) / .32, 0.0), 1.0)
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
    return {"pieces": len(selected), "vertices": changed, "endpoints": endpoints}


def _tip_cap_candidates(mesh, *, zmin, min_radius, cluster_radius, min_points, seed, dead_end=0.0):
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
        if dead_end > 0.0:
            tip_arr = np.array(tip)
            axis_arr = np.array(axis)
            rel_all = pts - tip_arr
            along = rel_all @ axis_arr
            side = rel_all - along[:, None] * axis_arr[None, :]
            side_norm = np.linalg.norm(side, axis=1)
            forward = (along > dead_end * .30) & (side_norm < max(radius * 2.2, dead_end * .8))
            if int(forward.sum()) >= 3:
                continue
        out.append({"ci": ci, "tip": tip, "axis": axis, "radius": radius, "hash": _hash01(ci, 47, seed)})
    return out


def _select_scaffold_fill_anchors(mesh, shoot_endpoints, *, max_count=6, seed=0):
    if max_count <= 0:
        return []
    distance = _foliage_distance_sampler(mesh)
    shoot_tips = [Vector(e["tip"]) for e in shoot_endpoints or ()]
    candidates = _tip_cap_candidates(
        mesh, zmin=4.7, min_radius=.10, cluster_radius=.55, min_points=3, seed=seed, dead_end=.24
    )
    rows = []
    for cand in candidates:
        tip, axis = Vector(cand["tip"]), Vector(cand["axis"])
        if axis.length < 1e-5:
            continue
        axis.normalize()
        radius = float(cand["radius"])
        if not (.065 <= radius <= .29) or not (4.8 <= tip.z <= 9.6) or axis.z < .12:
            continue
        if any((tip - shoot_tip).length < .55 for shoot_tip in shoot_tips):
            continue
        fdist = distance(tip)
        high_sky = tip.z >= 8.55
        if fdist < .24 and not high_sky:
            continue
        radial_len = math.hypot(tip.x, tip.y)
        score = min(fdist, 1.2) * 1.55 + max(0.0, tip.z - 5.0) * .045 + max(axis.z, 0.0) * .10 + max(0.0, 3.8 - radial_len) * .05
        if high_sky:
            score += .18
        rows.append({"tip": tip, "axis": axis, "radius": radius, "foliage_distance": fdist, "score": score, "ci": cand["ci"]})
    rows.sort(key=lambda r: (-r["score"], -r["tip"].z, r["ci"]))

    def far_enough(row, sel):
        return all((row["tip"] - other["tip"]).length >= .72 for other in sel)

    selected = []
    for row in [r for r in rows if r["tip"].z >= 7.2]:
        if len(selected) >= min(2, max_count):
            break
        if far_enough(row, selected):
            selected.append(row)
    for row in rows:
        if len(selected) >= max_count:
            break
        if row not in selected and far_enough(row, selected):
            selected.append(row)
    return [
        {
            "component": row["ci"],
            "tip": tuple(round(float(x), 4) for x in row["tip"]),
            "axis": tuple(round(float(x), 4) for x in row["axis"]),
            "radius": round(row["radius"], 4),
            "foliage_distance": round(row["foliage_distance"], 4),
            "score": round(row["score"], 4),
        }
        for row in selected
    ]


def _retract_scaffold_terminal_spikes(mesh, scaffold_anchors, *, max_items=4):
    anchors = [dict(a) for a in (scaffold_anchors or ())]
    if not anchors or max_items <= 0:
        return {"pieces": 0, "vertices": 0, "anchors": anchors}
    comps = _material_components(mesh, 0)
    if not comps:
        return {"pieces": 0, "vertices": 0, "anchors": anchors}
    large = max(comps, key=lambda c: len(c["polys"]))
    large_ids = set(large["verts"])
    ranked = []
    for ai, anchor in enumerate(anchors):
        tip, axis = Vector(anchor["tip"]), Vector(anchor["axis"])
        if axis.length < 1e-5:
            continue
        axis.normalize()
        radius = max(float(anchor.get("radius", .08)), .04)
        if not (axis.z >= .42 or tip.z >= 7.2):
            continue
        priority = tip.z * .16 + axis.z + min(float(anchor.get("foliage_distance", 0.0)), 1.0)
        ranked.append((priority, ai, tip, axis, radius))
    ranked.sort(key=lambda item: (-item[0], -item[2].z, item[1]))
    changed_ids = set()
    pieces = 0
    for _prio, ai, tip, axis, radius in ranked[:max_items]:
        retreat = min(max(radius * 3.2, .30), .62)
        influence = max(retreat * 2.15, radius * 5.0, .58)
        radial_limit = max(radius * 1.18, .105)
        affected = 0
        for vi in sorted(large_ids):
            if vi in changed_ids:
                continue
            co = mesh.vertices[vi].co
            back = -(co - tip).dot(axis)
            if back < -radius * .35 or back > influence:
                continue
            axial = tip - axis * back
            perp = co - axial
            if perp.length > radial_limit:
                continue
            q = min(max(back / max(influence, 1e-6), 0.0), 1.0)
            shift = retreat * ((1.0 - q) ** 1.15)
            radial_scale = .34 + .66 * (q ** .78)
            co[:] = axial + perp * radial_scale - axis * shift
            changed_ids.add(vi)
            affected += 1
        if affected >= 3:
            final_tip = tip - axis * retreat
            anchors[ai]["original_tip"] = anchors[ai]["tip"]
            anchors[ai]["tip"] = tuple(round(float(x), 4) for x in final_tip)
            anchors[ai]["retracted"] = True
            pieces += 1
    if changed_ids:
        mesh.update()
    return {"pieces": pieces, "vertices": len(changed_ids), "anchors": anchors}


def _orthogonal_frame(axis):
    axis = axis.normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < .88 else Vector((0, 1, 0))
    e1 = axis.cross(ref)
    if e1.length < 1e-6:
        e1 = Vector((1, 0, 0))
    e1.normalize()
    return e1, axis.cross(e1).normalized()


def _leaf_atlas_rect(h):
    u0 = .008 if _hash01(h, 401) < .5 else .508
    v0 = .008 if _hash01(h, 409) < .5 else .508
    return (u0, v0, u0 + .484, v0 + .484)


def _write_face_uvs(face, uv_layer, uvs):
    if uv_layer is not None:
        for loop, uv in zip(face.loops, uvs):
            loop[uv_layer].uv = uv


def _append_leaf_card(bm, base, vhat, *, width, length, seed=0, material_index=1,
                      uv_rect=(.008, .008, .492, .492), reverse_v=False, cup=.045,
                      twist_deg=24.0, pinch=.24):
    if vhat.length < 1e-6:
        return []
    vhat = vhat.normalized()
    horizontal = Vector((vhat.x, vhat.y, 0.0))
    uhat = Vector((-horizontal.y, horizontal.x, 0.0)).normalized() if horizontal.length > 1e-5 else Vector((1, 0, 0))
    nhat = uhat.cross(vhat)
    nhat = Vector((0, 0, 1)) if nhat.length < 1e-6 else nhat.normalized()
    uv_layer = bm.loops.layers.uv.active
    twist = math.radians((_hash01(seed, 421) * 2.0 - 1.0) * twist_deg)
    curl = (_hash01(seed, 427) - .5) * width * .18
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
            lattice[(iu, iv)] = bm.verts.new(
                base + vhat * (length * w) + u2 * x + n2 * camber + uhat * (curl * math.sin(math.pi * w))
            )
    faces = []
    umin, vmin, umax, vmax = uv_rect
    for iv in range(2):
        for iu in range(2):
            keys = ((iu, iv), (iu + 1, iv), (iu + 1, iv + 1), (iu, iv + 1))
            face = bm.faces.new(tuple(lattice[k] for k in keys))
            face.material_index = material_index
            uvs = [
                (
                    umin + (ku / 2.0) * (umax - umin),
                    vmax - (kv / 2.0) * (vmax - vmin) if reverse_v else vmin + (kv / 2.0) * (vmax - vmin),
                )
                for ku, kv in keys
            ]
            _write_face_uvs(face, uv_layer, uvs)
            faces.append(face)
    return faces


def _add_endpoint_foliage_clusters(mesh, shoot_endpoints, *, max_cards=34, scaffold_cards=6, seed=0, scaffold_anchors=None):
    if max_cards <= 0:
        return {"cards": 0, "faces": 0, "vertices": 0}
    endpoints = sorted([dict(item) for item in (shoot_endpoints or ())],
                       key=lambda e: (-e.get("score", 0.0), -e.get("tip", (0, 0, 0))[2]))
    scaffold = (_select_scaffold_fill_anchors(mesh, endpoints, max_count=scaffold_cards, seed=seed)
                if scaffold_anchors is None else [dict(a) for a in scaffold_anchors[:scaffold_cards]])
    remaining = max(0, max_cards - len(scaffold))
    plan = []
    for endpoint in endpoints:
        for copy_no in range(2):
            if remaining <= 0:
                break
            plan.append(("shoot", endpoint, copy_no))
            remaining -= 1
    for endpoint in scaffold:
        plan.append(("scaffold", endpoint, 0))
    if not plan:
        return {"cards": 0, "faces": 0, "vertices": 0}

    before_vertices = len(mesh.vertices)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    zup = Vector((0, 0, 1))
    cards, faces_made = 0, 0
    for pi, (kind, endpoint, copy_no) in enumerate(plan):
        tip, axis = Vector(endpoint["tip"]), Vector(endpoint["axis"])
        if axis.length < 1e-5:
            continue
        axis.normalize()
        radius = max(float(endpoint.get("radius", .035)), .02)
        radial = Vector((tip.x, tip.y, 0.0))
        if radial.length < .12:
            radial = Vector((axis.x, axis.y, 0.0))
        radial = Vector((1.0, 0.0, 0.0)) if radial.length < 1e-5 else radial.normalized()
        e1, e2 = _orthogonal_frame(axis)
        h1, h2, h3 = _hash01(pi, copy_no, 701, seed), _hash01(pi, copy_no, 707, seed), _hash01(pi, copy_no, 709, seed)
        h4, h5, h6 = _hash01(pi, copy_no, 719, seed), _hash01(pi, copy_no, 727, seed), _hash01(pi, copy_no, 733, seed)
        side = e1 * (1.0 if h2 < .5 else -1.0) + e2 * ((h3 - .5) * .75)
        side = e1.copy() if side.length < 1e-5 else side.normalized()
        if kind == "scaffold":
            direction = axis * .32 - radial * (.16 + .10 * h1) + zup * (.52 + .08 * h2) + side * (.18 + .14 * h3)
            width, length = 1.12 + .34 * h1, 1.25 + .34 * h2
        elif copy_no == 0:
            direction = axis * .46 + radial * (.24 + .10 * h1) + zup * (.50 + .10 * h2) + side * ((h3 - .5) * .22)
            width, length = 1.02 + .32 * h1, 1.14 + .34 * h2
        else:
            direction = axis * .24 - radial * (.24 + .10 * h1) + zup * (.48 + .10 * h2) + side * (.30 + .16 * h3)
            width, length = (1.02 + .32 * h1) * (.86 + .12 * h4), (1.14 + .34 * h2) * (.90 + .12 * h5)
        direction = zup.copy() if direction.length < 1e-5 else direction.normalized()
        if direction.z < .18:
            direction = (direction + zup * (.18 - direction.z)).normalized()
        if tip.z > 9.2:
            length *= .88
        base = tip - axis * (.022 + min(radius * .55, .045)) + side * ((h5 - .5) * min(radius * .45, .032))
        faces = _append_leaf_card(
            bm, base, direction, width=width, length=length, seed=seed + pi * 31 + copy_no,
            uv_rect=_leaf_atlas_rect(seed + pi * 17 + copy_no * 5), cup=.040 + .025 * h4,
            twist_deg=24.0 + 10.0 * h5, pinch=.20 + .08 * h6,
        )
        if faces:
            cards += 1
            faces_made += len(faces)
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    return {"cards": cards, "faces": faces_made, "vertices": len(mesh.vertices) - before_vertices}


def _set_new_blockcol_white(mesh, first_new_vertex):
    attr = mesh.color_attributes.get("blockcol")
    if attr is None or attr.domain != "POINT":
        return 0
    changed = 0
    for vi in range(first_new_vertex, min(len(mesh.vertices), len(attr.data))):
        attr.data[vi].color = (1.0, 1.0, 1.0, 1.0)
        changed += 1
    return changed


def _restore_template_foliage_normals(mesh, template_normals, original_loop_count):
    if not template_normals:
        return {"template_loops": 0, "new_foliage_loops": 0}
    acc = [Vector((0, 0, 0)) for _ in mesh.vertices]
    for p in mesh.polygons:
        if p.material_index == 1:
            n = p.normal * p.area
            for v in p.vertices:
                acc[v] += n
    loop_poly = {li: p for p in mesh.polygons for li in p.loop_indices}
    out = [template_normals[li].copy() if li < original_loop_count and li < len(template_normals) else Vector((0, 0, 1))
           for li in range(len(mesh.loops))]
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
        canopy = (radial.normalized() * .52 + Vector((0, 0, .78))).normalized() if radial.length > .15 else Vector((0, 0, 1))
        if geom.dot(canopy) < 0.0:
            geom = -geom
        out[li] = (geom * .58 + canopy * .42).normalized()
        authored += 1
    mesh.normals_split_custom_set(out)
    mesh.update()
    return {"template_loops": min(len(mesh.loops), original_loop_count), "new_foliage_loops": authored}


def _smooth_bark_normals(mesh):
    """Use area-weighted smooth split normals on wood while leaving foliage loops untouched."""
    old = [x.vector.copy() for x in mesh.corner_normals]
    acc = [Vector((0, 0, 0)) for _ in mesh.vertices]
    for p in mesh.polygons:
        if p.material_index == 0:
            n = p.normal * p.area
            for v in p.vertices:
                acc[v] += n
    loop_poly = {li: p for p in mesh.polygons for li in p.loop_indices}
    changed = 0
    for li, loop in enumerate(mesh.loops):
        if loop_poly[li].material_index != 0:
            continue
        v = loop.vertex_index
        if acc[v].length > 1e-6:
            old[li] = acc[v].normalized()
            changed += 1
    mesh.normals_split_custom_set(old)
    mesh.update()
    return changed


def _validate_source(obj, template_info, cfg):
    me = obj.data
    tris = vrlib.triangle_count([obj])
    base_tris = int(template_info["tris"])
    if tris < base_tris:
        raise SystemExit(f"{cfg['template']}: {tris} triangles, below verified template floor {base_tris}")
    hard_max = int(math.ceil(base_tris * cfg.get("max_triangle_factor", 1.15)))
    if tris > hard_max:
        raise SystemExit(f"{cfg['template']}: {tris} triangles exceed R9 subtractive max {hard_max}")
    if me.color_attributes.get(template_info["color_attribute"]) is None:
        raise SystemExit(f"{cfg['template']}: color attribute {template_info['color_attribute']} is missing")
    if not getattr(me, "has_custom_normals", False) and me.attributes.get("custom_normal") is None:
        raise SystemExit(f"{cfg['template']}: custom smooth canopy normals are missing")
    lo, hi = vrlib.world_bounds([obj])
    ez = cfg.get("expected_z_min", -0.65)
    if abs(lo.z - ez) > 0.025:
        raise SystemExit(f"{cfg['template']}: z_min {lo.z:.3f}, expected about {ez:.2f}")
    size = hi - lo
    for axis, actual, target in zip("XYZ", (size.x, size.y, hi.z), cfg["target_size_m"]):
        if abs(actual - target) / target > 0.12:
            raise SystemExit(f"{cfg['template']}: {axis} size {actual:.3f} m outside ca. target {target:.3f} m")
    return tris


def build_tree(cfg):
    """Build a subtractive-first Fantasy Open World tree into the Blender SOURCE collection."""
    paths = _staging_paths()
    template_info = _verify_library(paths, cfg["template"])
    obj = _append_template(paths, cfg["template"], cfg["asset_id"])
    _verify_packed_textures(paths, template_info)
    _centre_footprint(obj)

    mesh = obj.data
    template_loop_normals = [x.vector.copy() for x in mesh.corner_normals]
    template_loop_count = len(mesh.loops)

    geom = {"subtractive_original_base": True}
    if cfg.get("card_config"):
        geom["cards"] = _reshape_foliage_cards(mesh, **cfg["card_config"])
    if cfg.get("shelf_fold_config"):
        geom["shelf_fold"] = _fold_worst_shelf_cards(mesh, **cfg["shelf_fold_config"])
    endpoints = []
    if cfg.get("tip_trim_config"):
        trim = _taper_exposed_bark_tips(mesh, **cfg["tip_trim_config"])
        endpoints = trim.get("endpoints", [])
        geom["exposed_tip_trim"] = {"pieces": trim["pieces"], "vertices": trim["vertices"]}
    if cfg.get("endpoint_fill_config"):
        fill_cfg = dict(cfg["endpoint_fill_config"])
        scaffold_anchors = _select_scaffold_fill_anchors(
            mesh, endpoints, max_count=fill_cfg.get("scaffold_cards", 6), seed=fill_cfg.get("seed", 0)
        )
        if cfg.get("scaffold_retract_max", 0) > 0:
            retract = _retract_scaffold_terminal_spikes(
                mesh, scaffold_anchors, max_items=cfg["scaffold_retract_max"]
            )
            scaffold_anchors = retract.get("anchors", scaffold_anchors)
            geom["scaffold_retract"] = {"pieces": retract["pieces"], "vertices": retract["vertices"]}
        before_verts = len(mesh.vertices)
        geom["endpoint_fill"] = _add_endpoint_foliage_clusters(
            mesh, endpoints, scaffold_anchors=scaffold_anchors, **fill_cfg
        )
        geom["blockcol_new_vertices"] = _set_new_blockcol_white(mesh, before_verts)
        geom["foliage_normals"] = _restore_template_foliage_normals(
            mesh, template_loop_normals, template_loop_count
        )
    else:
        geom["foliage_normals"] = "template_custom_preserved"

    geom["bark_normals"] = _smooth_bark_normals(mesh)
    graded = _configure_materials(obj, template_info, cfg)
    tris = _validate_source(obj, template_info, cfg)

    obj["fantasy_open_world_template"] = cfg["template"]
    obj["palette_grade"] = (
        f"foliage {cfg.get('foliage_target', '#696F44')}@{cfg.get('foliage_strength', 0.80):.2f}, "
        f"bark {cfg.get('bark_target', '#41321D')}@{cfg.get('bark_strength', 0.36):.2f}"
    )
    obj["graded_images"] = ",".join(graded["bark"] + graded["foliage"])
    obj["geometry_revision"] = json.dumps(geom, sort_keys=True)
    vrlib.link_to_source(obj)
    print("VR_TREE_IMPORT", {"template": cfg["template"], "triangles": tris, "graded": graded, "geometry": geom}, flush=True)
