"""A long mineral blade along an exposed, faulted bedding plane."""
import math
import random

import bpy
from mathutils import Vector

import vrlib
import vrmat


def mesh(name, rings, material, rounding):
    n = len(rings[0])
    faces = [tuple(reversed(range(n)))]
    for level in range(len(rings) - 1):
        a = level * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a+i, a+j, a+j+n, a+i+n))
    faces.append(tuple(range((len(rings)-1)*n, len(rings)*n)))
    data = bpy.data.meshes.new(name)
    data.from_pydata([p for ring in rings for p in ring], [], faces)
    data.update()
    ob = vrlib.link_to_source(bpy.data.objects.new(name, data))
    data.materials.append(vrmat.get(material))
    if rounding:
        bevel = ob.modifiers.new("Weathered arrises", "BEVEL")
        bevel.width, bevel.segments = rounding, 3
        bevel.limit_method = "ANGLE"
    return ob


def fissure_bank(name, outline, surface, fall, phase):
    cx = sum(x for x, _ in outline) / len(outline)
    cy = sum(y for _, y in outline) / len(outline)
    rings = []
    for z, radius, drift in ((-.048, .89, 0), (0, 1, 0), (.15, 1, 0), (.20, .965, .02),
                             (.33, 1.015, .025), (.48, .985, .06), (.53, .92, .07),
                             (.60, .955, .085), (.73, .89, .09), (.77, .845, .10),
                             (.91, .84, .13), (1, .74, .14), (1.035, .56, .15), (1.05, .31, .15)):
        rings.append([(cx + (radius+(.20*min(z,1) if abs(x)<.7 else 0))*(x-cx) + drift*fall,
                       cy + radius*(y-cy) + drift*.25,
                       z if z <= 0 else z * surface[i] + .022*z*math.sin(i*2.1+z*16+phase))
                      for i, (x, y) in enumerate(outline)])
    ob = mesh(name, rings, "canyon_layered", .031)
    ob.data.materials.append(vrmat.get("monument_weathered"))
    for face in ob.data.polygons:
        if (face.index - 1) // len(outline) in (3, 6, 9):
            face.material_index = 1


def blade(name, base, width, height, lean, roll, rng):
    axis = Vector((*lean, 1)).normalized()
    u = Vector((0, 1, 0)).cross(axis).normalized()
    v = axis.cross(u)
    profile = [(1, 0), (.53, .89), (-.54, .90), (-1, -.06), (-.46, -.82), (.46, -.91)]
    spokes = [u*(x*math.cos(roll)-y*math.sin(roll)) + v*(x*math.sin(roll)+y*math.cos(roll))*.77
              for x, y in profile]
    heights = [.79, .72, .66, .71, .84, .87]
    waviness = [rng.uniform(.94, 1.07) for _ in profile]
    rings = []
    for t, r, shift in ((0, .69, 0), (.085, .96, -.06), (.25, 1.04, 0),
                        (.47, .99, -.08), (.75, 1, .04), (.94, .38, .21),
                        (1, .095, .26)):
        rings.append([Vector(base) + axis*(height*(heights[i] if t == .75 else t))
                      + width*(r*waviness[i]*s + shift*u) for i, s in enumerate(spokes)])
    mesh(name, rings, "violet_crystal", min(.017, width*.035))


def talus(rng, index, x, y, r, h, z):
    n = 7
    angles = [i*math.tau/n + rng.uniform(-.16,.16) for i in range(n)]
    outline = [rng.uniform(.67, 1.18) for _ in angles]
    rings = [[(x+r*(s*outline[i]*math.cos(a)+.10*f), y+r*.68*s*outline[i]*math.sin(a),
               max(-.051, z+(f+.1*f*math.sin(a*2))*h)) for i,a in enumerate(angles)]
             for f, s in ((-.12,.7),(.10,1),(.41,.96),(.62,.99),(.86,.73),(1,.44))]
    mesh(f"Fault scree {index:02}", rings, "canyon_layered" if index%4 else "mossy_rock", min(.037, r*.11))


def build():
    rng = random.Random(761308)
    fissure_bank("Uplifted west bank", [(-3.3,.08),(-2.51,-1.17),(-1.47,-1.75),(-.65,-1.9),
                 (-.16,-.97),(-.35,-.18),(.02,.66),(-.12,1.45),(-1.02,1.86),(-2.13,1.48),(-3.01,.98)],
                 [.26,.43,.65,1.18,1.66,1.59,1.58,1.35,.90,.48,.32], -1, .65)
    fissure_bank("Downthrown east bank", [(.61,-1.67),(1.45,-1.52),(2.47,-1.35),(3.08,-.58),
                 (3.13,.38),(2.32,1.29),(1.25,1.66),(.31,1.46),(.60,.73),(.29,.08),(.53,-.67)],
                 [.67,.49,.37,.21,.37,.42,.67,.97,1.07,.99,.93], 1, .27)
    blade("Main spire", (-.03,-.31,.53), .78, 6.94, (.15,.075), .19, rng)
    blade("Broken secondary blade", (-.09,.31,.63), .43, 3.74, (-.31,.23), .71, rng)
    blade("Downthrown fang", (.41,.07,.53), .42, 2.83, (.52,-.16), .86, rng)
    blade("Front seam tongue", (.04,-.86,.41), .27, 1.62, (-.17,-.62), .30, rng)
    blade("Back seam tongue", (.29,.81,.37), .24, 1.37, (.30,.48), 1.1, rng)
    for i in range(59):
        a = rng.uniform(0, math.tau)
        rf = rng.uniform(.77, 1.08)
        x, y = 2.98*rf*math.cos(a), 1.75*rf*math.sin(a)
        r = rng.uniform(.075,.37)*(1.65 if i<11 else .63)
        talus(rng, i, x, y, r, r*rng.uniform(.47,1.30), -.012)
    for i in range(12):
        y = -.97 + i*.177
        x = .16+.14*math.sin(y*3.6)
        talus(rng, i+59, x,y,rng.uniform(.15,.29),rng.uniform(.24,.53),0)
        if i % 3 == 0:
            blade(f"Seam splinter {i:02}", (x,y,.21), rng.uniform(.065,.13), rng.uniform(.30,.72),
                  (rng.uniform(-.4,.4),rng.uniform(-.35,.35)),rng.uniform(0,math.tau),rng)
    for ob in vrlib.source_objects():
        ob.rotation_euler.z = math.radians(-48)
