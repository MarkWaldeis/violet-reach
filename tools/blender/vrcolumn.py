"""Stonework profiles and solid fracture tools for the standing and fallen survey order."""

import math

import bmesh


FLUTE_DEPTH = 0.082


def flute(angle):
    u = abs(math.remainder(20 * angle / math.tau, 1.0)) / 0.474
    shoulder = 0.89
    if u <= shoulder:
        return 1 - u * u
    if u >= 1:
        return 0.0
    t = (u - shoulder) / (1 - shoulder)
    return (1 - t) ** 2 * (
        (1 + 2 * t) * (1 - shoulder**2) - 2 * shoulder * (1 - shoulder) * t
    )


def drum(mesh, name, lo, hi, radius_at, run_at, tone, rng):
    rings = [lo, lo + 0.005, lo + 0.014]
    rings += [lo + 0.027 + (hi - lo - 0.054) * i / 26 for i in range(27)]
    rings += [hi - 0.014, hi - 0.005, hi]
    phase, phase2 = (rng.uniform(0, math.tau) for _ in range(2))
    n = 640
    vertices, faces, recess = [], [], []
    for z in rings:
        t = (z - lo) / (hi - lo)
        lip = max(0, 1 - min(z - lo, hi - z) / 0.023)
        run = max(0, min(1, run_at(z)))
        for k in range(n):
            a = math.tau * k / n
            channel = flute(a) * run
            wear = math.sin(math.pi * t) ** 2 * (
                0.004 * math.sin(9 * a + phase)
                + 0.002 * math.sin(43 * a + phase2 + 6 * t)
            )
            radius = radius_at(z) - FLUTE_DEPTH * channel - 0.012 * lip**2 + wear
            vertices.append((radius * math.cos(a), radius * math.sin(a), z))
            side = 0.57 + 0.43 * math.cos(a - 0.55)
            recess.append(min(1, channel**2 * side + 0.67 * lip))
    for j in range(len(rings) - 1):
        for k in range(n):
            p, q = j * n + k, j * n + (k + 1) % n
            faces.append((p, q, q + n, p + n))
    smooth = range(len(faces))
    faces.extend(
        (tuple(reversed(range(n))), tuple(range(len(smooth), len(smooth) + n)))
    )
    obj = mesh(name, vertices, faces, (tone,), smooth)
    attr = obj.data.attributes.new("survey_recess", "FLOAT", "POINT")
    attr.data.foreach_set("value", recess)
    return obj


def fracture_planes(obj, planes, material):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if material.name not in obj.data.materials:
        obj.data.materials.append(material)
    material_index = obj.data.materials.find(material.name)
    for point, normal in planes:
        out = bmesh.ops.bisect_plane(
            bm,
            geom=[*bm.verts, *bm.edges, *bm.faces],
            dist=0.00001,
            plane_co=point,
            plane_no=normal,
            clear_outer=True,
        )
        edges = [
            edge
            for edge in out["geom_cut"]
            if isinstance(edge, bmesh.types.BMEdge)
            and edge.is_valid
            and edge.is_boundary
        ]
        if edges:
            for face in bmesh.ops.holes_fill(bm, edges=edges, sides=0)["faces"]:
                face.material_index = material_index
                face.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def weather_stone(tree, coord, color, palette, *, height, recess=0.0, exposed=0.0):
    nodes, links = tree.nodes, tree.links

    def math_node(operation, a, b, clamp=False):
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        node.use_clamp = clamp
        for i, value in enumerate((a, b)):
            if isinstance(value, (int, float)):
                node.inputs[i].default_value = value
            else:
                links.new(value, node.inputs[i])
        return node.outputs[0]

    def noise(scale, vector):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = 2.7
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def mix(factor, base, key, strength):
        node = nodes.new("ShaderNodeMixRGB")
        links.new(factor, node.inputs[0])
        links.new(base, node.inputs[1])
        node.inputs[2].default_value = (
            *[c * strength for c in palette[key]["linear_rgb"]],
            1,
        )
        return node.outputs[0]

    stretch = nodes.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (1.9, 1.9, 0.51)
    links.new(coord, stretch.inputs[0])
    run = noise(1.27, stretch.outputs["Vector"])
    fine = noise(9.0, coord)
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord, xyz.inputs[0])
    z = xyz.outputs["Z"]
    extent = math_node("MULTIPLY", math_node("SUBTRACT", run, 0.27), height * 1.75)
    contact = math_node("SUBTRACT", math_node("ADD", extent, 0.28), z, True)
    channel = nodes.new("ShaderNodeAttribute")
    channel.attribute_name = "survey_recess"
    sheltered = math_node("MULTIPLY", channel.outputs["Fac"], recess)
    patina = math_node("MAXIMUM", contact, sheltered)
    color = mix(math_node("MULTIPLY", patina, 0.80), color, "stone_weathered", 0.75)
    color = mix(math_node("MULTIPLY", contact, 0.33), color, "soil", 1.12)

    geometry = nodes.new("ShaderNodeNewGeometry")
    normal = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Normal"], normal.inputs[0])
    up = math_node(
        "MULTIPLY", math_node("SUBTRACT", normal.outputs["Z"], 0.34, True), exposed
    )
    wear = math_node("MAXIMUM", math_node("MULTIPLY", contact, 0.84), up, True)
    patches = math_node(
        "MULTIPLY", math_node("SUBTRACT", noise(1.82, coord), 0.485), 7, True
    )
    grain = math_node("MULTIPLY", math_node("SUBTRACT", fine, 0.20), 1.8, True)
    lichen = math_node("MULTIPLY", math_node("MULTIPLY", wear, patches), grain, True)
    return mix(lichen, color, "moss", 0.88)


def survey_capital(moulding, blend_curve, tones):
    collar = blend_curve(
        (
            ((15.408, 1.405), (15.46, 1.405), (15.46, 1.47), (15.50, 1.48)),
            ((15.50, 1.48), (15.54, 1.58), (15.64, 1.59), (15.69, 1.50)),
            ((15.69, 1.50), (15.753, 1.42), (15.82, 1.43), (15.98, 1.43)),
            ((15.98, 1.43), (16.06, 1.43), (16.04, 1.53), (16.12, 1.55)),
        )
    )
    neck = moulding("Capital · neck and astragal", collar, tones[0])
    cushion = blend_curve(
        (
            ((16.08, 1.48), (16.15, 1.48), (16.18, 1.48), (16.27, 1.51)),
            ((16.27, 1.51), (16.53, 1.53), (16.77, 1.92), (17.04, 1.98)),
            ((17.04, 1.98), (17.17, 2.01), (17.26, 2.02), (17.42, 2.02)),
        ),
        18,
    )

    def cushion_shape(a, z, r):
        t = min(1, max(0, (z - 16.21) / 1.16))
        square = (abs(math.cos(a)) ** 8 + abs(math.sin(a)) ** 8) ** (-0.125)
        # A subdued eight-lobed transition, carved into the mass of the echinus.
        petal = (
            0.084
            * math.sin(math.pi * t) ** 1.4
            * math.cos(8 * a + 0.6 * math.sin(math.pi * t))
        )
        return r * (1 + (square - 1) * t * t) + petal

    echinus = moulding(
        "Capital · lobed cushion echinus", cushion, tones[2], cushion_shape
    )
    abacus = blend_curve(
        (
            ((17.34, 2.008), (17.41, 2.008), (17.43, 2.13), (17.51, 2.145)),
            ((17.51, 2.145), (17.58, 2.151), (17.84, 2.184), (17.92, 2.184)),
            ((17.92, 2.184), (17.966, 2.184), (17.993, 2.157), (18, 2.124)),
        ),
        16,
    )

    def square(a, z, r):
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        big, small = max(ca, sa), min(ca, sa)
        flat = r / big
        if flat * small <= r - 0.22:
            return flat
        s = (r - 0.22) * (big + small)
        return s + math.sqrt(max(0, s * s - 2 * (r - 0.22) ** 2 + 0.22**2))

    top = moulding("Capital · solid square abacus", abacus, tones[1], square, n=480)
    return neck, echinus, top
