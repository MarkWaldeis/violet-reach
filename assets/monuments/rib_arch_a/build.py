"""Six quarried limestone sails on a single skewed foundation."""
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
    (.47, -.34), (.50, -.25), (.50, .24), (.47, .35), (.37, .49),
    (.27, .50), (.22, .43), (.15, .43), (.11, .49), (-.11, .49),
    (-.15, .43), (-.22, .43), (-.27, .50), (-.37, .49), (-.47, .35),
    (-.50, .24), (-.50, -.25), (-.47, -.34), (-.34, -.48),
    (-.19, -.50), (.19, -.50), (.34, -.48),
)


def sail(index, x, y, height, reach, width, thickness, rng):
    def spine(t):
        return Vector((
            x + reach * (.16 * t - 1.16 * t ** 2.8),
            y + (2.5 - index * .56) * t + 3.5 * t ** 3,
            2.6 + height * (1.48 * t - .48 * t ** 2.8),
        ))

    def sweep(name, start, end, rows, inset, stone, worn):
        vertices = []
        for j in range(rows + 1):
            t = start + (end - start) * j / rows
            point = spine(t)
            tangent = (spine(t + .0001) - spine(max(0, t - .0001))).normalized()
            flank = Vector((0, 1, 0))
            normal = tangent.cross(flank).normalized()
            flank = normal.cross(tangent)
            taper = 1 - .55 * t ** 1.45 - .31 * t ** 7
            edge = .97 if j in (0, rows) and not inset else 1
            for k, (a, b) in enumerate(PROFILE):
                if worn:
                    edge_damage = 1 - .14 * max(0, math.sin(k * 1.72 + index + start * 50)) ** 7
                    factor = edge * edge_damage if j in (0, rows) else edge
                else:
                    factor = edge
                vertices.append(point + (a * width * flank + b * thickness * normal)
                                * (taper * factor * (1 - inset)))
        n = len(PROFILE)
        faces = [tuple(reversed(range(n)))]
        for i in range(rows):
            for j in range(n):
                a, b = i * n + j, i * n + (j + 1) % n
                faces.append((a, b, b + n, a + n))
        faces.append(tuple(range(len(vertices) - n, len(vertices))))
        obj = mesh(name, vertices, faces, stone)
        for p in obj.data.polygons[1:-1]:
            p.use_smooth = True
        obj.data.set_sharp_from_angle(angle=math.radians(34))

    sweep(f"Sail {index} structural bed", 0, 1, 116, .22, "monument_weathered", False)
    start = 0
    course = 0
    while start < 1:
        end = min(1, start + rng.uniform(.048, .083) * (1.1 - .24 * start))
        gap = .0009
        sweep(f"Sail {index} dressed course {course:02}", start + (gap if start else 0),
              end - (gap if end < 1 else 0), 9, 0,
              "monument_weathered" if course < 2 else "monument_white", course % 3 == index % 3)
        start = end
        course += 1
        if 0 < 1 - start < .009:
            break


def build():
    rng = random.Random(38445)
    outline = [(-17, -27), (6, -27), (13, -18), (17, -1), (15, 13), (7, 26),
               (-5, 27), (-13, 17), (-17, 1)]
    podium("Flood-worn foundation", outline, [(0, 1), (.48, 1), (.74, .978), (1.53, .978)],
           "monument_weathered")
    podium("Stepped common stylobate", outline, [(1.49, .949), (2, .949), (2.54, .886),
                                                 (3.18, .853), (3.45, .853)], "monument_white")
    ribbons = [
        (-7.7, -20.8, 30.5, 11.5, 3.7, 3.6),
        (-5.5, -13.8, 42.5, 17.0, 4.9, 4.6),
        (-2.0, -6.0, 57.5, 23.5, 5.7, 5.6),
        (2.7, 2.2, 75.0, 29.5, 6.8, 7.4),
        (6.9, 11.0, 65.0, 18.4, 5.5, 6.0),
        (4.9, 19.0, 47.0, 11.5, 4.2, 4.6),
    ]
    for index, spec in enumerate(ribbons, 1):
        sail(index, *spec, rng)
