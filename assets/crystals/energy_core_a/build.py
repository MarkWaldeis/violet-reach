"""Double-terminated violet seed levitating over a fractured limestone cradle."""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector, noise

import vrlib
import vrmat

SEED = 840173


def mineral_attributes(mesh, radius, height, phase):
    fields = {name: mesh.attributes.new(name, "FLOAT", "POINT")
              for name in ("growth_height", "plane_distance_0", "plane_distance_1", "vein_window")}
    for vertex in mesh.vertices:
        p = vertex.co
        z = max(0, min(1, p.z / height))
        angle = math.atan2(p.y, p.x)
        fields["growth_height"].data[vertex.index].value = z + 0.018 * math.sin(2 * angle + phase)
        fields["vein_window"].data[vertex.index].value = math.sin(math.pi * z) ** 0.5
        for i in range(2):
            a = phase + i * 1.37
            fields[f"plane_distance_{i}"].data[vertex.index].value = (
                (p.x * math.cos(a) + p.y * math.sin(a)) / radius + 0.22 * z - 0.18)


def mineral_structure(mat):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    dark = tuple(v * 0.16 for v in palette["violet_shadow"]["linear_rgb"]) + (1,)
    light = tuple(0.65 * a + 0.35 * b for a, b in
                  zip(palette["violet_body"]["linear_rgb"], palette["violet_glow"]["linear_rgb"])) + (1,)

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
    strength = math_node("ADD", strength, math_node("MULTIPLY", veins, 0.7))
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


def seed_material():
    mat = vrmat.get("violet_crystal").copy()
    mat.name = "Seed | violet heart"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
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
    space.inputs[3].default_value = 0.22
    links.new(coords.outputs["Object"], space.inputs[0])
    for socket in targets:
        links.new(space.outputs[0], socket)
    mat["asset_tweaks"] = "geometry depth 0–1; palette violet_body gains 0.12/0.24/0.7; tip mixes violet_glow 0.3; library body mix 0.12; hue 0.515; centre-only emission 0–1.8; normal tilt 0.12; texture scale 0.22"
    source = bsdf.inputs["Base Color"].links[0].from_socket
    depth = nodes.new("ShaderNodeAttribute")
    depth.attribute_name = "mineral_depth"
    palette = vrmat.load_palette()
    violet = palette["violet_body"]["linear_rgb"]
    lavender = palette["violet_glow"]["linear_rgb"]
    def shade(gain):
        return tuple(v * gain for v in violet) + (1,)
    light = tuple(0.7 * a + 0.3 * b for a, b in zip(violet, lavender)) + (1,)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.name = "Geometry inner depth"
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
    heat = nodes.new("ShaderNodeAttribute")
    heat.attribute_name = "core_glow"
    glow = nodes.new("ShaderNodeValToRGB")
    glow.color_ramp.elements[0].color = shade(0.24)
    glow.color_ramp.elements[1].color = light
    glow.color_ramp.elements.new(0.35).color = shade(0.7)
    links.new(heat.outputs["Fac"], glow.inputs[0])
    light_color = nodes.new("ShaderNodeHueSaturation")
    light_color.inputs["Hue"].default_value = 0.515
    links.new(glow.outputs[0], light_color.inputs["Color"])
    links.new(light_color.outputs[0], bsdf.inputs["Emission Color"])
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 0.65
    links.new(heat.outputs["Fac"], gain.inputs[0])
    links.new(gain.outputs[0], bsdf.inputs["Emission Strength"])
    mineral_structure(mat)
    bsdf.inputs["Coat Weight"].default_value = 0
    bsdf.inputs["Specular IOR Level"].default_value = 0
    return mat


def seed(rng, mat):
    radius, height = 3.45, 14.75
    sides = 11
    twist = 0.22
    profile = [rng.uniform(0.82, 1.18) for _ in range(sides)]
    rings = [(0.0, 0.0), (0.05, 0.20), (0.12, 0.52), (0.28, 0.98),
             (0.42, 1.10), (0.445, 0.96), (0.60, 1.02), (0.74, 0.84),
             (0.86, 0.53), (0.92, 0.30), (1.0, 0.0)]
    tip_shift = Vector((0.20, -0.16, 0)) * radius
    bm = bmesh.new()
    loops = []
    for t, width in rings:
        if width == 0:
            loops.append([bm.verts.new(Vector((0, 0, height * t)) + tip_shift * (2 * t - 1))])
        else:
            loop = []
            for s in range(sides):
                angle = twist + math.tau * s / sides
                r = radius * width * profile[s]
                if t in (0.12, 0.88):
                    r *= rng.uniform(0.8, 1.2)
                z = height * (t + rng.uniform(-0.018, 0.018))
                loop.append(bm.verts.new(Vector((math.cos(angle) * r, math.sin(angle) * r, z))
                                         + tip_shift * ((t - 0.5) * 2) ** 3 * 0.6))
            loops.append(loop)
    for lower, upper in zip(loops, loops[1:]):
        for s in range(sides):
            n = (s + 1) % sides
            if len(lower) == 1:
                bm.faces.new((lower[0], upper[n], upper[s]))
            elif len(upper) == 1:
                bm.faces.new((lower[s], lower[n], upper[0]))
            else:
                bm.faces.new((lower[s], lower[n], upper[n], upper[s]))
    for point, normal in [((0, 0, height * 0.955), (0.6, -0.3, 1)),
                          ((0, 0, height * 0.025), (-0.4, 0.6, -1)),
                          ((radius * 0.87, 0, height * 0.52), (1, 0.3, 0.12)),
                          ((-radius * 0.88, 0, height * 0.68), (-1, 0.3, 0.17))]:
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                    plane_co=point, plane_no=Vector(normal).normalized(), clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=16, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("Seed planar facets")
    bm.to_mesh(mesh)
    bm.free()
    heat = mesh.attributes.new("core_distance", "FLOAT", "POINT")
    centre = Vector((0, 0, height * 0.5))
    for v, value in zip(mesh.vertices, heat.data):
        value.value = min(1, (v.co - centre).length / (height * 0.5))
    depth = mesh.attributes.new("mineral_depth", "FLOAT", "POINT")
    glow = mesh.attributes.new("core_glow", "FLOAT", "POINT")
    for vertex, value, light in zip(mesh.vertices, depth.data, glow.data):
        z = max(0, min(1, vertex.co.z / height))
        distance = min(1, (vertex.co - centre).length / (height * 0.5))
        growth = 0.04 * (1 - (z * 3) % 1)
        value.value = max(0, min(1, (0.68 - distance) / 0.4 - growth))
        central = max(0, 1 - abs(z - 0.5) / 0.22)
        light.value = central * max(0, min(1, (0.66 - distance) / 0.26)) ** 2
    mineral_attributes(mesh, radius, height, twist)
    obj = bpy.data.objects.new("Levitating violet seed", mesh)
    obj.data.materials.append(mat)
    obj.location = (0, 0, 4.55)
    bevel = obj.modifiers.new("Seed facet edges", "BEVEL")
    bevel.width, bevel.segments = 0.028, 2
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(12)
    return vrlib.link_to_source(obj)


def limestone_block(name, rng, size, location, rotation, mat):
    bm = bmesh.new()
    loops = []
    profile = [rng.uniform(0.8, 1.15) for _ in range(7)]
    for z, scale in [(-0.5, 0.95), (0.03, 1.05), (0.43, 0.74)]:
        loop = []
        for s in range(7):
            angle = math.tau * s / 7
            loop.append(bm.verts.new((math.cos(angle) * size[0] * 0.5 * scale * profile[s],
                                      math.sin(angle) * size[1] * 0.5 * scale * profile[s],
                                      (z + rng.uniform(-0.07, 0.07)) * size[2])))
        loops.append(loop)
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])
    for lower, upper in zip(loops, loops[1:]):
        for s in range(7):
            n = (s + 1) % 7
            bm.faces.new((lower[s], lower[n], upper[n], upper[s]))
    planes = [(Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 1)),
               Vector((0, 0, size[2] * rng.uniform(0.20, 0.38)))),
              (Vector((1, rng.uniform(-0.6, 0.6), rng.uniform(-0.3, 0.3))),
               Vector((size[0] * 0.36, 0, 0))),
              (Vector((-0.45, 1, 0.15)), Vector((0, size[1] * 0.36, 0))),
              (Vector((-1, -0.3, -0.08)), Vector((-size[0] * 0.42, 0, 0)))]
    for _ in range(2):
        corner = Vector(tuple(rng.choice((-1, 1)) * s * 0.5 for s in size))
        normal = Vector(tuple(math.copysign(rng.uniform(0.6, 1.2), c) for c in corner)).normalized()
        planes.append((normal, corner - normal * rng.uniform(0.15, 0.35)))
    for normal, point in planes:
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                    plane_co=point, plane_no=normal.normalized(), clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=10, use_grid_fill=True)
    bm.normal_update()
    for vertex in bm.verts:
        wear = noise.fractal(vertex.co * 2 + Vector(location), 1, 2, 3)
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
    obj.location, obj.rotation_euler = location, Euler(rotation)
    bevel = obj.modifiers.new("Limestone edge wear", "BEVEL")
    bevel.width, bevel.segments = 0.035, 2
    return vrlib.link_to_source(obj)


def mound(name, rng, radius, squash, location, mat):
    if name.startswith("Shared"):
        return ground_disc(name, radius, squash, location, mat)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=5, radius=radius)
    offset = Vector((rng.uniform(0, 20), rng.uniform(0, 20), rng.uniform(0, 20)))
    for v in bm.verts:
        v.co *= 1 + 0.11 * noise.fractal(v.co / radius * 3 + offset, 1, 2, 3)
        v.co.z *= squash
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for face in mesh.polygons:
        face.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    obj.location = location
    return vrlib.link_to_source(obj)


def ground_disc(name, radius, squash, location, mat):
    bm = bmesh.new()
    centre = bm.verts.new((0, 0, radius * squash))
    loops = []
    for t in (0.25, 0.5, 0.72, 0.88, 1.0):
        loop = []
        for i in range(64):
            angle = math.tau * i / 64
            edge = 1 + 0.07 * math.sin(angle * 3) + 0.055 * math.sin(angle * 7 + 1) + 0.025 * math.sin(angle * 17)
            r = radius * t * edge
            z = radius * squash * (1 - t * t) ** 2 - (location[2] + 0.055) * t ** 2
            loop.append(bm.verts.new((math.cos(angle) * r, math.sin(angle) * r, z)))
        loops.append(loop)
    for i in range(64):
        n = (i + 1) % 64
        bm.faces.new((centre, loops[0][i], loops[0][n]))
        for lower, upper in zip(loops, loops[1:]):
            bm.faces.new((lower[i], upper[i], upper[n], lower[n]))
    underside = bm.verts.new((0, 0, -location[2] - 0.055))
    for i in range(64):
        bm.faces.new((underside, loops[-1][(i + 1) % 64], loops[-1][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for face in mesh.polygons:
        face.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.data.materials.append(mat)
    return vrlib.link_to_source(obj)


def trim_ground():
    for obj in vrlib.source_objects():
        inv = obj.matrix_world.inverted()
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                    plane_co=inv @ Vector((0, 0, -0.055)),
                                    plane_no=obj.matrix_world.to_3x3().transposed() @ Vector((0, 0, 1)),
                                    clear_inner=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()


def energy_filaments(crystal, stones):
    material = vrmat.get("violet_energy").copy()
    material.name = "Seed | flowing energy filaments"
    palette = vrmat.load_palette()
    bsdf = material.node_tree.nodes["Principled BSDF"]
    for name in ("Base Color", "Emission Color", "Emission Strength", "Roughness"):
        for link in list(bsdf.inputs[name].links):
            material.node_tree.links.remove(link)
    body = palette["violet_body"]["linear_rgb"]
    glow = palette["violet_glow"]["linear_rgb"]
    bsdf.inputs["Base Color"].default_value = tuple(v * 0.35 for v in body) + (1,)
    bsdf.inputs["Emission Color"].default_value = tuple(0.9 * a + 0.1 * b for a, b in zip(body, glow)) + (1,)
    bsdf.inputs["Emission Strength"].default_value = 1.5
    bsdf.inputs["Roughness"].default_value = 0.5
    material["asset_tweaks"] = "palette violet body/glow mix; narrow tapered flowing filaments, emission 1.5"
    for i, stone in enumerate(sorted(stones, key=lambda obj: obj.name)):
        anchor = max((stone.matrix_world @ v.co for v in stone.data.vertices), key=lambda p: p.z)
        angle = math.atan2(anchor.y, anchor.x)
        points = [anchor - Vector((0, 0, 0.12))]
        for turn, radius, height in [(0.12, 4.1, 0.08), (0.55, 3.8, 0.3),
                                     (1.1, 3.25, 0.56), (1.65, 1.8, 0.82)]:
            points.append(crystal.location + Vector((math.cos(angle + turn) * radius,
                                                     math.sin(angle + turn) * radius, 14.75 * height)))
        curve = bpy.data.curves.new(f"filament_{i}", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 20
        curve.bevel_depth = 0.075
        curve.bevel_resolution = 3
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(len(points) - 1)
        for j, (point, position) in enumerate(zip(spline.bezier_points, points)):
            point.co = position
            point.handle_left_type = point.handle_right_type = "AUTO"
            point.radius = (0.55, 1.0, 0.85, 0.5, 0.04)[j]
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
    limestone = weathered_limestone("Fault | limestone")
    weather = weathered_limestone("Fault | sheltered stone")
    moss = moss_material()
    soil = vrmat.get("forest_soil").copy()
    earth = mound("Shared earth bed", rng, 7.4, 0.075, (0, 0, 0.12), soil)
    moss_tufts(earth, random.Random(SEED + 72), moss, 95, 7.1)

    stones = []
    for i in range(5):
        angle = math.tau * i / 5 + 0.3
        distance = 4.5 + rng.uniform(-0.2, 0.2)
        height = rng.uniform(4.6, 5.5)
        stones.append(((math.cos(angle) * distance, math.sin(angle) * distance, height * 0.43),
                       (rng.uniform(3.3, 4.2), rng.uniform(2.7, 3.4), height),
                       (0.12, -0.28, angle)))
    for i, (location, size, rotation) in enumerate(stones):
        limestone_block(f"Cradle stone {i}", rng, size, location, rotation,
                        weather if i == 3 else limestone)
        mound(f"Stone earth socket {i}", rng, 2.1, 0.16, (*location[:2], 0.30), soil)
        mound(f"Moss at cradle foot {i}", rng, 1.2, 0.30,
              (location[0] * 1.1, location[1] * 1.1, 0.28), moss)
        for j in range(3):
            angle = rng.uniform(0, math.tau)
            radius = rng.uniform(0.25, 0.65)
            mound(f"Limestone debris {i}_{j}", rng, radius, 0.65,
                  (location[0] + math.cos(angle) * 2.0, location[1] + math.sin(angle) * 2.0, 0.35 + radius * 0.3),
                  weather)
    crystal = seed(rng, seed_material())
    bpy.context.view_layer.update()
    stones = [obj for obj in vrlib.source_objects() if obj.name.startswith("Cradle stone")]
    _, tops = vrlib.world_bounds(stones)
    bottom, _ = vrlib.world_bounds([crystal])
    crystal.location.z += tops.z + 0.22 - bottom.z
    bpy.context.view_layer.update()
    energy_filaments(crystal, stones)
    trim_ground()
