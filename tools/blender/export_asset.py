"""blender -b <asset>.blend --python tools/blender/export_asset.py -- <asset_dir> <staging_dir>

Turns the high-detail SOURCE into the game asset: LOD0 is decimated from the source and gets
base colour, normal, roughness, occlusion and emission baked from it; lower LODs are decimated
from LOD0 and share its textures. Writes <staging_dir>/<id>.raw.glb with nodes <id>_LOD0..n.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import vrlib  # noqa: E402
from canopy_lod import mark_canopy, simplify_canopy  # noqa: E402

asset_dir, export_dir = map(os.path.abspath, vrlib.script_args())
meta = vrlib.load_meta(asset_dir)
asset_id = meta["id"]
tex = int(meta.get("texture_size", 2048))
lod_tris = meta["lod_triangles"]
scene = bpy.context.scene
vrlib.use_cycles_cpu(scene, 24)
scene.cycles.use_denoising = False


def select_only(objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def decimate(obj, target):
    select_only([obj], obj)
    lo, hi = vrlib.world_bounds([obj])
    detail_size = max(hi - lo) * 0.045
    triangles = vrlib.triangle_count([obj])
    if not detail_size or triangles <= target:
        return
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    pending = set(mesh.verts)
    candidates = []
    floor = 0
    while pending:
        todo = [pending.pop()]
        vertices = []
        while todo:
            vertex = todo.pop()
            vertices.append(vertex)
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in pending:
                    pending.remove(other)
                    todo.append(other)
        faces = {f for v in vertices for f in v.link_faces}
        count = sum(len(f.verts)-2 for f in faces)
        floor += min(2, count)
        coords = np.array([v.co[:] for v in vertices])
        if np.linalg.norm(coords.max(axis=0)-coords.min(axis=0)) > detail_size:
            continue
        candidates.append((sum(f.calc_area() for f in faces), vertices, count))
    remove = []
    if floor > target * 1.25:
        for _, vertices, count in sorted(candidates, key=lambda item: item[0]):
            if floor <= target * .75:
                break
            remove.extend(vertices)
            floor -= min(2, count)
    bmesh.ops.delete(mesh, geom=remove, context="VERTS")
    mesh.to_mesh(obj.data)
    obj.data.update()
    mesh.free()
    modifier = obj.modifiers.new("dec", "DECIMATE")
    modifier.ratio = min(1.0, target / max(1, vrlib.triangle_count([obj])))
    modifier.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=modifier.name)


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
mesh = bmesh.new()
mesh.from_mesh(lod0.data)
bmesh.ops.remove_doubles(mesh, verts=list(mesh.verts), dist=1e-6)
mesh.to_mesh(lod0.data)
lod0.data.update()
mesh.free()
decimate(lod0, lod_tris[0])
source_materials = list(lod0.data.materials)
has_canopy = asset_id in {"tree_broadleaf_a", "tree_broadleaf_b"} and mark_canopy(lod0, source_materials)
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
source_indices = [p.material_index for p in lod0.data.polygons]


def bake(name, bake_type, colorspace, project=True, **kw):
    img = bpy.data.images.new(f"{asset_id}_{name}", tex, tex, alpha=False, float_buffer=(name == "emission"))
    img.colorspace_settings.name = colorspace
    if not project:
        lod0.data.materials.clear()
        for mat in source_materials:
            lod0.data.materials.append(mat.copy())
        for poly, index in zip(lod0.data.polygons, source_indices):
            poly.material_index = index
    nodes = []
    for mat in lod0.data.materials:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        mat.node_tree.nodes.active = node
        nodes.append((mat, node))
    select_only(sources + [lod0] if project else [lod0], lod0)
    bpy.ops.object.bake(type=bake_type, use_selected_to_active=project, cage_extrusion=extrusion,
                        max_ray_distance=extrusion * 4, margin=8, **kw)
    for mat, node in nodes:
        mat.node_tree.nodes.remove(node)
    if not project:
        lod0.data.materials.clear()
        lod0.data.materials.append(bake_mat)
        for poly in lod0.data.polygons:
            poly.material_index = 0
    images[name] = img


bake_mat = bpy.data.materials.new(asset_id + "_bake")
bake_mat.use_nodes = True
lod0.data.materials.clear()
lod0.data.materials.append(bake_mat)
for poly in lod0.data.polygons:
    poly.material_index = 0

project_materials = meta.get("category") != "vegetation"
bake("basecolor", "DIFFUSE", "sRGB", project=project_materials, pass_filter={"COLOR"})
bake("normal", "NORMAL", "Non-Color")
bake("roughness", "ROUGHNESS", "Non-Color", project=project_materials)
bake("emission", "EMIT", "sRGB", project=project_materials)
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
    if has_canopy and i > 1:
        target = int(target * .65)
    source = lods[-1] if has_canopy and i > 1 else lod0
    lod = source.copy()
    lod.data = source.data.copy()
    lod.name = f"{asset_id}_LOD{i}"
    scene.collection.objects.link(lod)
    select_only([lod], lod)
    colour = bpy.data.images.get(source.get("canopy_albedo", "")) or images["basecolor"]
    occlusion = bpy.data.images.get(source.get("canopy_occlusion", "")) or images["occlusion"]
    if not has_canopy or not simplify_canopy(lod, target, decimate, colour, tex, planes=1 if i == 1 else 3, occlusion=occlusion):
        decimate(lod, target)
    lods.append(lod)

select_only(lods, lod0)
raw = os.path.join(export_dir, asset_id + ".raw.glb")
bpy.ops.export_scene.gltf(filepath=raw, use_selection=True, export_apply=True, export_yup=True,
                          export_image_format="AUTO", export_tangents=True, export_extras=False)
for name in images:
    os.remove(os.path.join(export_dir, f".{asset_id}_{name}.png"))
print("VR_RESULT", {"lod_triangles": [vrlib.triangle_count([o]) for o in lods], "source_triangles": source_tris,
                    "emission_strength": round(emission_strength, 3), "raw_bytes": os.path.getsize(raw)}, flush=True)
