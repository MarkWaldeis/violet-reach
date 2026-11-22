"""Violet crystal cluster on a mossy rock base. Units are metres, origin at ground centre, Z up."""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector, noise

import vrlib
import vrmat

SEED = 918643


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
    """Six-sided prism with an irregular double-tapered tip, built bottom-up."""
    sides = 6
    twist = rng.uniform(0, math.tau)
    profile = [rng.uniform(0.82, 1.18) for _ in range(sides)]
    rings = [
        (0.0, 1.00),
        (rng.uniform(0.30, 0.42), rng.uniform(1.04, 1.12)),
        (0.48, 1.07),
        (0.50, 0.90),
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
            if i == len(rings) - 1:
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
        if not bm.verts:
            bm.free()
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()


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
    ao.inputs["Distance"].default_value = 0.19
    joints = nodes.new("ShaderNodeMixRGB")
    joints.inputs[1].default_value = tuple(v * 0.55 for v in seam) + (1,)
    links.new(ao.outputs["AO"], joints.inputs[0])
    links.new(dirt.outputs[0], joints.inputs[2])
    links.new(joints.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.22
    mat["asset_tweaks"] = "approved stair_terrace_a: 0.87-scale cream variation, 0.19m joint AO, palette patina in recesses and feet; library pores retained"
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
    rock = weathered_limestone("Cluster | weathered fault rock")
    limestone = weathered_limestone("Cluster | limestone breaks")
    limestone.name = "Chalk limestone breaks"
    crystal = vrmat.get("violet_crystal").copy()
    crystal.name = "Cluster | library violet depth"
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
    space.inputs[3].default_value = 1
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
    crystal["asset_tweaks"] = "geometry depth 0–1; palette violet_body gains 0.12/0.24/0.7; tip mixes violet_glow 0.3; library body mix 0.12; hue 0.515; ramp-coloured emission 0.3 plus veins; normal tilt 0.12; texture scale 1"

    base = make_rock("rock_base", rng, 1.75, 0.40, 7, rock)
    base.location = (0, 0, 0.17)
    moss_tufts(base, random.Random(SEED + 92), moss_material(), 75, 1.6)
    for i, (angle, dist, radius) in enumerate([(0.6, 1.35, 0.62), (2.7, 1.2, 0.78), (4.4, 1.3, 0.55), (5.5, 0.95, 0.5)]):
        lump = make_rock(f"rock_lump_{i}", rng, radius, rng.uniform(0.6, 0.85), 6, rock if i % 2 else limestone)
        lump.location = (math.cos(angle) * dist, math.sin(angle) * dist, radius * 0.28)
        lump.rotation_euler = Euler((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0, 6.28)))
    for i in range(9):
        angle, dist, radius = rng.uniform(0, math.tau), rng.uniform(1.5, 2.1), rng.uniform(0.09, 0.2)
        pebble = make_rock(f"rock_pebble_{i}", rng, radius, rng.uniform(0.55, 0.8), 4, rock)
        pebble.location = (math.cos(angle) * dist, math.sin(angle) * dist, radius * 0.25)

    mineral_structure(crystal)
    main = make_crystal("crystal_main", rng, 0.43, 2.8, crystal, chip=0.91)
    place(main, rng, 2.2, 0.24, math.radians(12), 0.35)

    for i in range(5):
        angle = math.tau * i / 5 + rng.uniform(-0.25, 0.25)
        height = [1.25, 1.65, 1.65, 2.3, 1.1][i]
        chip = {1: 0.86, 3: 0.91}.get(i, 0.94)
        c = make_crystal(f"crystal_mid_{i}", rng, height * rng.uniform(0.105, 0.13), height,
                         crystal, chip=chip)
        place(c, rng, angle, rng.uniform(0.48, 0.7), math.radians(rng.uniform(23, 42)), 0.32)

    for i in range(9):
        angle = rng.uniform(0, math.tau)
        height = rng.uniform(0.35, 0.95)
        c = make_crystal(f"crystal_small_{i}", rng, height * rng.uniform(0.14, 0.2), height, crystal)
        place(c, rng, angle, rng.uniform(0.75, 1.25), math.radians(rng.uniform(22, 58)), 0.22)

    bpy.context.view_layer.update()
    cut_below_ground()
