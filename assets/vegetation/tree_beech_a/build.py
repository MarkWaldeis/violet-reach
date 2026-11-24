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
from mathutils import Matrix

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
ALPHA_CUTOFF = 0.42
ROUGHNESS_MIN = 0.65


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
    graded = _configure_materials(obj, template_info)
    tris = _validate_source(obj, template_info)
    obj["fantasy_open_world_template"] = TEMPLATE
    obj["palette_grade"] = (
        f"foliage {FOLIAGE_TARGET}@{FOLIAGE_STRENGTH:.2f}, "
        f"bark {BARK_TARGET}@{BARK_STRENGTH:.2f}"
    )
    obj["graded_images"] = ",".join(graded["bark"] + graded["foliage"])
    # vrmeshy.fix_normals is deliberately not called: the hashed template already has
    # outward wood normals, and a blanket recalculation must not endanger the custom
    # smooth canopy split normals on the foliage cards.
    vrlib.link_to_source(obj)
    print(
        "VR_TREE_IMPORT",
        {"template": TEMPLATE, "triangles": tris, "graded": graded},
        flush=True,
    )
