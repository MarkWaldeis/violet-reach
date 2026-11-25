"""blender -b --factory-startup --python tools/blender/test_canopy_lod.py"""
from pathlib import Path
import json
import sys
import tempfile

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from canopy_lod import (CANOPY_ATTRIBUTE, _plane_axes, canopy_alpha_cutoff, mark_canopy,
                        restore_vertical_extent, simplify_canopy)
from foliage_atlas import FoliageAtlas


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

# Synthetic rasterizer fixture: a diagonal opaque triangle must produce several partial-
# coverage alpha levels at 4x supersampling instead of the old nearest/binary edge.
coverage_image = bpy.data.images.new("Coverage source", 16, 16, alpha=True)
coverage_image.pixels.foreach_set(np.tile(np.array([.2, .55, .1, 1], dtype=np.float32), 16 * 16))
coverage_atlas = FoliageAtlas("Coverage atlas", coverage_image, 64, 1, supersample=4, alpha_cutoff=.5)
fixture_positions = np.array([[-.35, -.64, 0], [1, -.56, 0], [-.2, .78, 0]], dtype=float)
texture = np.array([(0, 0), (1, 0), (0, 1)], dtype=float)
leaf = (None, None, None, None, [(fixture_positions, texture)])
uvs = coverage_atlas.add([leaf], np.eye(3)[:2], np.zeros(3), np.array([-1, -1]), np.array([1, 1]))
alpha = coverage_atlas.pixels[..., 3]
intermediate = (alpha > .02) & (alpha < .98)
assert intermediate.any() and len(np.unique(alpha[intermediate])) >= 3, np.unique(alpha)
assert (alpha == 1).any() and (alpha == 0).any()
rgb = coverage_atlas.pixels[..., :3]
assert ((alpha == 0) & (rgb.sum(axis=2) > 0)).any(), "coverage edges need colour dilation"
assert not rgb[:, :2].sum(), "tile-edge dilation must not wrap colour to the opposite side"
assert uvs[0] == (2 / 64, 2 / 64) and uvs[2] == (62 / 64, 62 / 64), uvs
packing = FoliageAtlas("Packing fixture", coverage_image, 128, 10)
assert (packing.columns, packing.tile) == (4, 32), (packing.columns, packing.tile)
cutoff_material = coverage_atlas.material()
clip = next(node for node in cutoff_material.node_tree.nodes if node.type == "MATH" and node.operation == "GREATER_THAN")
assert abs(clip.inputs[1].default_value - .5) < 1e-6
assert abs(cutoff_material["vr_alpha_cutoff"] - .5) < 1e-6
cut_source_material = bpy.data.materials.new("Cutoff source material")
cut_source_material.use_nodes = True
cut_source_material["vrmat_name"] = "foliage_leaf"
cut_clip = cut_source_material.node_tree.nodes.new("ShaderNodeMath")
cut_clip.operation = "GREATER_THAN"
cut_clip.inputs[1].default_value = .42
cut_source_material.node_tree.links.new(cut_clip.outputs[0], cut_source_material.node_tree.nodes["Principled BSDF"].inputs["Alpha"])
assert abs(canopy_alpha_cutoff([cut_source_material]) - .42) < 1e-6
blend_image = bpy.data.images.new("Coverage blend source", 8, 8, alpha=True)
blend_pixels = np.zeros((8, 8, 4), dtype=np.float32)
blend_alpha = 128 / 255
blend_pixels[:, :4] = (1, 0, 0, blend_alpha)
blend_pixels[:, 4:] = (0, 1, 0, blend_alpha)
blend_image.pixels.foreach_set(blend_pixels.ravel())
blend_atlas = FoliageAtlas("Coverage blend atlas", blend_image, 64, 1, supersample=4)
base_positions = np.array([[-.5, -.5, 0], [.5, -.5, 0], [-.5, .5, 0]], dtype=float)
back_positions = base_positions.copy()
front_positions = base_positions + np.array([0, 0, .1])
red_uv = np.array([(.05, .05), (.45, .05), (.05, .45)], dtype=float)
green_uv = np.array([(.55, .05), (.95, .05), (.55, .45)], dtype=float)
ordered_leaf = (None, None, None, None, [(back_positions, green_uv), (front_positions, red_uv)])
blend_atlas.add([ordered_leaf], np.eye(3)[:2], np.zeros(3), np.array([-1, -1]), np.array([1, 1]))
centre_texel = blend_atlas.pixels[27, 27]
assert abs(centre_texel[3] - (1 - (1 - blend_alpha) ** 2)) < 1e-5, centre_texel
assert centre_texel[0] > centre_texel[1] * 1.8, centre_texel

# A hard alpha edge in the source texture must also become fractional coverage when the
# supersampled texel boundary cuts through an output pixel (here: 0 → 0.5 → 1 horizontally).
step_image = bpy.data.images.new("Coverage step source", 16, 16, alpha=True)
step_pixels = np.zeros((16, 16, 4), dtype=np.float32)
step_pixels[:, 8:] = (.2, .55, .1, 1)
step_image.pixels.foreach_set(step_pixels.ravel())
step_atlas = FoliageAtlas("Coverage step atlas", step_image, 64, 1, supersample=4)
p00, p10, p11, p01 = [np.array(point, dtype=float) for point in
                      [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]]
uv00, uv10, uv11, uv01 = [np.array(point, dtype=float) for point in
                          [(.013, .013), (.97, .013), (.97, .97), (.013, .97)]]
step_triangles = [(np.array([p00, p10, p11]), np.array([uv00, uv10, uv11])),
                  (np.array([p00, p11, p01]), np.array([uv00, uv11, uv01]))]
step_atlas.add([(None, None, None, None, step_triangles)], np.eye(3)[:2], np.zeros(3), np.array([-1, -1]), np.array([1, 1]))
assert list(step_atlas.pixels[20, 30:35, 3]) == [0, 0, .5, 1, 1], step_atlas.pixels[20, 30:35, 3]
print("PASS: 4x coverage alpha is multi-level, texture-edge-aware, padded and cutoff-configurable")

for target, planes in [(800, 1), (480, 3), (160, 3)]:
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

# Regression for clustered wood simplification: invisible vertices left behind by collapsed
# triangles must not define the trunk span that restore_vertical_extent preserves.
restore_mesh = bpy.data.meshes.new("Restore orphan fixture")
restore_mesh.from_pydata([
    (0, 0, 0), (0, 0, 3), (1, 0, 3),
    (0, 0, 9.4),  # faceless remnant, as produced by the old clustered fallback
], [], [(0, 1, 2)])
restore_mesh.update()
restore_vertical_extent(restore_mesh, 0, 9.4)
restored_visible_z = [restore_mesh.vertices[index].co.z for face in restore_mesh.polygons
                      for index in face.vertices]
assert abs(min(restored_visible_z)) < 1e-5 and abs(max(restored_visible_z) - 9.4) < 1e-5, restored_visible_z
print("PASS: vertical restore measures only face-referenced wood vertices")

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

# Small bent-leaf fixture: with enough budget every leaf remains its own patch, so the
# plane count and triangle order are directly observable instead of hidden by merging.
p2_vertices, p2_faces = [], []
for leaf_index in range(4):
    base_x = leaf_index * .55
    base_z = 2 + leaf_index * .04
    start = len(p2_vertices)
    p2_vertices.extend([
        (base_x, 0, base_z),
        (base_x + .36, 0, base_z + .02),
        (base_x + .36, .30, base_z + .36),
        (base_x, .30, base_z + .10),
    ])
    p2_faces.append(tuple(range(start, start + 4)))
p2_leaf_faces = len(p2_faces)
start = len(p2_vertices)
p2_vertices.extend((x, y, z) for z in (0, 2) for x, y in [(-.08, -.08), (.08, -.08), (.08, .08), (-.08, .08)])
p2_faces.extend(tuple(start + i for i in face) for face in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
p2_mesh = bpy.data.meshes.new("Two plane fixture")
p2_mesh.from_pydata(p2_vertices, [], p2_faces)
p2_mesh.update()
p2_original = bpy.data.objects.new("two_plane_fixture_LOD0", p2_mesh)
bpy.context.scene.collection.objects.link(p2_original)
p2_leaf = bpy.data.materials.new("Two plane leaf")
p2_leaf["vrmat_name"] = "foliage_leaf"
p2_wood = bpy.data.materials.new("Two plane wood")
p2_mesh.materials.append(p2_leaf)
p2_mesh.materials.append(p2_wood)
for face in list(p2_mesh.polygons)[p2_leaf_faces:]:
    face.material_index = 1
assert mark_canopy(p2_original, [p2_leaf, p2_wood])
p2_uv = p2_mesh.uv_layers.new(name="UVMap")
for face in p2_mesh.polygons:
    for index, coordinate in zip(face.loop_indices, [(.1, .1), (.3, .1), (.3, .3), (.1, .3)]):
        p2_uv.data[index].uv = coordinate

plane_objects = {}
plane_counts = {}
for plane_count in (1, 2, 3):
    lod = p2_original.copy()
    lod.data = p2_original.data.copy()
    bpy.context.scene.collection.objects.link(lod)
    assert simplify_canopy(lod, 64, lambda *_: None, source_image, 128, plane_count, source_ao)
    attribute = lod.data.attributes[CANOPY_ATTRIBUTE]
    card_faces = [face.index for face in lod.data.polygons if attribute.data[face.index].value]
    assert len(card_faces) == 4 * plane_count, (plane_count, card_faces)
    plane_objects[plane_count] = lod
    plane_counts[plane_count] = sum(len(face.vertices) - 2 for face in lod.data.polygons)
assert plane_counts[1] == 20 and plane_counts[2] == 28 and plane_counts[3] == 36, plane_counts
attribute = plane_objects[2].data.attributes[CANOPY_ATTRIBUTE]
card_faces = [face.index for face in plane_objects[2].data.polygons if attribute.data[face.index].value]
for first, second in zip(card_faces[::2], card_faces[1::2]):
    normal_a = np.array(plane_objects[2].data.polygons[first].normal[:])
    normal_b = np.array(plane_objects[2].data.polygons[second].normal[:])
    assert np.linalg.norm(normal_a) > .5 and np.linalg.norm(normal_b) > .5
    assert abs(float(np.dot(normal_a, normal_b))) < 1e-4, (normal_a, normal_b)
line_points = np.array([(t, 2 * t, .15 * t) for t in (-1, -.3, 0, .2, .7, 1)], dtype=float)
line_axes = _plane_axes(line_points, 2)
long_axis = np.array([1, 2, .15], dtype=float)
long_axis /= np.linalg.norm(long_axis)
assert abs(float(np.dot(line_axes[0][0], long_axis))) > .999, line_axes
assert np.allclose(line_axes[0][0], line_axes[1][0])
assert abs(float(np.dot(np.cross(*line_axes[0]), np.cross(*line_axes[1])))) < 1e-6
print("PASS: planes=2 emits paired perpendicular PCA/support cards at the expected triangle order")
