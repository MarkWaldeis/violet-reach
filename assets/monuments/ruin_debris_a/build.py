"""A fallen pair of limestone shaft drums and surrounding architectural rubble."""
import math
import random

import bpy
from mathutils import Euler, Vector

import vrlib
import vrmat


def stone(name, vertices, faces, position, rotation, material, smooth=(), old_faces=()):
    # Seat each piece after rotation, so fractured tips do not hang above the ground.
    matrix = Euler(rotation).to_matrix()
    transformed = [matrix @ Vector(vertex) for vertex in vertices]
    low = min(v.z for v in transformed)
    x, y = position
    vertices = [(v.x + x, v.y + y, v.z - low - .014) for v in transformed]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(material))
    if old_faces:
        obj.data.materials.append(vrmat.get("monument_weathered"))
    for polygon in mesh.polygons:
        polygon.use_smooth = polygon.index in smooth
        polygon.material_index = int(polygon.index in old_faces)
    mesh.set_sharp_from_angle(angle=math.radians(35))
    return obj


def drum(name, position, rotation, r, h, cracked, rng):
    n = 120
    vertices, faces = [], []
    frac = [rng.uniform(-.10, .10) for _ in range(12)]

    def shear(a, j):
        t = j / n * 12
        ripple = frac[int(t)] * (1 - t % 1) + frac[(int(t) + 1) % 12] * (t % 1)
        return r * (.28 * math.sin(a + .4) + .15 * math.cos(3 * a - .6) + ripple)

    rows = 16
    for k in range(rows):
        t = k / (rows - 1)
        for j in range(n):
            a = math.tau * j / n
            flutes = .072 * (.5 + .5 * math.cos(12 * a)) ** 3 if cracked else 0
            radius = r * (1 - .11 * t) - flutes
            radius += (.012 * math.sin(7 * a + t * 4) + .009 * math.cos(17 * a - t * 5))
            if not cracked:
                radius += r * (.15 * math.exp(-((t - .16) / .12) ** 2) +
                               .11 * math.exp(-((t - .77) / .13) ** 2))
            radius -= (.05 * r if k in (0, rows - 1) else 0)
            z = h * (t - .5) + (shear(a, j) * t ** 3 if cracked else 0)
            vertices.append((radius * math.cos(a), radius * math.sin(a), z))
    for i in range(rows - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    smooth = range(len(faces))
    faces.append(tuple(reversed(range(n))))
    damaged = len(faces)
    if cracked:
        for ring, f in enumerate((.78, .51, .22)):
            for j in range(n):
                a = math.tau * j / n
                cut = f * (1 + .11 * math.cos(5 * a - ring) + .07 * math.sin(9 * a))
                z = h / 2 + shear(a, j) * f + r * (.09 * math.cos(4 * a + ring) - .10 * (1 - f))
                vertices.append((r * cut * math.cos(a), r * cut * math.sin(a), z))
            inner = (rows + ring) * n
            for j in range(n):
                k = (j + 1) % n
                if (j // 5 + ring) % 2:
                    faces.extend(((inner - n + j, inner - n + k, inner + j),
                                  (inner - n + k, inner + k, inner + j)))
                else:
                    faces.append((inner - n + j, inner - n + k, inner + k, inner + j))
        centre = len(vertices)
        vertices.append((0, 0, h / 2 - .12 * r))
        faces.extend((centre - n + j, centre - n + (j + 1) % n, centre) for j in range(n))
    else:
        faces.append(tuple(range((rows - 1) * n, rows * n)))
    stone(name, vertices, faces, position, rotation, "monument_white", smooth,
          range(damaged, len(faces)) if cracked else ())


def rubble(name, position, dims, rng, dressed):
    w, d, h = (a / 2 for a in dims)
    vertices = []
    for j, z in enumerate((-h, -.62 * h, .68 * h, h)):
        for a, b in ((-.7, -1), (.7, -1), (1, -.64), (1, .64), (.7, 1), (-.7, 1), (-1, .64), (-1, -.64)):
            waver = rng.uniform(-.11, .11)
            f = (.83, 1, .98, .79)[j]
            vertices.append((w * (f * a + waver), d * (f * b + rng.uniform(-.13, .13)),
                             z + h * (rng.uniform(-.2, .2) + (.18 * a if j > 1 else 0))))
    faces = [tuple(reversed(range(8)))]
    for k in range(3):
        for j in range(8):
            a, b = 8 * k + j, 8 * k + (j + 1) % 8
            faces.append((a, b, b + 8, a + 8))
    vertices.append((w * .25, -.16 * d, h * rng.uniform(.75, 1.15)))
    faces.extend((24 + j, 24 + (j + 1) % 8, 32) for j in range(8))
    obj = stone(name, vertices, faces, position, (rng.uniform(-.22, .22), rng.uniform(-.17, .17),
                                                  rng.uniform(-math.pi, math.pi)),
                "monument_white" if dressed else "monument_weathered",
                old_faces=range(len(faces) - 8, len(faces)) if dressed else ())
    bevel = obj.modifiers.new("Small edge losses", "BEVEL")
    bevel.width, bevel.segments = min(dims) * .07, 3
    bevel.angle_limit = math.radians(19)
    obj.modifiers.new("Broad face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(7301)
    drum("Fractured reeded drum", (-1.73, -.40), (1.32, .26, .99), 1.13, 2.18, True, rng)
    drum("Separated shaft drum", (1.16, 1.21), (1.41, -.41, 2.6), 1.02, 1.57, True, rng)
    drum("Broken neck moulding", (2.69, -.72), (.79, .16, -.75), .81, .59, False, rng)
    for i, (x, y, a, b, c) in enumerate((
        (-2.65, 1.37, 1.36, .93, .72), (-3.38, .16, 1.08, .76, .61),
        (-.47, -1.99, 1.56, .84, .62), (.82, -1.29, .99, .77, .47),
        (-.82, 1.89, .9, .82, .43), (2.99, 1, .94, .66, .51),
        (2.41, -2.21, 1.27, .62, .46), (3.65, -.12, .70, .56, .36),
        (-2.68, -1.93, .57, .51, .31), (.17, .32, .70, .52, .32),
    )):
        rubble(f"Fallen ashlar {i}", (x, y), (a, b, c), rng, i not in (1, 4, 8))
    for i, (x, y) in enumerate(((-3.4, -1.43), (-3.68, -.72), (-1.94, -2.42), (-.97, -2.57),
                               (.28, -2.3), (1.28, -2.32), (3.36, -1.84), (3.75, -.93),
                               (3.37, .61), (2.94, 1.78), (1.98, 2.52), (.14, 2.61),
                               (-.96, 2.4), (-2.05, 2.1), (-3.22, 1.95), (-.25, .79),
                               (.78, -.6), (1.63, -.89), (-.44, 1.35))):
        a = rng.uniform(.14, .39)
        rubble(f"Spall {i}", (x, y), (a, a * rng.uniform(.61, .89), a * rng.uniform(.35, .65)), rng, False)
