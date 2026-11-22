"""A ruptured limestone retaining wall with missing masonry and settled collapse debris."""

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from vrcolumn import limestone, limestone_library
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
    return limestone_library(prefix, base=1.18, runoff=(3.7, 6.2))


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
    if broken:
        for _ in range(rng.randint(2, 4)):
            sx, sy, sz = (rng.choice((-1, 1)) for _ in range(3))
            planes.append(
                (
                    (
                        sx * w * rng.uniform(0.68, 0.98),
                        sy * d * rng.uniform(0.78, 1.02),
                        sz * h * rng.uniform(0.63, 0.95),
                    ),
                    (
                        sx * rng.uniform(0.36, 1.1),
                        sy * rng.uniform(0.65, 1.48),
                        sz * rng.uniform(0.5, 1.44),
                    ),
                    True,
                )
            )
    for sz in (1, -1) if spalled else (1,):
        sx, sy = rng.choice((-1, 1)), rng.choice((-1, 1))
        planes.append(
            (
                (sx * w * rng.uniform(0.80, 0.96), sy * d * 0.93, sz * h * 0.87),
                (sx * 0.54, sy * 0.86, sz),
                True,
            )
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
    matrix = Euler((*tilt, azimuth)).to_matrix()
    for v in bm.verts:
        v.co = matrix @ v.co
    floor = min(v.co.z for v in bm.verts)
    dz = foot - floor if foot is not None else max(position[2], -0.048 - floor)
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
    round_arrises(obj, min(0.065, min(w, d, h) * 0.23))
    return obj


def round_arrises(obj, radius):
    bevel = obj.modifiers.new("Worn arrises", "BEVEL")
    bevel.width, bevel.segments = radius, 3
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(18)
    bevel.harden_normals = True
    weld = obj.modifiers.new("Remove coincident bevel vertices", "WELD")
    weld.merge_threshold = 0.00005
    normal = obj.modifiers.new("Preserve flats", "WEIGHTED_NORMAL")
    normal.keep_sharp = True


COURSES = (
    (-0.038, 0.81, ((-8.35, -1.66, 5), (-1.60, 0.49, 2), (0.97, 7.69, 5))),
    (0.81, 1.62, ((-8.03, -1.51, 5), (1.18, 7.31, 4))),
    (1.62, 2.68, ((-7.94, -2.10, 4), (2.44, 7.09, 4))),
    (2.68, 3.46, ((-8.06, -2.89, 4), (3.17, 6.91, 3))),
    (3.46, 4.31, ((-7.82, -3.00, 4), (3.60, 4.36, 1), (4.71, 6.87, 2))),
    (4.31, 4.90, ((-7.69, -3.82, 3), (5.39, 6.91, 1))),
    (4.90, 5.76, ((-7.55, -6.22, 1), (-5.74, -4.09, 2))),
    (5.76, 6.76, ((-7.34, -6.53, 1),)),
)


def stone_run(lo, hi, count, rng):
    step = (hi - lo) / count
    bounds = (
        [lo]
        + [lo + step * i + rng.uniform(-0.31, 0.31) * step for i in range(1, count)]
        + [hi]
    )
    return zip(bounds, bounds[1:])


def core_stone(x, y, z, radius, tone, rng):
    bm = bmesh.new()
    for latitude in (-0.67, 0.13, 0.69):
        phase = rng.uniform(0, math.tau)
        for k in range(5):
            azimuth = phase + (k + rng.uniform(-0.22, 0.22)) * math.tau / 5
            r = radius * math.sqrt(1 - latitude**2) * rng.uniform(0.71, 1.20)
            bm.verts.new(
                (
                    x + r * math.cos(azimuth),
                    y + r * math.sin(azimuth),
                    z + radius * (latitude + rng.uniform(-0.27, 0.27)),
                )
            )
    bmesh.ops.convex_hull(bm, input=list(bm.verts))
    bmesh.ops.delete(
        bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS"
    )
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    name = "Broken angular rubble set in lime mortar"
    data = bpy.data.meshes.new(name)
    bm.to_mesh(data)
    bm.free()
    data.materials.append(tone)
    obj = vrlib.link_to_source(bpy.data.objects.new(name, data))
    round_arrises(obj, radius * 0.075)


def broken_heart(a, b, bottom, top, face_y, tones, rng):
    centres = []
    for j in range(48):
        radius = rng.uniform(0.066, 0.28) * (1.44 if j < 5 else 1)
        x = rng.uniform(a + radius * 0.52, b - radius * 0.52)
        z = rng.uniform(bottom + 0.09, top - 0.06)
        if any(
            math.hypot(x - px, 1.16 * (z - pz)) < 0.73 * (radius + pr)
            for px, pz, pr in centres
        ):
            continue
        centres.append((x, z, radius))
        core_stone(
            x,
            face_y + rng.uniform(-0.095, 0.025),
            z,
            radius,
            tones[rng.choice((0, 3, 4, 7, 9))],
            rng,
        )


def remnant(tones, mortar, fracture, rng):
    bed_rng = random.Random(410238)
    for row, (bottom, top, runs) in enumerate(COURSES):
        height = top - bottom
        for run_index, (lo, hi, count) in enumerate(runs):
            drive = 0.032 * row
            # Recessed bedding stays within each surviving run. It never bridges the breach.
            core_h = height + 0.018 if row < 5 else height * 0.67
            core_z = bottom + core_h / 2 - 0.009
            stone_block(
                "Rubble heart · lime-bound packing",
                (hi - lo - min(0.24, 0.46 * (hi - lo)), 1.58 - 2 * drive, core_h),
                ((lo + hi) / 2, -0.06, core_z),
                mortar,
                rng,
                broken=row >= 4,
                tilt=(0.02, -0.12 if row >= 4 else 0),
            )
            for side in (-1, 1):
                cuts = list(stone_run(lo, hi, count, rng))
                if row < 4:
                    for j, (a, b) in enumerate(cuts):
                        if j > 0:
                            stone_block(
                                "Recessed vertical lime joint",
                                (0.12, 0.30, height - 0.05),
                                (a, side * (0.79 - drive), bottom + height / 2),
                                mortar,
                                bed_rng,
                            )
                    stone_block(
                        "Recessed horizontal lime bed",
                        (hi - lo - 0.10, 0.28, 0.070),
                        ((lo + hi) / 2, side * (0.83 - drive), bottom + 0.025),
                        mortar,
                        bed_rng,
                        tilt=(0.015, -0.011 if row > 0 else 0),
                    )
                for j, (a, b) in enumerate(cuts):
                    edge = (j == len(cuts) - 1 and hi < 0) or (j == 0 and lo > 0)
                    crown = row >= 6 or (row >= 3 and lo > 0)
                    front = side > 0
                    width = b - a - 0.041
                    y = side * (0.76 - drive) + rng.uniform(-0.064, 0.054)
                    if front and (
                        (row == 4 and run_index == 0 and j == 2)
                        or (row == 3 and run_index == 1 and j == 0)
                        or (row == 2 and run_index == 0 and edge)
                    ):
                        broken_heart(
                            a - 0.03, b + 0.04, bottom, top, 0.76, tones, bed_rng
                        )
                        continue
                    if (
                        crown
                        and row in (4, 5, 6)
                        and (j + row + (side == 1)) % 4 == 0
                        and count > 1
                    ):
                        continue
                    if row == 0:
                        y += side * 0.11
                    if crown or edge:
                        y += side * rng.uniform(-0.17, 0.26)
                    depth = rng.uniform(0.63, 0.83)
                    if edge and row > 0:
                        depth = rng.uniform(0.69, 0.88)
                    shift = rng.uniform(-0.028, 0.028)
                    if edge and row in (2, 4, 6):
                        shift += (-0.07 if lo > 0 else 0.07) * rng.random()
                    x = (a + b) / 2 + shift
                    varied_h = height - rng.uniform(0.013, 0.031)
                    if crown:
                        varied_h *= rng.uniform(0.67, 1.02)
                        width *= rng.uniform(0.68, 1.12)
                        x += rng.uniform(-0.19, 0.19)
                    elif row >= 2 and (j + row + (side == 1)) % 3 == 0:
                        x += rng.uniform(-0.10, 0.10)
                        y += side * rng.uniform(-0.11, 0.10)
                    force = []
                    if edge:
                        sign = 1 if hi < 0 else -1
                        force.append(
                            (
                                (
                                    sign * width * rng.uniform(0.28, 0.45),
                                    side * depth * 0.26,
                                    varied_h * 0.22,
                                ),
                                (sign, side * 0.31, 0.40 + rng.random() * 0.79),
                                True,
                            )
                        )
                    if crown:
                        rise = rng.choice((-1, 1))
                        force.append(
                            (
                                (
                                    rise * width * 0.14,
                                    side * depth * 0.10,
                                    varied_h * rng.uniform(0.29, 0.46),
                                ),
                                (rise * 0.65, side * 0.40, 1),
                                True,
                            )
                        )
                    if row >= 2 and (crown or edge or (j + row) % 3 == 0):
                        sign = rng.choice((-1, 1))
                        force.append(
                            (
                                (
                                    sign * width * 0.35,
                                    side * depth * 0.28,
                                    varied_h * 0.18,
                                ),
                                (sign * 0.79, side * 0.52, rng.uniform(0.25, 1)),
                                True,
                            )
                        )
                    block_z = bottom + varied_h / 2 + rng.uniform(0.002, 0.014)
                    if row in (0, 1) and front and -4.9 < x < -2.6:
                        y += 0.075
                    if row == 2 and j == 1 and front:
                        for sign in (-1, 1):
                            stone_block(
                                "Dislocated half of fissured ashlar",
                                (width, depth, varied_h),
                                (x + sign * 0.017, y + sign * 0.042, block_z),
                                (tones[8], fracture),
                                rng,
                                fracture=[
                                    (
                                        (-sign * 0.020, 0, 0),
                                        (sign, sign * 0.24, sign * 0.55),
                                        True,
                                    )
                                ],
                                spalled=True,
                            )
                        continue
                    stone_block(
                        f"Ashlar · bed {row+1}, run {run_index+1}, face {side:+}, block {j+1}",
                        (width, depth, varied_h),
                        (x, y, block_z),
                        (rng.choice(tones), fracture),
                        rng,
                        azimuth=(
                            rng.uniform(-0.17, 0.17)
                            if crown
                            else rng.uniform(-0.09, 0.09)
                        ),
                        tilt=(
                            (
                                rng.uniform(-0.13, 0.13)
                                if crown
                                else rng.uniform(-0.025, 0.025)
                            ),
                            rng.uniform(-0.21, 0.21) if crown or edge else 0,
                        ),
                        broken=crown or edge or (row > 1 and (j + row) % 2 == 1),
                        fracture=force,
                        spalled=rng.random() < 0.42,
                    )
            if row >= 2 and (hi < 0 or lo > 0):
                x = hi - 0.18 if hi < 0 else lo + 0.14
                for j in range(3):
                    py = 0.34 - j * 0.42 + rng.uniform(-0.08, 0.08)
                    stone_block(
                        "Exposed split header",
                        (
                            rng.uniform(0.35, 0.66),
                            rng.uniform(0.32, 0.48),
                            height * 0.83,
                        ),
                        (x + rng.uniform(-0.11, 0.12), py, bottom + height * 0.40),
                        (rng.choice(tones), fracture),
                        rng,
                        tilt=(0.07, -0.09),
                        azimuth=rng.uniform(-0.3, 0.3),
                        broken=True,
                    )
    for x, y, z, w, d, h, az in (
        (-7.57, 0.44, 5.59, 1.38, 0.90, 1.06, -0.33),
        (-4.19, -0.25, 5.09, 1.04, 0.79, 0.91, 0.22),
        (5.89, 0.32, 4.63, 1.66, 0.91, 0.95, -0.16),
        (-2.09, 0.38, 1.39, 1.37, 0.85, 1.02, -0.16),
        (-1.27, 0.88, 0.48, 1.36, 1.02, 0.94, -0.29),
        (0.34, 0.44, 0.35, 0.99, 1.17, 0.66, 0.27),
        (1.66, -0.13, 1.40, 1.42, 0.82, 0.93, 0.12),
    ):
        stone_block(
            "Slipped or crushed course end",
            (w, d, h),
            (x, y, z),
            (rng.choice(tones), fracture),
            rng,
            azimuth=az,
            tilt=(0.07, rng.uniform(-0.17, 0.17)),
            broken=True,
        )


def fallen_masonry(tones, fracture, rng):
    # The collapse fans out from the central gap; sparse heavy stones carry farther.
    boulders = (
        (-2.55, 1.57, 1.54, 1.04, 0.84, -0.2),
        (-1.17, 1.81, 1.72, 1.17, 1.02, 0.36),
        (0.19, 1.47, 1.26, 0.84, 0.78, -0.29),
        (0.92, 2.44, 1.74, 1.21, 0.83, 0.58),
        (-2.84, 2.72, 1.19, 0.83, 0.69, 0.24),
        (-0.72, 3.39, 1.51, 0.77, 0.62, -0.43),
        (0.73, 3.92, 1.28, 0.81, 0.57, 0.71),
        (2.16, 3.13, 1.03, 0.79, 0.63, -0.61),
        (-3.99, 1.81, 0.97, 0.86, 0.63, 0.14),
        (-0.36, -1.95, 1.52, 0.96, 0.84, -0.21),
        (1.44, -1.60, 1.28, 0.90, 0.69, 0.41),
        (-2.14, -1.64, 1.68, 0.85, 0.85, 0.21),
        (-7.67, 1.86, 1.36, 1.04, 0.61, 0.33),
        (7.07, 0.96, 1.34, 1.19, 0.77, 0.21),
        (3.02, 1.91, 1.24, 0.64, 0.58, -0.33),
        (-1.79, 3.22, 1.63, 0.76, 0.25, 0.77),
        (1.58, 4.15, 1.39, 0.47, 0.29, -0.51),
        (0.55, -2.22, 1.46, 0.51, 0.32, 0.72),
    )
    for x, y, w, d, h, az in boulders:
        stone_block(
            "Fallen split ashlar",
            (w, d, h),
            (x, y, 0),
            (rng.choice(tones), fracture),
            rng,
            azimuth=az,
            tilt=(rng.uniform(-0.29, 0.29), rng.uniform(-0.28, 0.32)),
            broken=True,
            foot=-0.042,
        )
    for cx, cy, dx, dy, count in (
        (-0.89, 2.18, 0.91, 0.78, 33),
        (1.08, 3.08, 1.08, 0.74, 30),
        (-2.91, 3.22, 0.51, 0.59, 18),
        (-7.76, 1.62, 0.52, 0.40, 17),
        (0.02, -1.66, 1.31, 0.42, 31),
        (4.98, 1.36, 0.67, 0.53, 17),
    ):
        for _ in range(count):
            x, y = cx + rng.gauss(0, dx * 0.74), cy + rng.gauss(0, dy * 0.74)
            size = rng.uniform(0.088, 0.73) ** 1.36
            stone_block(
                "Limestone splinter",
                (
                    size * rng.uniform(1, 1.7),
                    size * rng.uniform(0.59, 1.2),
                    size * rng.uniform(0.30, 0.93),
                ),
                (x, y, 0),
                (rng.choice(tones), fracture),
                rng,
                azimuth=rng.uniform(-math.pi, math.pi),
                tilt=(rng.uniform(-0.35, 0.30), rng.uniform(-0.24, 0.44)),
                broken=True,
                foot=-0.021,
            )


def build():
    rng = random.Random(59187)
    tones = stone_library("Floodmark retaining wall")
    mortar = accent(
        "Wall · earth and aged lime bedding",
        "monument_weathered",
        "stone_weathered",
        0.52,
        0.88,
    )
    fracture = limestone(
        "Wall · exposed split beds", 0.90, 0.035, base=1.18, runoff=(3.7, 6.2)
    )
    ground = ground_materials("Floodmark collapse fan")
    remnant(tones, mortar, fracture, rng)
    fallen_masonry(tones, fracture, rng)
    for x, y, rx, ry, h, blades in (
        (-7.35, 1.04, 1.86, 0.86, 0.24, 130),
        (-5.3, 1.13, 1.36, 0.70, 0.18, 196),
        (-3.26, 1.05, 1.37, 1.21, 0.28, 185),
        (-1.9, 2.11, 1.23, 1.44, 0.43, 233),
        (-0.26, 1.53, 1.58, 1.07, 0.42, 240),
        (0.76, 3.15, 1.34, 1.67, 0.24, 217),
        (-2.16, 3.21, 1.31, 0.74, 0.16, 90),
        (2.62, 1.07, 1.69, 1.16, 0.34, 239),
        (5.51, 1.07, 1.63, 0.82, 0.28, 190),
        (6.77, 0.42, 0.93, 1.26, 0.23, 112),
        (-6.61, -1.05, 2.44, 0.82, 0.43, 170),
        (-3.79, -1.16, 1.30, 0.96, 0.32, 170),
        (-1.22, -1.11, 1.65, 1.18, 0.30, 217),
        (1.61, -1.20, 1.63, 0.77, 0.34, 216),
        (4.46, -1.10, 1.65, 0.78, 0.44, 206),
        (6.28, -0.92, 1.14, 0.89, 0.26, 175),
    ):
        turf(x, y, rx, ry, h, rng, ground, blades=blades)
    transform = Matrix.Rotation(math.radians(-59), 4, "Z")
    for obj in vrlib.source_objects():
        obj.data.transform(transform)
    fit_arrises()
