"""The survey column's torn footing, fallen shaft and chipped cushion capital."""

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

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


def stone_library(prefix):
    palette = vrmat.load_palette()
    cream, shade = (palette[k]["linear_rgb"] for k in ("monument_white", "stone_weathered"))
    tones = []
    for i, (value, warmth) in enumerate(
        (
            (0.89, 0.01),
            (0.94, 0.023),
            (1.02, 0.018),
            (0.97, -0.018),
            (0.88, -0.028),
            (0.92, 0.039),
            (1.035, -0.025),
            (0.83, 0.012),
            (0.97, 0.052),
            (0.91, -0.038),
        )
    ):
        material = vrmat.get("monument_white").copy()
        material.name = f"{prefix} · limestone bed {i+1:02}"
        tree = material.node_tree
        nodes, links = tree.nodes, tree.links
        surface = nodes["Principled BSDF"]
        prev = surface.inputs["Base Color"].links[0].from_socket
        tone = nodes.new("ShaderNodeMixRGB")
        tone.inputs[0].default_value = 0.60
        links.new(prev, tone.inputs[1])
        tone.inputs[2].default_value = (
            *[c * value * k for c, k in zip(cream, (1 + warmth, 1, 1 - warmth))],
            1,
        )
        coord = next(n for n in nodes if n.type == "TEX_COORD")
        weather = nodes.new("ShaderNodeTexNoise")
        links.new(coord.outputs["Object"], weather.inputs["Vector"])
        weather.inputs["Scale"].default_value = 3.1
        weather.inputs["Detail"].default_value = 4.0
        height = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coord.outputs["Object"], height.inputs[0])
        reach = nodes.new("ShaderNodeMath")
        reach.operation = "MULTIPLY_ADD"
        links.new(weather.outputs["Fac"], reach.inputs[0])
        reach.inputs[1].default_value = 1.17
        reach.inputs[2].default_value = -0.34
        depth = nodes.new("ShaderNodeMath")
        depth.operation = "SUBTRACT"
        depth.use_clamp = True
        links.new(reach.outputs[0], depth.inputs[0])
        links.new(height.outputs["Z"], depth.inputs[1])
        contact = nodes.new("ShaderNodeMixRGB")
        links.new(depth.outputs[0], contact.inputs[0])
        links.new(tone.outputs[0], contact.inputs[1])
        contact.inputs[2].default_value = (*[0.58 * a + 0.15 * b for a, b in zip(shade, cream)], 1)
        bands = nodes.new("ShaderNodeVectorMath")
        bands.operation = "MULTIPLY"
        bands.inputs[1].default_value = (2.1, 2.1, 17.0)
        links.new(coord.outputs["Object"], bands.inputs[0])
        beds = nodes.new("ShaderNodeTexNoise")
        beds.inputs["Scale"].default_value = 1.1
        beds.inputs["Detail"].default_value = 2.4
        links.new(bands.outputs[0], beds.inputs["Vector"])
        streak = nodes.new("ShaderNodeMixRGB")
        streak.inputs[1].default_value = (0.73, 0.69, 0.60, 1)
        streak.inputs[2].default_value = (1, 1, 1, 1)
        links.new(beds.outputs["Fac"], streak.inputs[0])
        calcite = nodes.new("ShaderNodeMixRGB")
        calcite.blend_type = "MULTIPLY"
        calcite.inputs[0].default_value = 0.34
        links.new(contact.outputs[0], calcite.inputs[1])
        links.new(streak.outputs[0], calcite.inputs[2])
        links.new(calcite.outputs[0], surface.inputs["Base Color"])
        surface.inputs["Specular IOR Level"].default_value = 0.24
        bump = surface.inputs["Normal"].links[0].from_node
        bump.inputs["Distance"].default_value = 0.006
        bump.inputs["Strength"].default_value = 0.30
        tones.append(material)
    return tones


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
            0.75 + 0.16 * math.cos(5 * t + 2 * a + phase) + 0.10 * math.sin(10 * t - 3 * a)
        )
        z = -0.047 + (height + 0.047) * relief
        return x, y, z

    vs = [(cx, cy, height * 0.79)]
    vs += [point(j / rows, math.tau * i / n) for j in range(1, rows + 1) for i in range(n)]
    fs = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    for j in range(rows - 1):
        for i in range(n):
            a, b = j * n + i + 1, j * n + (i + 1) % n + 1
            fs.append((a, a + n, b + n, b))
    fs.append(tuple(range(rows * n, (rows - 1) * n, -1)))
    # A continuous shader blend conceals the soil/grass transition at the edge.
    ground = mesh("Turf over settled soil", vs, fs, (soil,), True)
    mask = ground.data.color_attributes.new(name="turf_cover", type="FLOAT_COLOR", domain="POINT")
    for i, datum in enumerate(mask.data):
        t = 0 if i == 0 else ((i - 1) // n + 1) / rows
        x, y, _ = vs[i]
        w = max(
            0, min(1, 1.32 - 0.94 * t + 0.26 * math.sin(8 * x + 2 * y) + 0.28 * math.sin(5 * y - 3 * x))
        )
        datum.color = (w, w, w, 1)

    verts, faces, indices = [], [], []
    for _ in range(max(1, blades // 6)):
        a, t = rng.uniform(0, math.tau), rng.uniform(0.44, 0.93)
        for _ in range(rng.randint(5, 14)):
            x, y, z = point(
                min(0.96, max(0.05, t + rng.uniform(-0.11, 0.11))), a + rng.uniform(-0.19, 0.19)
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
            faces.extend(((p, p + 1, p + 3, p + 2), (p + 2, p + 3, p + 5, p + 4), (p + 4, p + 5, p + 6)))
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
    mix.inputs[2].default_value = (*(a * 0.69 + b * 0.22 for a, b in zip(moss, straw)), 1)
    tree.links.new(mix.outputs[0], surface.inputs["Base Color"])
    return (
        soil,
        accent(prefix + " · grass", "foliage_leaf", "grass_green", 1.02, 0.84),
        accent(prefix + " · dry grass", "foliage_leaf", "grass_dry", 1.22, 0.87),
    )


def flute(a):
    # Same 20 shallow, smoothly filleted cuts on both standing and fallen shafts.
    u = abs(math.remainder(20 * a / math.tau, 1.0)) / 0.406
    return (1 - u * u) ** 3 if u < 1 else 0.0


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
        coords, _, pieces, ids, _, _ = delaunay_2d_cdt(points, [], [tuple(range(boundary))], 1, 1e-6)
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
            corners.append(bm.verts.new(origin + u * x + v * y + normal * (amount * fade * gouge)))
        for ids in pieces:
            new = bm.faces.new([corners[i] for i in ids])
            new.material_index = 1


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
            if not all(e.is_manifold for e in bm.edges) or not all(f.calc_area() > 1e-10 for f in bm.faces):
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
            planes.append(((sx * (w - bevel), sy * d, 0), (sx * rng.uniform(0.66, 1.3), sy, 0), False))
        for sz in (-1, 1):
            bevel = rng.uniform(0.027, 0.095) * min(w, h)
            planes.append(((sx * w, 0, sz * (h - bevel)), (sx, 0, sz * rng.uniform(0.70, 1.3)), False))
    for sy in (-1, 1):
        for sz in (-1, 1):
            bevel = rng.uniform(0.05, 0.12) * min(d, h)
            planes.append(((0, sy * d, sz * (h - bevel)), (0, sy, sz * rng.uniform(0.7, 1.3)), False))
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
        planes.append(((sx * w * 0.21, sy * d * 0.92, h * 0.74), (sx * 0.19, sy * 0.72, 1), True))
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
            e for e in out["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_valid and e.is_boundary
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
    bevel.angle_limit = 0.39
    weld = obj.modifiers.new("Remove coincident bevel vertices", "WELD")
    weld.merge_threshold = 0.00005
    normal = obj.modifiers.new("Preserve flats", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


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


def edge_spall(obj, a, z, radius, width, height, depth, material):
    """Tapered flake that takes an arris with it, rather than a line on the surface."""
    axis = Vector((math.cos(a), math.sin(a), 0))
    tangent = Vector((-math.sin(a), math.cos(a), 0))
    centre = axis * radius + Vector((0, 0, z))
    outline = (
        (-0.76, -0.27),
        (-0.2, -0.77),
        (0.43, -0.57),
        (0.86, -0.08),
        (0.57, 0.71),
        (-0.36, 0.69),
        (-0.92, 0.21),
    )
    vertices = [centre + axis * 0.38 + tangent * width * x + Vector((0, 0, height * y)) for x, y in outline]
    vertices.append(centre - axis * depth + Vector((0, 0, -0.081)))
    n = len(outline)
    faces = [tuple(range(n))]
    faces.extend(((i + 1) % n, i, n) for i in range(n))
    cut(obj, vertices, faces, material)


def seat(obj, x, y, twist, yaw, rise, foot):
    matrix = Matrix.Rotation(yaw, 3, "Z") @ Matrix.Rotation(rise, 3, "Y") @ Matrix.Rotation(twist, 3, "Z")
    points = [matrix @ v.co for v in obj.data.vertices]
    offset = Vector((x, y, foot - min(p.z for p in points)))
    for vert, point in zip(obj.data.vertices, points):
        vert.co = point + offset
    obj.data.update()


def broken_drum(name, r, depth, bed, gap, tilt, rng, tone, fracture, broken_foot=False):
    n = 480
    phase, phase2 = (rng.uniform(0, math.tau) for _ in range(2))
    layers = [0, 0.008, 0.019, 0.031] + [i / 27 for i in range(1, 27)] + [0.975, 0.988, 1]
    variants = (
        (rng.uniform(-0.39, 0.39), rng.uniform(-0.39, 0.39), 0.22),
        (rng.uniform(-0.37, 0.37), rng.uniform(-0.37, 0.37), 0.31),
    )
    drifts = [(math.cos(a), math.sin(a)) for a in (phase, phase + 1.36, phase - 1.08)]

    def fault(x, y, top):
        u = x / r
        v = y / r
        a, b, amplitude = variants[top]
        p, q, s = [u * c + v * d for c, d in drifts]
        angle = phase if top else phase2
        w = (
            0.11 * math.sin(13 * u + 5 * v + angle)
            + 0.052 * math.sin(28 * u - 21 * v + 2 * angle)
            + 0.027 * math.cos(48 * u + 37 * v)
        )
        jump = 0.45 * max(0, p + 0.29) - 0.52 * abs(q - 0.42) + 0.27 * abs(s + 0.08)
        return r * (a * u + b * v + amplitude * (jump + w))

    end_chips = [
        (rng.uniform(0, math.tau), rng.uniform(0.095, 0.23), rng.uniform(0.09, 0.22)) for _ in range(6)
    ]
    vs, fs = [], []
    for t in layers:
        for j in range(n):
            a = math.tau * j / n
            flare = gap if broken_foot else 0
            run = min(1, (t + 0.018) / 0.24) if broken_foot else 1
            lip = max(0, 1 - min(t, 1 - t) / 0.035)
            decay = sum(
                d * max(0, 1 - abs(math.remainder(a - c, math.tau)) / w) ** 2 for c, w, d in end_chips
            )
            radius = (
                r * (1 + tilt * (0.5 - t))
                - 0.074 * flute(a) * run
                - 0.013 * lip * lip
                + 0.006 * math.sin(11 * a + phase + 4 * t)
                - decay * max(0, 1 - (1 - t) / 0.16) ** 2
                + flare * max(0, 1 - t / 0.21) ** 2
            )
            x, y = radius * math.cos(a), radius * math.sin(a)
            z0 = depth * bed + (fault(x, y, 0) * 0.61 if not broken_foot else 0)
            z1 = depth * (bed + 1) + fault(x, y, 1)
            vs.append((x, y, (1 - t) * z0 + t * z1))
    side = (len(layers) - 1) * n
    for j in range(len(layers) - 1):
        for k in range(n):
            a, b = j * n + k, j * n + (k + 1) % n
            fs.append((a, b, b + n, a + n))
    smooth = range(len(fs))

    for first, top in ((0, False), (side, True)):
        if not top and broken_foot:
            fs.append(tuple(reversed(range(n))))
            continue
        points = [Vector(v[:2]) for v in vs[first : first + n]]
        grid = r / 9
        for i in range(-9, 10):
            for j in range(-9, 10):
                x = grid * (i + rng.uniform(-0.32, 0.32))
                y = grid * (j + rng.uniform(-0.32, 0.32))
                if math.hypot(x, y) < r * 0.82:
                    points.append(Vector((x, y)))
        xy, _, tris, ids, _, _ = delaunay_2d_cdt(points, [], [tuple(range(n))], 1, 1e-6)
        face_verts = []
        for (x, y), origin in zip(xy, ids):
            if origin and origin[0] < n:
                face_verts.append(first + origin[0])
            else:
                face_verts.append(len(vs))
                f = fault(x, y, top) * (1 if top else 0.61)
                vs.append((x, y, depth * (bed + top) + f))
        fs.extend(tuple(face_verts[i] for i in (face if top else reversed(face))) for face in tris)
    indices = [0] * len(smooth) + [int(i != 0 or not broken_foot) for i in range(len(fs) - len(smooth))]
    return mesh(name, vs, fs, (tone, fracture), smooth, indices)


def split_drum(obj, r, fracture):
    # A torn-off flank leaves one long, solid oblique fracture face.
    n, m = 26, 21
    vertices, sides = [], []
    rng = random.Random(681127)
    for j in range(m):
        for i in range(n):
            y = 4.2 * i / (n - 1) - 2.1
            z = 3.5 * j / (m - 1) - 1.74
            if i not in (0, n - 1) and j not in (0, m - 1):
                y += rng.uniform(-0.056, 0.056)
                z += rng.uniform(-0.059, 0.059)
            ridge = -0.30 * abs(0.59 * y - 0.55 * z + 0.19) + 0.28 * max(0, 0.42 * y + 0.72 * z + 0.12)
            fractured = (
                0.033 * math.sin(6.3 * y + 9.1 * z)
                + 0.016 * math.sin(14.8 * z - 11 * y)
                + rng.uniform(-0.007, 0.007)
            )
            vertices.append((-0.66 * r - 0.24 * z + 0.14 * y + ridge + fractured, y, z))
    for j in range(m - 1):
        for i in range(n - 1):
            a = j * n + i
            if rng.random() < 0.5:
                sides.extend(((a, a + 1, a + n + 1), (a, a + n + 1, a + n)))
            else:
                sides.extend(((a, a + 1, a + n), (a + 1, a + n + 1, a + n)))
    perimeter = (
        list(range(n))
        + [j * n + n - 1 for j in range(1, m)]
        + list(range((m - 1) * n + n - 2, (m - 1) * n - 1, -1))
        + [j * n for j in range(m - 2, 0, -1)]
    )
    k = len(vertices)
    vertices.extend((-3, *vertices[i][1:]) for i in perimeter)
    for j, i in enumerate(perimeter):
        l = (j + 1) % len(perimeter)
        sides.append((perimeter[l], i, k + j, k + l))
    sides.append(tuple(reversed(range(k, len(vertices)))))
    cut(obj, vertices, sides, fracture)


def capital(tones, fracture):
    profile = blend_curve(
        (
            ((-0.986, 1.403), (-0.95, 1.411), (-0.94, 1.455), (-0.88, 1.470)),
            ((-0.88, 1.470), (-0.82, 1.57), (-0.72, 1.60), (-0.65, 1.51)),
            ((-0.65, 1.51), (-0.59, 1.43), (-0.58, 1.43), (-0.51, 1.45)),
            ((-0.51, 1.45), (-0.36, 1.46), (-0.36, 1.565), (-0.23, 1.576)),
            ((-0.23, 1.576), (0.02, 1.61), (0.24, 1.91), (0.44, 1.98)),
            ((0.44, 1.98), (0.58, 2.01), (0.63, 2.02), (0.669, 2.02)),
            ((0.669, 2.02), (0.693, 2.03), (0.70, 2.16), (0.74, 2.18)),
            ((0.74, 2.18), (0.76, 2.185), (1.066, 2.185), (1.09, 2.178)),
            ((1.09, 2.178), (1.12, 2.17), (1.14, 2.13), (1.154, 2.113)),
        ),
        12,
    )

    def shape(a, z, r):
        t = min(1, max(0, (z + 0.31) / 1.05))
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        a0, b0 = max(ca, sa), min(ca, sa)
        base = r / a0
        if base * b0 > r - 0.24:
            proj = (r - 0.24) * (a0 + b0)
            base = proj + math.sqrt(max(0, proj * proj - 2 * (r - 0.24) ** 2 + 0.24**2))
        return r + (base - r) * t * t + 0.073 * math.sin(math.pi * t) ** 2 * math.cos(8 * a)

    obj = moulding(
        "Broken cushion capital · neck, echinus and squared abacus", profile, tones[2], shape, n=480
    )
    edge_spall(obj, 0.81, 0.98, 2.91, 0.91, 0.61, 0.70, fracture)
    edge_spall(obj, 2.39, 1.03, 2.87, 1.43, 1.02, 1.26, fracture)
    edge_spall(obj, 5.11, -0.81, 1.56, 0.43, 0.27, 0.38, fracture)
    return obj


def build():
    rng = random.Random(873321)
    tones = stone_library("Fallen Survey Line")
    fracture = accent("Limestone break plane", "monument_white", "monument_white", 0.747, 0.77)
    soil = ground_materials("Fallen Survey Line")
    stump = broken_drum(
        "Source stump · sheared just above the foot",
        1.66,
        1.29,
        0,
        0.22,
        0.04,
        rng,
        tones[5],
        fracture,
        broken_foot=True,
    )
    seat(stump, -6.91, 0.76, 0.29, -0.10, 0.052, -0.038)
    obj = broken_drum("Fall 01 · heavy lower shaft", 1.61, 2.24, -0.5, 0, 0.027, rng, tones[1], fracture)
    edge_spall(obj, 0.79, 0.99, 1.59, 0.27, 0.38, 0.28, fracture)
    seat(obj, -3.92, 0.12, 0.74, -0.06, 1.46, -0.044)
    obj = broken_drum(
        "Fall 02 · shaft with split flank", 1.53, 1.99, -0.5, 0, 0.03, rng, tones[3], fracture
    )
    split_drum(obj, 1.53, fracture)
    seat(obj, -1.04, -0.51, 0.42, 0.23, 1.53, -0.043)
    obj = broken_drum(
        "Fall 03 · upper shaft kicked sideways", 1.43, 1.78, -0.5, 0, 0.016, rng, tones[6], fracture
    )
    edge_spall(obj, 4.48, 0.74, 1.44, 0.30, 0.44, 0.32, fracture)
    seat(obj, 1.91, 0.51, -0.19, -0.23, 1.36, -0.037)
    seat(capital(tones, fracture), 4.96, -0.38, 0.24, -0.17, 1.36, -0.044)
    for x, y, w, d, h, az in (
        (-7.31, -1.76, 1.14, 0.71, 0.49, -0.29),
        (-5.46, 1.73, 1.47, 1.08, 0.81, -0.51),
        (-3.80, 2.12, 1.37, 0.91, 0.67, 0.62),
        (-2.87, -1.96, 1.49, 0.89, 0.62, 0.34),
        (-0.42, 1.52, 1.04, 0.85, 0.56, -0.28),
        (0.05, -2.38, 1.34, 0.83, 0.58, -0.56),
        (1.97, 2.08, 1.25, 0.86, 0.48, 0.21),
        (2.81, -1.74, 1.47, 1.01, 0.67, 0.32),
        (3.93, 2.39, 1.06, 0.67, 0.48, 0.44),
        (5.55, 2.07, 1.39, 0.94, 0.69, -0.22),
        (6.70, -0.70, 1.40, 0.76, 0.60, 0.66),
        (-6.40, 0.64, 1.35, 1.14, 0.49, 0.22),
        (-0.75, 2.35, 0.81, 0.60, 0.41, -0.28),
        (6.28, -2.13, 1.03, 0.75, 0.39, -0.16),
    ):
        stone_block(
            "Scattered dressed beds & broken headers",
            (w, d, h),
            (x, y, 0),
            (rng.choice(tones), fracture),
            rng,
            azimuth=az,
            tilt=(rng.uniform(-0.31, 0.25), rng.uniform(-0.21, 0.40)),
            broken=True,
            spalled=True,
            foot=-0.038,
        )
    for x, y, rx, ry, h, blades in (
        (-6.9, -0.44, 1.57, 1.59, 0.49, 338),
        (-6.24, 1.94, 1.89, 1.05, 0.29, 246),
        (-4.16, 1.04, 1.94, 1.02, 0.49, 209),
        (-3.84, -1.02, 1.43, 0.91, 0.46, 236),
        (-1.62, -1.32, 1.81, 1.24, 0.39, 231),
        (-0.93, 0.78, 1.19, 1.23, 0.38, 250),
        (1.32, -0.32, 1.69, 1.08, 0.47, 215),
        (1.99, 1.43, 1.70, 1.29, 0.38, 200),
        (4.17, -1.39, 2.37, 0.98, 0.43, 244),
        (4.94, 1.37, 1.72, 1.23, 0.35, 225),
        (6.35, -0.53, 1.23, 1.43, 0.24, 121),
    ):
        turf(x, y, rx, ry, h, rng, soil, blades=blades)
    for cx, cy, n in (
        (-7.2, -1.0, 24),
        (-4.04, 1.81, 24),
        (-2.44, -1.51, 25),
        (0.94, 1.84, 19),
        (2.65, -1.16, 17),
        (4.64, 2.21, 23),
        (6.1, -1.22, 25),
    ):
        for _ in range(n):
            size = rng.uniform(0.092, 0.61) ** 1.45
            x, y = cx + rng.gauss(0, 0.58), cy + rng.gauss(0, 0.33)
            stone_block(
                "Graded limestone scree",
                (size * rng.uniform(1, 1.7), size * rng.uniform(0.63, 1.1), size * rng.uniform(0.45, 0.89)),
                (x, y, 0),
                (rng.choice(tones), fracture),
                rng,
                azimuth=rng.uniform(-math.pi, math.pi),
                tilt=(rng.uniform(-0.38, 0.38), rng.uniform(-0.38, 0.38)),
                broken=True,
                foot=-0.024,
            )
    transform = Matrix.Rotation(math.radians(-47), 4, "Z")
    for obj in vrlib.source_objects():
        obj.data.transform(transform)
    fit_arrises()
