"""A violet seam broken through a low fan of limestone and bare earth."""
import math
import random

import bpy
from mathutils import Vector

import vrlib
import vrmat


def loft(name, rings, material, bevel=0):
    n = len(rings[0])
    faces = [tuple(reversed(range(n)))]
    for row in range(len(rings) - 1):
        a, b = row * n, (row + 1) * n
        faces.extend((a + i, a + (i + 1) % n, b + (i + 1) % n, b + i) for i in range(n))
    faces.append(tuple(range(n * (len(rings) - 1), n * len(rings))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([v for ring in rings for v in ring], [], faces)
    mesh.update()
    obj = vrlib.link_to_source(bpy.data.objects.new(name, mesh))
    mesh.materials.append(vrmat.get(material))
    if bevel:
        mod = obj.modifiers.new("Cleaved edges", "BEVEL")
        mod.width, mod.segments = bevel, 3
        mod.limit_method = "ANGLE"
    return obj


def crystal(name, base, height, radius, lean, phase, rng):
    axis = Vector((*lean, 1)).normalized()
    u = axis.cross(Vector((0, 1, 0))).normalized()
    v = axis.cross(u)
    outline = [u * math.cos(phase + i * math.tau / 6) + v * math.sin(phase + i * math.tau / 6)
               for i in range(6)]
    girth = [rng.uniform(.80, 1.12) for _ in outline]
    shoulder = [.70, .78, .67, .72, .83, .73]
    rings = []
    for f, scale, shift in ((0, .66, 0), (.19, .96, -.11), (.39, 1.07, -.08),
                            (.75, 1, 0), (.94, .43, .20), (1, .11, .29)):
        rings.append([Vector(base) + axis * (height * (shoulder[i] if f == .75 else f))
                      + radius * (scale * girth[i] * q + shift * u) for i, q in enumerate(outline)])
    loft(name, rings, "violet_crystal", .009 if radius > .30 else .003)


def slab(name, x, y, rx, ry, h, yaw, rng, material, lift=0):
    angles = [yaw + i * math.tau / 9 + rng.uniform(-.16, .16) for i in range(9)]
    fac = [rng.uniform(.68, 1.17) for _ in angles]
    relief = [rng.uniform(-.13, .16) for _ in angles]
    rings = []
    for z, s, dx in ((-.045, .85, 0), (.17 * h, 1, 0), (.26 * h, .98, .02),
                     (.53 * h, .91, .09), (.61 * h, .95, .11), (.92 * h, .74, .20),
                     (h, .42, .21)):
        rings.append([(x + rx * (fac[i] * s * math.cos(a) + dx), y + ry * fac[i] * s * math.sin(a),
                       max(-.046,z + lift + max(z, 0) * relief[i])) for i, a in enumerate(angles)])
    obj = loft(name, rings, material, min(.035, .07 * h))
    if h > .25:
        obj.data.materials.append(vrmat.get("monument_weathered"))
        for poly in obj.data.polygons[19:28]:
            poly.material_index = 1


def build():
    rng = random.Random(695720)
    n = 80
    angles = [i * math.tau / n for i in range(n)]
    rings = []
    for r, z in ((1, -.046), (1, .002), (.94, .028), (.76, .087), (.52, .15),
                 (.35, .17), (.16, .11), (.02, .117)):
        rings.append([(2.72 * r * math.cos(a) * (1 + .09 * math.sin(3*a) + .08 * math.cos(5*a)),
                       1.85 * r * math.sin(a) * (1 + .11 * math.cos(4*a)+.045*math.sin(9*a)),
                       z + min(.7, 1-r) * (.045 * math.sin(5*a + r*8) + rng.uniform(-.028, .028)))
                      for a in angles])
    shelf = loft("Bare earth, heaved out of the seam", rings, "forest_soil")
    for poly in shelf.data.polygons:
        poly.use_smooth = len(poly.vertices) == 4

    for i, args in enumerate((
            (-.71, .15, 1.12, .85, .61, .34), (.39, .29, 1.28, .73, .48, .08),
            (-1.57, -.19, .73, .56, .36, .52), (.85, -.22, .91, .67, .33, .42),
            (.03, .91, .92, .53, .41, -.27), (-.81, -.57, .67, .36, .24, .19),
            (1.54, .07, .62, .43, .30, .22), (-1.18, .74, .53, .37, .39, 1.10),
            (-1.18,-.88,.47,.30,.155,.51), (.11,-.82,.32,.21,.14,-.26),
            (.72,.73,.34,.28,.29,.63))):
        slab(f"Ruptured limestone shelf {i+1:02}", *args, rng, "canyon_layered")

    for name, base, h, r, lean, phase in (
            ("Main crown", (-.51, .04, .40), 2.68, .52, (-.31, -.09), .48),
            ("Split shoulder", (-.20, .32, .40), 1.76, .34, (.12, .23), .90),
            ("Raking crystal", (.43, -.12, .32), 1.72, .37, (.73, -.18), .25),
            ("Low fork", (.27, -.34, .29), .96, .22, (.43, -.62), 1.2),
            ("Far blade", (-1.05, .55, .31), 1.16, .24, (-.70, .29), .72),
            ("Fissure crystal", (-.39, -.48, .15), .86, .21, (-.22, -.37), .34),
            ("Small counterpoint", (.75, .50, .28), .87, .19, (.48, .32), .88),
            ("Rear needle", (.10, .65, .38), 1.07, .16, (.09, .56), 1.25),
    ):
        crystal(name, base, h, r, lean, phase, rng)

    for i in range(82):
        a, r = rng.uniform(0, math.tau), rng.uniform(.60, .91)
        x, y = r * 2.58 * math.cos(a), r * 1.75 * math.sin(a)
        s = rng.uniform(.024, .102) * (1.0 if i < 68 else 1.6)
        slab(f"Limestone spall {i+1:02}", x, y, s, s * rng.uniform(.52, .96),
             s * rng.uniform(.65, 1.4), a, rng, "mossy_rock" if i % 4 == 0 else "canyon_layered",
             .025+.14*(1-r))
        if i < 17 and i % 2 == 0:
            crystal(f"Seam splinter {i+1:02}", (x * .69, y * .69, .13), rng.uniform(.11, .23),
                    rng.uniform(.025, .055), (.27 * math.cos(a), .42 * math.sin(a)), a, rng)
