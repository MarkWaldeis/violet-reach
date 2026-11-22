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

SEED = 918643


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
        base = tones(grain(0.87, 3), tuple(v * 0.55 for v in neutral),
                     tuple(v * 0.68 for v in neutral))
        geometry = nodes.new("ShaderNodeNewGeometry")
        up = nodes.new("ShaderNodeSeparateXYZ")
        links.new(geometry.outputs["Normal"], up.inputs[0])
        patch = nodes.new("ShaderNodeMapRange")
        patch.clamp = True
        patch.interpolation_type = "SMOOTHSTEP"
        patch.inputs["From Min"].default_value = 0.46
        patch.inputs["From Max"].default_value = 0.68
        links.new(grain(1.8, 5), patch.inputs["Value"])
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

def outcrop(rng, radius, mat):
    base = make_rock("Limestone fault", rng, radius, 0.38, 7, mat)
    base.location = (0, 0, 0.14)
    for i, (angle, distance, size) in enumerate(((0.6, 0.72, 0.39),
                                                (2.8, 0.68, 0.45),
                                                (4.2, 0.63, 0.33))):
        block = make_rock(f"Interlocked limestone {i}", rng, radius * size, 0.58, 6, mat)
        block.location = (math.cos(angle) * radius * distance,
                          math.sin(angle) * radius * distance, radius * size * 0.23)
        block.rotation_euler = Euler((0.12 * i, -0.09 * i, angle))



def build():
    rng = random.Random(SEED)
    outcrop(rng, 1.75, support_material("Mossy fractured limestone", 0.24))
    crystal = crystal_material()
    main = make_crystal("crystal_main", rng, 0.43, 2.8, crystal)
    chip_tip(main, 2.8, 0.93)
    place(main, rng, 2.2, 0.24, math.radians(12), 0.35)
    for i, height in enumerate((1.25, 1.65, 1.65, 2.3, 1.1)):
        angle = math.tau * i / 5 + rng.uniform(-0.25, 0.25)
        c = make_crystal(f"crystal_mid_{i}", rng, height * rng.uniform(0.105, 0.13), height, crystal)
        if i in (1, 3):
            chip_tip(c, height, 0.93)
        place(c, rng, angle, rng.uniform(0.48, 0.7), math.radians(rng.uniform(23, 42)), 0.32)
    for i in range(8):
        angle = rng.uniform(0, math.tau)
        height = rng.uniform(0.4, 0.95)
        c = make_crystal(f"crystal_small_{i}", rng, height * rng.uniform(0.14, 0.2), height, crystal)
        place(c, rng, angle, rng.uniform(0.65, 1.0), math.radians(rng.uniform(22, 45)), 0.30)
    finish()
