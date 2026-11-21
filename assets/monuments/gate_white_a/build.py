"""Floodmark Gate: battered limestone piers below a pointed, moulded arch."""
import math
import random

import bpy

import vrlib
import vrmat


def gate_stone(name):
    key = f"Floodmark {name}"
    saved = bpy.data.materials.get(key)
    if saved is not None:
        return saved
    base = vrmat.get(name)
    mat = base.copy()
    mat.name = key
    tree = mat.node_tree
    for node in tree.nodes:
        if node.type == "TEX_NOISE":
            scale = node.inputs["Scale"]
            for old, new in ((1.8, 6.8), (2.3, 7.8), (8, 19), (12, 25)):
                if abs(old - scale.default_value) < 1e-4:
                    scale.default_value = new
                    break
    surface = tree.nodes["Principled BSDF"].inputs["Base Color"]
    original = surface.links[0].from_socket
    mix = tree.nodes.new("ShaderNodeMixRGB")
    mix.label = "Low-contrast fine-grained limestone"
    weathered = name == "monument_weathered"
    mix.inputs["Fac"].default_value = .36 if weathered else .25
    gain = .84 if weathered else .93
    mix.inputs["Color1"].default_value = (*(gain * v for v in base.diffuse_color[:3]), 1)
    tree.links.new(original, mix.inputs["Color2"])
    tree.links.new(mix.outputs["Color"], surface)
    return mat


def make_stone(name, vertices, faces, stone, smooth=()):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(gate_stone(stone))
    for i in smooth:
        mesh.polygons[i].use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(23))
    return obj


def ashlar(name, bottom, top, foot, head, depth, cut, wear, rng, stone, y=0):
    vertices = []
    for i, (z, (left, right), scale) in enumerate(((bottom, foot, .985),
                                                   (bottom + wear * .7, foot, 1),
                                                   (top - wear, head, 1),
                                                   (top, head, .978))):
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
    bevel.width, bevel.segments = min(wear * .52, .12), 4
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(22)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


SPRING = 18.05
HALF_SPAN = 11.60
APEX_RISE = 16.25
CENTRE = (APEX_RISE ** 2 - HALF_SPAN ** 2) / (2 * HALF_SPAN)
RADIUS = HALF_SPAN + CENTRE
ARCH_FRONT = ((.04, -4.66), (.09, -5.05), (.33, -5.35), (.54, -5.35), (.65, -5.10),
              (.86, -5.10), (1.04, -5.53), (1.40, -5.55), (1.61, -5.26), (1.86, -4.90),
              (2.68, -4.90), (2.89, -5.33), (3.06, -5.55), (3.38, -5.56), (3.59, -5.23),
              (4.10, -4.97), (4.54, -4.47), (4.71, -3.97))
ARCH_SECTION = ARCH_FRONT + tuple((r, -y) for r, y in reversed(ARCH_FRONT))


def arch_stone(name, positions, section, rng, stone, flip, dress=False, key=False):
    rings = []
    for index, (side, t) in enumerate(positions):
        progress = index / (len(positions) - 1)
        end = index in (0, len(positions) - 1)
        flange = 1
        if dress:
            flange += .022 * math.sin(math.pi * progress) - (.026 if end else 0)
        taper = 1 - .27 * math.sin(math.pi * t / 2)
        ring = []
        for offset, y in section:
            r = RADIUS + offset * taper * flange
            if key:
                r += .33 * (offset / 4.71) * math.sin(math.pi * t / 2) ** 4
            theta = math.acos(CENTRE / r) * t
            x = side * (r * math.cos(theta) - CENTRE) if t < 1 else 0
            z = SPRING + r * math.sin(theta)
            if end and dress:
                chip = rng.uniform(-.08, .08)
                y *= .99
                y += rng.uniform(-.055, .055)
                z += chip * (offset / 4.71)
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
    cuts = (0, .11, .239, .36, .482, .596, .711, .821)
    for side, label in ((-1, "West"), (1, "East")):
        for i, (lo, hi) in enumerate(zip(cuts, cuts[1:])):
            a, b = lo + .0024, hi - .0024
            arch_stone(f"{label} pointed-arch voussoir {i + 1:02}",
                       [(side, a + (b - a) * j / 16) for j in range(17)],
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
        levels = (2.70, 4.84, 7.34, 10.10, 12.91, 15.37, 17.69)
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
    for i, (a, b) in enumerate(zip((-9.88, -7.07, -4.23, -1.42, 1.40, 4.24, 7.05),
                                  (-7.07, -4.23, -1.42, 1.40, 4.24, 7.05, 9.88))):
        ashlar(f"Threshold slab {i}", 0, .15, (a + .023, b - .023), (a + .023, b - .023),
               7.3, .17, .031, rng, old)
