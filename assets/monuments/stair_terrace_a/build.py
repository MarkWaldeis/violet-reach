"""Two flights of stepped limestone rise to an open-ended spillway terrace."""
import math
import random

import bpy

import vrlib
import vrmat


def ashlar(name, bounds, rng, stone, wear=.022):
    x0, x1, y0, y1, z0, z1 = bounds
    chamfer = min(wear * 1.9, (z1 - z0) * .22)
    footprint = [(x0 + chamfer, y0), (x1 - chamfer, y0), (x1, y0 + chamfer),
                 (x1, y1 - chamfer), (x1 - chamfer, y1), (x0 + chamfer, y1),
                 (x0, y1 - chamfer), (x0, y0 + chamfer)]
    corners = [(x + rng.uniform(-wear, wear) * .5, y + rng.uniform(-wear, wear) * .5)
               for x, y in footprint]
    vertices = [(x, y, z0) for x, y in corners]
    vertices += [(x + rng.uniform(-wear, wear) * .31, y + rng.uniform(-wear, wear) * .37, z1)
                 for x, y in corners]
    faces = [tuple(reversed(range(8)))]
    faces.extend((i, (i + 1) % 8, 8 + (i + 1) % 8, 8 + i) for i in range(8))
    faces.append(tuple(range(8, 16)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-y, x, z) for x, y, z in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone))
    bevel = obj.modifiers.new("Soft quarry edges", "BEVEL")
    bevel.width, bevel.segments = wear * .78, 4
    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(20)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(251553)
    white, old = "monument_white", "monument_weathered"
    rise = 6 / 34
    tread = .42
    start = -10.22
    lower_end = start + 17 * tread
    upper_start = lower_end + 2.04
    upper_end = upper_start + 17 * tread
    back = 10.22

    def course(label, cuts, y0, y1, bottom, top, worn=False):
        ashlar(f"{label} recessed bearing", (cuts[0] + .038, cuts[-1] - .038,
                                            y0 + .025, y1 - .026, bottom, top - .075),
               rng, old, .013)
        for k, (x0, x1) in enumerate(zip(cuts, cuts[1:])):
            ashlar(f"{label} slab {k}", (x0 + .007, x1 - .007, y0, y1, top - .115, top),
                   rng, old if worn and k in (0, len(cuts) - 2) else white,
                   .021 if worn else .013)

    for j in range(34):
        y = (start if j < 17 else upper_start) + (j % 17) * tread
        cuts = (-3.48, -1.12 + rng.uniform(-.28, .27), 1.10 + rng.uniform(-.26, .25), 3.48)
        course(f"Riser {j + 1:02}", cuts, y, y + tread, 0, (j + 1) * rise, j % 6 == 0)
    for j in range(4):
        y = lower_end + j * .51
        course(f"Rest landing bay {j}", (-3.48, -1.76, -.42 + .23 * (j % 2), 1.47, 3.48),
               y, y + .51, 0, 3, j % 2 == 0)
    for j in range(5):
        y0 = upper_end + (back - upper_end) * j / 5
        y1 = upper_end + (back - upper_end) * (j + 1) / 5
        shift = .23 if j % 2 else -.21
        course(f"Summit terrace bay {j}", (-5.26, -3.50, -1.72 + shift, .15 - shift, 2.05 + shift, 3.5, 5.26),
               y0, y1, 0, 6, j in (0, 4))

    # The broad retaining cheeks step back in plan, leaving the treads and upper terrace open.
    cheek = [
        (start + .29, start + 2.71, 1.30, 4.53),
        (start + 2.71, start + 5.19, 2.38, 4.95),
        (start + 5.19, lower_end + .62, 3.44, 5.29),
        (lower_end + .62, upper_start + 1.50, 4.13, 5.29),
        (upper_start + 1.50, upper_start + 3.91, 5.12, 5.48),
        (upper_start + 3.91, upper_end, 6.33, 5.64),
        (upper_end, back, 6.33, 5.62),
    ]
    for sign, side in ((-1, "west"), (1, "east")):
        for j, (y0, y1, ceiling, outer) in enumerate(cheek):
            layers = math.ceil(ceiling / .79)
            for row in range(layers):
                bottom, top = ceiling * row / layers, ceiling * (row + 1) / layers
                split = y0 + (y1 - y0) * (.42 if (row + j) % 2 else .59)
                for i, (a, b) in enumerate(((y0, split), (split, y1))):
                    x1 = outer - .057 * row - (.08 if row > 0 and row != layers - 1 else 0)
                    lo, hi = sorted((sign * 3.45, sign * x1))
                    ashlar(f"{side} cheek {j} course {row} block {i}",
                           (lo, hi, a + .011, b - .011, bottom, top),
                           rng, old if row == 0 or (i + j + row) % 8 == 0 else white, .032)
            lo, hi = sorted((sign * 3.40, sign * (outer - .057 * (layers - 1) + .10)))
            ashlar(f"{side} copestone {j}", (lo, hi, y0 + .018, y1 - .018, ceiling - .048, ceiling + .095),
                   rng, white, .035)
