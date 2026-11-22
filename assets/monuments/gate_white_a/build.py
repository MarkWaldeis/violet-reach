"""Floodmark Gate: three orders of limestone above a worn ford threshold."""

import math
import random

import bmesh
import bpy
from mathutils import Vector

import vrlib
import vrmat


SPRING = 15.4
INNER = 12.2


def finish():
    palette = vrmat.load_palette()
    cream = palette["monument_white"]["linear_rgb"]
    shades = []
    for i in range(12):
        mat = vrmat.get("monument_white").copy()
        mat.name = f"Dressed limestone | bed {i + 1:02}"
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        surface = nodes["Principled BSDF"]
        old_color = surface.inputs["Base Color"].links[0].from_socket
        tone = .87 + .018 * i
        warm = math.sin(1.93 * i)
        color = tuple(c * tone * s for c, s in zip(cream, (1 + .026 * warm, 1, 1 - .05 * warm)))
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs[0].default_value = .64
        mix.inputs[2].default_value = (*color, 1)
        links.new(old_color, mix.inputs[1])
        links.new(mix.outputs[0], surface.inputs["Base Color"])
        surface.inputs["Specular IOR Level"].default_value = .23
        old_normal = surface.inputs["Normal"].links[0].from_socket
        coords = next(node for node in nodes if node.type == "TEX_COORD")
        grit = nodes.new("ShaderNodeTexNoise")
        grit.inputs["Scale"].default_value = 8
        grit.inputs["Detail"].default_value = 3
        links.new(coords.outputs["Object"], grit.inputs["Vector"])
        relief = nodes.new("ShaderNodeBump")
        relief.inputs["Strength"].default_value = .31
        relief.inputs["Distance"].default_value = .022
        links.new(old_normal, relief.inputs["Normal"])
        links.new(grit.outputs["Fac"], relief.inputs["Height"])
        links.new(relief.outputs["Normal"], surface.inputs["Normal"])
        shades.append(mat)
    mortar = vrmat.get("monument_weathered").copy()
    mortar.name = "Recessed silty lime mortar"
    surface = mortar.node_tree.nodes["Principled BSDF"]
    source = surface.inputs["Base Color"].links[0].from_socket
    multiply = mortar.node_tree.nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs[0].default_value = 1
    multiply.inputs[2].default_value = (.39, .38, .32, 1)
    mortar.node_tree.links.new(source, multiply.inputs[1])
    mortar.node_tree.links.new(multiply.outputs[0], surface.inputs["Base Color"])
    return shades, mortar


def mesh(name, verts, faces, mat, cuts=(), rounding=0, curved=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(-y, x, z) for x, y, z in verts], [], faces)
    data.update()
    if cuts or rounding:
        bm = bmesh.new()
        bm.from_mesh(data)
        for point, normal in cuts:
            x, y, z = point
            nx, ny, nz = normal
            result = bmesh.ops.bisect_plane(
                bm, geom=[*bm.verts, *bm.edges, *bm.faces], dist=1e-6,
                plane_co=(-y, x, z), plane_no=(-ny, nx, nz), clear_outer=True,
            )
            rim = [edge for edge in result["geom_cut"]
                   if isinstance(edge, bmesh.types.BMEdge) and edge.is_valid and edge.is_boundary]
            if rim:
                bmesh.ops.holes_fill(bm, edges=rim)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    data.materials.append(mat)
    if rounding:
        for face in data.polygons:
            face.use_smooth = True
        bevel = obj.modifiers.new("Weathered arrises", "BEVEL")
        bevel.width, bevel.segments, bevel.angle_limit = rounding, 3, .20
        if not curved:
            obj.modifiers.new("Broad dressed faces", "WEIGHTED_NORMAL")
    return obj


def ashlar(name, x0, x1, y0, y1, z0, z1, mat, rng, wear=.08, shift=(0, 0), beds=()):
    dx, dy = shift
    verts = [(a + dx * j, b + dy * j, z)
             for j, z in enumerate((z0, z1))
             for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7)] + [
        (i, (i + 1) % 4, (i + 1) % 4 + 4, i + 4) for i in range(4)
    ]
    cuts = list(beds)
    if wear:
        for _ in range(1 + (rng.random() < .33)):
            sx, sy, sz = (rng.choice((-1, 1)) for _ in range(3))
            depth = rng.uniform(wear * .65, wear * 2.7)
            x = (x0 if sx < 0 else x1) + dx * (sz > 0)
            y = (y0 if sy < 0 else y1) + dy * (sz > 0)
            cuts.append(((x - sx * depth, y, z0 if sz < 0 else z1),
                         (sx, rng.uniform(.4, 1.3) * sy, rng.uniform(.58, 1.7) * sz)))
    return mesh(name, verts, faces, mat, cuts, wear * rng.uniform(.33, .62))


def ring(name, lo, hi, profile, mat, rounding, rng):
    steps = max(5, math.ceil((hi - lo) * 130))
    n = len(profile)
    verts = []
    phase = rng.uniform(0, math.tau) if rounding else 0
    for j in range(steps + 1):
        u = j / steps
        t = lo + (hi - lo) * u
        for r, y in profile:
            erosion = math.sin(math.pi * u)**2 if rounding else 0
            dr = erosion * (.021 * math.sin(6*u + .55*y + phase) + .008 * math.sin(13*u + y))
            dy = erosion * (.019 * math.sin(7*u + r + phase) + .005 * math.sin(18*u + 2*r))
            verts.append(((r+dr) * math.cos(t), y+dy, SPRING + (r+dr) * math.sin(t)))
    faces = [tuple(reversed(range(n)))]
    faces.extend((j * n + k, j * n + (k + 1) % n,
                  (j + 1) * n + (k + 1) % n, (j + 1) * n + k)
                 for j in range(steps) for k in range(n))
    faces.append(tuple(range(steps * n, (steps + 1) * n)))
    cuts = ()
    if rounding and rng.random() < .66:
        t = rng.choice((lo, hi))
        dr = rng.uniform(.09, .36)
        side = rng.choice((-1, 1))
        r, y = max(profile, key=lambda p: p[0] + .095 * p[1] * side)
        offset = -1 if t == lo else 1
        c, s = math.cos(t), math.sin(t)
        cuts = (((c * (r - dr), y, SPRING + s * (r - dr)),
                 (c - offset * s, side * rng.uniform(.44, .91), s + offset * c)),)
    obj = mesh(name, verts, faces, mat, cuts, rounding, curved=True)
    if rounding:
        obj.data.set_sharp_from_angle(angle=.26)
    elif not cuts:
        for face in obj.data.polygons[1:-1]:
            face.use_smooth = True


def arch(shades, mortar, rng):
    ring("Continuous mortar backing", -.004, math.pi + .004,
         [(INNER + .065, -3.45), (17.54, -3.45), (17.54, 3.45), (INNER + .065, 3.45)],
         mortar, 0, rng)
    profiles = (
        ("Through voussoir", [(INNER, -3.95), (INNER + .16, -4.10), (14.04, -4.10),
                              (14.16, -3.89), (14.16, 3.89), (14.04, 4.10),
                              (INNER + .16, 4.10), (INNER, 3.95)], 21, .071),
        ("Main archivolt", [(14.02, -3.98), (14.28, -4.31), (14.48, -4.42),
                            (16.49, -4.42), (16.65, -4.21), (16.65, 4.21),
                            (16.49, 4.42), (14.48, 4.42), (14.28, 4.31), (14.02, 3.98)], 19, .085),
        ("Drip mould", [(16.63, -3.99), (16.70, -4.27), (16.87, -4.47), (17.15, -4.51),
                        (17.36, -4.37), (17.55, -4.08), (17.61, -3.66), (17.61, 3.66),
                        (17.55, 4.08), (17.36, 4.37), (17.15, 4.51), (16.87, 4.47),
                        (16.70, 4.27), (16.63, 3.99)], 27, .043),
    )
    for order, profile, count, radius in profiles:
        # A continuous lime bed behind each face order closes the angular joints.
        inner, outer = min(r for r, _ in profile), max(r for r, _ in profile)
        depth = max(y for _, y in profile) - .15
        bed = [(inner + .065, -depth), (outer - .055, -depth),
               (outer - .055, depth), (inner + .065, depth)]
        ring(f"{order} recessed beds", 0, math.pi, bed, mortar, 0, rng)
        angles = [0] + [(i + rng.uniform(-.25, .25)) * math.pi / count for i in range(1, count)] + [math.pi]
        for i, (a, b) in enumerate(zip(angles, angles[1:])):
            front = rng.uniform(-.028, .028)
            key = i == count // 2 and order == "Main archivolt"
            stone = [(r + (max(0, r - 14.15) * .092 if key else 0),
                      y + math.copysign(front + (.28 if key else 0), y)) for r, y in profile]
            ring(f"{order} {i + 1:02}" if not key else "Crown keystone",
                 a + .0014, b - .0014, stone, rng.choice(shades), radius, rng)


def pier(sign, shades, mortar, rng):
    def interval(a, b):
        return (a, b) if sign > 0 else (-b, -a)

    # The battered lower wall carries a coved square impost which meets all three orders.
    courses = [(-.052, .57, 11.62, 18.82, 4.98), (.57, 1.18, 11.77, 18.60, 4.80),
               (1.18, 1.71, 11.94, 18.36, 4.57), (1.71, 3.11, 12.18, 18.09, 4.29),
               (3.11, 4.67, 12.20, 17.96, 4.18), (4.67, 6.28, 12.20, 17.81, 4.10),
               (6.28, 7.98, 12.20, 17.67, 4.02), (7.98, 9.45, 12.20, 17.55, 3.97),
               (9.45, 11.22, 12.20, 17.44, 3.91), (11.22, 13.01, 12.20, 17.37, 3.89),
               (13.01, 13.96, 12.18, 17.43, 3.94), (13.96, 14.40, 12.13, 17.50, 4.12),
               (14.40, 14.91, 12.01, 17.63, 4.30), (14.91, SPRING, 12.06, 17.70, 4.45)]
    for i, (z0, z1, x0, x1, depth) in enumerate(courses):
        a, b = interval(x0, x1)
        label = f"{'North' if sign > 0 else 'South'} pier bed {i + 1:02}"
        ashlar(label + " lime core", a + .13, b - .13, -depth + .14, depth - .14,
               z0, z1 + (.04 if i == len(courses) - 1 else .10), mortar, rng, 0)
        mid = (a + b) / 2
        ycut = rng.uniform(-.76, .76)
        for j, (f, g) in enumerate(((-depth, ycut - .022), (ycut + .022, depth))):
            cuts = [a, mid + (-1 if (i + j) % 2 else 1) * rng.uniform(.43, 1.10), b]
            for k, (lo, hi) in enumerate(zip(cuts, cuts[1:])):
                face_offset = rng.uniform(-.028, .028)
                early = i < 2 or (i == 2 and rng.random() < .60)
                stone = vrmat.get("monument_weathered") if early else rng.choice(shades)
                ashlar(f"{label} ashlar {j * 2 + k + 1}", lo + (.022 if k else 0),
                       hi - (.022 if not k else 0), f + face_offset, g + face_offset,
                       z0 + (.012 if i else 0), z1 - .012, stone, rng, .14 if early else .11)


def turf(sign, shades, rng):
    centre = sign * 15.8
    soil, grass = vrmat.get("forest_soil"), vrmat.get("grass_ground")
    mats = (soil, grass, vrmat.get("foliage_leaf"))
    n = 80
    coords = []
    for u in (.30, .57, .78, .92, 1):
        for j in range(n):
            t = j * math.tau / n
            wobble = 1 + .08 * math.sin(3 * t + sign) + .06 * math.cos(7 * t - sign)
            x = centre + 6.7 * u * wobble * math.cos(t)
            y = 8.2 * u * wobble * math.sin(t)
            h = .75 * (1 - u) ** 1.31 * (1 + .32 * math.sin(4 * t)) - .035
            coords.append((x, y, h))
    faces = [tuple(range(n))]
    faces.extend((n*i+j, n*(i+1)+j, n*(i+1)+(j+1)%n, n*i+(j+1)%n)
                 for i in range(4) for j in range(n))
    sod = mesh("Irregular soil and turf apron", coords, faces, grass)
    sod.data.materials.append(soil)
    for f in sod.data.polygons:
        f.use_smooth = True
        t = (f.index-1) * math.tau/n
        if math.sin(5*t+sign) + .57*math.sin(9*t-sign) > .93:
            f.material_index = 1
    leaves, blades = [], []
    clusters = [rng.uniform(0, math.tau) for _ in range(12)]
    for i in range(110):
        t = rng.choice(clusters) + rng.uniform(-.19, .19)
        u = rng.uniform(.69, .88)
        wobble = 1 + .08 * math.sin(3 * t + sign) + .06 * math.cos(7 * t - sign)
        x = centre + 6.7 * u * wobble * math.cos(t)
        y = 8.2 * u * wobble * math.sin(t)
        if abs(x) < 12.1 or (abs(x - centre) < 3.32 and abs(y) < 4.9):
            continue
        z = .75 * (1 - u) ** 1.31 * (1 + .32 * math.sin(4 * t)) - .055
        if i % 3 == 0:
            s = rng.uniform(.13, .48)
            ashlar("Limestone scatter", x - s, x + s, y - .61*s, y + .56*s, max(z - .06, -.052),
                   z + s * .58, rng.choice(shades), rng, min(.17, .43 * s), (.17*s, -.12*s))
        for _ in range(rng.randint(6, 13)):
            a = rng.uniform(0, math.tau)
            xx, yy = x + rng.uniform(-.19, .19), y + rng.uniform(-.19, .19)
            h, w = rng.uniform(.17, .46), rng.uniform(.022, .065)
            dx, dy = math.cos(a), math.sin(a)
            k = len(leaves)
            leaves.extend(((xx-w*dy, yy+w*dx, z), (xx+w*dy, yy-w*dx, z),
                           (xx + h*.19*dx, yy + h*.19*dy, z + h*.67),
                           (xx + h*.52*dx, yy + h*.52*dy, z + h)))
            blades.extend(((k,k+1,k+2),(k,k+2,k+3)))
    mesh("Clumps of ford sedge and grass", leaves, blades, mats[2])


def threshold(shades, mortar, rng):
    ys = [-7.38, -6.18, -4.72, -3.20, -1.49, .20, 1.66, 3.27, 4.83, 6.28, 7.41]
    for i, (front, back) in enumerate(zip(ys, ys[1:])):
        tier = min(i, len(ys) - i - 2, 3)
        h = .19 + .17 * tier
        ashlar("Rammed dirt beneath paving", -12.34, 12.34, front, back, -.054,
               h - .12, mortar, rng, 0)
        positions = [-12.38] + [-12.38 + j * 2.476 + rng.uniform(-.59, .59)
                                for j in range(1, 10)] + [12.38]
        for j, (left, right) in enumerate(zip(positions, positions[1:])):
            part = f"Threshold slab {i + 1}.{j + 1}"
            z = h + rng.uniform(-.018, .019)
            mat = rng.choice(shades)
            lo, hi = left + .025, right - .023
            f, g = front + .024, back - .025
            if rng.random() < .14:
                x, y = rng.uniform(lo + .3, hi - .3), (f + g) * .5
                normal = Vector((1, rng.uniform(-.66, .66), .20)).normalized()
                point = Vector((x, y, z))
                for sign in (-1, 1):
                    ashlar(part + f" fracture {sign}", lo, hi, f, g, -.052, z, mat, rng, .044,
                           beds=((point - normal * sign * .026, normal * sign),))
            else:
                ashlar(part, lo, hi, f, g, -.052, z, mat, rng, .067)


def build():
    rng = random.Random(87013)
    shades, mortar = finish()
    threshold(shades, mortar, rng)
    for side in (-1, 1):
        pier(side, shades, mortar, rng)
        turf(side, shades, rng)
    arch(shades, mortar, rng)
