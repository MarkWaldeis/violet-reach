"""An eighteen-metre survey column, with reeded arrises and weathered drum joints."""
import math
import random

import bpy

import vrlib
import vrmat


def limestone(name):
    local_name = f"column_white_a.{name}"
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


def turn_stone(name, profile, rng, stone, fluted=False, wear=.01, sides=288,
               shift=(0, 0), chip=None, petals=0):
    vertices = []
    frequency = 12
    for j, (z, radius, flute) in enumerate(profile):
        for i in range(sides):
            theta = i * math.tau / sides
            pitch = i * frequency / sides
            slot = abs(pitch - round(pitch)) / .36
            hollow = math.sqrt(max(0, 1 - slot * slot))
            surface = (.52 * math.sin(7 * theta + z * .82) +
                       .3 * math.sin(17 * theta - z) + .18 * math.sin(37 * theta + z * 2.2))
            r = radius - (flute * hollow if fluted else 0) + wear * surface
            if petals:
                r += petals * max(0, math.cos(8 * theta)) ** 2 * math.sin(math.pi * j / (len(profile)-1))
            ring_z = z
            if chip is not None and j >= len(profile) - 4:
                a = abs(math.remainder(theta - chip, math.tau))
                loss = max(0, 1 - abs(a - .035 * (len(profile)-1-j)) / .255)
                r -= .15 * loss * (j - len(profile) + 4) / 3
                ring_z -= (.05 * loss if j == len(profile) - 1 else 0)
            r += rng.uniform(-wear * .08, wear * .08)
            vertices.append((shift[0] + r * math.cos(theta), shift[1] + r * math.sin(theta), ring_z))
    faces = [tuple(reversed(range(sides)))]
    for j in range(len(profile) - 1):
        for i in range(sides):
            a, b = j * sides + i, j * sides + (i + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    faces.append(tuple(range(len(vertices) - sides, len(vertices))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(stone))
    for poly in mesh.polygons[1:-1]:
        poly.use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(22 if fluted else 35))


def build():
    rng = random.Random(66517)
    white = "monument_white"
    old = "monument_weathered"
    turn_stone("Dressed circular ground course",
               [(-.028, 2.35, 0), (.09, 2.42, 0), (.32, 2.42, 0), (.40, 2.36, 0),
                (.47, 2.23, 0), (.58, 2.23, 0), (.63, 2.17, 0)], rng, old, wear=.021,
               chip=.27)
    turn_stone("Scotia and foot moulding",
               [(.606, 2.09, 0), (.67, 2.13, 0), (.81, 2.13, 0), (.94, 2.03, 0),
                (1.02, 1.90, 0), (1.12, 1.85, 0), (1.24, 1.87, 0),
                (1.32, 1.94, 0), (1.41, 1.88, 0), (1.48, 1.75, 0)], rng, old, wear=.027)
    heights = (1.46, 3.01, 5.46, 7.66, 9.14, 12.03, 13.81, 16.15, 17.0)
    turn_stone("Recessed bed of drum joints", [(1.4, 1.32, 0), (8, 1.24, 0),
                                                 (16.6, .78, 0), (17.05, .91, 0)], rng, old, sides=64)
    for i, (lo, hi) in enumerate(zip(heights, heights[1:])):
        rings = []
        rows = (0, .015, .047, .09, .14, .22, .32, .45, .56, .68, .78, .88, .93, .97, .987, 1)
        for j, u in enumerate(rows):
            z = lo + .01 + (hi - lo - .026) * u
            t = (z - 1.46) / 15.55
            r = 1.68 - .61 * t + .105 * math.sin(t * math.pi)
            flute = .275 * math.sin(math.pi * min(1, t * 11, (1 - t) * 13) / 2)
            if j in (0, len(rows) - 1):
                r -= .017
            rings.append((z, r, flute))
        turn_stone(f"Shaft drum {i + 1}", rings, rng, white,
                   fluted=True, wear=.006, shift=(.023 * math.sin(i * 2), .025 * math.cos(i * 1.3)),
                   chip=(.74, -.4, 2.12, -1.3, 1.64, -.1, -2.2, 2.75)[i])

    turn_stone("Neck and double astragal",
               [(16.95, 1.035, 0), (16.98, 1.15, 0), (17.035, 1.17, 0),
                (17.09, 1.11, 0), (17.132, 1.11, 0), (17.16, 1.19, 0),
                (17.223, 1.19, 0), (17.25, 1.12, 0)], rng, white, wear=.006)
    turn_stone("Eight folded stone brackets",
               [(17.23, 1.11, 0), (17.30, 1.17, 0), (17.43, 1.28, 0), (17.55, 1.42, 0),
                (17.69, 1.59, 0), (17.81, 1.71, 0), (17.90, 1.77, 0)], rng, white,
               wear=.012, petals=.27)
    turn_stone("Twice-stepped octagonal abacus",
               [(17.86, 1.83, 0), (17.89, 1.93, 0), (17.98, 1.93, 0), (18.04, 2.08, 0),
                (18.22, 2.08, 0), (18.29, 1.98, 0)], rng, white, wear=.012, sides=8)
