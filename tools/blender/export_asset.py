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
from canopy_lod import canopy_textures, mark_canopy, simplify_canopy  # noqa: E402

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


def _cluster_geometry(mesh, cell_size):
    """Vertex-cluster mesh triangles in memory; returns geometry plus per-corner UVs."""
    vertices = np.array([v.co[:] for v in mesh.vertices], dtype=float)
    if not len(vertices) or not mesh.polygons:
        return None
    keys = np.floor((vertices - vertices.min(axis=0)) / max(float(cell_size), 1e-9)).astype(np.int64)
    cells = {}
    remap = []
    for index, key in enumerate(keys):
        key = tuple(int(v) for v in key)
        if key not in cells:
            cells[key] = len(cells)
        remap.append(cells[key])
    positions = np.zeros((len(cells), 3), dtype=float)
    counts = np.zeros(len(cells), dtype=float)
    for index, cell in enumerate(remap):
        positions[cell] += vertices[index]
        counts[cell] += 1
    positions /= counts[:, None]

    uv_layers = list(mesh.uv_layers)
    faces = []
    materials = []
    smoothing = []
    face_uvs = {layer.name: [] for layer in uv_layers}
    seen = set()
    for face in mesh.polygons:
        corner_vertices = list(face.vertices)
        corner_loops = list(face.loop_indices)
        for j in range(1, len(corner_vertices) - 1):
            corners = (0, j, j + 1)
            triangle = tuple(remap[corner_vertices[c]] for c in corners)
            if len(set(triangle)) < 3:
                continue
            key = tuple(sorted(triangle)) + (face.material_index,)
            if key in seen:
                continue
            seen.add(key)
            faces.append(triangle)
            materials.append(face.material_index)
            smoothing.append(face.use_smooth)
            for layer in uv_layers:
                face_uvs[layer.name].append([tuple(layer.data[corner_loops[c]].uv) for c in corners])
    if not faces:
        return None
    return positions, faces, materials, smoothing, face_uvs, len(faces)


def _replace_with_clustered_mesh(obj, clustered):
    positions, faces, materials, smoothing, face_uvs, _ = clustered
    old = obj.data
    result = bpy.data.meshes.new(old.name + "_clustered")
    result.from_pydata([tuple(v) for v in positions], [], faces)
    result.update()
    for material in old.materials:
        result.materials.append(material)
    for index, face in enumerate(result.polygons):
        face.material_index = materials[index]
        face.use_smooth = smoothing[index]
    for layer in old.uv_layers:
        uv = result.uv_layers.new(name=layer.name)
        for face, coordinates in zip(result.polygons, face_uvs[layer.name]):
            for loop, coordinate in zip(face.loop_indices, coordinates):
                uv.data[loop].uv = coordinate
    obj.data = result
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _vertex_cluster_decimate(obj, target):
    """Last-resort triangle-budget simplification for non-manifold wood proxies.

    Blender's collapse decimator can stop at a local minimum on the deeply chained,
    non-manifold bark meshes.  Vertex clustering is less precise, but it is topology-
    independent and is only used after collapse stops making progress.  A binary search
    picks the finest grid cell that still fits the triangle budget.
    """
    mesh = obj.data
    vertices = np.array([v.co[:] for v in mesh.vertices], dtype=float)
    if not len(vertices):
        return False
    scale = float(np.ptp(vertices, axis=0).max())
    if scale <= 0:
        return False
    low, high = 0.0, scale
    best = None
    for _ in range(30):
        middle = (low + high) / 2
        clustered = _cluster_geometry(mesh, middle)
        count = clustered[-1] if clustered else 0
        if 0 < count <= target:
            best = clustered
            high = middle
        elif count > target:
            low = middle
        else:
            high = middle
    if best is None:
        return False
    _replace_with_clustered_mesh(obj, best)
    return vrlib.triangle_count([obj]) <= target


def decimate(obj, target, preserve_uvs=False):
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
    # Decimate's ratio is counted in mesh faces, but the asset budgets are counted in
    # triangles.  Large meshy/ngon faces otherwise survive almost unchanged and can put
    # chained low LODs far over budget; triangulation makes both units agree without
    # changing the source shape.
    bmesh.ops.triangulate(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    obj.data.update()
    mesh.free()
    for _ in range(3):
        triangles = vrlib.triangle_count([obj])
        if triangles <= target:
            break
        modifier = obj.modifiers.new("dec", "DECIMATE")
        modifier.ratio = min(1.0, target / max(1, triangles))
        modifier.use_collapse_triangulate = True
        if preserve_uvs:
            modifier.delimit = {"UV"}
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    if vrlib.triangle_count([obj]) > target:
        _vertex_cluster_decimate(obj, target)


def _sanitize_meshy_uvs(obj):
    """Collapse underground burial-skirt UVs and seam-bridging pinhole fill UVs so AO bake stays clean."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None or not bm.verts:
        bm.free()
        return
    bm.normal_update()
    z_min = min(v.co.z for v in bm.verts)
    cap_faces = {f for f in bm.faces if all(v.co.z <= z_min + 0.02 for v in f.verts)}
    skirt_walls = {
        f for f in bm.faces
        if f not in cap_faces and any(v.co.z <= z_min + 0.02 for v in f.verts) and abs(f.normal.z) < 0.35
    }
    body_faces = set(bm.faces) - cap_faces - skirt_walls

    for f in cap_faces:
        for lp in f.loops:
            lp[uv_layer].uv = (0.001, 0.001)

    for f in skirt_walls:
        top_uv = {}
        inner_uv = {}
        top_edges = [e for e in f.edges if e.verts[0].co.z > z_min + 0.02 and e.verts[1].co.z > z_min + 0.02]
        for e in top_edges:
            adj = next((af for af in e.link_faces if af in body_faces), None)
            if adj is not None:
                adj_center = sum((bl[uv_layer].uv for bl in adj.loops), adj.loops[0][uv_layer].uv * 0.0) / len(adj.loops)
                for bl in adj.loops:
                    if bl.vert in e.verts:
                        uv0 = bl[uv_layer].uv.copy()
                        top_uv[bl.vert] = uv0
                        inner_uv[bl.vert] = uv0.lerp(adj_center, 0.45)
        for lp in f.loops:
            if lp.vert.co.z > z_min + 0.02 and lp.vert not in top_uv:
                fallback_lp = next((bl for bl in lp.vert.link_loops if bl.face in body_faces), None)
                if fallback_lp is not None:
                    adj = fallback_lp.face
                    adj_center = sum((bl[uv_layer].uv for bl in adj.loops), fallback_lp[uv_layer].uv * 0.0) / len(adj.loops)
                    uv0 = fallback_lp[uv_layer].uv.copy()
                    top_uv[lp.vert] = uv0
                    inner_uv[lp.vert] = uv0.lerp(adj_center, 0.45)
                else:
                    top_uv[lp.vert] = lp[uv_layer].uv.copy()
                    inner_uv[lp.vert] = top_uv[lp.vert]
        for lp in f.loops:
            if lp.vert.co.z > z_min + 0.02:
                if lp.vert in top_uv:
                    lp[uv_layer].uv = top_uv[lp.vert]
            else:
                partner = next(
                    (nl.vert for nl in (lp.link_loop_next, lp.link_loop_prev) if nl.vert.co.z > z_min + 0.02),
                    None,
                )
                if partner is not None and partner in inner_uv:
                    lp[uv_layer].uv = inner_uv[partner]
                elif inner_uv:
                    lp[uv_layer].uv = next(iter(inner_uv.values()))
                else:
                    lp[uv_layer].uv = (0.001, 0.001)

    for f in body_faces:
        n = len(f.loops)
        if n < 3:
            continue
        uvs = [lp[uv_layer].uv for lp in f.loops]
        uv_area = 0.5 * abs(sum(uvs[i].x * uvs[(i + 1) % n].y - uvs[(i + 1) % n].x * uvs[i].y for i in range(n)))
        max_edge_uv = max((uvs[(i + 1) % n] - uvs[i]).length for i in range(n))
        face_area = f.calc_area()
        if (uv_area > 0.0015 and face_area < 0.01) or (max_edge_uv > 0.25 and face_area < 0.005):
            anchor = uvs[0].copy()
            for lp in f.loops:
                lp[uv_layer].uv = anchor

    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


def meshy_finish(obj, tex):
    """Class B export: keep the Meshy UVs and textures, no re-bake.

    Scales every texture down to the texture budget and makes sure an occlusion
    map exists — either the imported one or a cheap AO bake onto the Meshy UVs.
    Returns the emission strength for the export receipt.
    """
    _sanitize_meshy_uvs(obj)
    for mat in obj.data.materials:
        if not mat or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            img = node.image if node.type == "TEX_IMAGE" else None
            if img and max(img.size) > tex:
                w, h = img.size
                factor = tex / max(w, h)
                img.scale(max(1, round(w * factor)), max(1, round(h * factor)))
    has_occlusion = any(
        node.type == "GROUP" and node.node_tree and "glTF" in node.node_tree.name
        for mat in obj.data.materials if mat and mat.node_tree for node in mat.node_tree.nodes)
    if not has_occlusion:
        img = bpy.data.images.new(f"{asset_id}_occlusion", tex, tex, alpha=False)
        img.colorspace_settings.name = "Non-Color"
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        nodes = []
        for mat in obj.data.materials:
            if not mat or not mat.node_tree:
                continue
            node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = img
            mat.node_tree.nodes.active = node
            nodes.append((mat, node))
        hidden = [o for o in scene.objects if o is not obj and o.type == "MESH" and not o.hide_render]
        for o in hidden:
            o.hide_render = True
        try:
            scene.cycles.samples = 64
            select_only([obj], obj)
            bpy.ops.object.bake(type="AO", use_selected_to_active=False, margin=8)
        finally:
            for o in hidden:
                o.hide_render = False
        for mat, node in nodes:
            mat.node_tree.nodes.remove(node)
            tex_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex_node.image = img
            occ = mat.node_tree.nodes.new("ShaderNodeGroup")
            occ.node_tree = group
            mat.node_tree.links.new(tex_node.outputs["Color"], occ.inputs["Occlusion"])
    strength = 0.0
    for mat in obj.data.materials:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat and mat.node_tree else None
        if bsdf is not None and bsdf.inputs["Emission Color"].is_linked:
            strength = max(strength, float(bsdf.inputs["Emission Strength"].default_value))
    return strength


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
if lod0.data.validate(verbose=False, clean_customdata=False):
    lod0.data.update()
meshy_b = meta.get("meshy_class") == "B"
decimate(lod0, lod_tris[0], preserve_uvs=meshy_b)
source_materials = list(lod0.data.materials)
if meshy_b:
    emission_strength = meshy_finish(lod0, tex)
    images = {}
    has_canopy = mark_canopy(lod0, source_materials)
    if has_canopy:
        canopy_albedo, canopy_occlusion = canopy_textures(source_materials)
        if canopy_albedo:
            lod0["canopy_albedo"] = canopy_albedo.name
            if canopy_occlusion:
                lod0["canopy_occlusion"] = canopy_occlusion.name
        else:
            has_canopy = False
else:
    has_canopy = mark_canopy(lod0, source_materials)
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
    source = lods[-1] if has_canopy and i > 1 else lod0
    lod = source.copy()
    lod.data = source.data.copy()
    lod.name = f"{asset_id}_LOD{i}"
    scene.collection.objects.link(lod)
    select_only([lod], lod)
    colour = occlusion = None
    if has_canopy:
        colour = bpy.data.images.get(source.get("canopy_albedo", "")) or images.get("basecolor")
        occlusion = bpy.data.images.get(source.get("canopy_occlusion", "")) or images.get("occlusion")
    if not has_canopy or colour is None or not simplify_canopy(lod, target, decimate, colour, tex, planes=1 if i == 1 else 3, occlusion=occlusion):
        decimate(lod, target, preserve_uvs=meshy_b)
    lods.append(lod)

for lod in lods:
    if lod.data.validate(verbose=False):
        lod.data.update()
select_only(lods, lod0)
raw = os.path.join(export_dir, asset_id + ".raw.glb")
bpy.ops.export_scene.gltf(filepath=raw, use_selection=True, export_apply=True, export_yup=True,
                          export_image_format="AUTO", export_tangents=True, export_extras=False)
for name in images:
    os.remove(os.path.join(export_dir, f".{asset_id}_{name}.png"))
print("VR_RESULT", {"lod_triangles": [vrlib.triangle_count([o]) for o in lods], "source_triangles": source_tris,
                    "emission_strength": round(emission_strength, 3), "raw_bytes": os.path.getsize(raw)}, flush=True)
