"""Violet crystal cluster on a mossy rock base. Units are metres, origin at ground centre, Z up."""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector, noise

import vrlib
import vrmat

SEED = 918643


def rock_material():
    mat = bpy.data.materials.new("vr_rock_mossy")
    mat.use_nodes = True
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    coords = N.new("ShaderNodeTexCoord")
    geo = N.new("ShaderNodeNewGeometry")

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
    e[0].position, e[0].color = 0.28, (0.18, 0.17, 0.14, 1)
    e[1].position, e[1].color = 0.74, (0.67, 0.64, 0.54, 1)
    mid = e.new(0.52)
    mid.color = (0.42, 0.40, 0.33, 1)
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
    moss_col.color_ramp.elements[0].color = (0.035, 0.085, 0.012, 1)
    moss_col.color_ramp.elements[1].color = (0.16, 0.26, 0.04, 1)
    L.new(fine.outputs["Fac"], moss_col.inputs["Fac"])
    mossy = N.new("ShaderNodeMixRGB")
    L.new(moss_mask.outputs["Color"], mossy.inputs["Fac"])
    L.new(cracked.outputs["Color"], mossy.inputs["Color1"])
    L.new(moss_col.outputs["Color"], mossy.inputs["Color2"])

    # Violet crystal dust close to the cluster centre.
    dist = N.new("ShaderNodeVectorMath")
    dist.operation = "LENGTH"
    L.new(geo.outputs["Position"], dist.inputs[0])
    dust_mask = N.new("ShaderNodeMapRange")
    dust_mask.inputs["From Min"].default_value = 0.5
    dust_mask.inputs["From Max"].default_value = 1.7
    dust_mask.inputs["To Min"].default_value = 0.55
    dust_mask.inputs["To Max"].default_value = 0.0
    L.new(dist.outputs["Value"], dust_mask.inputs["Value"])
    dusty = N.new("ShaderNodeMixRGB")
    dusty.inputs["Color2"].default_value = (0.20, 0.07, 0.36, 1)
    L.new(dust_mask.outputs["Result"], dusty.inputs["Fac"])
    L.new(mossy.outputs["Color"], dusty.inputs["Color1"])
    L.new(dusty.outputs["Color"], bsdf.inputs["Base Color"])

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


def make_crystal(name, rng, radius, height, mat, chip=None):
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
    if chip is not None:
        cut = bmesh.ops.bisect_plane(
            bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=(0, 0, height * chip),
            plane_no=Vector((0.32, -0.24, 1)).normalized(), clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        bmesh.ops.holes_fill(bm, edges=edges)
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


def build():
    rng = random.Random(SEED)
    rock = rock_material()
    limestone = vrmat.get("monument_weathered").copy()
    limestone.name = "Chalk limestone breaks"
    crystal = crystal_material()

    base = make_rock("rock_base", rng, 1.9, 0.25, 7, rock)
    base.location = (0, 0, 0.12)
    for i, (angle, dist, radius) in enumerate([(0.6, 1.35, 0.62), (2.7, 1.2, 0.78), (4.4, 1.3, 0.55), (5.5, 0.95, 0.5)]):
        lump = make_rock(f"rock_lump_{i}", rng, radius, rng.uniform(0.4, 0.6), 6, rock if i % 2 else limestone)
        lump.location = (math.cos(angle) * dist, math.sin(angle) * dist, radius * 0.16)
        lump.rotation_euler = Euler((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0, 6.28)))
    for i in range(9):
        angle, dist, radius = rng.uniform(0, math.tau), rng.uniform(1.5, 2.1), rng.uniform(0.09, 0.2)
        pebble = make_rock(f"rock_pebble_{i}", rng, radius, rng.uniform(0.55, 0.8), 4, rock)
        pebble.location = (math.cos(angle) * dist, math.sin(angle) * dist, radius * 0.25)

    main = make_crystal("crystal_main", rng, 0.43, 2.8, crystal, chip=0.95)
    place(main, rng, 2.2, 0.24, math.radians(12), 0.25)

    for i in range(5):
        angle = math.tau * i / 5 + rng.uniform(-0.25, 0.25)
        height = [1.25, 2.05, 1.65, 2.3, 1.1][i]
        chip = {0: 0.96, 1: 0.64, 3: 0.92}.get(i)
        c = make_crystal(f"crystal_mid_{i}", rng, height * rng.uniform(0.12, 0.16), height,
                         crystal, chip=chip)
        place(c, rng, angle, rng.uniform(0.55, 0.8), math.radians(rng.uniform(23, 42)), 0.28)

    for i in range(9):
        angle = rng.uniform(0, math.tau)
        height = rng.uniform(0.35, 0.95)
        c = make_crystal(f"crystal_small_{i}", rng, height * rng.uniform(0.14, 0.2), height, crystal)
        place(c, rng, angle, rng.uniform(0.75, 1.25), math.radians(rng.uniform(22, 58)), 0.22)

    # Broken shards lying on and around the base.
    for i in range(7):
        angle, dist = rng.uniform(0, math.tau), rng.uniform(1.35, 2.0)
        height = rng.uniform(0.18, 0.4)
        c = make_crystal(f"crystal_shard_{i}", rng, height * rng.uniform(0.16, 0.24), height, crystal)
        place(c, rng, angle, dist, math.radians(rng.uniform(70, 88)), rng.uniform(0.04, 0.09))

    bpy.context.view_layer.update()
    cut_below_ground()
