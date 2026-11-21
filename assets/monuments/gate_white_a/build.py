"""Floodmark Gate: battered twin piers under a shallow corbelled span."""
import math
import random

import bpy

import vrlib
import vrmat


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
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-py, x, z) for x, py, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone))
    for poly in mesh.polygons[1:25]:
        poly.use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(24))
    bevel = obj.modifiers.new("Stone arrises", "BEVEL")
    bevel.width, bevel.segments = min(wear * .52, .12), 4
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(22)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


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
        pier("battered plinth", .445, 2.43, 10.1, 23.75, 10.65, 22.42, 15.7, 1.12, .16, old)
        pier("plinth neck", 2.39, 2.92, 10.43, 22.55, 10.65, 22.22, 14.8, .86, .08, white)
        levels = (2.90, 5.36, 8.61, 11.49, 15.18, 18.12, 21.62, 24.40, 28.21, 31.24, 33.75)
        for i, (lo, hi) in enumerate(zip(levels, levels[1:])):
            t, u = lo / 34, hi / 34
            pier(f"load-bearing course {i:02}", lo, hi, 10.58 + t * 2.13, 22.41 - t * 2.83,
                 10.58 + u * 2.13, 22.41 - u * 2.83,
                 13.65 - 3.2 * t, .82 - t * .26, .19 if i in (0, 3, 7) else .12,
                 old if i == 0 else white)

        # Two engaged panel stacks bring the sloping outlines down to walking scale.
        for face in (-1, 1):
            for i, (lo, hi) in enumerate(zip((3, 6.4, 10.5, 15.6, 21.1, 27.7),
                                              (6.37, 10.47, 15.57, 21.07, 27.67, 32.62))):
                t, u = lo / 34, hi / 34
                pier(f"face {face:+} pilaster {i}", lo, hi, 13.45 + 2.23 * t, 16.3 + .75 * t,
                     13.45 + 2.23 * u, 16.3 + .75 * u, 2.35, .37, .09,
                     old if i == 0 else white, face * (6.52 - 1.68 * (t + u) / 2))

        for i, (lo, hi) in enumerate(((3.23, 7.06), (7.02, 12.48), (12.45, 18.03),
                                      (18, 24.90), (24.86, 30.04), (30, 33.12))):
            t, u = lo / 34, hi / 34
            a, b = 22.41 - t * 2.83, 22.41 - u * 2.83
            pier(f"Outboard buttress stone {i}", lo, hi, a - .38, a + 1.07 - .49 * t,
                 b - .38, b + 1.07 - .49 * u, 4.46 - .98 * t, .25, .12,
                 old if i == 0 else white)

        pier("impost", 33.67, 34.52, 11.55, 20.0, 11.55, 20.04, 11.65, .61, .12, white)
        pier("outer shoulder", 34.51, 39.02, 12.94, 20.0, 13.85, 19.2, 11.10, .63, .14, white)
        pier("raised shoulder cap", 38.97, 40.75, 13.56, 19.25, 14.05, 18.75, 11.3, .46, .14, white)

    divisions = (-13.42, -8.85, -4.21, 0, 4.21, 8.85, 13.42)
    ashlar("Continuous recessed lintel bed", 34.15, 38.23, (-14, 14), (-14.4, 14.4),
           8.6, .31, .07, rng, old)
    for i, (a, b) in enumerate(zip(divisions, divisions[1:])):
        aa = a * (1.04 if i not in (2, 3) else 1.03)
        bb = b * (1.04 if i not in (2, 3) else 1.03)
        ashlar(f"Span voussoir {i}", 34.02, 38.08, (a + .028, b - .028), (aa + .026, bb - .026),
               10.3, .19, .13, rng, white)
    for i, (a, b) in enumerate(zip((-14.15, -6.8, 1.3, 7.8), (-6.8, 1.3, 7.8, 14.15))):
        ashlar(f"Continuous drip cornice, slab {i}", 38.04, 38.75, (a, b - .028), (a - .04, b),
               11.26, .19, .055, rng, white)
    for i in range(8):
        x = (i - 3.5) * 2.42
        ashlar(f"Threshold slab {i}", 0, .15, (x - 1.18, x + 1.18), (x - 1.18, x + 1.18),
               7.3, .17, .031, rng, old)
