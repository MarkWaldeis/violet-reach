"""Broken ivory survey-column ruin for the phase-6 ruin fields.

A compact grounded cluster: a fluted upright stump on a buried moulded footing,
two fallen shaft drums, a stepped capital fragment, mineral-filled cracks and
small masonry rubble. Units are metres, origin at the centre of the grounded
cluster, Z up. The asset is procedural and credit-free.
"""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector
from mathutils.geometry import delaunay_2d_cdt

from vrcolumn import flute
import vrlib
import vrmat


def make_mesh(name, vertices, faces, materials, material_indices=None, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, data))
    for material in materials if isinstance(materials, (tuple, list)) else (materials,):
        data.materials.append(material)
    for i, poly in enumerate(data.polygons):
        poly.use_smooth = bool(smooth)
        if material_indices is not None and i < len(material_indices):
            poly.material_index = material_indices[i]
    return obj


def shifted_material(name, source, color_key, scale, blend):
    """Palette-shifted copy of a library material; the shared vrmat cache stays untouched."""
    material = vrmat.get(source).copy()
    material.name = name
    tree = material.node_tree
    surface = tree.nodes["Principled BSDF"]
    rgb = vrmat.load_palette()[color_key]["linear_rgb"]
    mix = tree.nodes.new("ShaderNodeMixRGB")
    mix.inputs[0].default_value = blend
    old = surface.inputs["Base Color"].links[0].from_socket
    tree.links.new(old, mix.inputs[1])
    mix.inputs[2].default_value = (*(c * scale for c in rgb), 1)
    tree.links.new(mix.outputs[0], surface.inputs["Base Color"])
    surface.inputs["Specular IOR Level"].default_value = 0.22
    return material


def frame_from_axis(start, end):
    start, end = Vector(start), Vector(end)
    axis = end - start
    length = axis.length
    rotation = axis.normalized().to_track_quat("Z", "Y").to_matrix()

    def convert(point):
        return start + rotation @ Vector(point)

    return convert, length, rotation


def angle_delta(a, b):
    return math.atan2(math.sin(a - b), math.cos(a - b))


def cylinder_fragment(
    name,
    start,
    end,
    radius,
    materials,
    seed,
    *,
    taper=0.045,
    flute_depth=0.034,
    segments=112,
    rings=18,
    grooves=(),
    break_scale=1.0,
):
    """Closed fluted shaft fragment with non-planar mineral fracture caps.

    The mesh is modelled in world coordinates (object transform remains identity),
    so vrmat's metre-scale object coordinates line up with the visible object.
    Returns the local-to-world conversion, length and radius function for cracks.
    """
    rng = random.Random(seed)
    convert, length, _rotation = frame_from_axis(start, end)
    phase = rng.uniform(0, math.tau)
    phases = [rng.uniform(0, math.tau) for _ in range(8)]
    end_amp = radius * 0.165 * break_scale
    edge_noise = [[rng.uniform(-1.0, 1.0) for _ in range(24)] for _ in range(2)]
    # Broad, volumetric loss zones near each broken end. Unlike the old z-only rim
    # ripple these bite radially into the shaft, so missing stone has real thickness.
    end_chips = []
    for _which in range(2):
        chip_base = rng.uniform(0, math.tau)
        end_chips.append([
            (
                chip_base + math.tau * k / 3.0 + rng.uniform(-0.34, 0.34),
                rng.uniform(0.18, 0.31),
                rng.uniform(0.46, 0.72),
                rng.uniform(0.140, 0.250) * radius / 0.46,
            )
            for k in range(3)
        ])
    dents = []
    for _ in range(5):
        dents.append(
            (
                rng.uniform(0.10, 0.90),
                rng.uniform(0, math.tau),
                rng.uniform(0.010, 0.030) * radius / 0.46,
                rng.uniform(0.025, 0.075),
                rng.uniform(0.12, 0.28),
            )
        )

    def end_wave(which, a):
        p = phases[0 if which == 0 else 3]
        sector = int((a / math.tau) * 24 + (5 if which else 0)) % 24
        stepped = edge_noise[which][sector]
        return end_amp * (
            (1 if which == 0 else -1)
            * 0.31
            + 0.31 * math.sin(3 * a + p)
            + 0.18 * math.sin(5 * a + p * 1.71)
            + 0.09 * math.cos(8 * a - p * 0.63)
            + 0.27 * stepped
        )

    def radius_at(t, a):
        base = radius * (1.0 + taper * (0.52 - t))
        value = base - flute_depth * flute(a + phase)
        value += radius * (0.007 * math.sin(5 * a + phases[6]) + 0.004 * math.cos(11 * a - phases[7])) * math.sin(math.pi * t) ** 2
        z = t * length
        for zc, width, depth in grooves:
            value -= depth * math.exp(-((z - zc) / width) ** 2)
        for tc, ac, amp, wt, wa in dents:
            value -= amp * math.exp(-((t - tc) / wt) ** 2) * math.exp(-(angle_delta(a, ac) / wa) ** 2)
        z = t * length
        for which, end_t in ((0, 0.0), (1, 1.0)):
            end_distance = abs(t - end_t) * length
            if end_distance < 0.28:
                for ac, loss, wa, axial in end_chips[which]:
                    angular = math.exp(-(angle_delta(a, ac) / wa) ** 2)
                    depth_falloff = math.exp(-(end_distance / axial) ** 2)
                    value -= radius * loss * angular * depth_falloff
        return max(radius * 0.55, value)

    vertices = []
    for j in range(rings + 1):
        t = j / rings
        z0 = t * length
        for i in range(segments):
            a = math.tau * i / segments
            z = z0 + ((1 - t) ** 9) * end_wave(0, a) + (t**9) * end_wave(1, a)
            r = radius_at(t, a)
            vertices.append(convert((r * math.cos(a), r * math.sin(a), z)))

    faces = []
    material_indices = []
    for j in range(rings):
        for i in range(segments):
            p, q = j * segments + i, j * segments + (i + 1) % segments
            faces.append((p, q, q + segments, p + segments))
            material_indices.append(0)

    side_count = len(faces)

    def cap_boundary_z(which, a):
        return (length if which else 0.0) + end_wave(which, a)

    def add_cap(which):
        # Irregular constrained Delaunay fracture surface. Interior points are jittered
        # in polar rings, so the cap reads as faceted broken stone instead of a radial fan.
        boundary_ring = (rings if which else 0) * segments
        inward = -1.0 if which else 1.0
        boundary_points = []
        boundary_local = []
        for i in range(segments):
            a = math.tau * i / segments
            rr = radius_at(float(which), a)
            x, y = rr * math.cos(a), rr * math.sin(a)
            boundary_points.append(Vector((x, y)))
            boundary_local.append((x, y, cap_boundary_z(which, a)))

        interior_points = []
        interior_meta = []
        cap_rng = random.Random(seed + 911 + which * 37)
        for frac, count in ((0.76, max(14, segments // 4)), (0.52, max(10, segments // 6)), (0.30, max(7, segments // 9))):
            offset = cap_rng.uniform(0, math.tau)
            for k in range(count):
                a = offset + math.tau * k / count + cap_rng.uniform(-0.11, 0.11)
                rr = radius_at(float(which), a) * frac * cap_rng.uniform(0.88, 1.08)
                x, y = rr * math.cos(a), rr * math.sin(a)
                interior_points.append(Vector((x, y)))
                interior_meta.append((x, y))
        interior_points.append(Vector((0.018 * math.sin(phases[2]), 0.014 * math.cos(phases[2]))))
        interior_meta.append((interior_points[-1].x, interior_points[-1].y))

        points = boundary_points + interior_points
        coords, _edges, pieces, ids, _verts_orig, _faces_orig = delaunay_2d_cdt(
            points, [], [tuple(range(segments))], 1, 1e-6
        )
        terrace_noise = [cap_rng.uniform(-1.0, 1.0) for _ in range(16)]
        output_to_mesh = []
        output_local = []
        for out_index, (co, source) in enumerate(zip(coords, ids)):
            if source and source[0] < segments:
                source_index = source[0]
                output_to_mesh.append(boundary_ring + source_index)
                output_local.append(boundary_local[source_index])
                continue
            x, y = co.x, co.y
            rho = math.hypot(x, y)
            a = math.atan2(y, x)
            edge_z = cap_boundary_z(which, a)
            depth = 0.012 + 0.048 * max(0.0, 1.0 - rho / max(radius, 0.001)) ** 1.18
            sector = int(((a + math.pi) % math.tau) / math.tau * 16) % 16
            terrace = 0.034 * terrace_noise[sector]
            rough = 0.014 * math.sin(8.3 * x + 5.1 * y + phases[4]) + 0.009 * math.cos(13.7 * x - 6.2 * y + phases[5])
            zz = edge_z + inward * (depth + terrace + rough)
            output_to_mesh.append(len(vertices))
            output_local.append((x, y, zz))
            vertices.append(convert((x, y, zz)))

        for tri in pieces:
            p0, p1, p2 = (Vector(output_local[i]) for i in tri)
            normal_z = (p1 - p0).cross(p2 - p0).z
            face = tuple(output_to_mesh[i] for i in tri)
            if (which and normal_z < 0) or (not which and normal_z > 0):
                face = tuple(reversed(face))
            faces.append(face)
            material_indices.append(1)

    add_cap(0)
    add_cap(1)
    obj = make_mesh(name, vertices, faces, materials, material_indices, False)
    for poly in obj.data.polygons[:side_count]:
        poly.use_smooth = True
    return obj, convert, length, radius_at


def surface_crack(name, convert, radius_at, length, seed, z0, z1, angle0, width, depth, material, edge_material=None, stations=10):
    """Ragged recessed crack with chipped light edges and a dark mineral bed.

    Five conforming vertices per station form a shallow V-shaped stone loss instead
    of a painted line: outer chipped lips stay near the shaft surface while the two
    central rows are genuinely recessed into the cylinder.
    """
    rng = random.Random(seed)
    drift = rng.uniform(-0.48, 0.48)
    phase = rng.uniform(0, math.tau)
    chip_events = [
        (rng.uniform(0.20, 0.80), rng.uniform(0.060, 0.120), rng.uniform(0.70, 1.20))
        for _ in range(2)
    ]
    vertices = []
    for s in range(stations):
        t = s / (stations - 1)
        z = z0 + (z1 - z0) * t
        a = angle0 + drift * t + 0.13 * math.sin(math.pi * t * 2.0 + phase) + 0.045 * math.sin(math.pi * t * 5.0 - phase) + rng.uniform(-0.034, 0.034)
        rt = max(0.0, min(1.0, z / length))
        r = radius_at(rt, a)
        radial = Vector((math.cos(a), math.sin(a), 0))
        tangent = Vector((-math.sin(a), math.cos(a), 0))
        taper = max(0.0, math.sin(math.pi * t)) ** 0.58
        w = width * (0.16 + 1.04 * taper) * (0.73 + 0.19 * math.sin(9 * t + phase) + 0.10 * math.cos(17 * t - phase))
        for centre_t, width_t, boost in chip_events:
            w += width * boost * math.exp(-((t - centre_t) / width_t) ** 2)
        half_left = w * (0.43 + 0.09 * math.sin(13 * t + phase) + 0.055 * rng.uniform(-1.0, 1.0))
        half_right = w * (0.50 + 0.08 * math.cos(11 * t - phase) + 0.055 * rng.uniform(-1.0, 1.0))
        half_left = max(width * 0.055, half_left)
        half_right = max(width * 0.060, half_right)
        centre = Vector((r * math.cos(a), r * math.sin(a), z))
        centre += tangent * (0.012 * math.sin(11 * t + phase) + 0.006 * math.sin(23 * t - phase) + rng.uniform(-0.024, 0.024))
        centre.z += 0.006 * math.sin(15 * t + phase * 0.7)
        offsets = (-half_left, -half_left * 0.42, 0.0, half_right * 0.42, half_right)
        radial_offsets = (0.0025, -depth * 0.52, -depth, -depth * 0.55, 0.0025)
        for k, (offset, radial_offset) in enumerate(zip(offsets, radial_offsets)):
            edge_chip = (0.0045 * math.sin((k + 2) * 7.0 + t * 31.0 + phase) if k in (0, 4) else 0.0)
            point = centre + tangent * (offset + edge_chip) + radial * radial_offset
            point.z += (0.0035 * math.sin(29 * t + k * 1.7 + phase) if k in (0, 4) else 0.002 * math.sin(19 * t + k))
            vertices.append(convert(point))

    faces = []
    material_indices = []
    # Outer sloping strips are pale freshly chipped stone; the two inner strips are
    # the darker recessed mineral bed. This material split is essential to keep the
    # crack from reading as a drawn dark curve.
    face_materials = (1, 0, 0, 1)
    for s in range(stations - 1):
        for k in range(4):
            p0 = 5 * s + k
            faces.append((p0, p0 + 1, p0 + 6, p0 + 5))
            material_indices.append(face_materials[k])
    # Small closed end wedges; recessed ends keep the strip volumetric rather than a paper decal.
    faces.extend(((0, 2, 1), (0, 3, 2), (0, 4, 3)))
    material_indices.extend((1, 0, 1))
    end = 5 * (stations - 1)
    faces.extend(((end, end + 1, end + 2), (end, end + 2, end + 3), (end, end + 3, end + 4)))
    material_indices.extend((1, 0, 1))
    materials = (material, edge_material if edge_material is not None else material)
    return make_mesh(name, vertices, faces, materials, material_indices, False)


def plinth(name, centre, materials, seed):
    rng = random.Random(seed)
    cx, cy = centre
    segments = 128
    profile = (
        (-0.105, 0.895),
        (-0.025, 0.895),
        (0.005, 0.940),
        (0.055, 0.940),
        (0.082, 0.855),
        (0.125, 0.855),
        (0.155, 0.780),
        (0.205, 0.780),
        (0.245, 0.700),
        (0.305, 0.665),
        (0.360, 0.610),
        (0.420, 0.570),
        (0.445, 0.570),
    )
    chip_a = rng.uniform(0, math.tau)
    vertices = []
    for z, rr in profile:
        for i in range(segments):
            a = math.tau * i / segments
            chip = 0.055 * math.exp(-(angle_delta(a, chip_a) / 0.35) ** 2) * max(0, (z - 0.15) / 0.30)
            r = rr + 0.0045 * math.sin(5 * a + z * 9) + 0.0025 * math.cos(13 * a - z * 6) - chip
            vertices.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    faces = []
    material_indices = []
    rows = len(profile)
    for j in range(rows - 1):
        for i in range(segments):
            p, q = j * segments + i, j * segments + (i + 1) % segments
            faces.append((p, q, q + segments, p + segments))
            material_indices.append(0)
    # Closed underside and uneven upper seat; both are real capped stone.
    bottom_centre = len(vertices)
    vertices.append((cx, cy, profile[0][0]))
    top_centre = len(vertices)
    vertices.append((cx, cy, profile[-1][0] + 0.012))
    for i in range(segments):
        ni = (i + 1) % segments
        faces.append((bottom_centre, ni, i))
        material_indices.append(1)
        a, b = (rows - 1) * segments + i, (rows - 1) * segments + ni
        faces.append((a, b, top_centre))
        material_indices.append(0)
    # Flat cross-section normals preserve the crisp torus/scotia steps; 128 radial
    # segments still keep the circular plan smooth in silhouette.
    obj = make_mesh(name, vertices, faces, materials, material_indices, False)
    return obj


def capital_cushion(name, centre, materials, seed):
    """Rounded echinus cushion for the fallen capital, with crisp stepped moulding."""
    rng = random.Random(seed)
    cx, cy = centre
    segments = 72
    profile = (
        (-0.030, 0.315),
        (0.015, 0.350),
        (0.060, 0.405),
        (0.125, 0.445),
        (0.185, 0.430),
        (0.235, 0.375),
        (0.290, 0.325),
        (0.335, 0.315),
    )
    chip_a = rng.uniform(0, math.tau)
    vertices = []
    for z, rr in profile:
        for i in range(segments):
            a = math.tau * i / segments
            chip = 0.065 * math.exp(-(angle_delta(a, chip_a) / 0.42) ** 2) * max(0.0, (z - 0.08) / 0.25)
            r = rr + 0.005 * math.sin(5 * a + z * 8.0) + 0.003 * math.cos(11 * a - z * 5.0) - chip
            vertices.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    rows = len(profile)
    faces = []
    material_indices = []
    for j in range(rows - 1):
        for i in range(segments):
            q = j * segments + i
            n = j * segments + (i + 1) % segments
            faces.append((q, n, n + segments, q + segments))
            material_indices.append(0)
    bottom_centre = len(vertices)
    vertices.append((cx, cy, profile[0][0]))
    top_centre = len(vertices)
    vertices.append((cx, cy, profile[-1][0] + 0.006))
    for i in range(segments):
        ni = (i + 1) % segments
        faces.append((bottom_centre, ni, i))
        material_indices.append(1)
        q = (rows - 1) * segments + i
        n = (rows - 1) * segments + ni
        faces.append((q, n, top_centre))
        material_indices.append(1)
    return make_mesh(name, vertices, faces, materials, material_indices, False)


def transform_local_points(points, rotation, translation, ground_z=None):
    matrix = Euler(rotation).to_matrix()
    out = [Vector(translation) + matrix @ Vector(p) for p in points]
    if ground_z is not None:
        dz = ground_z - min(p.z for p in out)
        out = [p + Vector((0, 0, dz)) for p in out]
    return [tuple(p) for p in out]


def chipped_block(name, centre, dims, rotation, material, seed, *, ground_z=-0.025, cuts=2, bevel_width=0.018):
    """Small closed masonry chip: jittered solid cube with two planar corner losses."""
    rng = random.Random(seed)
    hx, hy, hz = (v * 0.5 for v in dims)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    for v in bm.verts:
        v.co.x *= hx * rng.uniform(0.88, 1.08)
        v.co.y *= hy * rng.uniform(0.88, 1.08)
        v.co.z *= hz * rng.uniform(0.87, 1.08)
        v.co.x += rng.uniform(-0.085, 0.085) * dims[0]
        v.co.y += rng.uniform(-0.085, 0.085) * dims[1]
        v.co.z += rng.uniform(-0.055, 0.055) * dims[2]
    for _ in range(cuts):
        sx, sy, sz = (rng.choice((-1, 1)) for _ in range(3))
        point = (
            sx * hx * rng.uniform(0.45, 0.82),
            sy * hy * rng.uniform(0.48, 0.86),
            sz * hz * rng.uniform(0.40, 0.82),
        )
        normal = (sx * rng.uniform(0.45, 1.1), sy * rng.uniform(0.45, 1.1), sz * rng.uniform(0.55, 1.25))
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
            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    matrix = Euler(rotation).to_matrix()
    world = [Vector(centre) + matrix @ v.co for v in bm.verts]
    dz = ground_z - min(p.z for p in world)
    index = {v: i for i, v in enumerate(bm.verts)}
    vertices = [tuple(p + Vector((0, 0, dz))) for p in world]
    faces = [tuple(index[v] for v in f.verts) for f in bm.faces]
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    bm.free()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, data))
    data.materials.append(material)
    if bevel_width:
        bevel = obj.modifiers.new("Worn chipped edges", "BEVEL")
        bevel.width = min(bevel_width, min(dims) * 0.10)
        bevel.segments = 2
        bevel.angle_limit = 0.27
    return obj


def organic_patch(name, centre, rx, ry, height, material, seed, *, rotation=0.0, segments=56):
    """Closed low-volume soil/moss accumulation with a feathered sloping rim.

    The visible perimeter widens while its height falls to a few millimetres, so the
    patch reads as accumulated matter rather than a hard-edged decal. The underside
    remains embedded and closed, keeping the mesh solid.
    """
    rng = random.Random(seed)
    cx, cy = centre
    ca, sa = math.cos(rotation), math.sin(rotation)
    phase = rng.uniform(0, math.tau)
    phase2 = rng.uniform(0, math.tau)
    rings = 5
    vertices = [(cx, cy, height * 0.96)]

    def boundary_at(a):
        return (
            1.0
            + 0.17 * math.sin(3 * a + phase)
            + 0.095 * math.cos(7 * a - phase)
            + 0.045 * math.sin(11 * a + phase2)
        )

    for j in range(1, rings + 1):
        t = j / rings
        # Slight outward skirt in the last courses: height and slope feather together.
        radial_t = t * (1.0 + 0.11 * t)
        for i in range(segments):
            a = math.tau * i / segments
            boundary = boundary_at(a)
            rr = radial_t * boundary
            x, y = rx * rr * math.cos(a), ry * rr * math.sin(a)
            crown = height * max(0.0, 1.0 - t) ** 1.32
            undulation = 0.84 + 0.13 * math.sin(5 * a + phase + j * 0.7) + 0.05 * math.cos(9 * a - phase2)
            z = crown * undulation + 0.0022 * (1.0 - 0.35 * t)
            vertices.append((cx + ca * x - sa * y, cy + sa * x + ca * y, z))

    bottom_start = len(vertices)
    for i in range(segments):
        a = math.tau * i / segments
        boundary = 0.96 * boundary_at(a)
        x, y = rx * boundary * math.cos(a), ry * boundary * math.sin(a)
        vertices.append((cx + ca * x - sa * y, cy + sa * x + ca * y, -0.006))
    bottom_centre = len(vertices)
    vertices.append((cx, cy, -0.008))

    faces = []
    first = 1
    for i in range(segments):
        ni = (i + 1) % segments
        faces.append((0, first + i, first + ni))
    for j in range(1, rings):
        inner = 1 + (j - 1) * segments
        outer = 1 + j * segments
        for i in range(segments):
            ni = (i + 1) % segments
            faces.append((inner + i, outer + i, outer + ni, inner + ni))
    top_edge = 1 + (rings - 1) * segments
    for i in range(segments):
        ni = (i + 1) % segments
        faces.append((top_edge + i, bottom_start + i, bottom_start + ni, top_edge + ni))
        faces.append((bottom_centre, bottom_start + ni, bottom_start + i))
    return make_mesh(name, vertices, faces, material, smooth=True)


def build():
    rng = random.Random(642917)
    weathered = shifted_material(
        "Broken column · ivory weathered limestone",
        "monument_weathered",
        "stone_weathered",
        1.02,
        0.43,
    )
    fracture = shifted_material(
        "Broken column · pale mineral fracture",
        "monument_white",
        "monument_white",
        0.91,
        0.42,
    )
    crack = shifted_material(
        "Broken column · dark lime-filled cracks",
        "monument_weathered",
        "monument_shadow",
        0.72,
        0.58,
    )
    soil = shifted_material(
        "Broken column · accumulated earth",
        "forest_soil",
        "path_sand",
        0.72,
        0.54,
    )
    moss = shifted_material(
        "Broken column · olive moss film",
        "grass_ground",
        "moss",
        1.12,
        0.76,
    )
    rubble_mat = shifted_material(
        "Broken column · rubble stone",
        "monument_weathered",
        "monument_white",
        0.95,
        0.34,
    )
    stone_pair = (weathered, fracture)

    # Earth first, then low moss cushions at the contact lines. Both are closed volumes,
    # split into irregular islands rather than one hard-edged mat under the whole ruin.
    organic_patch("Earth accumulated around footing", (-1.78, 0.52), 0.98, 0.82, 0.036, soil, 7101, rotation=0.22)
    organic_patch("Olive moss at footing", (-1.79, 0.48), 0.57, 0.43, 0.050, moss, 7102, rotation=-0.18)
    organic_patch("Earth at west drum contact", (-0.43, -0.18), 0.45, 0.19, 0.027, soil, 7103, rotation=-0.39)
    organic_patch("Earth at east drum contact", (1.24, -0.82), 0.42, 0.18, 0.026, soil, 7106, rotation=-0.39)
    organic_patch("Moss along fallen drum west", (-0.02, -0.27), 0.32, 0.17, 0.040, moss, 7104, rotation=-0.39)
    organic_patch("Moss along fallen drum east", (0.88, -0.65), 0.34, 0.16, 0.036, moss, 7107, rotation=-0.48)
    organic_patch("Moss at capital fragment", (-0.12, 1.42), 0.36, 0.25, 0.034, moss, 7105, rotation=0.26)

    plinth("Buried moulded column footing", (-1.80, 0.55), stone_pair, 7210)

    upright, upright_convert, upright_len, upright_radius = cylinder_fragment(
        "Upright broken fluted shaft stump",
        (-1.80, 0.55, 0.30),
        (-1.80, 0.55, 2.13),
        0.515,
        stone_pair,
        7301,
        taper=0.052,
        flute_depth=0.038,
        segments=112,
        rings=17,
        grooves=((0.64, 0.035, 0.022),),
        break_scale=1.18,
    )
    surface_crack(
        "Stump crack west",
        upright_convert,
        upright_radius,
        upright_len,
        7401,
        0.58,
        1.70,
        3.60,
        0.082,
        0.044,
        crack,
        fracture,
        stations=11,
    )
    surface_crack(
        "Stump crack east fork",
        upright_convert,
        upright_radius,
        upright_len,
        7402,
        0.88,
        1.78,
        0.72,
        0.062,
        0.035,
        crack,
        fracture,
        stations=9,
    )

    long_drum, long_convert, long_len, long_radius = cylinder_fragment(
        "Fallen long fluted shaft drum",
        (-0.78, 0.02, 0.455),
        (1.88, -1.06, 0.470),
        0.455,
        stone_pair,
        7501,
        taper=0.026,
        flute_depth=0.034,
        segments=96,
        rings=17,
        grooves=((1.37, 0.030, 0.017),),
        break_scale=1.08,
    )
    surface_crack(
        "Long drum axial crack",
        long_convert,
        long_radius,
        long_len,
        7601,
        0.22,
        2.25,
        1.92,
        0.096,
        0.047,
        crack,
        fracture,
        stations=13,
    )
    surface_crack(
        "Long drum branching crack",
        long_convert,
        long_radius,
        long_len,
        7602,
        0.84,
        2.48,
        4.82,
        0.062,
        0.035,
        crack,
        fracture,
        stations=11,
    )

    short_drum, short_convert, short_len, short_radius = cylinder_fragment(
        "Fallen short fluted shaft drum",
        (2.12, -1.22, 0.405),
        (3.02, -1.82, 0.365),
        0.402,
        stone_pair,
        7701,
        taper=0.018,
        flute_depth=0.032,
        segments=88,
        rings=12,
        grooves=(),
        break_scale=1.12,
    )
    surface_crack(
        "Short drum cracked face line",
        short_convert,
        short_radius,
        short_len,
        7801,
        0.15,
        0.92,
        2.70,
        0.070,
        0.038,
        crack,
        fracture,
        stations=8,
    )

    # Fallen capital remainder: a crisp rounded echinus cushion overlapped by a thick
    # broken square abacus. The pairing gives the classical capital silhouette without
    # thin paving-slab pieces or broad planar wedge cheeks.
    capital_cushion("Fallen capital cushion echinus", (-0.11, 1.42), stone_pair, 7901)
    chipped_block(
        "Fallen capital thick broken abacus",
        (-0.08, 1.42, 0.42),
        (0.76, 0.64, 0.26),
        (0.06, -0.04, -0.56),
        weathered,
        7907,
        ground_z=0.235,
        cuts=6,
        bevel_width=0.023,
    )

    # Support stones are deliberately half-buried and intersect the drum underside:
    # they sell the weight and rule out a hovering cylinder without looking like props.
    supports = (
        ("West support stone under drum", (-0.23, -0.28, 0.09), (0.40, 0.31, 0.20), (0.18, 0.31, -0.42), 8101),
        ("East support stone under drum", (1.18, -0.78, 0.08), (0.36, 0.29, 0.18), (-0.12, 0.24, 0.34), 8102),
    )
    for name, centre, dims, rot, seed in supports:
        chipped_block(name, centre, dims, rot, rubble_mat, seed, ground_z=-0.035, cuts=3, bevel_width=0.014)

    rubble_specs = (
        (-2.50, -0.12, 0.30, 0.22, 0.16),
        (-2.32, 1.30, 0.25, 0.19, 0.14),
        (-1.15, 1.35, 0.34, 0.22, 0.16),
        (-0.72, -0.86, 0.22, 0.18, 0.13),
        (0.10, -1.18, 0.30, 0.20, 0.14),
        (1.80, -0.34, 0.24, 0.18, 0.13),
        (2.62, -0.88, 0.28, 0.20, 0.14),
        (3.24, -1.36, 0.20, 0.16, 0.12),
        (0.54, 1.30, 0.22, 0.16, 0.13),
        (-0.55, 1.86, 0.18, 0.15, 0.11),
    )
    for i, (x, y, sx, sy, sz) in enumerate(rubble_specs):
        chipped_block(
            f"Column masonry rubble {i + 1:02}",
            (x, y, sz * 0.42),
            (sx, sy, sz),
            (rng.uniform(-0.24, 0.24), rng.uniform(-0.24, 0.24), rng.uniform(-math.pi, math.pi)),
            rubble_mat,
            8200 + i,
            ground_z=-0.028,
            cuts=3 if i % 4 else 4,
            bevel_width=0.010,
        )

    # Review-sheet framing: the orange 1.8 m figure stands clear of the footprint,
    # and the two closeups show the broken crown and the grounded shaft/crack detail.
    scene = bpy.context.scene
    scene["vr_review_figure"] = (-2.86, -0.86, 0.0)
    scene["vr_hero"] = (0.10, -0.16, 0.70, 322.0, 17.0, 10.35)
    scene["vr_closeup_upper"] = (-1.76, 0.52, 1.40, 310.0, 13.0, 5.2)
    scene["vr_closeup_base"] = (0.40, -0.42, 0.40, 218.0, 17.0, 4.6)
