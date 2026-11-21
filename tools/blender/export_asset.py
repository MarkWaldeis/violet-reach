"""blender -b <asset>.blend --python tools/blender/export_asset.py -- <asset_dir>

Turns the high-detail SOURCE into the game asset: LOD0 is decimated from the source and gets
base colour, normal, roughness, occlusion and emission baked from it; lower LODs are decimated
from LOD0 and share its textures. Writes export/<id>.raw.glb with nodes <id>_LOD0..n.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import vrlib  # noqa: E402

asset_dir = os.path.abspath(vrlib.script_args()[0])
meta = vrlib.load_meta(asset_dir)
asset_id = meta["id"]
tex = int(meta.get("texture_size", 2048))
lod_tris = meta["lod_triangles"]
export_dir = os.path.join(asset_dir, "export")
os.makedirs(export_dir, exist_ok=True)
scene = bpy.context.scene
vrlib.use_cycles_cpu(scene, 24)
scene.cycles.use_denoising = False


def select_only(objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


sources = vrlib.source_objects()
source_tris = vrlib.triangle_count(sources)

# LOD0: one joined, decimated copy of the source.
copies = []
for o in sources:
    c = o.copy()
    c.data = o.data.copy()
    scene.collection.objects.link(c)
    copies.append(c)
select_only(copies, copies[0])
bpy.ops.object.convert(target="MESH")
bpy.ops.object.join()
lod0 = bpy.context.object
lod0.name = asset_id + "_LOD0"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
dec = lod0.modifiers.new("dec", "DECIMATE")
dec.ratio = min(1.0, lod_tris[0] / max(1, source_tris))
bpy.ops.object.modifier_apply(modifier=dec.name)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
bpy.ops.object.mode_set(mode="OBJECT")
for poly in lod0.data.polygons:
    poly.use_smooth = True
lod0.data.set_sharp_from_angle(angle=math.radians(38))
# The source is high-poly but also faceted; baking object-space detail needs a small cage.
lo, hi = vrlib.world_bounds([lod0])
extrusion = max(hi - lo) * 0.012

images = {}


def bake(name, bake_type, colorspace, **kw):
    img = bpy.data.images.new(f"{asset_id}_{name}", tex, tex, alpha=False, float_buffer=(name == "emission"))
    img.colorspace_settings.name = colorspace
    mat = lod0.data.materials[0]
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    mat.node_tree.nodes.active = node
    select_only(sources + [lod0], lod0)
    bpy.ops.object.bake(type=bake_type, use_selected_to_active=True, cage_extrusion=extrusion,
                        max_ray_distance=extrusion * 4, margin=8, **kw)
    mat.node_tree.nodes.remove(node)
    images[name] = img


bake_mat = bpy.data.materials.new(asset_id + "_bake")
bake_mat.use_nodes = True
lod0.data.materials.clear()
lod0.data.materials.append(bake_mat)

bake("basecolor", "DIFFUSE", "sRGB", pass_filter={"COLOR"})
bake("normal", "NORMAL", "Non-Color")
bake("roughness", "ROUGHNESS", "Non-Color")
bake("emission", "EMIT", "sRGB")
scene.cycles.samples = 64
bake("occlusion", "AO", "Non-Color")

# Emission is baked in scene-linear and can exceed 1; store it normalised and keep the gain as strength.
px = np.empty(tex * tex * 4, dtype=np.float32)
images["emission"].pixels.foreach_get(px)
peak = float(np.percentile(px.reshape(-1, 4)[:, :3].max(axis=1), 99.9))
emission_strength = max(peak, 1e-4)
px = px.reshape(-1, 4)
px[:, :3] = np.clip(px[:, :3] / emission_strength, 0, 1)
images["emission"].pixels.foreach_set(px.ravel())

for name, img in images.items():
    img.filepath_raw = os.path.join(export_dir, f".{asset_id}_{name}.png")
    img.file_format = "PNG"
    img.save()

# Game material: plain image textures that the glTF exporter understands.
mat = bpy.data.materials.new(asset_id)
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]


def tex_node(name):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = images[name]
    return n


nt.links.new(tex_node("basecolor").outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(tex_node("roughness").outputs["Color"], bsdf.inputs["Roughness"])
normal_map = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(tex_node("normal").outputs["Color"], normal_map.inputs["Color"])
nt.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
nt.links.new(tex_node("emission").outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = emission_strength
bsdf.inputs["Metallic"].default_value = 0.0
# The exporter reads ambient occlusion from a group node with this exact name.
group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
occ = nt.nodes.new("ShaderNodeGroup")
occ.node_tree = group
nt.links.new(tex_node("occlusion").outputs["Color"], occ.inputs["Occlusion"])
lod0.data.materials.clear()
lod0.data.materials.append(mat)

lods = [lod0]
for i, target in enumerate(lod_tris[1:], start=1):
    lod = lod0.copy()
    lod.data = lod0.data.copy()
    lod.name = f"{asset_id}_LOD{i}"
    scene.collection.objects.link(lod)
    select_only([lod], lod)
    d = lod.modifiers.new("dec", "DECIMATE")
    d.ratio = min(1.0, target / lod_tris[0])
    bpy.ops.object.modifier_apply(modifier=d.name)
    lods.append(lod)

select_only(lods, lod0)
raw = os.path.join(export_dir, asset_id + ".raw.glb")
bpy.ops.export_scene.gltf(filepath=raw, use_selection=True, export_apply=True, export_yup=True,
                          export_image_format="AUTO", export_tangents=False, export_extras=False)
for name in images:
    os.remove(os.path.join(export_dir, f".{asset_id}_{name}.png"))
print("VR_RESULT", {"lod_triangles": [vrlib.triangle_count([o]) for o in lods], "source_triangles": source_tris,
                    "emission_strength": round(emission_strength, 3), "raw_bytes": os.path.getsize(raw)}, flush=True)
