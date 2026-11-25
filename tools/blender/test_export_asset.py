"""blender -b --factory-startup --python tools/blender/test_export_asset.py"""
import json
from pathlib import Path
import runpy
import sys
import tempfile

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vrlib
from canopy_lod import restore_vertical_extent

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
source = bpy.data.collections.new(vrlib.SOURCE_COLLECTION)
bpy.context.scene.collection.children.link(source)
vertices, faces, indices = [], [], []
for x in range(20):
    for y in range(8):
        start = len(vertices)
        for u, v in ((x, y), (x+1, y), (x+1, y+1), (x, y+1)):
            vertices.append((u/20, v/8, abs(v/8-.5)*.15))
        faces.append(tuple(range(start, start+4)))
        indices.append(int(x >= 10))
for i in range(100):
    start = len(vertices)
    x = 1.2+i*.03
    vertices.extend(((x, 0, 0), (x+.008, 0, 0), (x, .008, 0), (x, 0, .008)))
    for a, b, c in ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)):
        faces.append((start+a, start+b, start+c))
        indices.append(0)
mesh = bpy.data.meshes.new("Leaf")
mesh.from_pydata(vertices, [], faces)
obj = bpy.data.objects.new("Leaf", mesh)
source.objects.link(obj)
for name, colour in (("Green", (.08, .31, .12, 1)), ("Dry", (.7, .45, .15, 1))):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = colour
    mesh.materials.append(material)
for polygon, index in zip(mesh.polygons, indices):
    polygon.material_index = index

bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=.3, location=(2, 0, 1))
trunk = bpy.context.object
for collection in list(trunk.users_collection):
    collection.objects.unlink(trunk)
source.objects.link(trunk)
trunk.data.materials.append(mesh.materials[0])

with tempfile.TemporaryDirectory() as folder:
    asset = Path(folder)
    (asset / "asset.json").write_text(json.dumps({"id": "leaf", "category": "vegetation", "texture_size": 128, "lod_triangles": [128, 32, 8]}))
    sys.argv = ["blender", "--", folder, folder]
    result = runpy.run_path(str(Path(__file__).with_name("export_asset.py")))
    counts = [vrlib.triangle_count([obj]) for obj in result["lods"]]
    assert all(0 < count <= target for count, target in zip(counts, (128, 32, 8))), counts
    image = result["images"]["basecolor"]
    pixels = np.array(image.pixels[:]).reshape(128, 128, 4)
    lod0 = result["lod0"]
    uv = lod0.data.uv_layers.active.data
    colours = []
    for face in lod0.data.polygons:
        centre = sum((uv[i].uv for i in face.loop_indices), uv[face.loop_indices[0]].uv*0)/len(face.loop_indices)
        colour = pixels[min(127, int(centre.y*128)), min(127, int(centre.x*128)), :3]
        assert colour.max() > .03, (tuple(centre), colour)
        colours.append(colour)
    assert any(c[1] > c[0]*1.5 for c in colours), colours
    assert any(c[0] > c[1]*1.2 for c in colours), colours
    assert image.colorspace_settings.name == "sRGB"
    assert result["images"]["normal"].colorspace_settings.name == "Non-Color"
    assert (asset / "leaf.raw.glb").is_file()
print("PASS: disconnected thin leaf welds into bounded LODs; both source colours bake without black face centres")

# Regression for the last-resort vertex clusterer: the tiny high triangle collapses away at
# the selected grid size.  Its cluster positions must not remain as invisible vertices that
# make restore_vertical_extent measure a longer trunk than the visible faces actually have.
cluster_mesh = bpy.data.meshes.new("Cluster orphan regression")
cluster_mesh.from_pydata([
    (0, 0, 0), (4, 0, 0), (0, 0, 6),
    (4, 0, 9.1), (4.3, 0, 9.4), (4, 0.3, 9.2),
], [], [(0, 1, 2), (3, 4, 5)])
cluster_mesh.update()
cluster_obj = bpy.data.objects.new("Cluster orphan regression", cluster_mesh)
bpy.context.scene.collection.objects.link(cluster_obj)
cluster_low = min(vertex.co.z for vertex in cluster_mesh.vertices)
cluster_high = max(vertex.co.z for vertex in cluster_mesh.vertices)
assert result["_vertex_cluster_decimate"](cluster_obj, 1)
assert 0 < vrlib.triangle_count([cluster_obj]) <= 1
referenced = sorted({index for face in cluster_obj.data.polygons for index in face.vertices})
assert len(cluster_obj.data.vertices) == len(referenced), (len(cluster_obj.data.vertices), referenced)
restore_vertical_extent(cluster_obj.data, cluster_low, cluster_high)
visible_z = [cluster_obj.data.vertices[index].co.z for face in cluster_obj.data.polygons
             for index in face.vertices]
visible_span = max(visible_z) - min(visible_z)
assert abs(min(visible_z) - cluster_low) < 1e-5, (min(visible_z), cluster_low)
assert abs(max(visible_z) - cluster_high) < 1e-5, (max(visible_z), cluster_high)
print(f"PASS: clustered fallback drops faceless cells; visible wood span restores to "
      f"{visible_span:.3f}/{cluster_high - cluster_low:.3f}")

# ---- class B: a prepared Meshy raw model exports without a re-bake ----
import hashlib
import os
import shutil
import struct
import subprocess

import vrmeshy

ROOT = Path(__file__).resolve().parents[2]


def wire_image(mat, image, socket, channel=None):
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    if channel:
        sep = mat.node_tree.nodes.new("ShaderNodeSeparateColor")
        mat.node_tree.links.new(node.outputs["Color"], sep.inputs["Color"])
        mat.node_tree.links.new(sep.outputs[channel], socket)
    else:
        mat.node_tree.links.new(node.outputs["Color"], socket)
    return node


def small_image(name, size, fn):
    img = bpy.data.images.new(name, size, size, alpha=True)
    px = [fn(x / (size - 1), y / (size - 1)) for y in range(size) for x in range(size)]
    img.pixels = [c for p in px for c in p]
    return img


with tempfile.TemporaryDirectory() as work:
    lib = Path(work) / "library"
    model_dir = lib / "meshy_rock" / "model" / "B-t1"
    model_dir.mkdir(parents=True)
    asset = Path(work) / "assets" / "props" / "meshy_rock"
    asset.mkdir(parents=True)

    # A fake "Meshy" GLB: UV unwrapped blob + loose chip, with real image textures.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=48, radius=1, location=(5, 5, 3))
    blob = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=0.04, location=(5, 5, 5.6))
    chip = bpy.context.object
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = blob
    bpy.ops.object.join()
    mat = bpy.data.materials.new("meshy_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    basecolor = small_image("meshy_basecolor", 128,
                            lambda u, v: ((u * 8) % 1 > 0.5, (v * 8) % 1 > 0.5, 0.6, 1.0))
    orm = small_image("meshy_orm", 64, lambda u, v: (0.0, 0.3, 0.9, 1.0))
    normal_img = small_image("meshy_normal", 64, lambda u, v: (0.5, 0.5, 1.0, 1.0))
    orm.colorspace_settings.name = normal_img.colorspace_settings.name = "Non-Color"
    wire_image(mat, basecolor, bsdf.inputs["Base Color"])
    wire_image(mat, orm, bsdf.inputs["Roughness"], "Green")
    wire_image(mat, orm, bsdf.inputs["Metallic"], "Blue")
    nmap = mat.node_tree.nodes.new("ShaderNodeNormalMap")
    nimg = mat.node_tree.nodes.new("ShaderNodeTexImage")
    nimg.image = normal_img
    mat.node_tree.links.new(nimg.outputs["Color"], nmap.inputs["Color"])
    mat.node_tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    blob.data.materials.append(mat)
    bpy.ops.object.select_all(action="SELECT")
    glb = model_dir / "model.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), use_selection=True, export_apply=True, export_yup=True)

    meta = {"asset": "meshy_rock", "class": "B",
            "image": {"ai_model": "nano-banana-2-lite", "prompt": "test", "task_id": "t1",
                      "file": "meshy_rock/image/chosen.png", "sha256": "0" * 64},
            "model": {"resource": "image-to-3d", "model_type": "smart-topology", "task_id": "t2",
                      "file": "meshy_rock/model/B-t1/model.glb",
                      "sha256": hashlib.sha256(glb.read_bytes()).hexdigest()},
            "credits": 15}
    (asset / "asset.json").write_text(json.dumps(
        {"id": "meshy_rock", "category": "props", "texture_size": 64,
         "lod_triangles": [400, 100, 25], "meshy_class": "B", "material_class": "rock_chalk",
         "texture_format": "ktx2"}))
    (asset / "meshy.json").write_text(json.dumps(meta))
    os.environ["VR_MESHY_DIR"] = str(lib)

    # Wrong hash aborts before touching the library file.
    bad = json.loads(json.dumps(meta))
    bad["model"]["sha256"] = "f" * 64
    (asset / "meshy.json").write_text(json.dumps(bad))
    try:
        vrmeshy.load_raw(str(asset))
        raise AssertionError("tampered sha256 was accepted")
    except SystemExit as exc:
        assert "sha256" in str(exc), exc
    (asset / "meshy.json").write_text(json.dumps(meta))

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    objs = vrmeshy.load_raw(str(asset))
    assert objs and all(o.type == "MESH" for o in objs)
    loose = vrmeshy.drop_loose(objs, min_fraction=0.01)
    assert loose > 0, "the detached chip should be dropped"
    vrmeshy.fix_normals(objs)
    vrmeshy.normalize(objs, size_m=(1.5, 1.5, 1.5), yaw_deg=30)
    lo, hi = vrlib.world_bounds(objs)
    assert abs(lo.z) < 1e-4 and max(hi - lo) <= 1.5 + 1e-4, (tuple(lo), tuple(hi))
    assert abs((lo.x + hi.x) / 2) < 1e-3 and abs((lo.y + hi.y) / 2) < 1e-3, (tuple(lo), tuple(hi))
    vrmeshy.burial_skirt(objs, depth=0.2)
    lo, hi = vrlib.world_bounds(objs)
    assert abs(lo.z + 0.2) < 1e-4, lo.z

    # clamp_material replaces the metal link and lifts textured roughness to >= 0.6.
    clamped = vrmeshy.clamp_material(objs, roughness_min=0.6)
    mats = [m for m in objs[0].data.materials if m and m.node_tree]
    b = mats[0].node_tree.nodes["Principled BSDF"]
    assert not b.inputs["Metallic"].is_linked and b.inputs["Metallic"].default_value == 0.0
    assert clamped, "the ORM texture should have been re-baked with a clamp"
    rough_img = next(iter(clamped.values()))
    g = np.array(rough_img.pixels[:]).reshape(-1, 4)[:, 1]
    assert g.min() >= 0.6 - 1e-4, g.min()

    # grade + delight produce new images and never touch the source texture.
    graded = vrmeshy.grade_basecolor(objs, "#E04848", strength=1.0)
    assert graded and all("_graded" in i.name for i in graded.values())
    delit = vrmeshy.delight_basecolor(objs, radius_frac=0.25)
    assert delit and all("_delit" in i.name for i in delit.values())

    vrmeshy.link_source(objs)
    assert objs[0] in vrlib.source_objects()

    sys.argv = ["blender", "--", str(asset), str(asset)]
    result = runpy.run_path(str(ROOT / "tools" / "blender" / "export_asset.py"))
    counts = [vrlib.triangle_count([o]) for o in result["lods"]]
    assert all(0 < count <= target * 2 for count, target in zip(counts, (400, 100, 25))), counts
    assert counts[0] <= 800 and counts[-1] < counts[0], counts

    # Class B keeps the imported UVs and the raw textures — no bake names appear.
    lod0 = result["lod0"]
    mats = [m for m in lod0.data.materials if m and m.node_tree]
    assert len(mats) == 1
    texs = [n.image.name for n in mats[0].node_tree.nodes if n.type == "TEX_IMAGE"]
    assert any(name.startswith("meshy_basecolor") for name in texs), texs
    assert not any(name == "meshy_rock_basecolor" for name in texs), texs
    bc = bpy.data.images[next(name for name in texs if name.startswith("meshy_basecolor"))]
    assert tuple(bc.size) == (64, 64), bc.size
    px = np.array(bc.pixels[:]).reshape(64, 64, 4)
    assert abs(px[:, :4, 0].mean() - px[:, 4:8, 0].mean()) > 0.05, \
        "the checker detail must survive — this is the raw texture"
    occ = [n for n in mats[0].node_tree.nodes if n.type == "GROUP" and n.node_tree and "glTF" in n.node_tree.name]
    assert occ, "class B still needs an occlusion socket for the exporter"
    assert result["emission_strength"] == 0.0

    raw = asset / "meshy_rock.raw.glb"
    assert raw.is_file()
    if not shutil.which("ktx"):
        ktx_bin = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs", "KTX-Software", "bin")
        if os.path.isdir(ktx_bin):
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + ktx_bin
    npx = shutil.which("npx") or "npx"
    web = ROOT / "web"
    tmp, packed = asset / "tex.glb", asset / "packed.glb"
    subprocess.run([npx, "--no-install", "gltf-transform", "etc1s", str(raw), str(tmp),
                    "--slots", "{baseColorTexture,metallicRoughnessTexture,occlusionTexture,emissiveTexture}"],
                   cwd=web, check=True)
    subprocess.run([npx, "--no-install", "gltf-transform", "uastc", str(tmp), str(packed),
                    "--slots", "normalTexture"], cwd=web, check=True)
    blob = packed.read_bytes()
    doc = json.loads(blob[20:20 + struct.unpack("<I", blob[12:16])[0]])
    assert all(i["mimeType"] == "image/ktx2" for i in doc["images"]), doc["images"]
    assert "KHR_texture_basisu" in doc["extensionsUsed"], doc["extensionsUsed"]

print("PASS: class B exports prepared Meshy UVs+textures (no bake), clamps materials, "
      "aborts on sha mismatch and encodes KTX2")
