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
    nodes.clear()
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    bsdf.inputs["IOR"].default_value = 1.6
    bsdf.inputs["Roughness"].default_value = 0.28
    bsdf.inputs["Coat Weight"].default_value = 0.08
    bsdf.inputs["Coat Roughness"].default_value = 0.12
    bsdf.inputs["Specular IOR Level"].default_value = 0.12
    heat = nodes.new("ShaderNodeAttribute")
    heat.attribute_name = "core_heat"
    body = nodes.new("ShaderNodeValToRGB")
    body.color_ramp.elements[0].color = (0.05, 0.004, 0.09, 1)
    body.color_ramp.elements[1].color = (0.11, 0.02, 0.27, 1)
    links.new(heat.outputs["Fac"], body.inputs["Fac"])
    links.new(body.outputs["Color"], bsdf.inputs["Base Color"])
    glow = nodes.new("ShaderNodeValToRGB")
    glow.color_ramp.elements[0].color = (0.045, 0.002, 0.08, 1)
    glow.color_ramp.elements[1].position = 0.55
    glow.color_ramp.elements[1].color = (0.40, 0.15, 0.85, 1)
    mid = glow.color_ramp.elements.new(0.25)
    mid.color = (0.20, 0.025, 0.48, 1)
    links.new(heat.outputs["Fac"], glow.inputs["Fac"])
    links.new(glow.outputs["Color"], bsdf.inputs["Emission Color"])
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.65
    gain.inputs[2].default_value = 0.12
    links.new(heat.outputs["Fac"], gain.inputs[0])
    links.new(gain.outputs[0], bsdf.inputs["Emission Strength"])
    return mat


def seed(rng, mat):
    radius, height = 3.45, 14.75
    sides = 6
    twist = 0.22
    profile = [rng.uniform(0.94, 1.06) for _ in range(sides)]
    rings = [(0.0, 0.0), (0.13, 0.48), (0.30, 1.0),
             (0.71, 0.96), (0.89, 0.48), (1.0, 0.0)]
    bm = bmesh.new()
    loops = []
    for t, width in rings:
        if width == 0:
            loops.append([bm.verts.new((0.18 * t, -0.12 * t, height * t))])
        else:
            loops.append([bm.verts.new((math.cos(twist + math.tau * s / sides) * radius * width * profile[s] + 0.18 * t,
                                        math.sin(twist + math.tau * s / sides) * radius * width * profile[s] - 0.12 * t,
                                        height * t)) for s in range(sides)])
    for lower, upper in zip(loops, loops[1:]):
        for s in range(sides):
            n = (s + 1) % sides
            if len(lower) == 1:
                bm.faces.new((lower[0], upper[n], upper[s]))
            elif len(upper) == 1:
                bm.faces.new((lower[s], lower[n], upper[0]))
            else:
                bm.faces.new((lower[s], lower[n], upper[n], upper[s]))
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=10, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("Seed planar facets")
    bm.to_mesh(mesh)
    bm.free()
    heat = mesh.attributes.new("core_heat", "FLOAT", "POINT")
    for v, value in zip(mesh.vertices, heat.data):
        t = v.co.z / height
        rho = Vector((v.co.x - 0.18 * t, v.co.y + 0.12 * t)).length / radius
        inward = max(0, min(1, (1 - rho) / 0.20))
        axial = math.sin(math.pi * t) ** 4
        value.value = inward ** 1.2 * axial
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
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector(tuple(a * b for a, b in zip(v.co, size)))
        v.co.x += v.co.z * rng.uniform(-0.18, 0.18)
        v.co.y += v.co.z * rng.uniform(-0.16, 0.16)
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
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    obj.location, obj.rotation_euler = location, Euler(rotation)
    bevel = obj.modifiers.new("Limestone edge wear", "BEVEL")
    bevel.width, bevel.segments = 0.035, 2
    return vrlib.link_to_source(obj)


def mound(name, rng, radius, squash, location, mat):
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
    limestone = vrmat.get("monument_white").copy()
    limestone.name = "Cradle | chalk limestone"
    weather = vrmat.get("monument_weathered").copy()
    weather.name = "Cradle | weathered breaks"
    moss = vrmat.get("mossy_rock").copy()
    soil = vrmat.get("forest_soil").copy()
    stones = [((-6.0, -4.6, 1.7), (6.3, 4.7, 4.9), (0.08, -0.18, -0.5)),
              ((5.4, -5.5, 1.75), (5.5, 5.0, 5.6), (-0.13, 0.12, 0.55)),
              ((5.6, 5.5, 1.9), (5.7, 5.0, 5.7), (0.10, 0.15, -0.35)),
              ((-5.5, 5.4, 1.6), (6.0, 5.2, 4.5), (-0.08, -0.14, 0.45))]
    for i, (location, size, rotation) in enumerate(stones):
        limestone_block(f"Cradle stone {i}", rng, size, location, rotation,
                        weather if i == 3 else limestone)
        mound(f"Stone earth socket {i}", rng, 3.15, 0.16, (*location[:2], 0.12), soil)
        mound(f"Moss at cradle foot {i}", rng, 1.2, 0.30,
              (location[0] * 1.1, location[1] * 1.1, 0.28), moss)
        for j in range(3):
            angle = rng.uniform(0, math.tau)
            radius = rng.uniform(0.25, 0.65)
            mound(f"Limestone debris {i}_{j}", rng, radius, 0.65,
                  (location[0] + math.cos(angle) * 3.2, location[1] + math.sin(angle) * 3.2, radius * 0.3),
                  weather)
    seed(rng, seed_material())
    bpy.context.view_layer.update()
    trim_ground()
