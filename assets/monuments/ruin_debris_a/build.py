"""The survey column's torn footing, fallen shaft and chipped cushion capital."""

import math
import random
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.geometry import delaunay_2d_cdt

from vrcolumn import SHAFT_LEVELS, fracture_planes, shaft_radius
import vrlib
import vrmat

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from assets.monuments.column_white_a import build as column


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
        relief = (1 - t * t) ** 1.35 * (
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


def relief(bm, rng, material_index=1):
    """Sculpt the ledges and granular surface of a split limestone bed."""
    bm.normal_update()
    for face in list(bm.faces):
        if face.material_index != material_index or face.calc_area() < 0.067:
            continue
        normal = face.normal.copy()
        verts = list(face.verts)
        origin = face.calc_center_median()
        u = (verts[1].co - verts[0].co).normalized()
        v = normal.cross(u)
        points = [Vector((u.dot(p.co - origin), v.dot(p.co - origin))) for p in verts]
        boundary = len(points)
        edges = list(zip(points, points[1:] + points[:1]))
        lo, hi = ([fn(p[k] for p in points) for k in range(2)] for fn in (min, max))
        dx, dy = hi[0] - lo[0], hi[1] - lo[1]
        step = max(0.054, min(0.14, max(dx, dy) / 15))

        def edge_distance(p):
            return min(
                (
                    p
                    - a
                    - (b - a)
                    * max(0, min(1, (p - a).dot(b - a) / (b - a).length_squared))
                ).length
                for a, b in edges
                if (b - a).length_squared > 1e-14
            )

        def inside(p):
            return (
                sum(
                    (a.y > p.y) != (b.y > p.y)
                    and p.x < a.x + (b.x - a.x) * (p.y - a.y) / (b.y - a.y)
                    for a, b in edges
                )
                % 2
            )

        for i in range(int(dx / step)):
            for j in range(int(dy / step)):
                p = Vector(
                    (
                        lo[0] + (i + rng.uniform(0.17, 0.83)) * step,
                        lo[1] + (j + rng.uniform(0.17, 0.83)) * step,
                    )
                )
                if inside(p) and edge_distance(p) > 0.043 * step:
                    points.append(p)
        if len(points) == boundary:
            continue
        coords, _, pieces, ids, _, _ = delaunay_2d_cdt(
            points, [], [tuple(range(boundary))], 1, 1e-6
        )
        amount = min(0.084, 0.12 * min(dx, dy))
        phi = rng.uniform(0, math.tau)
        bmesh.ops.delete(bm, geom=[face], context="FACES_ONLY")
        corners = []
        for (x, y), source in zip(coords, ids):
            if source and source[0] < boundary:
                corners.append(verts[source[0]])
                continue
            edge = edge_distance(Vector((x, y)))
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
            new.material_index = material_index


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
    bevel.angle_limit = 0.39
    weld = obj.modifiers.new("Remove coincident bevel vertices", "WELD")
    weld.merge_threshold = 0.00005
    normal = obj.modifiers.new("Preserve flats", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    return obj


def seat(parts, x, y, roll, bearing, fall, foot):
    rotation = (
        Matrix.Rotation(bearing, 4, "Z")
        @ Matrix.Rotation(fall, 4, "Y")
        @ Matrix.Rotation(roll, 4, "Z")
    )
    points = [rotation @ v.co for obj in parts for v in obj.data.vertices]
    lo, hi = ([fn(p[i] for p in points) for i in range(3)] for fn in (min, max))
    transform = (
        Matrix.Translation(
            (x - (lo[0] + hi[0]) / 2, y - (lo[1] + hi[1]) / 2, foot - lo[2])
        )
        @ rotation
    )
    for obj in parts:
        obj.matrix_world = transform


def split(obj, cuts, fracture, rng):
    fracture_planes(obj, cuts, fracture)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    relief(bm, rng, obj.data.materials.find(fracture.name))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def break_drum(obj, index, phase, slope, loss, rng, fracture, *, stump=False):
    bed, tip = SHAFT_LEVELS[index : index + 2]
    end = bed + 0.88 if stump else tip - loss
    r = shaft_radius(end)
    c, s = math.cos(phase), math.sin(phase)
    cuts = [
        ((0, 0, end), (slope * c, slope * s, 1)),
        (
            (0.83 * r * c, 0.83 * r * s, end - slope * r * 0.83 - 0.083),
            (0.71 * c, 0.71 * s, 1),
        ),
    ]
    if not stump:
        cuts.append(
            ((-0.81 * r * s, 0.81 * r * c, bed + 0.13), (-0.63 * s, 0.63 * c, -1))
        )
    split(obj, cuts, fracture, rng)


def source_parts():
    column.build()
    drums, footing, capital = {}, [], []
    for obj in list(vrlib.source_objects()):
        if obj.name.startswith("Survey shaft · drum "):
            drums[int(obj.name.rsplit(" ", 1)[-1]) - 1] = obj
        elif obj.name.startswith(
            ("Attic footing", "Footing course ", "Packed foundation")
        ):
            footing.append(obj)
        elif obj.name.startswith("Capital ·"):
            capital.append(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
    assert len(drums) == len(SHAFT_LEVELS) - 1 and len(capital) == 3
    return drums, footing, capital


def build():
    rng = random.Random(873321)
    drums, footing, capital = source_parts()
    fracture = column.accent(
        "Freshly split limestone · granular ochre",
        "monument_weathered",
        "stone_weathered",
        0.51,
        0.88,
    )
    tones = [obj.data.materials[0] for obj in drums.values()]
    break_drum(drums[0], 0, -0.72, 0.39, 0, rng, fracture, stump=True)
    seat([*footing, drums[0]], -8.20, 0.48, 0.10, 0, 0, -0.048)
    for index, phase, slope, loss, x, y, roll, bearing, fall in (
        (1, 1.84, 0.27, 0.33, -4.57, 0.48, 0.29, -0.20, 1.41),
        (3, -0.33, 0.46, 0.52, -1.38, -1.04, 0.54, 0.59, 0.16),
        (6, 0.82, 0.43, 0.42, 2.67, 0.52, -0.28, -0.72, 1.18),
    ):
        obj = drums[index]
        obj.name = f"Fallen survey drum {index+1:02}"
        break_drum(obj, index, phase, slope, loss, rng, fracture)
        seat((obj,), x, y, roll, bearing, fall, -0.049)

    for obj in capital:
        split(
            obj,
            [
                ((1.16, -0.88, 16.83), (0.71, -0.67, -0.18)),
                ((1.46, -1.19, 17.74), (0.82, -0.37, 0.36)),
            ],
            fracture,
            rng,
        )
    seat(capital, 6.54, -0.51, 0.03, -0.94, 1.57, -0.048)

    for index, a, x, y, length, thickness in (
        (2, -0.78, -5.42, 1.98, 0.86, 0.24),
        (2, 0.53, -3.42, -1.32, 0.71, 0.22),
        (4, -1.36, -1.95, 1.28, 0.91, 0.30),
        (4, 0.21, 1.17, -1.55, 0.71, 0.21),
        (5, 2.31, 4.97, 1.49, 0.78, 0.25),
        (5, 0.12, 6.80, -2.45, 0.64, 0.19),
    ):
        parent = drums[index]
        piece = vrlib.link_to_source(parent.copy())
        piece.data = parent.data.copy()
        piece.name = "Fluted casing spall"
        bed, top = SHAFT_LEVELS[index : index + 2]
        height = (bed + top) / 2
        radius = shaft_radius(height)
        c, s = math.cos(a), math.sin(a)
        edges = []
        for k in (-1, 1):
            angle = a + k * (0.19 + rng.uniform(-0.045, 0.057))
            edges.append(
                (
                    (radius * math.cos(angle), radius * math.sin(angle), height),
                    (
                        -k * math.sin(angle),
                        k * math.cos(angle),
                        rng.uniform(-0.14, 0.14),
                    ),
                )
            )
        split(
            piece,
            [
                (
                    (c * (radius - thickness), s * (radius - thickness), height),
                    (-c, -s, -0.07),
                ),
                (
                    (radius * c, radius * s, height + length / 2),
                    (0.31 * c, 0.31 * s, 1),
                ),
                (
                    (radius * c, radius * s, height - length / 2),
                    (-0.27 * c, -0.27 * s, -1),
                ),
                *edges,
            ],
            fracture,
            rng,
        )
        seat(
            (piece,),
            x,
            y,
            rng.uniform(-0.68, 0.60),
            rng.uniform(-1.9, 1.1),
            rng.uniform(0.99, 1.82),
            -0.035,
        )
    for index in (2, 4, 5):
        bpy.data.objects.remove(drums[index], do_unlink=True)

    soil = ground_materials("Fallen Survey Line")
    turf(-0.65, -0.04, 10.20, 3.55, 0.42, rng, soil, blades=890)
    for cx, cy, count in (
        (-7.9, -0.88, 16),
        (-5.0, 1.52, 18),
        (-3.04, -0.82, 22),
        (-1.5, -1.81, 15),
        (1.75, 0.82, 20),
        (4.67, 0.49, 21),
        (6.1, -1.27, 20),
        (8.37, -1.96, 15),
    ):
        for _ in range(count):
            size = rng.uniform(0.092, 0.55) ** 1.45
            x, y = cx + rng.gauss(0, 0.48), cy + rng.gauss(0, 0.36)
            stone_block(
                "Graded limestone scree",
                (
                    size * rng.uniform(1, 1.5),
                    size * rng.uniform(0.57, 1.1),
                    size * rng.uniform(0.39, 0.86),
                ),
                (x, y, 0),
                (rng.choice(tones), fracture),
                rng,
                azimuth=rng.uniform(-math.pi, math.pi),
                tilt=(rng.uniform(-0.38, 0.38), rng.uniform(-0.38, 0.38)),
                broken=True,
                foot=0.115,
            )

    turn = Matrix.Rotation(math.radians(-65), 4, "Z")
    for obj in vrlib.source_objects():
        obj.matrix_world = turn @ obj.matrix_world
    fit_arrises()
