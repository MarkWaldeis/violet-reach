"""Double-terminated violet seed levitating over a fractured limestone cradle."""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector, noise

import vrlib
import vrmat

SEED = 840173


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
    mat["asset_tweaks"] = "geometry depth 0–1; sRGB 2A1450/3A1E6A/6D48AB/9C86D8; library body mix 0.12; body hue 0.53; glow hue 0.52; centre-only emission 0–1.8; normal tilt 0.12; texture scale 0.22"
    source = bsdf.inputs["Base Color"].links[0].from_socket
    depth = nodes.new("ShaderNodeAttribute")
    depth.attribute_name = "mineral_depth"
    def linear(hex_color):
        rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb) + (1,)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.name = "Geometry inner depth"
    ramp.color_ramp.elements[0].color = linear("2A1450")
    ramp.color_ramp.elements[1].color = linear("9C86D8")
    for position, color in [(0.28, "3A1E6A"), (0.58, "6D48AB")]:
        ramp.color_ramp.elements.new(position).color = linear(color)
    links.new(depth.outputs["Fac"], ramp.inputs[0])
    body = nodes.new("ShaderNodeMixRGB")
    body.inputs[0].default_value = 0.88
    links.new(source, body.inputs[1])
    links.new(ramp.outputs[0], body.inputs[2])
    tone = nodes.new("ShaderNodeHueSaturation")
    tone.inputs["Hue"].default_value = 0.53
    links.new(body.outputs[0], tone.inputs["Color"])
    links.new(tone.outputs[0], bsdf.inputs["Base Color"])
    heat = nodes.new("ShaderNodeAttribute")
    heat.attribute_name = "core_glow"
    glow = nodes.new("ShaderNodeValToRGB")
    glow.color_ramp.elements[0].color = linear("3A1E6A")
    glow.color_ramp.elements[1].color = linear("9C86D8")
    glow.color_ramp.elements.new(0.35).color = linear("6D48AB")
    links.new(heat.outputs["Fac"], glow.inputs[0])
    light_color = nodes.new("ShaderNodeHueSaturation")
    light_color.inputs["Hue"].default_value = 0.52
    links.new(glow.outputs[0], light_color.inputs["Color"])
    links.new(light_color.outputs[0], bsdf.inputs["Emission Color"])
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 1.8
    links.new(heat.outputs["Fac"], gain.inputs[0])
    links.new(gain.outputs[0], bsdf.inputs["Emission Strength"])
    return mat


def seed(rng, mat):
    radius, height = 3.45, 14.75
    sides = 8
    twist = 0.22
    profile = [rng.uniform(0.82, 1.18) for _ in range(sides)]
    rings = [(0.0, 0.0), (0.05, 0.20), (0.12, 0.52), (0.28, 0.98),
             (0.52, 1.06), (0.74, 0.90), (0.88, 0.46), (0.95, 0.20), (1.0, 0.0)]
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
    for point, normal in [((0, 0, height * 0.985), (0.6, -0.3, 1)),
                          ((0, 0, height * 0.012), (-0.4, 0.6, -1))]:
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
            edge = 1 + 0.07 * math.sin(angle * 3) + 0.035 * math.sin(angle * 7 + 1)
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


def build():
    rng = random.Random(SEED)
    limestone = vrmat.get("monument_weathered").copy()
    limestone.name = "Cradle | chalk limestone"
    weather = vrmat.get("monument_weathered").copy()
    weather.name = "Cradle | weathered breaks"
    for material in (limestone, weather):
        nodes, links = material.node_tree.nodes, material.node_tree.links
        bsdf = nodes["Principled BSDF"]
        source = bsdf.inputs["Base Color"].links[0].from_socket
        grain = nodes.new("ShaderNodeTexNoise")
        grain.inputs["Scale"].default_value = 2.5
        mask = nodes.new("ShaderNodeMapRange")
        mask.inputs["From Min"].default_value = 0.58
        mask.inputs["From Max"].default_value = 0.78
        mask.inputs["To Max"].default_value = 0.4
        links.new(grain.outputs["Fac"], mask.inputs["Value"])
        lichen = nodes.new("ShaderNodeMixRGB")
        lichen.inputs[2].default_value = (*vrmat.load_palette()["grass_dry"]["linear_rgb"], 1)
        links.new(mask.outputs[0], lichen.inputs[0])
        links.new(source, lichen.inputs[1])
        links.new(lichen.outputs[0], bsdf.inputs["Base Color"])
    moss = vrmat.get("mossy_rock").copy()
    soil = vrmat.get("forest_soil").copy()
    mound("Shared earth bed", rng, 7.4, 0.075, (0, 0, 0.12), soil)
    mound("Shared moss turf", rng, 6.8, 0.065, (0.08, 0.1, 0.26), moss)
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
    trim_ground()
