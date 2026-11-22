"""A fallen pair of limestone shaft drums and surrounding architectural rubble."""
import math
import random

import bpy
from mathutils import Euler, Vector
from mathutils.geometry import delaunay_2d_cdt

import vrlib
import vrmat


def limestone(name):
    local_name = f"ruin_debris_a.{name}"
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


def stone(name, vertices, faces, position, rotation, material, smooth=(), old_faces=(), lift=-.026):
    # Seat each piece after rotation, so fractured tips do not hang above the ground.
    matrix = Euler(rotation).to_matrix()
    transformed = [matrix @ Vector(vertex) for vertex in vertices]
    low = min(v.z for v in transformed)
    x, y = position
    vertices = [(v.x + x, v.y + y, v.z - low + lift) for v in transformed]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    vrlib.link_to_source(obj)
    obj.data.materials.append(limestone(material))
    if old_faces:
        obj.data.materials.append(limestone("monument_weathered"))
    for polygon in mesh.polygons:
        polygon.use_smooth = polygon.index in smooth
        polygon.material_index = int(polygon.index in old_faces)
    mesh.set_sharp_from_angle(angle=math.radians(35))
    return obj


def drum(name, position, rotation, r, h, cracked, rng):
    n = 288
    vertices, faces = [], []
    def fault(x, y):
        return (.25*x - .13*y + .29*min(0, x + .47*y + .35*r)
                - .33*max(0, .60*x-y-.30*r) + .11*abs(.84*x+.34*y-.18*r))

    levels = (0, .014, .049, .13, .24, .37, .52, .66, .78, .88, .944, .98, 1)
    rows = len(levels)
    for k, t in enumerate(levels):
        for j in range(n):
            a = math.tau * j / n
            phase = j * 12 / n
            slot = abs(phase-round(phase))/.345
            flute_run = min(1, .18 + 5.8*t, .17 + 3.8*(1-t))
            flutes = .128 * math.sqrt(max(0,1-slot*slot)) * flute_run if cracked else 0
            radius = r * (1 - .055 * t) - flutes
            radius += .003 * math.cos(17 * a - t * 5)
            if not cracked:
                radius += r * (.15 if .13 <= t <= .24 else .09 if .78 <= t <= .88 else 0)
            radius -= (.025 * r if k in (0, rows - 1) else 0)
            if k >= rows-3:
                for center, depth, arc in ((.57,.21,.34), (2.61,.11,.19), (4.09,.27,.63)):
                    off = abs(math.remainder(a-center,math.tau))
                    radius -= depth * max(0,1-off/arc) * (k-rows+4)/3 * (1 if cracked else .42)
            z = h * (t - .5) + (fault(radius*math.cos(a),radius*math.sin(a)) * t if cracked else 0)
            vertices.append((radius * math.cos(a), radius * math.sin(a), z))
    for i in range(rows - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    smooth = range(len(faces))
    faces.append(tuple(reversed(range(n))))
    damaged = len(faces)
    if cracked:
        rim = (rows - 1) * n
        outline = [Vector((x,y)) for x,y,_ in vertices[rim:]]
        points = outline[:]
        for i in range(-7,8):
            for j in range(-7,8):
                x = r*(i*.119+rng.uniform(-.046,.046))
                y = r*(j*.122+rng.uniform(-.046,.046))
                if math.hypot(x,y) < .69*r:
                    points.append(Vector((x,y)))
        coords, _, pieces, source_ids, _, _ = delaunay_2d_cdt(points, [], [tuple(range(n))], 1, 1e-6)
        indices = []
        for (x,y), ids in zip(coords, source_ids):
            if ids and ids[0] < n:
                indices.append(rim + ids[0])
                continue
            trough = max(0, .64 - math.hypot(x/r-.16,(y/r+.13)*1.32))
            step = min(0, -.105+1.34*abs(y-.25*x+.17*r))
            z = h/2 + fault(x,y) - .43*r*trough + step + rng.uniform(-.025,.025)
            indices.append(len(vertices))
            vertices.append((x,y,z))
        faces.extend(tuple(indices[j] for j in face) for face in pieces)
    else:
        faces.append(tuple(range((rows - 1) * n, rows * n)))
    stone(name, vertices, faces, position, rotation, "monument_white", smooth,
          range(damaged, len(faces)) if cracked else ())


def rubble(name, position, dims, rng, dressed, lift=-.025):
    w, d, h = (a / 2 for a in dims)
    vertices = []
    shape = ((-.87,-1),(.71,-1),(1,-.81),(1,.68),(.73,1),(-.85,1),(-1,.83),(-1,-.88))
    notch = int(abs(position[0]*21 + position[1]*15)) % len(shape)
    for j, z in enumerate((-h, -.92*h, .66*h, h)):
        for i, (a, b) in enumerate(shape):
            f = (.97,1,1.04 if dressed else 1,.96 if dressed else 1)[j]
            cut = (.28*max(0, a+.51*b) - .24*max(0,-b-a)) if j>1 else 0
            if j == 3 and i == notch:
                f -= .14
                cut -= .22
            vertices.append((w*(f*a + rng.uniform(-.016,.016)+(.12*max(0,b) if j>1 else 0)),
                             d*(f*b + rng.uniform(-.018,.018)),
                             z + h*(cut + (rng.uniform(-.12,.12) if j==3 else 0))))
    faces = [tuple(reversed(range(8)))]
    for k in range(3):
        for j in range(8):
            a, b = 8 * k + j, 8 * k + (j + 1) % 8
            faces.append((a, b, b + 8, a + 8))
    faces.extend(((24,25,26,27), (24,27,28,29), (24,29,30,31)))
    obj = stone(name, vertices, faces, position, (rng.uniform(-.22, .22), rng.uniform(-.17, .17),
                                                  rng.uniform(-math.pi, math.pi)),
                "monument_white" if dressed else "monument_weathered",
                old_faces=range(len(faces)-3,len(faces)) if dressed else (), lift=lift)
    bevel = obj.modifiers.new("Small edge losses", "BEVEL")
    bevel.width, bevel.segments = min(dims) * .026, 2
    bevel.angle_limit = math.radians(19)
    obj.modifiers.new("Broad face normals", "WEIGHTED_NORMAL")


def build():
    rng = random.Random(7301)
    drum("Fractured fluted drum", (-1.73,-.40), (1.36,.25,1.83), 1.13, 2.18, True, rng)
    drum("Separated shaft drum", (.72,.22), (1.39,-.34,1.91), 1.02, 1.57, True, rng)
    drum("Broken neck moulding", (2.47,.77), (.99,.16,1.15), .81, .59, False, rng)
    rubble("Dislodged cornice shingle wedged on shaft", (.85,-.39), (.91,.52,.26), rng, True, lift=.42)
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
