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
