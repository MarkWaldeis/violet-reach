"""Dominant violet spire in fractured chalk limestone. Metres, Z up."""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector, noise

import vrlib
import vrmat

SEED = 630517


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
    stone_patina(mesh, radius * 2)
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    return vrlib.link_to_source(obj)


def make_crystal(name, rng, radius, height, mat, chip=None):
    """Uneven proof-style growth rings, a fault shoulder and fractured termination."""
    sides = 10 if height > 3 else 8
    twist = rng.uniform(0, math.tau)
    profile = [rng.uniform(0.74, 1.24) for _ in range(sides)]
    widths = [rng.uniform(0.65, 1.35) for _ in range(sides)]
    angles = [twist + math.tau * sum(widths[:i]) / sum(widths) for i in range(sides)]
    rings = [
        (0.0, 1.00),
        (0.29, 1.07),
        (0.43, 1.12),
        (0.455, 0.86),
        (0.73, 0.78),
        (0.88, 0.43),
    ]
    tip_shift = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0)) * radius
    bm = bmesh.new()
    loops = []
    for i, (t, scale) in enumerate(rings):
        lean = tip_shift * (t ** 2) * 0.6
        loop = []
        for s in range(sides):
            a = angles[s]
            r = radius * scale * profile[s]
            if i == len(rings) - 1:
                r *= rng.uniform(0.8, 1.2)
            z = height * t + (rng.uniform(-0.004, 0.004) * height if i else 0)
            loop.append(bm.verts.new(Vector((math.cos(a) * r, math.sin(a) * r, z)) + lean))
        loops.append(loop)
    apex = bm.verts.new(Vector((0, 0, height)) + tip_shift)
    for lower, upper in zip(loops, loops[1:]):
        for s in range(sides):
            bm.faces.new((lower[s], lower[(s + 1) % sides], upper[(s + 1) % sides], upper[s]))
    for s in range(sides):
        bm.faces.new((loops[-1][s], loops[-1][(s + 1) % sides], apex))
    bm.faces.new(list(reversed(loops[0])))
    if chip is not None:
        cut = bmesh.ops.bisect_plane(
            bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=(0, 0, height * chip),
            plane_no=Vector((0.85, -0.55, 1)).normalized(), clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=6, use_grid_fill=True)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    depth = mesh.attributes.new("mineral_depth", "FLOAT", "POINT")
    for vertex, value in zip(mesh.vertices, depth.data):
        z = max(0, min(1, vertex.co.z / height))
        axis = min(1, Vector((vertex.co.x, vertex.co.y)).length / radius)
        axis = max(0, min(1, (axis - 0.65) / 0.35))
        growth = 0.06 * (1 - (z * 3) % 1)
        crown = max(0, min(1, (z - 0.8) / 0.2))
        value.value = max(0, min(1, 0.18 + 0.72 * z
                                - 0.5 * (1 - axis) * (1 - crown) - growth))
    mineral_attributes(mesh, radius, height, twist)
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


def cut_below_ground(depth=0.055):
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


def limestone_block(name, rng, size, location, mat):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector(tuple(a * b for a, b in zip(v.co, size)))
        v.co.x += v.co.z * rng.uniform(-0.18, 0.18)
        v.co.y += v.co.z * rng.uniform(-0.16, 0.16)
    planes = [(Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 1)),
               Vector((0, 0, size[2] * rng.uniform(0.20, 0.38)))),
              (Vector((1, rng.uniform(-0.6, 0.6), rng.uniform(-0.3, 0.3))),
               Vector((size[0] * 0.36, 0, 0))),
              (Vector((-0.6, -1, 0.2)), Vector((0, -size[1] * 0.34, 0))),
              (Vector((0.6, 0.6, 0.5)), Vector((size[0] * 0.23, size[1] * 0.23, size[2] * 0.23)))]
    for _ in range(2):
        corner = Vector(tuple(rng.choice((-1, 1)) * s * 0.5 for s in size))
        normal = Vector(tuple(math.copysign(rng.uniform(0.6, 1.2), c) for c in corner)).normalized()
        planes.append((normal, corner - normal * rng.uniform(0.05, 0.12)))
    for normal, point in planes:
        cut = bmesh.ops.bisect_plane(
            bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=point, plane_no=normal.normalized(), clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=10, use_grid_fill=True)
    bm.normal_update()
    offset = Vector(location)
    for vertex in bm.verts:
        wear = noise.fractal(vertex.co * 6 + offset, 1, 2, 3)
        vertex.co += vertex.normal * wear * min(size) * 0.035
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    stone_patina(mesh, size[2])
    obj = bpy.data.objects.new(name, mesh)
    for face in mesh.polygons:
        face.use_smooth = True
    obj.data.materials.append(mat)
    obj.location = location
    obj.rotation_euler = Euler((rng.uniform(-0.19, 0.19), rng.uniform(-0.22, 0.22), rng.uniform(-0.6, 0.6)))
    bevel = obj.modifiers.new("Worn limestone edges", "BEVEL")
    bevel.width, bevel.segments = 0.014, 2
    return vrlib.link_to_source(obj)


def mineral_attributes(mesh, radius, height, phase):
    fields = {name: mesh.attributes.new(name, "FLOAT", "POINT")
              for name in ("growth_height", "plane_distance_0", "plane_distance_1", "vein_window")}
    for vertex in mesh.vertices:
        p = vertex.co
        z = max(0, min(1, p.z / height))
        angle = math.atan2(p.y, p.x)
        fields["growth_height"].data[vertex.index].value = z + 0.018 * math.sin(2 * angle + phase)
        fields["vein_window"].data[vertex.index].value = (
            math.sin(math.pi * z) ** 0.5 * max(0, math.sin(z * 19 + phase)))
        for i in range(2):
            a = phase + i * 1.37
            fields[f"plane_distance_{i}"].data[vertex.index].value = (
                (p.x * math.cos(a) + p.y * math.sin(a)) / radius + 0.22 * z - 0.18
                + 0.15 * math.sin(z * 24 + phase) + 0.06 * math.sin(z * 53 + a))


def mineral_structure(mat):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    dark = tuple(v * 0.16 for v in palette["violet_shadow"]["linear_rgb"]) + (1,)
    light = tuple(v * 0.46 for v in palette["violet_body"]["linear_rgb"]) + (1,)

    def attribute(name):
        node = nodes.new("ShaderNodeAttribute")
        node.attribute_name = name
        return node.outputs["Fac"]

    def math_node(operation, source, other=0):
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        links.new(source, node.inputs[0])
        if isinstance(other, (float, int)):
            node.inputs[1].default_value = other
        else:
            links.new(other, node.inputs[1])
        return node.outputs[0]

    def threshold(source, start, end):
        node = nodes.new("ShaderNodeMapRange")
        node.clamp = True
        node.inputs["From Min"].default_value = start
        node.inputs["From Max"].default_value = end
        links.new(source, node.inputs["Value"])
        return node.outputs[0]

    def mix(factor, source, color):
        node = nodes.new("ShaderNodeMixRGB")
        links.new(factor, node.inputs[0])
        links.new(source, node.inputs[1])
        node.inputs[2].default_value = color
        return node.outputs[0]

    phase = math_node("MULTIPLY", attribute("growth_height"), 6 * math.pi)
    bands = threshold(math_node("SINE", phase), 0.65, 0.95)
    source = bsdf.inputs["Base Color"].links[0].from_socket
    body = mix(math_node("MULTIPLY", bands, 0.72), source, dark)
    a = math_node("ABSOLUTE", attribute("plane_distance_0"))
    b = math_node("ABSOLUTE", attribute("plane_distance_1"))
    distance = math_node("MINIMUM", a, b)
    border = threshold(distance, 0.11, 0.04)
    veins = threshold(distance, 0.04, 0.008)
    veins = math_node("MULTIPLY", veins, attribute("vein_window"))
    body = mix(math_node("MULTIPLY", border, 0.8), body, dark)
    links.new(mix(veins, body, light), bsdf.inputs["Base Color"])
    strength = bsdf.inputs["Emission Strength"].links[0].from_socket
    attenuation = math_node("ADD", math_node("MULTIPLY", bands, -0.72), 1)
    strength = math_node("MULTIPLY", strength, attenuation)
    strength = math_node("ADD", strength, math_node("MULTIPLY", veins, 0.025))
    links.new(strength, bsdf.inputs["Emission Strength"])
    emission = bsdf.inputs["Emission Color"].links[0].from_socket
    links.new(mix(veins, emission, light), bsdf.inputs["Emission Color"])
    for link in list(bsdf.inputs["Roughness"].links):
        links.remove(link)
    bsdf.inputs["Roughness"].default_value = 0.38
    bsdf.inputs["Coat Weight"].default_value = 0.04
    bsdf.inputs["Specular IOR Level"].default_value = 0.12
    mat["structure_tweaks"] = "three dark growth bands; two signed crystal-plane attributes; dark vein borders, narrow violet veins; restrained coat/specular"


def weathered_limestone(name):
    mat = vrmat.get("monument_weathered").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    coords = next(node for node in nodes if node.type == "TEX_COORD").outputs["Object"]
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 0.87
    grain.inputs["Detail"].default_value = 3
    links.new(coords, grain.inputs["Vector"])
    cream = palette["monument_white"]["linear_rgb"]
    seam = palette["stone_weathered"]["linear_rgb"]
    shadow = palette["monument_shadow"]["linear_rgb"]
    tones = nodes.new("ShaderNodeValToRGB")
    tones.color_ramp.elements[0].position = 0.23
    tones.color_ramp.elements[0].color = tuple(v * 0.56 for v in cream) + (1,)
    tones.color_ramp.elements[1].position = 0.79
    tones.color_ramp.elements[1].color = tuple(v * 0.90 for v in cream) + (1,)
    links.new(grain.outputs["Fac"], tones.inputs[0])
    patina = nodes.new("ShaderNodeAttribute")
    patina.attribute_name = "stone_patina"
    dirt = nodes.new("ShaderNodeMixRGB")
    dirt.inputs[2].default_value = tuple(0.35 * a + 0.65 * b for a, b in zip(seam, palette["soil"]["linear_rgb"])) + (1,)
    links.new(patina.outputs["Fac"], dirt.inputs[0])
    links.new(tones.outputs[0], dirt.inputs[1])
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    ao.inputs["Distance"].default_value = 0.38
    joints = nodes.new("ShaderNodeMixRGB")
    joints.inputs[1].default_value = tuple(v * 0.35 for v in palette["soil"]["linear_rgb"]) + (1,)
    links.new(ao.outputs["AO"], joints.inputs[0])
    links.new(dirt.outputs[0], joints.inputs[2])
    links.new(joints.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.22
    mat["asset_tweaks"] = "approved stair_terrace_a approach: 0.87-scale cream variation, 0.38m soil-dark joint AO, palette patina in recesses and feet; library pores retained"
    return mat


def stone_patina(mesh, height):
    attr = mesh.attributes.new("stone_patina", "FLOAT", "POINT")
    low = min(vertex.co.z for vertex in mesh.vertices)
    for vertex, value in zip(mesh.vertices, attr.data):
        wear = noise.fractal(vertex.co * 2.3, 1, 2, 3)
        value.value = max(0, min(0.85, 0.9 - (vertex.co.z - low) / height + wear * 0.28))


def moss_material():
    mat = vrmat.get("mossy_rock").copy()
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 65
    grain.inputs["Detail"].default_value = 4
    colors = nodes.new("ShaderNodeValToRGB")
    green = vrmat.load_palette()["moss"]["linear_rgb"]
    colors.color_ramp.elements[0].color = tuple(v * 0.45 for v in green) + (1,)
    colors.color_ramp.elements[1].color = tuple(v * 1.55 for v in green) + (1,)
    links.new(grain.outputs["Fac"], colors.inputs[0])
    links.new(colors.outputs[0], nodes["Principled BSDF"].inputs["Base Color"])
    return mat


def moss_tufts(surface, rng, mat, count, extent):
    for i in range(count):
        angle = rng.uniform(0, math.tau)
        distance = extent * rng.uniform(0.15, 0.96)
        origin = Vector((math.cos(angle) * distance, math.sin(angle) * distance, extent * 4))
        hit, point, normal, _ = surface.ray_cast(origin, Vector((0, 0, -1)))
        if not hit or normal.z < 0.15:
            continue
        radius = extent * rng.uniform(0.035, 0.065)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
        for vertex in bm.verts:
            grain = noise.fractal(vertex.co * (8 / radius) + Vector((i, 0, 0)), 1, 2, 3)
            vertex.co *= 1 + grain * 0.24
            vertex.co.z *= 0.5
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        mesh = bpy.data.meshes.new(f"moss_tuft_{surface.name}_{i}")
        bm.to_mesh(mesh)
        bm.free()
        for face in mesh.polygons:
            face.use_smooth = True
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj.data.materials.append(mat)
        obj.matrix_world = surface.matrix_world.copy()
        obj.location += surface.matrix_world.to_3x3() @ (point + normal * radius * 0.05)
        vrlib.link_to_source(obj)


def build():
    rng = random.Random(SEED)
    limestone = weathered_limestone("Fault | limestone")
    weather = weathered_limestone("Fault | sheltered stone")
    soil = vrmat.get("forest_soil").copy()
    moss = moss_material()
    crystal = vrmat.get("violet_crystal").copy()
    crystal.name = "Spire | library violet depth"
    nodes, links = crystal.node_tree.nodes, crystal.node_tree.links
    bsdf = nodes["Principled BSDF"]
    # Keep the library graph; soften inclusion contrast and synthetic normal tilt.
    for node in nodes:
        if node.type == "VECT_MATH" and node.operation == "SCALE":
            node.inputs[3].default_value = 0.12
        if node.type == "VALTORGB" and node.inputs["Fac"].is_linked:
            if node.inputs["Fac"].links[0].from_node.type == "SEPXYZ":
                color = vrmat.load_palette()["violet_shadow"]["linear_rgb"]
                node.color_ramp.elements[0].color = (*(v * 0.65 for v in color), 1)
    coords = next(node for node in nodes if node.type == "TEX_COORD")
    targets = [link.to_socket for link in list(links) if link.from_socket == coords.outputs["Object"]]
    space = nodes.new("ShaderNodeVectorMath")
    space.operation = "SCALE"
    space.inputs[3].default_value = 0.45
    links.new(coords.outputs["Object"], space.inputs[0])
    for socket in targets:
        links.new(space.outputs[0], socket)
    source = bsdf.inputs["Base Color"].links[0].from_socket
    depth = nodes.new("ShaderNodeAttribute")
    depth.attribute_name = "mineral_depth"
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.name = "Geometry axial and axis depth"
    palette = vrmat.load_palette()
    violet = palette["violet_body"]["linear_rgb"]
    lavender = palette["violet_glow"]["linear_rgb"]
    def shade(gain):
        return tuple(v * gain for v in violet) + (1,)
    light = tuple(0.7 * a + 0.3 * b for a, b in zip(violet, lavender)) + (1,)
    ramp.color_ramp.elements[0].color = shade(0.12)
    ramp.color_ramp.elements[1].color = light
    for position, gain in [(0.28, 0.24), (0.58, 0.7)]:
        ramp.color_ramp.elements.new(position).color = shade(gain)
    links.new(depth.outputs["Fac"], ramp.inputs[0])
    body = nodes.new("ShaderNodeMixRGB")
    body.inputs[0].default_value = 0.88
    links.new(source, body.inputs[1])
    links.new(ramp.outputs[0], body.inputs[2])
    tone = nodes.new("ShaderNodeHueSaturation")
    tone.inputs["Hue"].default_value = 0.515
    links.new(body.outputs[0], tone.inputs["Color"])
    links.new(tone.outputs[0], bsdf.inputs["Base Color"])
    light_color = nodes.new("ShaderNodeHueSaturation")
    light_color.inputs["Hue"].default_value = 0.515
    links.new(ramp.outputs[0], light_color.inputs["Color"])
    links.new(light_color.outputs[0], bsdf.inputs["Emission Color"])
    veins = bsdf.inputs["Emission Strength"].links[0].from_socket
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "ADD"
    gain.inputs[1].default_value = 0.3
    links.new(veins, gain.inputs[0])
    links.new(gain.outputs[0], bsdf.inputs["Emission Strength"])
    # Emission uses the dark-to-light geometry ramp, never a uniform pale colour.
    crystal["asset_tweaks"] = "geometry depth 0–1; palette violet_body gains 0.12/0.24/0.7; tip mixes violet_glow 0.3; library body mix 0.12; hue 0.515; ramp-coloured emission 0.3 plus veins; normal tilt 0.12; texture scale 0.45"

    footing = [(-1.0, -0.6, 2.1, 1.4, 0.95), (0.7, -0.65, 1.8, 1.6, 0.8),
               (-1.0, 0.7, 1.65, 1.7, 1.3), (0.6, 0.7, 1.7, 1.35, 1.05),
               (1.6, 0.15, 0.9, 1.0, 0.55), (-1.7, 0.15, 1.0, 0.9, 0.5)]
    for i, (x, y, sx, sy, sz) in enumerate(footing):
        limestone_block(f"limestone_break_{i}", rng, (sx, sy, sz), (x * 0.85, y * 0.85, sz * 0.35),
                        weather if i in (2, 5) else limestone)
        nx, ny = footing[(i + 1) % len(footing)][:2]
        joint = make_rock(f"joint_earth_{i}", rng, 0.56, 0.23, 5, soil)
        joint.location = ((x + nx) * 0.47, (y + ny) * 0.47, 0.17)
        tuft = make_rock(f"joint_moss_{i}", rng, 0.21, 0.2, 4, moss)
        tuft.location = (joint.location.x, joint.location.y, 0.37)
    for i, (size, position) in enumerate([((1.0, 0.75, 0.55), (-1.55, 0.4, 1.05)),
                                         ((0.7, 0.85, 1.05), (0.6, 1.6, 1.03))]):
        block = limestone_block(f"leaning_break_{i}", rng, size, position, limestone)
        block.rotation_euler.x += 0.29 if i else -0.25

    foundation = make_rock("continuous_fault_rock", rng, 1.95, 0.24, 6, weather)
    foundation.location = (0, 0, 0.24)
    collar = make_rock("soil_collar", rng, 1.28, 0.20, 6, soil)
    collar.location = (0, -0.23, 0.59)
    moss_tufts(collar, random.Random(SEED + 83), moss, 145, 1.22)
    for i in range(6):
        angle = i * math.tau / 6 + 0.2
        pebble = make_rock(f"collar_pebble_{i}", rng, rng.uniform(0.09, 0.17), 0.75, 4, weather)
        pebble.location = (math.cos(angle), math.sin(angle), 0.66)
    for i in range(10):
        angle = rng.uniform(0, math.tau)
        distance = rng.uniform(1.9, 2.3)
        radius = rng.uniform(0.12, 0.30)
        debris = make_rock(f"limestone_scree_{i}", rng, radius, 0.65, 4, limestone)
        debris.location = (math.cos(angle) * distance, math.sin(angle) * distance, radius * 0.32)

    mineral_structure(crystal)
    main = make_crystal("dominant_spire", rng, 0.67, 6.72, crystal, chip=0.91)
    place(main, rng, 1.3, 0.04, math.radians(8), 0.56)
    for i, (angle, height, distance) in enumerate([(0.2, 3.65, 0.7), (2.0, 3.15, 0.65),
                                                   (3.8, 2.0, 0.62), (5.2, 0.95, 0.68)]):
        satellite = make_crystal(f"satellite_{i}", rng, height * 0.14, height, crystal,
                                 chip=0.83 if i == 1 else 0.93)
        place(satellite, rng, angle, distance, math.radians(rng.uniform(18, 28)), 0.45)
    bpy.context.view_layer.update()
    cut_below_ground()
