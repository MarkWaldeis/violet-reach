"""Survey Column: continuous-order limestone shaft, carved faults and a settled footing."""

import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector
from mathutils.geometry import delaunay_2d_cdt

from vrcolumn import (
    FLUTE_DEPTH,
    SHAFT_LEVELS,
    flute,
    fracture_planes,
    shaft_radius,
    survey_base,
    survey_capital,
    survey_drum,
)
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


def survey_limestone(name, value, *, torus=False):
    mat = vrmat.get("monument_white").copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = nodes["Principled BSDF"]
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]
    seam = palette["stone_weathered"]["linear_rgb"]
    shade = palette["monument_shadow"]["linear_rgb"]
    coords = next(n for n in nodes if n.type == "TEX_COORD").outputs["Object"]
    axes = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coords, axes.inputs[0])
    x, y, z = (axes.outputs[c] for c in "XYZ")

    def scalar(op, a, b=0.0):
        node = nodes.new("ShaderNodeMath")
        node.operation = op
        for socket, v in zip(node.inputs, (a, b)):
            if isinstance(v, (int, float)):
                socket.default_value = v
            else:
                links.new(v, socket)
        return node.outputs[0]

    def ramp(v, lo, hi, a=0.0, b=1.0):
        node = nodes.new("ShaderNodeMapRange")
        node.interpolation_type = "SMOOTHSTEP"
        for key, value in zip(
            ("From Min", "From Max", "To Min", "To Max"), (lo, hi, a, b)
        ):
            node.inputs[key].default_value = value
        links.new(v, node.inputs["Value"])
        return node.outputs[0]

    def noise(scale, detail, vector=coords):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def mix(factor, a, b):
        node = nodes.new("ShaderNodeMixRGB")
        if isinstance(factor, (float, int)):
            node.inputs[0].default_value = factor
        else:
            links.new(factor, node.inputs[0])
        for socket, val in zip(node.inputs[1:3], (a, b)):
            if isinstance(val, tuple):
                socket.default_value = (*val, 1)
            else:
                links.new(val, socket)
        return node.outputs["Color"]

    local_value = value * (0.73 if torus else 1.0)
    cool = tuple(c * k * local_value for c, k in zip(cream, (0.91, 0.95, 1.025)))
    pale = tuple(c * k * local_value for c, k in zip(cream, (1.035, 1.001, 0.945)))
    random_tone = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(
        0.18,
        mix(ramp(noise(0.87, 3), 0.23, 0.79), cool, pale),
        mix(random_tone, cool, pale),
    )
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    ao.inputs["Distance"].default_value = 0.16
    joints = tuple(0.72 * a + 0.28 * b for a, b in zip(shade, seam))
    tone = mix(ao.outputs["AO"], joints, tone)
    recess = nodes.new("ShaderNodeAttribute")
    recess.attribute_name = "survey_recess"
    channels = ramp(recess.outputs["Fac"], 0.15, 0.92)
    tone = mix(scalar("MULTIPLY", channels, 0.29), tone, joints)

    damp_height = scalar("ADD", z, scalar("MULTIPLY", noise(1.25, 2), 0.16))
    damp = ramp(damp_height, 0.18, 2.35, 0.83, 0)
    mineral = tuple(0.23 * a + 0.77 * b for a, b in zip(seam, (0.096, 0.058, 0.030)))
    tone = mix(damp, tone, mineral)

    direction = nodes.new("ShaderNodeVectorMath")
    direction.operation = "MULTIPLY"
    direction.inputs[1].default_value = (4.6, 4.6, 0.34 if torus else 0.102)
    links.new(coords, direction.inputs[0])
    streaks = ramp(noise(1, 3, direction.outputs["Vector"]), 0.47, 0.71)
    face = ramp(y, -0.52, 1.02, 0.63, 1.0)
    if torus:
        under = ramp(z, 1.12, 1.36, 0.70, 0)
    else:
        under_cap = ramp(z, 12.5, 16.3, 0, 0.92)
        under_torus = ramp(z, 0.12, 0.84, 0, 0.65)
        under = scalar("MAXIMUM", under_cap, under_torus)
    runoff = nodes.new("ShaderNodeMixRGB")
    runoff.blend_type = "MULTIPLY"
    runoff.inputs[2].default_value = (0.55, 0.49, 0.42, 1)
    links.new(
        scalar("MULTIPLY", streaks, scalar("MULTIPLY", under, face)), runoff.inputs[0]
    )
    links.new(tone, runoff.inputs[1])
    tone = runoff.outputs["Color"]

    if not torus:
        plinth_x = ramp(scalar("ABSOLUTE", x), 1.35, 2.17)
        plinth_y = ramp(scalar("ABSOLUTE", y), 1.35, 2.17)
        corners = scalar(
            "MULTIPLY", scalar("MINIMUM", plinth_x, plinth_y), ramp(z, 0.64, 1.12, 1, 0)
        )
        azimuth = scalar("ARCTAN2", y, x)
        flute_zone = ramp(scalar("COSINE", scalar("MULTIPLY", azimuth, 20)), 0.31, 0.92)
        shaft_zone = scalar("MULTIPLY", ramp(z, 1.76, 2.03), ramp(z, 4.6, 5.9, 1, 0))
        lower = scalar("MULTIPLY", flute_zone, shaft_zone)
        host = scalar("MAXIMUM", corners, lower)
        cluster = ramp(noise(2.77, 2), 0.515, 0.65)
        edges = ramp(noise(29.0, 2), 0.25, 0.71, 0.54, 0.96)
        growth = scalar("MULTIPLY", host, scalar("MULTIPLY", cluster, edges))
        moss = tuple(palette["moss"]["linear_rgb"])
        lichen = tuple(0.78 * a + 0.22 * b for a, b in zip(moss, seam))
        tone = mix(growth, tone, mix(ramp(noise(6.4, 1), 0.33, 0.67), moss, lichen))

    links.new(tone, surface.inputs["Base Color"])
    links.new(ramp(noise(8, 2), 0.16, 0.86, 0.76, 0.92), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = 0.27
    bump = surface.inputs["Normal"].links[0].from_node
    bump.inputs["Strength"].default_value = 0.23
    bump.inputs["Distance"].default_value = 0.008
    return mat


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


def turned(name, layers, radius, materials, n=480):
    vs, fs = [], []
    for j, level in enumerate(layers):
        for k in range(n):
            a = math.tau * k / n
            r = radius(j, a)
            vs.append((r * math.cos(a), r * math.sin(a), level))
    for j in range(len(layers) - 1):
        for k in range(n):
            p, q = j * n + k, j * n + (k + 1) % n
            fs.append((p, q, q + n, p + n))
    side_count = len(fs)
    fs.extend((tuple(reversed(range(n))), tuple(range(side_count, side_count + n))))
    return mesh(name, vs, fs, materials, range(side_count))


def moulding(name, profile, material, shaping=None, n=360):
    return turned(
        name,
        [z for z, _ in profile],
        lambda i, a: shaping(a, *profile[i]) if shaping else profile[i][1],
        (material,),
        n,
    )


def blend_curve(points, steps=12):
    """Piecewise cubic Beziers sampled with a common endpoint at each joint."""
    values = [points[0][0]]
    for p0, p1, p2, p3 in points:
        for j in range(1, steps + 1):
            t = j / steps
            s = 1 - t
            values.append(
                tuple(
                    a * s**3 + 3 * b * t * s * s + 3 * c * t * t * s + d * t**3
                    for a, b, c, d in zip(p0, p1, p2, p3)
                )
            )
    return values


def apply(obj, modifier):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def cut(obj, vertices, faces, material):
    cutter = mesh("Temporary fracture tool", vertices, faces)
    cutter.data.materials.append(material)
    if material.name not in obj.data.materials:
        obj.data.materials.append(material)
    mod = obj.modifiers.new("Subtracted stone", "BOOLEAN")
    mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cutter
    apply(obj, mod)
    bpy.data.objects.remove(cutter, do_unlink=True)


def fissure(obj, track, material):
    """An irregular V-section cutter. Track nodes specify angle, height, width and depth."""
    vertices = []
    for i, (a, h, width, depth) in enumerate(track):
        axis = Vector((math.cos(a), math.sin(a), 0))
        tangent = Vector((-math.sin(a), math.cos(a), 0))
        centre = axis * shaft_radius(h) + Vector((0, 0, h))
        prev, nxt = track[max(0, i - 1)], track[min(len(track) - 1, i + 1)]
        slant = Vector(
            ((nxt[0] - prev[0]) * shaft_radius(h), nxt[1] - prev[1])
        ).normalized()
        across = tangent * slant.y - Vector((0, 0, slant.x))
        vertices.extend(
            (
                centre + axis * 0.066 - across * width,
                centre + axis * 0.066 + across * width,
                centre - axis * depth + across * width * 0.17,
            )
        )
    faces = [(2, 1, 0)]
    for i in range(len(track) - 1):
        for k in range(3):
            p, q = 3 * i + k, 3 * i + (k + 1) % 3
            faces.append((p, q, q + 3, p + 3))
    top = len(vertices) - 3
    faces.append((top, top + 1, top + 2))
    cut(obj, vertices, faces, material)


def relief(bm, rng):
    """Sculpt the ledges and granular surface of a split limestone bed."""
    bm.normal_update()
    for face in list(bm.faces):
        if face.material_index != 1 or face.calc_area() < 0.067:
            continue
        normal = face.normal.copy()
        verts = list(face.verts)
        origin = face.calc_center_median()
        u = (verts[1].co - verts[0].co).normalized()
        v = normal.cross(u)
        points = [Vector((u.dot(p.co - origin), v.dot(p.co - origin))) for p in verts]
        boundary = len(points)
        lo, hi = ([fn(p[k] for p in points) for k in range(2)] for fn in (min, max))
        dx, dy = hi[0] - lo[0], hi[1] - lo[1]
        step = max(0.054, min(0.14, max(dx, dy) / 15))
        for i in range(int(dx / step)):
            for j in range(int(dy / step)):
                p = Vector(
                    (
                        lo[0] + (i + rng.uniform(0.17, 0.83)) * step,
                        lo[1] + (j + rng.uniform(0.17, 0.83)) * step,
                    )
                )
                if all(
                    (points[(k + 1) % boundary] - q).cross(p - q) > 0.011 * step
                    for k, q in enumerate(points[:boundary])
                ):
                    points.append(p)
        if len(points) == boundary:
            continue
        coords, _, pieces, ids, _, _ = delaunay_2d_cdt(
            points, [], [tuple(range(boundary))], 1, 1e-6
        )
        amount = min(0.048, 0.11 * min(dx, dy))
        phi = rng.uniform(0, math.tau)
        bmesh.ops.delete(bm, geom=[face], context="FACES_ONLY")
        corners = []
        for (x, y), source in zip(coords, ids):
            if source and source[0] < boundary:
                corners.append(verts[source[0]])
                continue
            edge = min(
                (points[(k + 1) % boundary] - p).cross(Vector((x, y)) - p)
                / (points[(k + 1) % boundary] - p).length
                for k, p in enumerate(points[:boundary])
            )
            fade = min(1, max(0, edge / (2 * step)))
            q = 1.61 * x + 2.38 * y
            gouge = (
                math.sin(6 * q + phi) * 0.42
                + 0.29 * math.sin(14 * q - 5 * x + phi)
                + 0.17 * math.cos(21 * x + 38 * y)
                + 0.12 * math.sin(46 * x - 41 * y)
            )
            corners.append(
                bm.verts.new(origin + u * x + v * y + normal * (amount * fade * gouge))
            )
        for ids in pieces:
            new = bm.faces.new([corners[i] for i in ids])
            new.material_index = 1


def stone_block(
    name,
    dims,
    position,
    material,
    rng,
    *,
    azimuth=0,
    tilt=(0, 0),
    broken=False,
    foot=None,
    fracture=None,
    spalled=False,
):
    """Clip a real solid with independent cut planes; retain broad dressed faces."""
    w, d, h = (v / 2 for v in dims)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= d
        v.co.z *= h
    planes = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            bevel = rng.uniform(0.035, 0.13) * min(w, d)
            planes.append(
                (
                    (sx * (w - bevel), sy * d, 0),
                    (sx * rng.uniform(0.66, 1.3), sy, 0),
                    False,
                )
            )
        for sz in (-1, 1):
            bevel = rng.uniform(0.027, 0.095) * min(w, h)
            planes.append(
                (
                    (sx * w, 0, sz * (h - bevel)),
                    (sx, 0, sz * rng.uniform(0.70, 1.3)),
                    False,
                )
            )
    for sy in (-1, 1):
        for sz in (-1, 1):
            bevel = rng.uniform(0.05, 0.12) * min(d, h)
            planes.append(
                (
                    (0, sy * d, sz * (h - bevel)),
                    (0, sy, sz * rng.uniform(0.7, 1.3)),
                    False,
                )
            )
    if broken:
        for _ in range(rng.randint(2, 4)):
            sx, sy, sz = (rng.choice((-1, 1)) for _ in range(3))
            planes.append(
                (
                    (
                        sx * w * rng.uniform(0.41, 0.87),
                        sy * d * rng.uniform(0.64, 1.02),
                        sz * h * rng.uniform(0.38, 0.87),
                    ),
                    (
                        sx * rng.uniform(0.36, 1.1),
                        sy * rng.uniform(0.65, 1.48),
                        sz * rng.uniform(0.5, 1.44),
                    ),
                    True,
                )
            )
    if spalled:
        sx, sy = rng.choice((-1, 1)), rng.choice((-1, 1))
        planes.append(
            ((sx * w * 0.21, sy * d * 0.92, h * 0.74), (sx * 0.19, sy * 0.72, 1), True)
        )
    if fracture:
        planes.extend(fracture)
    for point, normal, fresh in planes:
        out = bmesh.ops.bisect_plane(
            bm,
            geom=[*bm.verts, *bm.edges, *bm.faces],
            dist=0.00001,
            plane_co=point,
            plane_no=normal,
            clear_outer=True,
        )
        edges = [
            e
            for e in out["geom_cut"]
            if isinstance(e, bmesh.types.BMEdge) and e.is_valid and e.is_boundary
        ]
        if edges:
            result = bmesh.ops.holes_fill(bm, edges=edges, sides=0)
            for f in result["faces"]:
                f.material_index = int(fresh and isinstance(material, tuple))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if isinstance(material, tuple):
        relief(bm, random.Random(repr((dims, position))))
    matrix = Euler((*tilt, azimuth)).to_matrix()
    for v in bm.verts:
        v.co = matrix @ v.co
    dz = -min(v.co.z for v in bm.verts) + foot if foot is not None else position[2]
    for v in bm.verts:
        v.co += Vector((*position[:2], dz))
    data = bpy.data.meshes.new(name)
    bm.to_mesh(data)
    bm.free()
    data.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, data))
    for mat in material if isinstance(material, tuple) else (material,):
        data.materials.append(mat)
    for face in data.polygons:
        face.use_smooth = face.material_index == 0
    bevel = obj.modifiers.new("Worn arrises", "BEVEL")
    bevel.width = min(0.026, min(w, d, h) * 0.08)
    bevel.segments = 3
    bevel.angle_limit = 0.31
    weld = obj.modifiers.new("Remove coincident bevel vertices", "WELD")
    weld.merge_threshold = 0.00005
    normal = obj.modifiers.new("Preserve flats", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


def shaft(tones, mortar, fracture, rng):
    levels = SHAFT_LEVELS
    for index, (start, end) in enumerate(zip(levels, levels[1:])):
        lo, hi = start + 0.009, end - 0.009
        obj = survey_drum(
            mesh,
            f"Survey shaft · drum {index+1:02}",
            index,
            tones[[2, 0, 3, 1, 6, 2, 4][index]],
            rng,
        )
        if index == 1:
            fissure(
                obj,
                (
                    (0.47, 3.68, 0.044, 0.15),
                    (0.49, 3.96, 0.082, 0.22),
                    (0.52, 4.16, 0.060, 0.18),
                    (0.70, 4.30, 0.052, 0.17),
                    (0.71, 4.56, 0.026, 0.10),
                    (0.76, 4.78, 0.019, 0.057),
                    (0.77, 4.94, 0.008, 0.012),
                    (0.80, 5.06, 0.002, -0.026),
                ),
                fracture,
            )
        if index == 3:
            fissure(
                obj,
                (
                    (4.14, 9.99, 0.044, 0.22),
                    (4.13, 9.66, 0.049, 0.21),
                    (4.01, 9.42, 0.060, 0.21),
                    (3.96, 9.23, 0.053, 0.18),
                    (3.86, 8.93, 0.029, 0.13),
                    (3.83, 8.61, 0.018, 0.069),
                    (3.77, 8.45, 0.004, 0.012),
                    (3.73, 8.35, 0.002, -0.025),
                ),
                fracture,
            )
            bed_spall(obj, 4.11, hi, -1, fracture)
        if index == 4:
            fissure(
                obj,
                (
                    (1.02, 9.83, 0.064, 0.22),
                    (1.03, 10.20, 0.078, 0.24),
                    (1.14, 10.36, 0.069, 0.19),
                    (1.15, 10.59, 0.043, 0.16),
                    (1.28, 10.77, 0.032, 0.115),
                    (1.32, 10.99, 0.016, 0.051),
                    (1.41, 11.18, 0.002, -0.021),
                ),
                fracture,
            )
            bed_spall(obj, 1.03, lo, 1, fracture)

    for i, z in enumerate(levels[1:-1]):
        turned(
            f"Recessed lime bedding {i+1}",
            [z - 0.037, z + 0.037],
            lambda j, a: shaft_radius(z) - 0.029 - FLUTE_DEPTH * flute(a),
            (mortar,),
            n=480,
        )


def bed_spall(obj, angle, z, sign, fracture):
    radial = Vector((math.cos(angle), math.sin(angle), 0))
    along = Vector((-radial.y, radial.x, 0))
    centre = radial * shaft_radius(z) + Vector((0, 0, z))
    outline = (
        (-0.45, -0.15),
        (0.40, -0.15),
        (0.37, 0.19),
        (0.14, 0.27),
        (0.05, 0.39),
        (-0.12, 0.31),
        (-0.24, 0.12),
        (-0.46, 0.055),
    )
    vertices = [
        centre + 0.28 * radial + x * along + Vector((0, 0, sign * h))
        for x, h in outline
    ]
    vertices.append(
        centre - 0.32 * radial + 0.049 * along + Vector((0, 0, -sign * 0.096))
    )
    n = len(outline)
    faces = [tuple(range(n)), *[((i + 1) % n, i, n) for i in range(n)]]
    cut(
        obj,
        vertices,
        faces if sign > 0 else [tuple(reversed(f)) for f in faces],
        fracture,
    )


def footing(tones, mortar, fracture, rng):
    # Staggered foundation blocks, not a platform laid onto the surface.
    for j, (span, h, z) in enumerate(((4.90, 0.51, 0.23), (4.45, 0.47, 0.718))):
        for i, (x, y) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
            stagger = (0.21 if y == 1 else -0.16) * (-1 if j else 1)
            xc = stagger + x * (span / 4 - x * stagger / 2 + 0.008)
            dims = (span / 2 - x * stagger - 0.018, span / 2 - 0.018, h)
            stone_block(
                f"Footing course {j+1} · {i+1}",
                dims,
                (xc, y * (span / 4 + 0.008), z),
                (tones[(2 * i + 3 * j) % len(tones)], fracture),
                rng,
                spalled=(i + j) % 3 == 0,
            )
        stone_block(
            "Packed foundation bedding",
            (span - 0.08, span - 0.08, h + 0.028),
            (0, 0, z),
            mortar,
            rng,
        )
    survey_base(
        moulding,
        blend_curve,
        survey_limestone("Survey Column · damp torus", 0.97, torus=True),
    )


def capital(tones, fracture):
    _, _, abacus = survey_capital(moulding, blend_curve, tones)
    fracture_planes(
        abacus,
        [
            ((-1.90, 1.96, 17.82), (-0.75, 0.65, 0.32)),
            ((-2.01, 1.99, 17.88), (-0.95, 0.38, 0.59)),
        ],
        fracture,
    )


def build():
    rng = random.Random(483039)
    tones = [
        survey_limestone(f"Survey Column · bed {i:02}", value)
        for i, value in enumerate(
            (0.91, 0.97, 1.02, 0.94, 0.86, 1.0, 1.05, 0.83, 0.95, 0.88), 1
        )
    ]
    mortar = accent(
        "Compressed lime and grit", "monument_weathered", "stone_weathered", 0.32, 0.93
    )
    fracture = accent(
        "Old limestone fracture", "monument_white", "monument_white", 0.87, 0.61
    )
    footing(tones, mortar, fracture, rng)
    shaft(tones, mortar, fracture, rng)
    capital(tones, fracture)
    ground = ground_materials("Survey footing")
    skirts = (
        (-2.34, -1.54, 1.13, 1.05, 0.47, 206),
        (-0.81, -2.23, 1.34, 0.80, 0.22, 125),
        (1.44, -2.36, 1.28, 0.72, 0.30, 188),
        (2.38, -0.79, 0.90, 1.38, 0.29, 167),
        (2.18, 1.71, 1.06, 1.14, 0.38, 213),
        (0.52, 2.33, 1.07, 0.74, 0.22, 91),
        (-1.50, 2.28, 1.36, 0.68, 0.33, 165),
        (-2.39, 0.38, 0.79, 0.93, 0.29, 144),
    )
    for x, y, a, b, h, count in skirts:
        turf(x, y, a, b, h, rng, ground, blades=count)
    for cx, cy, count in (
        (-2.18, -2.55, 21),
        (2.56, -1.07, 12),
        (0.4, 2.68, 16),
        (-2.61, 1.0, 7),
    ):
        for _ in range(count):
            x, y = cx + rng.gauss(0, 0.36), cy + rng.gauss(0, 0.30)
            size = rng.uniform(0.075, 0.44) ** 1.18
            dims = (
                size * rng.uniform(1, 1.7),
                size * rng.uniform(0.58, 1.1),
                size * rng.uniform(0.33, 0.77),
            )
            stone_block(
                "Footing scree",
                dims,
                (x, y, 0),
                (rng.choice(tones), fracture),
                rng,
                azimuth=rng.uniform(-math.pi, math.pi),
                tilt=(0.18, 0.16),
                broken=True,
                foot=-0.025,
            )
