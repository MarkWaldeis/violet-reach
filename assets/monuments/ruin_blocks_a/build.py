"""Ruin blocks A — credit-free procedural ivory limestone rubble group.

Units are metres, origin at ground centre, Z up.  The asset is a coherent cluster of
0.8–3.8 m masonry fragments spread over roughly 7.2 × 4.4 m.  Every block is a solid,
partly embedded mesh; larger pieces carry clipped fracture planes and real boolean-cut
crack grooves.  A low compacted earth/lime bed and solid moss pads tie the group to the
ground for Phase-6 ruin fields.
"""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Vector
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat


# -----------------------------------------------------------------------------
# Materials


def _simple_material(name, rgb, roughness=0.9, specular=0.22):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Specular IOR Level"].default_value = specular
    bsdf.inputs["Transmission Weight"].default_value = 0.0
    return mat


def limestone_material(name, fracture=False):
    """Subtle matte ivory limestone; the library weathered shader is too blotchy at 1–4 m scale."""
    palette = vrmat.load_palette()
    ivory = palette["monument_white"]["linear_rgb"]
    weathered = palette["stone_weathered"]["linear_rgb"]
    soil = palette["soil"]["linear_rgb"]

    def rgba(rgb, gain=1.0):
        return tuple(min(1.0, c * gain) for c in rgb) + (1.0,)

    # Start from the mandated library material, then replace its blue-grey weathering
    # blotches with a warmer close-range limestone graph.  Unused library nodes remain
    # inert in the copy; the active output is fully controlled below.
    mat = vrmat.get("monument_white" if fracture else "monument_weathered").copy()
    mat.name = name
    mat.use_nodes = True
    mat.diffuse_color = rgba(weathered if not fracture else ivory)
    mat["vrmat_name"] = "stone_white"
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Alpha"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Transmission Weight"].default_value = 0.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.25

    coord = nodes.new("ShaderNodeTexCoord")
    vector = coord.outputs["Object"]

    def noise(scale, detail=4.0, roughness=0.72):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        node.inputs["Roughness"].default_value = roughness
        links.new(vector, node.inputs["Vector"])
        return node.outputs["Fac"]

    def color_ramp(source, low, high, positions=(0.25, 0.75)):
        node = nodes.new("ShaderNodeValToRGB")
        node.color_ramp.elements[0].position = positions[0]
        node.color_ramp.elements[0].color = low
        node.color_ramp.elements[1].position = positions[1]
        node.color_ramp.elements[1].color = high
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, first, second, blend="MIX"):
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = blend
        if isinstance(factor, (int, float)):
            node.inputs["Fac"].default_value = factor
        else:
            links.new(factor, node.inputs["Fac"])
        for value, socket in ((first, "Color1"), (second, "Color2")):
            if isinstance(value, tuple):
                node.inputs[socket].default_value = value
            else:
                links.new(value, node.inputs[socket])
        return node.outputs["Color"]

    def math_op(operation, first, second):
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        if isinstance(first, (int, float)):
            node.inputs[0].default_value = first
        else:
            links.new(first, node.inputs[0])
        if isinstance(second, (int, float)):
            node.inputs[1].default_value = second
        else:
            links.new(second, node.inputs[1])
        return node.outputs[0]

    # Broad mineral variation stays inside the two pale limestone palette colours.
    macro = color_ramp(noise(0.72, 3.0), rgba(weathered, 0.97), rgba(ivory, 1.015), (0.24, 0.78))
    neutral = rgba(tuple(0.45 * a + 0.55 * b for a, b in zip(ivory, weathered)), 1.0)
    base = mix(0.58, neutral, macro)

    # A small per-block tone shift separates the modular pieces without random dark patches.
    random_tone = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    warm = rgba(ivory, 0.99)
    cool = rgba(weathered, 0.94)
    piece_tone = mix(random_tone, cool, warm)
    base = mix(0.25 if not fracture else 0.10, base, piece_tone)

    # Hand-scale mineral grain plus fine pale grain: visible close up, but still warm
    # limestone rather than blue-grey marble clouds.
    medium = noise(7.4, 4.0, 0.76)
    medium_tone = color_ramp(medium, (0.91, 0.91, 0.91, 1), (1.065, 1.065, 1.065, 1), (0.22, 0.80))
    base = mix(0.58, base, medium_tone, "MULTIPLY")
    fine = noise(46.0, 5.0, 0.78)
    fine_tone = color_ramp(fine, (0.865, 0.865, 0.865, 1), (1.065, 1.065, 1.065, 1), (0.20, 0.82))
    base = mix(0.46, base, fine_tone, "MULTIPLY")

    # Tiny warm pore shadows in the albedo.  They are small and low-contrast, but keep
    # closeups from reading as painted plaster under the otherwise flat studio sun.
    surface_pores = nodes.new("ShaderNodeTexVoronoi")
    surface_pores.distance = "EUCLIDEAN"
    surface_pores.inputs["Scale"].default_value = 72.0
    links.new(vector, surface_pores.inputs["Vector"])
    pore_color = color_ramp(
        surface_pores.outputs["Distance"],
        (0.68, 0.66, 0.61, 1),
        (1.0, 1.0, 1.0, 1),
        (0.026, 0.105),
    )
    base = mix(0.18 if not fracture else 0.09, base, pore_color, "MULTIPLY")

    # Vertically elongated mineral runoff.  The noise is stretched along Z and masked
    # away from horizontal tops, so it reads as weathering rather than marble veining.
    stretched = nodes.new("ShaderNodeVectorMath")
    stretched.operation = "MULTIPLY"
    stretched.inputs[1].default_value = (4.1, 4.1, 0.25)
    links.new(vector, stretched.inputs[0])
    streak_tex = nodes.new("ShaderNodeTexNoise")
    streak_tex.inputs["Scale"].default_value = 1.18
    streak_tex.inputs["Detail"].default_value = 3.2
    streak_tex.inputs["Roughness"].default_value = 0.74
    links.new(stretched.outputs["Vector"], streak_tex.inputs["Vector"])
    streak_ramp = nodes.new("ShaderNodeValToRGB")
    streak_ramp.color_ramp.elements[0].position = 0.47
    streak_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1)
    streak_ramp.color_ramp.elements[1].position = 0.72
    streak_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1)
    links.new(streak_tex.outputs["Fac"], streak_ramp.inputs["Fac"])
    geom = nodes.new("ShaderNodeNewGeometry")
    normal_axes = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geom.outputs["Normal"], normal_axes.inputs["Vector"])
    abs_normal_z = math_op("ABSOLUTE", normal_axes.outputs["Z"], 0.0)
    vertical_mask = nodes.new("ShaderNodeMapRange")
    vertical_mask.interpolation_type = "SMOOTHSTEP"
    vertical_mask.inputs["From Min"].default_value = 0.18
    vertical_mask.inputs["From Max"].default_value = 0.78
    vertical_mask.inputs["To Min"].default_value = 1.0
    vertical_mask.inputs["To Max"].default_value = 0.0
    links.new(abs_normal_z, vertical_mask.inputs["Value"])
    streak_factor = math_op("MULTIPLY", streak_ramp.outputs["Color"], vertical_mask.outputs["Result"])
    streak_factor = math_op("MULTIPLY", streak_factor, 0.25 if not fracture else 0.10)
    stain_color = rgba(tuple(0.76 * w + 0.24 * s for w, s in zip(weathered, soil)), 1.0)
    base = mix(streak_factor, base, stain_color)

    # Ground contact: a restrained dusty lime/soil rise, strongest below 0.45 m.
    axes = nodes.new("ShaderNodeSeparateXYZ")
    links.new(vector, axes.inputs["Vector"])
    dirt_wobble = math_op("MULTIPLY", noise(2.4, 3.0), 0.11)
    dirty_z = math_op("ADD", axes.outputs["Z"], dirt_wobble)
    dirt_map = nodes.new("ShaderNodeMapRange")
    dirt_map.interpolation_type = "SMOOTHSTEP"
    dirt_map.inputs["From Min"].default_value = 0.02
    dirt_map.inputs["From Max"].default_value = 0.52
    dirt_map.inputs["To Min"].default_value = 0.11 if fracture else 0.30
    dirt_map.inputs["To Max"].default_value = 0.0
    links.new(dirty_z, dirt_map.inputs["Value"])
    dirt_color = rgba(tuple(0.48 * s + 0.52 * w for s, w in zip(soil, weathered)), 1.0)
    base = mix(dirt_map.outputs["Result"], base, dirt_color)

    # Real grooves and compressed contact shadows must stay dark even in sun.  AO is
    # restrained (warm grey-brown, never black) and is particularly important because
    # the cracks are true recessed geometry rather than painted lines.
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 4
    ao.inputs["Distance"].default_value = 0.13
    crevice = rgba(tuple(0.42 * s + 0.58 * w for s, w in zip(soil, weathered)), 0.78)
    base = mix(ao.outputs["AO"], crevice, base)
    links.new(base, bsdf.inputs["Base Color"])

    # Matte mineral response with fine pores feeding both roughness and bump.
    rough_map = nodes.new("ShaderNodeMapRange")
    rough_map.inputs["From Min"].default_value = 0.0
    rough_map.inputs["From Max"].default_value = 1.0
    rough_map.inputs["To Min"].default_value = 0.78 if not fracture else 0.73
    rough_map.inputs["To Max"].default_value = 0.94
    links.new(fine, rough_map.inputs["Value"])
    links.new(rough_map.outputs["Result"], bsdf.inputs["Roughness"])

    pores = nodes.new("ShaderNodeTexVoronoi")
    pores.distance = "EUCLIDEAN"
    pores.inputs["Scale"].default_value = 88.0
    links.new(vector, pores.inputs["Vector"])
    pore_height = color_ramp(pores.outputs["Distance"], (0.20, 0.20, 0.20, 1), (1.0, 1.0, 1.0, 1), (0.035, 0.13))
    height = mix(0.44, medium_tone, fine_tone, "MULTIPLY")
    height = mix(0.62, height, pore_height, "MULTIPLY")
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.54 if not fracture else 0.36
    bump.inputs["Distance"].default_value = 0.015 if not fracture else 0.008
    links.new(height, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_materials():
    palette = vrmat.load_palette()
    shadow = palette["monument_shadow"]["linear_rgb"]
    weathered_rgb = palette["stone_weathered"]["linear_rgb"]
    soil_rgb = palette["soil"]["linear_rgb"]
    crack_rgb = tuple(0.50 * s + 0.38 * w + 0.12 * e for s, w, e in zip(shadow, weathered_rgb, soil_rgb))
    dust_rgb = tuple(0.40 * w + 0.42 * s + 0.18 * e for w, s, e in zip(weathered_rgb, palette["path_sand"]["linear_rgb"], soil_rgb))
    return {
        "weathered": limestone_material("ruin_blocks_ivory_limestone", fracture=False),
        "fresh": limestone_material("ruin_blocks_fresh_fracture", fracture=True),
        "crack": _simple_material("ruin_blocks_crack_shadow", crack_rgb, 0.96, 0.16),
        "dirt": vrmat.get("dirt_path"),
        "dust": _simple_material("ruin_blocks_lime_dust", dust_rgb, 0.94, 0.18),
        "moss": vrmat.get("mossy_rock"),
    }


# -----------------------------------------------------------------------------
# Small mesh utilities


def mesh_object(name, vertices, faces, materials, indices=None, smooth=False):
    data = bpy.data.meshes.new(name + "_mesh")
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, data))
    for mat in materials:
        data.materials.append(mat)
    if indices is None:
        indices = [0] * len(data.polygons)
    for poly, index in zip(data.polygons, indices):
        poly.material_index = index
        poly.use_smooth = bool(smooth)
    return obj


def non_source_object(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def remove_doubles(obj, dist=1e-5):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=dist)
    bm.to_mesh(obj.data)
    obj.data.update()
    bm.free()


# -----------------------------------------------------------------------------
# Fractured masonry blocks


def _fill_cut(bm, out, material_index):
    edges = [
        e
        for e in out["geom_cut"]
        if isinstance(e, bmesh.types.BMEdge) and e.is_valid and e.is_boundary
    ]
    if not edges:
        return
    result = bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    for face in result["faces"]:
        face.material_index = material_index


def _clip_plane(bm, point, normal, material_index):
    out = bmesh.ops.bisect_plane(
        bm,
        geom=[*bm.verts, *bm.edges, *bm.faces],
        dist=0.00001,
        plane_co=point,
        plane_no=normal,
        clear_outer=True,
    )
    _fill_cut(bm, out, material_index)


def fracture_relief(bm, rng):
    """Subdivide and gouge large fresh fracture faces instead of leaving planar cuts.

    The clipped faces are the light material-1 surfaces.  Each sufficiently large face
    is retriangulated with jittered interior samples; displacement fades to zero at the
    boundary so the watertight arrises remain continuous.
    """
    bm.normal_update()
    for face in list(bm.faces):
        if not face.is_valid or face.material_index != 1 or face.calc_area() < 0.045:
            continue
        normal = face.normal.copy()
        verts = list(face.verts)
        if len(verts) < 3:
            continue
        origin = face.calc_center_median()
        u = (verts[1].co - verts[0].co)
        if u.length < 1e-6:
            continue
        u.normalize()
        v = normal.cross(u)
        points = [Vector((u.dot(p.co - origin), v.dot(p.co - origin))) for p in verts]
        boundary = len(points)
        lo, hi = ([fn(p[k] for p in points) for k in range(2)] for fn in (min, max))
        dx, dy = hi[0] - lo[0], hi[1] - lo[1]
        if min(dx, dy) < 0.075:
            continue
        step = max(0.050, min(0.125, max(dx, dy) / 13))
        for i in range(int(dx / step)):
            for j in range(int(dy / step)):
                p = Vector(
                    (
                        lo[0] + (i + rng.uniform(0.18, 0.82)) * step,
                        lo[1] + (j + rng.uniform(0.18, 0.82)) * step,
                    )
                )
                if all(
                    (points[(k + 1) % boundary] - q).cross(p - q) > 0.010 * step
                    for k, q in enumerate(points[:boundary])
                ):
                    points.append(p)
        if len(points) == boundary:
            continue
        try:
            coords, _, pieces, ids, _, _ = delaunay_2d_cdt(
                points, [], [tuple(range(boundary))], 1, 1e-6
            )
        except Exception:
            continue
        amount = min(0.018, 0.055 * min(dx, dy))
        phi = rng.uniform(0, math.tau)
        bmesh.ops.delete(bm, geom=[face], context="FACES_ONLY")
        corners = []
        for (x, y), source in zip(coords, ids):
            if source and source[0] < boundary:
                corners.append(verts[source[0]])
                continue
            edge = min(
                (points[(k + 1) % boundary] - p).cross(Vector((x, y)) - p)
                / max(1e-6, (points[(k + 1) % boundary] - p).length)
                for k, p in enumerate(points[:boundary])
            )
            fade = min(1, max(0, edge / (2 * step)))
            q = 1.53 * x + 2.41 * y
            gouge = (
                math.sin(5.7 * q + phi) * 0.40
                + 0.30 * math.sin(13.0 * q - 4.7 * x + phi)
                + 0.18 * math.cos(20.0 * x + 35.0 * y)
                + 0.12 * math.sin(43.0 * x - 37.0 * y)
            )
            corners.append(
                bm.verts.new(origin + u * x + v * y + normal * (amount * fade * gouge))
            )
        for tri in pieces:
            try:
                new = bm.faces.new([corners[i] for i in tri])
                new.material_index = 1
            except ValueError:
                pass


def _surface_frame(face, w, d, h):
    """center, normalized-u axis, normalized-v axis, outward normal for a nominal box face."""
    if face == "front":
        return Vector((0, -d, 0)), Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0)), (w, h)
    if face == "back":
        return Vector((0, d, 0)), Vector((-1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0)), (w, h)
    if face == "right":
        return Vector((w, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)), (d, h)
    if face == "left":
        return Vector((-w, 0, 0)), Vector((0, -1, 0)), Vector((0, 0, 1)), Vector((-1, 0, 0)), (d, h)
    return Vector((0, 0, h)), Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)), (w, d)


def _jagged_polyline(rng, vertical=True):
    """Normalized jagged crack polyline, kept away from the face border."""
    count = rng.randint(6, 8)
    if vertical:
        u = rng.uniform(0.28, 0.72)
        pts = []
        for i in range(count):
            v = 0.985 - i * (0.97 / max(1, count - 1))
            u += rng.uniform(-0.135, 0.135)
            u = max(0.13, min(0.87, u))
            pts.append((u, v + rng.uniform(-0.020, 0.020)))
        return pts
    horizontal = rng.random() < 0.55
    u = rng.uniform(0.18, 0.35)
    v = rng.uniform(0.25, 0.75)
    pts = []
    for i in range(count):
        t = i / max(1, count - 1)
        if horizontal:
            uu = 0.065 + 0.87 * t
            vv = v + 0.19 * (t - 0.5) + rng.uniform(-0.085, 0.085)
        else:
            uu = u + 0.25 * (t - 0.5) + rng.uniform(-0.085, 0.085)
            vv = 0.065 + 0.87 * t
        pts.append((max(0.055, min(0.945, uu)), max(0.055, min(0.945, vv))))
    return pts


def _crack_polylines(dims, seed, amount):
    dx, dy, dz = dims
    rng = random.Random(seed + 9100)
    faces = []
    vertical_faces = ["front", "back", "right", "left"]
    rng.shuffle(vertical_faces)
    # Tall stones need legible vertical fractures; low slabs read mainly from above.
    vertical_count = 1 + int(dz > 0.65 and amount > 0.42)
    for face in vertical_faces[:vertical_count]:
        faces.append((face, True))
    if rng.random() < 0.94:
        faces.append(("top", False))
    if amount > 0.76 and rng.random() < 0.28:
        faces.append((vertical_faces[-1], True))
    result = []
    for face, vertical in faces:
        main = _jagged_polyline(rng, vertical=vertical)
        result.append((face, main, 1.0))
        if rng.random() < 0.74:
            # Short branch starting around the middle of the main fissure.
            mu, mv = main[len(main) // 2]
            branch = [(mu, mv)]
            du = rng.choice((-1, 1)) * rng.uniform(0.12, 0.22)
            dv = rng.choice((-1, 1)) * rng.uniform(0.10, 0.20)
            branch.append((max(0.13, min(0.87, mu + du * 0.55)), max(0.13, min(0.87, mv + dv * 0.45))))
            branch.append((max(0.13, min(0.87, mu + du)), max(0.13, min(0.87, mv + dv))))
            result.append((face, branch, 0.58))
    return result


def _signed_volume(vertices, faces):
    volume = 0.0
    for face in faces:
        v0 = vertices[face[0]]
        for i in range(1, len(face) - 1):
            volume += v0.dot(vertices[face[i]].cross(vertices[face[i + 1]])) / 6.0
    return volume


def _crack_cutter(name, dims, cracks, seed, material):
    """Build one watertight triangular V-section cutter per crack polyline.

    The two lip vertices sit just outside the dressed face and the apex reaches into
    the stone.  Width and depth taper toward the ends, avoiding the rectangular,
    drilled look of box cutters.  Separate manifold cutters are much more reliable in
    Exact booleans than one self-intersecting mesh containing all branches.
    """
    dx, dy, dz = dims
    w, d, h = dx / 2, dy / 2, dz / 2
    rng = random.Random(seed + 12200)
    shortest = min(dx, dy, dz)
    cutters = []
    segments = []
    for crack_index, (face, polyline, width_scale) in enumerate(cracks):
        center0, axis_u0, axis_v0, outward, half_uv = _surface_frame(face, w, d, h)
        points = [
            center0
            + axis_u0 * ((u - 0.5) * 2 * half_uv[0])
            + axis_v0 * ((v - 0.5) * 2 * half_uv[1])
            for u, v in polyline
        ]
        if len(points) < 2:
            continue
        base_half_width = max(0.014, min(0.040, shortest * rng.uniform(0.024, 0.040) * width_scale))
        base_depth = max(0.085, min(0.22, shortest * rng.uniform(0.15, 0.23)))
        vertices = []
        stations = []
        previous_across = None
        for i, point in enumerate(points):
            before = points[max(0, i - 1)]
            after = points[min(len(points) - 1, i + 1)]
            tangent = after - before
            if tangent.length < 1e-6:
                continue
            tangent.normalize()
            across = outward.cross(tangent)
            if across.length < 1e-6:
                continue
            across.normalize()
            if previous_across is not None and across.dot(previous_across) < 0:
                across.negate()
            previous_across = across.copy()

            if len(points) == 2:
                shape = 0.72
            else:
                shape = math.sin(math.pi * i / (len(points) - 1))
            width_taper = 0.10 + 0.90 * shape ** 0.55
            depth_taper = 0.04 + 0.96 * shape ** 1.45
            if width_scale < 0.8 and i == 0:
                # Branch cracks begin inside the parent fissure; only their outer tip tapers away.
                width_taper = max(width_taper, 0.58)
                depth_taper = max(depth_taper, 0.48)
            half_width = base_half_width * width_taper * rng.uniform(0.62, 1.38)
            depth = base_depth * depth_taper * rng.uniform(0.75, 1.25)
            lip_centre = point + outward * 0.018
            apex = point - outward * depth + across * rng.uniform(-0.18, 0.18) * half_width
            vertices.extend(
                (
                    lip_centre - across * half_width,
                    lip_centre + across * half_width,
                    apex,
                )
            )
            stations.append(
                {
                    "point": point.copy(),
                    "tangent": tangent.copy(),
                    "across": across.copy(),
                    "half_width": half_width,
                    "depth": depth,
                }
            )
        if len(stations) < 2:
            continue
        faces = [(2, 1, 0)]
        for i in range(len(stations) - 1):
            for k in range(3):
                p, q = 3 * i + k, 3 * i + (k + 1) % 3
                faces.append((p, q, q + 3, p + 3))
        top = len(vertices) - 3
        faces.append((top, top + 1, top + 2))
        mesh = bpy.data.meshes.new(f"{name}_crack_{crack_index:02d}_mesh")
        # Face winding depends on the crack direction and surface orientation.  Exact
        # booleans are only safe with a positive outward-oriented cutter volume, so
        # measure the closed prism and flip it when a particular path wound the other way.
        oriented_faces = [tuple(reversed(f)) for f in faces]
        if _signed_volume(vertices, oriented_faces) < 0.0:
            oriented_faces = [tuple(reversed(f)) for f in oriented_faces]
        mesh.from_pydata([tuple(v) for v in vertices], [], oriented_faces)
        mesh.update()
        mesh.materials.append(material)
        cutters.append(non_source_object(f"{name}_crack_{crack_index:02d}", mesh))

        for a, b in zip(stations, stations[1:]):
            direction = b["point"] - a["point"]
            length = direction.length
            if length < 0.02:
                continue
            axis_u = direction.normalized()
            axis_v = outward.cross(axis_u)
            if axis_v.length < 1e-6:
                continue
            axis_v.normalize()
            segments.append(
                {
                    "p0": a["point"].copy(),
                    "axis_u": axis_u,
                    "axis_v": axis_v,
                    "outward": outward.copy(),
                    "length": length,
                    "width": (a["half_width"] + b["half_width"]),
                    "depth": (a["depth"] + b["depth"]) * 0.5,
                }
            )
    return cutters, segments


def _mark_crack_faces(obj, segments):
    """Assign the dark crevice material only to faces inside the carved grooves.

    Blender's Exact boolean does not reliably propagate cutter materials in 5.2,
    so ownership is recovered geometrically in the untransformed block space.
    Original coplanar ashlar faces are excluded by their outward normal and by
    their almost-zero surface distance.
    """
    if not segments:
        return 0
    marked = 0
    for poly in obj.data.polygons:
        center = poly.center
        normal = poly.normal
        for seg in segments:
            rel = center - seg["p0"]
            along = rel.dot(seg["axis_u"])
            if along < -seg["width"] * 0.55 or along > seg["length"] + seg["width"] * 0.55:
                continue
            across = rel.dot(seg["axis_v"])
            if abs(across) > seg["width"] * 0.72 + 0.006:
                continue
            out = rel.dot(seg["outward"])
            if out < -seg["depth"] - 0.028 or out > 0.014:
                continue
            side_or_bottom = normal.dot(seg["outward"]) < 0.82
            genuinely_recessed = out < -0.009
            if side_or_bottom or genuinely_recessed:
                poly.material_index = 2
                marked += 1
                break
    return marked


def _mesh_extent_signature(mesh):
    if not mesh.vertices:
        return (0.0, 0.0, 0.0)
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def _apply_boolean_difference(obj, cutter):
    """Apply one crack boolean, rolling back catastrophic Exact-solver collapses.

    Coplanar clipped/retriangulated ruin surfaces are difficult boolean operands.
    A valid groove normally adds vertices; if the solver instead collapses the block
    to a fragment, restoring the pre-cut mesh is visibly far better than losing the
    whole masonry piece.
    """
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    backup = obj.data.copy()
    before_vertices = len(obj.data.vertices)
    before_extent = _mesh_extent_signature(obj.data)
    mod = obj.modifiers.new("Carved crack grooves", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    if hasattr(mod, "use_self"):
        mod.use_self = True
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        success = True
    except RuntimeError:
        success = False
        try:
            obj.modifiers.remove(mod)
        except RuntimeError:
            pass
    if success:
        after_vertices = len(obj.data.vertices)
        after_extent = _mesh_extent_signature(obj.data)
        before_volume = max(1e-8, before_extent[0] * before_extent[1] * before_extent[2])
        after_volume = max(1e-8, after_extent[0] * after_extent[1] * after_extent[2])
        catastrophic = after_vertices < max(24, int(before_vertices * 0.42)) or after_volume < before_volume * 0.42
        if catastrophic:
            damaged = obj.data
            obj.data = backup
            bpy.data.meshes.remove(damaged)
            success = False
        else:
            bpy.data.meshes.remove(backup)
    else:
        bpy.data.meshes.remove(backup)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return success


def fractured_block(
    name,
    dims,
    center_xy,
    yaw_deg,
    pitch_deg,
    roll_deg,
    embed,
    seed,
    fracture,
    materials,
):
    """Create one solid clipped ashlar fragment, with all transforms baked into vertices."""
    dx, dy, dz = dims
    w, d, h = dx / 2, dy / 2, dz / 2
    rng = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= d
        v.co.z *= h

    # Worn, slightly unequal arrises on all twelve edges.
    planes = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            bevel = rng.uniform(0.035, 0.095) * min(w, d)
            planes.append(((sx * (w - bevel), sy * d, 0), (sx * rng.uniform(0.65, 1.25), sy, 0), 0))
        for sz in (-1, 1):
            bevel = rng.uniform(0.025, 0.075) * min(w, h)
            planes.append(((sx * w, 0, sz * (h - bevel)), (sx, 0, sz * rng.uniform(0.68, 1.25)), 0))
    for sy in (-1, 1):
        for sz in (-1, 1):
            bevel = rng.uniform(0.030, 0.085) * min(d, h)
            planes.append(((0, sy * d, sz * (h - bevel)), (0, sy, sz * rng.uniform(0.68, 1.25)), 0))

    # Broad broken corners and end spalls.  These are genuine clipped planes, not a bump trick.
    break_count = 2 + int(round(2 + fracture * 3.2))
    for _ in range(break_count):
        sx = rng.choice((-1, 1))
        sy = rng.choice((-1, 1))
        sz = rng.choice((-1, 1))
        deep = 0.70 - fracture * 0.10
        point = (
            sx * w * rng.uniform(deep + 0.08, 1.00),
            sy * d * rng.uniform(deep + 0.10, 1.02),
            sz * h * rng.uniform(deep + 0.03, 0.99),
        )
        normal = (
            sx * rng.uniform(0.45, 1.10),
            sy * rng.uniform(0.58, 1.36),
            sz * rng.uniform(0.50, 1.32),
        )
        planes.append((point, normal, 1))

    # A few side spalls break the otherwise cuboid rhythm.
    for _ in range(int(fracture * 3.0)):
        face_axis = rng.choice("xyz")
        sign = rng.choice((-1, 1))
        if face_axis == "x":
            point = (sign * w * rng.uniform(0.84, 1.01), rng.uniform(-0.45, 0.45) * d, rng.uniform(-0.55, 0.70) * h)
            normal = (sign * rng.uniform(0.8, 1.5), rng.uniform(-0.35, 0.35), rng.uniform(-0.25, 0.45))
        elif face_axis == "y":
            point = (rng.uniform(-0.45, 0.45) * w, sign * d * rng.uniform(0.84, 1.01), rng.uniform(-0.55, 0.70) * h)
            normal = (rng.uniform(-0.35, 0.35), sign * rng.uniform(0.8, 1.5), rng.uniform(-0.25, 0.45))
        else:
            point = (rng.uniform(-0.50, 0.50) * w, rng.uniform(-0.45, 0.45) * d, sign * h * rng.uniform(0.80, 1.01))
            normal = (rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), sign * rng.uniform(0.8, 1.5))
        planes.append((point, normal, 1))

    # Smaller stepped arris losses.  Repeating shallow cuts at different heights avoids
    # the "single clean chamfer" look and creates readable chipped silhouette notches.
    notch_count = 2 + int(round(fracture * 4.0))
    for _ in range(notch_count):
        sx = rng.choice((-1, 1))
        sy = rng.choice((-1, 1))
        sz = rng.choice((-1, 1))
        if rng.random() < 0.58:
            # Vertical corner loss localized to part of the height.
            bite_x = min(w, d) * rng.uniform(0.09, 0.22)
            bite_y = min(w, d) * rng.uniform(0.09, 0.22)
            z0 = rng.uniform(-0.66, 0.68) * h
            point = (sx * (w - bite_x), sy * (d - bite_y), z0)
            normal = (
                sx * rng.uniform(0.78, 1.30),
                sy * rng.uniform(0.78, 1.30),
                rng.uniform(-0.62, 0.62),
            )
        else:
            # Top/bottom edge loss; the horizontal normal component localizes the wedge.
            along_x = rng.random() < 0.55
            if along_x:
                point = (
                    rng.uniform(-0.48, 0.48) * w,
                    sy * (d - min(d, h) * rng.uniform(0.08, 0.20)),
                    sz * (h - min(d, h) * rng.uniform(0.08, 0.20)),
                )
                normal = (
                    rng.uniform(-0.72, 0.72),
                    sy * rng.uniform(0.80, 1.28),
                    sz * rng.uniform(0.78, 1.24),
                )
            else:
                point = (
                    sx * (w - min(w, h) * rng.uniform(0.08, 0.20)),
                    rng.uniform(-0.48, 0.48) * d,
                    sz * (h - min(w, h) * rng.uniform(0.08, 0.20)),
                )
                normal = (
                    sx * rng.uniform(0.80, 1.28),
                    rng.uniform(-0.72, 0.72),
                    sz * rng.uniform(0.78, 1.24),
                )
        planes.append((point, normal, 1))

    for point, normal, fresh in planes:
        _clip_plane(bm, point, normal, fresh)
    fracture_relief(bm, rng)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))

    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, mesh))
    for mat in (materials["weathered"], materials["fresh"], materials["crack"]):
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = False

    # Boolean-cut tapered V-shaped crack grooves.  Each polyline is a separate manifold
    # cutter; even if one difficult boolean is rejected, the remaining fissures survive.
    cracks = _crack_polylines(dims, seed, fracture)
    cutters, crack_segments = _crack_cutter(name, dims, cracks, seed, materials["crack"])
    crack_cuts = 0
    for cutter in cutters:
        crack_cuts += int(_apply_boolean_difference(obj, cutter))
    crack_faces = _mark_crack_faces(obj, crack_segments) if crack_cuts else 0
    remove_doubles(obj, 2e-5)

    rotation = Euler((math.radians(pitch_deg), math.radians(roll_deg), math.radians(yaw_deg)), "XYZ").to_matrix()
    rotated_z = []
    for vertex in obj.data.vertices:
        vertex.co = rotation @ vertex.co
        rotated_z.append(vertex.co.z)
    # Ground a low percentile rather than one fortuitous clipping vertex.  This makes
    # a small bottom edge/patch intersect the earth, so the blocks read settled rather
    # than balanced on a single point.
    rotated_z.sort()
    contact_index = max(1, min(len(rotated_z) - 1, int(len(rotated_z) * 0.055)))
    reference_z = rotated_z[contact_index]
    z_shift = -embed - reference_z
    for vertex in obj.data.vertices:
        vertex.co += Vector((center_xy[0], center_xy[1], z_shift))
    obj.data.update()

    bevel_width = min(0.038, max(0.018, min(dx, dy, dz) * 0.030))
    bevel = obj.modifiers.new("Worn chipped arrises", "BEVEL")
    bevel.width = bevel_width
    bevel.segments = 2
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = 0.36
    if hasattr(bevel, "harden_normals"):
        bevel.harden_normals = True
    weld = obj.modifiers.new("Weld boolean microvertices", "WELD")
    weld.merge_threshold = 0.00005
    normal = obj.modifiers.new("Preserve dressed flats", "WEIGHTED_NORMAL")
    normal.keep_sharp = True
    obj["ruin_piece"] = True
    obj["nominal_size_m"] = [round(dx, 3), round(dy, 3), round(dz, 3)]
    obj["crack_faces_darkened"] = crack_faces
    obj["crack_cutters_applied"] = crack_cuts
    return obj


# -----------------------------------------------------------------------------
# Ground integration: compacted earth/lime bed and solid moss accumulation


def rubble_bed(materials):
    rng = random.Random(424242)
    n_ang = 64
    n_rings = 5
    rx, ry = 3.62, 2.18
    verts = [(0.0, 0.0, 0.105)]
    ring_start = []
    for j in range(1, n_rings + 1):
        frac = j / n_rings
        ring_start.append(len(verts))
        for i in range(n_ang):
            a = math.tau * i / n_ang
            edge_wobble = 1.0 + 0.075 * math.sin(3 * a + 0.7) + 0.045 * math.sin(7 * a - 0.3)
            inner_wobble = 1.0 + (1.0 - frac) * 0.035 * math.sin(5 * a + 1.2)
            rscale = edge_wobble * inner_wobble
            x = rx * frac * rscale * math.cos(a)
            y = ry * frac * rscale * math.sin(a)
            crown = (1.0 - frac) ** 1.55 * 0.095
            uneven = (0.012 + 0.020 * (1.0 - frac)) * (
                math.sin(4.7 * x + 1.9 * y) * 0.55 + math.sin(7.3 * y - 1.1 * x) * 0.45
            )
            z = 0.012 + crown + uneven
            verts.append((x, y, z))

    faces = []
    indices = []
    # Center fan.
    first = ring_start[0]
    for i in range(n_ang):
        ni = (i + 1) % n_ang
        a = math.tau * (i + 0.5) / n_ang
        faces.append((0, first + i, first + ni))
        indices.append(1 if math.sin(2.0 * a + 0.55) + 0.55 * math.sin(5.0 * a - 1.2) > 0.78 else 0)
    # Ring quads.
    for j in range(n_rings - 1):
        inner = ring_start[j]
        outer = ring_start[j + 1]
        frac = (j + 1.5) / n_rings
        for i in range(n_ang):
            ni = (i + 1) % n_ang
            a = math.tau * (i + 0.5) / n_ang
            faces.append((inner + i, outer + i, outer + ni, inner + ni))
            patch = math.sin(2.0 * a + 0.55 + j * 0.28) + 0.55 * math.sin(5.0 * a - 1.2)
            lime = frac < 0.76 and patch > 0.72
            indices.append(1 if lime else 0)

    # Solid vertical skirt and closed underside.  The skirt reaches well below z=0.
    outer = ring_start[-1]
    skirt_start = len(verts)
    for i in range(n_ang):
        x, y, _ = verts[outer + i]
        verts.append((x, y, -0.24))
    bottom_center = len(verts)
    verts.append((0.0, 0.0, -0.24))
    for i in range(n_ang):
        ni = (i + 1) % n_ang
        faces.append((outer + i, skirt_start + i, skirt_start + ni, outer + ni))
        indices.append(0)
    for i in range(n_ang):
        ni = (i + 1) % n_ang
        faces.append((bottom_center, skirt_start + ni, skirt_start + i))
        indices.append(0)

    obj = mesh_object(
        "compacted earth and lime bed",
        verts,
        faces,
        (materials["dirt"], materials["dust"]),
        indices,
        smooth=True,
    )
    obj["ground_integration"] = True
    return obj


def moss_patch(name, center, rx, ry, thickness, yaw_deg, seed, material):
    """Low closed moss accumulation with a scalloped footprint, not a circular decal."""
    rng = random.Random(seed)
    n_ang = 30
    n_rings = 3
    phase = rng.uniform(0, math.tau)
    yaw = math.radians(yaw_deg)
    rot = Euler((0, 0, yaw), "XYZ").to_matrix()
    cx, cy, cz = center
    verts = [(cx, cy, cz + thickness * 0.82)]
    ring_start = []

    def outline_scale(angle):
        return (
            1.0
            + 0.19 * math.sin(3.0 * angle + phase)
            + 0.11 * math.sin(7.0 * angle - 1.7 * phase)
            + 0.045 * math.sin(11.0 * angle + 0.4 * phase)
        )

    for j in range(1, n_rings + 1):
        frac = j / n_rings
        ring_start.append(len(verts))
        for i in range(n_ang):
            a = math.tau * i / n_ang
            scallop = outline_scale(a)
            rscale = 1.0 + (scallop - 1.0) * frac ** 0.72
            lx = rx * frac * rscale * math.cos(a)
            ly = ry * frac * rscale * math.sin(a)
            p = rot @ Vector((lx, ly, 0.0))
            cushion = (1.0 - frac ** 1.45) * thickness * (0.78 + 0.12 * math.sin(4.0 * a + phase))
            uneven = thickness * 0.16 * (1.0 - frac) * math.sin(6.0 * a + 3.0 * frac + phase)
            verts.append((cx + p.x, cy + p.y, cz + cushion + uneven))

    faces = []
    first = ring_start[0]
    for i in range(n_ang):
        faces.append((0, first + i, first + (i + 1) % n_ang))
    for j in range(n_rings - 1):
        inner = ring_start[j]
        outer = ring_start[j + 1]
        for i in range(n_ang):
            ni = (i + 1) % n_ang
            faces.append((inner + i, outer + i, outer + ni, inner + ni))

    # A short vertical skirt and closed underside make the pad volumetric even where
    # it is partly buried by the lime bed.
    outer = ring_start[-1]
    skirt_start = len(verts)
    for i in range(n_ang):
        x, y, _ = verts[outer + i]
        verts.append((x, y, cz - 0.018))
    bottom_center = len(verts)
    verts.append((cx, cy, cz - 0.018))
    for i in range(n_ang):
        ni = (i + 1) % n_ang
        faces.append((outer + i, skirt_start + i, skirt_start + ni, outer + ni))
    for i in range(n_ang):
        ni = (i + 1) % n_ang
        faces.append((bottom_center, skirt_start + ni, skirt_start + i))

    obj = mesh_object(name, verts, faces, (material,), smooth=True)
    obj["moss_accumulation"] = True
    return obj


# -----------------------------------------------------------------------------
# Asset assembly


def build():
    materials = make_materials()
    rubble_bed(materials)

    # Ten masonry fragments, all in the 0.8–3.8 m target band.  Tilts are small enough
    # that the pieces read as settled; every lowest vertex is intentionally buried.
    specs = [
        # name, dims, center xy, yaw, pitch, roll, embed, seed, fracture
        ("rear fractured pier", (1.45, 1.05, 2.65), (0.15, 1.15), 7, 2, -2, 0.17, 1101, 0.72),
        ("left broken wall tooth", (1.80, 0.90, 2.25), (-2.15, 0.55), 15, -1, 3, 0.18, 1202, 0.78),
        ("right slumped ashlar mass", (2.40, 1.55, 1.35), (1.65, 0.55), -17, 2, -4, 0.18, 1303, 0.66),
        ("central long fallen lintel", (3.80, 1.15, 0.85), (-0.25, -0.15), -8, 0, -2, 0.18, 1404, 0.68),
        ("diagonal cap beam", (3.10, 0.72, 0.68), (0.55, -0.35), -43, 4, 2, 0.14, 1505, 0.61),
        ("front left wedge", (1.50, 1.05, 0.82), (-2.45, -1.20), 23, -1, 2, 0.14, 1606, 0.63),
        ("front center block", (1.10, 0.90, 0.68), (-0.45, -1.65), -5, 1, -2, 0.12, 1707, 0.50),
        ("front right slab", (1.65, 1.00, 0.55), (1.85, -1.18), -20, -1, 2, 0.12, 1808, 0.64),
        ("right end upright fragment", (0.95, 0.82, 1.05), (3.00, -0.05), 10, 2, -2, 0.14, 1909, 0.68),
        ("far left small fracture", (0.85, 0.80, 0.72), (-3.15, -0.15), -12, 1, 2, 0.12, 2010, 0.55),
    ]
    for args in specs:
        fractured_block(*args, materials=materials)

    moss_specs = [
        ((-2.72, -0.72, 0.025), 0.46, 0.28, 0.036, 18, 3101),
        ((-1.08, -1.34, 0.018), 0.40, 0.24, 0.032, -9, 3102),
        ((0.82, -1.33, 0.020), 0.36, 0.22, 0.030, 27, 3103),
        ((2.58, -0.70, 0.022), 0.43, 0.25, 0.034, -22, 3104),
        ((-1.83, 0.72, 0.020), 0.34, 0.21, 0.030, 42, 3105),
        ((0.12, 1.76, 0.018), 0.40, 0.23, 0.031, 5, 3106),
        ((2.55, 0.95, 0.020), 0.36, 0.22, 0.030, -35, 3107),
        ((-3.16, 0.34, 0.018), 0.30, 0.18, 0.027, 14, 3108),
    ]
    for i, (center, rx, ry, thickness, yaw, seed) in enumerate(moss_specs):
        moss_patch(f"moss accumulation {i + 1:02d}", center, rx, ry, thickness, yaw, seed, materials["moss"])

    # Scale figure and closeups are placed to show both the tall fractures and the ground integration.
    scene = bpy.context.scene
    scene["vr_review_turn"] = (0.05, -0.10, 0.72, 32.0, 17.0, 11.2)
    scene["vr_review_figure"] = (4.12, 1.05, 0.0)
    scene["vr_closeup_upper"] = (0.05, 0.90, 1.45, 62.0, 10.0, 4.5)
    scene["vr_closeup_base"] = (-0.30, -0.80, 0.40, 205.0, 17.0, 4.2)
