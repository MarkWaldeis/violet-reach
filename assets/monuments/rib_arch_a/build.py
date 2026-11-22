"""Six hooked, keeled limestone blades on a shared terraced foundation."""
import math
import random

import bpy
from mathutils import Vector

import vrlib
import vrmat


def limestone(name):
    local_name = f"rib_arch_a.{name}"
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
    coords = next(n for n in nodes if n.type == "TEX_COORD").outputs["Object"]
    grain_scale = .30

    def noise(scale, detail):
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        links.new(coords, node.inputs["Vector"])
        return node.outputs["Fac"]

    def ramp(source, lo, hi, low, high):
        node = nodes.new("ShaderNodeValToRGB")
        for stop, position, color in zip(node.color_ramp.elements, (lo, hi), (low, high)):
            stop.position = position
            stop.color = (*(color if isinstance(color, tuple) else (color,) * 3), 1)
        links.new(source, node.inputs["Fac"])
        return node.outputs["Color"]

    def mix(factor, first, second, blend="MIX"):
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = blend
        if isinstance(factor, (int, float)):
            node.inputs["Fac"].default_value = factor
        else:
            links.new(factor, node.inputs["Fac"])
        for value, socket in zip((first, second), ("Color1", "Color2")):
            if isinstance(value, tuple):
                node.inputs[socket].default_value = (*value, 1)
            else:
                links.new(value, node.inputs[socket])
        return node.outputs["Color"]

    cool = tuple(c * k for c, k in zip(white, (.94, .974, 1.020)))
    cream = tuple(c * k for c, k in zip(white, (1.005, .965, .895)))
    temperature = noise(.34 * grain_scale, 2)
    tone = ramp(temperature, .15, .86, cool, cream)
    random_tint = nodes.new("ShaderNodeObjectInfo").outputs["Random"]
    tone = mix(.24, tone, ramp(random_tint, 0, 1, cream, cool))

    pores = next(n for n in nodes if n.type == "TEX_VORONOI")
    pores.inputs["Scale"].default_value = 27 * grain_scale
    grain = noise(13 * grain_scale, 2)
    pits = ramp(pores.outputs["Distance"], .12, .31, .36, 1)
    deposits = ramp(grain, .23, .79, .80, 1)
    tone = mix(.72, tone, mix(.54, deposits, pits, "MULTIPLY"), "MULTIPLY")

    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 6
    ao.inputs["Distance"].default_value = (.36 if weathered else .19) / grain_scale
    strength = .68 if weathered else .36
    grime = tuple(a * (1-strength) + b * strength for a, b in zip(white, patina))
    links.new(mix(ao.outputs["AO"], grime, tone), surface.inputs["Base Color"])
    links.new(ramp(grain, .22, .79, .65, .96), surface.inputs["Roughness"])
    surface.inputs["Specular IOR Level"].default_value = .29

    def bump(height, depth, strength):
        node = nodes.new("ShaderNodeBump")
        node.inputs["Distance"].default_value = depth / grain_scale
        node.inputs["Strength"].default_value = strength
        links.new(height, node.inputs["Height"])
        return node

    sand = bump(noise(69 * grain_scale, 2), .006, .58)
    etch = bump(mix(.78, grain, pits, "MULTIPLY"), .035, .8)
    links.new(sand.outputs["Normal"], etch.inputs["Normal"])
    links.new(etch.outputs["Normal"], surface.inputs["Normal"])
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

    def sweep(name, start, end, rings, bed, stone):
        vertices = []
        notch = rng.randrange(len(PROFILE)) if not bed else 0
        spall = rng.uniform(.1, .22) if not bed else 0
        skew = rng.uniform(-.001, .001) if not bed else 0
        for progress, flare in rings:
            t = start + (end - start) * progress
            point = spine(t)
            tangent = (spine(t + .0001) - spine(max(0, t - .0001))).normalized()
            roll = (.30 + .19 * t) * fan / 19
            flank = Vector((math.sin(roll), math.cos(roll), 0))
            normal = tangent.cross(flank).normalized()
            flank = normal.cross(tangent)
            taper = 1 - .37 * t ** 1.35 - .13 * t ** 4 + .08 * math.exp(-((t-.970)/.053)**4)
            blade = 1 + .34 * min(1, t / .14) - .15 * t ** 4
            w, d = ((.69, .55) if bed else (1, 1))
            for k, (a, b) in enumerate(PROFILE):
                chip = 1
                if not bed:
                    distance = abs(math.remainder(k - notch, len(PROFILE)))
                    chip -= spall * max(0, 1 - distance / 2.4) * max(0, 1 - progress / .16)
                    distance = abs(math.remainder(k - notch - 8, len(PROFILE)))
                    chip -= spall * .65 * max(0, 1 - distance / 1.7) * max(0, (progress - .86) / .14)
                if not bed:
                    chip += .009 * math.sin(k * 1.9 + progress * 17 + start * 94)
                vertices.append(point + tangent * skew * height * a
                                + (a * width * blade * w * flank + b * depth * d * normal)
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
          True, "monument_weathered")
    start = 0
    course = 0
    while start < 1:
        end = start + rng.uniform(.052, .126) + .095 * start
        if end > .92:
            end = 1
        gap = rng.uniform(.0016, .0025)
        crown = 1.035 if end == 1 else rng.uniform(.96, 1.07)
        shoulder = rng.uniform(.015, .045)
        rings = [(j / 22, crown + shoulder * abs(2*j/22-1) ** 2) for j in range(23)]
        rings[0] = (0, crown + shoulder - .035)
        rings[-1] = (1, crown + shoulder - .035)
        sweep(f"Sail {index} dressed course {course:02}", start + (gap if start else 0),
              end - (gap if end < 1 else 0), rings, False,
              "monument_white")
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
