"""Floodmark Gate: raked limestone piers carrying an asymmetric round crown."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    local_name = f"gate_white_a.{name}"
    mat = bpy.data.materials.get(local_name)
    if mat is not None:
        return mat
    mat = vrmat.get(name).copy()
    mat.name = local_name
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    surface = nodes["Principled BSDF"]
    weathered = name == "monument_weathered"
    palette = vrmat.load_palette()
    white = palette["monument_white"]["linear_rgb"]
    patina = palette["stone_weathered"]["linear_rgb"]
    pores = next(n for n in nodes if n.type == "TEX_VORONOI")
    pores.inputs["Scale"].default_value = 32
    grain = nodes.new("ShaderNodeValToRGB")
    grain.color_ramp.elements[0].position = .11
    grain.color_ramp.elements[0].color = (*(v * .74 for v in white), 1)
    grain.color_ramp.elements[1].position = .34
    grain.color_ramp.elements[1].color = (*white, 1)
    links.new(pores.outputs["Distance"], grain.inputs["Fac"])
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = .31 if weathered else .14
    tone = nodes.new("ShaderNodeMixRGB")
    strength = .68 if weathered else .34
    tone.inputs["Color1"].default_value = (*(a * (1-strength) + b * strength for a, b in zip(white, patina)), 1)
    links.new(ao.outputs["AO"], tone.inputs["Fac"])
    links.new(grain.outputs["Color"], tone.inputs["Color2"])
    links.new(tone.outputs["Color"], surface.inputs["Base Color"])
    bump = surface.inputs["Normal"].links[0].from_node
    bump.inputs["Strength"].default_value = .67
    bump.inputs["Distance"].default_value = .021
    roughness = surface.inputs["Roughness"].links[0].from_node
    roughness.inputs["To Min"].default_value = .77
    roughness.inputs["To Max"].default_value = .94
    return mat


def make_stone(name, vertices, faces, stone, smooth=()):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(stone))
    for i in smooth:
        mesh.polygons[i].use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(23))
    return obj


def ashlar(name, bottom, top, foot, head, depth, cut, wear, rng, stone, y=0):
    vertices = []
    for i, (z, (left, right), scale) in enumerate(((bottom, foot, .995),
                                                   (bottom + wear * .7, foot, 1),
                                                   (top - wear, head, 1),
                                                   (top, head, .993))):
        half = depth / 2 * (1 - .02 * i)
        s = cut
        mid = (left + right) / 2
        outline = [(left + s, -half), (right - s, -half), (right, -half + s),
                   (right, half - s), (right - s, half), (left + s, half),
                   (left, half - s), (left, -half + s)]
        for j, (x, dy) in enumerate(outline):
            vertices.append((mid + (x - mid) * scale + rng.uniform(-wear, wear) * .45,
                             y + dy * scale + rng.uniform(-wear, wear) * .55,
                             z + (rng.uniform(-wear, wear) * .39 if i in (0, 3) and bottom > .1 else 0)))
    faces = [tuple(reversed(range(8)))]
    faces.extend((8 * i + j, 8 * i + (j + 1) % 8,
                  8 * (i + 1) + (j + 1) % 8, 8 * (i + 1) + j)
                 for i in range(3) for j in range(8))
    faces.extend(((24, 25, 26, 27), (24, 27, 28, 29), (24, 29, 30, 31)))
    obj = make_stone(name, vertices, faces, stone, range(1, 25))
    bevel = obj.modifiers.new("Stone arrises", "BEVEL")
    bevel.width, bevel.segments = min(wear * .29, .056), 2
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(22)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


SPRING = 18.05
HALF_SPAN = 11.60
APEX_RISE = 16.25
ARCH_FRONT = ((.04, -4.66), (.09, -5.05), (.33, -5.35), (.54, -5.35), (.65, -5.10),
              (.86, -5.10), (1.04, -5.53), (1.40, -5.55), (1.61, -5.26), (1.86, -4.90),
              (2.68, -4.90), (2.89, -5.33), (3.06, -5.55), (3.38, -5.56), (3.59, -5.23),
              (4.10, -4.97), (4.54, -4.47), (4.71, -3.97))
ARCH_SECTION = ARCH_FRONT + tuple((r, -y) for r, y in reversed(ARCH_FRONT))


def split_section(section):
    points = []
    for (u0, v0), (u1, v1) in zip(section, section[1:] + section[:1]):
        count = max(1, math.ceil(math.hypot(u1-u0, v1-v0) / .32))
        for j in range(count):
            f = j / count
            points.append((u0 + f*(u1-u0), v0 + f*(v1-v0)))
    return points


def arch_stone(name, positions, section, rng, stone, flip, dress=False, key=False):
    if dress:
        section = split_section(section)
    rings = []
    for index, (side, t) in enumerate(positions):
        progress = index / (len(positions) - 1)
        end = index in (0, len(positions) - 1)
        flange = 1
        if dress:
            flange -= .009 if end else 0
        taper = 1 - .27 * math.sin(math.pi * t / 2)
        ring = []
        for k, (offset, y) in enumerate(section):
            radial = offset * taper * flange
            relief = 0
            if dress:
                activity = math.sin(25.9*progress+1.3*y) * math.cos(5.6*y-.23*t)
                track = math.sin(58*progress-3.8*y) * math.cos(4.7*offset+2.3*y)
                relief = .021 * activity + .031 * track
                if offset > 3.92:
                    radial += relief * min(1, (offset-3.92)/.34)
                if end and offset > 2.9 and .62 < math.sin(y*.79 + t*28) < .93:
                    radial -= .098
            if key:
                radial += .49 * (offset / 4.71) * math.sin(math.pi * t / 2) ** 5
            theta = math.pi / 2 * t
            shift = 1.18 * math.sin(theta) ** 2
            x = side * (HALF_SPAN + radial) * math.cos(theta) + shift
            z = SPRING + (APEX_RISE + radial) * math.sin(theta)
            z += side * .46 * math.sin(math.pi * t) ** 2
            if end and dress:
                chip = rng.uniform(-.10, .10)
                if (k + int(t * 109)) % 9 in (0, 1):
                    y *= .963
                y += rng.uniform(-.055, .055)
                z += chip * (offset / 4.71)
            if dress:
                y += math.copysign(1, y) * relief * min(1,abs(y)*.32)
            if key:
                y *= 1.033
            ring.append((x, y * (1 - .13 * t) * flange, z))
        rings.extend(ring)
    n = len(section)
    faces = [tuple(reversed(range(n)))]
    for i in range(len(positions) - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    faces.append(tuple(range(len(rings) - n, len(rings))))
    make_stone(name, rings, [tuple(reversed(face)) for face in faces] if flip else faces,
               stone, range(1, len(faces) - 1))


def build_arch(rng, white, old):
    bed = ((.34, -3.80), (4.17, -3.80), (4.17, 3.80), (.34, 3.80))
    arch_stone("Continuous recessed arch bed",
               [(-1, j / 64) for j in range(65)] + [(1, j / 64) for j in range(63, -1, -1)],
               bed, rng, old, True)
    for side, label, cuts in ((-1, "West", (0, .096, .237, .349, .533, .664, .813)),
                              (1, "East", (0, .127, .204, .382, .499, .602, .738, .812))):
        for i, (lo, hi) in enumerate(zip(cuts, cuts[1:])):
            a, b = lo + .0024, hi - .0024
            arch_stone(f"{label} pointed-arch voussoir {i + 1:02}",
                       [(side, a + (b - a) * j / 38) for j in range(39)],
                       ARCH_SECTION, rng, white, side == -1, dress=True)
    crown = .823
    arch_stone("Saddle keystone",
               [(-1, crown + (1 - crown) * j / 24) for j in range(25)] +
               [(1, crown + (1 - crown) * j / 24) for j in range(23, -1, -1)],
               ARCH_SECTION, rng, white, True, dress=True, key=True)


def build():
    rng = random.Random(6327)
    white = "monument_white"
    old = "monument_weathered"
    for sign, name in ((-1, "West"), (1, "East")):
        def mirror(left, right):
            return tuple(sorted((sign * left, sign * right)))

        def pier(label, z0, z1, inner0, outer0, inner1, outer1, d, cut, wear, stone, y=0):
            ashlar(f"{name} {label}", z0, z1, mirror(inner0, outer0), mirror(inner1, outer1),
                   d, cut, wear, rng, stone, y)

        pier("foundation", 0, .46, 9.65, 24.5, 9.65, 24.5, 17.6, 1.2, .065, old)
        pier("battered plinth", .445, 2.18, 10.08, 23.78, 10.34, 22.8, 15.7, 1.12, .16, old)
        pier("plinth neck", 2.14, 2.72, 10.2, 22.95, 10.36, 22.64, 14.8, .86, .08, white)
        levels = (2.70, 4.14, 7.49, 9.16, 12.91, 14.66, 17.69) if sign < 0 else (
            2.70, 5.82, 8.06, 9.44, 13.12, 15.73, 17.69)
        for i, (lo, hi) in enumerate(zip(levels, levels[1:])):
            t, u = lo / SPRING, hi / SPRING
            pier(f"load-bearing course {i:02}", lo, hi, 10.33 + t * 1.25, 23.14 - t * 5.30,
                 10.33 + u * 1.25, 23.14 - u * 5.30,
                 14.12 - 2.8 * t, .78 - t * .25, .20 if i in (0, 3) else .14,
                 old if i == 0 else white)

        for face in (-1, 1):
            for i, (lo, hi) in enumerate(zip((2.65, 5.21, 8.92, 12.68, 15.59),
                                              (5.18, 8.89, 12.65, 15.56, 17.68))):
                t, u = lo / SPRING, hi / SPRING
                pier(f"face {face:+} engaged stem {i}", lo, hi,
                     12.1 + 1.03 * t, 14.68 + .31 * t, 12.1 + 1.03 * u, 14.68 + .31 * u,
                     2.35 - .40 * t, .37, .10, old if i == 0 else white,
                     face * (6.86 - 1.54 * (t + u) / 2))

        for i, (lo, hi) in enumerate(((2.07, 5.92), (5.89, 9.99), (9.96, 14.08),
                                      (14.05, 17.38), (17.35, 20.76))):
            t, u = lo / 21, hi / 21
            pier(f"Raked outboard buttress {i}", lo, hi,
                 21.04 - 5.95 * t, 25 - 7.37 * t, 21.04 - 5.95 * u, 25 - 7.37 * u,
                 6.50 - 3.0 * t, .49, .13, old if i == 0 else white)
        pier("Springer cornice", 17.61, 18.07, 11.58, 18.13, 11.58, 17.82, 11.91, .46, .08, white)
        pier("Keyed springer seat", 18.04, 18.32, 11.64, 16.25, 11.66, 16.21, 10.22, .36, .045, white)

    build_arch(rng, white, old)
    ashlar("Continuous keyed threshold foundation", -.034, .25, (-11, 11), (-10.8, 10.8),
           10.08, .52, .038, rng, old)
    cuts = (-10.78, -7.17, -5.23, -1.32, 1.08, 4.66, 7.53, 10.78)
    for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
        ashlar(f"Threshold inset stone {i}", .22, .34, (a + .019, b - .019), (a + .026, b - .026),
               9.92, .17, .031, rng, white)
