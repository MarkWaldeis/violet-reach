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


def rock_material():
    mat = bpy.data.materials.new("vr_rock_mossy")
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    coords = N.new("ShaderNodeTexCoord")
    geo = N.new("ShaderNodeNewGeometry")
    palette = vrmat.load_palette()

    big = N.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 1.6
    big.inputs["Detail"].default_value = 9
    big.inputs["Roughness"].default_value = 0.62
    fine = N.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 22
    fine.inputs["Detail"].default_value = 8
    cracks = N.new("ShaderNodeTexVoronoi")
    cracks.feature = "DISTANCE_TO_EDGE"
    cracks.inputs["Scale"].default_value = 1.9
    cracks.inputs["Randomness"].default_value = 1.0
    for n in (big, fine):
        L.new(coords.outputs["Object"], n.inputs["Vector"])
    # Warp the crack pattern so it reads as natural fractures, not a honeycomb.
    warp = N.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 2.3
    warp.inputs["Detail"].default_value = 4
    L.new(coords.outputs["Object"], warp.inputs["Vector"])
    warped = N.new("ShaderNodeMixRGB")
    warped.inputs["Fac"].default_value = 0.22
    L.new(coords.outputs["Object"], warped.inputs["Color1"])
    L.new(warp.outputs["Color"], warped.inputs["Color2"])
    L.new(warped.outputs["Color"], cracks.inputs["Vector"])

    stone = N.new("ShaderNodeValToRGB")
    e = stone.color_ramp.elements
    e[0].position, e[0].color = 0.28, (*palette["monument_shadow"]["linear_rgb"], 1)
    e[1].position, e[1].color = 0.74, (*palette["stone_weathered"]["linear_rgb"], 1)
    mid = e.new(0.52)
    mid.color = (*palette["canyon_chalk"]["linear_rgb"], 1)
    L.new(big.outputs["Fac"], stone.inputs["Fac"])

    # Lighter wear on convex edges, darker in creases.
    wear = N.new("ShaderNodeValToRGB")
    wear.color_ramp.elements[0].position = 0.46
    wear.color_ramp.elements[1].position = 0.58
    L.new(geo.outputs["Pointiness"], wear.inputs["Fac"])
    worn = N.new("ShaderNodeMixRGB")
    worn.blend_type = "OVERLAY"
    worn.inputs["Fac"].default_value = 0.75
    L.new(stone.outputs["Color"], worn.inputs["Color1"])
    L.new(wear.outputs["Color"], worn.inputs["Color2"])

    crack_mask = N.new("ShaderNodeValToRGB")
    crack_mask.color_ramp.elements[0].position = 0.0
    crack_mask.color_ramp.elements[1].position = 0.014
    # Only keep cracks where the coarse noise is low, so they come and go.
    crack_fade = N.new("ShaderNodeMath")
    crack_fade.operation = "ADD"
    crack_gate = N.new("ShaderNodeMapRange")
    crack_gate.inputs["From Min"].default_value = 0.42
    crack_gate.inputs["From Max"].default_value = 0.56
    crack_gate.inputs["To Max"].default_value = 0.05
    L.new(big.outputs["Fac"], crack_gate.inputs["Value"])
    L.new(cracks.outputs["Distance"], crack_fade.inputs[0])
    L.new(crack_gate.outputs["Result"], crack_fade.inputs[1])
    L.new(crack_fade.outputs["Value"], crack_mask.inputs["Fac"])
    cracked = N.new("ShaderNodeMixRGB")
    cracked.blend_type = "MULTIPLY"
    cracked.inputs["Fac"].default_value = 0.65
    L.new(worn.outputs["Color"], cracked.inputs["Color1"])
    L.new(crack_mask.outputs["Color"], cracked.inputs["Color2"])

    # Moss on upward faces, broken up by noise.
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Normal"], sep.inputs["Vector"])
    moss_noise = N.new("ShaderNodeTexNoise")
    moss_noise.inputs["Scale"].default_value = 3.0
    moss_noise.inputs["Detail"].default_value = 6
    L.new(coords.outputs["Object"], moss_noise.inputs["Vector"])
    up = N.new("ShaderNodeMath")
    up.operation = "MULTIPLY"
    L.new(sep.outputs["Z"], up.inputs[0])
    L.new(moss_noise.outputs["Fac"], up.inputs[1])
    moss_mask = N.new("ShaderNodeValToRGB")
    moss_mask.color_ramp.elements[0].position = 0.36
    moss_mask.color_ramp.elements[1].position = 0.50
    L.new(up.outputs["Value"], moss_mask.inputs["Fac"])
    moss_col = N.new("ShaderNodeValToRGB")
    moss_col.color_ramp.elements[0].color = (*palette["moss"]["linear_rgb"], 1)
    moss_col.color_ramp.elements[1].color = (*palette["grass_green"]["linear_rgb"], 1)
    L.new(fine.outputs["Fac"], moss_col.inputs["Fac"])
    mossy = N.new("ShaderNodeMixRGB")
    L.new(moss_mask.outputs["Color"], mossy.inputs["Fac"])
    L.new(cracked.outputs["Color"], mossy.inputs["Color1"])
    L.new(moss_col.outputs["Color"], mossy.inputs["Color2"])

    L.new(mossy.outputs["Color"], bsdf.inputs["Base Color"])

    rough = N.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.72
    rough.inputs["To Max"].default_value = 0.96
    L.new(fine.outputs["Fac"], rough.inputs["Value"])
    L.new(rough.outputs["Result"], bsdf.inputs["Roughness"])

    bump_fine = N.new("ShaderNodeBump")
    bump_fine.inputs["Strength"].default_value = 0.35
    bump_fine.inputs["Distance"].default_value = 0.03
    L.new(fine.outputs["Fac"], bump_fine.inputs["Height"])
    bump_crack = N.new("ShaderNodeBump")
    bump_crack.inputs["Strength"].default_value = 0.9
    bump_crack.inputs["Distance"].default_value = 0.04
    L.new(crack_mask.outputs["Color"], bump_crack.inputs["Height"])
    L.new(bump_fine.outputs["Normal"], bump_crack.inputs["Normal"])
    L.new(bump_crack.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


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
    mat = rock_material()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    mossy = bsdf.inputs["Base Color"].links[0].from_node
    moss_colors = mossy.inputs["Color2"].links[0].from_node
    palette = vrmat.load_palette()
    for element, key in zip(moss_colors.color_ramp.elements, ("moss", "grass_green")):
        element.color = (*palette[key]["linear_rgb"], 1)
    stone = next(node for node in nodes if node.type == "VALTORGB"
                 and abs(node.color_ramp.elements[0].position - 0.28) < 0.001)
    low = palette["soil" if earth else "monument_shadow"]["linear_rgb"]
    high = palette["grass_green" if earth else "stone_weathered"]["linear_rgb"]
    for element, factor in zip(stone.color_ramp.elements, (0, 0.5, 1)):
        element.color = tuple((1 - factor) * a + factor * b for a, b in zip(low, high)) + (1,)
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 8
    ao.inputs["Distance"].default_value = ao_distance
    grime = nodes.new("ShaderNodeMixRGB")
    grime.inputs[1].default_value = tuple(v * 0.45 for v in palette["soil"]["linear_rgb"]) + (1,)
    links.new(ao.outputs["AO"], grime.inputs[0])
    links.new(mossy.outputs[0], grime.inputs[2])
    links.new(grime.outputs[0], bsdf.inputs["Base Color"])
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


def radial_glow(crystal, radius, height):
    bm = bmesh.new()
    bm.from_mesh(crystal.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=14, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(crystal.data)
    bm.free()
    distance = crystal.data.attributes.new("core_distance", "FLOAT", "POINT")
    glow = crystal.data.attributes.new("core_glow", "FLOAT", "POINT")
    for vertex, d, g in zip(crystal.data.vertices, distance.data, glow.data):
        p = vertex.co - Vector((0, 0, height * 0.5))
        d.value = Vector((p.x / (radius * 1.15), p.y / (radius * 1.15),
                          p.z / (radius * 1.6))).length
        g.value = max(0, min(1, (1.1 - d.value) / 0.5)) ** 2
    mat = crystal.data.materials[0]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = "core_glow"
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 2
    gain.inputs[2].default_value = 0.025
    links.new(attribute.outputs["Fac"], gain.inputs[0])
    links.new(gain.outputs[0], nodes["Principled BSDF"].inputs["Emission Strength"])
    crystal["glow_radii"] = (radius * 1.15, radius * 1.15, radius * 1.6)
    crystal["glow_centre"] = (0, 0, height * 0.5)


def menhir(name, rng, size, location, angle, mat):
    section = [(0.5, -0.42), (0.5, -0.10), (0.5, 0), (0.5, 0.10),
               (0.5, 0.40), (-0.15, 0.5), (-0.5, 0.24), (-0.46, -0.4), (0.05, -0.5)]
    bm = bmesh.new()
    loops = []
    for z, scale in ((-0.5, 1.0), (0.02, 0.95), (0.5, 0.62)):
        loop = []
        for i, (x, y) in enumerate(section):
            top = z == 0.5
            height = z
            if top:
                height += (0.045 * math.sin(i * 1.7 + angle) if i not in (1, 2, 3) else 0)
                if i == 2:
                    height -= 0.16
            loop.append(bm.verts.new(((x * scale + (0.08 if top else 0)) * size[0],
                                      (y * scale - (0.04 if top else 0)) * size[1],
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
                          ((0.2, 1, 0.05), (0, size[1] * 0.42, 0))):
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                    plane_co=point, plane_no=Vector(normal).normalized(),
                                    clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=min(size) * 0.008, segments=1, affect="EDGES")
    bm.normal_update()
    sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle() > math.radians(32)]
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
    obj.rotation_euler = Euler((0.08, -0.18, angle))
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
    bsdf.inputs["Emission Strength"].default_value = 1.1
    bsdf.inputs["Roughness"].default_value = 0.45
    for i, stone in enumerate(stones):
        anchor = stone.matrix_world @ Vector(stone["socket_local"])
        angle = math.atan2(anchor.y, anchor.x)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        tangent = Vector((-math.sin(angle), math.cos(angle), 0))
        points = [anchor - Vector((0, 0, 0.08))]
        for outward, around, height in ((0.35, 0.5, 0.18), (0.15, 0.95, 0.55),
                                        (-0.65, 1.15, 0.85), (-1.25, 0.65, 1.3)):
            points.append(anchor + radial * outward + tangent * around + Vector((0, 0, height)))
        curve = bpy.data.curves.new(f"filament_{i}", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 20
        curve.bevel_depth = 0.09
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
    stones = []
    for i in range(5):
        angle = math.tau * i / 5 + 0.3
        distance = 4.4 + rng.uniform(-0.15, 0.15)
        height = rng.uniform(4.6, 5.1)
        location = (math.cos(angle) * distance, math.sin(angle) * distance, height * 0.43)
        stone = menhir(f"Cradle stone {i}", rng, (rng.uniform(3.3, 3.9), rng.uniform(2.7, 3.2), height),
                       location, angle, rock)
        stones.append(stone)
        socket = make_rock(f"Buried stone socket {i}", rng, 1.6, 0.13, 5, earth)
        socket.location = (*location[:2], 0.18)
    crystal = make_crystal("Levitating violet seed", rng, 3.0, 13.1, crystal_material())
    chip_tip(crystal, 13.1, 0.96)
    radial_glow(crystal, 3.0, 13.1)
    bpy.context.view_layer.update()
    _, tops = vrlib.world_bounds(stones)
    bottom, _ = vrlib.world_bounds([crystal])
    crystal.location.z += tops.z + 0.22 - bottom.z
    bpy.context.view_layer.update()
    energy_filaments(stones)
    finish()
