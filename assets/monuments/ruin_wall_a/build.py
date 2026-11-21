"""A fractured retaining wall with surviving steps up to its rear walk."""
import math
import random

import bpy

import vrlib
import vrmat


def block(name, x, y, z, length, depth, height, rng, stone, fracture=0, wear=.06):
    c = min(length, depth) * .14
    w, d = length / 2, depth / 2
    outline = [(-w + c, -d), (w - c, -d), (w, -d + c), (w, d - c),
               (w - c, d), (-w + c, d), (-w, d - c), (-w, -d + c)]
    outline = [(a + rng.uniform(-wear, wear), b + rng.uniform(-wear, wear)) for a, b in outline]
    vertices = []
    for i, (a, b) in enumerate(outline):
        vertices.append((x + a, y + b, z))
    for i, (a, b) in enumerate(outline):
        loss = fracture * (.23 + .65 * (a / max(w, .01) + 1) / 2 + rng.uniform(0, .37))
        vertices.append((x + a + rng.uniform(-wear, wear), y + b + rng.uniform(-wear, wear),
                         z + height - loss + (rng.uniform(-wear, wear) * .6 if fracture else 0)))
    faces = [tuple(reversed(range(8)))]
    faces.extend((i, (i + 1) % 8, 8 + (i + 1) % 8, 8 + i) for i in range(8))
    if fracture:
        peak = z + height - fracture * rng.uniform(.22, .47)
        vertices.append((x - .21 * w, y + .15 * d, peak))
        faces.extend((8 + i, 8 + (i + 1) % 8, 16) for i in range(8))
    else:
        faces.append(tuple(range(8, 16)))
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone))
    bevel = obj.modifiers.new("Worn arrises", "BEVEL")
    bevel.width, bevel.segments = min(wear * .72, height * .14), 4
    bevel.angle_limit = math.radians(18)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(13052)
    white, old = "monument_white", "monument_weathered"
    block("Inset retaining bed", -.63, -1, 0, 8.7, 1.26, .93, rng, old)
    schedule = [
        (0, .54, (-5, -3.61, -2.05, -.04, 1.32, 2.89, 4.86)),
        (.52, .70, (-4.88, -3.03, -1.0, .70, 2.22, 4.02)),
        (1.2, .67, (-4.82, -3.72, -2.0, -.36, 1.44, 2.93)),
        (1.85, .65, (-4.79, -2.98, -1.29, .38, 1.87)),
        (2.48, .64, (-4.74, -3.55, -2.19, -.4, .74)),
        (3.10, .67, (-4.72, -3.08, -1.55, -.44)),
        (3.75, .64, (-4.69, -3.69, -2.17, -1.54)),
        (4.37, .48, (-4.62, -3.73, -2.92)),
    ]
    for course, (z, h, joints) in enumerate(schedule):
        for i, (a, b) in enumerate(zip(joints, joints[1:])):
            terminal = i >= len(joints) - 2
            damaged = (.21 + .27 * rng.random()) if terminal and course > 1 else 0
            if course >= 6:
                damaged += rng.uniform(.08, .20)
            if course == 5 and i == 1:
                damaged = .23
            block(f"Retaining course {course} stone {i}", (a + b) / 2, -1.09 + .055 * course,
                  z, b - a - .019, 1.95 - course * .07, h, rng,
                  old if damaged or (course + 2 * i) % 5 == 0 else white,
                  fracture=damaged, wear=.045 + .03 * rng.random())
    for course, (z, _, joints) in enumerate(schedule[2:], 2):
        a, b = joints[0] + .23, joints[-1] - .24
        block(f"Recessed hearting at bed {course}", (a + b) / 2, -1.09 + .055 * course,
              z - .24, b - a, 1.14 - course * .052, .31, rng, old, wear=.022)
    # The lower walk turns behind the break, where tread blocks rise to the remaining platform.
    block("Rear terrace lower bed", -.92, .98, 0, 7.79, 2.44, .38, rng, old)
    for i in range(7):
        x = 3.82 - i * .46
        top = .19 * (i + 1)
        block(f"Rear stair tread {i + 1}", x, 1.09, 0, .46, 2.23, top,
              rng, white if i % 4 else old, wear=.018)
    block("Upper walk solid fill", -1.85, 1.04, 0, 5.38, 2.45, 1.21, rng, old)
    for i, (a, b) in enumerate(zip((-4.58, -3.11, -1.81, -.51), (-3.11, -1.81, -.51, .87))):
        block(f"Upper walk paving {i + 1}", (a + b) / 2, 1.05, 1.185, b - a - .018, 2.54,
              .145, rng, white if i != 2 else old, wear=.032)
    for i, spec in enumerate(((3.72, -2.32, .83, .43, .33), (2.61, -2.48, .53, .33, .24),
                              (4.63, -.18, .6, .48, .3), (.51, -2.36, .35, .24, .16),
                              (-3.6, -2.35, .24, .19, .17))):
        x, y, l, d, h = spec
        block(f"Dislodged fragment {i}", x, y, 0, l, d, h, rng, old, fracture=h * .57, wear=.048)
