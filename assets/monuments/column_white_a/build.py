"""An eighteen-metre survey column, with reeded arrises and weathered drum joints."""
import math
import random

import bpy

import vrlib
import vrmat


def turn_stone(name, profile, rng, stone, fluted=False, wear=.01, sides=120):
    vertices = []
    frequency = 12
    for j, (z, radius, flute) in enumerate(profile):
        for i in range(sides):
            theta = i * math.tau / sides
            rounded_flute = (.5 + .5 * math.cos(frequency * theta)) ** 3
            surface = (.52 * math.sin(7 * theta + z * .82) +
                       .3 * math.sin(17 * theta - z) + .18 * math.sin(37 * theta + z * 2.2))
            r = radius - (flute * rounded_flute if fluted else 0) + wear * surface
            chip = max(0, math.sin(13 * theta + z * .9)) ** 16
            ring_z = z + (wear * (.3 * surface + 1.7 * chip) if j == 0 else 0)
            ring_z -= wear * (1.1 * chip + .5 * surface) if j == len(profile) - 1 else 0
            r += rng.uniform(-wear * .08, wear * .08)
            vertices.append((r * math.cos(theta), r * math.sin(theta), ring_z))
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
    obj.data.materials.append(vrmat.get(stone))
    for poly in mesh.polygons[1:-1]:
        poly.use_smooth = True
    mesh.set_sharp_from_angle(angle=math.radians(32))


def build():
    rng = random.Random(66517)
    white = "monument_white"
    old = "monument_weathered"
    turn_stone("Twelve sided ground course",
               [(.009, 2.35, 0), (.09, 2.42, 0), (.32, 2.42, 0), (.40, 2.36, 0),
                (.47, 2.23, 0), (.58, 2.23, 0), (.63, 2.17, 0)], rng, old, wear=.032, sides=12)
    turn_stone("Scotia and foot moulding",
               [(.606, 2.09, 0), (.67, 2.13, 0), (.81, 2.13, 0), (.94, 2.03, 0),
                (1.02, 1.90, 0), (1.12, 1.85, 0), (1.24, 1.87, 0),
                (1.32, 1.94, 0), (1.41, 1.88, 0), (1.48, 1.75, 0)], rng, old, wear=.027)
    heights = (1.46, 3.33, 5.11, 7.32, 9.62, 11.94, 14.19, 16.28, 17.0)
    turn_stone("Recessed bed of drum joints", [(1.4, 1.49, 0), (8, 1.32, 0),
                                                 (17.05, .98, 0)], rng, old, sides=64)
    for i, (lo, hi) in enumerate(zip(heights, heights[1:])):
        rings = []
        for j in range(15):
            z = lo + .01 + (hi - lo - .021) * j / 14
            t = (z - 1.46) / 15.55
            r = 1.68 - .61 * t + .105 * math.sin(t * math.pi)
            flute = .142 * math.sin(math.pi * min(1, t * 6, (1 - t) * 9) / 2)
            if j in (0, 14):
                r -= .029
            rings.append((z, r, flute))
        turn_stone(f"Shaft drum {i + 1}", rings, rng, old if i == 0 else white,
                   fluted=True, wear=.022 if i in (0, 2, 5, 7) else .011)

    turn_stone("Neck, bowl and overhanging capital",
               [(16.98, 1.03, 0), (17.03, 1.16, 0), (17.12, 1.16, 0),
                (17.17, 1.10, 0), (17.29, 1.10, 0), (17.42, 1.15, 0),
                (17.55, 1.24, 0), (17.67, 1.37, 0), (17.75, 1.55, 0),
                (17.83, 1.55, 0), (17.88, 1.48, 0)], rng, white, wear=.019)
    turn_stone("Crowned abacus", [(17.855, 1.66, 0), (17.905, 1.73, 0), (18.03, 1.73, 0),
                                (18.09, 1.65, 0)], rng, white, wear=.016, sides=12)
