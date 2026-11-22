"""Six hooked, keeled limestone blades on a shared terraced foundation."""
import math
import random

import bpy
from mathutils import Vector

import vrlib
import vrmat


def limestone(name):
    mat = vrmat.get(name)
    if mat.get("quarried_finish"):
        return mat
    mat["quarried_finish"] = True
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


def mesh(name, vertices, faces, stone):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(stone))
    return obj


def podium(name, outline, bands, stone, anchor=(0, 0)):
    vertices = [(anchor[0] + x * scale, anchor[1] + y * scale, z)
                for z, scale in bands for x, y in outline]
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
            taper = 1 - .44 * t ** 1.35 - .12 * t ** 4 + .12 * math.exp(-((t-.970)/.053)**4)
            w, d = ((.69, .55) if bed else (1, 1))
            for k, (a, b) in enumerate(PROFILE):
                chip = 1
                if worn and (progress < .08 or progress > .92):
                    chip -= .095 * max(0, math.sin(k * .88 + index + start * 50)) ** 5
                if not bed:
                    chip += .0027 * math.sin(k * 1.9 + progress * 47 + start * 94)
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
    start = 0
    course = 0
    while start < 1:
        end = start + rng.uniform(.064, .112) + .124 * start
        if end > .90:
            end = 1
        gap = rng.uniform(.0008, .0019)
        crown = 1.035 if end == 1 else rng.uniform(.994, 1.012)
        rings = [(j / 22, crown if j not in (0, 22) else crown - .019) for j in range(23)]
        rings[1] = (.009, crown)
        rings[-2] = (.991, crown)
        sweep(f"Sail {index} dressed course {course:02}", start + (gap if start else 0),
              end - (gap if end < 1 else 0), rings, False,
              "monument_white", course % 3 != index % 3)
        start = end
        course += 1

    def footing(name, x0, x1, y0, y1, bands):
        c = .34
        shape = [(x0+c,y0), (x1-c,y0), (x1,y0+c), (x1,y1-c),
                 (x1-c,y1), (x0+c,y1), (x0,y1-c), (x0,y0+c)]
        anchor = ((x0+x1)/2, (y0+y1)/2)
        for i, (low, high, lower, upper) in enumerate(bands):
            loop = [(u-anchor[0], v-anchor[1]) for u, v in shape]
            podium(f"Sail {index} {name} {i}", loop,
                   [(low, lower), (low+.07, lower), (high-.11, upper), (high, upper*.98)],
                   "monument_weathered" if i == 0 else "monument_white", anchor)

    flank = width / 2 + .32
    for left, right in ((x-3.74, x+1.8), (x+4.63, x+6.58)):
        footing("split root", left, right, y-flank, y+flank,
                [(4.43, 5.08, 1.10, 1.07), (5.055, 6.14, 1.055, 1.015),
                 (6.115, 7.47, 1.02, .94)])
    footing("root crown", x-3.77, x+6.66, y-flank-.50, y+flank+.50,
            [(7.43, 8.04, 1, 1.012), (8.015, 9.51, 1.012, .83)])


def build():
    rng = random.Random(38445)
    outline = [(-32, -37), (3, -37), (17, -33), (24, -21), (26, -3), (24, 17),
               (21, 33), (10, 38), (-9, 38), (-25, 33), (-35, 16), (-36, -20)]
    podium("Flood-worn foundation", outline, [(-.025, 1), (.86, 1), (1.00, .993), (1.34, .993)],
           "monument_weathered")
    podium("Lower terrace and scotia", outline, [(1.30, .943), (1.45, .943), (1.64, .921),
                                                (2.02, .921), (2.15, .933)], "monument_white")
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
