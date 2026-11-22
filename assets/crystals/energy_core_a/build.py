"""Proof-derived violet crystals on weathered, mossy fault limestone."""
import json
import math
import random
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector, noise

import vrlib
import vrmat

SEED = 840173


def crystal_material():
    mat = bpy.data.materials.new("vr_crystal_violet")
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    coords = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(coords.outputs["Generated"], sep.inputs["Vector"])

    body = N.new("ShaderNodeValToRGB")
    e = body.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.030, 0.004, 0.10, 1)
    e[1].position, e[1].color = 1.0, (0.36, 0.10, 0.80, 1)
    mid = e.new(0.55)
    mid.color = (0.13, 0.022, 0.40, 1)
    L.new(sep.outputs["Z"], body.inputs["Fac"])

    # Angular inner fractures: large Voronoi cells shift tone and glow.
    cells = N.new("ShaderNodeTexVoronoi")
    cells.inputs["Scale"].default_value = 5.5
    L.new(coords.outputs["Object"], cells.inputs["Vector"])
    cell_sep = N.new("ShaderNodeSeparateXYZ")
    L.new(cells.outputs["Color"], cell_sep.inputs["Vector"])
    fract = N.new("ShaderNodeMixRGB")
    fract.blend_type = "OVERLAY"
    fract.inputs["Fac"].default_value = 0.14
    L.new(body.outputs["Color"], fract.inputs["Color1"])
    L.new(cells.outputs["Color"], fract.inputs["Color2"])
    tint = N.new("ShaderNodeMixRGB")
    tint.blend_type = "MIX"
    tint.inputs["Fac"].default_value = 0.45
    L.new(fract.outputs["Color"], tint.inputs["Color1"])
    L.new(body.outputs["Color"], tint.inputs["Color2"])
    L.new(tint.outputs["Color"], bsdf.inputs["Base Color"])

    veins = N.new("ShaderNodeTexNoise")
    veins.inputs["Scale"].default_value = 2.4
    veins.inputs["Detail"].default_value = 3
    veins.inputs["Distortion"].default_value = 0.4
    L.new(coords.outputs["Object"], veins.inputs["Vector"])
    vein_mask = N.new("ShaderNodeValToRGB")
    vein_mask.color_ramp.elements[0].position = 0.35
    vein_mask.color_ramp.elements[1].position = 0.75
    L.new(veins.outputs["Fac"], vein_mask.inputs["Fac"])

    # Glow: strongest in the core near the base, fading toward the tip, plus bright veins.
    core = N.new("ShaderNodeMapRange")
    core.inputs["From Min"].default_value = 0.0
    core.inputs["From Max"].default_value = 0.9
    core.inputs["To Min"].default_value = 0.55
    core.inputs["To Max"].default_value = 0.03
    L.new(sep.outputs["Z"], core.inputs["Value"])
    vein_gain = N.new("ShaderNodeMath")
    vein_gain.operation = "MULTIPLY_ADD"
    vein_gain.inputs[1].default_value = 0.14
    L.new(vein_mask.outputs["Color"], vein_gain.inputs[0])
    L.new(core.outputs["Result"], vein_gain.inputs[2])
    cell_gain = N.new("ShaderNodeMath")
    cell_gain.operation = "MULTIPLY_ADD"
    cell_gain.inputs[1].default_value = 0.10
    L.new(cell_sep.outputs["X"], cell_gain.inputs[0])
    L.new(vein_gain.outputs["Value"], cell_gain.inputs[2])
    bsdf.inputs["Emission Color"].default_value = (0.30, 0.05, 1.0, 1)
    L.new(cell_gain.outputs["Value"], bsdf.inputs["Emission Strength"])

    rough = N.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.06
    rough.inputs["To Max"].default_value = 0.24
    L.new(veins.outputs["Fac"], rough.inputs["Value"])
    L.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bsdf.inputs["Coat Weight"].default_value = 0.6
    bsdf.inputs["Coat Roughness"].default_value = 0.04
    bsdf.inputs["IOR"].default_value = 1.6

    # Growth striations running along the crystal axis.
    stria = N.new("ShaderNodeTexWave")
    stria.bands_direction = "Z"
    stria.inputs["Scale"].default_value = 5
    stria.inputs["Distortion"].default_value = 2.2
    stria.inputs["Detail"].default_value = 3
    L.new(coords.outputs["Object"], stria.inputs["Vector"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    bump.inputs["Distance"].default_value = 0.01
    L.new(stria.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_rock(name, rng, radius, squash, subdivisions, mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    # Chisel the sphere with random planes to get hard, faceted rock breaks.
    planes = []
    for _ in range(26):
        n = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 1))).normalized()
        planes.append((n, radius * rng.uniform(0.62, 0.96)))
    offset = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    for v in bm.verts:
        p = v.co.copy()
        for n, d in planes:
            over = p.dot(n) - d
            if over > 0:
                p -= n * over
        direction = v.co.normalized()
        coarse = noise.fractal(p * (1.1 / radius) + offset, 1.0, 2.0, 5)
        ridged = noise.ridged_multi_fractal(p * (3.2 / radius) + offset, 1.0, 2.1, 5, 1.0, 2.0)
        fine = noise.fractal(p * (16.0 / radius) + offset, 1.0, 2.0, 4)
        p += direction * radius * (0.10 * coarse + 0.035 * (ridged - 1.0) + 0.008 * fine)
        v.co = p
    for v in bm.verts:
        v.co.z *= squash
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    return vrlib.link_to_source(obj)


def make_crystal(name, rng, radius, height, mat):
    """Six-sided prism with an irregular double-tapered tip, built bottom-up."""
    sides = 6
    twist = rng.uniform(0, math.tau)
    profile = [rng.uniform(0.82, 1.18) for _ in range(sides)]
    rings = [
        (0.0, 1.00),
        (rng.uniform(0.30, 0.42), rng.uniform(1.04, 1.12)),
        (rng.uniform(0.66, 0.76), rng.uniform(0.92, 1.0)),
        (rng.uniform(0.86, 0.91), rng.uniform(0.50, 0.64)),
    ]
    tip_shift = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0)) * radius
    bm = bmesh.new()
    loops = []
    for i, (t, scale) in enumerate(rings):
        lean = tip_shift * (t ** 2) * 0.6
        loop = []
        for s in range(sides):
            a = twist + math.tau * s / sides
            r = radius * scale * profile[s]
            if i == 3:
                r *= rng.uniform(0.8, 1.2)
            z = height * t + (rng.uniform(-0.02, 0.02) * height if i in (2, 3) else 0)
            loop.append(bm.verts.new(Vector((math.cos(a) * r, math.sin(a) * r, z)) + lean))
        loops.append(loop)
    apex = bm.verts.new(Vector((0, 0, height)) + tip_shift)
    for lower, upper in zip(loops, loops[1:]):
        for s in range(sides):
            bm.faces.new((lower[s], lower[(s + 1) % sides], upper[(s + 1) % sides], upper[s]))
    for s in range(sides):
        bm.faces.new((loops[-1][s], loops[-1][(s + 1) % sides], apex))
    bm.faces.new(list(reversed(loops[0])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("edge_bevel", "BEVEL")
    bevel.width = max(0.004, radius * 0.045)
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(12)
    return vrlib.link_to_source(obj)


def place(obj, rng, angle, distance, tilt, base_z):
    """Lean the crystal outward from the cluster centre by `tilt` radians."""
    outward = Vector((math.cos(angle), math.sin(angle), 0))
    axis = Vector((0, 0, 1)).cross(outward)
    lean = Matrix.Rotation(tilt, 4, axis) if axis.length > 0 else Matrix.Identity(4)
    spin = Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z")
    obj.matrix_world = Matrix.Translation(outward * distance + Vector((0, 0, base_z))) @ lean @ spin


def cut_below_ground(depth=0.06):
    """Remove everything deeper than `depth` under the ground plane; the underside is never seen."""
    for obj in vrlib.source_objects():
        inv = obj.matrix_world.inverted()
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                               plane_co=inv @ Vector((0, 0, -depth)),
                               plane_no=inv.to_3x3() @ Vector((0, 0, 1)), clear_inner=True)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()


def support_material(name, ao_distance, earth=False):
    mat = vrmat.get("forest_soil" if earth else "monument_weathered").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    coords = next(node for node in nodes if node.type == "TEX_COORD").outputs["Object"]

    def grain(scale, detail):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(coords, node.inputs["Vector"])
        return node.outputs["Fac"]

    def tones(source, low, high):
        node = nodes.new("ShaderNodeValToRGB")
        node.color_ramp.elements[0].color = (*low, 1)
        node.color_ramp.elements[1].color = (*high, 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, first, second):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, (float, int)):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, value in zip(node.inputs[1:3], (first, second)):
            if isinstance(value, tuple):
                socket.default_value = (*value, 1)
            else:
                links.new(value, socket)
        return node.outputs["Color"]

    if earth:
        base = bsdf.inputs["Base Color"].links[0].from_socket
        coverage = nodes.new("ShaderNodeAttribute")
        coverage.attribute_name = "moss_coverage"
        mask = coverage.outputs["Fac"]
    else:
        neutral = tuple(0.55 * a + 0.45 * b for a, b in zip(
            palette["stone_weathered"]["linear_rgb"], palette["monument_shadow"]["linear_rgb"]))
        base = tones(grain(0.87, 3), tuple(v * 0.78 for v in neutral),
                     tuple(v * 0.95 for v in neutral))
        geometry = nodes.new("ShaderNodeNewGeometry")
        up = nodes.new("ShaderNodeSeparateXYZ")
        links.new(geometry.outputs["Normal"], up.inputs[0])
        patch = nodes.new("ShaderNodeMapRange")
        patch.clamp = True
        patch.interpolation_type = "SMOOTHSTEP"
        patch.inputs["From Min"].default_value = 0.46
        patch.inputs["From Max"].default_value = 0.68
        links.new(grain(0.7, 5), patch.inputs["Value"])
        coverage = nodes.new("ShaderNodeMath")
        coverage.operation = "MULTIPLY"
        coverage.use_clamp = True
        links.new(up.outputs["Z"], coverage.inputs[0])
        links.new(patch.outputs[0], coverage.inputs[1])
        mask = coverage.outputs[0]
    moss = tones(grain(18, 5), tuple(v * 0.8 for v in palette["grass_green"]["linear_rgb"]),
                 tuple(0.7 * a + 0.3 * b for a, b in zip(
                     palette["grass_green"]["linear_rgb"], palette["grass_dry"]["linear_rgb"])))
    base = mix(mask, base, moss)
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 8
    ao.inputs["Distance"].default_value = ao_distance
    grime = tuple(v * 0.65 for v in palette["soil"]["linear_rgb"])
    links.new(mix(ao.outputs["AO"], grime, base), bsdf.inputs["Base Color"])
    if not earth:
        normal = bsdf.inputs["Normal"].links[0].from_socket
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = 0.035
        bump.inputs["Strength"].default_value = 0.35
        links.new(grain(10, 3), bump.inputs["Height"])
        links.new(normal, bump.inputs["Normal"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.18
    mat["asset_tweaks"] = "copied library pores; narrow palette limestone tones, irregular moss coverage, recessed AO soil; no painted fracture lines"
    return mat


def fracture(obj, point, normal):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    cut = bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
        plane_co=point, plane_no=Vector(normal).normalized(), clear_outer=True)
    edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
    filled = bmesh.ops.holes_fill(bm, edges=edges)
    for face in filled["faces"]:
        face.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def chip_tip(obj, height, fraction):
    fracture(obj, (0, 0, height * fraction), (0.85, -0.55, 1))
    fracture(obj, (0, 0, height * (fraction + 0.025)), (-0.6, 0.9, 1))


def finish():
    bpy.context.view_layer.update()
    cut_below_ground(0.055)
    objects = vrlib.source_objects()
    lo, hi = vrlib.world_bounds(objects)
    target = json.loads(Path(__file__).with_name("asset.json").read_text())["target_size_m"]
    factor = min(1, *(0.995 * t / s for t, s in zip(target, hi - lo)))
    if factor < 1:
        scale = Matrix.Scale(factor, 4)
        for obj in objects:
            obj.data.transform(scale)
            obj.location *= factor
            for modifier in obj.modifiers:
                if modifier.type == "BEVEL":
                    modifier.width *= factor
            for name in ("socket_local", "glow_radii", "glow_centre"):
                if name in obj:
                    obj[name] = list(Vector(obj[name]) * factor)
    bpy.context.view_layer.update()


def ground_disc(name, radius, squash, location, mat):
    vertices = []
    faces = []
    coverage = []
    for ring in range(25):
        t = ring / 24
        for i in range(128):
            angle = math.tau * i / 128
            edge = (1 + 0.10 * math.sin(angle * 3) + 0.07 * math.sin(angle * 7 + 1)
                    + 0.055 * math.sin(angle * 13) + 0.035 * math.sin(angle * 29 + 0.7))
            r = radius * t * edge
            x, y = math.cos(angle) * r, math.sin(angle) * r
            p = Vector((x, y, 2.7))
            patch = noise.fractal(p * 0.42, 1, 2, 4)
            moss = max(0, min(1, (patch - 0.06) / 0.26)) * max(0, min(1, (0.92 - t) / 0.15))
            rough = noise.fractal(p * 2.1, 1, 2, 4)
            z = (radius * squash * (1 - t * t) ** 2
                 + (0.10 * rough + 0.055 * moss) * (1 - t ** 4)
                 - (location[2] + 0.055) * t ** 2)
            vertices.append((x, y, z))
            coverage.append(moss)
    for ring in range(24):
        for i in range(128):
            a = ring * 128 + i
            b = ring * 128 + (i + 1) % 128
            if ring == 0:
                faces.append((a, b + 128, a + 128))
            else:
                faces.append((a, b, b + 128, a + 128))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], [tuple(reversed(face)) for face in faces])
    mesh.update()
    field = mesh.attributes.new("moss_coverage", "FLOAT", "POINT")
    field.data.foreach_set("value", coverage)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.000001)
    bm.to_mesh(mesh)
    bm.free()
    for face in mesh.polygons:
        face.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.data.materials.append(mat)
    return vrlib.link_to_source(obj)


def radial_glow(crystals):
    centre = Vector((0, 0, 8.1))
    radii = Vector((4.3, 4.3, 6.8))
    for crystal in crystals:
        bm = bmesh.new()
        bm.from_mesh(crystal.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=10, use_grid_fill=True)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(crystal.data)
        bm.free()
        distance = crystal.data.attributes.new("core_distance", "FLOAT", "POINT")
        glow = crystal.data.attributes.new("core_glow", "FLOAT", "POINT")
        for vertex, d, g in zip(crystal.data.vertices, distance.data, glow.data):
            p = crystal.matrix_world @ vertex.co - centre
            d.value = Vector(tuple(p[i] / radii[i] for i in range(3))).length
            g.value = max(0, min(1, (1.05 - d.value) / 0.65)) ** 2
        crystal["glow_radii"] = list(radii)
        crystal["glow_centre"] = list(centre)
    mat = crystals[0].data.materials[0]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = "core_glow"
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.8
    gain.inputs[2].default_value = 0.015
    links.new(attribute.outputs["Fac"], gain.inputs[0])
    links.new(gain.outputs[0], bsdf.inputs["Emission Strength"])
    palette = vrmat.load_palette()
    body = bsdf.inputs["Base Color"].links[0].from_socket
    inner = nodes.new("ShaderNodeMixRGB")
    inner.inputs[0].default_value = 0.18
    inner.inputs[2].default_value = (*palette["violet_glow"]["linear_rgb"], 1)
    links.new(body, inner.inputs[1])
    links.new(inner.outputs[0], bsdf.inputs["Emission Color"])
    depth = nodes.new("ShaderNodeMixRGB")
    depth.blend_type = "MULTIPLY"
    depth.inputs[0].default_value = 1
    depth.inputs[2].default_value = (0.6, 0.6, 0.6, 1)
    links.new(body, depth.inputs[1])
    links.new(depth.outputs[0], bsdf.inputs["Base Color"])
    for name in ("Roughness", "Normal"):
        for link in list(bsdf.inputs[name].links):
            links.remove(link)
    bsdf.inputs["Roughness"].default_value = 0.32
    bsdf.inputs["Specular IOR Level"].default_value = 0.16
    bsdf.inputs["Coat Weight"].default_value = 0


def menhir(name, rng, size, location, angle, mat):
    section = [(0.5, -0.42), (0.5, -0.10), (0.5, 0), (0.5, 0.10),
               (0.5, 0.40), (-0.15, 0.5), (-0.5, 0.24), (-0.46, -0.4), (0.05, -0.5)]
    bm = bmesh.new()
    loops = []
    local_rng = random.Random(SEED + int(angle * 10000))
    profile = [local_rng.uniform(0.86, 1.12) if i > 4 else 1 for i in range(len(section))]
    for z, scale in ((-0.5, 0.94), (-0.12, 1.03), (0.19, 0.88), (0.5, 0.72)):
        loop = []
        for i, (x, y) in enumerate(section):
            top = z == 0.5
            scale_x = scale * profile[i]
            scale_y = scale * (1 + (0.09 * math.sin(i * 1.9 + z * 5 + angle) if i > 4 else 0))
            height = z
            if top:
                height += (0.045 * math.sin(i * 1.7 + angle) if i not in (1, 2, 3) else 0)
                if i == 2:
                    height -= 0.16
            loop.append(bm.verts.new(((x * scale_x + (0.08 if top else -0.035 * math.sin(z * 9 + angle))) * size[0],
                                      (y * scale_y - (0.04 if top else 0.025 * math.sin(z * 7))) * size[1],
                                      height * size[2])))
        loops.append(loop)
    socket = loops[-1][2].co.copy()
    bm.faces.new(list(reversed(loops[0])))
    centre = bm.verts.new((0, 0, size[2] * 0.39))
    for i in range(len(section)):
        j = (i + 1) % len(section)
        for lower, upper in zip(loops, loops[1:]):
            bm.faces.new((lower[i], lower[j], upper[j], upper[i]))
        bm.faces.new((loops[-1][i], loops[-1][j], centre))
    for normal, point in (((-0.4, -0.2, 1), (-size[0] * 0.2, -size[1] * 0.18, size[2] * 0.47)),
                          ((-1, 0.2, 0.15), (-size[0] * 0.40, 0, 0)),
                          ((0.2, 1, 0.05), (0, size[1] * 0.42, 0)),
                          ((1, 1, 0.15), (size[0] * 0.36, size[1] * 0.26, size[2] * 0.12)),
                          ((1, -1, -0.25), (size[0] * 0.39, -size[1] * 0.35, -size[2] * 0.10)),
                          ((-0.7, 1, 0.24), (-size[0] * 0.3, size[1] * 0.3, size[2] * 0.12))):
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                    plane_co=point, plane_no=Vector(normal).normalized(),
                                    clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=min(size) * 0.008, segments=1, affect="EDGES")
    bm.normal_update()
    sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle() > math.radians(12)]
    bmesh.ops.split_edges(bm, edges=sharp)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=8, use_grid_fill=True)
    for vertex in bm.verts:
        wear = noise.fractal(vertex.co * 2 + Vector(location), 1, 2, 3)
        vertex.co += vertex.co.normalized() * wear * min(size) * 0.008
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for face in mesh.polygons:
        face.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    obj.location = location
    obj.rotation_euler = Euler((0.08, -0.27, angle))
    obj["socket_local"] = list(socket)
    return vrlib.link_to_source(obj)


def energy_filaments(stones):
    material = vrmat.get("violet_energy").copy()
    material.name = "Stone-rooted tapered energy"
    bsdf = material.node_tree.nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    for name in ("Base Color", "Emission Color", "Emission Strength", "Roughness"):
        for link in list(bsdf.inputs[name].links):
            material.node_tree.links.remove(link)
    bsdf.inputs["Base Color"].default_value = (*palette["violet_body"]["linear_rgb"], 1)
    bsdf.inputs["Emission Color"].default_value = tuple(
        0.92 * a + 0.08 * b for a, b in zip(palette["violet_body"]["linear_rgb"],
                                          palette["violet_glow"]["linear_rgb"])) + (1,)
    bsdf.inputs["Emission Strength"].default_value = 2.6
    bsdf.inputs["Roughness"].default_value = 0.45
    for i, stone in enumerate(stones):
        anchor = stone.matrix_world @ Vector(stone["socket_local"])
        angle = math.atan2(anchor.y, anchor.x)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        tangent = Vector((-math.sin(angle), math.cos(angle), 0))
        points = [anchor - Vector((0, 0, 0.08))]
        for outward, around, height in ((-0.2, 0.3, 0.8), (-0.9, 0.7, 1.7),
                                        (-1.8, 0.65, 2.7), (-2.7, 0.15, 3.7)):
            points.append(anchor + radial * outward + tangent * around + Vector((0, 0, height)))
        curve = bpy.data.curves.new(f"filament_{i}", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 20
        curve.bevel_depth = 0.075
        curve.bevel_resolution = 3
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(len(points) - 1)
        for point, position, radius in zip(spline.bezier_points, points, (1.8, 1.2, 0.75, 0.3, 0.02)):
            point.co = position
            point.handle_left_type = point.handle_right_type = "AUTO"
            point.radius = radius
        obj = bpy.data.objects.new(curve.name, curve)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        strand = bpy.data.objects.new(curve.name + "_mesh", mesh)
        strand.data.materials.append(material)
        vrlib.link_to_source(strand)
        bpy.data.objects.remove(obj, do_unlink=True)



def build():
    rng = random.Random(SEED)
    rock = support_material("Weathered notched limestone", 0.65)
    earth = support_material("Mossy shared earth", 0.45, earth=True)
    ground_disc("Shared earth bed", 7.4, 0.075, (0, 0, 0.12), earth)
    bed = make_rock("Continuous fractured cradle", rng, 4.6, 0.43, 6, rock)
    bed.location = (0, 0, 1.4)
    for i in range(7):
        angle = math.tau * i / 7 + 0.2
        distance = 2.4 + rng.uniform(-0.2, 0.2)
        rubble = make_rock(f"Interlocked cradle rubble {i}", rng, rng.uniform(1.6, 2.1),
                           rng.uniform(0.55, 0.8), 5, rock)
        rubble.location = (math.cos(angle) * distance, math.sin(angle) * distance,
                           rng.uniform(1.5, 2.2))
        rubble.rotation_euler = Euler((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), angle))
    stones = []
    for i in range(4):
        angle = math.tau * i / 4 + 0.3
        distance = 4.4 + rng.uniform(-0.15, 0.15)
        height = rng.uniform(5.0, 5.8)
        location = (math.cos(angle) * distance, math.sin(angle) * distance, height * 0.43)
        stone = menhir(f"Cradle stone {i}", rng, (rng.uniform(2.7, 3.2), rng.uniform(2.4, 2.8), height),
                       location, angle, rock)
        stones.append(stone)
        socket = make_rock(f"Buried stone socket {i}", rng, 1.6, 0.13, 5, earth)
        socket.location = (*location[:2], 0.18)
    mat = crystal_material()
    crystals = []
    main = make_crystal("crystal_core_main", rng, 2.05, 13.9, mat)
    chip_tip(main, 13.9, 0.965)
    place(main, rng, 2.2, 0.24, math.radians(5), 2.7)
    crystals.append(main)
    for i, (height, angle, tilt) in enumerate(((9.1, 0.2, 15), (10.5, 2.2, 18),
                                              (7.2, 3.7, 21), (8.4, 5.0, 16))):
        crystal = make_crystal(f"crystal_core_intergrown_{i}", rng, height * 0.15, height, mat)
        chip_tip(crystal, height, 0.95)
        place(crystal, rng, angle, 1.45, math.radians(tilt), 2.5)
        crystals.append(crystal)
    bpy.context.view_layer.update()
    radial_glow(crystals)
    energy_filaments(stones)
    finish()
