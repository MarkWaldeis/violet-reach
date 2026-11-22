"""Stonework profiles and solid fracture tools for the standing and fallen survey order."""

import math

import bmesh

import vrmat

FLUTE_DEPTH = 0.082
SHAFT_LEVELS = (1.82, 3.79, 5.92, 7.66, 9.91, 11.67, 13.71, 15.44)


def shaft_radius(z):
    t = (z - SHAFT_LEVELS[0]) / (SHAFT_LEVELS[-1] - SHAFT_LEVELS[0])
    return 1.65 - 0.24 * t + 0.093 * math.sin(math.pi * t)


def survey_drum(mesh, name, index, tone, rng):
    return drum(
        mesh,
        name,
        SHAFT_LEVELS[index] + 0.009,
        SHAFT_LEVELS[index + 1] - 0.009,
        shaft_radius,
        lambda z: min(1, (z - SHAFT_LEVELS[0]) / 0.23, (SHAFT_LEVELS[-1] - z) / 0.29),
        tone,
        rng,
    )


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


def limestone(name, value, warmth, *, base, runoff, flute_lichen=0.0):
    material = vrmat.get("monument_white").copy()
    material.name = name
    nodes, links = material.node_tree.nodes, material.node_tree.links
    surface = nodes["Principled BSDF"]
    palette = vrmat.load_palette()

    def rgb(key):
        return tuple(palette[key]["linear_rgb"])

    def gray(value):
        return (value,) * 3

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

    def noise(scale, vector, detail=2.0):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(signal, low, high):
        node = nodes.new("ShaderNodeMapRange")
        node.interpolation_type = "SMOOTHERSTEP"
        node.inputs["From Min"].default_value = low
        node.inputs["From Max"].default_value = high
        links.new(signal, node.inputs["Value"])
        return node.outputs[0]

    def mix(factor, a, b):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, (float, int)):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, value in zip(node.inputs[1:3], (a, b)):
            if isinstance(value, tuple):
                socket.default_value = (*value, 1)
            else:
                links.new(value, socket)
        return node.outputs[0]

    geometry = nodes.new("ShaderNodeNewGeometry")
    coord = geometry.outputs["Position"]
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord, xyz.inputs[0])
    z = xyz.outputs["Z"]
    normal = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Normal"], normal.inputs[0])

    ivory = tuple(
        c * value * k
        for c, k in zip(rgb("monument_white"), (1 + warmth, 1, 1 - warmth))
    )
    cool = tuple(c * k for c, k in zip(ivory, (0.94, 0.96, 1.02)))
    pale = tuple(c * k for c, k in zip(ivory, (1.07, 1.035, 0.98)))
    tone = mix(ramp(noise(0.87, coord, 3), 0.23, 0.79), cool, pale)
    random = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(0.24, tone, mix(random, cool, pale))

    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    ao.inputs["Distance"].default_value = 0.16
    channel = nodes.new("ShaderNodeAttribute")
    channel.attribute_name = "survey_recess"
    cavity = ramp(channel.outputs["Fac"], 0.17, 0.93)
    shadow = math_node("SUBTRACT", 1, ao.outputs["AO"])
    shade = math_node(
        "MAXIMUM",
        math_node("MULTIPLY", shadow, 0.72),
        math_node("MULTIPLY", cavity, 0.23),
    )
    joint = tuple(
        0.66 * a + 0.34 * b
        for a, b in zip(rgb("monument_shadow"), rgb("stone_weathered"))
    )
    tone = mix(shade, tone, joint)

    drift = math_node("MULTIPLY", math_node("SUBTRACT", noise(0.75, coord), 0.5), 0.27)
    damp = math_node("SUBTRACT", 1, ramp(math_node("ADD", z, drift), 0.03, base))
    mineral = tuple(
        0.44 * a + 0.56 * b
        for a, b in zip(rgb("stone_weathered"), (0.096, 0.058, 0.030))
    )
    tone = mix(math_node("MULTIPLY", damp, 0.74), tone, mineral)

    if runoff:
        stretch = nodes.new("ShaderNodeVectorMath")
        stretch.operation = "MULTIPLY"
        stretch.inputs[1].default_value = (5.2, 5.2, 0.22)
        links.new(coord, stretch.inputs[0])
        streaks = ramp(noise(1, stretch.outputs["Vector"], 3), 0.46, 0.69)
        below = ramp(z, *runoff)
        side = ramp(xyz.outputs["Y"], -0.25, 1.2)
        vertical = ramp(math_node("ABSOLUTE", normal.outputs["Z"], 0), 0.19, 0.68)
        mask = math_node(
            "MULTIPLY",
            below,
            math_node("MULTIPLY", side, math_node("SUBTRACT", 1, vertical)),
        )
        tone = mix(
            math_node("MULTIPLY", math_node("MULTIPLY", streaks, mask), 0.53),
            tone,
            mineral,
        )

    up = math_node("MULTIPLY", ramp(normal.outputs["Z"], 0.53, 0.94), 0.86)
    lower_flutes = math_node(
        "MULTIPLY", cavity, math_node("SUBTRACT", 1, ramp(z, 3.4, 5.5))
    )
    lower_face = math_node(
        "MAXIMUM", damp, math_node("MULTIPLY", lower_flutes, flute_lichen)
    )
    patch = ramp(noise(2.85, coord, 3), 0.54, 0.69)
    fleck = math_node(
        "ADD", 0.51, math_node("MULTIPLY", ramp(noise(21, coord), 0.25, 0.74), 0.49)
    )
    colonized = math_node(
        "MULTIPLY",
        math_node("MULTIPLY", math_node("MAXIMUM", up, lower_face), patch),
        fleck,
    )
    lichen = mix(
        ramp(noise(5.8, coord), 0.25, 0.7),
        rgb("moss"),
        tuple(0.73 * a + 0.27 * b for a, b in zip(rgb("moss"), rgb("stone_weathered"))),
    )
    links.new(mix(colonized, tone, lichen), surface.inputs["Base Color"])

    links.new(
        mix(ramp(noise(8, coord), 0.16, 0.86), gray(0.75), gray(0.93)),
        surface.inputs["Roughness"],
    )
    surface.inputs["Specular IOR Level"].default_value = 0.27
    bump = surface.inputs["Normal"].links[0].from_node
    bump.inputs["Distance"].default_value = 0.013
    bump.inputs["Strength"].default_value = 0.34
    return material


def limestone_library(prefix, **weather):
    beds = (
        (0.89, 0.020),
        (0.96, 0.035),
        (1.03, 0.024),
        (0.92, -0.042),
        (0.79, -0.054),
        (0.97, 0.066),
        (1.06, -0.026),
        (0.76, 0.046),
        (0.93, 0.043),
        (0.85, -0.028),
    )
    return [
        limestone(f"{prefix} · limestone bed {i:02}", *bed, **weather)
        for i, bed in enumerate(beds, 1)
    ]


def survey_base(moulding, blend_curve, tone):
    curve = blend_curve(
        (
            ((0.92, 2.09), (0.94, 2.16), (0.97, 2.19), (1.014, 2.19)),
            ((1.014, 2.19), (1.10, 2.19), (1.107, 2.37), (1.244, 2.37)),
            ((1.244, 2.37), (1.387, 2.37), (1.402, 2.05), (1.405, 2.021)),
            ((1.405, 2.021), (1.454, 1.86), (1.475, 1.84), (1.542, 1.837)),
            ((1.542, 1.837), (1.60, 1.834), (1.63, 1.918), (1.674, 1.918)),
            ((1.674, 1.918), (1.752, 1.918), (1.752, 1.70), (1.811, 1.68)),
            ((1.811, 1.68), (1.821, 1.677), (1.833, 1.644), (1.844, 1.643)),
        ),
        14,
    )
    return moulding("Attic footing · broad torus and scotia", curve, tone)


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
