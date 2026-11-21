"""Six hooked, keeled limestone blades on a shared terraced foundation."""
import math
import random

import bpy
from mathutils import Vector

import vrlib
import vrmat


def mesh(name, vertices, faces, stone):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone))
    return obj


def podium(name, outline, bands, stone):
    vertices = [(x * scale, y * scale, z) for z, scale in bands for x, y in outline]
    n = len(outline)
    faces = [tuple(reversed(range(n)))]
    for i in range(len(bands) - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    faces.append(tuple(range(len(vertices) - n, len(vertices))))
    obj = mesh(name, vertices, faces, stone)
    bevel = obj.modifiers.new("Rounded arrises", "BEVEL")
    bevel.width, bevel.segments = .14, 4
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


PROFILE = (
    (.09, -.72), (.15, -.58), (.22, -.40), (.42, -.40), (.48, -.32),
    (.50, -.19), (.50, .17), (.47, .28), (.42, .35), (.25, .41), (0, .43),
    (-.25, .41), (-.42, .35), (-.47, .28), (-.50, .17), (-.50, -.19),
    (-.48, -.32), (-.42, -.40), (-.22, -.40), (-.15, -.58), (-.09, -.72),
)


def sail(index, x, y, height, reach, fan, width, depth, rng):
    turn = 1.79 + .05 * index

    def spine(t):
        return Vector((
            x + reach * (.17 * math.sin(math.pi * t) - t ** 2.4),
            y + fan * (.39 * t + .61 * t ** 1.85),
            3.75 + height * math.sin(turn * t),
        ))

    def sweep(name, start, end, rings, bed, stone, worn):
        vertices = []
        for progress, flare in rings:
            t = start + (end - start) * progress
            point = spine(t)
            tangent = (spine(t + .0001) - spine(max(0, t - .0001))).normalized()
            roll = (.30 + .19 * t) * fan / 19
            flank = Vector((math.sin(roll), math.cos(roll), 0))
            normal = tangent.cross(flank).normalized()
            flank = normal.cross(tangent)
            taper = 1 - .42 * t ** 1.5 - .29 * t ** 6
            w, d = ((.69, .55) if bed else (1, 1))
            for k, (a, b) in enumerate(PROFILE):
                chip = 1
                if worn and (progress < .13 or progress > .87):
                    chip -= .115 * max(0, math.sin(k * 1.72 + index + start * 50)) ** 7
                vertices.append(point + (a * width * w * flank + b * depth * d * normal)
                                * (taper * flare * chip))
        n = len(PROFILE)
        faces = [tuple(reversed(range(n)))]
        for i in range(len(rings) - 1):
            for j in range(n):
                a, b = i * n + j, i * n + (j + 1) % n
                faces.append((a, b, b + n, a + n))
        faces.append(tuple(range(len(vertices) - n, len(vertices))))
        obj = mesh(name, vertices, faces, stone)
        for p in obj.data.polygons[1:-1]:
            p.use_smooth = True
        obj.data.set_sharp_from_angle(angle=math.radians(28))

    sweep(f"Sail {index} recessed bed", 0, .995, [(j / 140, 1) for j in range(141)],
          True, "monument_weathered", False)
    flares = ((0, .96), (.04, 1.04), (.12, 1.07), (.22, 1.015), (.39, .99),
              (.55, .98), (.70, .99), (.80, 1.015), (.91, 1.07), (.97, 1.04), (1, .96))
    start = 0
    course = 0
    while start < 1:
        end = start + rng.uniform(.048, .076) * (1.12 - .21 * start)
        if end > .967:
            end = 1
        gap = .0023 if course % 3 else .0031
        sweep(f"Sail {index} dressed course {course:02}", start + (gap if start else 0),
              end - (gap if end < 1 else 0), flares, False,
              "monument_weathered" if course < 2 else "monument_white", course % 3 == index % 3)
        start = end
        course += 1


def build():
    rng = random.Random(38445)
    outline = [(-20, -33), (1, -33), (12, -29), (19, -19), (21, -3), (19, 15),
               (16, 29), (9, 34), (-6, 34), (-16, 28), (-22, 13), (-23, -15)]
    podium("Flood-worn foundation", outline, [(0, 1), (.42, 1), (.51, .993), (.94, .993)],
           "monument_weathered")
    podium("Lower terrace and scotia", outline, [(.91, .943), (1.27, .943), (1.43, .921),
                                                (1.98, .921), (2.15, .933)], "monument_white")
    podium("Middle terrace", outline, [(2.12, .884), (2.38, .884), (2.73, .867),
                                       (3.10, .867), (3.28, .879)], "monument_white")
    podium("Raised rib court", outline, [(3.25, .827), (3.73, .827), (4.04, .812),
                                         (4.43, .812), (4.57, .823)], "monument_white")
    ribbons = [
        (-7.7, -22.0, 29, 14, -16, 5.6, 2.2),
        (-5.1, -13.8, 40, 23, -12, 6.8, 2.55),
        (-1.7, -5.0, 55, 32, -6, 8.3, 3.20),
        (3.2, 4.4, 74, 48, 3, 9.5, 3.75),
        (7.1, 13.8, 63, 39, 11, 8.6, 3.30),
        (7.7, 22.0, 43, 25, 19, 6.8, 2.60),
    ]
    for index, spec in enumerate(ribbons, 1):
        sail(index, *spec, rng)
