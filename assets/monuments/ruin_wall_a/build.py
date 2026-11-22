"""A ruptured limestone retaining wall with missing masonry and settled collapse debris."""

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
import vrlib
import vrmat


def mesh(name, vertices, faces, materials=(), smooth=False, indices=()):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, data))
    for material in materials:
        data.materials.append(material)
    for i, poly in enumerate(data.polygons):
        poly.use_smooth = smooth is True or (smooth is not False and i in smooth)
    for poly, index in zip(data.polygons, indices):
        poly.material_index = index
    return obj


def limestone(name, tone, *, mortar=False, fracture=False, infill=False):
    material = vrmat.get("monument_white").copy()
    material.name = name
    nodes, links = material.node_tree.nodes, material.node_tree.links
    surface = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]
    weathered = palette["stone_weathered"]["linear_rgb"]
    shadow = palette["monument_shadow"]["linear_rgb"]
    soil = palette["soil"]["linear_rgb"]
    moss = tuple(palette["moss"]["linear_rgb"])
    coords = next(n for n in nodes if n.type == "TEX_COORD").outputs["Object"]

    def noise(scale, detail=2, vector=coords):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(source, low, high, a=(0, 0, 0), b=(1, 1, 1)):
        node = nodes.new("ShaderNodeValToRGB")
        node.color_ramp.interpolation = "EASE"
        for stop, pos, color in zip(node.color_ramp.elements, (low, high), (a, b)):
            stop.position, stop.color = pos, (*color, 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, a, b):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, float):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, val in zip(node.inputs[1:3], (a, b)):
            if isinstance(val, tuple):
                socket.default_value = (*val, 1)
            else:
                links.new(val, socket)
        return node.outputs["Color"]

    def attr(name):
        node = nodes.new("ShaderNodeAttribute")
        node.attribute_name = name
        return node.outputs["Fac"]

    if mortar:
        umber = tuple(0.19 * a + 0.64 * b for a, b in zip(shadow, soil))
        lime = tuple(0.24 * a + 0.64 * b for a, b in zip(weathered, soil))
        color = ramp(noise(6.8, 3), 0.21, 0.79, umber, lime)
    else:
        cool = tuple(c * t * k for c, t, k in zip(cream, tone, (0.88, 0.94, 1.065)))
        pale = tuple(c * t * k for c, t, k in zip(cream, tone, (1.035, 1.001, 0.945)))
        variation = ramp(noise(0.87, 3), 0.23, 0.79, cool, pale)
        random = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
        color = mix(0.27, variation, ramp(random, 0, 1, cool, pale))
        ao = nodes.new("ShaderNodeAmbientOcclusion")
        ao.samples = 4
        ao.inputs["Distance"].default_value = 0.19
        seam = tuple(0.44 * a + 0.56 * b for a, b in zip(shadow, (0.096, 0.058, 0.030)))
        color = mix(ao.outputs["AO"], seam, color)
        ochre = tuple(
            0.19 * a + 0.81 * b for a, b in zip(weathered, (0.096, 0.058, 0.030))
        )
        contact = ramp(noise(2.4), 0.23, 0.76, (0.48,) * 3, (0.98,) * 3)
        color = mix(attr("patina"), color, mix(contact, color, ochre))

        stretch = nodes.new("ShaderNodeVectorMath")
        stretch.operation = "MULTIPLY"
        stretch.inputs[1].default_value = (4.3, 4.3, 0.64)
        links.new(coords, stretch.inputs[0])
        runoff = ramp(
            noise(1, 3, stretch.outputs["Vector"]), 0.39, 0.68, (0,) * 3, (0.92,) * 3
        )
        rain = nodes.new("ShaderNodeMath")
        rain.operation = "MAXIMUM"
        rain.inputs[0].default_value = 0.16
        links.new(attr("coping_runoff"), rain.inputs[1])
        color = mix(rain.outputs[0], color, mix(runoff, color, ochre))
        geom = nodes.new("ShaderNodeNewGeometry")
        axis = nodes.new("ShaderNodeSeparateXYZ")
        links.new(geom.outputs["Normal"], axis.inputs[0])
        up = ramp(axis.outputs["Z"], 0.43, 0.95)
        colonies = ramp(noise(2.9, 3), 0.47, 0.68)
        lichen = tuple(0.67 * a + 0.33 * b for a, b in zip(moss, weathered))
        growth = mix(ramp(noise(25, 2), 0.28, 0.73), lichen, moss)
        color = mix(up, color, mix(colonies, color, growth))
        color = mix(attr("joint_growth"), color, mix(colonies, color, moss))

    links.new(color, surface.inputs["Base Color"])
    links.new(
        ramp(noise(8), 0.16, 0.86, (0.76,) * 3, (0.94,) * 3),
        surface.inputs["Roughness"],
    )
    surface.inputs["Specular IOR Level"].default_value = 0.27
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = (
        0.027 if fracture or mortar or infill else 0.017
    )
    bump.inputs["Strength"].default_value = (
        0.48 if fracture or mortar or infill else 0.32
    )
    links.new(noise(9 if fracture or mortar or infill else 13), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], surface.inputs["Normal"])
    return material


def accent(prefix, key, color_key, scale, blend):
    material = vrmat.get(key).copy()
    material.name = prefix
    tree = material.node_tree
    surface = tree.nodes["Principled BSDF"]
    rgb = vrmat.load_palette()[color_key]["linear_rgb"]
    mix = tree.nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = blend
    tree.links.new(surface.inputs["Base Color"].links[0].from_socket, mix.inputs[1])
    mix.inputs[2].default_value = (*(c * scale for c in rgb), 1)
    tree.links.new(mix.outputs[0], surface.inputs["Base Color"])
    surface.inputs["Specular IOR Level"].default_value = 0.22
    return material


def turf(cx, cy, rx, ry, height, rng, style, blades=130):
    """An uneven, buried edge and clumped blade geometry, not a raised disc."""
    soil, leaf, straw = style
    n, rows = 48, 12
    phase = rng.uniform(0, math.tau)

    def point(t, a):
        r = 1 + 0.13 * math.sin(3 * a + phase) + 0.07 * math.sin(5 * a - phase)
        x, y = cx + rx * t * r * math.cos(a), cy + ry * t * r * math.sin(a)
        relief = (1 - t * t) ** 1.6 * (
            0.75
            + 0.16 * math.cos(5 * t + 2 * a + phase)
            + 0.10 * math.sin(10 * t - 3 * a)
        )
        z = -0.047 + (height + 0.047) * relief
        return x, y, z

    vs = [(cx, cy, height * 0.79)]
    vs += [
        point(j / rows, math.tau * i / n) for j in range(1, rows + 1) for i in range(n)
    ]
    fs = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    for j in range(rows - 1):
        for i in range(n):
            a, b = j * n + i + 1, j * n + (i + 1) % n + 1
            fs.append((a, a + n, b + n, b))
    fs.append(tuple(range(rows * n, (rows - 1) * n, -1)))
    # A continuous shader blend conceals the soil/grass transition at the edge.
    ground = mesh("Turf over settled soil", vs, fs, (soil,), True)
    mask = ground.data.color_attributes.new(
        name="turf_cover", type="FLOAT_COLOR", domain="POINT"
    )
    for i, datum in enumerate(mask.data):
        t = 0 if i == 0 else ((i - 1) // n + 1) / rows
        x, y, _ = vs[i]
        w = max(
            0,
            min(
                1,
                1.32
                - 0.94 * t
                + 0.26 * math.sin(8 * x + 2 * y)
                + 0.28 * math.sin(5 * y - 3 * x),
            ),
        )
        datum.color = (w, w, w, 1)

    verts, faces, indices = [], [], []
    for _ in range(max(1, blades // 6)):
        a, t = rng.uniform(0, math.tau), rng.uniform(0.44, 0.93)
        for _ in range(rng.randint(5, 14)):
            x, y, z = point(
                min(0.96, max(0.05, t + rng.uniform(-0.11, 0.11))),
                a + rng.uniform(-0.19, 0.19),
            )
            if z < 0.005:
                continue
            direction = rng.uniform(0, math.tau)
            dx, dy = math.cos(direction), math.sin(direction)
            h = rng.uniform(0.10, 0.30) * min(1.36, 0.78 + height)
            lean, width = rng.uniform(0.20, 0.76) * h, rng.uniform(0.017, 0.044)
            p = len(verts)
            for f, s in ((0, 1), (0.36, 0.82), (0.72, 0.44)):
                verts.extend(
                    (
                        x + dx * lean * f * f + dy * width * s * k / 2,
                        y + dy * lean * f * f - dx * width * s * k / 2,
                        z - 0.008 + h * f,
                    )
                    for k in (-1, 1)
                )
            verts.append((x + dx * lean, y + dy * lean, z + h - 0.01))
            faces.extend(
                (
                    (p, p + 1, p + 3, p + 2),
                    (p + 2, p + 3, p + 5, p + 4),
                    (p + 4, p + 5, p + 6),
                )
            )
            indices.extend((int(rng.random() < 0.23),) * 3)
    if faces:
        mesh("Bent grass blades & dry tips", verts, faces, (leaf, straw), True, indices)


def ground_materials(prefix):
    soil = vrmat.get("forest_soil").copy()
    soil.name = prefix + " · earth and heather"
    tree = soil.node_tree
    surface = tree.nodes["Principled BSDF"]
    cover = tree.nodes.new("ShaderNodeVertexColor")
    cover.layer_name = "turf_cover"
    palette = vrmat.load_palette()
    # Keep exposed earth visible between olive and dry grass.
    mix = tree.nodes.new("ShaderNodeMixRGB")
    tree.links.new(cover.outputs["Color"], mix.inputs[0])
    tree.links.new(surface.inputs["Base Color"].links[0].from_socket, mix.inputs[1])
    moss, straw = (palette[k]["linear_rgb"] for k in ("grass_green", "grass_dry"))
    mix.inputs[2].default_value = (
        *(a * 0.69 + b * 0.22 for a, b in zip(moss, straw)),
        1,
    )
    tree.links.new(mix.outputs[0], surface.inputs["Base Color"])
    return (
        soil,
        accent(prefix + " · grass", "foliage_leaf", "grass_green", 1.02, 0.84),
        accent(prefix + " · dry grass", "foliage_leaf", "grass_dry", 1.22, 0.87),
    )


def fit_arrises():
    """Reduce the radius where a narrow fragment cannot take a full bevel."""
    pending = [
        (obj, mod)
        for obj in vrlib.source_objects()
        if (mod := obj.modifiers.get("Worn arrises")) is not None
    ]
    deps = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for _ in range(3):
        deps.update()
        failed = []
        for obj, bevel in pending:
            bm.from_mesh(obj.evaluated_get(deps).data)
            if not all(e.is_manifold for e in bm.edges) or not all(
                f.calc_area() > 1e-10 for f in bm.faces
            ):
                failed.append((obj, bevel))
            bm.clear()
        pending = failed
        if not pending:
            break
        for _, bevel in pending:
            bevel.width *= 0.44
    for obj, bevel in pending:
        obj.modifiers.remove(obj.modifiers["Remove coincident bevel vertices"])
        obj.modifiers.remove(bevel)
    bm.free()


def ashlar(
    name,
    bounds,
    rng,
    material,
    *,
    wear=0.025,
    chip=0.0,
    break_side=0,
    split=None,
    coping=None,
    yaw=0.0,
    tilt=(0.0, 0.0),
    ground=None,
    rubble=False,
):
    x0, x1, y0, y1, bottom, top = bounds
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (bottom + top) / 2
    w, d, h = (x1 - x0) / 2, (y1 - y0) / 2, (top - bottom) / 2
    wear = min(wear, w / 9, d / 9, h / 5)
    bevel_width = 0.51 * wear
    chamfer = min(wear * (3.1 if rubble else 1.9), h * 0.44)
    outline = (
        (-w + chamfer, -d),
        (w - chamfer, -d),
        (w, -d + chamfer),
        (w, d - chamfer),
        (w - chamfer, d),
        (-w + chamfer, d),
        (-w, d - chamfer),
        (-w, -d + chamfer),
    )
    corners = [
        (x + rng.uniform(-0.5, 0.5) * wear, y + rng.uniform(-0.5, 0.5) * wear)
        for x, y in outline
    ]
    notch = rng.randrange(8)
    n = len(corners)
    vertices = [(x, y, -h) for x, y in corners]
    vertices += [
        (
            x + rng.uniform(-0.31, 0.31) * wear - (0.065 * x if i == notch else 0),
            y + rng.uniform(-0.37, 0.37) * wear - (0.081 * y if i == notch else 0),
            h - (max(chip, min(0.080, wear * 1.26)) if i == notch else 0),
        )
        for i, (x, y) in enumerate(corners)
    ]
    faces = [tuple(reversed(range(n)))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    faces.append(tuple(range(n, 2 * n)))
    obj = mesh(name, vertices, faces, (material,))
    if break_side or chip > 0.055:
        if split != material:
            obj.data.materials.append(split)
        sign = break_side or rng.choice((-1, 1))
        edge = rng.uniform(0.40, 0.77)
        slope_y, slope_z = rng.uniform(-0.44, 0.44), rng.uniform(-0.62, 0.48)
        if abs(slope_z) < 0.25:
            slope_z = math.copysign(0.29, slope_z)
        front = rng.choice((-1, 1))
        cut = [
            ((sign * w * edge, 0, 0), (sign, slope_y, slope_z)),
            (
                (sign * w * (edge - 0.12), front * d * 0.71, h * 0.53),
                (sign * 0.69, front * 0.68, 0.74),
            ),
            (
                (sign * w * (edge - 0.042), -front * d * 0.78, -h * 0.62),
                (sign * 0.78, -front * 0.38, -0.61),
            ),
        ]
        if not break_side:
            front = -1 if notch in (0, 1, 2, 7) else 1
            cut = [
                (
                    (
                        sign * (w - chip * 0.58),
                        front * (d - chip * 0.28),
                        h - chip * 0.48,
                    ),
                    (sign * 0.74, front * 0.88, 1),
                ),
                (
                    (sign * (w - chip * 0.31), front * d, h - chip * 0.73),
                    (sign * 0.88, front * 0.93, 0.24),
                ),
            ]
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for point, normal in cut:
            result = bmesh.ops.bisect_plane(
                bm,
                geom=[*bm.verts, *bm.edges, *bm.faces],
                dist=0.00003,
                plane_co=point,
                plane_no=normal,
                clear_outer=True,
            )
            edge_ring = [
                e
                for e in result["geom_cut"]
                if isinstance(e, bmesh.types.BMEdge) and e.is_valid and e.is_boundary
            ]
            if edge_ring:
                for face in bmesh.ops.holes_fill(bm, edges=edge_ring, sides=0)["faces"]:
                    face.material_index = int(split != material)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()

    turn = Euler((*tilt, yaw)).to_matrix()
    transformed = [turn @ v.co for v in obj.data.vertices]
    low = min(v.z for v in transformed)
    cz = max(cz, -0.052 + bevel_width - low) if ground is None else ground - low
    for vert, point in zip(obj.data.vertices, transformed):
        vert.co = point + Vector((cx, cy, cz))
    obj.data.update()
    bevel = obj.modifiers.new("Worn arrises", "BEVEL")
    bevel.width, bevel.segments = bevel_width * (1.45 if rubble else 1), 3
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(20)
    bevel.harden_normals = True
    weld = obj.modifiers.new("Remove coincident bevel vertices", "WELD")
    weld.merge_threshold = 0.000035
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")
    patina = obj.data.attributes.new("patina", "FLOAT", "POINT")
    patina.data.foreach_set(
        "value",
        [
            max(
                0,
                min(
                    0.94,
                    (
                        2.02
                        + 0.32 * math.sin(1.9 * v.co.x)
                        + 0.19 * math.sin(3.4 * v.co.x + 2.1 * v.co.y)
                        - v.co.z
                    )
                    / 1.51,
                ),
            )
            for v in obj.data.vertices
        ],
    )
    joint = obj.data.attributes.new("joint_growth", "FLOAT", "POINT")
    joint.data.foreach_set(
        "value",
        [
            max(0, min(0.87, (1.25 - v.co.z) / 0.65))
            * max(0, 1 - abs(v.co.z - (cz - h)) / 0.24)
            for v in obj.data.vertices
        ],
    )
    if coping is not None:
        runoff = obj.data.attributes.new("coping_runoff", "FLOAT", "POINT")
        runoff.data.foreach_set(
            "value",
            [
                max(0, min(0.87, 0.87 - (coping - v.co.z) / 1.40))
                for v in obj.data.vertices
            ],
        )


LEVELS = (-0.035, 0.73, 1.59, 2.47, 3.29, 4.18, 4.95, 5.85, 6.68)
LEFT = (
    (-7.88, -0.62, 5),
    (-7.77, -0.94, 5),
    (-7.90, -1.44, 4),
    (-7.68, -2.30, 4),
    (-7.49, -3.02, 3),
    (-7.61, -3.86, 3),
    (-7.42, -4.45, 2),
    (-6.84, -5.68, 1),
)
RIGHT = (
    (0.76, 7.56, 5),
    (1.28, 7.70, 4),
    (2.30, 7.58, 4),
    (2.75, 7.43, 3),
    (3.98, 7.29, 2),
    (5.05, 6.22, 1),
)


def stone_cuts(lo, hi, count, rng):
    widths = [rng.uniform(0.76, 1.27) for _ in range(count)]
    scale = (hi - lo) / sum(widths)
    return [lo] + [lo + scale * sum(widths[: i + 1]) for i in range(count - 1)] + [hi]


def lime_matrix(lo, hi, base, top, y, side, mortar):
    rng = random.Random(repr((lo, hi, y, base)))
    nx, nz = max(3, math.ceil((hi - lo) / 0.13)), 7
    coords, faces = [], []
    stride = nx + 1
    jitter = min(0.043, 0.29 * (hi - lo) / nx)
    for j in range(nz + 1):
        v = j / nz
        for i in range(stride):
            u = i / nx
            x = lo + u * (hi - lo) + rng.uniform(-jitter, jitter)
            z = base - 0.019 + v * (top - base - 0.021) + rng.uniform(-0.043, 0.027)
            setback = 0.058 + rng.uniform(-0.061, 0.058)
            if i in (0, nx) or j in (0, nz):
                setback += rng.uniform(0.035, 0.105)
            coords.append((x, y - side * setback, max(-0.050, z)))
            if i and j:
                a = j * stride + i
                faces.extend(
                    ((a, a - 1, a - stride), (a - 1, a - stride - 1, a - stride))
                )

    border = list(range(stride))
    border += [j * stride + nx for j in range(1, nz + 1)]
    border += [nz * stride + i for i in range(nx - 1, -1, -1)]
    border += [j * stride for j in range(nz - 1, 0, -1)]
    back = len(coords)
    coords.extend((coords[i][0], y - side * 0.39, coords[i][2]) for i in border)
    for k, a in enumerate(border):
        j = (k + 1) % len(border)
        faces.append((a, border[j], back + j, back + k))
    faces.append(tuple(range(back, len(coords))))
    obj = mesh("Eroded lime matrix around chinking", coords, faces, (mortar,))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()


def expose_core(lo, hi, base, top, y, side, beds, mortar, rng):
    width = hi - lo
    course = top - base
    lime_matrix(lo, hi, base, top, y, side, mortar)
    for band in range(3):
        z = base + (band + rng.uniform(0.30, 0.58)) * course / 3
        count = max(2, round(width / rng.uniform(0.18, 0.34)))
        cuts = stone_cuts(lo, hi, count, rng)
        for a, b in zip(cuts, cuts[1:]):
            r = (b - a) * rng.uniform(0.29, 0.72)
            t = course * rng.uniform(0.053, 0.161)
            x = (a + b) / 2 + rng.uniform(-0.044, 0.044)
            stone_z = z + rng.uniform(-0.093, 0.091)
            depth = r * rng.uniform(0.68, 1.21)
            cy = y - side * (depth * 0.54 + rng.uniform(0.01, 0.056))
            bed = rng.choice(beds)
            ashlar(
                "Angular limestone chinking in lime mortar",
                (x - r, x + r, cy - depth, cy + depth, stone_z - t, stone_z + t),
                rng,
                bed,
                wear=rng.uniform(0.017, 0.044),
                chip=t * 0.18,
                break_side=rng.choice((-1, 0, 0, 1)),
                split=bed,
                yaw=rng.uniform(-0.75, 0.75),
                tilt=(rng.uniform(-0.49, 0.49), rng.uniform(-0.31, 0.31)),
                rubble=True,
            )


def make_remnant(runs, breach, beds, rubble, mortar, fracture, rng):
    front_rng = random.Random(rng.randrange(1 << 30))
    for row, (lo, hi, count) in enumerate(runs):
        bottom, top = LEVELS[row : row + 2]
        x0, x1 = lo + 0.066, hi - 0.066
        core_y = 0.565 if row == 0 else 0.505
        ashlar(
            "Continuous recessed lime and stone hearting",
            (x0, x1, -core_y, core_y, bottom, top - 0.075),
            rng,
            mortar,
            wear=0.026,
            chip=(top - bottom) * 0.18,
            break_side=breach if row else 0,
            split=mortar,
        )
        for side in (-1, 1):
            cuts = stone_cuts(lo, hi, count, rng)
            face_y = 0.84 if row == 0 else 0.75
            y0, y1 = sorted((side * 0.39, side * face_y))
            backing = side * (face_y - 0.074)
            m0, m1 = sorted((side * 0.36, backing))
            ashlar(
                "Recessed mortar bearing",
                (lo + 0.081, hi - 0.081, m0, m1, bottom - 0.033, bottom + 0.040),
                rng,
                mortar,
                wear=0.009,
            )
            exposed = (side == 1 and row in (2, 4)) or (side == -1 and row == 3)
            for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
                end = i == (len(cuts) - 2 if breach == 1 else 0)
                span = b - a
                if exposed and end:
                    pocket = rng.uniform(0.48, 0.67) * span
                    inner = b - pocket if breach == 1 else a + pocket
                    void = (inner, b) if breach == 1 else (a, inner)
                    expose_core(
                        void[0],
                        void[1],
                        bottom,
                        top,
                        side * (core_y - 0.035),
                        side,
                        rubble,
                        mortar,
                        front_rng,
                    )
                    a, b = (a, inner - 0.026) if breach == 1 else (inner + 0.026, b)

                lit = row >= len(runs) - 2 or end
                chipped = lit or rng.random() < 0.34
                chipped_side = breach if end and row >= 1 else 0
                if row >= len(runs) - 2 and not chipped_side and rng.random() < 0.50:
                    chipped_side = -breach
                bed_top = top - 0.028
                if row == len(runs) - 1:
                    bed_top -= rng.uniform(0.04, 0.23)
                if i != 0 and not (exposed and end and breach == -1):
                    ashlar(
                        "Recessed head joint",
                        (a - 0.055, a + 0.055, m0, m1, bottom + 0.002, top - 0.018),
                        rng,
                        mortar,
                        wear=0.009,
                    )
                ashlar(
                    "Chipped ashlar" if chipped_side else "Dressed ashlar",
                    (a + 0.022, b - 0.022, y0, y1, bottom + 0.028, bed_top),
                    rng,
                    rng.choice(beds),
                    wear=(
                        rng.uniform(0.026, 0.053)
                        if chipped
                        else rng.uniform(0.016, 0.029)
                    ),
                    chip=rng.uniform(0.074, 0.20) if chipped else 0,
                    break_side=chipped_side,
                    split=fracture,
                    coping=top if lit else None,
                    yaw=(
                        rng.uniform(-0.042, 0.042)
                        if row < 4
                        else rng.uniform(-0.17, 0.17)
                    ),
                    tilt=(
                        (rng.uniform(-0.032, 0.032), rng.uniform(-0.027, 0.027))
                        if row < 4
                        else (rng.uniform(-0.14, 0.14), rng.uniform(-0.13, 0.15))
                    ),
                )
            if row and (side == 1 or row == len(runs) - 1):
                edge = hi if breach == 1 else lo
                reach = front_rng.uniform(0.17, 0.42)
                expose_core(
                    edge - reach if breach == 1 else edge - 0.03,
                    edge + 0.03 if breach == 1 else edge + reach,
                    bottom,
                    top,
                    side * (core_y - 0.17),
                    side,
                    rubble,
                    mortar,
                    front_rng,
                )
        if row >= 4:
            lip = hi - 0.55 if breach == 1 else lo + 0.55
            for _ in range(5):
                x = lip + front_rng.uniform(-0.45, 0.45)
                y = front_rng.uniform(-0.37, 0.37)
                size = front_rng.uniform(0.13, 0.46)
                ashlar(
                    "Exposed crown rubble set in lime",
                    (
                        x - size / 2,
                        x + size / 2,
                        y - size * 0.46,
                        y + size * 0.46,
                        top - 0.36,
                        top - 0.36 + size,
                    ),
                    front_rng,
                    front_rng.choice(rubble),
                    wear=0.017,
                    break_side=breach,
                    split=rubble[0],
                    yaw=front_rng.uniform(-1, 1),
                    tilt=(front_rng.uniform(-0.3, 0.3), front_rng.uniform(-0.3, 0.3)),
                    rubble=True,
                )


def fallen_stone(label, x, y, w, d, h, rng, beds, fracture):
    ashlar(
        label,
        (x - w / 2, x + w / 2, y - d / 2, y + d / 2, -0.023, h - 0.023),
        rng,
        rng.choice(beds),
        wear=0.023,
        chip=h * rng.uniform(0.055, 0.17),
        break_side=rng.choice((-1, 1)),
        split=fracture,
        yaw=rng.uniform(-math.pi, math.pi),
        tilt=(rng.uniform(-0.30, 0.30), rng.uniform(-0.30, 0.30)),
        ground=-0.03,
    )


def build():
    rng = random.Random(247186)
    recipes = (
        (1.04, 1.01, 0.95),
        (0.80, 0.86, 0.94),
        (0.66, 0.61, 0.56),
        (0.95, 0.91, 0.86),
        (0.88, 0.92, 1.00),
        (1.01, 0.98, 0.91),
        (0.81, 0.65, 0.52),
    )
    beds = [
        limestone(f"Floodmark · ashlar bed {i}", value)
        for i, value in enumerate(recipes)
    ]
    mortar = limestone("Floodmark · recessed lime and grit", (1, 1, 1), mortar=True)
    fracture = limestone(
        "Floodmark · split ochre limestone", (0.71, 0.67, 0.58), fracture=True
    )
    rubble = [
        limestone(f"Floodmark · old core stone {i}", value, infill=True)
        for i, value in enumerate(
            ((0.46, 0.43, 0.36), (0.38, 0.39, 0.38), (0.56, 0.51, 0.43))
        )
    ]
    make_remnant(LEFT, 1, beds, rubble, mortar, fracture, rng)
    make_remnant(RIGHT, -1, beds, rubble, mortar, fracture, rng)
    for x, y, w, d, h in (
        (-2.85, 0.95, 1.32, 0.82, 0.61),
        (-1.93, 1.58, 1.62, 0.84, 0.65),
        (-0.34, 0.45, 1.70, 0.88, 0.69),
        (0.62, 0.93, 1.82, 1.05, 0.78),
        (-1.15, 2.57, 1.59, 0.98, 0.62),
        (0.22, 2.45, 1.35, 1.02, 0.51),
        (1.49, 1.72, 1.42, 0.91, 0.69),
        (2.65, 1.03, 1.27, 0.90, 0.67),
        (-0.87, -0.94, 1.25, 0.84, 0.64),
        (0.83, -1.28, 1.52, 0.83, 0.71),
        (-7.13, 0.88, 1.28, 0.74, 0.56),
        (5.91, 1.31, 1.19, 0.71, 0.56),
        (1.95, 2.98, 1.46, 0.79, 0.56),
        (-2.31, 3.36, 1.13, 0.88, 0.54),
        (-0.72, 3.92, 1.44, 0.76, 0.45),
        (0.96, 3.64, 0.99, 0.72, 0.48),
    ):
        fallen_stone("Displaced broken ashlar", x, y, w, d, h, rng, beds, fracture)
    for center, count in (
        ((-0.73, 2.70), 45),
        ((1.25, 1.75), 27),
        ((-5.2, 0.81), 18),
        ((5.65, 0.91), 18),
        ((0.5, -1.2), 17),
    ):
        for _ in range(count):
            x, y = (rng.gauss(c, sigma) for c, sigma in zip(center, (0.95, 0.55)))
            size = rng.uniform(0.13, 0.52)
            fallen_stone(
                "Weathered collapse scree",
                x,
                y,
                size,
                size * rng.uniform(0.63, 1.2),
                size * rng.uniform(0.46, 0.80),
                rng,
                beds,
                fracture,
            )

    ground = ground_materials("Floodmark collapse fan")
    for x, y, rx, ry, h, blades in (
        (-7.21, 0.77, 1.58, 0.78, 0.26, 146),
        (-5.21, 0.76, 1.65, 0.88, 0.29, 176),
        (-3.16, 0.93, 1.31, 1.19, 0.33, 139),
        (-2.41, 2.00, 1.32, 1.33, 0.32, 205),
        (-0.49, 2.42, 1.68, 1.32, 0.38, 231),
        (1.10, 2.96, 1.54, 1.35, 0.34, 177),
        (2.24, 0.85, 1.60, 1.06, 0.37, 186),
        (4.29, 0.88, 1.51, 0.77, 0.22, 142),
        (6.51, 0.88, 1.59, 0.73, 0.29, 135),
        (-6.1, -0.91, 2.16, 0.71, 0.33, 183),
        (-3.72, -1.02, 1.54, 1.05, 0.24, 144),
        (-1.29, -0.89, 1.49, 0.84, 0.41, 150),
        (1.20, -1.06, 1.50, 1.08, 0.43, 199),
        (3.74, -0.92, 1.59, 0.75, 0.31, 159),
        (6.08, -0.91, 2.16, 0.69, 0.30, 174),
    ):
        turf(x, y, rx, ry, h, rng, ground, blades=blades)
    transform = Matrix.Rotation(math.radians(-54), 4, "Z")
    for obj in vrlib.source_objects():
        obj.data.transform(transform)
    fit_arrises()
