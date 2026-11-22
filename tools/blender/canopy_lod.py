"""Spatial foliage proxies sharing the baked leaf atlas; wood has its own budget."""
import bmesh
import bpy
import numpy as np
from foliage_atlas import FoliageAtlas


CANOPY_ATTRIBUTE = "vr_canopy"


def mark_canopy(obj, materials):
    leaves = {i for i, material in enumerate(materials)
              if material and material.get("vrmat_name") == "foliage_leaf"}
    if not leaves:
        return False
    attribute = obj.data.attributes.new(CANOPY_ATTRIBUTE, "INT", "FACE")
    height = max(v.co.z for v in obj.data.vertices)
    for face, value in zip(obj.data.polygons, attribute.data):
        value.value = int(face.material_index in leaves and face.center.z > height * .2)
    return any(value.value for value in attribute.data)


def simplify_canopy(obj, target, simplify_wood, source_image, texture_size, planes=3, occlusion=None):
    if target < 32:
        raise ValueError("Canopy LOD needs at least 32 triangles")
    mesh = obj.data
    attribute = mesh.attributes.get(CANOPY_ATTRIBUTE)
    if attribute is None or not any(value.value for value in attribute.data):
        return False
    if mesh.uv_layers.active is None:
        raise ValueError("Canopy LOD needs a baked UV atlas")
    foliage = [face for face in mesh.polygons if attribute.data[face.index].value]
    parent = {}

    def root(index):
        parent.setdefault(index, index)
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for face in foliage:
        anchor = root(face.vertices[0])
        for index in face.vertices[1:]:
            parent[root(index)] = anchor
    components = {}
    for face in foliage:
        components.setdefault(root(face.vertices[0]), []).append(face)
    leaves = []
    uv = mesh.uv_layers.active.data
    for faces in components.values():
        indices = sorted({index for face in faces for index in face.vertices})
        coordinates = np.array([mesh.vertices[index].co[:] for index in indices])
        representative = max(faces, key=lambda face: face.area)
        texture = np.array([uv[index].uv[:] for index in list(representative.loop_indices)[:3]])
        triangles = []
        for face in faces:
            for i in range(1, len(face.vertices) - 1):
                corners = [0, i, i + 1]
                triangles.append((np.array([mesh.vertices[face.vertices[j]].co[:] for j in corners]),
                                  np.array([uv[face.loop_indices[j]].uv[:] for j in corners])))
        leaves.append((coordinates.mean(axis=0), coordinates, texture,
                       sum(face.area for face in faces), triangles))
    leaves.sort(key=lambda leaf: tuple(leaf[0]))
    centres = np.array([leaf[0] for leaf in leaves])
    origin = centres.min(axis=0)
    wood_target = max(12, int(target * .2))
    cards = 3

    def partition(size):
        if size == 0:
            return [[leaf] for leaf in leaves]
        cells = {}
        for leaf in leaves:
            key = tuple(np.floor((leaf[0] - origin) / size).astype(int))
            cells.setdefault(key, []).append(leaf)
        return list(cells.values())

    bm = bmesh.new()
    bm.from_mesh(mesh)
    layer = bm.faces.layers.int[CANOPY_ATTRIBUTE]
    bmesh.ops.delete(bm, geom=[face for face in bm.faces if face[layer]], context="FACES")
    bmesh.ops.delete(bm, geom=[vertex for vertex in bm.verts if not vertex.link_faces], context="VERTS")
    height = max(vertex.co.z for vertex in bm.verts) if bm.verts else 0
    pending = set(bm.verts)
    remove = []
    while pending:
        todo = [pending.pop()]
        component = []
        while todo:
            vertex = todo.pop()
            component.append(vertex)
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other in pending:
                    pending.remove(other)
                    todo.append(other)
        coordinates = np.array([vertex.co[:] for vertex in component])
        extent = coordinates.max(axis=0) - coordinates.min(axis=0)
        area = sum(face.calc_area() for face in {face for vertex in component for face in vertex.link_faces})
        length = np.linalg.norm(extent)
        woody = coordinates[:, 2].max() > height * .15 and area > length * height * .006
        ground = area > height * height * .01 and extent[2] < height * .05
        if not woody and not ground:
            remove.extend(component)
    bmesh.ops.delete(bm, geom=remove, context="VERTS")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    simplify_wood(obj, wood_target)
    mesh = obj.data
    wood_triangles = sum(len(face.vertices) - 2 for face in mesh.polygons)
    if planes == 1 and len(leaves) * 2 <= target - wood_triangles:
        cards = 1
    limit = (target - wood_triangles) // (2 * cards)
    if limit < 1:
        raise ValueError("Wood leaves no room for canopy coverage")
    groups = partition(0)
    if len(groups) > limit:
        low, high = 0.0, max(float(np.ptp(centres, axis=0).max()) * 2, .001)
        for _ in range(24):
            middle = (low + high) / 2
            if len(partition(middle)) > limit:
                low = middle
            else:
                high = middle
        groups = partition(high)
    vertices = [vertex.co[:] for vertex in mesh.vertices]
    faces = [tuple(face.vertices) for face in mesh.polygons]
    texture = [[mesh.uv_layers.active.data[index].uv[:] for index in face.loop_indices]
               for face in mesh.polygons]
    smooth = [face.use_smooth for face in mesh.polygons]
    wood_faces = len(faces)
    atlas = FoliageAtlas(obj.name + "_foliage", source_image, texture_size, len(groups) * cards, occlusion)
    for group in groups:
        points = np.concatenate([leaf[1] for leaf in group])
        centre = (points.min(axis=0) + points.max(axis=0)) / 2
        if cards == 1:
            _, _, basis = np.linalg.svd(points - centre, full_matrices=False)
            if np.cross(basis[0], basis[1])[2] < 0:
                basis[1] *= -1
            axes = [basis[:2]]
        else:
            axes = [np.eye(3)[[0, 1]], np.eye(3)[[0, 2]], np.eye(3)[[1, 2]]]
        for basis in axes:
            projected = (points - centre) @ basis.T
            low, high = projected.min(axis=0), projected.max(axis=0)
            offset = len(vertices)
            for x, y in [(low[0], low[1]), (high[0], low[1]), (high[0], high[1]), (low[0], high[1])]:
                vertices.append(tuple(centre + x * basis[0] + y * basis[1]))
            faces.append(tuple(range(offset, offset + 4)))
            texture.append(atlas.add(group, basis, centre, low, high))
            smooth.append(False)
    result = bpy.data.meshes.new(mesh.name + "_canopy")
    result.from_pydata(vertices, [], faces)
    result.update()
    for material in mesh.materials:
        result.materials.append(material)
    canopy_material = len(result.materials)
    result.materials.append(atlas.material())
    uv = result.uv_layers.new(name="UVMap")
    attribute = result.attributes.new(CANOPY_ATTRIBUTE, "INT", "FACE")
    for face, coordinates, shading in zip(result.polygons, texture, smooth):
        face.use_smooth = shading
        face.material_index = canopy_material if face.index >= wood_faces else 0
        attribute.data[face.index].value = int(face.index >= wood_faces)
        for index, coordinate in zip(face.loop_indices, coordinates):
            uv.data[index].uv = coordinate
    obj.data = result
    obj["canopy_albedo"] = atlas.image.name
    obj["canopy_occlusion"] = atlas.image.name + "_occlusion" if occlusion else ""
    bpy.data.meshes.remove(mesh)
    print(f"CANOPY_LOD {obj.name}: {len(leaves)} leaf components → {len(groups)} patches, {cards} cards/patch", flush=True)
    return True
