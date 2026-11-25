"""blender -b --factory-startup --python tools/blender/test_canopy_lod.py"""
from pathlib import Path
import json
import sys
import tempfile

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from canopy_lod import CANOPY_ATTRIBUTE, mark_canopy, simplify_canopy


def projection(obj, axes, bounds):
    mask = np.zeros((96, 96), dtype=bool)
    attribute = obj.data.attributes[CANOPY_ATTRIBUTE]
    textures = {}
    for i, material in enumerate(obj.data.materials):
        image = next((node.image for node in material.node_tree.nodes if node.type == "TEX_IMAGE"), None) if material.node_tree else None
        textures[i] = np.array(image.pixels[:]).reshape(image.size[1], image.size[0], 4) if image else None
    for face in obj.data.polygons:
        if not attribute.data[face.index].value:
            continue
        points = np.array([obj.data.vertices[i].co[:] for i in face.vertices])[:, axes]
        pixels = textures[face.material_index]
        points = (points - bounds[0]) / (bounds[1] - bounds[0]) * 93 + 1
        for j in range(1, len(points) - 1):
            a, b, c = points[[0, j, j + 1]]
            low, high = np.maximum(0, np.floor(points.min(axis=0)).astype(int)), np.minimum(95, np.ceil(points.max(axis=0)).astype(int))
            x, y = np.meshgrid(np.arange(low[0], high[0] + 1) + .5, np.arange(low[1], high[1] + 1) + .5)
            ab, ac = b - a, c - a
            determinant = ab[0] * ac[1] - ab[1] * ac[0]
            if abs(determinant) < 1e-9:
                continue
            u = ((x - a[0]) * ac[1] - (y - a[1]) * ac[0]) / determinant
            v = (ab[0] * (y - a[1]) - ab[1] * (x - a[0])) / determinant
            inside = (u >= 0) & (v >= 0) & (u + v <= 1)
            if pixels is not None:
                texture = np.array([obj.data.uv_layers.active.data[face.loop_indices[k]].uv[:] for k in [0, j, j + 1]])
                coordinates = texture[0] + u[..., None] * (texture[1] - texture[0]) + v[..., None] * (texture[2] - texture[0])
                tx = np.clip((coordinates[..., 0] * pixels.shape[1]).astype(int), 0, pixels.shape[1] - 1)
                ty = np.clip((coordinates[..., 1] * pixels.shape[0]).astype(int), 0, pixels.shape[0] - 1)
                inside &= pixels[ty, tx, 3] > .35
            mask[low[1]:high[1] + 1, low[0]:high[0] + 1] |= inside
    return mask


vertices, faces = [], []
for z in range(3):
    for x in range(10):
        for y in range(10):
            start = len(vertices)
            for u, v in [(0, 0), (.19, 0), (.19, .19), (0, .19)]:
                vertices.append((x * .2 + u, y * .2 + v, 2 + z * .3 + u * .5 + v * .2))
            faces.append(tuple(range(start, start + 4)))
leaf_vertices, leaf_faces = len(vertices), len(faces)
start = len(vertices)
vertices.extend((x, y, z) for z in (0, 2.6) for x, y in [(-.08, -.08), (.08, -.08), (.08, .08), (-.08, .08)])
faces.extend(tuple(start + i for i in face) for face in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
mesh = bpy.data.meshes.new("Canopy")
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new("tree_canopy_LOD0", mesh)
bpy.context.scene.collection.objects.link(obj)
leaf = bpy.data.materials.new("Leaf")
leaf["vrmat_name"] = "foliage_leaf"
mesh.materials.append(leaf)
wood = bpy.data.materials.new("Wood")
wood["vrmat_name"] = "tree_bark"
mesh.materials.append(wood)
for face in list(mesh.polygons)[leaf_faces:]:
    face.material_index = 1
assert mark_canopy(obj, [leaf])
uv = mesh.uv_layers.new(name="UVMap")
for face in mesh.polygons:
    for index, coordinate in zip(face.loop_indices, [(.1, .1), (.3, .1), (.3, .3), (.1, .3)]):
        uv.data[index].uv = coordinate
original = obj.copy()
original.data = mesh.copy()
positions = np.array(vertices[:leaf_vertices])
source_image = bpy.data.images.new("Leaf albedo", 32, 32, alpha=True)
source_image.pixels.foreach_set(np.tile(np.array([.12, .4, .09, 1], dtype=np.float32), 32 * 32))
source_ao = bpy.data.images.new("Leaf AO", 32, 32, alpha=False)
source_ao.pixels.foreach_set(np.full(32 * 32 * 4, .5, dtype=np.float32))
for target, planes in [(800, 1), (480, 1), (160, 3)]:
    lod = original.copy()
    lod.data = original.data.copy()
    bpy.context.scene.collection.objects.link(lod)
    assert simplify_canopy(lod, target, lambda *_: None, source_image, 512, planes, source_ao)
    count = sum(len(face.vertices) - 2 for face in lod.data.polygons)
    assert 0 < count <= target, (count, target)
    for axes in [(0, 1), (0, 2), (1, 2)]:
        bounds = positions[:, axes].min(axis=0), positions[:, axes].max(axis=0)
        before, after = projection(original, axes, bounds), projection(lod, axes, bounds)
        retention = (before & after).sum() / max(1, before.sum())
        assert retention > .85, (target, axes, retention)
    assert all(0 <= value <= 1 for loop in lod.data.uv_layers.active.data for value in loop.uv)
    image = bpy.data.images[lod.data.materials[-1].name]
    pixels = np.array(image.pixels[:]).reshape(-1, 4)
    assert (pixels[:, 3] == 0).any() and (pixels[:, 3] == 1).any()
    assert np.all(pixels[pixels[:, 3] > .5, 1] > .3)
    woody = np.array([lod.data.vertices[index].co[:] for face in lod.data.polygons
                      if not lod.data.attributes[CANOPY_ATTRIBUTE].data[face.index].value for index in face.vertices])
    assert woody[:, 2].min() == 0 and woody[:, 2].max() > 2.59
    if target == 800:
        near_lod = lod
    print(f"PASS: canopy {target} budget uses {count} triangles; three-axis coverage and atlas UVs retained")
with tempfile.TemporaryDirectory() as folder:
    bpy.ops.object.select_all(action="DESELECT")
    lod.select_set(True)
    bpy.context.view_layer.objects.active = lod
    path = Path(folder) / "canopy.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), use_selection=True)
    data = path.read_bytes()
    document = json.loads(data[20:20 + int.from_bytes(data[12:16], "little")])
    material = next(material for material in document["materials"] if material["name"] == lod.data.materials[-1].name)
    assert material["alphaMode"] == "MASK" and abs(material["alphaCutoff"] - .35) < 1e-6, material
    assert material["doubleSided"] and "normalTexture" not in material
print("PASS: foliage exports as double-sided alpha MASK with cutoff 0.35, not transparent BLEND")
chained = near_lod.copy()
chained.data = near_lod.data.copy()
bpy.context.scene.collection.objects.link(chained)


def squash_wood_for_regression_test(obj, _target):
    for vertex in obj.data.vertices:
        vertex.co.z = 2 + vertex.co.z * .5
    obj.data.update()


assert simplify_canopy(chained, 160, squash_wood_for_regression_test, bpy.data.images[near_lod["canopy_albedo"]], 512, 3, bpy.data.images[near_lod["canopy_occlusion"]])
woody = np.array([chained.data.vertices[index].co[:] for face in chained.data.polygons
                  if not chained.data.attributes[CANOPY_ATTRIBUTE].data[face.index].value for index in face.vertices])
assert abs(woody[:, 2].min()) < 1e-6 and woody[:, 2].max() > 2.59
for axes in [(0, 1), (0, 2), (1, 2)]:
    bounds = positions[:, axes].min(axis=0), positions[:, axes].max(axis=0)
    before, after = projection(near_lod, axes, bounds), projection(chained, axes, bounds)
    assert (before & after).sum() / before.sum() > .85
print("PASS: chained LOD1 → LOD2 preserves masked coverage, AO atlas and trunk height")
empty = bpy.data.objects.new("Empty", bpy.data.meshes.new("Empty"))
assert not simplify_canopy(empty, 32, lambda *_: None, source_image, 512)
try:
    simplify_canopy(original, 0, lambda *_: None, source_image, 512)
    raise AssertionError("Invalid canopy budget accepted")
except ValueError:
    pass
no_uv = original.copy()
no_uv.data = original.data.copy()
no_uv.data.uv_layers.remove(no_uv.data.uv_layers.active)
try:
    simplify_canopy(no_uv, 160, lambda *_: None, source_image, 512)
    raise AssertionError("Missing UV atlas accepted")
except ValueError:
    pass
print("PASS: empty canopy is unchanged; invalid budget and missing atlas are rejected")
