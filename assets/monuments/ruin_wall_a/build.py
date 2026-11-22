"""A fractured retaining wall with surviving steps up to its rear walk."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    local_name = f"ruin_wall_a.{name}"
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
    grain_scale = 1

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


def block(name, x, y, z, length, depth, height, rng, stone, fracture=0, wear=.025, tilt=0):
    c = min(length, depth) * (.13 if fracture else .036)
    w, d = length / 2, depth / 2
    outline = [(-w + c, -d), (w - c, -d), (w, -d + c), (w, d - c),
               (w - c, d), (-w + c, d), (-w, d - c), (-w, -d + c)]
    outline = [(a + rng.uniform(-wear, wear), b + rng.uniform(-wear, wear)) for a, b in outline]
    vertices = []
    for i, (a, b) in enumerate(outline):
        vertices.append((x + a, y + b, z))
    fault = rng.choice((-1, 1))
    notch = int(abs(x*17 + z*31 + y*7)) % 8
    for i, (a, b) in enumerate(outline):
        loss = fracture * (.12 + .61 * max(0, fault * a / w) + .18 * max(0, b / d) + rng.uniform(0, .10))
        spall = min(.10, height * .14) if i == notch else 0
        vertices.append((x + a*(1-spall) + rng.uniform(-wear, wear),
                         y + b*(1-spall) + rng.uniform(-wear, wear),
                         z + height - loss - spall + tilt * a / w))
    faces = [tuple(reversed(range(8)))]
    faces.extend((i, (i + 1) % 8, 8 + (i + 1) % 8, 8 + i) for i in range(8))
    if fracture:
        for a, b in ((-.32, -.38), (.37, .18)):
            vertices.append((x + w * a, y + d * b,
                             z + height - fracture * (.24 + .6 * max(0, fault * a))))
        faces.extend((8+i, 8+(i+1)%8, 16 if i in (0, 5, 6, 7) else 17) for i in range(8))
        faces.extend(((9, 17, 16), (13, 16, 17)))
    else:
        faces.append(tuple(range(8, 16)))
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    vrlib.link_to_source(obj)
    obj.data.materials.append(vrmat.get(stone) if stone == "mossy_rock" else limestone(stone))
    bevel = obj.modifiers.new("Worn arrises", "BEVEL")
    bevel.width, bevel.segments = min(wear * .43, height * .11), 2
    bevel.angle_limit = math.radians(18)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(13052)
    white, old = "monument_white", "monument_weathered"
    block("Inset retaining bed", -.05, -1, -.035, 9.55, 1.26, .95, rng, old)
    schedule = [
        (0, .54, ((-5, -3.61, -2.05, -.04, 1.32, 2.89, 4.86),)),
        (.52, .81, ((-4.88, -3.03, -1.0, .75, 2.22, 3.92), (4.4, 4.85))),
        (1.31, .46, ((-4.86, -3.72, -2.0, -.36, .73), (1.41, 2.58, 3.81))),
        (1.75, .88, ((-4.79, -2.98, -1.29, .27), (2.29, 3.25, 3.72))),
        (2.61, .59, ((-4.79, -3.57, -2.19, -.82), (2.78, 3.65))),
        (3.18, .74, ((-4.70, -3.15, -1.75, -.99),)),
        (3.90, .52, ((-4.74, -4.16, -2.75, -1.99),)),
        (4.38, .54, ((-4.70, -4.13, -3.03),)),
    ]
    for course, (z, h, runs) in enumerate(schedule):
        for run, joints in enumerate(runs):
            for i, (a, b) in enumerate(zip(joints, joints[1:])):
                terminal = i >= len(joints) - 2
                exposed = course >= 6 or run > 0 or (terminal and course in (2, 4, 5))
                damaged = h * rng.uniform(.17, .62) if exposed else 0
                block(f"Retaining course {course} run {run} stone {i}", (a + b) / 2,
                      -1.09 + .044*course + rng.uniform(-.065, .065), z, b-a-.026,
                      1.95-course*.063, h, rng, old if course == 0 else white, fracture=damaged,
                      wear=.027 if exposed else .016, tilt=rng.uniform(-.064, .061) if exposed else 0)
            a, b = joints[0] + .09, joints[-1] - .09
            block(f"Recessed hearting {course} run {run}", (a+b)/2, -.93+.04*course,
                  max(-.035,z-.20), b-a, 1.27-course*.053, .268, rng, old, wear=.011)
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
                              (-3.6, -2.35, .24, .19, .17), (1.14,-2.11,.88,.46,.39),
                              (2.34,-2.15,.54,.34,.34), (3.75,-1.96,1.12,.64,.49),
                              (-.12,-2.04,.56,.36,.22), (.86,-2.53,.22,.19,.16))):
        x, y, l, d, h = spec
        block(f"Dislodged fragment {i}", x, y, -.02, l, d, h, rng, old if i%3==0 else white,
              fracture=h*.72, wear=.017, tilt=h*.076)
    for seed, (x, y) in enumerate(((-3.83,-2.02),(-.77,-2.01),(1.22,-2.09),(3.02,-2.04))):
        for i in range(9):
            block(f"Groundside moss cluster {seed} fragment {i}", x+rng.uniform(-.18,.18),
                  y+rng.uniform(-.037,.037), -.007, rng.uniform(.035,.092),
                  rng.uniform(.041,.091), rng.uniform(.017,.044), rng, "mossy_rock",
                  fracture=.012, wear=.003)
