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
    clusters = ramp(noise(3.4 * grain_scale, 3), .29, .66, .10, .96)
    coarse_pits = ramp(pores.outputs["Distance"], .10, .30, .43, 1)
    fine_cells = nodes.new("ShaderNodeTexVoronoi")
    fine_cells.inputs["Scale"].default_value = 84 * grain_scale
    links.new(coords, fine_cells.inputs["Vector"])
    fine_pits = ramp(fine_cells.outputs["Distance"], .08, .24, .60, 1)
    pits = mix(clusters, fine_pits, coarse_pits)
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


def block(name, x, y, z, length, depth, height, rng, stone, fracture=0, wear=.025, tilt=0,
          split=None, pitch=0, yaw=0):
    c = min(length, depth) * (.13 if fracture else .036)
    w, d = length / 2, depth / 2
    outline = [(-w + c, -d), (w - c, -d), (w, -d + c), (w, d - c),
               (w - c, d), (-w + c, d), (-w, d - c), (-w, -d + c)]
    outline = [(a + rng.uniform(-wear, wear), b + rng.uniform(-wear, wear)) for a, b in outline]
    vertices = []
    def point(a, b, height_offset, progress):
        if split is not None:
            low, high = split
            shoulder = (a+w)/length
            skew = math.sin(3.8*x+.6)*b/d
            offset = low+(high-low)*progress + length*(.21*(abs(b/d+.22)-.50)+.21*skew)
            a += shoulder * max(-.88*length, offset)
        return (x + a*math.cos(yaw) - b*math.sin(yaw),
                y + a*math.sin(yaw) + b*math.cos(yaw) - pitch*height_offset,
                z + height_offset + pitch*b)

    for a, b in outline:
        vertices.append(point(a, b, 0, 0))
    fault = rng.choice((-1, 1))
    notch = int(abs(x*17 + z*31 + y*7)) % 8
    for i, (a, b) in enumerate(outline):
        loss = fracture * (.12 + .61 * max(0, fault * a / w) + .18 * max(0, b / d) + rng.uniform(0, .10))
        spall = min(.10, height * .14) if i == notch else 0
        vertices.append(point(a*(1-spall) + rng.uniform(-wear, wear),
                              b*(1-spall) + rng.uniform(-wear, wear),
                              height - loss - spall + tilt * a / w, 1))
    faces = [tuple(reversed(range(8)))]
    split_faces = []
    for i in range(8):
        j = (i+1) % 8
        if split is not None and i in (1, 2, 3):
            split_faces.extend((len(faces), len(faces)+1))
            faces.extend(((i, j, 8+i), (j, 8+j, 8+i)))
        else:
            faces.append((i, j, 8+j, 8+i))
    if fracture:
        for a, b in ((-.32, -.38), (.37, .18)):
            vertices.append(point(w*a, d*b, height - fracture * (.24 + .6 * max(0, fault * a)), 1))
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
    if split_faces:
        obj.data.materials.append(limestone("monument_weathered"))
        for i in split_faces:
            data.polygons[i].material_index = 1
    bevel = obj.modifiers.new("Worn arrises", "BEVEL")
    bevel.width, bevel.segments = min(wear * .43, height * .11), 2
    bevel.angle_limit = math.radians(18)
    obj.modifiers.new("Dressed face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(13052)
    white, old = "monument_white", "monument_weathered"
    block("Inset retaining bed", -.05, -1, -.035, 9.55, 1.26, .95, rng, old)
    schedule = [
        (0, .56, (-5, -3.61, -2.05, -.04, 1.32, 2.25), (3.10, 2.76)),
        (.56, .80, (-4.88, -3.03, -1.0, .75, 1.77), (2.75, 1.98)),
        (1.36, .53, (-4.86, -3.72, -2.0, -.36, .91), (1.98, 2.48)),
        (1.89, .76, (-4.79, -3.65, -2.98, -1.29, -.27), (1.74, .26)),
        (2.65, .60, (-4.79, -3.57, -2.19, -.63), (.31, -.16)),
        (3.25, .68, (-4.70, -3.31, -2.26), (-1.12, -1.03)),
        (3.93, .53, (-4.74, -4.02, -2.90), (-1.04, -2.48)),
        (4.46, .54, (-4.70, -4.13, -3.64), (-2.91, -3.24)),
    ]
    for course, (z, h, joints, (low, high)) in enumerate(schedule):
        limits = (*joints, max(low, high))
        for i, (a, b) in enumerate(zip(limits, limits[1:])):
            if (course, i) == (3, 1):
                continue
            missing_half = (course, i) == (4, 2)
            if missing_half:
                b = a+(b-a)*.58
            tip = i == len(limits)-2
            loose = (course, i) in ((2, 3), (4, 1), (6, 0))
            y = -1.09 + .044*course - (.21 if loose else 0) + rng.uniform(-.073, .073)
            eroded = rng.uniform(.039, .096)
            sloped = (1, .78, .63, .19, .09, .61, .29, .43)[course]
            block(f"Retaining course {course} stone {i}", (a+b)/2, y, z+eroded*.38, b-a-eroded,
                  1.95-course*.063, h-eroded, rng, old if course == 0 else white,
                  fracture=h*(.22+sloped*.36 if tip else .36 if missing_half else .22 if loose or course >= 6 else 0),
                  wear=.030 if tip or loose else .022, tilt=.085 if loose else 0,
                  split=(low-b, high-b) if tip else (.06, -.24) if missing_half else None,
                  pitch=.14 if loose else 0, yaw=-.12 if loose else 0)
            if not missing_half and (course != 3 or i not in (0, 2)):
                end = min(low, high) - .08 if tip else b
                if end - a > .24:
                    block(f"Recessed hearting {course} stone {i}", (a+end)/2, -.97+.04*course,
                          max(-.035,z-.19), end-a-.09, 1.12-course*.045, .30, rng, old, wear=.011)
    block("Split header over breach", -1.07, -.99, 2.46, 1.15, 1.24, .38, rng, white,
          fracture=.27, split=(0, -.62), wear=.019, yaw=.20, pitch=-.10)
    for i, (x, z, length, h) in enumerate(((3.98, -.027, 1.74, .68), (4.36, .61, .94, .69),
                                            (4.49, 1.22, .72, .54), (3.27, .53, .65, .39))):
        block(f"Broken detached return {i}", x, -1.12+.06*i, z, length, 1.59, h, rng,
              old if i == 0 else white, fracture=h*.46, split=(0, -length*.25),
              pitch=.07 if i in (1, 3) else 0, yaw=.07*i)
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
              fracture=h*.68, wear=.017, tilt=h*.076, yaw=rng.uniform(-.56,.56))
    for i, (x, y, z, length, depth, h) in enumerate(((3.67,-2.11,.25,.56,.43,.30),
            (3.94,-2.12,.36,.48,.31,.27), (2.43,-2.34,.11,.53,.31,.32),
            (1.12,-2.17,.19,.47,.40,.38), (1.31,-2.35,.07,.28,.27,.26))):
        block(f"Stacked fall fragment {i}", x, y, z, length, depth, h, rng, white,
              fracture=h*.64, yaw=rng.uniform(-.81,.81), wear=.013)
    for i in range(27):
        x, y = rng.choice(((1.15,-2.42),(2.51,-2.56),(3.74,-2.50)))
        size = rng.uniform(.09,.29)
        block(f"Broken rubble chip {i}", x+rng.uniform(-.57,.57), y+rng.uniform(-.32,.34),
              -.019, size, size*rng.uniform(.63,.91), size*.61, rng, old if i%4==0 else white,
              fracture=size*.30, wear=.006, yaw=rng.uniform(-1,1))
    for seed, (x, y) in enumerate(((-3.83,-2.02),(-.77,-2.01),(1.22,-2.09),(3.02,-2.04))):
        for i in range(9):
            block(f"Groundside moss cluster {seed} fragment {i}", x+rng.uniform(-.18,.18),
                  y+rng.uniform(-.037,.037), -.007, rng.uniform(.035,.092),
                  rng.uniform(.041,.091), rng.uniform(.017,.044), rng, "mossy_rock",
                  fracture=.012, wear=.003)
