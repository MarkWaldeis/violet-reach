"""Spatial foliage proxies sharing the baked leaf atlas; wood has its own budget."""
import bmesh
import bpy
import numpy as np
from foliage_atlas import FoliageAtlas


CANOPY_ATTRIBUTE = "vr_canopy"


def socket_image(socket, depth=0):
    if socket is None or depth > 8:
        return None
    for link in socket.links:
        node = link.from_node
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
        for input_socket in node.inputs:
            image = socket_image(input_socket, depth + 1)
            if image:
                return image
    return None


def foliage_material(material):
    if not material:
        return False
    if material.get("vrmat_name") == "foliage_leaf":
        return True
    bsdf = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
    return bool(bsdf and bsdf.inputs["Alpha"].is_linked and socket_image(bsdf.inputs["Base Color"]))


def foliage_indices(materials):
    return {i for i, material in enumerate(materials) if foliage_material(material)}


def canopy_textures(materials):
    albedo = {}
    occlusion = {}
    for index in foliage_indices(materials):
        material = materials[index]
        bsdf = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
        image = socket_image(bsdf.inputs["Base Color"]) if bsdf else None
        if image:
            albedo[image.name] = image
        for node in material.node_tree.nodes if material.node_tree else []:
            if node.type == "GROUP" and node.node_tree and "glTF" in node.node_tree.name:
                image = socket_image(node.inputs.get("Occlusion"))
                if image:
                    occlusion[image.name] = image
    pick = lambda images: next(iter(images.values())) if len(images) == 1 else None
    return pick(albedo), pick(occlusion)


def canopy_alpha_cutoff(materials):
    """Return the shared alpha-cutout threshold of foliage materials, if unambiguous."""
    values = set()
    for index in foliage_indices(materials):
        material = materials[index]
        bsdf = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
        alpha = bsdf.inputs["Alpha"] if bsdf else None
        for link in alpha.links if alpha and alpha.is_linked else []:
            node = link.from_node
            if node.type == "MATH" and node.operation == "GREATER_THAN":
                values.add(round(float(node.inputs[1].default_value), 6))
    return next(iter(values)) if len(values) == 1 else None


def mark_canopy(obj, materials):
    leaves = foliage_indices(materials)
    if not leaves:
        return False
    attribute = obj.data.attributes.new(CANOPY_ATTRIBUTE, "INT", "FACE")
    height = max(v.co.z for v in obj.data.vertices)
    for face, value in zip(obj.data.polygons, attribute.data):
        value.value = int(face.material_index in leaves and face.center.z > height * .2)
    return any(value.value for value in attribute.data)


def restore_vertical_extent(mesh, low, high):
    """Map a simplified trunk back to its pre-simplification vertical extent.

    Edge collapse and clustering both erode thin lower trunks first: a mesh can fit the
    triangle budget while its lowest remaining vertex floats well above the ground.  The
    vertical span is a silhouette/ground-contact constraint, so restore exactly that span
    after simplification.  This intentionally does not invent detail; it only stops the
    coarse proxy from losing the trunk endpoint that was present in its input.
    """
    if not mesh.vertices or high - low <= 1e-9:
        return
    current_low = min(vertex.co.z for vertex in mesh.vertices)
    current_high = max(vertex.co.z for vertex in mesh.vertices)
    current_span = current_high - current_low
    if current_span <= 1e-9:
        return
    scale = (high - low) / current_span
    for vertex in mesh.vertices:
        vertex.co.z = low + (vertex.co.z - current_low) * scale
    mesh.update()


def _orthonormal_basis(rows):
    """Complete PCA/SVD rows to a deterministic orthonormal 3D basis."""
    basis = []

    def add(vector):
        vector = np.array(vector, dtype=float)
        for existing in basis:
            vector -= np.dot(vector, existing) * existing
        length = np.linalg.norm(vector)
        if length <= 1e-9:
            return False
        basis.append(vector / length)
        return len(basis) == 3

    for row in rows:
        if add(row):
            break
    for axis in np.eye(3):
        if len(basis) == 3:
            break
        add(axis)
    basis = np.array(basis)
    for index in range(3):
        pivot = np.argmax(np.abs(basis[index]))
        if basis[index, pivot] < 0:
            basis[index] *= -1
    if np.linalg.det(basis) < 0:
        basis[2] *= -1
    return basis


def _principal_basis(points):
    points = np.asarray(points, dtype=float)
    centred = points - points.mean(axis=0)
    try:
        _, _, rows = np.linalg.svd(centred, full_matrices=False)
    except np.linalg.LinAlgError:
        rows = []
    return _orthonormal_basis(rows)


def _plane_axes(points, cards):
    """Return projection axes for one, two, or three impostor cards.

    The two-card mode uses the PCA main plane and a second plane perpendicular to it.
    Both planes contain the longest PCA axis, so the support card follows the elongated
    direction of the patch instead of becoming an unrelated axis-aligned cross.
    """
    if cards in (1, 2):
        basis = _principal_basis(points)
        if cards == 1:
            return [basis[[0, 1]]]
        return [basis[[0, 1]], basis[[0, 2]]]
    return [np.eye(3)[[0, 1]], np.eye(3)[[0, 2]], np.eye(3)[[1, 2]]]


def _pad_degenerate_span(low, high, points):
    """Keep mathematically valid card quads when a projection axis has zero thickness."""
    extent = float(np.ptp(points, axis=0).max()) if len(points) else 0.0
    minimum = max(extent * 1e-4, 1e-6)
    for axis in range(2):
        if high[axis] - low[axis] < minimum:
            middle = (high[axis] + low[axis]) / 2
            low[axis] = middle - minimum / 2
            high[axis] = middle + minimum / 2
    return low, high


def simplify_canopy(obj, target, simplify_wood, source_image, texture_size, planes=3, occlusion=None,
                    alpha_cutoff=.35, supersample=4):
    if target < 32:
        raise ValueError("Canopy LOD needs at least 32 triangles")
    planes = int(planes)
    if planes not in (1, 2, 3):
        raise ValueError("Canopy LOD planes must be 1, 2 or 3")
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
    cards = planes

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
    wood_low = min((vertex.co.z for vertex in mesh.vertices), default=0.0)
    wood_high = max((vertex.co.z for vertex in mesh.vertices), default=0.0)
    simplify_wood(obj, wood_target)
    mesh = obj.data
    restore_vertical_extent(mesh, wood_low, wood_high)
    wood_triangles = sum(len(face.vertices) - 2 for face in mesh.polygons)
    remaining = target - wood_triangles
    while cards > 1 and remaining // (2 * cards) < 1 and remaining >= 2:
        cards -= 1
    limit = remaining // (2 * cards)
    if limit < 1:
        limit = 1
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
    atlas = FoliageAtlas(obj.name + "_foliage", source_image, texture_size, len(groups) * cards, occlusion,
                         supersample=supersample, alpha_cutoff=alpha_cutoff)
    for group in groups:
        points = np.concatenate([leaf[1] for leaf in group])
        centre = (points.min(axis=0) + points.max(axis=0)) / 2
        axes = _plane_axes(points, cards)
        for basis in axes:
            projected = (points - centre) @ basis.T
            low, high = projected.min(axis=0), projected.max(axis=0)
            low, high = _pad_degenerate_span(low, high, points)
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
